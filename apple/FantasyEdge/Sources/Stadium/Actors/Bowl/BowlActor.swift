import RealityKit
import simd

/// The bowl: stepped seating tiers with aisles and rails, the wall cap, the
/// concourse and the fascia under the upper deck, the press box, tunnels and
/// the back wall. The ribbon board on the fascia is Broadcast's; the boards on
/// the wall face are Sideline's. Reads `bowl` and `visual.bowl`.
///
/// Publishes to the blackboard: where the press box is, and a point in the
/// stands behind each end zone.
@MainActor
final class BowlActor: StadiumActor {
    let name = "bowl"
    let root = Entity()

    init() { root.name = "actor.bowl" }

    func build(_ c: StadiumContext) {
        clear()
        let s = c.spec, B = c.look.bowl, pal = s.palette
        let tiers = c.tiers
        let shape = s.bowl.shape
        let S = B.segments
        let angles = (0...S).map { Double($0) / Double(S) * 2 * .pi }
        let concrete = c.assets.texture("bowl.concrete")
        let seats = c.assets.texture("bowl.seats")

        for tier in tiers {
            let rows = B.rows[tier.name] ?? 20
            var treads = MeshBuilder(), risers = MeshBuilder(), aisles = MeshBuilder()
            for r in 0..<rows {
                let row = SceneMath.row(tier, r, of: rows)
                let front = angles.map { SceneMath.bowlPoint(shape, offset: row.front, angle: $0) }
                let back = angles.map { SceneMath.bowlPoint(shape, offset: row.back, angle: $0) }
                var run: Float = 0
                for k in 0..<S {
                    if c.cut(angles[k], angles[k + 1]) { continue }
                    let f0 = front[k], f1 = front[k + 1], b0 = back[k], b1 = back[k + 1]
                    let seg = Float(hypot(f1.x - f0.x, f1.z - f0.z))
                    let u0 = run / 4, u1 = (run + seg) / 4
                    run += seg
                    let y = Float(row.tread), y0 = Float(row.riserFrom)
                    treads.quad(SIMD3(Float(f0.x), y, Float(f0.z)), SIMD3(Float(f1.x), y, Float(f1.z)),
                                SIMD3(Float(b1.x), y, Float(b1.z)), SIMD3(Float(b0.x), y, Float(b0.z)),
                                uv: (SIMD2(u0, 0), SIMD2(u1, 0), SIMD2(u1, 1), SIMD2(u0, 1)), normal: SIMD3(0, 1, 0))
                    let inward = SceneMath.inward(shape, offset: row.front, angle: (angles[k] + angles[k + 1]) / 2)
                    risers.quad(SIMD3(Float(f0.x), y0, Float(f0.z)), SIMD3(Float(f1.x), y0, Float(f1.z)),
                                SIMD3(Float(f1.x), y, Float(f1.z)), SIMD3(Float(f0.x), y, Float(f0.z)),
                                uv: (SIMD2(u0, 0), SIMD2(u1, 0), SIMD2(u1, (y - y0) / 4), SIMD2(u0, (y - y0) / 4)),
                                normal: SIMD3(Float(inward.x), 0, Float(inward.y)))
                    if k % max(1, B.aisleEvery) == B.aisleOffset % max(1, B.aisleEvery) {
                        let t = angles[k]
                        let mid = SceneMath.bowlPoint(shape, offset: (row.front + row.back) / 2, angle: t)
                        let n = SceneMath.inward(shape, offset: row.front, angle: t)
                        let tangent = SIMD2(-n.y, n.x) * (B.aisleYards / 2)
                        let depth = n * ((row.back - row.front) / 2)
                        let p = { (v: SIMD2<Double>) in SIMD3(Float(v.x), y + 0.03, Float(v.y)) }
                        let cc = SIMD2(mid.x, mid.z)
                        aisles.quad(p(cc + depth - tangent), p(cc + depth + tangent), p(cc - depth + tangent), p(cc - depth - tangent),
                                    normal: SIMD3(0, 1, 0))
                    }
                }
            }
            let seatColor = pal[tier.color] ?? "#302722"
            root.addChild(treads.entity("tier.\(tier.name).treads",
                                        StadiumLook.solid("#FFFFFF", roughness: 0.85, texture: seats, cull: false)))
            root.addChild(risers.entity("tier.\(tier.name).risers",
                                        StadiumLook.solid(seatColor, roughness: 0.9, texture: concrete, cull: false)))
            root.addChild(aisles.entity("tier.\(tier.name).aisles",
                                        StadiumLook.solid(pal["bowl.aisle"] ?? "#5A5650", roughness: 0.9, texture: concrete, cull: false)))

            // A rail along the top of the tier and the front of any tier raised
            // off the ground. A rail runs in unbroken pieces; the cutaway breaks it.
            var rails = MeshBuilder()
            for (m, h) in [(tier.outer, tier.rise[1]), (tier.inner, tier.rise[0])] where h > 2 || m == tier.outer {
                var piece: [SIMD3<Float>] = []
                for (k, t) in angles.enumerated() {
                    if k < S && c.cut(angles[k], angles[k + 1]) {
                        if piece.count > 1 { rails.tube(piece, radius: Float(B.railRadius), sides: 5) }
                        piece = []
                        continue
                    }
                    let p = SceneMath.bowlPoint(shape, offset: m, angle: t)
                    piece.append(SIMD3(Float(p.x), Float(h + B.railYards), Float(p.z)))
                }
                if piece.count > 1 { rails.tube(piece, radius: Float(B.railRadius), sides: 5) }
            }
            root.addChild(rails.entity("tier.\(tier.name).rails", StadiumLook.solid("#3A3F46", roughness: 0.35, metallic: 0.7)))
        }

        // The cap between the wall and the first row, and the tunnels.
        if let wall = s.bowl.wall, let lower = tiers.first {
            var cap = MeshBuilder()
            for k in 0..<S {
                if c.cut(angles[k], angles[k + 1]) { continue }
                let a = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k])
                let b = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k + 1])
                let ai = SceneMath.bowlPoint(shape, offset: lower.inner, angle: angles[k])
                let bi = SceneMath.bowlPoint(shape, offset: lower.inner, angle: angles[k + 1])
                let h = Float(wall.height), top = Float(max(wall.height, lower.rise[0]))
                cap.quad(SIMD3(Float(a.x), h, Float(a.z)), SIMD3(Float(b.x), h, Float(b.z)),
                         SIMD3(Float(bi.x), top, Float(bi.z)), SIMD3(Float(ai.x), top, Float(ai.z)))
            }
            root.addChild(cap.entity("wall.cap", StadiumLook.solid("#2A2724", roughness: 0.9, texture: concrete, cull: false)))
            for tunnel in s.bowl.tunnels ?? [] {
                let lx = Float(tunnel.x - 50)
                let x = lx + (lx < 0 ? 0.08 : -0.08)
                let w = Float(tunnel.width / 2), h = Float(tunnel.height)
                var t = MeshBuilder()
                t.quad(SIMD3(x, 0, -w), SIMD3(x, 0, w), SIMD3(x, h, w), SIMD3(x, h, -w))
                root.addChild(t.entity("tunnel", StadiumLook.solid("#020203", roughness: 1, cull: false)))
            }
        }

        // The concourse and the fascia under the upper deck, leaving the band
        // the ribbon board fills.
        if let ribbon = s.bowl.ribbon, tiers.count > 1, let lower = tiers.first, let upper = tiers.dropFirst().first {
            var floorB = MeshBuilder(), fascia = MeshBuilder()
            for k in 0..<S {
                let t0 = angles[k], t1 = angles[k + 1]
                let a0 = SceneMath.bowlPoint(shape, offset: lower.outer, angle: t0)
                let a1 = SceneMath.bowlPoint(shape, offset: lower.outer, angle: t1)
                let r0 = SceneMath.bowlPoint(shape, offset: ribbon.offset, angle: t0)
                let r1 = SceneMath.bowlPoint(shape, offset: ribbon.offset, angle: t1)
                let u0p = SceneMath.bowlPoint(shape, offset: upper.inner, angle: t0)
                let u1p = SceneMath.bowlPoint(shape, offset: upper.inner, angle: t1)
                let low = Float(lower.rise[1]), top = Float(upper.rise[0])
                floorB.quad(SIMD3(Float(a0.x), low, Float(a0.z)), SIMD3(Float(a1.x), low, Float(a1.z)),
                            SIMD3(Float(r1.x), low, Float(r1.z)), SIMD3(Float(r0.x), low, Float(r0.z)))
                let rb = Float(ribbon.rise[0]), rt = Float(ribbon.rise[1])
                for (y0, y1) in [(low, rb), (rt, top)] {
                    fascia.quad(SIMD3(Float(r0.x), y0, Float(r0.z)), SIMD3(Float(r1.x), y0, Float(r1.z)),
                                SIMD3(Float(r1.x), y1, Float(r1.z)), SIMD3(Float(r0.x), y1, Float(r0.z)))
                }
                fascia.quad(SIMD3(Float(r0.x), top, Float(r0.z)), SIMD3(Float(r1.x), top, Float(r1.z)),
                            SIMD3(Float(u1p.x), top, Float(u1p.z)), SIMD3(Float(u0p.x), top, Float(u0p.z)))
            }
            root.addChild(floorB.entity("concourse", StadiumLook.solid("#1A1715", roughness: 0.95, texture: concrete, cull: false)))
            root.addChild(fascia.entity("fascia", StadiumLook.solid("#24211F", roughness: 0.9, texture: concrete, cull: false)))
        }

        // The press box: a long glass room in the far concourse, lit warm.
        if let pb = s.bowl.pressBox, tiers.count > 1 {
            let sign: Float = pb.side == "far" ? -1 : 1
            let z0 = sign * Float(shape.halfWidth + pb.offset), z1 = sign * Float(shape.halfWidth + pb.offset + pb.depth)
            let x0 = Float(pb.fromX - 50), x1 = Float(pb.toX - 50)
            let y0 = Float(pb.rise[0]), y1 = Float(pb.rise[1])
            var body = MeshBuilder(), glass = MeshBuilder(), mullions = MeshBuilder()
            body.box(min: SIMD3(x0, y1 - 0.2, min(z0, z1)), max: SIMD3(x1, y1 + 0.8, max(z0, z1)))
            body.box(min: SIMD3(x0, y0 - 0.6, min(z0, z1)), max: SIMD3(x1, y0 + 0.15, max(z0, z1)))
            let gy0 = y0 + 0.15, gy1 = y1 - 0.2
            glass.quad(SIMD3(x0, gy0, z0), SIMD3(x1, gy0, z0), SIMD3(x1, gy1, z0), SIMD3(x0, gy1, z0),
                       normal: SIMD3(0, 0, -sign))
            var x = x0
            while x < x1 {
                mullions.box(min: SIMD3(x - 0.08, gy0, z0 - 0.05), max: SIMD3(x + 0.08, gy1, z0 + 0.05))
                x += Float(pb.mullionEvery)
            }
            root.addChild(body.entity("pressbox.body", StadiumLook.solid("#1C1B1A", roughness: 0.6, texture: concrete)))
            root.addChild(glass.entity("pressbox.glass", StadiumLook.emissive(pal[pb.glass] ?? "#FFD7A1", scale: pb.glassBrightness)))
            root.addChild(mullions.entity("pressbox.mullions", StadiumLook.solid("#0D0D0E", roughness: 0.5, metallic: 0.5)))
            c.shared.pressBox = SIMD3((x0 + x1) / 2, (y0 + y1) / 2, z0)
        }

        // A back wall to close the top of the bowl.
        if let top = tiers.last {
            var back = MeshBuilder()
            for k in 0..<S {
                if c.cut(angles[k], angles[k + 1]) { continue }
                let a = SceneMath.bowlPoint(shape, offset: top.outer, angle: angles[k])
                let b = SceneMath.bowlPoint(shape, offset: top.outer, angle: angles[k + 1])
                let y0 = Float(top.rise[1]), y1 = y0 + Float(B.wallTopBand)
                back.quad(SIMD3(Float(a.x), y0, Float(a.z)), SIMD3(Float(b.x), y0, Float(b.z)),
                          SIMD3(Float(b.x), y1, Float(b.z)), SIMD3(Float(a.x), y1, Float(a.z)))
            }
            root.addChild(back.entity("backwall", StadiumLook.solid("#1F1C1A", roughness: 0.9, texture: concrete, cull: false)))
        }

        // Where the stands are loudest behind each end, for sound.
        let behind = (tiers.first?.inner ?? 6) + 8
        let home = SceneMath.bowlPoint(shape, offset: behind, angle: .pi)
        let away = SceneMath.bowlPoint(shape, offset: behind, angle: 0)
        let h = Float(tiers.first.map { SceneMath.tierHeight($0, offset: behind) } ?? 6)
        c.shared.standsBehind = (SIMD3(Float(home.x), h, Float(home.z)), SIMD3(Float(away.x), h, Float(away.z)))
    }
}
