import RealityKit
import UIKit
import simd

/// What the static build hands back: the entities the renderer animates or
/// updates later, so nothing has to be found by name.
@MainActor
final class StadiumStatic {
    let root = Entity()
    var glows: [ModelEntity] = []
    var glowOpacity: Double = 0.5
    var ribbon: TextureResource?
    var ribbonKey = ""
    /// Local positions of the rim light banks, for fireworks and strobes.
    var banks: [SIMD3<Float>] = []
    /// Where the stands are loudest for a given end of the field: a point on
    /// the lower bowl behind that end zone, for the roar.
    var standsBehind: (home: SIMD3<Float>, away: SIMD3<Float>) = (.zero, .zero)
    var pressBox: SIMD3<Float> = .zero
}

@MainActor
enum StadiumBowl {

    static func build(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets,
                      tabletop: Bool, tiers: [SceneSpec.Tier]) -> StadiumStatic {
        let out = StadiumStatic()
        out.root.name = "stadium.static"
        out.root.addChild(field(s, look: look, assets: assets, tabletop: tabletop))
        out.root.addChild(props(s, look: look, assets: assets))
        out.root.addChild(stands(s, look: look, assets: assets, tiers: tiers, tabletop: tabletop, out: out))
        out.root.addChild(lights(s, look: look, assets: assets, tiers: tiers, tabletop: tabletop, out: out))
        if tabletop {
            out.root.addChild(baseplate(s, look: look, tiers: tiers))
        } else {
            out.root.addChild(sky(look: look, assets: assets))
        }
        let lowerBack = (tiers.first?.inner ?? 6) + 8
        let home = SceneMath.bowlPoint(s.bowl.shape, offset: lowerBack, angle: .pi)
        let away = SceneMath.bowlPoint(s.bowl.shape, offset: lowerBack, angle: 0)
        let h = Float(tiers.first.map { SceneMath.tierHeight($0, offset: lowerBack) } ?? 6)
        out.standsBehind = (SIMD3(Float(home.x), h, Float(home.z)), SIMD3(Float(away.x), h, Float(away.z)))
        return out
    }

    // MARK: the field

