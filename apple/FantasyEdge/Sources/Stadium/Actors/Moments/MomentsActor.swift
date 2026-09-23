import RealityKit
import UIKit
import simd

/// The choreography of the game's big beats.
///
/// A moment arrives once (the composer dedupes by play) and this actor plays
/// its schedule from `visual.moments.timeline[kind]` on the frame clock:
///
///   whistle    Audio's (it reads the same timeline)
///   surge      the scoring side's section rises: `shared.surge`, read by
///              Crowd and by Lighting's wash
///   strobe     the banks flash for `strobeSeconds`: `shared.strobeUntil`
///   particles  a burst off the rim over the scoring end: fireworks, sparks
///   banner     drawn by Broadcast/Experience from `visual.moments.banner`
///   chime      Audio's
///   settle     everything above has ended
///
/// Reduce motion plays the same beats without movement: the section holds its
/// wash and the banks hold a steady glow for `reduceMotion.glowSeconds`
/// (Lighting holds rather than flashes while reduce motion is on); no
/// particles. A turnover lights nothing: the side that took the ball surges,
/// and the rest is Audio's.
///
/// Cues - the horn, the two-minute warning, third down, the final whistle -
/// arrive through `cue(_:_:)` once the composer delivers them; the red-zone
/// crossing already arrives as `.redZoneEntered`. See
/// docs/actors/moments-audio.md for the hooks this actor asks of others.
@MainActor
final class MomentsActor: StadiumActor {
    let name = "moments"
    let root = Entity()

    private struct Step {
        let at: Double
        let run: @MainActor () -> Void
    }
    private var steps: [Step] = []
    private struct Shell {
        let entity: Entity
        let stopAt: Double
        let removeAt: Double
    }
    private var shells: [Shell] = []
    /// The last cue played, so a cue repeated across polls plays once.
    private var lastCue: String?
    /// When the composer's own red-zone event fired: the server's red-zone cue
    /// for the same crossing arrives a poll later and must not play twice.
    private var redZoneAt = -Double.infinity

    init() { root.name = "actor.moments" }

    func build(_ c: StadiumContext) {
        clear()
        steps.removeAll()
        shells.removeAll()
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        switch event {
        case .moment(let m):
            choreograph(m, c)
        case .redZoneEntered:
            redZoneAt = c.shared.time
            cue(treatment: "redZone", side: c.spec.status.possession, id: nil, c)
        case .cue(let q):
            cue(treatment: q.treatment, side: q.side, id: q.id, c)
        }
    }

    // MARK: moments

    private func choreograph(_ m: SceneSpec.Moment, _ c: StadiumContext) {
        let M = c.look.moments
        guard let T = M.timeline[m.kind] else { return }
        let now = c.shared.time
        let reduced = c.reduceMotion
        let hold = max(T.settle, c.spec.motion.momentSeconds ?? T.settle)
        let away = m.side == "away"

        // A kick through swings the net behind that end (Sideline reads it).
        if m.kind == "fieldGoal" {
            c.shared.netSway = (m.anchorX, 1.0, now + hold)
        }

        if T.surge >= 0 {
            // The surge still drives Lighting's wash; the crowd itself is
            // told to stand (the scorers, or the side that took the ball) and
            // to groan (the side that gave it up) through Crowd's hooks.
            let side = m.side
            let other = side == "home" ? "away" : "home"
            schedule(now + T.surge) { [c] in
                c.shared.surge = (away, now + hold)
                if T.standSeconds > 0 { c.shared.stand(.side(side), until: c.shared.time + T.standSeconds) }
                if T.groanSeconds > 0 { c.shared.groan(other, until: c.shared.time + T.groanSeconds) }
            }
        }
        if T.strobe >= 0 {
            let seconds = reduced ? (M.reduceMotion.strobe ? T.strobeSeconds : M.reduceMotion.glowSeconds) : T.strobeSeconds
            schedule(now + T.strobe) { [c] in c.shared.strobeUntil = max(c.shared.strobeUntil, c.shared.time + seconds) }
        }
        if T.particles >= 0, let key = M.burstFor[m.kind], key != "none",
           !reduced || M.reduceMotion.particles {
            let team = c.spec.teams.side(m.side)
            schedule(now + T.particles) { [weak self, c] in
                self?.fire(key, overEndX: m.anchorX, team: team, c)
            }
        }
    }

    // MARK: cues

