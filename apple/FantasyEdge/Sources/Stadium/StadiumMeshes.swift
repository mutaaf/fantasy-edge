import RealityKit
import UIKit
import simd

/// Procedural geometry for the stadium and the tabletop. No stored assets:
/// every mesh is built from the scene's numbers, in yards, under a root the
/// renderer scales to metres.
@MainActor
enum StadiumMeshes {

    // MARK: materials

    static func material(_ hex: String, opacity: Double? = nil) -> UnlitMaterial {
        let c = SceneMath.rgba(hex)
        let alpha = Float(opacity ?? Double(c.w))
        var m = UnlitMaterial(color: UIColor(red: CGFloat(c.x), green: CGFloat(c.y),
                                             blue: CGFloat(c.z), alpha: 1))
        if alpha < 0.999 {
            m.blending = .transparent(opacity: .init(floatLiteral: alpha))
        }
        m.faceCulling = .none
        return m
    }

    // MARK: primitives

    static func mesh(_ positions: [SIMD3<Float>], _ indices: [UInt32], name: String) -> MeshResource? {
        guard !positions.isEmpty, !indices.isEmpty else { return nil }
        var d = MeshDescriptor(name: name)
        d.positions = MeshBuffers.Positions(positions)
        d.primitives = .triangles(indices)
        return try? MeshResource.generate(from: [d])
    }

    /// A flat rectangle on the plane y = `y`, from x0..x1 and z0..z1.
    static func plate(x0: Double, x1: Double, z0: Double, z1: Double, y: Double = 0,
                      color: String, opacity: Double? = nil, name: String) -> ModelEntity {
        let p = [SceneMath.local(x: x0, y: y, z: z0), SceneMath.local(x: x1, y: y, z: z0),
                 SceneMath.local(x: x1, y: y, z: z1), SceneMath.local(x: x0, y: y, z: z1)]
        let e = ModelEntity()
        if let m = mesh(p, [0, 1, 2, 0, 2, 3], name: name) {
            e.model = ModelComponent(mesh: m, materials: [material(color, opacity: opacity)])
        }
        e.name = name
        return e
    }

    /// Many flat rectangles as one mesh, so a hundred hash marks are one entity.
    static func plates(_ rects: [(Double, Double, Double, Double)], y: Double, color: String,
                       opacity: Double? = nil, name: String) -> ModelEntity {
        var p: [SIMD3<Float>] = []
        var idx: [UInt32] = []
        for (x0, x1, z0, z1) in rects {
            let b = UInt32(p.count)
            p += [SceneMath.local(x: x0, y: y, z: z0), SceneMath.local(x: x1, y: y, z: z0),
                  SceneMath.local(x: x1, y: y, z: z1), SceneMath.local(x: x0, y: y, z: z1)]
            idx += [b, b + 1, b + 2, b, b + 2, b + 3]
        }
        let e = ModelEntity()
        if let m = mesh(p, idx, name: name) {
            e.model = ModelComponent(mesh: m, materials: [material(color, opacity: opacity)])
        }
        e.name = name
        return e
    }

    /// A tube through points: an arc, a horizon, a rail. Six sides is enough
    /// at the size these are drawn and keeps a whole drive to a few hundred
    /// triangles.
    static func tube(_ pts: [SIMD3<Float>], radius: Float, sides: Int = 6) -> ([SIMD3<Float>], [UInt32]) {
        guard pts.count > 1 else { return ([], []) }
        var positions: [SIMD3<Float>] = []
        var indices: [UInt32] = []
        for (i, p) in pts.enumerated() {
            let ahead = pts[min(i + 1, pts.count - 1)] - pts[max(i - 1, 0)]
            let t = simd_length(ahead) > 1e-6 ? simd_normalize(ahead) : SIMD3(1, 0, 0)
            var n = simd_cross(t, SIMD3(0, 0, 1))
            if simd_length(n) < 1e-4 { n = simd_cross(t, SIMD3(0, 1, 0)) }
            n = simd_normalize(n)
            let b = simd_normalize(simd_cross(t, n))
            for k in 0..<sides {
                let a = Float(k) / Float(sides) * 2 * .pi
                positions.append(p + (n * cos(a) + b * sin(a)) * radius)
            }
        }
        let ring = UInt32(sides)
        for i in 0..<UInt32(pts.count - 1) {
            for k in 0..<ring {
                let a = i * ring + k, b = i * ring + (k + 1) % ring
                let c = a + ring, d = b + ring
                indices += [a, c, b, b, c, d]
            }
        }
        return (positions, indices)
    }

