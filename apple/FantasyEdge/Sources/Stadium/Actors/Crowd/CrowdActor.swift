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

    enum Ring: Int { case lod0 = 0, lod1 = 1, lod2 = 2, card = 3 }

    /// Whose colours a section wears. Decided per section, never per seat: a group of fans
    /// shares one texture, so a lone visitor in a home section would cost another draw part.
    enum Support: Int, Hashable {
        case home = 0, away = 1, neutral = 2
        var name: String { self == .home ? "home" : self == .away ? "away" : "neutral" }
    }

    /// A group of fans that move together.
    final class Group {
        let entity: ModelEntity
        let ring: Ring
        let away: Bool
        let support: Support
        let slice: Int
        /// Near rings: the merged mesh for each slot. Cards: empty.
        var slotMeshes: [CrowdChoreography.Slot: MeshResource] = [:]
        var material: PhysicallyBasedMaterial
        var pose = -1
        var slot: CrowdChoreography.Slot?
        /// Where the group sits and which way is its fans' left, for the ripple and for heads turning to the play.
        var centre = SIMD3<Float>.zero
        var left = SIMD3<Float>(1, 0, 0)
        var brightness = -1.0
        let phase: Double
        let standing: Bool
        init(entity: ModelEntity, ring: Ring, away: Bool, support: Support = .home, slice: Int,
             material: PhysicallyBasedMaterial, phase: Double, standing: Bool) {
            self.entity = entity; self.ring = ring; self.away = away; self.support = support; self.slice = slice
            self.material = material; self.phase = phase; self.standing = standing
        }
    }

    private(set) var groups: [Group] = []
    private(set) var fans = 0
    private(set) var counts: [Ring: Int] = [:]
    private var tint: String? = "unset"
    private var seatKey: SIMD3<Float>?
    /// Which card slices hold each `bowl.seating` section, for cues aimed at sections.
    private var sectionSlices: [String: Set<Int>] = [:]
    private var cardRowV: Float = 0
    private var generation = 0
    /// The side whose moment just ended, and when: it settles back into its seats over `settleSeconds`.
    private var lastScoring: (away: Bool, ended: Double)?
    /// The moment on now: when it began and where the play was, for the ripple.
    private var momentStart: (time: Double, at: SIMD3<Float>)?
    /// How many seats each kind of support took, for the look-dev log.
    private(set) var supportCounts: [Support: Int] = [:]

    struct SectionKey: Hashable { let tier: String; let section: Int }
    private var previousTint: String?

    init() { root.name = "actor.crowd" }

    // MARK: build

    func build(_ c: StadiumContext) {
        clear()
        groups.removeAll()
        fans = 0
        counts = [:]
        tint = "unset"
        sectionSlices = [:]
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
        let pitch = C.seatPitchYards.value(tabletop: c.tabletop)
        let yard = Float(1 / C.metresPerYard)
        let cardScale = Float(C.impostor.scale.value(tabletop: c.tabletop))
        let cw = Float(C.impostor.worldMetres[0]) * yard * cardScale
        let ch = Float(C.impostor.worldMetres[1]) * yard * cardScale
        let slices = max(1, C.slices)
        let away = s.bowl.crowd.awaySection
        let wearerSeats = (s.presentation.stadium.seats ?? []).map { SceneMath.local(x: $0.x, y: $0.y, z: $0.z) }
        let clear = Float(C.clearance.radius), clearHeight = Float(C.clearance.height)

        struct Placed {
            let fan: Int; let base: SIMD3<Float>; let facing: SIMD3<Float>; let away: Bool; let slice: Int; let variant: Int
            let dist: Float; let row: Int; let seat: Int
            /// The next seat along the row is on this fan's left.
            var nextOnLeft = true
            var support = Support.home
        }
        var placed: [Placed] = []
        var rowId = 0
        // Every seat Bowl built, when the scene carries them: fans sit exactly in
        // Bowl's chairs, pairs never straddle an aisle, and a group's edge is a
        // section's edge, so a pose change lands where a real stand changes.
        let drawn = Set(c.tiers.map(\.name))
        let support = CrowdActor.supportBySection(s, look: C, drawn: drawn)
        supportCounts = [:]
        if !c.tabletop, let seating = s.bowl.seating {
            for tierSeats in seating.tiers where drawn.contains(tierSeats.tier) {
                let sections = tierSeats.sections ?? []
                // Who sits where in the row in front, by run and seat, so nobody has their twin directly ahead.
                var ahead: [Int: Int] = [:]
                for row in tierSeats.rows {
                    let ring = SceneMath.Ring(shape, offset: row.feet)
                    var recent: [Int] = []
                    var here: [Int: Int] = [:]
                    for (runIndex, run) in row.runs.enumerated() where run.count == 2 {
                        rowId += 1
                        for k in 0..<Int(run[1]) {
                            let draw = rng.next()
                            let spot = SceneMath.seat(row, run: runIndex, k: k, shape: shape, ring: ring)
                            let p = spot.position
                            // Empty seats: fewer in the upper deck than the lower, fewer in the corners
                            // than at midfield, and fewer again high up in a game already decided.
                            guard draw < C.fill * CrowdActor.keepChance(at: p, tier: tierSeats.tier, look: C, spec: s) else { continue }
                            if wearerSeats.contains(where: { w in
                                hypot(p.x - w.x, p.z - w.z) < clear && abs(p.y - w.y) < clearHeight
                            }) { continue }
                            // 24 people and 45,000 seats repeat, but never within four seats along
                            // the row or the three seats straight ahead: at the club seat a twin beside
                            // or in front of another is the first thing the eye finds.
                            let slot = runIndex * 4096 + k
                            let banned = Set(recent + [ahead[slot - 1], ahead[slot], ahead[slot + 1]].compactMap { $0 })
                            var fan = Int(rng.next() * Double(C.fans)) % C.fans
                            var tries = 0
                            while banned.contains(fan) && tries < C.fans {
                                fan = (fan + 7) % C.fans
                                tries += 1
                            }
                            recent.append(fan)
                            if recent.count > 4 { recent.removeFirst() }
                            here[slot] = fan
                            let fraction = ((run[0] + Double(k) * row.pitch) / max(1e-6, row.length))
                                .truncatingRemainder(dividingBy: 1)
                            let section = sections.firstIndex { sec in
                                sec.to <= 1 ? (fraction >= sec.from && fraction < sec.to)
                                            : (fraction >= sec.from || fraction < sec.to - 1)
                            } ?? Int(fraction * Double(max(1, sections.count)))
                            // Whose section this is, and how full it is: both decided before the seat is taken.
                            let wears = support[SectionKey(tier: tierSeats.tier, section: section)] ?? .home
                            let isAway = wears == .away
                            supportCounts[wears, default: 0] += 1
                            let slice = sections.isEmpty ? Int(fraction * Double(slices)) % slices
                                                         : section * slices / sections.count
                            if section < sections.count { sectionSlices[sections[section].id, default: []].insert(slice) }
                            let facing = SIMD3(Float(spot.facing.x), 0, Float(spot.facing.y))
                            let next = SceneMath.seat(row, run: runIndex, k: k + 1, shape: shape, ring: ring).position
                            var fanPlaced = Placed(fan: fan, base: p, facing: facing, away: isAway, slice: slice,
                                                   variant: Int(rng.next() * Double(max(1, C.cardVariants))),
                                                   dist: simd_distance(p, seat), row: rowId, seat: k)
                            fanPlaced.nextOnLeft = simd_dot(next - p, CrowdActor.leftOf(facing)) > 0
                            fanPlaced.support = wears
                            placed.append(fanPlaced)
                        }
                    }
                    ahead = here
                }
            }
        }
        let seated = !placed.isEmpty
        for tier in c.tiers where !seated {
            let rows = c.look.bowl.rows[tier.name] ?? 20
            let step = c.tabletop ? 2 : 1
            for r in stride(from: 0, to: rows, by: step) {
                let row = SceneMath.row(tier, r, of: rows)
                let m = row.front + (row.back - row.front) * 0.45
                // Seats at the scene's pitch, so a far card of two neighbours lines up with its seats.
                let (_, ringLength) = SceneMath.evenAngles(shape, offset: m, count: 1, resolution: 360)
                let (angles, _) = SceneMath.evenAngles(shape, offset: m, count: max(1, Int(ringLength / pitch)))
                var previous = -1
                rowId += 1
                for (seatIndex, t) in angles.enumerated() {
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
                    let edge = (rng.next() - 0.5) * C.sliceJitter
                    let slice = (Int((t / (2 * .pi) * Double(slices) + edge).rounded(.down)) + slices) % slices
                    placed.append(Placed(fan: fan, base: base, facing: SIMD3(Float(n.x), 0, Float(n.y)),
                                         away: isAway, slice: slice, variant: Int(rng.next() * Double(max(1, C.cardVariants))),
                                         dist: simd_distance(base, seat), row: rowId, seat: seatIndex))
                }
            }
        }

        // Rings: the nearest fans become meshes, up to the budget's caps.
        var ringOf = [Ring](repeating: .card, count: placed.count)
        if !c.tabletop {
            let order = placed.indices.sorted { placed[$0].dist < placed[$1].dist }
            var n0 = 0, n1 = 0, n2 = 0
            for i in order {
                // Dithered: each fan's ring distance wanders by up to ditherYards,
                // so a ring's edge is a ragged band, never a line of cards meeting meshes.
                var hd = UInt64(truncatingIfNeeded: i) &* 0x9E3779B97F4A7C15
                hd ^= hd >> 31
                let d = Double(placed[i].dist) + (Double(hd % 1000) / 1000 - 0.5) * 2 * C.rings.ditherYards
                if d < C.rings.lod0Yards && n0 < C.rings.lod0Max { ringOf[i] = .lod0; n0 += 1 }
                else if d < C.rings.lod1Yards && n1 < C.rings.lod1Max { ringOf[i] = .lod1; n1 += 1 }
                else if d < C.rings.lod2Yards && n2 < C.rings.lod2Max { ringOf[i] = .lod2; n2 += 1 }
                // Never a card within arm's reach of the wearer, whatever the caps say:
                // a magnified card beside you is worse than a few thousand triangles.
                else if Double(placed[i].dist) < C.rings.minCardYards { ringOf[i] = .lod2; n2 += 1 }
            }
        }

        // Near rings: one merged mesh per group per pose.
        struct NearKey: Hashable { let ring: Ring; let support: Support; let phase: Int }
        var near: [NearKey: [Placed]] = [:]
        // Cards: one quad per fan, grouped by slice and side.
        struct CardKey: Hashable { let slice: Int; let support: Support; let variant: Int }
        var cards: [CardKey: MeshBuilder] = [:]
        var cardCentres: [CardKey: (sum: SIMD3<Float>, n: Float)] = [:]
        let atlas = kit.impostorSize
        let cell = SIMD2<Float>(Float(C.impostor.cellPixels[0]), Float(C.impostor.cellPixels[1]))
        let blockW = Float(C.impostor.cellPixels[0] * C.impostor.blockCells[0])
        let blockH = Float(C.impostor.cellPixels[1] * C.impostor.blockCells[1])
        cardRowV = cell.y / Float(atlas.height)
        // Far fans sit in pairs of neighbours on one card: two seats, two triangles.
        var consumed = Set<Int>()
        for (i, f) in placed.enumerated() {
            if consumed.contains(i) { continue }
            switch ringOf[i] {
            case .lod0, .lod1, .lod2:
                near[NearKey(ring: ringOf[i], support: f.support, phase: f.slice % max(1, C.nearPhases)), default: []].append(f)
            case .card:
                var centre = f.base
                let cardForward = Float(C.chair.cardForwardMetres) * yard
                if i + 1 < placed.count, ringOf[i + 1] == .card, placed[i + 1].row == f.row, placed[i + 1].seat == f.seat + 1 {
                    centre = (f.base + placed[i + 1].base) / 2
                    consumed.insert(i + 1)
                    fans += 1
                    counts[.card, default: 0] += 1
                }
                centre += f.facing * cardForward
                let toViewer = simd_normalize(SIMD3(seat.x - centre.x, 0, seat.z - centre.z) + SIMD3(0, 0, 1e-6))
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
                let a = centre - right * (cw / 2), b = centre + right * (cw / 2)
                let up = SIMD3<Float>(0, ch, 0)
                // A neutral section keeps one card variant: two would cost a draw part for no mottle.
                let ck = CardKey(slice: f.slice, support: f.support, variant: f.support == .neutral ? 0 : f.variant)
                var mb = cards[ck] ?? MeshBuilder()
                mb.quad(a, b, b + up, a + up,
                        uv: (SIMD2(ul, vBottom), SIMD2(ur, vBottom), SIMD2(ur, vTop), SIMD2(ul, vTop)),
                        normal: toViewer)
                cards[ck] = mb
                let sofar = cardCentres[ck] ?? (.zero, 0)
                cardCentres[ck] = (sofar.sum + centre, sofar.n + 1)
            }
            fans += 1
            counts[ringOf[i], default: 0] += 1
        }

        for (key, list) in near.sorted(by: { ($0.key.ring.rawValue, $0.key.support.rawValue, $0.key.phase) < ($1.key.ring.rawValue, $1.key.support.rawValue, $1.key.phase) }) {
            var meshes: [CrowdChoreography.Slot: MeshResource] = [:]
            for slot in CrowdChoreography.Slot.allCases {
                var mb = MeshBuilder()
                for f in list {
                    let pose = CrowdActor.nearPose(slot, fan: f.fan, row: f.row, seat: f.seat, nextOnLeft: f.nextOnLeft, look: C)
                    guard let hit = kit.nearPoseMesh(ring: key.ring, fan: f.fan, pose: pose) else { continue }
                    let (name, src) = hit
                    // Into Bowl's chair: forward of its origin, pelvis on the pan whatever the fan's height.
                    let seated = name.hasPrefix("sit")
                    let forward = Float(seated ? C.chair.sitForwardMetres : C.chair.standForwardMetres) * yard
                    let scale = kit.height(f.fan) / Float(C.chair.referenceHeightMetres)
                    // The kit seats a 1.75 m fan's pelvis at kitPelvisMetres; scaled by height, then lifted to the pan.
                    let lift = seated ? (Float(C.chair.pelvisMetres) - Float(C.chair.kitPelvisMetres) * scale) * yard : 0
                    mb.append(src.placed(at: f.base + f.facing * forward + SIMD3(0, lift, 0), facing: f.facing, scale: yard))
                }
                if let res = mb.resource("crowd.\(key.ring).\(slot.rawValue)") { meshes[slot] = res }
            }
            guard let first = meshes[.sit] else { continue }
            var mat = PhysicallyBasedMaterial()
            mat.baseColor = .init(tint: .white, texture: .init(dress.fan(key.support)))
            mat.roughness = .init(floatLiteral: Float(C.roughness))
            mat.faceCulling = .back
            let e = ModelEntity(mesh: first, materials: [mat])
            e.name = "crowd.\(key.ring).\(key.support.name).\(key.phase)"
            root.addChild(e)
            let phases = Double(max(1, C.nearPhases))
            let g = Group(entity: e, ring: key.ring, away: key.support == .away, support: key.support,
                          slice: key.phase * slices / max(1, C.nearPhases),
                          material: mat, phase: (Double(key.phase) + 0.35) / phases, standing: false)
            g.slotMeshes = meshes
            g.slot = .sit
            g.centre = list.reduce(SIMD3<Float>.zero) { $0 + $1.base } / Float(max(1, list.count))
            let facing = list.reduce(SIMD3<Float>.zero) { $0 + $1.facing }
            g.left = CrowdActor.leftOf(simd_length(facing) > 1e-4 ? simd_normalize(facing) : SIMD3(0, 0, 1))
            groups.append(g)
            #if DEBUG
            let missing = CrowdChoreography.Slot.allCases.filter { meshes[$0] == nil }.map(\.rawValue)
            StadiumLog.log.notice("[stadium] crowd group \(e.name): slots \(meshes.count)/\(CrowdChoreography.Slot.allCases.count)\(missing.isEmpty ? "" : ", missing \(missing.joined(separator: ","))"), \(list.count) fans")
            #endif
        }
        for (key, mb) in cards.sorted(by: { ($0.key.slice, $0.key.support.rawValue, $0.key.variant) < ($1.key.slice, $1.key.support.rawValue, $1.key.variant) }) {
            guard let res = mb.resource("crowd.cards.\(key.slice).\(key.variant)") else { continue }
            var mat = PhysicallyBasedMaterial()
            mat.baseColor = .init(tint: .white, texture: .init(dress.card(key.support)))
            if let normal { mat.normal = .init(texture: .init(normal)) }
            mat.roughness = .init(floatLiteral: Float(C.roughness))
            mat.opacityThreshold = Float(C.impostor.alphaCutoff)
            // Spill in the club's colour, not the texture's: an emissive texture read grey here,
            // and at a hundred metres the albedo carries the mottle anyway.
            let spill = SceneMath.rgba(key.support == .away ? s.bowl.crowd.away
                                       : key.support == .neutral ? (s.palette[s.bowl.crowd.neutral] ?? s.bowl.crowd.neutral)
                                       : s.bowl.crowd.home)
            mat.emissiveColor = .init(color: UIColor(red: CGFloat(spill.x), green: CGFloat(spill.y), blue: CGFloat(spill.z), alpha: 1))
            mat.emissiveIntensity = Float(C.impostor.floodFill)
            mat.faceCulling = .none
            let e = ModelEntity(mesh: res, materials: [mat])
            e.name = "crowd.cards.\(key.slice).\(key.variant).\(key.support.name)"
            root.addChild(e)
            var h = UInt64(key.slice * 7919 + key.variant * 3571 + key.support.rawValue * 104_729) &+ C.seed
            h ^= h >> 17
            let phase = Double(h % 997) / 997
            let g = Group(entity: e, ring: .card, away: key.support == .away, support: key.support, slice: key.slice,
                          material: mat, phase: phase, standing: phase < CrowdActor.standingShare(C, spec: s))
            if let c = cardCentres[key], c.n > 0 { g.centre = c.sum / c.n }
            groups.append(g)
        }
        #if DEBUG
        // Look-dev: `-crowdCue clap:home` (or stand, sit, groan) holds a cue from the first frame,
        // so each blackboard hook can be shot before Moments calls it.
        let args = ProcessInfo.processInfo.arguments
        if let i = args.firstIndex(of: "-crowdCue"), i + 1 < args.count {
            let parts = args[i + 1].split(separator: ":").map(String.init)
            if parts.count == 2 {
                switch parts[0] {
                case "stand": c.shared.stand(.side(parts[1]), until: .infinity)
                case "clap": c.shared.stand(.side(parts[1]), until: .infinity, clap: true)
                case "sit": c.shared.sit(.side(parts[1]), until: .infinity)
                case "groan": c.shared.groan(parts[1], until: .infinity)
                default: break
                }
            }
        }
        #endif
        if ready == nil {
            let token = generation
            kit.composeDress(for: s, look: c.look) { [weak self] d in
                guard let self, self.generation == token else { return }
                self.redress(d)
            }
        }
        if !C.castShadows {
            for g in groups { g.entity.components.set(DynamicLightShadowComponent(castsShadow: false)) }
        }
        StadiumLog.log.notice("[stadium] crowd: \(self.fans) fans, lod0 \(self.counts[.lod0] ?? 0), lod1 \(self.counts[.lod1] ?? 0), lod2 \(self.counts[.lod2] ?? 0), cards \(self.counts[.card] ?? 0), groups \(self.groups.count)")
        let seatsTaken = max(1, self.supportCounts.values.reduce(0, +))
        StadiumLog.log.notice("[stadium] crowd support: home \(Int(Double(self.supportCounts[.home] ?? 0) / Double(seatsTaken) * 100))%, visiting \(Int(Double(self.supportCounts[.away] ?? 0) / Double(seatsTaken) * 100))%, neutral \(Int(Double(self.supportCounts[.neutral] ?? 0) / Double(seatsTaken) * 100))% of \(seatsTaken) seats taken")
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
        // The side that gave the ball away groans.
        c.shared.groan(m.side == "home" ? "away" : "home", until: c.shared.time + c.look.crowd.groanSeconds)
    }

    // MARK: motion

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        let C = c.look.crowd, s = c.spec
        let time = frame.time
        let index = { (name: String) in C.poses.firstIndex(of: name) ?? 0 }

        let surge = c.shared.surge.flatMap { time < $0.until ? $0 : nil }
        let cues = CrowdCues.live(c.shared, at: time)
        let tintSide = s.bowl.sectionTint.side
        if previousTint != nil, tintSide == nil { lastScoring = (previousTint == "away", time) }
        let ball = s.ball.map { SceneMath.local(x: $0.x, y: $0.y, z: $0.z) }
        if tintSide == nil { momentStart = nil }
        else if previousTint == nil || momentStart == nil { momentStart = (time, ball ?? .zero) }
        if tintSide != nil { lastScoring = nil }
        previousTint = tintSide
        // Third down: the defence's crowd gets up.
        var standingSide: Bool? = nil
        var hushSide: Bool? = nil
        if s.status.state == "in", s.status.down == 3, let offense = s.status.possession {
            // The defence's crowd gets up; the crowd whose own offence is at the line goes quiet.
            if C.thirdDownStand { standingSide = offense == "home" }
            if C.hushOwnOffence { hushSide = offense == "away" }
        }
        // A visiting score is real, but outnumbered: the away sections celebrate smaller.
        let visitorsScoring = tintSide == "away"
        let slices = Double(max(1, C.slices))

        for g in groups {
            let reaching: [CrowdChoreography.CueKind] = cues.compactMap { cue in
                let hits: Bool
                switch cue.target {
                case .side(let side): hits = (side == "away") == g.away
                case .sections(let ids): hits = g.ring == .card && ids.contains { sectionSlices[$0]?.contains(g.slice) ?? false }
                }
                return hits ? CrowdChoreography.CueKind(rawValue: cue.kind.rawValue) : nil
            }
            let input = CrowdChoreography.Input(
                away: g.away, isCard: g.ring == .card, phase: g.phase, standing: g.standing, slice: g.slice,
                slices: Int(slices), time: time, reduceMotion: c.reduceMotion, tintSide: tintSide,
                lastScoringAway: lastScoring?.away, lastScoringEnded: lastScoring?.ended ?? 0,
                settleSeconds: (C.settleSeconds[0], C.settleSeconds[1]), surgeAway: surge?.away,
                standingSideAway: standingSide, idleSeconds: (C.idleSeconds[0], C.idleSeconds[1]),
                waveSeconds: C.waveSeconds, waveWidth: C.waveWidth, surgeHz: C.surgeHz, cues: reaching,
                momentStarted: momentStart?.time,
                // The reaction spreads out from the play: the nearest groups move first.
                delay: momentStart.map { C.rippleSeconds * Double(min(1, simd_distance(g.centre, $0.at) / Float(C.rippleYards))) } ?? 0,
                riseStageSeconds: C.riseStageSeconds,
                // Heads follow the play across the group, group by group, never per fan.
                look: ball.map { b in
                    let across = simd_dot(b - g.centre, g.left)
                    return across > Float(C.lookYards) ? 1 : (across < -Float(C.lookYards) ? -1 : 0)
                } ?? 0,
                hush: hushSide.map { $0 == g.away } ?? false,
                neutral: g.support == .neutral,
                visitorsScoring: visitorsScoring,
                visitorCelebration: C.visitorCelebration,
                settleStageSeconds: C.settleStageSeconds,
                // A wave is a late-game or dead-game thing; a 0-0 first quarter is watching the football.
                waveAllowed: s.status.period >= C.idleStandShare.aboutPeriod || CrowdActor.decided(s, C))
            if g.ring == .card {
                setPose(g, index(CrowdChoreography.pose(input).rawValue))
            } else {
                setSlot(g, CrowdChoreography.slot(input))
            }
            let dim = g.ring == .card ? C.tint.dim : C.tint.meshDim
            let bright: Double = tintSide.map { side in (side == "away") == g.away ? C.tint.bright : dim } ?? C.tint.normal
            if bright != g.brightness {
                g.brightness = bright
                g.material.baseColor.tint = UIColor(white: CGFloat(bright), alpha: 1)
                if g.ring == .card { g.material.emissiveIntensity = Float(C.impostor.floodFill * bright) }
                g.entity.model?.materials = [g.material]
            }
        }
    }

    private func setPose(_ g: Group, _ pose: Int) {
        guard pose != g.pose else { return }
        g.pose = pose
        g.material.textureCoordinateTransform = .init(offset: SIMD2(0, -Float(pose) * cardRowV), scale: SIMD2(1, 1), rotation: 0)
        g.entity.model?.materials = [g.material]
    }

    private func setSlot(_ g: Group, _ slot: CrowdChoreography.Slot) {
        guard slot != g.slot, let mesh = g.slotMeshes[slot] ?? g.slotMeshes[.sit] else { return }
        g.slot = slot
        g.entity.model?.mesh = mesh
    }

    /// Whose colours each section of the bowl wears.
    ///
    /// A home game is the home club's, overwhelmingly. The visitors get whole sections in the
    /// order a real away support fills them: the scene's own `bowl.crowd.awaySection` first, then
    /// behind their bench (their sideline, between `field.props.benches` fromX and toX), then the
    /// upper corners on that side, until `support.visitingShare` of the sections are theirs.
    /// `support.neutralShare` more, taken from the corners farthest from the visitors, wear
    /// neither club. Nothing here is assumed about which club is which: home, away and the away
    /// section all come from the scene.
    nonisolated static func supportBySection(_ s: SceneSpec, look C: SceneSpec.Look.CrowdLook,
                                             drawn: Set<String>) -> [SectionKey: Support] {
        guard let seating = s.bowl.seating else { return [:] }
        let shape = s.bowl.shape
        let visitorsFar = (s.bowl.crowd.awaySection?.side ?? "far") == "far"
        let fromX = (s.bowl.crowd.awaySection?.fromX ?? 90) - 50
        let bench = s.field.props?.benches
        let benchFrom = (bench?.fromX ?? 30) - 50, benchTo = (bench?.toX ?? 70) - 50
        let corner = Float(C.support.cornerFrom)
        var scored: [(key: SectionKey, visitor: Double, neutral: Double)] = []
        for tier in seating.tiers where drawn.contains(tier.tier) {
            let sections = tier.sections ?? []
            guard let row = tier.rows.first.map({ tier.rows[tier.rows.count / 2].length > 0 ? tier.rows[tier.rows.count / 2] : $0 }) else { continue }
            let ring = SceneMath.Ring(shape, offset: row.feet)
            for (index, sec) in sections.enumerated() {
                // The section's middle, on its tier's middle row.
                let mid = sec.to > sec.from ? (sec.from + sec.to) / 2 : ((sec.from + sec.to + 1) / 2).truncatingRemainder(dividingBy: 1)
                let t = ring.angle(at: mid * row.length)
                let p = SceneMath.bowlPoint(shape, offset: row.feet, angle: t)
                let onVisitorsSide = visitorsFar ? p.z < 0 : p.z > 0
                let cornerness = min(1, max(0, (abs(p.x) / max(1, shape.halfLength) - Double(corner)) / max(0.01, 1 - Double(corner))))
                let upper = tier.tier != C.support.benchRowsTier
                var visitor = 0.0
                if onVisitorsSide && p.x >= Double(fromX) { visitor = 1.0 }                 // the scene's own away section
                else if onVisitorsSide && !upper && p.x >= Double(benchFrom) && p.x <= Double(benchTo) { visitor = 0.8 }  // behind their bench
                else if onVisitorsSide && upper && cornerness > 0.3 { visitor = 0.6 + 0.2 * cornerness }                  // upper corners, their side
                else if onVisitorsSide { visitor = 0.2 }
                // The unaligned sit high in the corners, as far from the visitors as the bowl allows.
                let neutral = (upper ? 0.6 : 0.2) + 0.4 * cornerness - (onVisitorsSide ? 0.5 : 0)
                scored.append((SectionKey(tier: tier.tier, section: index), visitor, neutral))
            }
        }
        guard !scored.isEmpty else { return [:] }
        var out: [SectionKey: Support] = [:]
        let visiting = Int((Double(scored.count) * C.support.visitingShare).rounded())
        let neutrals = Int((Double(scored.count) * C.support.neutralShare).rounded())
        for entry in scored.sorted(by: { $0.visitor > $1.visitor }).prefix(visiting) where entry.visitor > 0 {
            out[entry.key] = .away
        }
        for entry in scored.sorted(by: { $0.neutral > $1.neutral }) where out.count < visiting + neutrals {
            if out[entry.key] == nil { out[entry.key] = .neutral }
        }
        for entry in scored where out[entry.key] == nil { out[entry.key] = .home }
        return out
    }

    /// How likely this seat is to be taken: the upper deck thinner than the lower, the corners
    /// thinner than midfield, and thinner again high up once the game is decided. The scene knows
    /// the score, the period and the clock; it knows nothing about attendance, so nothing else is inferred.
    nonisolated static func keepChance(at p: SIMD3<Float>, tier: String, look C: SceneSpec.Look.CrowdLook,
                                       spec s: SceneSpec) -> Double {
        let shape = s.bowl.shape
        let upper = tier != C.support.benchRowsTier
        var keep = upper ? C.emptySeats.upperFactor : 1
        let corner = Double(C.support.cornerFrom)
        let alongEnd = min(1, max(0, (Double(abs(p.x)) / max(1, shape.halfLength) - corner) / max(0.01, 1 - corner)))
        keep *= 1 - alongEnd * (1 - C.emptySeats.cornerFactor)
        if Double(abs(p.x)) > shape.halfLength * 0.9 { keep *= C.emptySeats.endZoneFactor }
        if decided(s, C) { keep *= upper ? C.emptySeats.blowout.upperFactor : C.emptySeats.blowout.lowerFactor }
        return keep
    }

    /// Is this game over bar the clock? Margin, period and the clock the scene carries.
    nonisolated static func decided(_ s: SceneSpec, _ C: SceneSpec.Look.CrowdLook) -> Bool {
        let b = C.emptySeats.blowout
        guard s.status.state == "in", abs(s.status.homeScore - s.status.awayScore) >= b.margin else { return false }
        if s.status.period > b.fromPeriod { return true }
        guard s.status.period == b.fromPeriod else { return false }
        return clockSeconds(s.status.clock).map { $0 <= b.clockSeconds } ?? false
    }

    /// "12:40" as seconds. The scene carries the clock as the broadcast writes it.
    nonisolated static func clockSeconds(_ clock: String) -> Double? {
        let parts = clock.split(separator: ":")
        guard parts.count == 2, let m = Double(parts[0]), let sec = Double(parts[1]) else { return nil }
        return m * 60 + sec
    }

    /// How many fans are on their feet between plays: fewer in the first half than the fourth quarter.
    nonisolated static func standingShare(_ C: SceneSpec.Look.CrowdLook, spec s: SceneSpec) -> Double {
        s.status.period >= C.idleStandShare.aboutPeriod ? C.idleStandShare.late : C.idleStandShare.early
    }

    /// A fan's left, for a fan facing `facing` with Y up: the kit's +X (MakeHuman's .L side).
    nonisolated static func leftOf(_ facing: SIMD3<Float>) -> SIMD3<Float> {
        SIMD3(facing.z, 0, -facing.x)
    }

    /// Which pose this fan wears in a near slot: drawn from `visual.crowd.nearMix` by the fan's own
    /// seat, so one group's people are not one posture; chatting pairs turn to each other in `sit`.
    nonisolated static func nearPose(_ slot: CrowdChoreography.Slot, fan: Int, row: Int, seat: Int, nextOnLeft: Bool,
                                     look C: SceneSpec.Look.CrowdLook) -> String {
        func hash(_ salt: UInt64) -> Double {
            var h = UInt64(truncatingIfNeeded: row &* 92_821 &+ seat &* 68_917 &+ fan &* 131) &+ salt &* 0x9E3779B97F4A7C15
            h ^= h >> 31; h = h &* 0xBF58476D1CE4E5B9; h ^= h >> 27
            return Double(h % 10_000) / 10_000
        }
        if slot == .sit {
            let pair = UInt64(truncatingIfNeeded: row &* 7_919 &+ (seat / 2))
            var h = pair &* 0x9E3779B97F4A7C15; h ^= h >> 29
            if Double(h % 10_000) / 10_000 < C.chatShare {
                // The even seat turns to the next seat; the odd seat back to the one before.
                let towardNext = seat % 2 == 0
                return (towardNext == nextOnLeft) ? "sit_look_l" : "sit_look_r"
            }
        }
        guard let shares = C.nearMix[slot.rawValue], !shares.isEmpty else { return slot.rawValue }
        let total = shares.reduce(0) { $0 + $1.share }
        var x = hash(slot.rawValue.utf8.reduce(UInt64(0)) { $0 &* 31 &+ UInt64($1) }) * total
        // The idle slots draw from one stream, so going between sit and sit_b only moves the fans whose draw differs.
        if slot == .sit || slot == .sitB { x = hash(1) * total }
        for s in shares {
            if x < s.share { return s.pose }
            x -= s.share
        }
        return shares[shares.count - 1].pose
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
        let q = CrowdFacing.rotation(facing: facing)
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
    /// Each fan's standing height in metres, from the kit's manifest.
    private var heights: [Float] = []

    func height(_ fan: Int) -> Float { fan < heights.count ? heights[fan] : Float(look.chair.referenceHeightMetres) }
    private let fanAlbedo: CGImage, fanMask: CGImage, cardAlbedo: CGImage, cardMask: CGImage
    var impostorSize: (width: Int, height: Int) { (cardAlbedo.width, cardAlbedo.height) }

    struct Dress {
        let fanHome: TextureResource, fanAway: TextureResource
        let cardHome: TextureResource, cardAway: TextureResource
        /// Sections wearing neither club: the scene's own `crowd.neutral` and `crowd.dark`.
        let fanNeutral: TextureResource, cardNeutral: TextureResource

        func fan(_ support: CrowdActor.Support) -> TextureResource {
            switch support {
            case .home: return fanHome
            case .away: return fanAway
            case .neutral: return fanNeutral
            }
        }

        func card(_ support: CrowdActor.Support) -> TextureResource {
            switch support {
            case .home: return cardHome
            case .away: return cardAway
            case .neutral: return cardNeutral
            }
        }
    }

    private init?(_ C: SceneSpec.Look.CrowdLook) {
        guard let folder = StadiumAssets.folder,
              let fa = StadiumAssets.image(folder.appendingPathComponent(C.kit.fanAlbedo)),
              let fm = StadiumAssets.image(folder.appendingPathComponent(C.kit.fanMask)),
              let ca = StadiumAssets.image(folder.appendingPathComponent(C.kit.impostorAlbedo)),
              let cm = StadiumAssets.image(folder.appendingPathComponent(C.kit.impostorMask)) else { return nil }
        look = C
        fanAlbedo = fa; fanMask = fm; cardAlbedo = ca; cardMask = cm
        struct Manifest: Decodable { struct Fan: Decodable { let height: Double }; let fans: [Fan] }
        if let data = try? Data(contentsOf: folder.appendingPathComponent(C.kit.manifest)),
           let m = try? JSONDecoder().decode(Manifest.self, from: data) {
            heights = m.fans.map { Float($0.height) }
        }
        for id in ["lod0Poses", "lod1Poses", "lod2Poses"] {
            guard let template = StadiumAssets.shared.model("crowd.\(id)") else { continue }
            collect(template, root: template)
        }
        for ring in [CrowdActor.Ring.lod0, .lod1, .lod2] {
            let (ok, apex) = measuredForward(ring: ring)
            let z = apex.map { String(format: "%+.3f", $0) } ?? "no probe"
            if ok {
                StadiumLog.log.notice("[stadium] crowd kit \(String(describing: ring)) faces +Z (probe apex z \(z))")
            } else {
                StadiumLog.log.error("[stadium] crowd kit \(String(describing: ring)) does not face +Z (probe apex z \(z)); every near fan is seated backwards")
            }
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

    /// A near pose, or the nearest one the kit has: an older kit without the head turns
    /// and the rise still draws its fans seated.
    func nearPoseMesh(ring: CrowdActor.Ring, fan: Int, pose: String) -> (String, CrowdPoseMesh)? {
        let fallback = ["sit_look_l": "sit", "sit_look_r": "sit", "rise": "sit_b"]
        for name in [pose, fallback[pose]].compactMap({ $0 }) {
            if let m = poseMesh(ring: ring, fan: fan, pose: name) { return (name, m) }
        }
        return nil
    }

    /// Which way the loaded kit's fans face, from the marker build.py exports beside them.
    ///
    /// The axis is a property of the export, not of anatomy: at LOD2's 250 triangles a shoe is
    /// a blob, and round 5 tucked seated feet under the chair, so every anatomical cue was a
    /// guess. The probe is one triangle whose apex points where the fans face, and nothing ever
    /// looks it up as a pose, so it is never drawn. CrowdPoseMesh.placed turns +Z onto a seat's
    /// facing, so anything else seats every near fan backwards.
    func measuredForward(ring: CrowdActor.Ring) -> (ok: Bool, apex: Float?) {
        guard let probe = meshes["forward_probe_lod\(ring.rawValue)"], probe.positions.count >= 3 else { return (false, nil) }
        let mid = probe.positions.reduce(SIMD3<Float>.zero, +) / Float(probe.positions.count)
        let apex = probe.positions.max { a, b in
            (a.x - mid.x) * (a.x - mid.x) + (a.z - mid.z) * (a.z - mid.z) <
            (b.x - mid.x) * (b.x - mid.x) + (b.z - mid.z) * (b.z - mid.z)
        }
        guard let apex else { return (false, nil) }
        return (apex.z - mid.z > 0, apex.z - mid.z)
    }

    func poseMesh(ring: CrowdActor.Ring, fan: Int, pose: String) -> CrowdPoseMesh? {
        let id = String(format: "fan%02d_lod%d_%@", fan, ring.rawValue, pose)
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
        let d = Dress(fanHome: fan, fanAway: fan, cardHome: card, cardAway: card, fanNeutral: fan, cardNeutral: card)
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
        let fanLayout = Layout.grid(cols: C.fanGrid[0], rows: C.fanGrid[1])
        let cardLayout = Self.cardLayout(C)
        let fa = Self.pixels(fanAlbedo), fm = Self.pixels(fanMask)
        let ca = Self.pixels(cardAlbedo), cm = Self.pixels(cardMask)
        func make(_ a: Pixels, _ m: Pixels, _ chip: SIMD4<Float>, _ raw: SIMD4<Float>, _ layout: Layout, away: Bool, card: Bool) -> CGImage? {
            Self.tint(a, m, chip: chip, raw: raw, palette: Palette(C, salt: away ? 2 : 1, card: card), layout: layout, divisor: 4)
        }
        let plain = plainDress()
        let d = Dress(fanHome: StadiumText.texture(make(fa, fm, home, homeRaw, fanLayout, away: false, card: false)) ?? plain.fanHome,
                      fanAway: StadiumText.texture(make(fa, fm, away, awayRaw, fanLayout, away: true, card: false)) ?? plain.fanAway,
                      cardHome: StadiumText.texture(make(ca, cm, home, homeRaw, cardLayout, away: false, card: true)) ?? plain.cardHome,
                      cardAway: StadiumText.texture(make(ca, cm, away, awayRaw, cardLayout, away: true, card: true)) ?? plain.cardAway,
                      fanNeutral: plain.fanNeutral, cardNeutral: plain.cardNeutral)
        quick[key] = d
        return d
    }

    private static func key(_ s: SceneSpec, _ C: SceneSpec.Look.CrowdLook) -> String {
        "\(s.bowl.crowd.home)|\(s.bowl.crowd.away)|\(s.teams.home.color)|\(s.teams.away.color)|\(C.secondary)|\(C.rawShare)|\(C.shirtShade)|\(C.clubLuma)|\(C.neutralShare)|\(C.neutrals)|\(C.desaturate)|\(C.cardContrast)"
    }

    func cachedDress(for s: SceneSpec, look: SceneSpec.Look) -> Dress? {
        Self.dressCache[Self.key(s, look.crowd)]
    }

    private struct Images: @unchecked Sendable {
        let fanHome: CGImage?, fanAway: CGImage?, cardHome: CGImage?, cardAway: CGImage?
        let fanNeutral: CGImage?, cardNeutral: CGImage?
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
        // Neither club: the scene's own neutral and dark crowd colours.
        let neutral = SceneMath.rgba(s.palette[s.bowl.crowd.neutral] ?? s.bowl.crowd.neutral)
        let neutralRaw = SceneMath.rgba(s.palette[s.bowl.crowd.dark] ?? s.bowl.crowd.dark)
        let src = Sources(fanAlbedo: fanAlbedo, fanMask: fanMask, cardAlbedo: cardAlbedo, cardMask: cardMask)
        let fanLayout = Layout.grid(cols: C.fanGrid[0], rows: C.fanGrid[1])
        let cardLayout = Self.cardLayout(C)
        let homeFan = Palette(C, salt: 1, card: false), awayFan = Palette(C, salt: 2, card: false)
        let homeCard = Palette(C, salt: 1, card: true), awayCard = Palette(C, salt: 2, card: true)
        let neutralFan = Palette(C, salt: 3, card: false), neutralCard = Palette(C, salt: 3, card: true)
        let started = Date()
        Task.detached(priority: .userInitiated) {
            let fa = CrowdKit.pixels(src.fanAlbedo), fm = CrowdKit.pixels(src.fanMask)
            let ca = CrowdKit.pixels(src.cardAlbedo), cm = CrowdKit.pixels(src.cardMask)
            let decoded = Date()
            // The away section is always across the bowl, so its copies are
            // composed at half size: it keeps the crowd inside its 60 MB.
            let images = Images(
                fanHome: CrowdKit.tint(fa, fm, chip: home, raw: homeRaw, palette: homeFan, layout: fanLayout, divisor: 1),
                fanAway: CrowdKit.tint(fa, fm, chip: away, raw: awayRaw, palette: awayFan, layout: fanLayout, divisor: 2),
                cardHome: CrowdKit.tint(ca, cm, chip: home, raw: homeRaw, palette: homeCard, layout: cardLayout, divisor: 1),
                cardAway: CrowdKit.tint(ca, cm, chip: away, raw: awayRaw, palette: awayCard, layout: cardLayout, divisor: 2),
                // The unaligned sit highest and farthest of anyone: a quarter is plenty, and it keeps
                // both the crowd's texture budget and the time it takes to dress where round 4 left them.
                fanNeutral: CrowdKit.tint(fa, fm, chip: neutral, raw: neutralRaw, palette: neutralFan, layout: fanLayout, divisor: 4),
                cardNeutral: CrowdKit.tint(ca, cm, chip: neutral, raw: neutralRaw, palette: neutralCard, layout: cardLayout, divisor: 4))
            let tinted = Date()
            await MainActor.run {
                let hop = Date()
                let plain = self.plainDress()
                let d = Dress(fanHome: StadiumText.texture(images.fanHome) ?? plain.fanHome,
                              fanAway: StadiumText.texture(images.fanAway) ?? plain.fanAway,
                              cardHome: StadiumText.texture(images.cardHome) ?? plain.cardHome,
                              cardAway: StadiumText.texture(images.cardAway) ?? plain.cardAway,
                              fanNeutral: StadiumText.texture(images.fanNeutral) ?? plain.fanNeutral,
                              cardNeutral: StadiumText.texture(images.cardNeutral) ?? plain.cardNeutral)
                Self.dressCache[key] = d
                let f = { (a: Date, b: Date) in String(format: "%.2f", b.timeIntervalSince(a)) }
                StadiumLog.log.notice("[stadium] crowd dress composed in \(f(started, Date())) s (decode \(f(started, decoded)), tint \(f(decoded, tinted)), main-actor wait \(f(tinted, hop)), textures \(f(hop, Date())))")
                done(d)
            }
        }
    }

    nonisolated static func cardLayout(_ C: SceneSpec.Look.CrowdLook) -> Layout {
        .blocks(perRow: C.impostor.blocksPerRow,
                w: C.impostor.cellPixels[0] * C.impostor.blockCells[0],
                h: C.impostor.cellPixels[1] * C.impostor.blockCells[1],
                cellW: C.impostor.cellPixels[0])
    }

    /// Where each fan's pixels are in an atlas.
    enum Layout: Sendable {
        case grid(cols: Int, rows: Int)
        /// Impostor blocks whose cells hold two fans: `cellW` px wide, fan on the left half, mate on the right.
        case blocks(perRow: Int, w: Int, h: Int, cellW: Int)

        /// How many independently dressed people the atlas holds per fan block.
        var people: Int { if case .blocks = self { return 2 } else { return 1 } }

        func rect(_ fan: Int, width: Int, height: Int) -> (x: Int, y: Int, w: Int, h: Int) {
            switch self {
            case .grid(let cols, let rows):
                return (fan % cols * width / cols, fan / cols * height / rows, width / cols, height / rows)
            case .blocks(let perRow, let w, let h, _):
                return (fan % perRow * w, fan / perRow * h, w, h)
            }
        }
    }

    /// Unpremultiply, grow colour into transparent texels `passes` times, and
    /// wrap it as a straight-alpha image (CGContext cannot hold one; CGImage can).
    /// An atlas's decoded RGBA bytes, row 0 at the top, read in place.
    ///
    /// No copy: at -Onone a byte loop over four atlases cost three seconds
    /// before a single texel was tinted. visionOS's ImageIO hands a PNG with
    /// alpha over premultiplied (macOS hands the same file over straight), so
    /// `premultiplied` says which, and `tint` handles both.
    struct Pixels: @unchecked Sendable {
        let width: Int, height: Int
        let stride: Int
        let data: CFData
        let premultiplied: Bool
        let alpha: Bool
    }

    nonisolated static func pixels(_ img: CGImage) -> Pixels {
        let W = img.width, H = img.height
        let info = img.alphaInfo
        let order = img.bitmapInfo.intersection(.byteOrderMask)
        let rgbaOrder = order == [] || order == .byteOrder32Big
        let layouts: [CGImageAlphaInfo] = [.last, .premultipliedLast, .noneSkipLast]
        if img.bitsPerComponent == 8, img.bitsPerPixel == 32, rgbaOrder, layouts.contains(info),
           let data = img.dataProvider?.data, CFDataGetLength(data) >= img.bytesPerRow * H {
            return Pixels(width: W, height: H, stride: img.bytesPerRow, data: data,
                          premultiplied: info == .premultipliedLast, alpha: info != .noneSkipLast)
        }
        StadiumLog.log.notice("[stadium] crowd atlas drawn to a bitmap (alpha \(info.rawValue), \(img.bitsPerPixel) bpp, order \(order.rawValue))")
        let out = NSMutableData(length: W * H * 4)!
        if let ctx = CGContext(data: out.mutableBytes, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4,
                               space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) {
            ctx.interpolationQuality = .none
            ctx.draw(img, in: CGRect(x: 0, y: 0, width: W, height: H))
        }
        return Pixels(width: W, height: H, stride: W * 4, data: out as CFData, premultiplied: true, alpha: true)
    }

    /// albedo x chip through the mask. Each fan gets its own shade of the
    /// chip, and some wear the raw club colour, so a section is mottled.
    /// How a side dresses: which fans wear neutrals, and how far each club colour wanders.
    struct Palette: Sendable {
        let secondary: SIMD4<Float>
        let fans: Int
        let rawShare: Float
        let shade: (Float, Float)
        let neutralShare: Float
        let neutrals: [SIMD4<Float>]
        let desaturate: (Float, Float)
        let luma: (Float, Float)
        /// 1 keeps the kit's contrast; less pulls each fan toward its own mean.
        let contrast: Float
        let salt: UInt64

        init(_ C: SceneSpec.Look.CrowdLook, salt: UInt64, card: Bool) {
            secondary = SceneMath.rgba(C.secondary)
            fans = C.fans
            rawShare = Float(C.rawShare)
            shade = (Float(C.shirtShade[0]), Float(C.shirtShade[1]))
            neutralShare = Float(C.neutralShare)
            neutrals = C.neutrals.map { SceneMath.rgba($0) }
            desaturate = (Float(C.desaturate[0]), Float(C.desaturate[1]))
            luma = (Float(C.clubLuma.min), Float(C.clubLuma.max))
            contrast = card ? Float(C.cardContrast) : 1
            self.salt = salt
        }
    }

    /// One side's copy of an atlas, `divisor` times smaller.
    ///
    /// Written for a Debug build as much as a Release one: the look-dev
    /// harness runs -Onone, where SIMD and closures in a per-texel loop cost
    /// 25 s for four atlases. So the inner loop is scalar Float over raw
    /// buffers, and fans are composed in parallel - every texel belongs to
    /// exactly one person's rect (or half of a pair cell), so the writes never
    /// overlap. Every texel is tinted, transparent ones too, so the padding
    /// build.py grew around each figure wears the same colour as the figure.
    nonisolated static func tint(_ albedo: Pixels, _ mask: Pixels, chip: SIMD4<Float>, raw: SIMD4<Float>,
                                 palette P: Palette, layout: Layout, divisor k: Int) -> CGImage? {
        let W = albedo.width / k, H = albedo.height / k
        guard W > 0, H > 0, mask.width > 0, mask.height > 0 else { return nil }
        let people = layout.people
        var cellW = 0
        if case .blocks(_, _, _, let w) = layout { cellW = w / k }
        let persons = P.fans * people
        // Per person: the colour they wear (r, g, b) and whether they are a pair cell's right half.
        var colours = [Float](repeating: 0, count: persons * 3)
        for person in 0..<persons {
            // Salted per side, so the home and away stands put neutrals on different fans.
            var h = UInt64(person) &* 2654435761 &+ 97 &+ P.salt &* 40503
            h ^= h >> 13
            h = h &* 0x9E3779B97F4A7C15
            h ^= h >> 29
            let r1 = Float(h % 1000) / 1000, r2 = Float((h / 1000) % 1000) / 1000
            let r3 = Float((h / 1_000_000) % 1000) / 1000, r4 = Float((h / 1_000_000_000) % 1000) / 1000
            let wearsNeutral = r3 < P.neutralShare && !P.neutrals.isEmpty
            var colour = wearsNeutral ? P.neutrals[Int(r4 * Float(P.neutrals.count)) % P.neutrals.count]
                                      : (r2 < P.rawShare ? raw : chip)
            colour *= P.shade.0 + (P.shade.1 - P.shade.0) * r1
            if !wearsNeutral {
                // Into the club luma band first, so the shade below still mottles within it.
                let y = max(1e-4, colour.x * 0.2126 + colour.y * 0.7152 + colour.z * 0.0722)
                let target = min(P.luma.1, max(P.luma.0, y))
                let lift = target / y
                colour = SIMD4(min(1, colour.x * lift), min(1, colour.y * lift), min(1, colour.z * lift), colour.w)
                let d = P.desaturate.0 + (P.desaturate.1 - P.desaturate.0) * r4
                let l = colour.x * 0.2126 + colour.y * 0.7152 + colour.z * 0.0722
                colour = colour + (SIMD4(l, l, l, colour.w) - colour) * d
            }
            colours[person * 3] = colour.x; colours[person * 3 + 1] = colour.y; colours[person * 3 + 2] = colour.z
        }
        let sr = P.secondary.x, sg = P.secondary.y, sb = P.secondary.z
        let contrast = P.contrast
        let cards = people > 1
        let AS = albedo.stride, MS = mask.stride, MW = mask.width, MH = mask.height
        let AW = albedo.width, AH = albedo.height
        let premultiplied = albedo.premultiplied, opaque = !albedo.alpha
        var out = [UInt8](repeating: 0, count: W * H * 4)
        colours.withUnsafeBufferPointer { cols in
        out.withUnsafeMutableBufferPointer { o in
            // Disjoint writes from many threads: the pointers cross into
            // concurrentPerform as one unchecked-Sendable bundle.
            struct Buffers: @unchecked Sendable {
                let o: UnsafeMutablePointer<UInt8>, a: UnsafePointer<UInt8>, m: UnsafePointer<UInt8>, c: UnsafePointer<Float>
            }
            let B = Buffers(o: o.baseAddress!, a: CFDataGetBytePtr(albedo.data), m: CFDataGetBytePtr(mask.data), c: cols.baseAddress!)
            // Texels outside every person's rect (a grid's rounding remainder) keep the kit's colour.
            DispatchQueue.concurrentPerform(iterations: H) { y in
                let oBase = B.o, aBase = B.a
                let row = aBase + min(AH - 1, y * k) * AS
                if k == 1 && W <= AW {
                    // Full size: one library copy a row, not four byte stores a texel at -Onone.
                    (oBase + y * W * 4).update(from: row, count: W * 4)
                    return
                }
                for x in 0..<W {
                    let s = min(AW - 1, x * k) * 4, d = (y * W + x) * 4
                    oBase[d] = row[s]; oBase[d + 1] = row[s + 1]; oBase[d + 2] = row[s + 2]; oBase[d + 3] = opaque ? 255 : row[s + 3]
                }
            }
            DispatchQueue.concurrentPerform(iterations: persons) { person in
                let oBase = B.o, mBase = B.m, cBase = B.c
                let fan = person / people
                let right = person % people != 0
                var (x0, y0, w, h0) = layout.rect(fan, width: AW, height: AH)
                x0 /= k; y0 /= k; w /= k; h0 /= k
                let xs = max(0, x0), xe = min(W, x0 + w), ys = max(0, y0), ye = min(H, y0 + h0)
                guard xs < xe, ys < ye else { return }
                let pr = cBase[person * 3], pg = cBase[person * 3 + 1], pb = cBase[person * 3 + 2]
                // Cards: this person's mean colour, straight. Contrast pulls their flecks
                // toward it, and it fills the transparent texels around them.
                var mr0: Float = 0, mg0: Float = 0, mb0: Float = 0
                if cards {
                    var n: Float = 0
                    for y in Swift.stride(from: ys, to: ye, by: 2) {
                        for x in Swift.stride(from: xs, to: xe, by: 2) {
                            if cellW > 0 && (((x - x0) % cellW) >= cellW / 2) != right { continue }
                            let d = (y * W + x) * 4
                            let a = oBase[d + 3]
                            guard a > 127 else { continue }
                            let u: Float = premultiplied ? 255 / Float(a) : 1
                            mr0 += Float(oBase[d]) * u; mg0 += Float(oBase[d + 1]) * u; mb0 += Float(oBase[d + 2]) * u; n += 1
                        }
                    }
                    let inv = 1 / (255 * max(1, n))
                    mr0 *= inv; mg0 *= inv; mb0 *= inv
                }
                let inv255: Float = 1 / 255
                // Premultiplied cards lose every transparent texel's colour; those
                // are filled after the figure with the figure's own tinted mean.
                let fill = cards && premultiplied
                var tr: Float = 0, tg: Float = 0, tb: Float = 0, tn: Float = 0
                for y in ys..<ye {
                    let mrow = mBase + min(MH - 1, (y * k) * MH / AH) * MS
                    for x in xs..<xe {
                        if cards && cellW > 0 && (((x - x0) % cellW) >= cellW / 2) != right { continue }
                        let d = (y * W + x) * 4
                        let a = oBase[d + 3]
                        if fill && a == 0 { continue }
                        let mi = min(MW - 1, (x * k) * MW / AW) * 4
                        var mr = Float(mrow[mi]) * inv255, mg = Float(mrow[mi + 1]) * inv255, mb = Float(mrow[mi + 2]) * inv255
                        if mask.premultiplied {
                            let ma = Float(mrow[mi + 3])
                            if ma > 0 && ma < 255 { mr *= 255 / ma; mg *= 255 / ma; mb *= 255 / ma }
                        }
                        let tinted = mr + mg + mb > 0.004
                        if !tinted && contrast >= 1 && !fill { continue }
                        let u: Float = premultiplied && a > 0 ? 1 / Float(a) : inv255
                        var r = Float(oBase[d]) * u, g = Float(oBase[d + 1]) * u, b = Float(oBase[d + 2]) * u
                        if contrast < 1 {
                            r = mr0 + (r - mr0) * contrast; g = mg0 + (g - mg0) * contrast; b = mb0 + (b - mb0) * contrast
                        }
                        if tinted {
                            r *= (1 + (pr - 1) * mr) * (1 + (sr - 1) * mg)
                            g *= (1 + (pg - 1) * mr) * (1 + (sg - 1) * mg)
                            b *= (1 + (pb - 1) * mr) * (1 + (sb - 1) * mg)
                            r += (pr * 0.86 - r) * mb; g += (pg * 0.86 - g) * mb; b += (pb * 0.86 - b) * mb
                        }
                        r = max(0, min(1, r)); g = max(0, min(1, g)); b = max(0, min(1, b))
                        if fill && a > 127 { tr += r; tg += g; tb += b; tn += 1 }
                        oBase[d] = UInt8(r * 255); oBase[d + 1] = UInt8(g * 255); oBase[d + 2] = UInt8(b * 255)
                    }
                }
                if fill && tn > 0 {
                    let fr = UInt8(tr / tn * 255), fg = UInt8(tg / tn * 255), fb = UInt8(tb / tn * 255)
                    for y in ys..<ye {
                        for x in xs..<xe {
                            if cellW > 0 && (((x - x0) % cellW) >= cellW / 2) != right { continue }
                            let d = (y * W + x) * 4
                            if oBase[d + 3] == 0 { oBase[d] = fr; oBase[d + 1] = fg; oBase[d + 2] = fb }
                        }
                    }
                }
            }
        }
        }
        guard let provider = CGDataProvider(data: Data(out) as CFData) else { return nil }
        return CGImage(width: W, height: H, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: W * 4,
                       space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: (opaque ? CGImageAlphaInfo.noneSkipLast : CGImageAlphaInfo.last).rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }

}