    /// A cue's visual beats: the crowd's part through the blackboard, a
    /// strobe if the treatment asks, a burst (confetti for a home win).
    /// `id` dedupes a cue the server repeats while it holds.
    /// `crowd` is the final cue's `crowd` from the scene: the sections that
    /// stand and the ones that sit. Without it the final falls back to sides.
    func cue(treatment: String, side: String?, id: String?,
             crowd: (stand: [String], sit: [String])? = nil, _ c: StadiumContext) {
        if let id {
            guard id != lastCue else { return }
            lastCue = id
        }
        if treatment == "redZone", id != nil, c.shared.time - redZoneAt < 8 { return }
        guard let T = c.look.moments.cues[treatment] else { return }
        let now = c.shared.time
        let reduced = c.reduceMotion
        // The crowd's part, through Crowd's hooks (Actors/Crowd/CrowdCues.swift).
        // Reduce motion is Crowd's to honour: every cue becomes a still pose.
        let who = side ?? "home"
        switch T.crowd {
        case "stand":
            c.shared.stand(.side(who), until: now + T.seconds)
        case "clap":
            c.shared.stand(.side(who), until: now + T.seconds, clap: true)
        case "final":
            let loser = who == "home" ? "away" : "home"
            if let crowd, !crowd.stand.isEmpty {
                c.shared.stand(.sections(crowd.stand), until: .infinity)
                if !crowd.sit.isEmpty { c.shared.sit(.sections(crowd.sit), until: now + T.seconds) }
            } else {
                c.shared.stand(.side(who), until: .infinity)
                c.shared.sit(.side(loser), until: now + T.seconds)
            }
        default:
            break
        }
        if T.strobeSeconds > 0 {
            let M = c.look.moments
            c.shared.strobeUntil = now + (reduced && !M.reduceMotion.strobe ? M.reduceMotion.glowSeconds : T.strobeSeconds)
        }
        if T.burst != "none", !reduced || c.look.moments.reduceMotion.particles {
            fire(T.burst, overEndX: 50, team: c.spec.teams.side(side), c)
        }
    }

    // MARK: particles

    /// One burst: `shells` emitters, staggered. A point shell opens off the
    /// rim over the end the play finished in; a sheet (`widthYards` > 0)
    /// hangs over the field and rains. Every size and speed is in yards, in
    /// the stage's space, so the tabletop gets the same burst in miniature.
    private func fire(_ key: String, overEndX endX: Double, team: SceneSpec.Team?, _ c: StadiumContext) {
        guard let B = c.look.moments.bursts[key], B.shells > 0 else { return }
        let s = c.spec
        let chip = StadiumLook.color(team?.chip ?? s.palette["arc.score"] ?? "#FFD400", scale: 1.5)
        let gold = StadiumLook.color(s.palette["arc.score"] ?? "#FFD400", scale: 1.2)
        let white = UIColor(white: 1, alpha: 1)
        let now = c.shared.time

        let origins: [SIMD3<Float>]
        if B.widthYards > 0 {
            origins = [SceneMath.local(x: endX, y: B.lift, z: 0)]
        } else {
            origins = rimPoints(near: endX, count: B.shells, c).map { $0 + SIMD3(0, Float(B.lift), 0) }
        }
        for (i, origin) in origins.enumerated() {
            let at = now + Double(i) * B.stagger
            schedule(at) { [weak self, c] in
                guard let self else { return }
                let e = Entity()
                e.name = "moments.\(key).\(i)"
                e.position = origin
                e.components.set(self.emitter(B, colors: (i % 2 == 0 ? chip : gold, i % 3 == 2 ? white : chip)))
                self.root.addChild(e)
                self.shells.append(Shell(entity: e, stopAt: c.shared.time + B.burstSeconds,
                                         removeAt: c.shared.time + B.burstSeconds + B.lifeSpan * 1.6 + 0.5))
            }
        }
    }

