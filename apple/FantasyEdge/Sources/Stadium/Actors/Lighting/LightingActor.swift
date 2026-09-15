import RealityKit
import simd
import UIKit

/// The light: image-based light from the night probe, the rim light banks,
/// their glow and bloom, beams falling toward the field, haze in the air over
/// the bowl, and the floodlights that actually light the grass and throw the
/// goal posts' shadows. Reads `bowl.rimLights` and `visual.lighting`.
///
/// The banks are Blender models (`tools/blender/lighting/rigs.py`): the ones
/// facing the seats carry every fixture on its pipe with truss, deck and legs,
/// the ones behind the wearer a housing with the baked face. However many
/// banks stand round the rim, every bank of one model is merged into a single
/// mesh per material - housing, steel, lens, face - so the draw count does not
/// grow with the bowl.
///
/// Moments drives two hooks through the blackboard and never calls in:
/// `shared.strobeUntil` makes lenses, glows and beams pulse, and
/// `shared.surge` washes the glow and beams toward the surging side's colour.
///
/// Publishes the positions of the banks facing the seats to `shared.banks`.
@MainActor
final class LightingActor: StadiumActor {
    let name = "lighting"
    let root = Entity()

    private struct Bank {
        let position: SIMD3<Float>
        let facing: SIMD3<Float>          // flat, toward the field
        let front: Bool                   // faces the seats
    }

    private var banks: [Bank] = []
    private var lenses: ModelEntity?      // near model lenses, merged
    private var faces: ModelEntity?       // far model faces, merged
    private var glowLayers: [ModelEntity] = []   // stadium: merged, seat-facing
    private var billboards: [ModelEntity] = []   // tabletop: one per glow
    private var beams: ModelEntity?
    private var haze: ModelEntity?
    private var floods: [(entity: Entity, lumens: Float)] = []
    /// Dust drifting through the beams: the same quads, a tiling texture,
    /// its offset moved along the beam a few times a second. UnlitMaterial's
    /// texture transform (visionOS 2) rather than a Shader Graph, which a
    /// headless build cannot author; the ports scroll a UV offset the same way.
    private var dust: ModelEntity?
    /// The beam as a Shader Graph (`visual.lighting.beams.shader`): soft
    /// profile, dust drifting on the shader clock, and a view-angle falloff so
    /// a crossed quad seen edge-on fades out. When it loads it replaces both
    /// the beam and the UV-scroll dust above, which stay as the fallback - and
    /// as what the web and Android ports draw until they port the graph.
    private var beamGraph: ShaderGraphMaterial?
    private var buildToken = 0
    private var dustOffset: Float = 0
    private var dustTick: Double = 0
    private var glowSeat: SIMD3<Float>?
    private var applied = (gain: -1.0, wash: -1.0, away: false)

    init() { root.name = "actor.lighting" }

    // MARK: build

    func build(_ c: StadiumContext) {
        clear()
        lenses = nil; faces = nil; beams = nil; dust = nil; haze = nil; beamGraph = nil
        buildToken += 1
        floods.removeAll()
        glowLayers.removeAll(); billboards.removeAll()
        glowSeat = nil
        applied = (-1, -1, false)
        let s = c.spec, V = c.look.lighting, lights = s.bowl.rimLights
        let tabletop = c.tabletop

        if let env = c.assets.environment, !tabletop || V.probeOnTabletop {
            root.components.set(ImageBasedLightComponent(source: .single(env),
                                                         intensityExponent: Float(V.probeIntensityExponent)))
        }

        guard let top = c.tiers.last else { return }
        let rimOffset = top.outer + (lights.beyondOuter ?? 1)
        let height = top.rise[1] + V.rim.heightAbove.value(tabletop: tabletop)
        banks = []
        for k in 0..<lights.count {
            let t = Double(k) * .pi / Double(max(1, lights.count / 2)) + V.rim.phase
            let p = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset, angle: t)
            let front = p.z <= V.rim.farSideMaxZ
            if lights.side == "far" && !front { continue }
            let pos = SIMD3(Float(p.x), Float(height), Float(p.z))
            let flat = simd_normalize(SIMD3(-pos.x, 0, -pos.z))
            banks.append(Bank(position: pos, facing: flat, front: front))
        }
        c.shared.banks = banks.filter(\.front).map(\.position)