    static func field(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, tabletop: Bool) -> Entity {
        let root = Entity()
        root.name = "field"
        let f = s.field, L = look.lines, T = look.turf
        let half = f.width / 2
        let tile = T.tileYards

        var surround = MeshBuilder()
        surround.floor(x0: -f.endZone - 8, x1: f.length + f.endZone + 8, z0: -half - 9, z1: half + 9, y: -0.03, tile: tile)
        let surroundEntity = surround.entity("turf.surround", StadiumLook.turf(tint: T.surroundTint, roughness: T.stripeRoughness[0],
                                                                                look: look, assets: assets))
        StadiumLook.ground(surroundEntity, order: 0)
        root.addChild(surroundEntity)

        var stripes = [MeshBuilder(), MeshBuilder()]
        var x = -f.endZone, i = 0
        while x < f.length + f.endZone - 1e-6 {
            let to = min(f.length + f.endZone, x + f.stripeEvery)
            stripes[i % 2].floor(x0: x, x1: to, z0: -half, z1: half, y: 0, tile: tile)
            x = to; i += 1
        }
        for k in 0..<2 {
            let e = stripes[k].entity("turf.stripe.\(k)",
                                      StadiumLook.turf(tint: T.stripeTint[k % T.stripeTint.count],
                                                       roughness: T.stripeRoughness[k % T.stripeRoughness.count],
                                                       look: look, assets: assets))
            StadiumLook.ground(e, order: 1)
            root.addChild(e)
        }

        // End zones: club paint over the grass, the club's name across it.
        for (team, x0, x1) in [(s.teams.home, -f.endZone, 0.0), (s.teams.away, f.length, f.length + f.endZone)] {
            var b = MeshBuilder()
            b.floor(x0: x0, x1: x1, z0: -half, z1: half, y: L.lift * 0.5, tile: tile)
            let e = b.entity("endzone.\(team.abbr)", StadiumLook.paint(team.chip, opacity: T.endZonePaintOpacity,
                                                                       roughness: T.paintRoughness, assets: assets))
            StadiumLook.ground(e, order: 2)
            root.addChild(e)
            let name = MeshResource.generateText(team.name.uppercased(), extrusionDepth: 0.02,
                                                 font: .systemFont(ofSize: CGFloat(L.endZoneTextHeight), weight: .black),
                                                 containerFrame: .zero, alignment: .center, lineBreakMode: .byClipping)
            let text = ModelEntity(mesh: name, materials: [StadiumLook.paint(s.palette["line.yard"] ?? "#FFFFFF",
                                                                               opacity: T.paintOpacity * 0.9,
                                                                               roughness: T.paintRoughness, assets: assets)])
            let c = name.bounds.center
            let home = x0 < 0
            // Flat on the grass, running across the field, its top toward the end line.
            let flat = simd_quatf(angle: -.pi / 2, axis: SIMD3(1, 0, 0))
            let turn = simd_quatf(angle: home ? .pi / 2 : -.pi / 2, axis: SIMD3(0, 1, 0))
            text.orientation = turn * flat
            let at = SceneMath.local(x: (x0 + x1) / 2, y: L.lift, z: 0)
            text.position = at - (turn * flat).act(c)
            StadiumLook.ground(text, order: 3)
            root.addChild(text)
        }

        // Lines: goal lines, the five-yard lines, the border, hashes.
        var lines = MeshBuilder()
        var yard = 0.0
        while yard <= f.length + 1e-6 {
            let w = yard.truncatingRemainder(dividingBy: 10) == 0 ? L.tenWidth : L.fiveWidth
            lines.stripe(from: SIMD2(yard, -half), to: SIMD2(yard, half), width: w, y: L.lift, tile: tile)
            yard += f.stripeEvery
        }
        for z in [-half - L.border / 2, half + L.border / 2] {
            lines.stripe(from: SIMD2(-f.endZone - L.border, z), to: SIMD2(f.length + f.endZone + L.border, z),
                         width: L.border, y: L.lift, tile: tile)
        }
        for xe in [-f.endZone - L.border / 2, f.length + f.endZone + L.border / 2] {
            lines.stripe(from: SIMD2(xe, -half), to: SIMD2(xe, half), width: L.border, y: L.lift, tile: tile)
        }
        let hash = half - f.hashFromSideline
        for y in 1..<Int(f.length) where y % 5 != 0 {
            for z in [hash, -hash, half - 0.4 - L.hashLength / 2, -(half - 0.4 - L.hashLength / 2)] {
                lines.stripe(from: SIMD2(Double(y), z - L.hashLength / 2), to: SIMD2(Double(y), z + L.hashLength / 2),
                             width: L.hashWidth, y: L.lift, tile: 1)
            }
        }
        let paint = StadiumLook.paint(s.palette["line.yard"] ?? "#FFFFFF", opacity: T.paintOpacity,
                                      roughness: T.paintRoughness, assets: assets)
        let lineEntity = lines.entity("lines", paint)
        StadiumLook.ground(lineEntity, order: 3)
        root.addChild(lineEntity)

        // Numbers stand on the field, tops toward the middle, read from their own sideline.
        var n = f.numbersEvery
        while n < f.length {
            let label = "\(Int(n <= 50 ? n : f.length - n))"
            let mesh = MeshResource.generateText(label, extrusionDepth: 0.02,
                                                 font: .systemFont(ofSize: CGFloat(L.numberHeight), weight: .bold),
                                                 containerFrame: .zero, alignment: .center, lineBreakMode: .byClipping)
            let c = mesh.bounds.center
            for near in [true, false] {
                let e = ModelEntity(mesh: mesh, materials: [paint])
                let flat = simd_quatf(angle: -.pi / 2, axis: SIMD3(1, 0, 0))
                let turn = near ? simd_quatf(angle: 0, axis: SIMD3(0, 1, 0)) : simd_quatf(angle: .pi, axis: SIMD3(0, 1, 0))
                e.orientation = turn * flat
                let at = SceneMath.local(x: n, y: L.lift, z: near ? half - L.numberInset : -(half - L.numberInset))
                e.position = at - (turn * flat).act(c)
                StadiumLook.ground(e, order: 3)
                root.addChild(e)
            }
            n += f.numbersEvery
        }
        return root
    }

    // MARK: props

