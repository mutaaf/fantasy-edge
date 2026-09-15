import RealityKit
import simd

extension MeshBuilder {
    /// A flat strip through points, turned at every point to face `view`, so
    /// a trail reads as a line of light with soft edges from wherever it is
    /// seen. u runs `uRange` along the strip by length; v crosses it 0..1.
    mutating func facingStrip(_ pts: [SIMD3<Float>], halfWidth: Float,
                              view: (SIMD3<Float>) -> SIMD3<Float>,
                              uRange: ClosedRange<Float> = 0...1) {
        guard pts.count > 1, halfWidth > 0 else { return }
        var lengths: [Float] = [0]
        for i in 1..<pts.count { lengths.append(lengths[i - 1] + simd_distance(pts[i - 1], pts[i])) }
        let total = max(1e-6, lengths.last!)
        let base = UInt32(positions.count)
        var lastSide = SIMD3<Float>(0, 1, 0)
        for (i, p) in pts.enumerated() {
            let ahead = pts[min(i + 1, pts.count - 1)] - pts[max(i - 1, 0)]
            let t = simd_length(ahead) > 1e-6 ? simd_normalize(ahead) : SIMD3(1, 0, 0)
            let toEye = view(p)
            var side = simd_cross(t, toEye)
            if simd_length(side) < 1e-4 { side = lastSide } else { side = simd_normalize(side) }
            // Keep the strip from flipping over as the view swings past it.
            if simd_dot(side, lastSide) < 0, i > 0 { side = -side }
            lastSide = side
            let u = uRange.lowerBound + (uRange.upperBound - uRange.lowerBound) * lengths[i] / total
            let n = toEye
            positions += [p - side * halfWidth, p + side * halfWidth]
            normals += [n, n]
            uvs += [SIMD2(u, 0), SIMD2(u, 1)]
        }
        for i in 0..<UInt32(pts.count - 1) {
            let a = base + i * 2, b = a + 1, c = a + 2, d = a + 3
            indices += [a, c, b, b, c, d]
        }
    }
}

/// The drive drawn in light: one trail per play, the newest bright, the rest
/// ghosting and thinning with age (`visual.broadcast.trail`).
@MainActor
final class BroadcastTrails {
    let root = Entity()
    private(set) var order: [String] = []
    private var arcs: [String: SceneSpec.Arc] = [:]
    private var entities: [String: Entity] = [:]

    init() { root.name = "broadcast.trails" }

    var count: Int { order.count }
    func has(_ id: String) -> Bool { arcs[id] != nil }

    func clear() {
        root.children.removeAll()
        order.removeAll()
        arcs.removeAll()
        entities.removeAll()
    }

    /// Lay a play down and re-age the drive behind it.
    func add(_ arc: SceneSpec.Arc, _ c: StadiumContext) {
        guard arcs[arc.id] == nil else { return }
        arcs[arc.id] = arc
        order.append(arc.id)
        rebuild(c)
    }

    /// A whole drive laid down at rest, aged once rather than once per play.
    func set(_ list: [SceneSpec.Arc], _ c: StadiumContext) {
        for arc in list where arcs[arc.id] == nil {
            arcs[arc.id] = arc
            order.append(arc.id)
        }
        rebuild(c)
    }

    /// Everything again - after a seat change the strips must face the new eye.
    ///
    /// The newest `age.individual` plays are drawn one by one, each in its
    /// style's colour and faded by its age. Everything older is merged into a
    /// single ghost in `age.historyColor`: two draw parts for the whole back
    /// of the drive rather than two per play, which a fifteen-play drive would
    /// otherwise spend past the actor's budget.
    func rebuild(_ c: StadiumContext) {
        for e in entities.values { e.removeFromParent() }
        entities.removeAll()
        let look = c.look.broadcast.trail
        var historyCore = MeshBuilder(), historyHalo = MeshBuilder()
        for (index, id) in order.enumerated() {
            guard let arc = arcs[id] else { continue }
            let age = order.count - 1 - index
            let g = geometry(arc, age: age, c)
            if age < max(1, look.age.individual) {
                let e = entity(arc, geometry: g, c)
                entities[id] = e
                root.addChild(e)
            } else {
                historyCore.append(g.core)
                historyHalo.append(g.halo)
            }
        }
        if !historyCore.isEmpty {
            let colour = c.spec.palette[look.age.historyColor] ?? "#C9CCD1"
            let holder = Entity()
            holder.name = "trail.history"
            holder.addChild(historyHalo.entity("trail.history.halo",
                StadiumLook.glow(colour, opacity: look.haloOpacity * look.age.historyOpacity, texture: c.assets.texture("broadcast.trailHalo"))))
            holder.addChild(historyCore.entity("trail.history.core",
                StadiumLook.glow(colour, opacity: look.coreOpacity * look.age.historyOpacity, texture: c.assets.texture("broadcast.trailCore"))))
            entities["history"] = holder
            root.addChild(holder)
        }
    }