    static func tubeEntity(_ pieces: [[SIMD3<Float>]], radius: Float, color: String,
                           opacity: Double? = nil, name: String) -> ModelEntity {
        var positions: [SIMD3<Float>] = []
        var indices: [UInt32] = []
        for piece in pieces {
            let (p, i) = tube(piece, radius: radius)
            let base = UInt32(positions.count)
            positions += p
            indices += i.map { $0 + base }
        }
        let e = ModelEntity()
        if let m = mesh(positions, indices, name: name) {
            e.model = ModelComponent(mesh: m, materials: [material(color, opacity: opacity)])
        }
        e.name = name
        return e
    }

    // MARK: the field

    static func field(_ spec: SceneSpec) -> Entity {
        let root = Entity()
        root.name = "field"
        let f = spec.field, pal = spec.palette
        let half = f.width / 2
        let turfA = pal["turf.a"] ?? "#1E6A34", turfB = pal["turf.b"] ?? "#237A3C"
        root.addChild(plate(x0: -f.endZone - 6, x1: f.length + f.endZone + 6, z0: -half - 6,
                            z1: half + 6, y: -0.02, color: pal["turf.surround"] ?? "#17401F",
                            name: "surround"))
        var stripesA: [(Double, Double, Double, Double)] = []
        var stripesB: [(Double, Double, Double, Double)] = []
        var x = 0.0, i = 0
        while x < f.length {
            if i % 2 == 0 { stripesB.append((x, x + f.stripeEvery, -half, half)) }
            else { stripesA.append((x, x + f.stripeEvery, -half, half)) }
            x += f.stripeEvery; i += 1
        }
        root.addChild(plates(stripesA, y: 0, color: turfA, name: "turf.a"))
        root.addChild(plates(stripesB, y: 0, color: turfB, name: "turf.b"))
        root.addChild(plate(x0: -f.endZone, x1: 0, z0: -half, z1: half,
                            color: spec.teams.home.chip, name: "endzone.home"))
        root.addChild(plate(x0: f.length, x1: f.length + f.endZone, z0: -half, z1: half,
                            color: spec.teams.away.chip, name: "endzone.away"))
        let line = pal["line.yard"] ?? "#FFFFFF"
        var heavy: [(Double, Double, Double, Double)] = []
        var light: [(Double, Double, Double, Double)] = []
        var yard = 0.0
        while yard <= f.length {
            if yard.truncatingRemainder(dividingBy: 10) == 0 {
                heavy.append((yard - 0.22, yard + 0.22, -half, half))
            } else {
                light.append((yard - 0.14, yard + 0.14, -half, half))
            }
            yard += f.stripeEvery
        }
        let hash = half - f.hashFromSideline
        var hashes: [(Double, Double, Double, Double)] = []
        for y in 1..<Int(f.length) {
            for z in [hash, -hash] {
                hashes.append((Double(y) - 0.06, Double(y) + 0.06, z - 0.35, z + 0.35))
            }
        }
        root.addChild(plates(heavy, y: 0.01, color: line, opacity: 0.85, name: "lines.ten"))
        root.addChild(plates(light, y: 0.01, color: line, opacity: 0.55, name: "lines.five"))
        root.addChild(plates(hashes, y: 0.01, color: line, opacity: 0.45, name: "hashes"))
        // Yard numbers, flat on the grass and read from the home sideline.
        var n = f.numbersEvery
        while n < f.length {
            let label = "\(Int(n <= 50 ? n : f.length - n))"
            let text = MeshResource.generateText(label, extrusionDepth: 0.02,
                                                 font: .systemFont(ofSize: 2.4, weight: .bold),
                                                 containerFrame: .zero, alignment: .center,
                                                 lineBreakMode: .byClipping)
            let e = ModelEntity(mesh: text, materials: [material(line, opacity: 0.7)])
            let bounds = text.bounds.extents
            e.orientation = simd_quatf(angle: -.pi / 2, axis: SIMD3(1, 0, 0))
            e.position = SceneMath.local(x: n, y: 0.02, z: half - 9) + SIMD3(-bounds.x / 2, 0, bounds.y / 2)
            root.addChild(e)
            n += f.numbersEvery
        }
        return root
    }

    // MARK: the bowl