    static func props(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets) -> Entity {
        let root = Entity()
        root.name = "props"
        guard let p = s.field.props else { return root }
        let f = s.field, half = f.width / 2, pal = s.palette

        var pylons = MeshBuilder()
        let ps = Float(p.pylon.size / 2)
        for x in [-f.endZone, 0, f.length, f.length + f.endZone] {
            for z in [-half, half] {
                let c = SceneMath.local(x: x, y: 0, z: z)
                pylons.box(min: c + SIMD3(-ps, 0, -ps), max: c + SIMD3(ps, Float(p.pylon.height), ps))
            }
        }
        root.addChild(pylons.entity("pylons", StadiumLook.solid(pal[p.pylon.color] ?? "#FF6A13", roughness: 0.5)))

        // Goal posts: base behind the end line, a gooseneck forward, crossbar,
        // uprights. They cast the only dynamic shadows in the stadium.
        let g = p.goalpost
        var posts = MeshBuilder()
        var pads = MeshBuilder()
        for (xe, dir) in [(-f.endZone, -1.0), (f.length + f.endZone, 1.0)] {
            let xb = xe + dir * g.baseBehind
            let bar = Float(g.crossbar)
            var neck: [SIMD3<Float>] = [SceneMath.local(x: xb, y: 0, z: 0), SceneMath.local(x: xb, y: g.crossbar - 1.4, z: 0)]
            for k in 1...10 {
                let t = Double(k) / 10
                let px = xb + (xe - xb) * t * t
                let py = (g.crossbar - 1.4) + 1.4 * sin(t * .pi / 2)
                neck.append(SceneMath.local(x: px, y: py, z: 0))
            }
            posts.tube(neck, radius: Float(g.radius.base), sides: 10)
            let w = f.goalPostWidth / 2
            posts.tube([SceneMath.local(x: xe, y: g.crossbar, z: -w - 0.05), SceneMath.local(x: xe, y: g.crossbar, z: w + 0.05)],
                       radius: Float(g.radius.crossbar), sides: 10)
            for z in [-w, w] {
                posts.tube([SceneMath.local(x: xe, y: g.crossbar, z: z),
                            SceneMath.local(x: xe, y: g.crossbar + g.uprightAbove, z: z)], radius: Float(g.radius.upright), sides: 8)
            }
            let base = SceneMath.local(x: xb, y: 0, z: 0)
            let pw = Float(g.padWidth / 2)
            pads.box(min: base + SIMD3(-pw, 0, -pw), max: base + SIMD3(pw, min(bar - 1.6, Float(g.padHeight)), pw))
        }
        let postEntity = posts.entity("goalposts", StadiumLook.solid(pal[g.color] ?? "#F2C21B", roughness: 0.32,
                                                                     metallic: 0.15, cull: false))
        postEntity.components.set(DynamicLightShadowComponent(castsShadow: true))
        root.addChild(postEntity)
        root.addChild(pads.entity("goalpost.pads", StadiumLook.solid(pal[p.benches.color] ?? "#23272E", roughness: 0.8)))

        // Benches, each club's on its own sideline, a chip-coloured back.
        let b = p.benches
        for (team, sign) in [(s.teams.home, 1.0), (s.teams.away, -1.0)] {
            var seat = MeshBuilder(), back = MeshBuilder()
            let z = sign * (half + b.offset)
            let lo = SceneMath.local(x: b.fromX, y: 0, z: z - b.depth / 2)
            let hi = SceneMath.local(x: b.toX, y: b.height, z: z + b.depth / 2)
            seat.box(min: lo, max: hi)
            let bz = Float(sign * b.depth / 2)
            back.box(min: SceneMath.local(x: b.fromX, y: b.height, z: z) + SIMD3(0, 0, bz - 0.06),
                     max: SceneMath.local(x: b.toX, y: b.height + b.backHeight, z: z) + SIMD3(0, 0, bz + 0.06))
            root.addChild(seat.entity("bench.\(team.abbr)", StadiumLook.solid(pal[b.color] ?? "#23272E", roughness: 0.6)))
            root.addChild(back.entity("bench.back.\(team.abbr)", StadiumLook.solid(team.chip, roughness: 0.55)))
        }
        return root
    }

    // MARK: the stands

