import RealityKit
import UIKit
import simd

/// The crowd: 24 modelled fans from the Blender kit, seated on every row in
/// the clubs' colours, and moving the way a stand moves.
///
/// Three rings, by distance from the wearer's seat (`visual.crowd.rings`):
///
/// - **lod0**, the row or two around you: the kit's full meshes, frozen in
///   each pose and merged per group.
/// - **lod1**, out to about 12 yards: the kit's light meshes, the same way.
/// - **everyone else**: a card per fan from the kit's impostor atlas, cut
///   from the view angle that fan is seen at, mirrored for the far side.
///
/// Fans move by group, never per fan on the CPU (docs/ART_BIBLE.md). A near
/// group changes pose by swapping which merged mesh it shows; a card group by
/// shifting its material's texture transform down the atlas one pose row.
/// So idle fidgets, the wave, a section on its feet for third down and a
/// scoring section's surge all cost a handful of property writes a frame.
///
/// Club colour is composed once per matchup: the kit's albedo is multiplied
/// by the chips through its tint mask (R primary, G secondary, B face paint),
/// once for the home side and once for the away section.
///
/// Reads `bowl.crowd`, `bowl.sectionTint`, the scene's status, and
/// `visual.crowd`; surges when Moments writes a surge to the blackboard.
@MainActor
final class CrowdActor: StadiumActor {
    let name = "crowd"
    let root = Entity()

    enum Ring: Int { case lod0 = 0, lod1 = 1, card = 2 }

    /// A group of fans that move together.
    final class Group {
        let entity: ModelEntity
        let ring: Ring
        let away: Bool
        let slice: Int
        /// Near rings: the merged mesh for each pose. Cards: empty.
        var poseMeshes: [MeshResource] = []
        var material: PhysicallyBasedMaterial
        var pose = -1
        var brightness = -1.0
        let phase: Double
        let standing: Bool
        init(entity: ModelEntity, ring: Ring, away: Bool, slice: Int, material: PhysicallyBasedMaterial,
             phase: Double, standing: Bool) {
            self.entity = entity; self.ring = ring; self.away = away; self.slice = slice
            self.material = material; self.phase = phase; self.standing = standing
        }
    }

    private(set) var groups: [Group] = []
    private(set) var fans = 0
    private(set) var counts: [Ring: Int] = [:]
    private var tint: String? = "unset"
    private var seatKey: SIMD3<Float>?
    private var groanUntil: (away: Bool, until: Double)?
    private var cardRowV: Float = 0
    private var generation = 0

    init() { root.name = "actor.crowd" }

    // MARK: build