    static func tier(_ tier: SceneSpec.Tier, shape: SceneSpec.Shape, color: String,
                     segments: Int = 96, rows: Int = 5) -> ModelEntity {
        var positions: [SIMD3<Float>] = []
        var indices: [UInt32] = []
        for r in 0...rows {
            let m = tier.inner + (tier.outer - tier.inner) * Double(r) / Double(rows)
            let y = SceneMath.tierHeight(tier, offset: m)
            for s in 0...segments {
                let (x, z) = SceneMath.bowlPoint(shape, offset: m, angle: Double(s) / Double(segments) * 2 * .pi)
                positions.append(SIMD3(Float(x), Float(y), Float(z)))
            }
        }
        let cols = UInt32(segments + 1)
        for r in 0..<UInt32(rows) {
            for s in 0..<UInt32(segments) {
                let a = r * cols + s, b = a + 1, c = a + cols, d = c + 1
                indices += [a, c, b, b, c, d]
            }
        }
        let e = ModelEntity()
        if let m = mesh(positions, indices, name: "tier.\(tier.name)") {
            e.model = ModelComponent(mesh: m, materials: [material(color)])
        }
        e.name = "tier.\(tier.name)"
        return e
    }

    /// The crowd as tiny quads on the tiers, one mesh per section and colour.
    /// Sections are the two sidelines, which is what a tint lights.
    static func crowd(_ spec: SceneSpec, tiers: [SceneSpec.Tier], count: Int) -> [String: [String: ModelEntity]] {
        struct Rng { var s: UInt64; mutating func next() -> Double { s = s &* 6364136223846793005 &+ 1442695040888963407; return Double(s >> 11) / Double(1 << 53) } }
        var rng = Rng(s: 12)
        let shape = spec.bowl.shape, crowd = spec.bowl.crowd, pal = spec.palette
        var buckets: [String: [String: ([SIMD3<Float>], [UInt32])]] = [:]
        let size: Float = 0.45
        guard !tiers.isEmpty else { return [:] }
        for _ in 0..<count {
            let tier = tiers[min(tiers.count - 1, Int(rng.next() * Double(tiers.count)))]
            let m = tier.inner + 0.5 + (tier.outer - tier.inner - 1) * rng.next()
            let t = rng.next() * 2 * .pi
            let (x, z) = SceneMath.bowlPoint(shape, offset: m, angle: t)
            let y = SceneMath.tierHeight(tier, offset: m) + 0.4
            let section = z >= 0 ? "home" : "away"
            let r = rng.next()
            let visitors = x > 40 && z < -10
            let colour: String
            if visitors {
                colour = r < 0.8 ? crowd.away : (pal[crowd.neutral] ?? "#F4F1EA")
            } else {
                colour = r < 0.62 ? crowd.home : r < 0.86 ? (pal[crowd.neutral] ?? "#F4F1EA")
                                                         : (pal[crowd.dark] ?? "#2A2A2A")
            }
            let c = SIMD3(Float(x), Float(y), Float(z))
            var bucket = buckets[section, default: [:]][colour, default: ([], [])]
            let base = UInt32(bucket.0.count)
            bucket.0 += [c + SIMD3(-size, 0, -size), c + SIMD3(size, 0, -size),
                         c + SIMD3(size, size, size), c + SIMD3(-size, size, size)]
            bucket.1 += [base, base + 1, base + 2, base, base + 2, base + 3]
            buckets[section, default: [:]][colour] = bucket
        }
        var out: [String: [String: ModelEntity]] = [:]
        for (section, colours) in buckets {
            for (colour, (p, i)) in colours {
                let e = ModelEntity()
                if let m = mesh(p, i, name: "crowd.\(section)") {
                    e.model = ModelComponent(mesh: m, materials: [material(colour)])
                }
                e.name = "crowd.\(section).\(colour)"
                out[section, default: [:]][colour] = e
            }
        }
        return out
    }

    /// Light banks on the far rim, each a lamp and a soft glow around it.
    static func rimLights(_ spec: SceneSpec, rim: Double, height: Double, glow: Float = 9,
                          lamp size: SIMD2<Float> = SIMD2(10, 4)) -> Entity {
        let root = Entity()
        root.name = "rim"
        let lights = spec.bowl.rimLights
        let colour = spec.palette[lights.color] ?? "#FFF8E6"
        for k in 0..<lights.count {
            let t = Double(k) * .pi / Double(max(1, lights.count / 2)) + 0.3
            let (x, z) = SceneMath.bowlPoint(spec.bowl.shape, offset: rim, angle: t)
            if lights.side == "far" && z > 12 { continue }
            let lamp = ModelEntity(mesh: .generateBox(width: size.x, height: size.y, depth: 0.6),
                                   materials: [material(colour)])
            lamp.position = SIMD3(Float(x), Float(height), Float(z))
            lamp.look(at: SIMD3(0, 0, 0), from: lamp.position, relativeTo: nil)
            // No halo sphere. A translucent unlit sphere is not a glow in
            // RealityKit - there is no additive blend here - and against the
            // night sky it rendered as a grey disc around every lamp.
            _ = glow
            root.addChild(lamp)
        }
        return root
    }
}