    static func stands(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, tiers: [SceneSpec.Tier],
                       tabletop: Bool, out: StadiumStatic) -> Entity {
        let root = Entity()
        root.name = "stands"
        let shape = s.bowl.shape, B = look.bowl, pal = s.palette
        let S = B.segments
        let angles = (0...S).map { Double($0) / Double(S) * 2 * .pi }
        let concrete = assets.texture("concrete")

        for tier in tiers {
            let rows = B.rows[tier.name] ?? 20
            var treads = MeshBuilder(), risers = MeshBuilder(), aisles = MeshBuilder()
            for r in 0..<rows {
                let row = SceneMath.row(tier, r, of: rows)
                let front = angles.map { SceneMath.bowlPoint(shape, offset: row.front, angle: $0) }
                let back = angles.map { SceneMath.bowlPoint(shape, offset: row.back, angle: $0) }
                var run: Float = 0
                for k in 0..<S {
                    if tabletop && cut(angles[k], angles[k + 1], look) { continue }
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
                        let c = SIMD2(mid.x, mid.z)
                        aisles.quad(p(c + depth - tangent), p(c + depth + tangent), p(c - depth + tangent), p(c - depth - tangent),
                                    normal: SIMD3(0, 1, 0))
                    }
                }
            }
            let seatColor = pal[tier.color] ?? "#302722"
            root.addChild(treads.entity("tier.\(tier.name).treads",
                                        StadiumLook.solid("#FFFFFF", roughness: 0.85, texture: assets.texture("seats"), cull: false)))
            root.addChild(risers.entity("tier.\(tier.name).risers",
                                        StadiumLook.solid(seatColor, roughness: 0.9, texture: concrete, cull: false)))
            root.addChild(aisles.entity("tier.\(tier.name).aisles",
                                        StadiumLook.solid(pal["bowl.aisle"] ?? "#5A5650", roughness: 0.9, texture: concrete, cull: false)))

            // A rail along the top of the tier and the front of any tier
            // raised off the ground.
            var rails = MeshBuilder()
            for (m, h) in [(tier.outer, tier.rise[1]), (tier.inner, tier.rise[0])] where h > 2 || m == tier.outer {
                // A rail runs in unbroken pieces; the cutaway breaks it.
                var piece: [SIMD3<Float>] = []
                for (k, t) in angles.enumerated() {
                    if tabletop && k < S && cut(angles[k], angles[k + 1], look) {
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

        // The wall at the front of the stands, lined with LED boards.
        if let wall = s.bowl.wall, let lower = tiers.first {
            var board = MeshBuilder(), cap = MeshBuilder()
            var run: Float = 0
            for k in 0..<S {
                if tabletop && cut(angles[k], angles[k + 1], look) { continue }
                let a = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k])
                let b = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k + 1])
                let seg = Float(hypot(b.x - a.x, b.z - a.z))
                let u0 = run / 24, u1 = (run + seg) / 24
                run += seg
                let h = Float(wall.height)
                board.quad(SIMD3(Float(a.x), 0, Float(a.z)), SIMD3(Float(b.x), 0, Float(b.z)),
                           SIMD3(Float(b.x), h, Float(b.z)), SIMD3(Float(a.x), h, Float(a.z)),
                           uv: (SIMD2(u0, 0), SIMD2(u1, 0), SIMD2(u1, 1), SIMD2(u0, 1)))
                let ai = SceneMath.bowlPoint(shape, offset: lower.inner, angle: angles[k])
                let bi = SceneMath.bowlPoint(shape, offset: lower.inner, angle: angles[k + 1])
                let top = Float(max(wall.height, lower.rise[0]))
                cap.quad(SIMD3(Float(a.x), h, Float(a.z)), SIMD3(Float(b.x), h, Float(b.z)),
                         SIMD3(Float(bi.x), top, Float(bi.z)), SIMD3(Float(ai.x), top, Float(ai.z)))
            }
            let boards = StadiumText.boards(s)
            let material: any Material = boards.map { StadiumLook.emissive("#FFFFFF", scale: 0.85, texture: $0) }
                ?? StadiumLook.solid(pal[wall.color] ?? "#07090D")
            root.addChild(board.entity("wall.boards", material))
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

        // The concourse, the fascia under the upper deck and its ribbon board.
        if let ribbon = s.bowl.ribbon, tiers.count > 1, let lower = tiers.first, let upper = tiers.dropFirst().first {
            var floorB = MeshBuilder(), fascia = MeshBuilder(), band = MeshBuilder()
            var run: Float = 0
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
                let seg = Float(hypot(r1.x - r0.x, r1.z - r0.z))
                let v0 = run / Float(look.ribbon.segmentYards), v1 = (run + seg) / Float(look.ribbon.segmentYards)
                run += seg
                let rb = Float(ribbon.rise[0]), rt = Float(ribbon.rise[1])
                for (y0, y1) in [(low, rb), (rt, top)] {
                    fascia.quad(SIMD3(Float(r0.x), y0, Float(r0.z)), SIMD3(Float(r1.x), y0, Float(r1.z)),
                                SIMD3(Float(r1.x), y1, Float(r1.z)), SIMD3(Float(r0.x), y1, Float(r0.z)))
                }
                fascia.quad(SIMD3(Float(r0.x), top, Float(r0.z)), SIMD3(Float(r1.x), top, Float(r1.z)),
                            SIMD3(Float(u1p.x), top, Float(u1p.z)), SIMD3(Float(u0p.x), top, Float(u0p.z)))
                band.quad(SIMD3(Float(r0.x), rb, Float(r0.z)), SIMD3(Float(r1.x), rb, Float(r1.z)),
                          SIMD3(Float(r1.x), rt, Float(r1.z)), SIMD3(Float(r0.x), rt, Float(r0.z)),
                          uv: (SIMD2(v0, 0), SIMD2(v1, 0), SIMD2(v1, 1), SIMD2(v0, 1)))
            }
            root.addChild(floorB.entity("concourse", StadiumLook.solid("#1A1715", roughness: 0.95, texture: concrete, cull: false)))
            root.addChild(fascia.entity("fascia", StadiumLook.solid("#24211F", roughness: 0.9, texture: concrete, cull: false)))
            let tex = StadiumText.ribbon(s, look: look)
            out.ribbon = tex
            let bandMaterial: any Material = tex.map { StadiumLook.emissive("#FFFFFF", scale: 1.0, texture: $0) }
                ?? StadiumLook.emissive(pal[ribbon.color] ?? "#05060A")
            root.addChild(band.entity("ribbon", bandMaterial))
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
            out.pressBox = SIMD3((x0 + x1) / 2, (y0 + y1) / 2, z0)
        }

