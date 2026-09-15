import CoreGraphics
import RealityKit
import simd

/// The field: lit turf with a mowing stripe, the painted lines, hashes and
/// numbers, and each club's end zone. Reads `visual.field`.
@MainActor
final class FieldActor: StadiumActor {
    let name = "field"
    let root = Entity()

    init() { root.name = "actor.field" }

    func build(_ c: StadiumContext) {
        clear()
        let s = c.spec, V = c.look.field, T = V.turf, L = V.lines
        let a = c.assets
        let f = s.field
        let half = f.width / 2
        let tile = T.tileYards
        let albedo = a.texture("field.turfAlbedo"), rough = a.texture("field.turfRoughness")
        let normal = a.texture("field.turfNormal"), mask = a.texture("field.paint")

        var surround = MeshBuilder()
        surround.floor(x0: -f.endZone - 8, x1: f.length + f.endZone + 8, z0: -half - 9, z1: half + 9, y: -0.03, tile: tile)
        let surroundEntity = surround.entity("turf.surround",
                                             StadiumLook.turf(tint: T.surroundTint, roughness: T.stripeRoughness[0],
                                                              albedo: albedo, roughnessMap: rough, normal: normal))
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
                                                       albedo: albedo, roughnessMap: rough, normal: normal))
            StadiumLook.ground(e, order: 1)
            root.addChild(e)
        }

        // End zones: club paint over the grass, the club's name across it.
        let white = s.palette["line.yard"] ?? "#FFFFFF"
        for (team, x0, x1) in [(s.teams.home, -f.endZone, 0.0), (s.teams.away, f.length, f.length + f.endZone)] {
            var b = MeshBuilder()
            b.floor(x0: x0, x1: x1, z0: -half, z1: half, y: L.lift * 0.5, tile: tile)
            let e = b.entity("endzone.\(team.abbr)", StadiumLook.paint(team.chip, opacity: T.endZonePaintOpacity,
                                                                       roughness: T.paintRoughness, mask: mask))
            StadiumLook.ground(e, order: 2)
            root.addChild(e)
            let label = MeshResource.generateText(team.name.uppercased(), extrusionDepth: 0.02,
                                                  font: .systemFont(ofSize: CGFloat(L.endZoneTextHeight), weight: .black),
                                                  containerFrame: .zero, alignment: .center, lineBreakMode: .byClipping)
            let text = ModelEntity(mesh: label, materials: [StadiumLook.paint(white, opacity: T.paintOpacity * 0.9,
                                                                                roughness: T.paintRoughness, mask: mask)])
            let home = x0 < 0
            // Flat on the grass, running across the field, its top toward the end line.
            let flat = simd_quatf(angle: -.pi / 2, axis: SIMD3(1, 0, 0))
            let turn = simd_quatf(angle: home ? .pi / 2 : -.pi / 2, axis: SIMD3(0, 1, 0))
            text.orientation = turn * flat
            text.position = SceneMath.local(x: (x0 + x1) / 2, y: L.lift, z: 0) - (turn * flat).act(label.bounds.center)
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
        let paint = StadiumLook.paint(white, opacity: T.paintOpacity, roughness: T.paintRoughness, mask: mask)
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
            for near in [true, false] {
                let e = ModelEntity(mesh: mesh, materials: [paint])
                let flat = simd_quatf(angle: -.pi / 2, axis: SIMD3(1, 0, 0))
                let turn = simd_quatf(angle: near ? 0 : .pi, axis: SIMD3(0, 1, 0))
                e.orientation = turn * flat
                let at = SceneMath.local(x: n, y: L.lift, z: near ? half - L.numberInset : -(half - L.numberInset))
                e.position = at - (turn * flat).act(mesh.bounds.center)
                StadiumLook.ground(e, order: 3)
                root.addChild(e)
            }
            n += f.numbersEvery
        }
    }
}