    func build(_ c: StadiumContext) {
        clear()
        groups.removeAll()
        fans = 0
        counts = [:]
        tint = "unset"
        let s = c.spec, C = c.look.crowd
        guard let kit = CrowdKit.load(C) else {
            StadiumLog.log.error("[stadium] crowd kit missing from the bundle; no fans")
            return
        }
        // Composing club colour takes a second or more; the first frame must not
        // wait for it. Draw in the kit's own colours and re-dress when ready.
        let ready = kit.cachedDress(for: s, look: c.look)
        // Untinted, a club region is 0.86 grey and a stand reads as snow, so
        // the first frame wears a quarter-size dress composed right here.
        let dress = ready ?? kit.quickDress(for: s, look: c.look)
        generation += 1
        let normal = c.assets.texture("crowd.impostorNormal")

        // Where the wearer sits decides the rings and which way each card turns.
        let seat = c.shared.seat ?? {
            let o = s.presentation.stadium.seat(nil)
            return SceneMath.local(x: o.x, y: o.y, z: o.z)
        }()
        seatKey = c.tabletop ? nil : seat

        var rng = CrowdRng(s: C.seed)
        let shape = s.bowl.shape
        let perRow = C.seatsPerRow.value(tabletop: c.tabletop)
        let yard = Float(1 / C.metresPerYard)
        let cardScale = Float(C.impostor.scale.value(tabletop: c.tabletop))
        let cw = Float(C.impostor.worldMetres[0]) * yard * cardScale
        let ch = Float(C.impostor.worldMetres[1]) * yard * cardScale
        let slices = max(1, C.slices)
        let away = s.bowl.crowd.awaySection
        let wearerSeats = (s.presentation.stadium.seats ?? []).map { SceneMath.local(x: $0.x, y: $0.y, z: $0.z) }
        let clear = Float(C.clearance.radius), clearHeight = Float(C.clearance.height)

        struct Placed { let fan: Int; let base: SIMD3<Float>; let facing: SIMD3<Float>; let away: Bool; let slice: Int; let dist: Float }
        var placed: [Placed] = []
        for tier in c.tiers {
            let rows = c.look.bowl.rows[tier.name] ?? 20
            let step = c.tabletop ? 2 : 1
            for r in stride(from: 0, to: rows, by: step) {
                let row = SceneMath.row(tier, r, of: rows)
                let m = row.front + (row.back - row.front) * 0.45
                let (angles, _) = SceneMath.evenAngles(shape, offset: m, count: perRow)
                var previous = -1
                for t in angles {
                    guard rng.next() < C.fill else { continue }
                    if c.cut(t, t) { continue }
                    let p = SceneMath.bowlPoint(shape, offset: m, angle: t)
                    if !c.tabletop && wearerSeats.contains(where: { w in
                        hypot(Float(p.x) - w.x, Float(p.z) - w.z) < clear && abs(Float(row.tread) - w.y) < clearHeight
                    }) { continue }
                    let n = SceneMath.inward(shape, offset: m, angle: t)
                    let isAway = away.map { a in (a.side == "far" ? p.z < 0 : p.z > 0) && p.x >= a.fromX - 50 } ?? false
                    // Never the same fan twice in a row: nobody sits beside their twin.
                    var fan = Int(rng.next() * Double(C.fans)) % C.fans
                    if fan == previous { fan = (fan + 1 + Int(rng.next() * Double(C.fans - 1))) % C.fans }
                    previous = fan
                    let side = SIMD3<Float>(-Float(n.y), 0, Float(n.x))
                    let jitter = Float(rng.next() - 0.5) * Float(C.sideJitter) * 2
                    let base = SIMD3(Float(p.x), Float(row.tread), Float(p.z)) + side * jitter
                    let slice = min(slices - 1, Int(t / (2 * .pi) * Double(slices)))
                    placed.append(Placed(fan: fan, base: base, facing: SIMD3(Float(n.x), 0, Float(n.y)),
                                         away: isAway, slice: slice, dist: simd_distance(base, seat)))
                }
            }
        }

        // Rings: the nearest fans become meshes, up to the budget's caps.
        var ringOf = [Ring](repeating: .card, count: placed.count)
        if !c.tabletop {
            let order = placed.indices.sorted { placed[$0].dist < placed[$1].dist }
            var n0 = 0, n1 = 0
            for i in order {
                let d = Double(placed[i].dist)
                if d < C.rings.lod0Yards && n0 < C.rings.lod0Max { ringOf[i] = .lod0; n0 += 1 }
                else if d < C.rings.lod1Yards && n1 < C.rings.lod1Max { ringOf[i] = .lod1; n1 += 1 }
            }
        }

        // Near rings: one merged mesh per group per pose.
        struct NearKey: Hashable { let ring: Ring; let away: Bool; let phase: Int }
        var near: [NearKey: [Placed]] = [:]
        // Cards: one quad per fan, grouped by slice and side.
        struct CardKey: Hashable { let slice: Int; let away: Bool }
        var cards: [CardKey: MeshBuilder] = [:]
        let atlas = kit.impostorSize
        let cell = SIMD2<Float>(Float(C.impostor.cellPixels[0]), Float(C.impostor.cellPixels[1]))
        let blockW = Float(C.impostor.cellPixels[0] * C.impostor.blockCells[0])
        let blockH = Float(C.impostor.cellPixels[1] * C.impostor.blockCells[1])
        cardRowV = cell.y / Float(atlas.height)
        for (i, f) in placed.enumerated() {
            switch ringOf[i] {
            case .lod0, .lod1:
                near[NearKey(ring: ringOf[i], away: f.away, phase: f.slice % 2), default: []].append(f)
            case .card:
                let toViewer = simd_normalize(SIMD3(seat.x - f.base.x, 0, seat.z - f.base.z) + SIMD3(0, 0, 1e-6))
                let right = simd_normalize(simd_cross(-toViewer, SIMD3<Float>(0, 1, 0)))
                // Which way the fan faces as the wearer sees it: 0 toward, +90 to the wearer's right.
                let yaw = atan2(simd_dot(f.facing, right), simd_dot(f.facing, toViewer)) * 180 / .pi
                let views = C.impostor.viewsYaw
                let step = 180 / Float(max(1, views.count - 1))
                let k = Int((abs(yaw) / step).rounded())
                let view = min(views.count - 1, k)
                let mirrored = yaw < 0 && view > 0 && view < views.count - 1
                let bx = Float(f.fan % C.impostor.blocksPerRow) * blockW
                let by = Float(f.fan / C.impostor.blocksPerRow) * blockH
                let u0 = (bx + Float(view) * cell.x + 0.5) / Float(atlas.width)
                let u1 = (bx + Float(view + 1) * cell.x - 0.5) / Float(atlas.width)
                let vTop = 1 - (by + 0.5) / Float(atlas.height)
                let vBottom = 1 - (by + cell.y - 0.5) / Float(atlas.height)
                let (ul, ur) = mirrored ? (u1, u0) : (u0, u1)
                let a = f.base - right * (cw / 2), b = f.base + right * (cw / 2)
                let up = SIMD3<Float>(0, ch, 0)
                var mb = cards[CardKey(slice: f.slice, away: f.away)] ?? MeshBuilder()
                mb.quad(a, b, b + up, a + up,
                        uv: (SIMD2(ul, vBottom), SIMD2(ur, vBottom), SIMD2(ur, vTop), SIMD2(ul, vTop)),
                        normal: toViewer)
                cards[CardKey(slice: f.slice, away: f.away)] = mb
            }
            fans += 1
            counts[ringOf[i], default: 0] += 1
        }

        let poses = C.poses.count
        for (key, list) in near.sorted(by: { ($0.key.ring.rawValue, $0.key.away ? 1 : 0, $0.key.phase) < ($1.key.ring.rawValue, $1.key.away ? 1 : 0, $1.key.phase) }) {
            var meshes: [MeshResource] = []
            for pi in 0..<poses {
                var mb = MeshBuilder()
                for f in list {
                    guard let src = kit.poseMesh(ring: key.ring, fan: f.fan, pose: C.poses[pi]) else { continue }
                    mb.append(src.placed(at: f.base, facing: f.facing, scale: yard))
                }
                if let res = mb.resource("crowd.\(key.ring).\(pi)") { meshes.append(res) }
            }
            guard meshes.count == poses else { continue }
            var mat = PhysicallyBasedMaterial()
            mat.baseColor = .init(tint: .white, texture: .init((key.away ? dress.fanAway : dress.fanHome)))
            mat.roughness = .init(floatLiteral: Float(C.roughness))
            mat.faceCulling = .back
            let e = ModelEntity(mesh: meshes[0], materials: [mat])
            e.name = "crowd.\(key.ring).\(key.away ? "away" : "home").\(key.phase)"
            root.addChild(e)
            let g = Group(entity: e, ring: key.ring, away: key.away, slice: key.phase * slices / 2,
                          material: mat, phase: Double(key.phase) * 0.37, standing: false)
            g.poseMeshes = meshes
            g.pose = 0
            groups.append(g)
        }
        for (key, mb) in cards.sorted(by: { ($0.key.slice, $0.key.away ? 1 : 0) < ($1.key.slice, $1.key.away ? 1 : 0) }) {
            guard let res = mb.resource("crowd.cards.\(key.slice)") else { continue }
            var mat = PhysicallyBasedMaterial()
            mat.baseColor = .init(tint: .white, texture: .init(key.away ? dress.cardAway : dress.cardHome))
            if let normal { mat.normal = .init(texture: .init(normal)) }
            mat.roughness = .init(floatLiteral: Float(C.roughness))
            mat.opacityThreshold = Float(C.impostor.alphaCutoff)
            mat.faceCulling = .none
            let e = ModelEntity(mesh: res, materials: [mat])
            e.name = "crowd.cards.\(key.slice).\(key.away ? "away" : "home")"
            root.addChild(e)
            var h = UInt64(key.slice * 7919 + (key.away ? 104_729 : 0)) &+ C.seed
            h ^= h >> 17
            let phase = Double(h % 997) / 997
            groups.append(Group(entity: e, ring: .card, away: key.away, slice: key.slice, material: mat,
                                phase: phase, standing: phase < C.standingShare))
        }
        if ready == nil {
            let token = generation
            kit.composeDress(for: s, look: c.look) { [weak self] d in
                guard let self, self.generation == token else { return }
                self.redress(d)
            }
        }
        StadiumLog.log.notice("[stadium] crowd: \(self.fans) fans, lod0 \(self.counts[.lod0] ?? 0), lod1 \(self.counts[.lod1] ?? 0), cards \(self.counts[.card] ?? 0), groups \(self.groups.count)")
    }