        // A back wall to close the top of the bowl.
        if let top = tiers.last {
            var back = MeshBuilder()
            for k in 0..<S {
                if tabletop && cut(angles[k], angles[k + 1], look) { continue }
                let a = SceneMath.bowlPoint(shape, offset: top.outer, angle: angles[k])
                let b = SceneMath.bowlPoint(shape, offset: top.outer, angle: angles[k + 1])
                let y0 = Float(top.rise[1]), y1 = y0 + Float(B.wallTopBand)
                back.quad(SIMD3(Float(a.x), y0, Float(a.z)), SIMD3(Float(b.x), y0, Float(b.z)),
                          SIMD3(Float(b.x), y1, Float(b.z)), SIMD3(Float(a.x), y1, Float(a.z)))
            }
            root.addChild(back.entity("backwall", StadiumLook.solid("#1F1C1A", roughness: 0.9, texture: concrete, cull: false)))
        }
        return root
    }

    /// Whether a segment falls in the tabletop's cutaway, the stands left out
    /// so the wearer can see into the bowl from the table's edge.
    static func cut(_ t0: Double, _ t1: Double, _ look: SceneSpec.Look) -> Bool {
        let c = look.tabletop.cutaway
        let mid = (t0 + t1) / 2
        // Home is +z, which the superellipse reaches for angles in (0, pi).
        let half = c.side == "home" ? mid : mid - .pi
        let f = half / .pi
        return f > c.from && f < c.to
    }

    // MARK: light

    static func lights(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, tiers: [SceneSpec.Tier],
                       tabletop: Bool, out: StadiumStatic) -> Entity {
        let root = Entity()
        root.name = "lights"
        let rim = look.light.rim, lights = s.bowl.rimLights
        let colour = s.palette[lights.color] ?? "#FFF8E6"
        guard let top = tiers.last else { return root }
        let rimOffset = top.outer + (lights.beyondOuter ?? 1)
        let standTop = top.rise[1]
        let height = standTop + rim.heightAbove.value(tabletop: tabletop)
        let lamp = rim.lampYards.value(tabletop: tabletop)
        let glowSize = Float(rim.glowYards.value(tabletop: tabletop))
        let hazeLength = Float(rim.hazeLength.value(tabletop: tabletop))
        out.glowOpacity = rim.glowOpacity

        var positions: [SIMD3<Float>] = []
        for k in 0..<lights.count {
            let t = Double(k) * .pi / Double(max(1, lights.count / 2)) + rim.phase
            let p = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset, angle: t)
            if lights.side == "far" && p.z > rim.farSideMaxZ { continue }
            positions.append(SIMD3(Float(p.x), Float(height), Float(p.z)))
        }
        out.banks = positions

        var poles = MeshBuilder(), faces = MeshBuilder()
        let glowMaterial = StadiumLook.glow(colour, opacity: rim.glowOpacity, texture: assets.texture("glow"))
        let hazeMaterial = StadiumLook.glow(colour, opacity: rim.hazeOpacity, texture: assets.texture("haze"))
        let coreMaterial = StadiumLook.glow(colour, opacity: rim.coreGlowOpacity, texture: assets.texture("glow"))
        var haze = MeshBuilder()
        let target = SIMD3<Float>(0, 0, 0)
        for p in positions {
            let pole = Float(rim.poleYards / 2)
            poles.box(min: SIMD3(p.x - pole, Float(standTop), p.z - pole), max: SIMD3(p.x + pole, p.y, p.z + pole))
            // The lamp face, turned to the field.
            let flat = simd_normalize(SIMD3(target.x - p.x, 0, target.z - p.z))
            let side = simd_normalize(simd_cross(SIMD3(0, 1, 0), flat))
            let w = Float(lamp[0] / 2), h = Float(lamp[1] / 2)
            let tilt = SIMD3<Float>(0, 1, 0) * h
            let c = p + flat * 0.4
            faces.quad(c - side * w - tilt, c + side * w - tilt, c + side * w + tilt, c - side * w + tilt,
                       normal: flat)
            // The glow, always facing the eye.
            let g = ModelEntity(mesh: .generatePlane(width: glowSize, height: glowSize), materials: [glowMaterial])
            g.position = c + flat * 0.6
            g.components.set(BillboardComponent())
            root.addChild(g)
            out.glows.append(g)
            let coreSize = glowSize * Float(rim.coreGlowScale)
            let core = ModelEntity(mesh: .generatePlane(width: coreSize, height: coreSize), materials: [coreMaterial])
            core.position = c + flat * 0.8
            core.components.set(BillboardComponent())
            root.addChild(core)
            out.glows.append(core)
            // A haze cone from the lamp toward the field.
            let aim = simd_normalize(target - p)
            var basisA = simd_cross(aim, SIMD3(0, 1, 0))
            if simd_length(basisA) < 1e-3 { basisA = SIMD3(1, 0, 0) }
            basisA = simd_normalize(basisA)
            let basisB = simd_normalize(simd_cross(aim, basisA))
            let sides = 12
            let far = p + aim * hazeLength
            let r0 = Float(max(lamp[0], lamp[1]) * rim.hazeStartScale)
            let r1 = Float(rim.hazeRadius) * (tabletop ? 0.45 : 1)
            for k in 0..<sides {
                let a0 = Float(k) / Float(sides) * 2 * .pi, a1 = Float(k + 1) / Float(sides) * 2 * .pi
                let d0 = basisA * cos(a0) + basisB * sin(a0), d1 = basisA * cos(a1) + basisB * sin(a1)
                let u0 = Float(k) / Float(sides), u1 = Float(k + 1) / Float(sides)
                haze.quad(p + d0 * r0, p + d1 * r0, far + d1 * r1, far + d0 * r1,
                          uv: (SIMD2(u0, 1), SIMD2(u1, 1), SIMD2(u1, 0), SIMD2(u0, 0)))
            }
        }
        root.addChild(poles.entity("rim.poles", StadiumLook.solid("#2B2E33", roughness: 0.5, metallic: 0.6)))
        // The lamps themselves blend additively, so they burn rather than sit.
        root.addChild(faces.entity("rim.lamps", StadiumLook.glow(colour, opacity: 1.0, texture: assets.texture("lampFace"))))
        let hazeEntity = haze.entity("rim.haze", hazeMaterial)
        root.addChild(hazeEntity)

        // The light dome: the glow a floodlit bowl throws into the air above
        // its rim, all the way round. Not drawn on the table.
        if !tabletop {
            let sky = look.sky
            var dome = MeshBuilder()
            let S = 96
            for k in 0..<S {
                let t0 = Double(k) / Double(S) * 2 * .pi, t1 = Double(k + 1) / Double(S) * 2 * .pi
                let a = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset + 4, angle: t0)
                let b = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset + 4, angle: t1)
                let y0 = Float(standTop), y1 = Float(standTop + sky.domeHeight)
                let u0 = Float(k) / Float(S), u1 = Float(k + 1) / Float(S)
                dome.quad(SIMD3(Float(a.x), y0, Float(a.z)), SIMD3(Float(b.x), y0, Float(b.z)),
                          SIMD3(Float(b.x), y1, Float(b.z)), SIMD3(Float(a.x), y1, Float(a.z)),
                          uv: (SIMD2(u0, 1), SIMD2(u1, 1), SIMD2(u1, 0), SIMD2(u0, 0)))
            }
            root.addChild(dome.entity("sky.dome", StadiumLook.glow(sky.domeColor, opacity: sky.domeOpacity,
                                                                  texture: assets.texture("haze"))))
        }

        // Floodlights that actually light: a few spots from the banks, aimed at
        // midfield, one of them casting shadows.
        let flood = look.light.flood
        let chosen = stride(from: 0, to: positions.count, by: max(1, positions.count / max(1, flood.count)))
            .prefix(flood.count).map { positions[$0] }
        for (i, p) in chosen.enumerated() {
            let e = Entity()
            e.name = "flood.\(i)"
            e.position = p
            e.look(at: SIMD3(0, 0, 0), from: p, relativeTo: nil)
            var spot = SpotLightComponent(color: StadiumLook.color(colour),
                                          intensity: Float(tabletop ? flood.tabletopLumens : flood.lumens),
                                          innerAngleInDegrees: Float(flood.innerDegrees),
                                          outerAngleInDegrees: Float(flood.outerDegrees),
                                          attenuationRadius: Float(tabletop ? flood.tabletopReach : flood.reach))
            spot.intensity = Float(tabletop ? flood.tabletopLumens : flood.lumens)
            e.components.set(spot)
            if i < flood.shadows { e.components.set(SpotLightComponent.Shadow()) }
            root.addChild(e)
        }
        return root
    }

    // MARK: sky and table

    static func sky(look: SceneSpec.Look, assets: StadiumAssets) -> Entity {
        let r = Float(look.sky.radiusYards)
        let sky = ModelEntity(mesh: .generateSphere(radius: r),
                              materials: [StadiumLook.emissive("#FFFFFF", scale: 1, texture: assets.texture("sky"), tile: false)])
        sky.name = "sky"
        sky.scale = SIMD3(-1, 1, 1)
        return sky
    }

    static func baseplate(_ s: SceneSpec, look: SceneSpec.Look, tiers: [SceneSpec.Tier]) -> Entity {
        let root = Entity()
        root.name = "baseplate"
        let shape = s.bowl.shape
        let outer = ((tiers.last?.outer ?? 36) + 3) * look.baseplate.marginScale
        let yards = Float(look.baseplate.thicknessMeters / max(1e-6, s.presentation.tabletop.metersPerYard))
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
        root.addChild(top.entity("baseplate.top", StadiumLook.solid(s.palette["baseplate"] ?? "#101216",
                                                                    roughness: 0.28, metallic: 0.55, cull: false)))
        root.addChild(band.entity("baseplate.band", StadiumLook.solid(s.palette["baseplate"] ?? "#101216",
                                                                      roughness: 0.4, metallic: 0.6, cull: false)))
        var ring = MeshBuilder()
        ring.tube(rim, radius: Float(look.baseplate.rimRadiusYards), sides: 6)
        root.addChild(ring.entity("baseplate.rim", StadiumLook.glow(s.palette["baseplate.rim"] ?? "#FFE9C2",
                                                                    opacity: look.baseplate.rimOpacity, texture: nil)))
        return root
    }
}

