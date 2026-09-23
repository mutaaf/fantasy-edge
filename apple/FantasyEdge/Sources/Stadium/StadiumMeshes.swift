import RealityKit
import simd

/// Geometry with normals and texture coordinates, in the renderer's local
/// yards. Everything a material needs to light and texture a surface is
/// built here; what it looks like is `StadiumLook`'s business.
struct MeshBuilder {
    var positions: [SIMD3<Float>] = []
    var normals: [SIMD3<Float>] = []
    var uvs: [SIMD2<Float>] = []
    var indices: [UInt32] = []

    var isEmpty: Bool { indices.isEmpty }
    var triangles: Int { indices.count / 3 }

    /// A quad from four corners in order, with its own normal and UVs.
    mutating func quad(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>, _ d: SIMD3<Float>,
                       uv: (SIMD2<Float>, SIMD2<Float>, SIMD2<Float>, SIMD2<Float>) =
                        (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, 1), SIMD2(0, 1)),
                       normal: SIMD3<Float>? = nil) {
        let n = normal ?? {
            let raw = simd_cross(b - a, d - a)
            return simd_length(raw) > 1e-9 ? simd_normalize(raw) : SIMD3(0, 1, 0)
        }()
        let base = UInt32(positions.count)
        positions += [a, b, c, d]
        normals += [n, n, n, n]
        uvs += [uv.0, uv.1, uv.2, uv.3]
        indices += [base, base + 1, base + 2, base, base + 2, base + 3]
    }

    /// A rectangle lying on y, from x0..x1 and z0..z1, UVs in `tile` yards.
    mutating func floor(x0: Double, x1: Double, z0: Double, z1: Double, y: Double, tile: Double) {
        let p = { (x: Double, z: Double) in SceneMath.local(x: x, y: y, z: z) }
        let t = Float(max(1e-6, tile))
        let uv = { (x: Double, z: Double) in SIMD2(Float(x) / t, Float(z) / t) }
        quad(p(x0, z1), p(x1, z1), p(x1, z0), p(x0, z0),
             uv: (uv(x0, z1), uv(x1, z1), uv(x1, z0), uv(x0, z0)), normal: SIMD3(0, 1, 0))
    }

    /// A painted stripe on the ground: u runs along it in `tile` yards, v
    /// crosses it 0..1, which is how the paint mask's worn edges line up.
    mutating func stripe(from: SIMD2<Double>, to: SIMD2<Double>, width: Double, y: Double, tile: Double) {
        let dir = SIMD2(to.x - from.x, to.y - from.y)
        let len = max(1e-6, (dir.x * dir.x + dir.y * dir.y).squareRoot())
        let side = SIMD2(-dir.y / len, dir.x / len) * (width / 2)
        let p = { (v: SIMD2<Double>) in SceneMath.local(x: v.x, y: y, z: v.y) }
        let u = Float(len / max(1e-6, tile))
        quad(p(from - side), p(to - side), p(to + side), p(from + side),
             uv: (SIMD2(0, 0), SIMD2(u, 0), SIMD2(u, 1), SIMD2(0, 1)), normal: SIMD3(0, 1, 0))
    }

    /// An axis-aligned box in local space.
    mutating func box(min lo: SIMD3<Float>, max hi: SIMD3<Float>, tile: Float = 1) {
        let x0 = lo.x, y0 = lo.y, z0 = lo.z, x1 = hi.x, y1 = hi.y, z1 = hi.z
        let w = (x1 - x0) / tile, h = (y1 - y0) / tile, d = (z1 - z0) / tile
        quad(SIMD3(x0, y1, z1), SIMD3(x1, y1, z1), SIMD3(x1, y1, z0), SIMD3(x0, y1, z0),
             uv: (SIMD2(0, 0), SIMD2(w, 0), SIMD2(w, d), SIMD2(0, d)), normal: SIMD3(0, 1, 0))
        quad(SIMD3(x0, y0, z1), SIMD3(x1, y0, z1), SIMD3(x1, y1, z1), SIMD3(x0, y1, z1),
             uv: (SIMD2(0, 0), SIMD2(w, 0), SIMD2(w, h), SIMD2(0, h)), normal: SIMD3(0, 0, 1))
        quad(SIMD3(x1, y0, z0), SIMD3(x0, y0, z0), SIMD3(x0, y1, z0), SIMD3(x1, y1, z0),
             uv: (SIMD2(0, 0), SIMD2(w, 0), SIMD2(w, h), SIMD2(0, h)), normal: SIMD3(0, 0, -1))
        quad(SIMD3(x1, y0, z1), SIMD3(x1, y0, z0), SIMD3(x1, y1, z0), SIMD3(x1, y1, z1),
             uv: (SIMD2(0, 0), SIMD2(d, 0), SIMD2(d, h), SIMD2(0, h)), normal: SIMD3(1, 0, 0))
        quad(SIMD3(x0, y0, z0), SIMD3(x0, y0, z1), SIMD3(x0, y1, z1), SIMD3(x0, y1, z0),
             uv: (SIMD2(0, 0), SIMD2(d, 0), SIMD2(d, h), SIMD2(0, h)), normal: SIMD3(-1, 0, 0))
    }

    /// A tube through points. u runs 0..1 along the whole tube (so a trail
    /// texture fades from snap to landing), v goes round it.
    mutating func tube(_ pts: [SIMD3<Float>], radius: Float, sides: Int = 8,
                       uRange: ClosedRange<Float> = 0...1) {
        guard pts.count > 1 else { return }
        var lengths: [Float] = [0]
        for i in 1..<pts.count { lengths.append(lengths[i - 1] + simd_distance(pts[i - 1], pts[i])) }
        let total = max(1e-6, lengths.last!)
        let base = UInt32(positions.count)
        for (i, p) in pts.enumerated() {
            let ahead = pts[min(i + 1, pts.count - 1)] - pts[max(i - 1, 0)]
            let t = simd_length(ahead) > 1e-6 ? simd_normalize(ahead) : SIMD3(1, 0, 0)
            var n = simd_cross(t, SIMD3(0, 0, 1))
            if simd_length(n) < 1e-4 { n = simd_cross(t, SIMD3(0, 1, 0)) }
            n = simd_normalize(n)
            let b = simd_normalize(simd_cross(t, n))
            let u = uRange.lowerBound + (uRange.upperBound - uRange.lowerBound) * lengths[i] / total
            for k in 0...sides {
                let a = Float(k) / Float(sides) * 2 * .pi
                let dir = n * cos(a) + b * sin(a)
                positions.append(p + dir * radius)
                normals.append(dir)
                uvs.append(SIMD2(u, Float(k) / Float(sides)))
            }
        }
        let ring = UInt32(sides + 1)
        for i in 0..<UInt32(pts.count - 1) {
            for k in 0..<UInt32(sides) {
                let a = base + i * ring + k, b = a + 1, c = a + ring, d = c + 1
                indices += [a, c, b, b, c, d]
            }
        }
    }

    /// A surface of revolution about the x axis: `profile` is (x, radius)
    /// pairs from tip to tip. u goes round, v along - the football.
    mutating func lathe(_ profile: [(Float, Float)], sides: Int = 24) {
        guard profile.count > 1 else { return }
        let base = UInt32(positions.count)
        for (i, (x, r)) in profile.enumerated() {
            let prev = profile[max(0, i - 1)], next = profile[min(profile.count - 1, i + 1)]
            let slope = (next.1 - prev.1) / max(1e-6, next.0 - prev.0)
            for k in 0...sides {
                let a = Float(k) / Float(sides) * 2 * .pi
                let ring = SIMD3<Float>(0, cos(a), sin(a))
                positions.append(SIMD3(x, 0, 0) + ring * r)
                normals.append(simd_normalize(ring - SIMD3(slope, 0, 0)))
                uvs.append(SIMD2(Float(k) / Float(sides), Float(i) / Float(profile.count - 1)))
            }
        }
        let ringCount = UInt32(sides + 1)
        for i in 0..<UInt32(profile.count - 1) {
            for k in 0..<UInt32(sides) {
                let a = base + i * ringCount + k, b = a + 1, c = a + ringCount, d = c + 1
                indices += [a, b, c, b, d, c]
            }
        }
    }

    mutating func append(_ other: MeshBuilder) {
        let base = UInt32(positions.count)
        positions += other.positions
        normals += other.normals
        uvs += other.uvs
        indices += other.indices.map { $0 + base }
    }

    @MainActor
    func resource(_ name: String) -> MeshResource? {
        guard !indices.isEmpty else { return nil }
        var d = MeshDescriptor(name: name)
        d.positions = MeshBuffers.Positions(positions)
        d.normals = MeshBuffers.Normals(normals)
        d.textureCoordinates = MeshBuffers.TextureCoordinates(uvs)
        d.primitives = .triangles(indices)
        return try? MeshResource.generate(from: [d])
    }

    @MainActor
    func entity(_ name: String, _ material: any Material) -> ModelEntity {
        let e = ModelEntity()
        e.name = name
        if let m = resource(name) { e.model = ModelComponent(mesh: m, materials: [material]) }
        return e
    }
}