    private func redress(_ d: CrowdKit.Dress) {
        for g in groups {
            let t: TextureResource = g.ring == .card ? (g.away ? d.cardAway : d.cardHome) : (g.away ? d.fanAway : d.fanHome)
            g.material.baseColor.texture = .init(t)
            g.entity.model?.materials = [g.material]
        }
    }

    // MARK: moments

    func apply(_ c: StadiumContext, previous: SceneSpec?) {
        // A new seat turns every card and moves the rings: rebuild.
        if let seat = c.shared.seat, let key = seatKey, simd_distance(seat, key) > 2 {
            build(c)
        }
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        guard case .moment(let m) = event, m.kind == "turnover" else { return }
        // The side that gave the ball away groans.
        groanUntil = (away: m.side == "home", until: c.shared.time + c.look.crowd.groanSeconds)
    }

    // MARK: motion

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        let C = c.look.crowd, s = c.spec
        let time = frame.time
        let index = { (name: String) in C.poses.firstIndex(of: name) ?? 0 }
        let sit = index("sit"), sitB = index("sit_b"), stand = index("stand")
        let clap = index("clap_b"), cheer = index("cheer_a"), groan = index("groan")

        let surge = c.shared.surge.flatMap { time < $0.until ? $0 : nil }
        let groaning = groanUntil.flatMap { time < $0.until ? $0 : nil }
        let tintSide = s.bowl.sectionTint.side
        // Third down: the defence's crowd gets up.
        var standingSide: Bool? = nil
        if C.thirdDownStand, s.status.state == "in", s.status.down == 3, let offense = s.status.possession {
            standingSide = offense == "home"          // away defending: the away section stands
        }
        let slices = Double(max(1, C.slices))
        let wavePhase = (time / max(1, C.waveSeconds)).truncatingRemainder(dividingBy: 2.5)

