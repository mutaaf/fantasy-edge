import Foundation
import Metal
import RealityKit
import simd

/// The field: floodlit turf grown blade by blade, mowing stripes that are two
/// lean directions rather than two greens, wear, the painted markings of the
/// scene's league, each club's end zone and name, and the home ring at
/// midfield. Reads `visual.field` and `scene.field` (art, markings).
///
/// Every marking is one of two distance-field textures (white, yellow) that
/// hold half the field; the other half is the same texture under a half turn,
/// which a football field is. So all of the paint - lines, hashes, numerals,
/// arrows, limit and coaching lines - costs two draw parts, and the edge is
/// exact at any distance because it is a threshold, not a blurred mask.
///
/// Draw parts: surround 1, stripes 2, end zones 2, ring 1, paint 2,
/// lettering 1, grass through the paint 1, wear 1 - eleven.
@MainActor
final class FieldActor: StadiumActor {
    let name = "field"
    let root = Entity()

    private var textures: [String: TextureResource] = [:]
    private var loading: Set<String> = []
    private var pending: [(ModelEntity, String, (TextureResource) -> any Material)] = []

    init() { root.name = "actor.field" }

    func build(_ c: StadiumContext) {
        clear()
        pending.removeAll()
        let s = c.spec, V = c.look.field, T = V.turf, P = V.paint, L = V.lift, K = V.canvas
        let a = c.assets
        let f = s.field
        let half = f.width / 2
        let tile = T.tileYards
        let albedo = a.texture("field.turfAlbedo"), rough = a.texture("field.turfRoughness")
        let normals = [a.texture("field.turfWithNormal"), a.texture("field.turfAgainstNormal")]

        // Surround: the apron out to the wall, blades leaning one way.
        var surround = MeshBuilder()
        surround.floor(x0: K.x0, x1: K.x1, z0: -(half + (K.y1 - f.width)), z1: half + (K.y1 - f.width),
                       y: -0.03, tile: tile)
        add(surround.entity("turf.surround", turf(T.surroundTint, T.stripeRoughness[0], albedo, rough, normals[0], T)), order: 0)

        // Stripes: the same blades, combed with the mower and against it.
        var stripes = [MeshBuilder(), MeshBuilder()]
        var x = -f.endZone, i = 0
        while x < f.length + f.endZone - 1e-6 {
            let to = min(f.length + f.endZone, x + f.stripeEvery)
            stripes[i % 2].floor(x0: x, x1: to, z0: -half, z1: half, y: 0, tile: tile)
            x = to; i += 1
        }
        for k in 0..<2 {
            let m = turf(T.stripeTint[k % T.stripeTint.count], T.stripeRoughness[k % T.stripeRoughness.count],
                         albedo, rough, normals[k], T)
            add(stripes[k].entity("turf.stripe.\(k)", m), order: 1)
        }

        // Wear and macro tone, over the whole canvas, from the league's map.
        var wear = MeshBuilder()
        canvasQuad(&wear, x0: K.x0, x1: K.x1, lift: L.wear, canvas: K, width: f.width, half: false)
        let wearEntity = wear.entity("turf.wear", SimpleMaterial())
        wearEntity.isEnabled = false
        // Over the paint as well as the grass: where the turf is trampled the
        // lines are too, and a line as clean at the hash as at the wall is CG.
        add(wearEntity, order: 6)

        // End zones: club paint over the grass.
        for (team, x0, x1) in [(s.teams.home, -f.endZone, 0.0), (s.teams.away, f.length, f.length + f.endZone)] {
            var b = MeshBuilder()
            b.floor(x0: x0, x1: x1, z0: -half, z1: half, y: L.endZone, tile: tile)
            var m = PhysicallyBasedMaterial()
            m.baseColor = .init(tint: StadiumLook.color(team.chip))
            m.roughness = .init(floatLiteral: Float(P.roughness))
            m.blending = .transparent(opacity: .init(floatLiteral: Float(P.endZoneOpacity)))
            add(b.entity("endzone.\(team.abbr)", m), order: 3)
        }

        // Midfield ring in the home club's chip, under the paint so the yard
        // lines stay visible across it.
        if let art = f.art {
            let mid = art.midfield
            var ring = MeshBuilder()
            let segments = c.tabletop ? 48 : 128
            let cx = mid.center.first ?? 50, cz = mid.center.count > 1 ? mid.center[1] : 0
            for k in 0..<segments {
                let a0 = Double(k) / Double(segments) * 2 * .pi, a1 = Double(k + 1) / Double(segments) * 2 * .pi
                let p = { (r: Double, t: Double) in SceneMath.local(x: cx + r * cos(t), y: L.ring, z: cz + r * sin(t)) }
                ring.triangle(p(mid.outer, a0), p(mid.outer, a1), p(mid.inner, a1))
                ring.triangle(p(mid.outer, a0), p(mid.inner, a1), p(mid.inner, a0))
            }
            var m = PhysicallyBasedMaterial()
            m.baseColor = .init(tint: StadiumLook.color(s.teams.home.chip))
            m.roughness = .init(floatLiteral: Float(P.roughness))
            add(ring.entity("midfield.ring", m), order: 3)
        }

        // Paint: two distance fields, each drawn as two half-canvas quads.
        var paint = MeshBuilder()
        canvasQuad(&paint, x0: K.x0, x1: K.halfX1, lift: L.paint, canvas: K, width: f.width, half: true)
        canvasQuad(&paint, x0: K.halfX1, x1: K.x1, lift: L.paint, canvas: K, width: f.width, half: true, turned: true)
        let white = paint.entity("paint.white", SimpleMaterial())
        var yellowMesh = MeshBuilder()
        yellowMesh.append(paint)
        let yellow = yellowMesh.entity("paint.yellow", SimpleMaterial())
        white.isEnabled = false
        yellow.isEnabled = false
        add(white, order: 4)
        add(yellow, order: 4)

        // Grass through the paint: the turf again, over the paint and the
        // lettering, shown only where blades stand up through them. Over bare
        // turf it is turf on turf, so it only reads where there is paint.
        if let through = a.texture("field.turfGrassThrough") {
            var over = MeshBuilder()
            over.floor(x0: K.x0, x1: K.x1, z0: -(half + (K.y1 - f.width)), z1: half + (K.y1 - f.width),
                       y: L.art + 0.002, tile: tile)
            var m = turf(T.stripeTint[0], T.stripeRoughness[0], albedo, rough, normals[0], T)
            m.blending = .transparent(opacity: .init(scale: Float(P.grassThrough), texture: StadiumLook.repeating(through)))
            add(over.entity("paint.grass", m), order: 5)
        }

        // Lettering: each club's name across its end zone, the home name at midfield.
        if let art = f.art, let font = FieldGlyphs.load(art.glyphs) {
            var letters = MeshBuilder()
            for z in art.endZones { font.set(z.layout, tracking: art.tracking, lift: L.art, into: &letters) }
            if let t = art.midfield.text { font.set(t, tracking: art.tracking, lift: L.art, into: &letters) }
            var m = PhysicallyBasedMaterial()
            m.baseColor = .init(tint: StadiumLook.color(P.white))
            m.roughness = .init(floatLiteral: Float(P.roughness))
            add(letters.entity("lettering", m), order: 4)
        }

        // The league's maps, loaded once and then handed to the meshes waiting for them.
        let folder = f.markings.map { ($0 as NSString).deletingLastPathComponent } ?? "actors/field/markings"
        let fieldRoot = (folder as NSString).deletingLastPathComponent          // actors/field
        let league = s.league
        let path = { (template: String) in "\(fieldRoot)/" + template.replacingOccurrences(of: "{league}", with: league) }
        let threshold = Float(P.threshold), paintRough = Float(P.roughness)
        want(path(V.perLeague.variation), for: wearEntity) { tex in
            var m = PhysicallyBasedMaterial()
            m.baseColor = .init(tint: StadiumLook.color(T.wearTint))
            m.roughness = .init(floatLiteral: 0.95)
            m.specular = .init(floatLiteral: Float(T.specular))
            m.blending = .transparent(opacity: .init(scale: Float(T.wearStrength), texture: StadiumLook.clamped(tex)))
            return m
        }
        for (entity, hex, template) in [(white, P.white, V.perLeague.paintWhite), (yellow, P.yellow, V.perLeague.paintYellow)] {
            want(path(template), for: entity) { tex in
                var m = PhysicallyBasedMaterial()
                m.baseColor = .init(tint: StadiumLook.color(hex))
                m.roughness = .init(floatLiteral: paintRough)
                m.blending = .transparent(opacity: .init(texture: StadiumLook.clamped(tex)))
                m.opacityThreshold = threshold
                return m
            }
        }
    }

