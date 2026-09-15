import RealityKit
import simd

/// The sideline: goal posts, pylons, benches, the team-area dressing, the
/// end-line nets and camera towers, the chain crew, and the LED boards along
/// the front wall. Reads `field.props`, `visual.sideline` and the models
/// exported by tools/blender/field/build.py.
///
/// A loaded model is never drawn as itself. Its meshes are named
/// `<prop>__<material>`, and every placed copy is baked into one merged mesh
/// per palette entry (team-tinted entries once per club), so the whole
/// sideline costs one draw part per material however many props stand on it.
/// The chain crew moves when the line to gain does, so it is a second, small
/// merge rebuilt then.
///
/// Draw parts: static palette ~10, chain crew ~4, boards 1.
@MainActor
final class SidelineActor: StadiumActor {
    let name = "sideline"
    let root = Entity()

    private let fixed = Entity()
    /// Each end's field-goal net, on its own pivot at the top bar so a kick
    /// through can swing it (`shared.netSway`).
    private var nets: [(endX: Double, entity: Entity)] = []
    private var sway: (until: Double, started: Double)?
    private let crew = Entity()
    private var crewKey = ""
    /// Model geometry in model metres, by model id then material key.
    private var geometry: [String: [String: MeshBuilder]] = [:]
    /// Each model's footprint on the ground (x, z half extents, metres),
    /// measured from what stands below `shadow.footprintBelowMetres`.
    private var footprints: [String: SIMD2<Float>] = [:]
    /// Faked floodlight shadows under every static prop, one merged decal.
    private var shadows = MeshBuilder()

    init() {
        root.name = "actor.sideline"
        fixed.name = "sideline.fixed"
        crew.name = "sideline.crew"
    }

    func build(_ c: StadiumContext) {
        clear()
        fixed.children.removeAll()
        crew.children.removeAll()
        nets = []
        sway = nil
        crewKey = ""
        root.addChild(fixed)
        root.addChild(crew)
        buildProps(c)
        buildBoards(c)
        apply(c, previous: nil)
    }

    func apply(_ c: StadiumContext, previous: SceneSpec?) {
        buildCrew(c)
    }

