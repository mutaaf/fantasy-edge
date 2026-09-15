import RealityKit
import simd

/// Where the wearer is: the stage placed at table scale or at a seat, the
/// seat change that fades the world down, turns it about the wearer and
/// fades it back, and the tabletop's lit baseplate. The views, the immersion
/// ramp and the controls live beside this file. Reads
/// `presentation` and `visual.experience`.
///
/// Publishes the wearer's eyes, in local yards, to the blackboard.
@MainActor
final class ExperienceActor: StadiumActor {
    let name = "experience"
    let root = Entity()
    private(set) var seatID: String?
    private var fade: (elapsed: Double, duration: Double, swapped: Bool, seat: String?)?
    /// Called at the dark middle of a seat change, so trails can be relaid
    /// for the new seat's near-seat rule.
    var onSeatChanged: (() -> Void)?

    init() { root.name = "actor.experience" }

    func build(_ c: StadiumContext) {
        clear()
        if c.tabletop { buildBaseplate(c) }
        place(c)
    }

    func apply(_ c: StadiumContext, previous: SceneSpec?) {
        if fade == nil { place(c) }
    }

    func seat(_ c: StadiumContext) -> SceneSpec.SeatOption {
        c.spec.presentation.stadium.seat(seatID)
    }

    /// Sit somewhere else; reduce motion cuts instead of fading.
    func sit(_ id: String?, _ c: StadiumContext?) {
        guard id != seatID else { return }
        guard let c, !c.tabletop, !c.reduceMotion else {
            seatID = id
            if let c { place(c) }
            return
        }
        fade = (0, max(0.1, c.look.experience.camera.seatFadeSeconds * 2), false, id)
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard var fd = fade else { return }
        fd.elapsed += frame.dt
        let half = fd.duration / 2
        let opacity: Float
        if fd.elapsed < half {
            opacity = Float(1 - fd.elapsed / half)
        } else {
            if !fd.swapped {
                seatID = fd.seat
                place(c)
                onSeatChanged?()
                fd.swapped = true
            }
            opacity = Float(min(1, (fd.elapsed - half) / half))
        }
        c.world.components.set(OpacityComponent(opacity: opacity))
        if fd.elapsed >= fd.duration {
            c.world.components.remove(OpacityComponent.self)
            fade = nil
        } else {
            fade = fd
        }
    }

    /// Put the stage where the wearer is. The world turns about them; they never move.
    private func place(_ c: StadiumContext) {
        let s = c.spec, stage = c.stage
        if c.tabletop {
            let t = s.presentation.tabletop
            stage.scale = SIMD3(repeating: Float(t.metersPerYard))
            stage.position = SIMD3(0, Float(t.floor), 0)
            stage.orientation = simd_quatf(angle: 0, axis: SIMD3(0, 1, 0))
            c.shared.seat = nil
        } else {
            let st = s.presentation.stadium
            let eye = c.look.experience.camera.eyeMeters
            let option = st.seat(seatID)
            let placed = SceneMath.seatRoot(option, metersPerYard: st.metersPerYard, eye: eye)
            stage.scale = SIMD3(repeating: Float(st.metersPerYard))
            stage.orientation = placed.orientation
            stage.position = placed.position
            c.shared.seat = SceneMath.local(x: option.x, y: option.y + eye / st.metersPerYard, z: option.z)
        }
    }

    /// The table model's plinth: dark glossy stone under the bowl, a lit rim.
    private func buildBaseplate(_ c: StadiumContext) {
        let s = c.spec, P = c.look.experience.baseplate
        let shape = s.bowl.shape
        let outer = ((c.tiers.last?.outer ?? 36) + 3) * P.marginScale
        let yards = Float(P.thicknessMeters / max(1e-6, s.presentation.tabletop.metersPerYard))
        let S = 96
        var top = MeshBuilder(), band = MeshBuilder()
        var rim: [SIMD3<Float>] = []
        for k in 0..<S {
            let t0 = Double(k) / Double(S) * 2 * .pi, t1 = Double(k + 1) / Double(S) * 2 * .pi
            let a = SceneMath.bowlPoint(shape, offset: outer, angle: t0), b = SceneMath.bowlPoint(shape, offset: outer, angle: t1)
            let y = Float(-0.05)
            top.quad(SIMD3(0, y, 0), SIMD3(Float(b.x), y, Float(b.z)), SIMD3(Float(a.x), y, Float(a.z)), SIMD3(0, y, 0),
                     normal: SIMD3(0, 1, 0))
            band.quad(SIMD3(Float(a.x), y - yards, Float(a.z)), SIMD3(Float(b.x), y - yards, Float(b.z)),
                      SIMD3(Float(b.x), y, Float(b.z)), SIMD3(Float(a.x), y, Float(a.z)))
            rim.append(SIMD3(Float(a.x), y + 0.05, Float(a.z)))
        }
        rim.append(rim[0])
        let stone = s.palette["baseplate"] ?? "#101216"
        root.addChild(top.entity("baseplate.top", StadiumLook.solid(stone, roughness: 0.28, metallic: 0.55, cull: false)))
        root.addChild(band.entity("baseplate.band", StadiumLook.solid(stone, roughness: 0.4, metallic: 0.6, cull: false)))
        var ring = MeshBuilder()
        ring.tube(rim, radius: Float(P.rimRadiusYards), sides: 6)
        root.addChild(ring.entity("baseplate.rim", StadiumLook.glow(s.palette["baseplate.rim"] ?? "#FFE9C2",
                                                                    opacity: P.rimOpacity, texture: nil)))
    }
}