    private func emitter(_ B: SceneSpec.Look.MomentBurst, colors: (UIColor, UIColor)) -> ParticleEmitterComponent {
        var p = ParticleEmitterComponent()
        let sheet = B.widthYards > 0
        p.emitterShape = sheet ? .plane : .sphere
        p.emitterShapeSize = sheet ? SIMD3(Float(B.widthYards), 0.5, Float(B.widthYards) * 0.45) : SIMD3(repeating: Float(B.radius * 2))
        p.birthLocation = .surface
        p.birthDirection = sheet ? .world : .normal
        p.emissionDirection = sheet ? SIMD3(0, -1, 0) : SIMD3(0, 1, 0)
        p.speed = Float(B.speed)
        p.speedVariation = Float(B.speed * 0.3)
        p.particlesInheritTransform = true
        p.fieldSimulationSpace = .local
        p.isEmitting = true

        var main = ParticleEmitterComponent.ParticleEmitter()
        main.birthRate = Float(B.birthRate)
        main.birthRateVariation = Float(B.birthRate * 0.1)
        main.lifeSpan = B.lifeSpan
        main.lifeSpanVariation = B.lifeSpan * 0.3
        main.size = Float(B.size)
        main.sizeVariation = Float(B.size * 0.35)
        main.sizeMultiplierAtEndOfLifespan = sheet ? 1 : 0.15
        main.acceleration = SIMD3(0, Float(B.gravity), 0)
        main.dampingFactor = Float(B.damping)
        main.spreadingAngle = Float(B.spreadDegrees * .pi / 180)
        main.blendMode = B.additive ? .additive : .alpha
        main.isLightingEnabled = false
        main.opacityCurve = sheet ? .gradualFadeInOut : .linearFadeOut
        main.color = .evolving(start: .single(colors.0), end: .single(colors.1))
        main.colorEvolutionPower = 1.4
        if sheet {
            main.billboardMode = .free(axis: SIMD3(0, 1, 0), variation: 1)
            main.angularSpeed = 3
            main.angularSpeedVariation = 3
            main.noiseStrength = 0.4
            main.noiseScale = 1
            main.noiseAnimationSpeed = 0.5
        } else {
            main.billboardMode = .billboard
            main.stretchFactor = Float(B.streak)
        }
        p.mainEmitter = main

        if B.sparkle > 0 && !sheet {
            var spark = ParticleEmitterComponent.ParticleEmitter()
            spark.birthRate = Float(40 * B.sparkle)
            spark.lifeSpan = 0.35
            spark.size = Float(B.size * 0.35)
            spark.sizeMultiplierAtEndOfLifespan = 0
            spark.acceleration = SIMD3(0, Float(B.gravity) * 0.5, 0)
            spark.blendMode = .additive
            spark.isLightingEnabled = false
            spark.opacityCurve = .linearFadeOut
            spark.color = .constant(.single(UIColor(white: 1, alpha: 1)))
            p.spawnOccasion = .onUpdate
            p.spawnInheritsParentColor = true
            p.spawnVelocityFactor = 0.1
            p.spawnedEmitter = spark
        }
        return p
    }

    /// Rim positions nearest an end: the banks Lighting publishes, else the
    /// top of the outermost tier drawn, so a burst never waits on Lighting.
    private func rimPoints(near endX: Double, count: Int, _ c: StadiumContext) -> [SIMD3<Float>] {
        let end = Float(endX - 50)
        if !c.shared.banks.isEmpty {
            return Array(c.shared.banks.sorted { abs($0.x - end) < abs($1.x - end) }.prefix(count))
        }
        guard let tier = c.tiers.last else { return [SceneMath.local(x: endX, y: 20)] }
        let shape = c.spec.bowl.shape
        let side: Double = endX > 50 ? 0 : .pi
        return (0..<count).map { k in
            let t = side + (Double(k) - Double(count - 1) / 2) * 0.22
            let p = SceneMath.bowlPoint(shape, offset: tier.outer, angle: t)
            return SIMD3(Float(p.x), Float(SceneMath.tierHeight(tier, offset: tier.outer)), Float(p.z))
        }
    }

    // MARK: clock

    private func schedule(_ at: Double, _ run: @escaping @MainActor () -> Void) {
        steps.append(Step(at: at, run: run))
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        if !steps.isEmpty {
            let due = steps.filter { $0.at <= frame.time }
            steps.removeAll { $0.at <= frame.time }
            for step in due { step.run() }
        }
        guard !shells.isEmpty else { return }
        for shell in shells where frame.time > shell.stopAt {
            if var p = shell.entity.components[ParticleEmitterComponent.self], p.isEmitting {
                p.isEmitting = false
                shell.entity.components.set(p)
            }
        }
        let gone = shells.filter { frame.time > $0.removeAt }
        for shell in gone { shell.entity.removeFromParent() }
        shells.removeAll { frame.time > $0.removeAt }
    }
}
