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
    private var fade: (elapsed: Double, duration: Double, swapped: Bool, held: Bool, seat: String?)?
    /// A game change: fading out, swapping at the dark, fading back.
    private var changeover: (elapsed: Double, swapped: Bool, held: Bool, swap: () -> Void)?
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
        var seconds = max(0.1, c.look.experience.camera.seatFadeSeconds * 2)
        #if DEBUG
        // The same stretch the changeover honours, so a screenshot can land
        // inside a seat change too (`-stadiumFadeScale 8`).
        if let k = Double(StadiumShots.argument("-stadiumFadeScale") ?? ""), k > 0 { seconds *= k }
        #endif
        fade = (0, seconds, false, false, id)
    }

    /// Leave one game for another: fade the bowl down, swap the clubs while
    /// nothing can be seen, and fade back.
    ///
    /// The same shape as a seat change, and for the same reason - the wearer
    /// never moves, the world does - but the swap is handed in rather than
    /// being a transform this actor can do itself. The composer calls this
    /// only once it is holding the new scene, so the dark is never a wait for
    /// the network: it is exactly as long as it takes to repaint.
    ///
    /// Returns false when the caller should just swap now: the tabletop, where
    /// there is no bowl around the wearer to fade, and reduce motion, which is
    /// asked for by people for whom a fade is the problem.
    @discardableResult
    func beginChangeover(_ c: StadiumContext?, swap: @escaping () -> Void) -> Bool {
        guard let c, !c.tabletop, !c.reduceMotion else { return false }
        // Already going: take the newer destination and keep the one fade.
        // Two fades over each other would read as a flicker.
        if changeover != nil {
            changeover?.swap = swap
            return true
        }
        changeover = (elapsed: 0, swapped: false, held: false, swap: swap)
        return true
    }

    /// The two curves a dissolve bends along, from
    /// `visual.experience.camera`. The world leaves fast and is gone; it comes
    /// back on a curve that settles rather than arriving at speed. A straight
    /// ramp on an opacity is what makes a dissolve read as a wipe, and at 0.35
    /// s a side it is exactly long enough to notice.
    private static func curves(_ c: StadiumContext) -> (out: String?, back: String?) {
        let camera = c.look.experience.camera
        return (camera.fadeOutEase ?? "out", camera.fadeInEase ?? "smooth")
    }

    var changingOver: Bool { changeover != nil }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        updateChangeover(frame, c)
        guard var fd = fade else { return }
        // The frame the seat changed cost whatever relaying every trail for the
        // new eye cost, and that lands here as this frame's delta. Charging it
        // to the way back would eat the fade; hold the clock for one frame
        // instead. Same rule as the changeover below, same reason.
        if fd.held { fd.held = false } else { fd.elapsed += frame.dt }
        let half = fd.duration / 2
        let curve = Self.curves(c)
        let opacity: Float
        if fd.elapsed < half {
            opacity = Float(1 - SceneMath.ease(fd.elapsed / half, curve.out))
        } else {
            if !fd.swapped {
                seatID = fd.seat
                place(c)
                onSeatChanged?()
                fd.swapped = true
                fd.held = true
                fd.elapsed = half
                c.world.components.set(OpacityComponent(opacity: 0))
                fade = fd
                return
            }
            opacity = Float(SceneMath.ease(min(1, (fd.elapsed - half) / half), curve.back))
        }
        c.world.components.set(OpacityComponent(opacity: opacity))
        if fd.elapsed >= fd.duration {
            c.world.components.remove(OpacityComponent.self)
            fade = nil
        } else {
            fade = fd
        }
    }

    /// Drive the changeover's opacity. A seat fade, if one is also running,
    /// writes opacity after this and wins for its duration; the two never
    /// overlap in practice, because a channel does not change seat and game at
    /// the same instant, and if they did the seat fade is the shorter.
    ///
    /// Two things make this read as a dissolve rather than as a cut.
    ///
    /// **The repaint is not charged to the way back.** `ch.swap()` repaints the
    /// whole bowl in the dark: 0.19 s for clubs seen before and 0.36 s for new
    /// ones (docs/REDZONE.md measured all eight). Whatever it costs arrives as
    /// the *next* frame's delta, and against a 0.35 s rise that delta is the
    /// whole rise - the first frame after the swap computed an opacity of 1 and
    /// the world snapped back from black, so every whip-around ended in a cut.
    /// It only looked right under `-stadiumFadeScale 10`, which is how the
    /// screenshots in docs/REDZONE.md were taken and how it stayed hidden. The
    /// clock holds for the one frame the swap happened in, so the rise starts
    /// from black on the first frame that can actually draw it.
    ///
    /// **Both halves are eased.** A straight ramp on an opacity reads as a
    /// wipe. The curves are `visual.experience.camera`'s.
    private func updateChangeover(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard var ch = changeover else { return }
        var half = max(0.05, c.look.experience.camera.seatFadeSeconds)
        #if DEBUG
        // `-stadiumFadeScale 8`: stretch the changeover so a simulator
        // screenshot, which costs about a second, can land inside a fade that
        // is otherwise over in a third of one.
        if let s = Double(StadiumShots.argument("-stadiumFadeScale") ?? ""), s > 0 { half *= s }
        #endif
        if ch.held { ch.held = false } else { ch.elapsed += frame.dt }
        let curve = Self.curves(c)
        let opacity: Float
        if ch.elapsed < half {
            opacity = Float(1 - SceneMath.ease(ch.elapsed / half, curve.out))
        } else {
            if !ch.swapped {
                ch.swapped = true
                StadiumLog.log.notice("[stadium] changeover: dark at \(ch.elapsed, format: .fixed(precision: 2)) s, swapping")
                ch.swap()
                ch.held = true
                ch.elapsed = half
                c.world.components.set(OpacityComponent(opacity: 0))
                changeover = ch
                return
            }
            opacity = Float(SceneMath.ease(min(1, (ch.elapsed - half) / half), curve.back))
        }
        c.world.components.set(OpacityComponent(opacity: opacity))
        if ch.elapsed >= half * 2 {
            c.world.components.remove(OpacityComponent.self)
            changeover = nil
            // What the wearer actually saw of the way back. Beside the
            // `relivery` line it is the whole of the bug this pairs with: a
            // repaint of 0.20-0.41 s against a rise of 0.35 s, charged to the
            // rise, left nothing of it. `tools/measure_changeover.py` reads
            // both lines out of the simulator log.
            StadiumLog.log.notice("[stadium] changeover: back up over \(half, format: .fixed(precision: 2)) s")
        } else {
            changeover = ch
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
            // The model sits on the table, not over it.
            if c.look.experience.baseplate.groundingShadow == true,
               !stage.components.has(GroundingShadowComponent.self) {
                stage.components.set(GroundingShadowComponent(castsShadow: true))
            }
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

    /// The table model's plinth: dark glossy stone under the bowl, a bevelled
    /// edge that catches the room's light, a lit rim, and under the bevel a
    /// thin edge light in each club's colour, home along the home half.
    private func buildBaseplate(_ c: StadiumContext) {
        let s = c.spec, P = c.look.experience.baseplate
        let shape = s.bowl.shape
        let outer = ((c.tiers.last?.outer ?? 36) + 3) * P.marginScale
        let bevel = P.bevelYards ?? 0
        let yards = Float(P.thicknessMeters / max(1e-6, s.presentation.tabletop.metersPerYard))
        let S = 96
        var top = MeshBuilder(), band = MeshBuilder(), chamfer = MeshBuilder()
        var rim: [SIMD3<Float>] = [], homeEdge: [SIMD3<Float>] = [], awayEdge: [SIMD3<Float>] = []
        let y = Float(-0.05), drop = Float(bevel) * 0.5
        for k in 0..<S {
            let t0 = Double(k) / Double(S) * 2 * .pi, t1 = Double(k + 1) / Double(S) * 2 * .pi
            let a = SceneMath.bowlPoint(shape, offset: outer, angle: t0), b = SceneMath.bowlPoint(shape, offset: outer, angle: t1)
            let A = SceneMath.bowlPoint(shape, offset: outer + bevel, angle: t0)
            let B = SceneMath.bowlPoint(shape, offset: outer + bevel, angle: t1)
            top.quad(SIMD3(0, y, 0), SIMD3(Float(b.x), y, Float(b.z)), SIMD3(Float(a.x), y, Float(a.z)), SIMD3(0, y, 0),
                     normal: SIMD3(0, 1, 0))
            if bevel > 0 {
                chamfer.quad(SIMD3(Float(a.x), y, Float(a.z)), SIMD3(Float(b.x), y, Float(b.z)),
                             SIMD3(Float(B.x), y - drop, Float(B.z)), SIMD3(Float(A.x), y - drop, Float(A.z)))
            }
            band.quad(SIMD3(Float(A.x), y - drop - yards, Float(A.z)), SIMD3(Float(B.x), y - drop - yards, Float(B.z)),
                      SIMD3(Float(B.x), y - drop, Float(B.z)), SIMD3(Float(A.x), y - drop, Float(A.z)))
            rim.append(SIMD3(Float(a.x), y + 0.05, Float(a.z)))
            // The home sideline is +z; its half of the edge takes the home colour.
            let edge = SIMD3(Float(A.x), y - drop - yards * 0.5, Float(A.z))
            if A.z >= 0 { homeEdge.append(edge) } else { awayEdge.append(edge) }
        }
        rim.append(rim[0])
        let stone = s.palette["baseplate"] ?? "#101216"
        root.addChild(top.entity("baseplate.top", StadiumLook.solid(stone, roughness: P.topRoughness ?? 0.22, metallic: P.topMetallic ?? 0.08, cull: false)))
        root.addChild(band.entity("baseplate.band", StadiumLook.solid(stone, roughness: P.bandRoughness ?? 0.45, metallic: P.bandMetallic ?? 0.05, cull: false)))
        if !chamfer.isEmpty {
            root.addChild(chamfer.entity("baseplate.bevel", StadiumLook.solid(stone, roughness: P.bevelRoughness ?? 0.16, metallic: P.bevelMetallic ?? 0.15, cull: false)))
        }
        var ring = MeshBuilder()
        ring.tube(rim, radius: Float(P.rimRadiusYards), sides: 6)
        root.addChild(ring.entity("baseplate.rim", StadiumLook.glow(s.palette["baseplate.rim"] ?? "#FFE9C2",
                                                                    opacity: P.rimOpacity, texture: nil)))
        if let opacity = P.edgeOpacity {
            for (pts, team) in [(homeEdge, s.teams.home), (awayEdge, s.teams.away)] where pts.count > 1 {
                var edge = MeshBuilder()
                edge.tube(pts, radius: Float(P.rimRadiusYards) * 0.7, sides: 6)
                root.addChild(edge.entity("baseplate.edge.\(team.abbr)", StadiumLook.glow(team.chip, opacity: opacity, texture: nil)))
            }
        }
    }
}