        for g in groups {
            var pose: Int
            if c.reduceMotion {
                pose = g.standing ? stand : sit
            } else {
                // Idle: sit, shift, sit - each group on its own clock.
                let span = C.idleSeconds[0] + (C.idleSeconds[1] - C.idleSeconds[0]) * g.phase
                let beat = Int((time / span + g.phase * 7).rounded(.down))
                pose = g.standing ? (beat % 3 == 0 ? clap : stand) : (beat % 2 == 0 ? sit : sitB)
                if let standingSide, g.away == standingSide { pose = stand }
                if g.ring == .card, wavePhase < 1 {
                    let a = (Double(g.slice) + 0.5) / slices
                    let d = min(abs(a - wavePhase), 1 - abs(a - wavePhase))
                    if d < C.waveWidth { pose = cheer } else if d < C.waveWidth * 2 { pose = stand }
                }
                if let groaning, g.away == groaning.away { pose = groan }
                if let surge {
                    if g.away == surge.away {
                        let beat = Int(((time + g.phase) * C.surgeHz).rounded(.down))
                        pose = [cheer, clap, cheer, stand][beat % 4]
                    } else if !g.standing {
                        pose = sit
                    }
                }
            }
            setPose(g, pose)
            let bright: Double = tintSide.map { side in (side == "away") == g.away ? C.tint.bright : C.tint.dim } ?? C.tint.normal
            if bright != g.brightness {
                g.brightness = bright
                g.material.baseColor.tint = UIColor(white: CGFloat(bright), alpha: 1)
                g.entity.model?.materials = [g.material]
            }
        }
    }

    private func setPose(_ g: Group, _ pose: Int) {
        guard pose != g.pose else { return }
        g.pose = pose
        if g.ring == .card {
            g.material.textureCoordinateTransform = .init(offset: SIMD2(0, -Float(pose) * cardRowV), scale: SIMD2(1, 1), rotation: 0)
            g.entity.model?.materials = [g.material]
        } else if pose < g.poseMeshes.count {
            g.entity.model?.mesh = g.poseMeshes[pose]
        }
    }
}