/// Text drawn into textures: the ribbon board and the LED boards.
@MainActor
enum StadiumText {
    static func image(width: Int, height: Int, _ draw: (CGContext, CGSize) -> Void) -> CGImage? {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let size = CGSize(width: width, height: height)
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            draw(ctx.cgContext, size)
        }.cgImage
    }

    static func texture(_ img: CGImage?) -> TextureResource? {
        guard let img else { return nil }
        var o = TextureResource.CreateOptions(semantic: .color)
        o.mipmapsMode = .allocateAndGenerateAll
        return try? TextureResource(image: img, options: o)
    }

    static func ribbonKey(_ s: SceneSpec) -> String {
        "\(s.teams.away.abbr)\(Int(s.status.awayScore))|\(s.teams.home.abbr)\(Int(s.status.homeScore))|\(s.status.downDistance)|\(s.status.redZone)|\(s.status.label)"
    }

    static func ribbonImage(_ s: SceneSpec, look: SceneSpec.Look) -> CGImage? {
        let h = look.ribbon.heightPixels
        let w = h * Int((look.ribbon.segmentYards / ((s.bowl.ribbon?.rise[1] ?? 23.6) - (s.bowl.ribbon?.rise[0] ?? 21))).rounded())
        return image(width: max(256, w), height: h) { ctx, size in
            UIColor(cgColor: StadiumLook.color(s.palette[s.bowl.ribbon?.color ?? ""] ?? "#05060A").cgColor).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            let ink = StadiumLook.color(s.palette[s.bowl.ribbon?.text ?? ""] ?? "#F7F6F2")
            let font = UIFont.systemFont(ofSize: size.height * 0.56, weight: .heavy)
            var x: CGFloat = size.height * 0.4
            func chip(_ t: SceneSpec.Team, _ score: Double) {
                let rect = CGRect(x: x, y: size.height * 0.16, width: size.height * 1.35, height: size.height * 0.68)
                StadiumLook.color(t.chip).setFill()
                UIBezierPath(roundedRect: rect, cornerRadius: size.height * 0.08).fill()
                let abbr = NSAttributedString(string: t.abbr, attributes: [.font: UIFont.systemFont(ofSize: size.height * 0.42, weight: .black),
                                                                           .foregroundColor: UIColor.white])
                let ab = abbr.size()
                abbr.draw(at: CGPoint(x: rect.midX - ab.width / 2, y: rect.midY - ab.height / 2))
                x = rect.maxX + size.height * 0.3
                let n = NSAttributedString(string: "\(Int(score))", attributes: [.font: font, .foregroundColor: ink])
                n.draw(at: CGPoint(x: x, y: (size.height - n.size().height) / 2))
                x += n.size().width + size.height * 0.7
            }
            chip(s.teams.away, s.status.awayScore)
            chip(s.teams.home, s.status.homeScore)
            var tail = [s.status.label, s.status.downDistance].filter { !$0.isEmpty }.joined(separator: "   ·   ")
            if s.status.redZone { tail += "   ·   RED ZONE" }
            let t = NSAttributedString(string: tail.uppercased(), attributes: [.font: UIFont.systemFont(ofSize: size.height * 0.44, weight: .bold),
                                                                               .foregroundColor: ink])
            t.draw(at: CGPoint(x: x, y: (size.height - t.size().height) / 2))
        }
    }

    static func ribbon(_ s: SceneSpec, look: SceneSpec.Look) -> TextureResource? {
        texture(ribbonImage(s, look: look))
    }

    static func updateRibbon(_ tex: TextureResource, _ s: SceneSpec, look: SceneSpec.Look) {
        guard let img = ribbonImage(s, look: look) else { return }
        try? tex.replace(withImage: img, options: .init(semantic: .color))
    }

    /// The LED boards along the front wall: each club's colours and name, in
    /// turn, 24 yards to a panel.
    static func boards(_ s: SceneSpec) -> TextureResource? {
        texture(image(width: 1024, height: 64) { ctx, size in
            let half = size.width / 2
            for (i, t) in [s.teams.home, s.teams.away].enumerated() {
                let rect = CGRect(x: CGFloat(i) * half, y: 0, width: half, height: size.height)
                UIColor(white: 0.03, alpha: 1).setFill()
                ctx.fill(rect)
                StadiumLook.color(t.chip).setFill()
                ctx.fill(CGRect(x: rect.minX, y: 0, width: half * 0.12, height: size.height))
                ctx.fill(CGRect(x: rect.maxX - half * 0.04, y: 0, width: half * 0.04, height: size.height))
                let label = NSAttributedString(string: t.name.uppercased(), attributes: [
                    .font: UIFont.systemFont(ofSize: size.height * 0.52, weight: .heavy),
                    .foregroundColor: UIColor(white: 0.92, alpha: 1), .kern: 6])
                let ls = label.size()
                label.draw(at: CGPoint(x: rect.minX + half * 0.18, y: (size.height - ls.height) / 2))
            }
        })
    }
}