    private struct Geometry {
        var core = MeshBuilder()
        var halo = MeshBuilder()
        var fade: Double = 1
        var emphasis = false
    }

    private func geometry(_ arc: SceneSpec.Arc, age: Int, _ c: StadiumContext) -> Geometry {
        let look = c.look.broadcast.trail
        var g = Geometry()
        g.emphasis = arc.style == "score"
        var width = look.core.value(tabletop: c.tabletop)
        if let seat = c.shared.seat, !c.tabletop {
            width *= SceneMath.nearSeatScale(SceneMath.samples(arc, count: 32), seat: seat, rule: look.nearSeat)
        }
        let a = Double(age)
        g.fade = age == 0 ? 1 : max(look.age.minOpacity, pow(look.age.decay, a))
        width *= age == 0 ? 1 : max(look.age.minScale, pow(look.age.thin, a))
        let core = Float(width * (g.emphasis ? look.scoreEmphasis.core : 1))
        let halo = Float(width * look.haloScale * (g.emphasis ? look.scoreEmphasis.halo : 1))
        let view = Self.view(c)
        let pieces = SceneMath.dashes(arc, count: 72)
        let total = Float(pieces.count)
        for (i, piece) in pieces.enumerated() {
            let lo = pieces.count == 1 ? 0 : Float(i) / total
            let hi = pieces.count == 1 ? 1 : Float(i + 1) / total
            g.core.facingStrip(piece, halfWidth: core / 2, view: view, uRange: lo...hi)
        }
        g.halo.facingStrip(SceneMath.samples(arc, count: 72), halfWidth: halo / 2, view: view)
        return g
    }

    private func entity(_ arc: SceneSpec.Arc, geometry g: Geometry, _ c: StadiumContext) -> Entity {
        let look = c.look.broadcast.trail
        let colour = c.spec.palette[arc.color] ?? "#FFFFFF"
        let holder = Entity()
        holder.name = "trail.\(arc.id)"
        holder.addChild(g.halo.entity("trail.halo",
            StadiumLook.glow(colour, opacity: look.haloOpacity * g.fade * (g.emphasis ? look.scoreEmphasis.halo : 1),
                             texture: c.assets.texture("broadcast.trailHalo"))))
        holder.addChild(g.core.entity("trail.core",
            StadiumLook.glow(colour, opacity: look.coreOpacity * g.fade, texture: c.assets.texture("broadcast.trailCore"))))
        return holder
    }

    /// The direction a strip faces at a point: the wearer's eyes in the
    /// stadium, the tokens' fixed view over the table.
    static func view(_ c: StadiumContext) -> (SIMD3<Float>) -> SIMD3<Float> {
        if let seat = c.shared.seat, !c.tabletop {
            return { p in
                let d = seat - p
                return simd_length(d) > 1e-4 ? simd_normalize(d) : SIMD3(0, 0, 1)
            }
        }
        let v = c.look.broadcast.trail.tabletopView
        let fixed = v.count == 3 ? SIMD3(Float(v[0]), Float(v[1]), Float(v[2])) : SIMD3<Float>(0, 0.85, 1)
        let n = simd_length(fixed) > 1e-6 ? simd_normalize(fixed) : SIMD3(0, 0, 1)
        return { _ in n }
    }
}