// MARK: - kit

struct CrowdRng {
    var s: UInt64
    mutating func next() -> Double {
        s = s &* 6364136223846793005 &+ 1442695040888963407
        return Double(s >> 11) / Double(1 << 53)
    }
}

/// A frozen fan mesh from the kit, in metres, Y up, facing +Z.
struct CrowdPoseMesh {
    var positions: [SIMD3<Float>] = []
    var normals: [SIMD3<Float>] = []
    var uvs: [SIMD2<Float>] = []
    var indices: [UInt32] = []

    /// This fan in the stands: yards, turned to face the field, on its seat.
    func placed(at base: SIMD3<Float>, facing: SIMD3<Float>, scale: Float) -> MeshBuilder {
        let yaw = atan2(facing.x, facing.z)
        let q = simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0))
        var mb = MeshBuilder()
        mb.positions = positions.map { q.act($0 * scale) + base }
        mb.normals = normals.map { q.act($0) }
        mb.uvs = uvs
        mb.indices = indices
        return mb
    }
}

/// The Blender kit, loaded once: frozen pose meshes by name, and the atlases
/// to dress per matchup.
@MainActor
final class CrowdKit {
    private static var cache: CrowdKit?
    private static var dressCache: [String: Dress] = [:]

    let look: SceneSpec.Look.CrowdLook
    private var meshes: [String: CrowdPoseMesh] = [:]
    private let fanAlbedo: CGImage, fanMask: CGImage, cardAlbedo: CGImage, cardMask: CGImage
    var impostorSize: (width: Int, height: Int) { (cardAlbedo.width, cardAlbedo.height) }

    struct Dress {
        let fanHome: TextureResource, fanAway: TextureResource
        let cardHome: TextureResource, cardAway: TextureResource
    }

    private init?(_ C: SceneSpec.Look.CrowdLook) {
        guard let folder = StadiumAssets.folder,
              let fa = StadiumAssets.image(folder.appendingPathComponent(C.kit.fanAlbedo)),
              let fm = StadiumAssets.image(folder.appendingPathComponent(C.kit.fanMask)),
              let ca = StadiumAssets.image(folder.appendingPathComponent(C.kit.impostorAlbedo)),
              let cm = StadiumAssets.image(folder.appendingPathComponent(C.kit.impostorMask)) else { return nil }
        look = C
        fanAlbedo = fa; fanMask = fm; cardAlbedo = ca; cardMask = cm
        for id in ["lod0Poses", "lod1Poses"] {
            guard let template = StadiumAssets.shared.model("crowd.\(id)") else { continue }
            collect(template, root: template)
        }
    }

    static func load(_ C: SceneSpec.Look.CrowdLook) -> CrowdKit? {
        if let cache, cache.look == C { return cache }
        cache = CrowdKit(C)
        dressCache.removeAll()
        return cache
    }