    // MARK: pieces

    private func add(_ e: ModelEntity, order: Int32) {
        StadiumLook.ground(e, order: order)
        root.addChild(e)
    }

    private func turf(_ tint: String, _ roughness: Double, _ albedo: TextureResource?, _ roughMap: TextureResource?,
                      _ normal: TextureResource?, _ T: SceneSpec.Look.FieldTurf) -> PhysicallyBasedMaterial {
        var m = StadiumLook.turf(tint: tint, roughness: roughness, albedo: albedo, roughnessMap: roughMap, normal: normal)
        m.specular = .init(floatLiteral: Float(T.specular))
        return m
    }

    /// A quad over part of the markings canvas. Field yards (x, z) map to the
    /// canvas as y = width/2 - z (the canvas's near sideline is the home one).
    /// With `half`, UVs address the half texture: the left half directly and
    /// the right half through the half turn (x, y) -> (100 - x, width - y).
    private func canvasQuad(_ b: inout MeshBuilder, x0: Double, x1: Double, lift: Double,
                            canvas K: SceneSpec.Look.FieldCanvas, width: Double, half: Bool, turned: Bool = false) {
        let yz = { (y: Double) in width / 2 - y }
        let uv = { (x: Double, y: Double) -> SIMD2<Float> in
            guard half else {
                return SIMD2(Float((x - K.x0) / (K.x1 - K.x0)), Float((y - K.y0) / (K.y1 - K.y0)))
            }
            let (hx, hy) = turned ? (100 - x, width - y) : (x, y)
            return SIMD2(Float((hx - K.x0) / (K.halfTextureX1 - K.x0)), Float((hy - K.y0) / (K.y1 - K.y0)))
        }
        let p = { (x: Double, y: Double) in SceneMath.local(x: x, y: lift, z: yz(y)) }
        // corners in the order MeshBuilder.floor uses, so the quad faces up
        b.quad(p(x0, K.y0), p(x1, K.y0), p(x1, K.y1), p(x0, K.y1),
               uv: (uv(x0, K.y0), uv(x1, K.y0), uv(x1, K.y1), uv(x0, K.y1)), normal: SIMD3(0, 1, 0))
    }

    private func want(_ rel: String, for entity: ModelEntity, _ make: @escaping (TextureResource) -> any Material) {
        if let tex = textures[rel] {
            entity.model?.materials = [make(tex)]
            entity.isEnabled = true
            return
        }
        pending.append((entity, rel, make))
        guard !loading.contains(rel), let folder = StadiumAssets.folder else { return }
        loading.insert(rel)
        let url = folder.appendingPathComponent(rel)
        Task { @MainActor in
            var options = TextureResource.CreateOptions(semantic: .color)
            options.mipmapsMode = .allocateAndGenerateAll
            guard let tex = try? await TextureResource(contentsOf: url, options: options) else {
                StadiumLog.log.error("[stadium] field: \(rel) failed to load")
                return
            }
            self.textures[rel] = tex
            for (e, r, make) in self.pending where r == rel {
                e.model?.materials = [make(tex)]
                e.isEnabled = true
            }
            self.pending.removeAll { $0.1 == rel }
        }
    }
}
