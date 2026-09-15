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
    func rebuild(_ c: StadiumContext) {
        for e in entities.values { e.removeFromParent() }
        entities.removeAll()
        for (index, id) in order.enumerated() {
            guard let arc = arcs[id] else { continue }
            let age = order.count - 1 - index
            let e = build(arc, age: age, c)
            entities[id] = e
            root.addChild(e)
        }
    }

    private func build(_ arc: SceneSpec.Arc, age: Int, _ c: StadiumContext) -> Entity {
        let s = c.spec, look = c.look.broadcast.trail
        let colour = s.palette[arc.color] ?? "#FFFFFF"
        let emphasis = arc.style == "score"
        var width = look.core.value(tabletop: c.tabletop)
        if let seat = c.shared.seat, !c.tabletop {
            width *= SceneMath.nearSeatScale(SceneMath.samples(arc, count: 32), seat: seat, rule: look.nearSeat)
        }
        let a = Double(age)
        let fade = age == 0 ? 1 : max(look.age.minOpacity, pow(look.age.decay, a))
        width *= age == 0 ? 1 : max(look.age.minScale, pow(look.age.thin, a))
        let core = Float(width * (emphasis ? look.scoreEmphasis.core : 1))
        let halo = Float(width * look.haloScale * (emphasis ? look.scoreEmphasis.halo : 1))

        let view = Self.view(c)
        var coreB = MeshBuilder(), haloB = MeshBuilder()
        let pieces = SceneMath.dashes(arc, count: 72)
        let total = Float(pieces.count)
        for (i, piece) in pieces.enumerated() {
            let lo = pieces.count == 1 ? 0 : Float(i) / total
            let hi = pieces.count == 1 ? 1 : Float(i + 1) / total
            coreB.facingStrip(piece, halfWidth: core / 2, view: view, uRange: lo...hi)
        }
        haloB.facingStrip(SceneMath.samples(arc, count: 72), halfWidth: halo / 2, view: view)

        let holder = Entity()
        holder.name = "trail.\(arc.id)"
        let assets = c.assets
        let haloE = haloB.entity("trail.halo", StadiumLook.glow(colour, opacity: look.haloOpacity * fade * (emphasis ? look.scoreEmphasis.halo : 1),
                                                                texture: assets.texture("broadcast.trailHalo")))
        let coreE = coreB.entity("trail.core", StadiumLook.glow(colour, opacity: look.coreOpacity * fade,
                                                                texture: assets.texture("broadcast.trailCore")))
        holder.addChild(haloE)
        holder.addChild(coreE)
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
