import RealityKit
import UIKit
import simd

/// The choreography of a moment: fireworks off the rim, and the strobe and
/// section surge it asks Lighting and Crowd for through the blackboard. Each
/// kind has its own restrained treatment -
///
///   touchdown   fireworks at that end, the banks strobe, the scoring section rises
///   field goal  a short strobe, the section rises
///   safety      as a field goal
///   turnover    no light, no fire: Audio's groan is the whole of it
///
/// Reduce motion keeps the section tint (Crowd reads it from the scene) and
/// drops the strobe, the fireworks and the surge. Reads `visual.moments`.
@MainActor
final class MomentsActor: StadiumActor {
    let name = "moments"
    let root = Entity()
    private var fireworks: [Entity] = []
    private var fireworksUntil: Double = 0

    init() { root.name = "actor.moments" }

    func build(_ c: StadiumContext) {
        clear()
        fireworks.removeAll()
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        guard case .moment(let m) = event, m.celebrates else { return }
        let seconds = c.spec.motion.momentSeconds ?? 4.5
        let big = m.kind == "touchdown"
        let now = c.shared.time
        guard !c.reduceMotion else { return }
        c.shared.surge = (m.side == "away", now + seconds)
        c.shared.strobeUntil = now + (big ? seconds * 0.6 : 1.2)
        if big && !c.tabletop { launchFireworks(c, anchorX: m.anchorX) }
    }

    private func launchFireworks(_ c: StadiumContext, anchorX: Double) {
        let s = c.spec, M = c.look.moments
        fireworks.forEach { $0.removeFromParent() }
        fireworks.removeAll()
        let end = Float(anchorX - 50)
        let nearest = c.shared.banks.sorted { abs($0.x - end) < abs($1.x - end) }.prefix(M.fireworks)
        let team = anchorX > 50 ? s.teams.home : s.teams.away
        fireworksUntil = c.shared.time + M.fireworksSeconds
        for p in nearest {
            let e = Entity()
            e.position = p + SIMD3(0, Float(M.fireworksLift), 0)
            var emitter = ParticleEmitterComponent.Presets.fireworks
            emitter.mainEmitter.color = .evolving(start: .single(StadiumLook.color(team.chip, scale: 1.4)),
                                                  end: .single(StadiumLook.color(s.palette["arc.score"] ?? "#FFD400")))
            emitter.particlesInheritTransform = true
            emitter.isEmitting = true
            e.scale = SIMD3(repeating: Float(M.fireworksScale))
            e.components.set(emitter)
            root.addChild(e)
            fireworks.append(e)
        }
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard !fireworks.isEmpty, frame.time > fireworksUntil else { return }
        for e in fireworks {
            if var emitter = e.components[ParticleEmitterComponent.self], emitter.isEmitting {
                emitter.isEmitting = false
                e.components.set(emitter)
            }
        }
    }
}