    private func collect(_ e: Entity, root: Entity) {
        if let model = e.components[ModelComponent.self] {
            let world = e.transformMatrix(relativeTo: root)
            var out = CrowdPoseMesh()
            let contents = model.mesh.contents
            for instance in contents.instances {
                guard let m = contents.models[instance.model] else { continue }
                let xf = world * instance.transform
                let nx = simd_float3x3(SIMD3(xf.columns.0.x, xf.columns.0.y, xf.columns.0.z),
                                       SIMD3(xf.columns.1.x, xf.columns.1.y, xf.columns.1.z),
                                       SIMD3(xf.columns.2.x, xf.columns.2.y, xf.columns.2.z)).inverse.transpose
                for part in m.parts {
                    let base = UInt32(out.positions.count)
                    let pos = part.positions.elements
                    out.positions += pos.map { p in
                        let w = xf * SIMD4(p, 1)
                        return SIMD3(w.x, w.y, w.z)
                    }
                    let nrm = part.normals?.elements ?? Array(repeating: SIMD3(0, 1, 0), count: pos.count)
                    out.normals += nrm.map { simd_normalize(nx * $0) }
                    out.uvs += part.textureCoordinates?.elements ?? Array(repeating: .zero, count: pos.count)
                    out.indices += (part.triangleIndices?.elements ?? []).map { $0 + base }
                }
            }
            if !out.indices.isEmpty {
                // USD prim names from Blender: "<fan>_lod<k>_<pose>", sometimes nested under a same-named xform.
                meshes[e.name] = out
                if let parent = e.parent, meshes[parent.name] == nil { meshes[parent.name] = out }
            }
        }
        for child in e.children { collect(child, root: root) }
    }

    func poseMesh(ring: CrowdActor.Ring, fan: Int, pose: String) -> CrowdPoseMesh? {
        let id = String(format: "fan%02d_lod%d_%@", fan, ring == .lod0 ? 0 : 1, pose)
        return meshes[id]
    }

    // MARK: dressing

    private var plain: Dress?

    /// The kit's atlases untinted: what the crowd wears until its club colours are composed.
    func plainDress() -> Dress {
        if let plain { return plain }
        func tex(_ img: CGImage) -> TextureResource {
            StadiumText.texture(img) ?? (try! TextureResource(image: img, options: .init(semantic: .color)))
        }
        let fan = tex(fanAlbedo), card = tex(cardAlbedo)
        let d = Dress(fanHome: fan, fanAway: fan, cardHome: card, cardAway: card)
        plain = d
        return d
    }

    private var quick: [String: Dress] = [:]

    /// A quarter-size dress, composed synchronously in well under a frame
    /// budget's worth of seconds, so fans never appear in the kit's grey.
    func quickDress(for s: SceneSpec, look: SceneSpec.Look) -> Dress {
        let C = look.crowd
        let key = Self.key(s, C)
        if let d = quick[key] { return d }
        let home = SceneMath.rgba(s.bowl.crowd.home), away = SceneMath.rgba(s.bowl.crowd.away)
        let homeRaw = SceneMath.rgba(s.teams.home.color), awayRaw = SceneMath.rgba(s.teams.away.color)
        let secondary = SceneMath.rgba(C.secondary)
        let fanLayout = Layout.grid(cols: C.fanGrid[0], rows: C.fanGrid[1])
        let cardLayout = Layout.blocks(perRow: C.impostor.blocksPerRow,
                                       w: C.impostor.cellPixels[0] * C.impostor.blockCells[0],
                                       h: C.impostor.cellPixels[1] * C.impostor.blockCells[1])
        let shade = (Float(C.shirtShade[0]), Float(C.shirtShade[1]))
        func make(_ a: CGImage, _ m: CGImage, _ chip: SIMD4<Float>, _ raw: SIMD4<Float>, _ layout: Layout) -> CGImage? {
            Self.tint(a, m, chip: chip, raw: raw, secondary: secondary, fans: C.fans, rawShare: Float(C.rawShare),
                      shade: shade, layout: layout, divisor: 4)
        }
        let plain = plainDress()
        let d = Dress(fanHome: StadiumText.texture(make(fanAlbedo, fanMask, home, homeRaw, fanLayout)) ?? plain.fanHome,
                      fanAway: StadiumText.texture(make(fanAlbedo, fanMask, away, awayRaw, fanLayout)) ?? plain.fanAway,
                      cardHome: StadiumText.texture(make(cardAlbedo, cardMask, home, homeRaw, cardLayout)) ?? plain.cardHome,
                      cardAway: StadiumText.texture(make(cardAlbedo, cardMask, away, awayRaw, cardLayout)) ?? plain.cardAway)
        quick[key] = d
        return d
    }