    /// The net swings back and forth about its top bar, decaying, when Moments
    /// asks. Under reduce motion it holds still.
    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard let ask = c.shared.netSway, !nets.isEmpty else { return }
        let S = c.look.sideline.sway
        let now = c.shared.time
        if sway?.until != ask.until {
            sway = (ask.until, now)
            StadiumLog.log.notice("[stadium] sideline: net sway at x \(ask.endX, privacy: .public) for \(ask.until - now, privacy: .public)s\(c.reduceMotion ? ", held still (reduce motion)" : "", privacy: .public)")
        }
        guard let started = sway?.started else { return }
        let net = nets.min { abs($0.endX - ask.endX) < abs($1.endX - ask.endX) }!.entity
        guard now < ask.until, !c.reduceMotion else {
            net.orientation = simd_quatf(angle: 0, axis: SIMD3(0, 0, 1))
            if now >= ask.until { c.shared.netSway = nil }
            return
        }
        let t = now - started
        let angle = S.maxDegrees * .pi / 180 * min(1, max(0, ask.strength))
            * exp(-t / S.decaySeconds) * sin(2 * .pi * S.frequency * t)
        // The net faces the field along x. It billows about z - its bottom
        // toward and away from the end line - and sways a share of that about
        // x, within its own plane, which is the motion that reads from behind
        // the goal, where the billow is straight toward the eye.
        let billow = simd_quatf(angle: Float(angle), axis: SIMD3(0, 0, 1))
        let lateral = simd_quatf(angle: Float(angle * S.lateralShare * cos(.pi * S.frequency * t)), axis: SIMD3(1, 0, 0))
        net.orientation = billow * lateral
    }

    // MARK: props

    private struct Bin {
        var mesh = MeshBuilder()
        let material: String
        let side: String?
    }

    private func buildProps(_ c: StadiumContext) {
        let s = c.spec, V = c.look.sideline
        guard let p = s.field.props else { return }
        let f = s.field, half = f.width / 2
        let college = s.league == "college-football"
        var bins: [String: Bin] = [:]

        shadows = MeshBuilder()
        func place(_ model: String, x: Double, z: Double, yaw: Float, side: String) {
            add(model, c, at: SceneMath.local(x: x, y: 0, z: z), yaw: yaw, side: side, into: &bins)
            shadow(model, c, x: x, z: z)
        }

        // Toward the field is model -Z. On the home sideline (z > 0) the field
        // lies toward -z, so no turn; on the away sideline a half turn.
        let sides: [(String, Double, Float)] = [("home", 1, 0), ("away", -1, .pi)]

        // Goal posts on the end lines, pylons where the book puts them.
        let goal = college ? "goalpost_college" : "goalpost_nfl"
        place(goal, x: -f.endZone, z: 0, yaw: -.pi / 2, side: "home")
        place(goal, x: f.length + f.endZone, z: 0, yaw: .pi / 2, side: "away")
        let pylon = college ? "pylon_college" : "pylon_nfl"
        for spot in p.pylon.at ?? [] where spot.count == 2 {
            place(pylon, x: spot[0], z: spot[1], yaw: 0, side: spot[0] < 50 ? "home" : "away")
        }

        // Each club's team area: benches down its middle, the dressing around them.
        let centre = (p.benches.fromX + p.benches.toX) / 2
        for (side, sign, yaw) in sides {
            let n = V.benches.count
            // Benches pair off either side of an open gap at the team area's
            // middle: the tunnel's mouth, and the field-level seat's sightline.
            for k in 0..<n {
                let rank = Double(k / 2)
                let x = centre + (k % 2 == 0 ? -1 : 1) * (V.benches.centreGap / 2 + (rank + 0.5) * V.benches.spacing)
                place("bench", x: x, z: sign * (half + p.benches.offset), yaw: yaw, side: side)
            }
            for d in V.dressing {
                // Mirror `along` on the away side, so the half turn holds.
                place(d.model, x: centre + sign * d.along, z: sign * (half + d.offset), yaw: yaw, side: side)
            }
        }
        // Behind each end line: nets and camera towers, facing the field.
        for (side, xe, dir, yaw) in [("home", -f.endZone, -1.0, Float(-Double.pi / 2)),
                                     ("away", f.length + f.endZone, 1.0, Float(Double.pi / 2))] {
            for d in V.endLine {
                let x = xe + dir * d.offset, z = -dir * d.along
                guard d.model == V.sway.model else {
                    place(d.model, x: x, z: z, yaw: yaw, side: side)
                    continue
                }
                // The net's mesh hangs from its own pivot; its poles stay put.
                let pivot = SceneMath.local(x: x, y: V.sway.pivotHeightMetres / V.metresPerYard, z: z)
                var hanging: [String: Bin] = [:]
                add(d.model, c, at: SceneMath.local(x: x, y: 0, z: z), yaw: yaw, side: side, into: &bins,
                    only: { !$0.contains("__prop_net") })
                add(d.model, c, at: SceneMath.local(x: x, y: 0, z: z) - pivot, yaw: yaw, side: side, into: &hanging,
                    only: { $0.contains("__prop_net") })
                shadow(d.model, c, x: x, z: z)
                let holder = Entity()
                holder.name = "sideline.net.\(side)"
                holder.position = pivot
                for (key, bin) in hanging where !bin.mesh.isEmpty {
                    holder.addChild(bin.mesh.entity("sideline.net.\(side).\(key)", material(bin.material, side: bin.side, c)))
                }
                fixed.addChild(holder)
                nets.append((xe, holder))
            }
        }

        if !shadows.isEmpty, let decal = c.assets.texture("lighting.propShadowDecal") ?? c.assets.texture("sideline.propShadow") {
            // Lighting's contract (docs/actors/lighting-sky.md): black, the
            // decal as opacity, scaled by the shared contact occlusion, under
            // the paint, never additive.
            // Lighting's decal is RGBA: black colour, the shadow in alpha. A
            // base colour texture's alpha is what a transparent PBR surface
            // takes its coverage from, scaled here by the shared occlusion.
            var m = PhysicallyBasedMaterial()
            m.baseColor = .init(tint: .black, texture: StadiumLook.clamped(decal))
            m.roughness = .init(floatLiteral: 1)
            m.blending = .transparent(opacity: .init(floatLiteral: Float(V.shadow.strength)))
            let e = shadows.entity("sideline.shadows", m)
            StadiumLook.ground(e, order: 2)
            fixed.addChild(e)
        }
        var netMeshes: [ModelEntity] = []
        for (key, bin) in bins.sorted(by: { $0.key < $1.key }) where !bin.mesh.isEmpty {
            let e = bin.mesh.entity("sideline.\(key)", material(bin.material, side: bin.side, c))
            if bin.material == "prop_gold" {
                e.components.set(DynamicLightShadowComponent(castsShadow: true))
            }
            if bin.material == "prop_net" { netMeshes.append(e) }
            fixed.addChild(e)
        }
        for holder in nets.map(\.entity) {
            netMeshes += holder.children.compactMap { $0 as? ModelEntity }
        }
        upgradeNets(netMeshes, c)
    }

    /// The chain set on the chain crew's sideline, its forward rod on the line
    /// to gain; the down box at the ball with the down showing; the college
    /// ground markers at the line to gain on both sidelines.
    private func buildCrew(_ c: StadiumContext) {
        let s = c.spec, V = c.look.sideline
        guard let p = s.field.props else { return }
        let gain = s.lasers.first { $0.kind == "lineToGain" }?.x
        let scrimmage = s.lasers.first { $0.kind == "scrimmage" }?.x
        let down = s.status.down ?? 0
        let key = "\(gain ?? -1)|\(scrimmage ?? -1)|\(down)|\(s.league)"
        guard key != crewKey else { return }
        crewKey = key
        crew.children.removeAll()
        guard let gain, let scrimmage else { return }

        let half = s.field.width / 2
        let sign: Double = p.chains.side == "home" ? 1 : -1
        let yaw: Float = sign > 0 ? 0 : .pi
        let side = p.chains.side
        let forward = gain >= scrimmage ? 1.0 : -1.0
        var bins: [String: Bin] = [:]
        let z = sign * (half + V.chains.offset)
        // The crew is three parts: its steel links and rod ends draw in the rods' white.
        let crewMap = ["prop_steel": "prop_white"]
        add(V.chains.set, c, at: SceneMath.local(x: gain - forward * 5, y: 0, z: z), yaw: yaw, side: side, into: &bins,
            remap: crewMap)
        add(V.chains.box, c, at: SceneMath.local(x: scrimmage, y: 0, z: sign * (half + V.chains.boxOffset)), yaw: yaw,
            side: side, into: &bins, only: { part in
                // the box carries four digit sets; show the down being played
                !part.hasPrefix("down_") || part.hasPrefix("down_\(max(1, min(4, down)))__")
            }, remap: crewMap)
        if s.league == "college-football" {
            for (gs, gy) in [(1.0, Float(0)), (-1.0, Float.pi)] {
                add(V.chains.ground, c, at: SceneMath.local(x: gain, y: 0, z: gs * (half + 0.5)), yaw: gy,
                    side: side, into: &bins, remap: crewMap)
            }
        }
        for (k, bin) in bins.sorted(by: { $0.key < $1.key }) where !bin.mesh.isEmpty {
            crew.addChild(bin.mesh.entity("crew.\(k)", material(bin.material, side: bin.side, c)))
        }
    }

    /// Nets on the view-angle graph (NetFresnel.usda): a mesh of cords at
    /// `visual.sideline.net.minOpacity` face-on - behind the goal, the view
    /// that matters - fading only as the net turns edge-on. The blended
    /// texture material stays if it does not load.
    private func upgradeNets(_ meshes: [ModelEntity], _ c: StadiumContext) {
        let V = c.look.sideline
        guard !meshes.isEmpty, let spec = c.spec.shaderGraph?.materials?[V.netMaterial],
              let mask = c.assets.texture("sideline.netMask") else { return }
        Task { @MainActor in
            guard var m = await StadiumShaderGraph.material(spec.prim, file: spec.file) else {
                StadiumLog.log.error("[shadergraph] net falloff unavailable; keeping the blended net")
                return
            }
            for (k, v) in spec.parameters { StadiumShaderGraph.set(&m, k, v.any) }
            // a net keeps a face-on minimum; it only fades as it turns edge-on
            StadiumShaderGraph.set(&m, "FaceOpacity", V.net.minOpacity)
            StadiumShaderGraph.set(&m, "GrazingOpacity", V.net.grazingOpacity)
            do { try m.setParameter(name: "Mask", value: .textureResource(mask)) } catch {
                StadiumLog.log.error("[shadergraph] net mask: \(error.localizedDescription, privacy: .public)")
                return
            }
            for e in meshes { e.model?.materials = [m] }
            StadiumLog.log.notice("[shadergraph] net falloff on \(meshes.count) meshes")
        }
    }

    // MARK: shadows

    /// A shadow decal under a prop: a quad on the turf about three times its
    /// footprint, one yaw for every prop so the lobes keep to the banks.
    private func shadow(_ id: String, _ c: StadiumContext, x: Double, z: Double) {
        let V = c.look.sideline, S = V.shadow
        let modelId = id + (c.tabletop ? V.lodSuffix.tabletop : V.lodSuffix.stadium)
        guard let foot = footprints[modelId] else { return }
        let yards = Double(max(foot.x, foot.y)) * 2 / V.metresPerYard
        let size = min(S.maxYards, max(S.minYards, yards * S.footprintScale))
        let h = size / 2
        let y = S.lift
        shadows.quad(SceneMath.local(x: x - h, y: y, z: z + h), SceneMath.local(x: x + h, y: y, z: z + h),
                     SceneMath.local(x: x + h, y: y, z: z - h), SceneMath.local(x: x - h, y: y, z: z - h),
                     uv: (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, 1), SIMD2(0, 1)), normal: SIMD3(0, 1, 0))
    }

    // MARK: models into merged meshes

    private func add(_ id: String, _ c: StadiumContext, at position: SIMD3<Float>, yaw: Float, side: String,
                     into bins: inout [String: Bin], only: ((String) -> Bool)? = nil,
                     remap: [String: String] = [:]) {
        let V = c.look.sideline
        let modelId = id + (c.tabletop ? V.lodSuffix.tabletop : V.lodSuffix.stadium)
        guard let parts = parts(modelId, c) else { return }
        let scale = Float(1 / V.metresPerYard)
        let turn = simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0))
        for (partName, mesh) in parts {
            if let only, !only(partName) { continue }
            // Blender suffixes a repeated mesh name (`_002`); the palette key is the name without it.
            var material = String(partName.split(separator: "__").last ?? "")
            if let r = material.range(of: #"_\d{3}$"#, options: .regularExpression) { material.removeSubrange(r) }
            guard var entry = V.palette[material] else { continue }
            if let alias = entry.alias, let target = V.palette[alias] { material = alias; entry = target }
            if let to = remap[material], let target = V.palette[to] { material = to; entry = target }
            // Every team-tinted surface wears the same chip, so a club's pads,
            // bench backs, tents and cooler lids are one mesh, not four.
            let tinted = entry.tint == "team"
            let key = tinted ? "team@\(side)" : material
            var bin = bins[key] ?? Bin(material: tinted ? "tint_team_primary" : material, side: tinted ? side : nil)
            var moved = mesh
            moved.positions = mesh.positions.map { position + turn.act($0 * scale) }
            moved.normals = mesh.normals.map { turn.act($0) }
            bin.mesh.append(moved)
            bins[key] = bin
        }
    }

    /// A model's meshes, flattened into its own metres, keyed by mesh name.
    private func parts(_ modelId: String, _ c: StadiumContext) -> [String: MeshBuilder]? {
        if let hit = geometry[modelId] { return hit }
        guard let model = c.assets.model("sideline.\(modelId)") else { return nil }
        var out: [String: MeshBuilder] = [:]
        func visit(_ e: Entity) {
            if let mc = e.components[ModelComponent.self] {
                let named = e.name.contains("__") ? e.name : (e.parent?.name ?? e.name)
                let toModel = e.transformMatrix(relativeTo: model)
                var b = out[named] ?? MeshBuilder()
                let contents = mc.mesh.contents
                for inst in contents.instances {
                    guard let m = contents.models[inst.model] else { continue }
                    let t = toModel * inst.transform
                    let n3 = simd_float3x3(SIMD3(t.columns.0.x, t.columns.0.y, t.columns.0.z),
                                           SIMD3(t.columns.1.x, t.columns.1.y, t.columns.1.z),
                                           SIMD3(t.columns.2.x, t.columns.2.y, t.columns.2.z))
                    for part in m.parts {
                        let pos = part.positions.elements
                        guard !pos.isEmpty else { continue }
                        let nrm = part.normals?.elements
                        let uv = part.textureCoordinates?.elements
                        let idx = part.triangleIndices?.elements ?? Array(0..<UInt32(pos.count))
                        let base = UInt32(b.positions.count)
                        for (k, p) in pos.enumerated() {
                            let w = t * SIMD4(p, 1)
                            b.positions.append(SIMD3(w.x, w.y, w.z))
                            let n = nrm.map { simd_normalize(n3 * $0[k]) } ?? SIMD3(0, 1, 0)
                            b.normals.append(n)
                            b.uvs.append(uv.map { $0[k] } ?? .zero)
                        }
                        b.indices += idx.map { $0 + base }
                    }
                }
                out[named] = b
            }
            for child in e.children { visit(child) }
        }
        visit(model)
        geometry[modelId] = out
        let below = Float(c.look.sideline.shadow.footprintBelowMetres)
        var lo = SIMD2<Float>(repeating: .greatestFiniteMagnitude), hi = SIMD2<Float>(repeating: -.greatestFiniteMagnitude)
        for mesh in out.values {
            for p in mesh.positions where p.y < below {
                lo = simd_min(lo, SIMD2(p.x, p.z)); hi = simd_max(hi, SIMD2(p.x, p.z))
            }
        }
        if lo.x <= hi.x { footprints[modelId] = simd_max(simd_abs(lo), simd_abs(hi)) }
        return out
    }

    private func material(_ key: String, side: String?, _ c: StadiumContext) -> any Material {
        let V = c.look.sideline
        guard let entry = V.palette[key] else { return StadiumLook.solid("#808080") }
        var hex = entry.color
        if entry.tint == "team", let side {
            hex = side == "away" ? c.spec.teams.away.chip : c.spec.teams.home.chip
        }
        var m = StadiumLook.solid(hex, roughness: entry.roughness, metallic: entry.metallic, cull: entry.mask == nil)
        if let mask = entry.mask, let tex = c.assets.texture("sideline.\(mask)") {
            // Blended, not cut: a cutout net's mips fall under any threshold
            // and the net vanishes past a few yards; blended it fades to the
            // haze a real net is from the stands.
            m.blending = .transparent(opacity: .init(scale: Float(entry.opacity ?? 1), texture: StadiumLook.repeating(tex)))
        }
        return m
    }

    // MARK: boards

    /// LED boards on the face of the stands' front wall, all the way round.
    private func buildBoards(_ c: StadiumContext) {
        let s = c.spec, V = c.look.sideline
        guard let wall = s.bowl.wall else { return }
        let shape = s.bowl.shape
        let S = c.look.bowl.segments
        let angles = (0...S).map { Double($0) / Double(S) * 2 * .pi }
        var board = MeshBuilder()
        var run: Float = 0
        for k in 0..<S {
            if c.cut(angles[k], angles[k + 1]) { continue }
            let a = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k])
            let b = SceneMath.bowlPoint(shape, offset: wall.offset, angle: angles[k + 1])
            let seg = Float(hypot(b.x - a.x, b.z - a.z))
            let panel = Float(V.boards.panelYards)
            let u0 = run / panel, u1 = (run + seg) / panel
            run += seg
            let h = Float(wall.height)
            // v runs up the image, so the board text reads upright.
            board.quad(SIMD3(Float(a.x), 0, Float(a.z)), SIMD3(Float(b.x), 0, Float(b.z)),
                       SIMD3(Float(b.x), h, Float(b.z)), SIMD3(Float(a.x), h, Float(a.z)),
                       uv: (SIMD2(u0, 0), SIMD2(u1, 0), SIMD2(u1, 1), SIMD2(u0, 1)))
        }
        let material: any Material = StadiumText.boards(s).map { StadiumLook.emissive("#FFFFFF", scale: V.boards.brightness, texture: $0) }
            ?? StadiumLook.solid(s.palette[wall.color] ?? "#07090D")
        root.addChild(board.entity("wall.boards", material))
    }
}
