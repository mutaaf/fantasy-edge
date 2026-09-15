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
    /// Meshes the Shader Graph paint takes over once it loads: entity, colour,
    /// whether it reads the markings mask, and that mask's path.
    private var paintTargets: [(ModelEntity, String, Bool, String?)] = []

    init() { root.name = "actor.field" }

    func build(_ c: StadiumContext) {
        clear()
        pending.removeAll()
        paintTargets.removeAll()
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
        let surroundEntity = surround.entity("turf.surround", turf(T.surroundTint, T.stripeRoughness[0], albedo, rough, normals[0], T))
        add(surroundEntity, order: 0)
        var turfTargets = [(surroundEntity, T.surroundTint, T.stripeRoughness[0], T.surroundSheen, "turfWithNormal")]

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
            let e = stripes[k].entity("turf.stripe.\(k)", m)
            add(e, order: 1)
            turfTargets.append((e, T.stripeTint[k % T.stripeTint.count], T.stripeRoughness[k % T.stripeRoughness.count],
                                T.stripeSheen[k % T.stripeSheen.count], k == 0 ? "turfWithNormal" : "turfAgainstNormal"))
        }
        if !c.tabletop { upgradeTurf(c, turfTargets) }

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
            let lettering = letters.entity("lettering", m)
            add(lettering, order: 4)
            paintTargets.append((lettering, P.white, false, nil))
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
        if !c.tabletop && V.shells.enabled { buildShells(c, maskPath: path(V.perLeague.paintWhite)) }
        paintTargets.append((white, P.white, true, path(V.perLeague.paintWhite)))
        paintTargets.append((yellow, P.yellow, true, path(V.perLeague.paintYellow)))
        upgradePaint(c)
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
                            canvas K: SceneSpec.Look.FieldCanvas, width: Double, half: Bool, turned: Bool = false,
                            y0 cy0: Double? = nil, y1 cy1: Double? = nil) {
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
        // canvas y runs from the home sideline (z = width/2) toward the away one
        let ya = cy0.map { width / 2 - $0 } ?? K.y0, yb = cy1.map { width / 2 - $0 } ?? K.y1
        let (lo, hi) = (min(ya, yb), max(ya, yb))
        b.quad(p(x0, lo), p(x1, lo), p(x1, hi), p(x0, hi),
               uv: (uv(x0, lo), uv(x1, lo), uv(x1, hi), uv(x0, hi)), normal: SIMD3(0, 1, 0))
    }

    /// Swap the paint and lettering onto the Shader Graph paint material
    /// (tools/blender/field/shadergraph/FieldPaint.usda) when it loads: grass
    /// through the paint and a breakup-driven edge. The texture materials stay
    /// as they are if it does not, and are what the web and Android draw.
    private func upgradePaint(_ c: StadiumContext) {
        let V = c.look.field
        guard let spec = c.spec.shaderGraph?.materials?[V.paintMaterial] else { return }
        let targets = paintTargets
        let turf = c.assets.texture("field.turfAlbedo")
        let P = V.paint
        let halfWidth = c.spec.field.width / 2, halfLength = c.spec.field.length / 2 + c.spec.field.endZone
        Task { @MainActor in
            guard let base = await StadiumShaderGraph.material(spec.prim, file: spec.file),
                  let blades = await self.texture(V.shaderTextures.blades, semantic: .raw),
                  let wear = await self.texture(V.shaderTextures.wear, semantic: .raw),
                  let detail = await self.texture(V.shaderTextures.blades, semantic: .raw, mips: false),
                  let normalPath = V.assets["turfWithNormal"],
                  let normal = await self.texture(normalPath, semantic: .raw),
                  let turf else {
                StadiumLog.log.error("[shadergraph] field paint unavailable; keeping the texture paint")
                return
            }
            for (entity, hex, masked, maskPath) in targets {
                var m = base
                for (k, v) in spec.parameters { StadiumShaderGraph.set(&m, k, v.any) }
                // real field paint, not white: its albedo, roughness and how much
                // grass the border lets through live in visual.field.paint
                StadiumShaderGraph.set(&m, "Color", hex)
                StadiumShaderGraph.set(&m, "Roughness", P.roughness)
                StadiumShaderGraph.set(&m, "BorderColor", P.border)
                StadiumShaderGraph.set(&m, "BorderRoughness", P.borderRoughness)
                StadiumShaderGraph.set(&m, "BorderGrassCut", P.borderGrassCut)
                StadiumShaderGraph.set(&m, "HalfWidth", halfWidth)
                StadiumShaderGraph.set(&m, "HalfLength", halfLength)
                StadiumShaderGraph.set(&m, "UseMask", masked ? 1.0 : 0.0)
                do {
                    try m.setParameter(name: "Blades", value: .textureResource(blades))
                    try m.setParameter(name: "Wear", value: .textureResource(wear))
                    // the near layer: single blades at the eye's feet, faded out
                    // by the graph before the missing mips could shimmer
                    try m.setParameter(name: "Detail", value: .textureResource(detail))
                    // paint coats the blades: their relief stays under it
                    try m.setParameter(name: "Normal", value: .textureResource(normal))
                    try m.setParameter(name: "Turf", value: .textureResource(turf))
                    if let maskPath, let mask = await self.texture(maskPath, semantic: .color) {
                        try m.setParameter(name: "Mask", value: .textureResource(mask))
                    } else if masked {
                        continue
                    }
                } catch {
                    StadiumLog.log.error("[shadergraph] field paint texture: \(error.localizedDescription, privacy: .public)")
                    continue
                }
                entity.model?.materials = [m]
                entity.isEnabled = true
            }
            StadiumLog.log.notice("[shadergraph] field paint on \(targets.count) meshes")
        }
    }

    /// Swap the turf onto the Shader Graph turf (tools/blender/field/shadergraph/
    /// Turf.rkassets/TurfSheen.usda) when it loads: the same tile, normals and
    /// tints, plus the grazing-angle fill and sheen that give it depth from
    /// field level. The PBR turf stays if it does not.
    private func upgradeTurf(_ c: StadiumContext, _ targets: [(ModelEntity, String, Double, Double, String)]) {
        let V = c.look.field
        guard let spec = c.spec.shaderGraph?.materials?[V.turfMaterial],
              let albedoPath = V.assets["turfAlbedo"] else { return }
        Task { @MainActor in
            guard let base = await StadiumShaderGraph.material(spec.prim, file: spec.file),
                  let albedo = await self.texture(albedoPath, semantic: .color),
                  let orm = await self.texture(V.shaderTextures.turfOrm, semantic: .raw) else {
                StadiumLog.log.error("[shadergraph] turf sheen unavailable; keeping the PBR turf")
                return
            }
            for (entity, tint, roughness, sheen, normalKey) in targets {
                guard let normalPath = V.assets[normalKey],
                      let normal = await self.texture(normalPath, semantic: .raw) else { continue }
                var m = base
                for (k, v) in spec.parameters { StadiumShaderGraph.set(&m, k, v.any) }
                StadiumShaderGraph.set(&m, "Tint", tint)
                StadiumShaderGraph.set(&m, "Roughness", roughness)
                StadiumShaderGraph.set(&m, "Sheen", sheen)
                do {
                    try m.setParameter(name: "Albedo", value: .textureResource(albedo))
                    try m.setParameter(name: "Normal", value: .textureResource(normal))
                    try m.setParameter(name: "Orm", value: .textureResource(orm))
                } catch {
                    StadiumLog.log.error("[shadergraph] turf texture: \(error.localizedDescription, privacy: .public)")
                    return
                }
                entity.model?.materials = [m]
            }
            StadiumLog.log.notice("[shadergraph] turf sheen on \(targets.count) meshes")
        }
    }

    /// Shell grass along the home sideline in front of the field-level seat:
    /// flat layers a few millimetres apart on the Shader Graph shell material
    /// (FieldShells.usda), each cutting out the blades taller than it. Drawn
    /// only if the graph loads; from the stands the flat turf is all there is.
    private func buildShells(_ c: StadiumContext, maskPath: String) {
        let V = c.look.field, Sh = V.shells, K = V.canvas, L = V.lift
        guard let spec = c.spec.shaderGraph?.materials?[Sh.material],
              case .number(let base)? = spec.parameters["BaseYards"],
              case .number(let step)? = spec.parameters["StepYards"] else { return }
        let f = c.spec.field, half = f.width / 2
        var mesh = MeshBuilder()
        for layer in Sh.firstLayer...Sh.lastLayer {
            let y = base + Double(layer) * step + L.wear * 0.5
            for (x0, x1, turned) in [(Sh.fromX, K.halfX1, false), (K.halfX1, Sh.toX, true)] where x1 > x0 {
                canvasQuad(&mesh, x0: x0, x1: x1, lift: y, canvas: K, width: f.width, half: true, turned: turned,
                           y0: half - Sh.depth, y1: half)
            }
        }
        let shells = mesh.entity("turf.shells", SimpleMaterial())
        shells.isEnabled = false
        add(shells, order: 1)
        let turf = c.assets.texture("field.turfAlbedo")
        Task { @MainActor in
            guard var m = await StadiumShaderGraph.material(spec.prim, file: spec.file),
                  let atlas = await self.texture(Sh.atlas, semantic: .raw),
                  let mask = await self.texture(maskPath, semantic: .color), let turf else {
                StadiumLog.log.error("[shadergraph] shell grass unavailable; flat turf only")
                return
            }
            for (k, v) in spec.parameters { StadiumShaderGraph.set(&m, k, v.any) }
            // the patch in object units (SceneMath.local: x - 50, z as is)
            StadiumShaderGraph.set(&m, "PatchX0", Sh.fromX - 50)
            StadiumShaderGraph.set(&m, "PatchX1", Sh.toX - 50)
            StadiumShaderGraph.set(&m, "PatchZ0", half - Sh.depth)
            StadiumShaderGraph.set(&m, "PatchZ1", half)
            StadiumShaderGraph.set(&m, "PatchFade", Sh.fade)
            do {
                try m.setParameter(name: "Atlas", value: .textureResource(atlas))
                try m.setParameter(name: "Turf", value: .textureResource(turf))
                try m.setParameter(name: "Mask", value: .textureResource(mask))
            } catch {
                StadiumLog.log.error("[shadergraph] shell textures: \(error.localizedDescription, privacy: .public)")
                return
            }
            shells.model?.materials = [m]
            shells.isEnabled = true
            StadiumLog.log.notice("[shadergraph] shell grass on \(Sh.lastLayer - Sh.firstLayer + 1) layers")
        }
    }

    private func texture(_ rel: String, semantic: TextureResource.Semantic, mips: Bool = true) async -> TextureResource? {
        let key = (semantic == .raw ? rel + "#raw" : rel) + (mips ? "" : "#nomips")
        if let hit = textures[key] { return hit }
        guard let folder = StadiumAssets.folder else { return nil }
        var options = TextureResource.CreateOptions(semantic: semantic)
        options.mipmapsMode = mips ? .allocateAndGenerateAll : .none
        guard let tex = try? await TextureResource(contentsOf: folder.appendingPathComponent(rel), options: options) else {
            StadiumLog.log.error("[stadium] field: \(rel) failed to load")
            return nil
        }
        textures[key] = tex
        return tex
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
                if e.model?.materials.first is ShaderGraphMaterial { continue }
                e.model?.materials = [make(tex)]
                e.isEnabled = true
            }
            self.pending.removeAll { $0.1 == rel }
        }
    }
}