        buildRigs(c)
        buildGlows(c)
        buildBeams(c)
        if !tabletop { buildHaze(c); buildFill(c) }
        buildFloods(c)
    }

    /// Merge every bank of one model into one mesh per material.
    private func buildRigs(_ c: StadiumContext) {
        let V = c.look.lighting, B = V.bank
        let lamp = V.rim.lampYards.value(tabletop: c.tabletop)
        // Authored in metres at real size; the stage works in yards.
        let scale = Float(lamp[0] / V.rim.modelWidthYards / 0.9144)
        var parts: [String: MeshBuilder] = [:]
        var anyModel = false
        for (key, front) in [("lighting.bankNear", true), ("lighting.bankFar", false)] {
            guard let template = c.assets.model(key) else { continue }
            anyModel = true
            let pieces = Self.pieces(of: template)
            for bank in banks where bank.front == front {
                let yaw = atan2(bank.facing.x, bank.facing.z)
                let placed = Transform(scale: SIMD3(repeating: scale),
                                       rotation: simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0)),
                                       translation: bank.position).matrix
                for piece in pieces {
                    parts[piece.role, default: MeshBuilder()].append(piece, placed)
                }
            }
        }
        if !anyModel {
            // Models missing from the bundle: the old flat faces, so the rim is never dark.
            var flat = MeshBuilder()
            for bank in banks {
                let side = simd_normalize(simd_cross(SIMD3<Float>(0, 1, 0), bank.facing))
                let w = Float(lamp[0] / 2), h = Float(lamp[1] / 2)
                let at = bank.position + bank.facing * 0.4
                let up = SIMD3<Float>(0, h, 0)
                flat.quad(at - side * w - up, at + side * w - up, at + side * w + up, at - side * w + up, normal: bank.facing)
            }
            parts["face"] = flat
        }
        let materials: [String: any Material] = [
            "housing": StadiumLook.solid(B.housing, roughness: B.housingRoughness, metallic: B.housingMetallic),
            "steel": StadiumLook.solid(B.steel, roughness: B.steelRoughness, metallic: B.steelMetallic, cull: false),
            "lens": lensMaterial(c, gain: 1),
            "face": faceMaterial(c, gain: 1),
        ]
        for role in ["housing", "steel", "lens", "face"] {
            guard let mesh = parts[role], !mesh.isEmpty, let material = materials[role] else { continue }
            let e = mesh.entity("rim.\(role)", material)
            root.addChild(e)
            if role == "lens" { lenses = e }
            if role == "face" { faces = e }
        }
    }

    /// A model's meshes flattened to triangles in the template's own space,
    /// each tagged with the role its Blender object name ends in.
    fileprivate struct Piece {
        let role: String
        let positions: [SIMD3<Float>]
        let normals: [SIMD3<Float>]
        let uvs: [SIMD2<Float>]
        let indices: [UInt32]
    }

    private static func pieces(of template: Entity) -> [Piece] {
        var out: [Piece] = []
        func visit(_ e: Entity) {
            if let model = e.components[ModelComponent.self] {
                let role = ["housing", "steel", "lens", "face"].first { name in
                    var node: Entity? = e
                    while let n = node {
                        if n.name.lowercased().contains("_\(name)") { return true }
                        node = n.parent
                    }
                    return false
                } ?? "steel"
                let toTemplate = e.transformMatrix(relativeTo: template)
                let contents = model.mesh.contents
                for instance in contents.instances {
                    guard let m = contents.models[instance.model] else { continue }
                    let xf = toTemplate * instance.transform
                    let nxf = simd_float3x3(SIMD3(xf.columns.0.x, xf.columns.0.y, xf.columns.0.z),
                                            SIMD3(xf.columns.1.x, xf.columns.1.y, xf.columns.1.z),
                                            SIMD3(xf.columns.2.x, xf.columns.2.y, xf.columns.2.z)).inverse.transpose
                    for part in m.parts {
                        let pos = part.positions.elements.map { p -> SIMD3<Float> in
                            let v = xf * SIMD4(p, 1)
                            return SIMD3(v.x, v.y, v.z)
                        }
                        let nor = (part.normals?.elements ?? Array(repeating: SIMD3(0, 1, 0), count: pos.count))
                            .map { simd_normalize(nxf * $0) }
                        let uv = part.textureCoordinates?.elements ?? Array(repeating: SIMD2(0, 0), count: pos.count)
                        guard let idx = part.triangleIndices?.elements else { continue }
                        out.append(Piece(role: role, positions: pos, normals: nor, uvs: uv, indices: idx))
                    }
                }
            }
            for child in e.children { visit(child) }
        }
        visit(template)
        return out
    }

    private func lensMaterial(_ c: StadiumContext, gain: Double) -> UnlitMaterial {
        let B = c.look.lighting.bank
        return StadiumLook.glow(B.lensColor, opacity: B.lensGain * gain, texture: c.assets.texture("lighting.lens"))
    }

    private func faceMaterial(_ c: StadiumContext, gain: Double) -> UnlitMaterial {
        let B = c.look.lighting.bank
        return StadiumLook.glow(B.lensColor, opacity: B.faceGain * gain, texture: c.assets.texture("lighting.face"))
    }

    // MARK: glow

    /// A seat-facing card per bank: `size` wide and tall, centred `forward`
    /// yards toward the field and `drop` yards below the bank.
    private struct GlowLayer {
        let key: String; let size: SIMD2<Float>; let opacity: Double
        var forward: Float = 0; var drop: Float = 0
        init(key: String, size: Float, opacity: Double) {
            self.key = key; self.size = SIMD2(size, size); self.opacity = opacity
        }
        init(key: String, size: SIMD2<Float>, opacity: Double, forward: Float, drop: Float) {
            self.key = key; self.size = size; self.opacity = opacity; self.forward = forward; self.drop = drop
        }
    }

    private func layers(_ c: StadiumContext) -> [GlowLayer] {
        let G = c.look.lighting.glow, t = c.tabletop
        // On the table the lens is the core and billboards cost a draw each,
        // so only the halo is drawn there; the stadium gets bloom, halo, core.
        if t {
            return [GlowLayer(key: "lighting.glowHalo", size: Float(G.haloYards.value(tabletop: t)), opacity: G.haloOpacity)]
        }
        // The spill: the banks' light lying on the seats just below and in
        // front of them. Without it a bank glows in the air over stands that
        // look unlit, which is the tell of a stadium lit by stickers.
        let spill = GlowLayer(key: "lighting.spill", size: SIMD2(Float(G.spillYards[0]), Float(G.spillYards[1])),
                              opacity: G.spillOpacity, forward: Float(G.spillForwardYards), drop: Float(G.spillDropYards))
        return [spill,
                GlowLayer(key: "lighting.bloom", size: Float(G.bloomYards.value(tabletop: t)), opacity: G.bloomOpacity),
                GlowLayer(key: "lighting.glowHalo", size: Float(G.haloYards.value(tabletop: t)), opacity: G.haloOpacity),
                GlowLayer(key: "lighting.glowCore", size: Float(G.coreYards.value(tabletop: t)), opacity: G.coreOpacity)]
    }

    private func glowCentre(_ bank: Bank, _ c: StadiumContext) -> SIMD3<Float> {
        bank.position + bank.facing * Float(c.look.lighting.glow.liftYards)
    }

    private func buildGlows(_ c: StadiumContext) {
        let G = c.look.lighting.glow
        if c.tabletop {
            // No seat on the table: billboards, and only the banks you face.
            for layer in layers(c) {
                let material = StadiumLook.glow(G.color, opacity: layer.opacity, texture: c.assets.texture(layer.key))
                for bank in banks where bank.front {
                    let g = ModelEntity(mesh: .generatePlane(width: layer.size.x, height: layer.size.y), materials: [material])
                    g.name = "rim.glow"
                    g.position = glowCentre(bank, c)
                    g.components.set(BillboardComponent())
                    root.addChild(g)
                    billboards.append(g)
                }
            }
            return
        }
        for layer in layers(c) {
            let e = ModelEntity()
            e.name = "rim.\(layer.key.split(separator: ".").last ?? "glow")"
            root.addChild(e)
            glowLayers.append(e)
        }
        relayGlows(c, seat: c.shared.seat ?? defaultSeat(c))
    }

    /// One mesh per glow layer, every quad turned to the seat. A seat change
    /// relays them; nothing billboards per frame.
    private func relayGlows(_ c: StadiumContext, seat: SIMD3<Float>) {
        glowSeat = seat
        for (layer, entity) in zip(layers(c), glowLayers) {
            var mesh = MeshBuilder()
            for bank in banks {
                let centre = glowCentre(bank, c) + bank.facing * layer.forward - SIMD3(0, layer.drop, 0)
                let toSeat = simd_normalize(seat - centre)
                var right = simd_cross(SIMD3<Float>(0, 1, 0), toSeat)
                right = simd_length(right) < 1e-4 ? SIMD3(1, 0, 0) : simd_normalize(right)
                let up = simd_cross(toSeat, right)
                let r = right * layer.size.x / 2, u = up * layer.size.y / 2
                mesh.quad(centre - r - u, centre + r - u, centre + r + u, centre - r + u, normal: toSeat)
            }
            let material = StadiumLook.glow(c.look.lighting.glow.color, opacity: layer.opacity,
                                            texture: c.assets.texture(layer.key))
            if let resource = mesh.resource(entity.name) {
                entity.model = ModelComponent(mesh: resource, materials: [material])
            }
        }
    }

    private func defaultSeat(_ c: StadiumContext) -> SIMD3<Float> {
        let seat = c.spec.presentation.stadium.seat(nil)
        return SceneMath.local(x: seat.x, y: seat.y + 1.3, z: seat.z)
    }

    // MARK: beams

    private func buildBeams(_ c: StadiumContext) {
        let Bm = c.look.lighting.beams, t = c.tabletop
        let seat = c.shared.seat ?? defaultSeat(c)
        let length = Float(Bm.lengthYards.value(tabletop: t))
        let widthScale: Float = t ? 0.5 : 1
        struct Beam { let from: SIMD3<Float>; let to: SIMD3<Float>; let w0: Float; let w1: Float; let cover: Double }
        var all: [Beam] = []
        for bank in banks where bank.front {
            let side = simd_normalize(simd_cross(SIMD3<Float>(0, 1, 0), bank.facing))
            for i in 0..<max(0, Bm.perBank) {
                let offset = Float(i) - Float(Bm.perBank - 1) / 2
                var aim = SIMD3<Float>(0, 0, 0) + side * offset * Float(Bm.fanYards)
                aim.y = 0
                let dir = simd_normalize(aim - bank.position)
                var end = bank.position + dir * length
                // Stop short of the grass: the last yards of a shaft sit at
                // the height of the far lower bowl, and from the upper deck
                // they read as fog over those seats, not as light on the turf.
                let floor = Float(Bm.endHeightYards.value(tabletop: t))
                if end.y < floor {
                    let k = (bank.position.y - floor) / max(1e-3, bank.position.y - end.y)
                    end = bank.position + (end - bank.position) * k
                }
                // A shaft only exists over the field. From the lamp to the
                // bowl's inner edge the beam lies across the stands, and seen
                // against them additive light turns club colour to grey fog
                // (integration-1). So the quad starts where the ray crosses
                // `startInsideOffsetYards` of the bowl, fading in there, and
                // the lens and its halo carry the light over the seats.
                let tStart = Self.entry(from: bank.position, to: end, shape: c.spec.bowl.shape,
                                        offset: Bm.startInsideOffsetYards)
                guard tStart < 0.9 else { continue }
                let from = bank.position + (end - bank.position) * tStart
                let wFull0 = Float(Bm.startWidthYards) * widthScale, w1 = Float(Bm.endWidthYards) * widthScale
                let w0 = wFull0 + (w1 - wFull0) * tStart
                let mid = (from + end) / 2
                let area = Double(simd_length(end - from) * (w0 + w1) / 2)
                let d2 = Double(max(1, simd_length_squared(mid - seat)))
                // Two crossed quads, about 0.7 of their area facing the eye;
                // a headset's field of view is about 2.4 steradians.
                let cover = 2 * 0.7 * area / d2 / 2.4
                all.append(Beam(from: from, to: end, w0: w0, w1: w1, cover: cover))
            }
        }
        // Keep the nearest-to-the-field-centre beams; drop the rest past the cap.
        var kept: [Beam] = []
        var screens = 0.0
        for b in all.sorted(by: { simd_length($0.to) < simd_length($1.to) }) {
            if screens + b.cover > Bm.overdrawCapScreens && !kept.isEmpty { continue }
            kept.append(b)
            screens += b.cover
        }
        var mesh = MeshBuilder(), dustMesh = MeshBuilder()
        let dustTile = Float(max(1, Bm.dustTileYards))
        for b in kept {
            let axis = simd_normalize(b.to - b.from)
            var a = simd_cross(axis, SIMD3<Float>(0, 1, 0))
            a = simd_length(a) < 1e-4 ? SIMD3(1, 0, 0) : simd_normalize(a)
            let bb = simd_normalize(simd_cross(axis, a))
            for across in [a, bb] {
                let p0 = b.from - across * b.w0 / 2, p1 = b.from + across * b.w0 / 2
                let p2 = b.to + across * b.w1 / 2, p3 = b.to - across * b.w1 / 2
                // v = 1 at the lamp: the beam texture's top row is the throat.
                mesh.quad(p0, p1, p2, p3, uv: (SIMD2(0, 1), SIMD2(1, 1), SIMD2(1, 0), SIMD2(0, 0)))
                let v = simd_distance(b.from, b.to) / dustTile
                dustMesh.quad(p0, p1, p2, p3, uv: (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, v), SIMD2(0, v)))
            }
        }
        StadiumLog.log.notice("[stadium] lighting beams \(kept.count)/\(all.count), overdraw ≈ \(String(format: "%.2f", screens)) screens (cap \(Bm.overdrawCapScreens))")
        guard !mesh.isEmpty else { return }
        let e = mesh.entity("rim.beams", beamMaterial(c, gain: 1, tint: nil))
        root.addChild(e)
        beams = e
        if c.assets.texture("lighting.beamDust") != nil, !dustMesh.isEmpty {
            let d = dustMesh.entity("rim.beamDust", dustMaterial(c, gain: 1, tint: nil))
            root.addChild(d)
            dust = d
        }
        loadBeamGraph(c)
    }

    private func loadBeamGraph(_ c: StadiumContext) {
        let G = c.look.lighting.beams.shader
        guard !G.file.isEmpty else { return }
        let token = buildToken
        Task { @MainActor [weak self] in
            guard let base = await StadiumShaderGraph.material(G.prim, file: G.file) else {
                StadiumLog.log.notice("[shadergraph] lighting beams: graph unavailable, drawing the UV-scroll fallback")
                return
            }
            guard let self, token == self.buildToken, let beams = self.beams else { return }
            var m = base
            m.faceCulling = .none
            m.writesDepth = false
            self.beamGraph = m
            self.applyBeamGraph(c, gain: 1, tint: nil)
            self.dust?.removeFromParent()
            self.dust = nil
            StadiumLog.log.notice("[shadergraph] lighting beams: Shader Graph in use on \(beams.name, privacy: .public)")
        }
    }

    /// Set the graph's parameters from tokens, with a strobe gain and wash tint.
    private func applyBeamGraph(_ c: StadiumContext, gain: Double, tint: String?) {
        guard var m = beamGraph, let beams else { return }
        let G = c.look.lighting.beams.shader
        StadiumShaderGraph.set(&m, "Color", tint ?? G.color)
        StadiumShaderGraph.set(&m, "Opacity", G.opacity.value(tabletop: c.tabletop) * gain)
        StadiumShaderGraph.set(&m, "DustRepeat", G.dustRepeat)
        StadiumShaderGraph.set(&m, "DustSpeed", c.reduceMotion ? 0.0 : G.dustSpeed)
        StadiumShaderGraph.set(&m, "DustFloor", G.dustFloor)
        StadiumShaderGraph.set(&m, "DustAmount", G.dustAmount)
        StadiumShaderGraph.set(&m, "ViewPower", G.viewPower)
        StadiumShaderGraph.set(&m, "Additive", G.additive)
        beams.model?.materials = [m]
    }

    private func dustMaterial(_ c: StadiumContext, gain: Double, tint: String?) -> UnlitMaterial {
        let Bm = c.look.lighting.beams
        var m = StadiumLook.glow(tint ?? Bm.color, opacity: Bm.dustOpacity.value(tabletop: c.tabletop) * gain,
                                 texture: c.assets.texture("lighting.beamDust"), tile: true)
        m.textureCoordinateTransform.offset = SIMD2(0, dustOffset)
        return m
    }

    /// The fraction along `from`→`to` where the ray's ground position first
    /// comes inside the bowl's superellipse at `offset` yards (0 if it starts
    /// inside, 1 if it never gets there). Bisection on the shape's own test.
    static func entry(from: SIMD3<Float>, to: SIMD3<Float>, shape: SceneSpec.Shape, offset: Double) -> Float {
        func inside(_ t: Float) -> Bool {
            let p = from + (to - from) * t
            let a = shape.halfLength + offset, b = shape.halfWidth + offset
            return pow(abs(Double(p.x)) / a, shape.exponent) + pow(abs(Double(p.z)) / b, shape.exponent) <= 1
        }
        if inside(0) { return 0 }
        if !inside(1) { return 1 }
        var lo: Float = 0, hi: Float = 1
        for _ in 0..<20 {
            let m = (lo + hi) / 2
            if inside(m) { hi = m } else { lo = m }
        }
        return hi
    }

    private func beamMaterial(_ c: StadiumContext, gain: Double, tint: String?) -> UnlitMaterial {
        let Bm = c.look.lighting.beams
        let colour = tint ?? Bm.color
        return StadiumLook.glow(colour, opacity: Bm.opacity.value(tabletop: c.tabletop) * gain,
                                texture: c.assets.texture("lighting.beam"))
    }

    // MARK: haze

    private func buildHaze(_ c: StadiumContext) {
        let H = c.look.lighting.haze, s = c.spec
        var mesh = MeshBuilder()
        let segments = 96
        let repeats = Float(max(1, H.repeatsAround))
        for (li, h) in H.heights.enumerated() {
            let lift = Float(h)
            let phase = Double(li) * 0.37
            for k in 0..<segments {
                let t0 = (Double(k) + phase) / Double(segments) * 2 * .pi
                let t1 = (Double(k + 1) + phase) / Double(segments) * 2 * .pi
                let i0 = SceneMath.bowlPoint(s.bowl.shape, offset: H.inner, angle: t0)
                let i1 = SceneMath.bowlPoint(s.bowl.shape, offset: H.inner, angle: t1)
                let o0 = SceneMath.bowlPoint(s.bowl.shape, offset: H.outer, angle: t0)
                let o1 = SceneMath.bowlPoint(s.bowl.shape, offset: H.outer, angle: t1)
                let pts = [i0, i1, o1, o0].map { SIMD3(Float($0.x), lift, Float($0.z)) }
                // u round the bowl, v from the inner edge (0) to the outer (1):
                // the band texture fades at both, so the sheet has no rim.
                let u0 = Float(k) / Float(segments) * repeats + Float(li) * 0.5
                let u1 = Float(k + 1) / Float(segments) * repeats + Float(li) * 0.5
                mesh.quad(pts[0], pts[1], pts[2], pts[3],
                          uv: (SIMD2(u0, 0), SIMD2(u1, 0), SIMD2(u1, 1), SIMD2(u0, 1)), normal: SIMD3(0, 1, 0))
            }
        }
        let e = mesh.entity("rim.haze", hazeMaterial(c, gain: 1))
        root.addChild(e)
        haze = e
    }

    private func hazeMaterial(_ c: StadiumContext, gain: Double) -> UnlitMaterial {
        let H = c.look.lighting.haze
        return StadiumLook.glow(H.color, opacity: H.opacity * gain, texture: c.assets.texture("lighting.haze"), tile: true)
    }

    // MARK: concourse fill

    /// The back of the upper deck's guard wall faces the seats, away from
    /// every flood, and the night probe gives a vertical face almost nothing:
    /// it rendered near-black under Bowl's LED strip. Real stadiums fill it from the
    /// concourse and the vomitories behind. That light is drawn as a band
    /// just in front of the wall face and a glow in each tunnel mouth, unlit
    /// and additive - one draw, no light, no shadow. The band's geometry
    /// mirrors Bowl's guard wall (`visual.lighting.fill`, checked against
    /// tools/blender/bowl/structure.py by a test).
    private func buildFill(_ c: StadiumContext) {
        let F = c.look.lighting.fill, s = c.spec
        var mesh = MeshBuilder()
        let segments = 128
        let off = F.wallOffsetYards + F.standOffYards       // on the seats' side of the face
        let y0 = Float(F.wallRise[0]), y1 = Float(F.wallRise[1])
        let repeats = Float(max(1, F.repeatsAround))
        for k in 0..<segments {
            let t0 = Double(k) / Double(segments) * 2 * .pi, t1 = Double(k + 1) / Double(segments) * 2 * .pi
            let p0 = SceneMath.bowlPoint(s.bowl.shape, offset: off, angle: t0)
            let p1 = SceneMath.bowlPoint(s.bowl.shape, offset: off, angle: t1)
            let u0 = Float(k) / Float(segments) * repeats, u1 = Float(k + 1) / Float(segments) * repeats
            mesh.quad(SIMD3(Float(p0.x), y0, Float(p0.z)), SIMD3(Float(p1.x), y0, Float(p1.z)),
                      SIMD3(Float(p1.x), y1, Float(p1.z)), SIMD3(Float(p0.x), y1, Float(p0.z)),
                      uv: (SIMD2(u0, 1), SIMD2(u1, 1), SIMD2(u1, 0), SIMD2(u0, 0)))
        }
        for tunnel in s.bowl.tunnels ?? [] {
            // A tunnel mouth at x, under the end-zone stands, facing the field.
            let x = Float(tunnel.x - 50)
            let towardField: Float = x < 0 ? 1 : -1
            let w = Float(tunnel.width * F.tunnelScale) / 2, h = Float(tunnel.height * F.tunnelScale)
            let face = x + towardField * Float(F.standOffYards)
            mesh.quad(SIMD3(face, 0, -w), SIMD3(face, 0, w), SIMD3(face, h, w), SIMD3(face, h, -w),
                      uv: (SIMD2(0, 1), SIMD2(repeats / 8, 1), SIMD2(repeats / 8, 0), SIMD2(0, 0)))
        }
        let material = StadiumLook.glow(F.color, opacity: F.opacity, texture: c.assets.texture("lighting.fill"), tile: true)
        root.addChild(mesh.entity("rim.concourseFill", material))
    }

    // MARK: floods

    private func buildFloods(_ c: StadiumContext) {
        let flood = c.look.lighting.flood, t = c.tabletop
        let facing = banks.filter(\.front)
        guard !facing.isEmpty else { return }
        let step = max(1, facing.count / max(1, flood.count))
        let chosen = stride(from: 0, to: facing.count, by: step).prefix(flood.count).map { facing[$0] }
        for (i, bank) in chosen.enumerated() {
            let e = Entity()
            e.name = "flood.\(i)"
            e.position = bank.position
            e.look(at: SIMD3(0, 0, 0), from: bank.position, relativeTo: nil)
            var spot = SpotLightComponent(color: StadiumLook.color(flood.color),
                                          intensity: Float(t ? flood.tabletopLumens : flood.lumens),
                                          innerAngleInDegrees: Float(flood.innerDegrees),
                                          outerAngleInDegrees: Float(flood.outerDegrees),
                                          attenuationRadius: Float(t ? flood.tabletopReach : flood.reach))
            spot.attenuationFalloffExponent = 1
            e.components.set(spot)
            if i < flood.shadows { e.components.set(SpotLightComponent.Shadow()) }
            root.addChild(e)
            floods.append((e, spot.intensity))
        }
    }

    // MARK: frame

    /// Strobe and wash, and relaying the glow when the wearer changes seat.
    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        var dustMoved = false
        if dust != nil, !c.reduceMotion, frame.time - dustTick >= 0.1 {
            dustOffset = (dustOffset - Float(c.look.lighting.beams.dustScrollPerSecond * (frame.time - dustTick)))
                .truncatingRemainder(dividingBy: 1)
            dustTick = frame.time
            dustMoved = true
        }
        if !c.tabletop, let seat = c.shared.seat, glowSeat.map({ simd_distance($0, seat) > 0.5 }) ?? true {
            relayGlows(c, seat: seat)
            applied = (-1, -1, false)
        }
        let S = c.look.lighting.strobe, M = c.look.moments
        var pulse = 0.0
        if !c.reduceMotion && frame.time < c.shared.strobeUntil {
            pulse = 0.5 + 0.5 * sin(frame.time * 2 * .pi * M.strobeHz)
        } else if c.reduceMotion && frame.time < c.shared.strobeUntil {
            pulse = 0.5                                   // held, not flashing
        }
        var wash = 0.0, away = false
        if let surge = c.shared.surge, frame.time < surge.until {
            wash = 1
            away = surge.away
        }
        let gain = (pulse * 20).rounded() / 20
        let changed = gain != applied.gain || wash != applied.wash || away != applied.away
        if dustMoved && !changed {
            let tint = applied.wash > 0 ? Self.mix(c.look.lighting.beams.color, applied.away ? c.spec.bowl.crowd.away : c.spec.bowl.crowd.home,
                                                   c.look.lighting.wash.beamTint) : nil
            dust?.model?.materials = [dustMaterial(c, gain: Self.strobeGain(c.look.lighting.strobe.beamGain, max: c.look.lighting.strobe.beamGainMax, pulse: applied.gain), tint: tint)]
        }
        guard changed else { return }
        applied = (gain, wash, away)

        let W = c.look.lighting.wash, G = c.look.lighting.glow
        let chip = away ? c.spec.bowl.crowd.away : c.spec.bowl.crowd.home
        lenses?.model?.materials = [lensMaterial(c, gain: 1 + (S.lensGain - 1) * gain)]
        faces?.model?.materials = [faceMaterial(c, gain: 1 + (S.lensGain - 1) * gain)]
        let glowColour = wash > 0 ? Self.mix(G.color, chip, W.glowTint) : G.color
        for (layer, entity) in zip(layers(c), glowLayers) {
            // The spill lies over seats; it pulses no more than the haze may.
            let layerGain = layer.key == "lighting.spill"
                ? Self.strobeGain(S.glowGain, max: S.hazeGainMax, pulse: gain)
                : 1 + (S.glowGain - 1) * gain
            entity.model?.materials = [StadiumLook.glow(glowColour, opacity: layer.opacity * layerGain,
                                                        texture: c.assets.texture(layer.key))]
        }
        if c.tabletop {
            let scale = Float(1 + (S.glowGain - 1) * gain * 0.5)
            for g in billboards { g.scale = SIMD3(repeating: scale) }
        }
        let beamColour = wash > 0 ? Self.mix(c.look.lighting.beams.color, chip, W.beamTint) : nil
        // Beams and haze are volume the eye sees against the stands: pulsed
        // hard they turn both decks to grey fog (integration-2 td-moment).
        // They are capped; the lenses, the glows and a brief wash of extra
        // flood on the field carry the strobe instead.
        let beamGain = Self.strobeGain(S.beamGain, max: S.beamGainMax, pulse: gain)
        if beamGraph != nil {
            applyBeamGraph(c, gain: beamGain, tint: beamColour)
        } else {
            beams?.model?.materials = [beamMaterial(c, gain: beamGain, tint: beamColour)]
        }
        dust?.model?.materials = [dustMaterial(c, gain: beamGain, tint: beamColour)]
        haze?.model?.materials = [hazeMaterial(c, gain: Self.strobeGain(S.beamGain, max: S.hazeGainMax, pulse: gain))]
        let fieldWash = Float(1 + (S.fieldWashGain - 1) * gain)
        for f in floods {
            if var spot = f.entity.components[SpotLightComponent.self] {
                spot.intensity = f.lumens * fieldWash
                f.entity.components.set(spot)
            }
        }
    }

    /// A strobe multiplier: `1 + (gain - 1) * pulse`, never above `max`.
    static func strobeGain(_ gain: Double, max cap: Double, pulse: Double) -> Double {
        min(cap, 1 + (gain - 1) * pulse)
    }

    private static func mix(_ a: String, _ b: String, _ t: Double) -> String {
        let x = SceneMath.rgba(a), y = SceneMath.rgba(b)
        let f = Float(max(0, min(1, t)))
        let m = x + (y - x) * f
        let hex = { (v: Float) in String(format: "%02X", Int((max(0, min(1, v)) * 255).rounded())) }
        return "#" + hex(m.x) + hex(m.y) + hex(m.z)
    }
}

private extension MeshBuilder {
    /// A model's piece, placed by a bank's transform.
    mutating func append(_ piece: LightingActor.Piece, _ m: simd_float4x4) {
        let n3 = simd_float3x3(SIMD3(m.columns.0.x, m.columns.0.y, m.columns.0.z),
                               SIMD3(m.columns.1.x, m.columns.1.y, m.columns.1.z),
                               SIMD3(m.columns.2.x, m.columns.2.y, m.columns.2.z)).inverse.transpose
        let base = UInt32(positions.count)
        positions += piece.positions.map { p in let v = m * SIMD4(p, 1); return SIMD3(v.x, v.y, v.z) }
        normals += piece.normals.map { simd_normalize(n3 * $0) }
        uvs += piece.uvs
        indices += piece.indices.map { $0 + base }
    }
}
