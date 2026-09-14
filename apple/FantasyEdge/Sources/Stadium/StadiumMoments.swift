import RealityKit
import UIKit
import simd

/// What happens when the game does something: the stadium's light, fire and
/// sound. Each kind of moment has its own restrained treatment -
///
///   touchdown   fireworks off the rim at that end, the banks strobe, the
///               scoring section rises, the roar comes from their seats
///   field goal  a short strobe, a smaller roar, the PA chime
///   safety      as a field goal
///   turnover    no light: a groan from the side that lost the ball
///   red zone    entering it rings the PA chime from the press box
///
/// Reduce motion keeps the tint and the sound and drops the strobe, the
/// fireworks and the surge.
@MainActor
final class StadiumMoments {
    let root = Entity()
    private let tabletop: Bool
    private var bed: [AudioPlaybackController] = []
    private let voice = Entity()
    private let chimeVoice = Entity()
    private var fireworks: [Entity] = []
    private var fireworksUntil: Double = 0
    private var lastMoment: String?
    private var lastRedZone = false
    private var strobeUntil: Double = 0
    private var time: Double = 0
    private var started = false
    var muted = false {
        didSet { bed.forEach { muted ? $0.pause() : $0.play() } }
    }

    init(tabletop: Bool) {
        self.tabletop = tabletop
        root.name = "moments"
        root.addChild(voice)
        root.addChild(chimeVoice)
    }

    func build(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, statics: StadiumStatic, tiers: [SceneSpec.Tier]) {
        fireworks.forEach { $0.removeFromParent() }
        fireworks.removeAll()
        bed.forEach { $0.stop() }
        bed.removeAll()
        lastMoment = s.activeMoment?.playId
        lastRedZone = s.status.redZone
        guard !tabletop else { return }
        // The crowd bed, from a few points round the lower bowl.
        if let sound = assets.audio["crowdBed"], let lower = tiers.first {
            let m = (lower.inner + lower.outer) / 2
            for k in 0..<max(1, look.audio.bedEmitters) {
                let t = Double(k) / Double(max(1, look.audio.bedEmitters)) * 2 * .pi + 0.4
                let p = SceneMath.bowlPoint(s.bowl.shape, offset: m, angle: t)
                let e = Entity()
                e.position = SIMD3(Float(p.x), Float(SceneMath.tierHeight(lower, offset: m)), Float(p.z))
                e.components.set(SpatialAudioComponent(gain: Audio.Decibel(look.audio.bedGain)))
                root.addChild(e)
                let c = e.playAudio(sound)
                if muted { c.pause() }
                bed.append(c)
            }
        }
        chimeVoice.position = statics.pressBox
        chimeVoice.components.set(SpatialAudioComponent(gain: Audio.Decibel(look.audio.chimeGain)))
        started = true
    }

    func update(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, statics: StadiumStatic,
                crowd: StadiumCrowd?, reduceMotion: Bool) {
        defer { lastRedZone = s.status.redZone }
        if s.status.redZone && !lastRedZone && started {
            play("chime", on: chimeVoice, gain: look.audio.chimeGain, assets: assets)
        }
        guard let m = s.activeMoment, m.playId != lastMoment else {
            if s.activeMoment == nil { lastMoment = nil }
            return
        }
        lastMoment = m.playId
        let seconds = s.motion.momentSeconds ?? 4.5
        let home = m.anchorX > 50
        let stands = home ? statics.standsBehind.away : statics.standsBehind.home
        switch m.kind {
        case "turnover":
            // The groan comes from the side that lost it.
            voice.position = home ? statics.standsBehind.home : statics.standsBehind.away
            play("groan", on: voice, gain: look.audio.groanGain, assets: assets)
        default:
            guard m.celebrates else { return }
            let big = m.kind == "touchdown"
            voice.position = stands
            play("roar", on: voice, gain: look.audio.roarGain - (big ? 0 : 6), assets: assets)
            if !big { play("chime", on: chimeVoice, gain: look.audio.chimeGain, assets: assets) }
            crowd?.celebrate(side: m.side, seconds: seconds)
            guard !reduceMotion else { return }
            strobeUntil = time + (big ? seconds * 0.6 : 1.2)
            if big && !tabletop {
                launchFireworks(s, look: look, statics: statics, anchorX: m.anchorX)
            }
        }
    }

    private func play(_ id: String, on e: Entity, gain: Double, assets: StadiumAssets) {
        guard !muted, !tabletop, let sound = assets.audio[id] else { return }
        e.components.set(SpatialAudioComponent(gain: Audio.Decibel(gain)))
        _ = e.playAudio(sound)
    }

    private func launchFireworks(_ s: SceneSpec, look: SceneSpec.Look, statics: StadiumStatic, anchorX: Double) {
        fireworks.forEach { $0.removeFromParent() }
        fireworks.removeAll()
        let end = Float(anchorX - 50)
        let nearest = statics.banks.sorted { abs($0.x - end) < abs($1.x - end) }.prefix(look.moment.fireworks)
        let team = (anchorX > 50 ? s.teams.home : s.teams.away)
        fireworksUntil = time + look.moment.fireworksSeconds
        for p in nearest {
            let e = Entity()
            e.position = p + SIMD3(0, Float(look.moment.fireworksLift), 0)
            var emitter = ParticleEmitterComponent.Presets.fireworks
            emitter.mainEmitter.color = .evolving(start: .single(StadiumLook.color(team.chip, scale: 1.4)),
                                                  end: .single(StadiumLook.color(s.palette["arc.score"] ?? "#FFD400")))
            emitter.particlesInheritTransform = true
            emitter.isEmitting = true
            e.scale = SIMD3(repeating: Float(look.moment.fireworksScale))
            e.components.set(emitter)
            root.addChild(e)
            fireworks.append(e)
        }
    }

    /// The banks pulse while a celebration strobes, then settle.
    func tick(_ dt: Double, statics: StadiumStatic, look: SceneSpec.Look) {
        time += dt
        if !fireworks.isEmpty && time > fireworksUntil {
            for e in fireworks {
                if var emitter = e.components[ParticleEmitterComponent.self], emitter.isEmitting {
                    emitter.isEmitting = false
                    e.components.set(emitter)
                }
            }
        }
        let strobing = time < strobeUntil
        for g in statics.glows {
            let pulse: Float
            if strobing {
                let wave = 0.5 + 0.5 * sin(time * 2 * .pi * look.moment.strobeHz)
                pulse = 1 + Float(wave * look.moment.strobeGain)
            } else {
                pulse = 1
            }
            if g.scale.x != pulse { g.scale = SIMD3(repeating: pulse) }
        }
    }
}
