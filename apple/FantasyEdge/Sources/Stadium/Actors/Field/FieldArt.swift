import Foundation
import simd

// What the scene says about the painted art that changes per game, and the
// glyph shapes it is set in. The scene lays it out (fantasyedge/scene.py
// `field_art`); this file only applies the layout, so the web and Android
// draw the same letters in the same places.

extension SceneSpec {
    /// A line of text on the grass. A glyph point (gx, gy), in em units with
    /// cap height 1, lands at origin + (gx * along + gy * up) * capHeight in
    /// (x, z) yards.
    public struct ArtText: Decodable, Equatable, Sendable {
        public let text: String
        public let capHeight: Double
        public let origin: [Double]
        public let along: [Double]
        public let up: [Double]
        public let tint: String
    }

    public struct EndZoneArt: Decodable, Equatable, Sendable {
        public let side: String
        public let text: String
        public let capHeight: Double
        public let origin: [Double]
        public let along: [Double]
        public let up: [Double]
        public let tint: String

        var layout: ArtText {
            ArtText(text: text, capHeight: capHeight, origin: origin, along: along, up: up, tint: tint)
        }
    }

    public struct MidfieldArt: Decodable, Equatable, Sendable {
        public let center: [Double]
        public let outer: Double
        public let inner: Double
        public let tint: String
        public let text: ArtText?
    }

    public struct FieldArt: Decodable, Equatable, Sendable {
        public let glyphs: String
        public let tracking: Double
        public let endZones: [EndZoneArt]
        public let midfield: MidfieldArt
    }
}

/// The field font: Graduate (SIL OFL 1.1) as triangles, from
/// assets/actors/field/fonts/glyphs.json.
struct FieldGlyphs: Decodable {
    struct Glyph: Decodable {
        let triangles: [[[Double]]]
        let minX: Double
        let width: Double
    }
    let space: Double
    let glyphs: [String: Glyph]

    private static var cache: [String: FieldGlyphs] = [:]

    @MainActor
    static func load(_ rel: String) -> FieldGlyphs? {
        if let hit = cache[rel] { return hit }
        guard let folder = StadiumAssets.folder,
              let data = try? Data(contentsOf: folder.appendingPathComponent(rel)),
              let font = try? JSONDecoder().decode(FieldGlyphs.self, from: data) else { return nil }
        cache[rel] = font
        return font
    }

    /// Append a laid-out line of text to `b`, flat on the grass at `lift`.
    func set(_ t: SceneSpec.ArtText, tracking: Double, lift: Double, into b: inout MeshBuilder) {
        guard t.origin.count == 2, t.along.count == 2, t.up.count == 2 else { return }
        var pen = 0.0
        for ch in t.text.uppercased() {
            if ch == " " { pen += space; continue }
            guard let g = glyphs[String(ch)] else { continue }
            for tri in g.triangles where tri.count == 3 {
                let pts = tri.map { p -> SIMD3<Float> in
                    let gx = pen + (p[0] - g.minX), gy = p[1]
                    let x = t.origin[0] + (gx * t.along[0] + gy * t.up[0]) * t.capHeight
                    let z = t.origin[1] + (gx * t.along[1] + gy * t.up[1]) * t.capHeight
                    return SceneMath.local(x: x, y: lift, z: z)
                }
                b.triangle(pts[0], pts[1], pts[2])
            }
            pen += g.width + tracking
        }
    }
}

extension MeshBuilder {
    /// One triangle facing up, wound counter-clockwise seen from above.
    mutating func triangle(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD3<Float>) {
        let up = simd_cross(b - a, c - a).y >= 0
        let base = UInt32(positions.count)
        positions += up ? [a, b, c] : [a, c, b]
        normals += [SIMD3(0, 1, 0), SIMD3(0, 1, 0), SIMD3(0, 1, 0)]
        uvs += [SIMD2(0, 0), SIMD2(0, 0), SIMD2(0, 0)]
        indices += [base, base + 1, base + 2]
    }
}
