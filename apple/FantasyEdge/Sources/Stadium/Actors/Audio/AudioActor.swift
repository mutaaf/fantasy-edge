import RealityKit
import simd

/// The sound of the stadium: a crowd bed from a few points round the lower
/// bowl, a roar from the scoring side's seats, a groan from the side that
/// lost the ball, the PA chime from the press box on a field goal and on
/// entering the red zone. Stadium only; the table is silent. Reads
/// `visual.audio` and the positions Bowl publishes.
@MainActor
final class AudioActor: StadiumActor {
    let name = "audio"
    let root = Entity()
    private var bed: [AudioPlaybackController] = []
    private let voice = Entity()
    private let pa = Entity()
    private var muted = false

    init() {
        root.name = "actor.audio"
    }

    func build(_ c: StadiumContext) {
        bed.forEach { $0.stop() }
        bed.removeAll()
        clear()
        root.addChild(voice)
        root.addChild(pa)
        muted = c.shared.muted
        guard !c.tabletop else { return }
        let A = c.look.audio
        if let sound = c.assets.audio["audio.crowdBed"], let lower = c.tiers.first {
            let m = (lower.inner + lower.outer) / 2
            for k in 0..<max(1, A.bedEmitters) {
                let t = Double(k) / Double(max(1, A.bedEmitters)) * 2 * .pi + 0.4
                let p = SceneMath.bowlPoint(c.spec.bowl.shape, offset: m, angle: t)
                let e = Entity()
                e.position = SIMD3(Float(p.x), Float(SceneMath.tierHeight(lower, offset: m)), Float(p.z))
                e.components.set(SpatialAudioComponent(gain: Audio.Decibel(A.bedGain)))
                root.addChild(e)
                let controller = e.playAudio(sound)
                if muted { controller.pause() }
                bed.append(controller)
            }
        }
        pa.position = c.shared.pressBox
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard c.shared.muted != muted else { return }
        muted = c.shared.muted
        bed.forEach { muted ? $0.pause() : $0.play() }
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        let A = c.look.audio
        switch event {
        case .redZoneEntered:
            play("audio.chime", on: pa, gain: A.chimeGain, c)
        case .moment(let m):
            let homeEnd = m.anchorX > 50
            if m.kind == "turnover" {
                voice.position = homeEnd ? c.shared.standsBehind.home : c.shared.standsBehind.away
                play("audio.groan", on: voice, gain: A.groanGain, c)
            } else if m.celebrates {
                let big = m.kind == "touchdown"
                voice.position = homeEnd ? c.shared.standsBehind.away : c.shared.standsBehind.home
                play("audio.roar", on: voice, gain: A.roarGain - (big ? 0 : 6), c)
                if !big { play("audio.chime", on: pa, gain: A.chimeGain, c) }
            }
        }
    }

    private func play(_ key: String, on e: Entity, gain: Double, _ c: StadiumContext) {
        guard !c.shared.muted, !c.tabletop, let sound = c.assets.audio[key] else { return }
        e.components.set(SpatialAudioComponent(gain: Audio.Decibel(gain)))
        _ = e.playAudio(sound)
    }
}