    private static func key(_ s: SceneSpec, _ C: SceneSpec.Look.CrowdLook) -> String {
        "\(s.bowl.crowd.home)|\(s.bowl.crowd.away)|\(s.teams.home.color)|\(s.teams.away.color)|\(C.secondary)|\(C.rawShare)|\(C.shirtShade)"
    }

    func cachedDress(for s: SceneSpec, look: SceneSpec.Look) -> Dress? {
        Self.dressCache[Self.key(s, look.crowd)]
    }

    private struct Images: @unchecked Sendable {
        let fanHome: CGImage?, fanAway: CGImage?, cardHome: CGImage?, cardAway: CGImage?
    }
    private struct Sources: @unchecked Sendable {
        let fanAlbedo: CGImage, fanMask: CGImage, cardAlbedo: CGImage, cardMask: CGImage
    }

    /// The kit's atlases in this matchup's colours, composed off the main
    /// actor and cached per pair of clubs. `done` runs on the main actor.
    func composeDress(for s: SceneSpec, look: SceneSpec.Look, done: @escaping @MainActor (Dress) -> Void) {
        let C = look.crowd
        let key = Self.key(s, C)
        if let d = Self.dressCache[key] { done(d); return }
        let home = SceneMath.rgba(s.bowl.crowd.home), away = SceneMath.rgba(s.bowl.crowd.away)
        let homeRaw = SceneMath.rgba(s.teams.home.color), awayRaw = SceneMath.rgba(s.teams.away.color)
        let secondary = SceneMath.rgba(C.secondary)
        let src = Sources(fanAlbedo: fanAlbedo, fanMask: fanMask, cardAlbedo: cardAlbedo, cardMask: cardMask)
        let fanLayout = Layout.grid(cols: C.fanGrid[0], rows: C.fanGrid[1])
        let cardLayout = Layout.blocks(perRow: C.impostor.blocksPerRow,
                                       w: C.impostor.cellPixels[0] * C.impostor.blockCells[0],
                                       h: C.impostor.cellPixels[1] * C.impostor.blockCells[1])
        let fans = C.fans, rawShare = Float(C.rawShare)
        let shade = (Float(C.shirtShade[0]), Float(C.shirtShade[1]))
        Task.detached(priority: .userInitiated) {
            func tint(_ a: CGImage, _ m: CGImage, _ chip: SIMD4<Float>, _ raw: SIMD4<Float>, _ layout: Layout, _ half: Bool) -> CGImage? {
                CrowdKit.tint(a, m, chip: chip, raw: raw, secondary: secondary, fans: fans, rawShare: rawShare,
                              shade: shade, layout: layout, divisor: half ? 2 : 1)
            }
            // The away section is always across the bowl, so its copies are
            // composed at half size: it keeps the crowd inside its 60 MB.
            let images = Images(
                fanHome: tint(src.fanAlbedo, src.fanMask, home, homeRaw, fanLayout, false),
                fanAway: tint(src.fanAlbedo, src.fanMask, away, awayRaw, fanLayout, true),
                cardHome: tint(src.cardAlbedo, src.cardMask, home, homeRaw, cardLayout, false),
                cardAway: tint(src.cardAlbedo, src.cardMask, away, awayRaw, cardLayout, true))
            await MainActor.run {
                let plain = self.plainDress()
                let d = Dress(fanHome: StadiumText.texture(images.fanHome) ?? plain.fanHome,
                              fanAway: StadiumText.texture(images.fanAway) ?? plain.fanAway,
                              cardHome: StadiumText.texture(images.cardHome) ?? plain.cardHome,
                              cardAway: StadiumText.texture(images.cardAway) ?? plain.cardAway)
                Self.dressCache[key] = d
                done(d)
            }
        }
    }

    /// Where each fan's pixels are in an atlas.
    enum Layout: Sendable {
        case grid(cols: Int, rows: Int)
        case blocks(perRow: Int, w: Int, h: Int)

        func rect(_ fan: Int, width: Int, height: Int) -> (x: Int, y: Int, w: Int, h: Int) {
            switch self {
            case .grid(let cols, let rows):
                return (fan % cols * width / cols, fan / cols * height / rows, width / cols, height / rows)
            case .blocks(let perRow, let w, let h):
                return (fan % perRow * w, fan / perRow * h, w, h)
            }
        }
    }

    nonisolated private static func rgba(_ img: CGImage, width: Int, height: Int) -> (CGContext, UnsafeMutablePointer<UInt8>)? {
        guard let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                                  space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
              let data = ctx.data?.assumingMemoryBound(to: UInt8.self) else { return nil }
        ctx.interpolationQuality = .none
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: width, height: height))
        return (ctx, data)
    }

    /// albedo x chip through the mask. Each fan gets its own shade of the
    /// chip, and some wear the raw club colour, so a section is mottled.
    nonisolated static func tint(_ albedo: CGImage, _ mask: CGImage, chip: SIMD4<Float>, raw: SIMD4<Float>,
                                 secondary: SIMD4<Float>, fans: Int, rawShare: Float, shade: (Float, Float),
                                 layout: Layout, divisor k: Int) -> CGImage? {
        let W = albedo.width / k, H = albedo.height / k
        guard let (out, o) = rgba(albedo, width: W, height: H),
              let (maskContext, m) = rgba(mask, width: W, height: H) else { return nil }
        // `m` points into the mask context's memory: keep the context alive
        // for the whole loop, or Swift frees it after its last named use.
        withExtendedLifetime(maskContext) {
        for fan in 0..<fans {
            var h = UInt64(fan * 2654435761 + 97)
            h ^= h >> 13
            let r1 = Float(h % 1000) / 1000, r2 = Float((h / 1000) % 1000) / 1000
            let colour = (r2 < rawShare ? raw : chip) * (shade.0 + (shade.1 - shade.0) * r1)
            var (x0, y0, w, h0) = layout.rect(fan, width: W * k, height: H * k)
            x0 /= k; y0 /= k; w /= k; h0 /= k
            for y in max(0, y0)..<min(H, y0 + h0) {
                for x in max(0, x0)..<min(W, x0 + w) {
                    let i = (y * W + x) * 4
                    let a = Float(o[i + 3]) / 255
                    guard a > 0.004 else { continue }
                    let mr = Float(m[i]) / 255, mg = Float(m[i + 1]) / 255, mb = Float(m[i + 2]) / 255
                    guard mr + mg + mb > 0.004 else { continue }
                    var c = SIMD3(Float(o[i]), Float(o[i + 1]), Float(o[i + 2])) / (255 * a)
                    let p = SIMD3(colour.x, colour.y, colour.z), s = SIMD3(secondary.x, secondary.y, secondary.z)
                    c = c * (SIMD3(repeating: 1) + (p - 1) * mr) * (SIMD3(repeating: 1) + (s - 1) * mg)
                    c = c + (p * 0.86 - c) * mb
                    c = simd_clamp(c, .zero, SIMD3(repeating: 1)) * a * 255
                    o[i] = UInt8(c.x); o[i + 1] = UInt8(c.y); o[i + 2] = UInt8(c.z)
                }
            }
        }
        }
        return out.makeImage()
    }
}
