import CoreGraphics
import ImageIO
import RealityKit
import SwiftUI

/// Your own hall of fame, built out of your own seven seasons.
///
/// The other immersive space in this app places flat panels in the wearer's
/// real room. This one is a *place*: a stone rotunda with a ring of lit
/// alcoves, an arcade of piers and arches, a dome with an oculus over it, and
/// ten bronze busts on plinths. Every surface is generated - see
/// `HallGeometry.swift` - because this repository checks in no binary assets,
/// and the only imagery is the player headshots the read API already serves.
///
/// ## Not Canton
///
/// This is deliberately not a model of the Pro Football Hall of Fame and does
/// not use its name or marks. The building's trade dress is protected and this
/// is meant to become a product. What is borrowed is the *vocabulary* a
/// visitor recognises - rotunda, plinth, bronze, alcove, gallery ring - and
/// the thing standing in it is the wearer's own league history, which is a
/// better idea anyway: nobody needs a worse copy of a building they can visit.
///
/// ## Who gets a plinth
///
/// `Hall.swift` decides, and it decides from records rather than from a vibe.
/// Four wings - highest positional finish, biggest single week, furthest past
/// his ADP, most weeks scored - each ranked on its own number, filled
/// round-robin so the first four busts are the four wing leaders. The plinth
/// says which record earned it, what the number was, and what field it was
/// measured against. A man with no claim gets no bust and his alcove holds a
/// bare plinth, because an empty plinth is true and a filled one would not be.
///
/// ## The fourth dimension
///
/// "4D" read as time, and made real rather than said. The database holds seven
/// seasons; the bronze dial in the middle of the floor walks the wearer
/// through them, and each one inducts a different ten men off that season's
/// own records. 2026 has been drafted but not played, so its hall is almost
/// entirely the steal wing - which is the correct thing for it to be, and is
/// the sort of fact a room can tell you faster than a table.
///
/// ## The frame budget
///
/// A headset redraws this ninety times a second per eye. Three rules, all of
/// which the previous immersive space learned the hard way:
///
///   * Every mesh is generated once in `build` and shared. Ten plinths point
///     at one cylinder and ten busts at one solid of revolution.
///   * `update:` never adds or removes an entity. It re-dresses the ones that
///     are already there - enabling a bust, swapping a material, moving an
///     attachment. Tearing the graph down and rebuilding it each tick is what
///     froze the board.
///   * The portraits arrive one at a time on a detached task, so the room is
///     walkable while it fills. Ten simultaneous 1024px decodes on the main
///     actor is a visible hitch at exactly the moment the wearer arrives.
struct HallOfFame: View {
    @Environment(Board.self) private var board
    @Environment(\.dismissImmersiveSpace) private var dismissImmersive
    @Environment(\.openWindow) private var openWindow

    /// Entity handles, held across passes so `update:` can re-dress rather
    /// than rebuild. A plain class, not `@Observable`: nothing in SwiftUI
    /// should redraw because a material changed.
    @State private var stage = Stage()
    @State private var era: Hall.Era = .allTime
    @State private var inductees: [Hall.Inductee] = []
    @State private var detailID: String?
    @State private var loading = true

    // MARK: - the room, in metres

    private static let bays = 10
    private let arcadeR: Float = 3.90
    private let wallR: Float = 4.95
    private let wallH: Float = 3.62
    private let pierH: Float = 2.30
    private let plinthR: Float = 4.30
    private let eyeHeight: Float = 1.35

    private var step: Float { 2 * .pi / Float(Self.bays) }

    /// The portrait is 0.84 m across and a wearer reads a plinth from about
    /// 1.6 m. visionOS renders a point at 1/1360 of a metre, so that is the
    /// apparent size of 561 points; `Art.width` triples it for headroom and
    /// caps at 1024, which is where this lands. That is the largest ESPN's
    /// combiner is asked for anywhere in this app, and it is right that it is:
    /// a bust is the biggest a portrait is ever drawn here. Asking for the
    /// bare 600px path instead - which is what every other surface used to do
    /// - would have been a visible upscale on a face at arm's length.
    private static let cameoPoints: CGFloat = 0.84 * 1360 / 1.6

    var body: some View {
        RealityView { content, attachments in
            let root = stage.root
            root.name = "hall"
            content.add(root)
            await build(root)
            dress(attachments)
        } update: { _, attachments in
            // Idempotent by construction. Nothing here allocates a mesh, a
            // material or an entity - it moves and enables what `build` made.
            dress(attachments)
        } attachments: {
            ForEach(0..<Self.bays, id: \.self) { i in
                Attachment(id: "plate-\(i)") { plate(i) }
            }
            Attachment(id: "dial") { dial }
            Attachment(id: "frieze") { frieze }
            if let id = detailID {
                Attachment(id: "detail") {
                    PlayerHologram(id: id, cell: nil) { detailID = nil }
                        .frame(width: 900, height: 640)
                        .glassBackgroundEffect(in: .rect(cornerRadius: 34))
                }
            }
        }
        // The bust itself is the target, not the plate: a tap in a headset is
        // a gaze plus a pinch and it lands where the wearer was looking, which
        // in a hall is the face.
        .gesture(
            SpatialTapGesture().targetedToAnyEntity().onEnded { hit in
                guard let n = hit.entity.name.split(separator: "-").last,
                      let i = Int(n), i < inductees.count else { return }
                let id = inductees[i].id
                detailID = (detailID == id) ? nil : id
            }
        )
        .task { await open() }
        // TEMPORARY-HALL-TOUR
        .task {
            try? await Task.sleep(for: .seconds(22))
            stage.root.orientation = simd_quatf(angle: 0.55, axis: [0, 1, 0])
            try? await Task.sleep(for: .seconds(10))
            era = .season(2026)
            try? await Task.sleep(for: .seconds(12))
            stage.root.orientation = simd_quatf(angle: 0, axis: [0, 1, 0])
            era = .allTime
            board.hallStyle = .mixed
        }
        // END-TEMPORARY-HALL-TOUR
        .onChange(of: era) { _, _ in reinduct() }
        .onDisappear { board.stop() }
    }

    // MARK: - loading

    /// Read every man the wearer rosters, then induct.
    ///
    /// `board.profile(_:)` is already memoised, so a second visit to the hall
    /// is free. The first is 39 season logs; they are fetched a few at a time
    /// rather than all at once because the read API is a single Python process
    /// on somebody's Mac and forty simultaneous connections is how you make a
    /// local server look like a broken one.
    private func open() async {
        board.start()
        await board.loadPrefs()
        if board.roster.isEmpty { await board.loadContext() }
        let ids = board.roster.map(\.id)
        var got: [Profile] = []
        var i = 0
        while i < ids.count {
            let slice = ids[i..<min(i + 4, ids.count)]
            await withTaskGroup(of: Profile?.self) { g in
                for id in slice { g.addTask { @MainActor in await board.profile(id) } }
                for await p in g { if let p { got.append(p) } }
            }
            i += 4
        }
        stage.profiles = got
        loading = false
        reinduct()
    }

    private func reinduct() {
        inductees = Hall.induct(stage.profiles, era: era, bays: Self.bays)
        Task { await loadPortraits(inductees) }
    }

    /// One portrait at a time, so the hall fills while you are standing in it.
    ///
    /// A blocking pass over ten 1024px PNGs - download, decode, upload to the
    /// GPU - is roughly a second of dropped frames on arrival. Sequential with
    /// a breath between each means the wearer sees bronze armatures and then
    /// watches the faces appear, which is a better arrival anyway.
    private func loadPortraits(_ men: [Hall.Inductee]) async {
        for (i, man) in men.enumerated() {
            if Task.isCancelled { return }
            if let hit = stage.textures[man.id] { apply(hit, to: i); continue }
            guard let url = Art.at(man.img, points: Self.cameoPoints)
                    ?? Art.headshot(id: man.id, points: Self.cameoPoints)
            else { continue }
            guard let (data, _) = try? await URLSession.shared.data(from: url),
                  let src = CGImageSourceCreateWithData(data as CFData, nil),
                  let cg = CGImageSourceCreateImageAtIndex(src, 0, nil),
                  let bronzed = HallMaterial.duotone(cg),
                  let tex = try? await TextureResource(
                    image: bronzed, options: .init(semantic: .color))
            else { continue }
            stage.textures[man.id] = tex
            apply(tex, to: i)
            try? await Task.sleep(for: .milliseconds(50))
        }
    }

    @MainActor
    private func apply(_ tex: TextureResource, to bay: Int) {
        guard bay < stage.bays.count else { return }
        let b = stage.bays[bay]
        b.cameo.model?.materials = [HallMaterial.cast(tex)]
        b.cameo.isEnabled = true
    }

    // MARK: - building the room, once

    private func build(_ root: Entity) async {
        guard !stage.built else { return }
        stage.built = true

        // The light. Bronze is metallic 1.0, which means it has no colour of
        // its own and is nothing but a reflection of this: without it every
        // bust in the room renders black.
        if let env = await HallLight.environment() {
            root.components.set(ImageBasedLightComponent(source: .single(env),
                                                         intensityExponent: 2.1))
            root.components.set(ImageBasedLightReceiverComponent(imageBasedLight: root))
        }

        // Meshes, generated once and shared by everything that wants one.
        let m = Meshes(arcadeR: arcadeR, wallR: wallR, wallH: wallH,
                       pierH: pierH, bays: Self.bays)
        let stoneLight = HallMaterial.stone(0.34, rough: 0.66)
        // The vault takes almost nothing from an image-based light aimed down
        // at it, so without a little emission of its own the whole upper half
        // of the room renders as void and the arcade appears to hold up
        // nothing. This is the smallest amount that makes it a surface.
        var vault = HallMaterial.stone(0.40, rough: 0.85)
        vault.emissiveColor = .init(color: UIColor(red: 0.42, green: 0.34,
                                                   blue: 0.26, alpha: 1))
        vault.emissiveIntensity = 0.10
        let stoneDark = HallMaterial.stone(0.16, rough: 0.80)
        let bronze = HallMaterial.bronze
        let patina = HallMaterial.patina
        let glow = HallMaterial.glow()

        let arch = Entity()
        arch.name = "architecture"
        root.addChild(arch)
        stage.architecture = arch

        // Floor, and the two bronze rings set into it. The inner one is the
        // dial's kerb; the outer marks where the arcade stands.
        let floor = ModelEntity(mesh: m.floorSlab, materials: [stoneDark])
        floor.position = [0, -0.05, 0]
        arch.addChild(floor)
        for (mesh, mat, y) in [(m.medallion, bronze, Float(0.005)),
                               (m.kerb, bronze, Float(0.006)),
                               (m.arcadeLine, bronze, Float(0.006))] {
            let e = ModelEntity(mesh: mesh, materials: [mat])
            e.position = [0, y, 0]
            arch.addChild(e)
        }

        // The ambulatory's outer wall - the surface the busts are seen
        // against, and the only thing in the room that is nearly black.
        let wall = ModelEntity(mesh: m.outerWall, materials: [stoneDark])
        arch.addChild(wall)

        // The entablature above the arches, the ceiling of the ambulatory,
        // and the dome over the middle.
        let band = ModelEntity(mesh: m.entablature, materials: [vault])
        band.position = [0, pierH + 1.05, 0]
        arch.addChild(band)
        let cornice = ModelEntity(mesh: m.cornice, materials: [vault])
        cornice.position = [0, pierH + 1.32, 0]
        arch.addChild(cornice)
        let dome = ModelEntity(mesh: m.dome, materials: [vault])
        dome.position = [0, pierH + 1.32, 0]
        // Squashed, because a true hemisphere on a 3.7 m springing line puts
        // the apex seven metres up and the room turns into a silo.
        dome.scale = [1, 0.62, 1]
        arch.addChild(dome)
        let collar = ModelEntity(mesh: m.oculusRing, materials: [bronze])
        collar.position = [0, pierH + 1.32 + m.oculusHeight * 0.62, 0]
        arch.addChild(collar)
        // The daylight the room is nominally lit by, so the oculus is a hole
        // onto something rather than onto the void.
        let sky = ModelEntity(mesh: m.oculusDisc, materials: [HallMaterial.glow(2.6)])
        sky.position = [0, pierH + 1.32 + m.oculusHeight * 0.62 + 0.06, 0]
        arch.addChild(sky)

        // Ten bays: a pier on each side, an arch over, a lit wall behind, and
        // a plinth in the middle of it.
        for i in 0..<Self.bays {
            let angle = Float(i) * step

            // Piers sit on the bay boundaries, so bay i is flanked by the
            // piers at i ± a half step. Drawn once per bay at the leading edge
            // and the ring closes itself.
            let pier = ModelEntity(mesh: m.pier, materials: [stoneLight])
            let pa = angle + step / 2
            pier.position = [-sin(pa) * arcadeR, pierH / 2, -cos(pa) * arcadeR]
            pier.orientation = simd_quatf(angle: pa, axis: [0, 1, 0])
            arch.addChild(pier)

            let ring = ModelEntity(mesh: m.arch, materials: [stoneLight])
            ring.position = [-sin(angle) * arcadeR, pierH, -cos(angle) * arcadeR]
            ring.orientation = simd_quatf(angle: angle, axis: [0, 1, 0])
            arch.addChild(ring)

            let bay = Entity()
            bay.name = "bay-\(i)"
            bay.orientation = simd_quatf(angle: angle, axis: [0, 1, 0])
            root.addChild(bay)

            // The alcove light: an emissive panel on the wall behind the bust
            // rather than ten shadow-casting spot lights, which at ninety
            // frames a second per eye is not a trade worth making.
            let lit = ModelEntity(mesh: m.alcoveGlow, materials: [glow])
            lit.position = [0, 1.70, -(wallR - 0.05)]
            bay.addChild(lit)

            let base = ModelEntity(mesh: m.plinthBase, materials: [stoneLight])
            base.position = [0, 0.07, -plinthR]
            bay.addChild(base)
            let shaft = ModelEntity(mesh: m.plinthShaft, materials: [stoneLight])
            shaft.position = [0, 0.59, -plinthR]
            bay.addChild(shaft)
            let cap = ModelEntity(mesh: m.plinthCap, materials: [stoneLight])
            cap.position = [0, 1.09, -plinthR]
            bay.addChild(cap)

            let bust = ModelEntity(mesh: m.bust, materials: [patina])
            bust.position = [0, 1.14, -plinthR]
            bay.addChild(bust)

            let cameo = ModelEntity(mesh: m.cameo, materials: [patina])
            cameo.position = [0, 0.30, 0.13]
            cameo.isEnabled = false
            bust.addChild(cameo)

            // One collision box for the whole plinth, on an entity named for
            // the bay, so a tap anywhere on the man opens him in depth.
            let target = Entity()
            target.name = "hit-\(i)"
            target.position = [0, 0.95, -plinthR]
            target.components.set(CollisionComponent(
                shapes: [.generateBox(width: 0.8, height: 1.9, depth: 0.8)]))
            target.components.set(InputTargetComponent())
            bay.addChild(target)

            stage.bays.append(Bay(group: bay, bust: bust, cameo: cameo,
                                  plinth: shaft, light: lit))
        }
    }

    // MARK: - dressing it, every pass

    private func dress(_ attachments: RealityViewAttachments) {
        // Mixed keeps the wearer's room, so the architecture goes away and
        // what is left is the gallery ring as a scale model standing on their
        // floor. A four-metre stone rotunda in a living room is not a
        // compromise between the two, it is a wall through the sofa.
        let scaled = board.hallStyle != .full
        stage.architecture?.isEnabled = !scaled
        stage.root.scale = scaled ? .init(repeating: 0.42) : .one
        stage.root.position = [0, scaled ? eyeHeight - 0.42 * 1.42 : 0, 0]

        for (i, bay) in stage.bays.enumerated() {
            let man = i < inductees.count ? inductees[i] : nil
            bay.bust.isEnabled = man != nil
            bay.light.isEnabled = man != nil && !scaled
            if man == nil { bay.cameo.isEnabled = false }
            if let e = attachments.entity(for: "plate-\(i)") {
                if e.parent !== bay.group { bay.group.addChild(e) }
                e.position = [0, 0.66, -(plinthR - 0.36)]
                e.isEnabled = man != nil
            }
        }
        pin("dial", attachments, [0, 0.76, -1.28], pitch: 0.42)
        pin("frieze", attachments, [0, 2.56, -(arcadeR - 0.30)])
        pin("detail", attachments, [0, eyeHeight + 0.05, -2.05])
    }

    private func pin(_ id: String, _ attachments: RealityViewAttachments,
                     _ p: SIMD3<Float>, pitch: Float = 0) {
        guard let e = attachments.entity(for: id) else { return }
        if e.parent !== stage.root { stage.root.addChild(e) }
        e.position = p
        // Assigned unconditionally, for the reason the other space records:
        // skipping a zero rotation leaves a panel wearing whatever it was
        // turned to last time it was placed.
        e.orientation = simd_quatf(angle: pitch, axis: [1, 0, 0])
    }

    // MARK: - the flat type, where flat type belongs

    /// Points per unit at this distance.
    ///
    /// A plate stands 3.96 m away. The other immersive space measured its own
    /// scale against the window - a 330pt cell at 1.9 m - and everything here
    /// is that, carried out to four metres: `1.6 × 3.96/1.9`. Set at the
    /// window's sizes a plinth would be a smudge, which is exactly what the
    /// first version of the other space was.
    private let plateScale: CGFloat = 1.6 * 3.94 / 1.9
    private func p(_ v: CGFloat) -> CGFloat { v * plateScale }
    /// The dial is a metre and a bit away, so it needs far less.
    private func d(_ v: CGFloat) -> CGFloat { v * 1.6 * 1.42 / 1.9 }

    /// The plaque under a bust: who, what he did, and out of what.
    ///
    /// Ink and opaque chips, like everywhere else in this app. A bronze-lit
    /// room is a harder backdrop than glass and colour carries no word here
    /// either - the wing is a filled chip with a glyph on it, the record is in
    /// ink, and `apple/contrast_check.py` still governs the fills.
    @ViewBuilder
    private func plate(_ i: Int) -> some View {
        if i < inductees.count {
            let man = inductees[i]
            VStack(alignment: .leading, spacing: p(6)) {
                HStack(spacing: p(7)) {
                    Chip(text: man.pos.uppercased(),
                         fill: Theme.positionFill(man.pos), size: p(10))
                    Text(man.team.uppercased())
                        .font(.system(size: p(11), weight: .heavy)).kerning(1.2)
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                    Label(man.honour.wing, systemImage: man.honour.glyph)
                        .font(.system(size: p(10), weight: .heavy)).kerning(1.1)
                        .foregroundStyle(.secondary)
                }
                Text(man.name)
                    .font(.system(size: p(24), weight: .bold))
                    .lineLimit(1).minimumScaleFactor(0.7)
                Text(man.headline)
                    .font(.system(size: p(17), weight: .semibold))
                    .monospacedDigit()
                    .fixedSize(horizontal: false, vertical: true)
                Text(man.detail)
                    .font(.system(size: p(12)))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                // The rank inside the wing, said out loud. "Second best week
                // of 2021" is a smaller claim than "best week of 2021" and a
                // plinth that leaves the number off is overstating him.
                Text(man.place == 1
                     ? "\(man.honour.premise) — \(era.label)"
                     : "\(ordinal(man.place)) \(man.honour.premise) — \(era.label)")
                    .font(.system(size: p(11), weight: .medium)).kerning(0.6)
                    .foregroundStyle(.tertiary)
            }
            .frame(width: p(340), alignment: .leading)
            .padding(p(18))
            .glassBackgroundEffect(in: .rect(cornerRadius: p(20)))
        } else {
            Color.clear.frame(width: 1, height: 1)
        }
    }

    private func ordinal(_ n: Int) -> String {
        switch n {
        case 2: return "second"
        case 3: return "third"
        case 4: return "fourth"
        case 5: return "fifth"
        default: return "\(n)th"
        }
    }

    /// The inscription over the arcade.
    private var frieze: some View {
        VStack(spacing: 4) {
            // Sized for 3.6 m, not for a window. A point is 1/1360 of a
            // metre of physical height whatever the distance, so the 26pt
            // sub-line this started at was 19 mm of type read from across a
            // rotunda - about a third of a degree, which is a smudge.
            Text("YOUR HALL OF FAME")
                .font(.system(size: 84, weight: .black)).kerning(12)
            Text(era == .allTime
                 ? "every season in your database"
                 : "the class of \(era.label)")
                .font(.system(size: 40, weight: .medium)).kerning(3)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 60).padding(.vertical, 28)
        .glassBackgroundEffect(in: .capsule)
    }

    /// The dial: which year you are standing in.
    ///
    /// This is the fourth dimension and it is a real one - each of these
    /// re-inducts the whole ring off that season's records, and the counts
    /// beside it are read from what actually came back rather than assumed.
    private var dial: some View {
        VStack(alignment: .leading, spacing: d(13)) {
            HStack(spacing: d(10)) {
                Text("WALK THE YEARS")
                    .font(.system(size: d(13), weight: .heavy)).kerning(1.5)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 0)
                Text(standing)
                    .font(.system(size: d(13)))
                    .foregroundStyle(.tertiary)
            }
            if loading {
                HStack(spacing: d(10)) {
                    ProgressView()
                    Text("Reading \(board.roster.count) season logs…")
                        .font(.system(size: d(15))).foregroundStyle(.secondary)
                }
            } else {
                HStack(spacing: d(8)) {
                    ForEach(Hall.eras(stage.profiles)) { e in
                        Button { era = e } label: {
                            Text(e.label)
                                .font(.system(size: d(15), weight: .bold))
                                .monospacedDigit().lineLimit(1).fixedSize()
                                .padding(.horizontal, d(13))
                                .padding(.vertical, d(9))
                                .plate(d(11), e == era ? Theme.goldFill
                                                       : .white.opacity(0.07))
                                .overlay {
                                    RoundedRectangle(cornerRadius: d(11))
                                        .strokeBorder(.white.opacity(
                                            e == era ? 0.6 : 0.16), lineWidth: 1)
                                }
                        }
                        .buttonStyle(.plain).hoverEffect(.highlight)
                    }
                }
            }
            Divider().opacity(0.3)
            HStack(spacing: d(12)) {
                // Mixed is kept working on purpose. Somebody with a real game
                // on in their living room should be able to have the ring
                // without losing the room it is standing in.
                Picker("", selection: Binding(get: { board.hallStyle },
                                              set: { board.hallStyle = $0 })) {
                    ForEach(RoomStyle.allCases) { s in
                        Text(s.label).tag(s)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: d(300))

                Button {
                    Task { await dismissImmersive(); openWindow(id: "board") }
                } label: {
                    Label("Leave the hall", systemImage: "rectangle.on.rectangle")
                        .font(.system(size: d(15), weight: .medium))
                }
                .buttonStyle(.bordered)
            }
            Text(board.hallStyle.note)
                .font(.system(size: d(11))).foregroundStyle(.tertiary)
        }
        .frame(width: d(560), alignment: .leading)
        .padding(d(20))
        .glassBackgroundEffect(in: .rect(cornerRadius: d(26)))
    }

    /// What the room is showing, counted rather than claimed.
    private var standing: String {
        guard !loading else { return "" }
        let filled = inductees.count
        if filled == 0 {
            return "no records in \(era.label)"
        }
        let empty = Self.bays - filled
        let of = "\(filled) of \(stage.profiles.count) men you roster"
        return empty == 0 ? of : "\(of) · \(empty) alcove\(empty == 1 ? "" : "s") empty"
    }
}


/// The scene graph's handles, kept alive between passes.
@MainActor
final class Stage {
    let root = Entity()
    var architecture: Entity?
    var bays: [Bay] = []
    var built = false
    var profiles: [Profile] = []
    /// Kept so walking back through the years does not re-download a face
    /// that is already on the GPU. Ten 1024px textures is a few megabytes and
    /// the alternative is a re-fetch every time the dial moves.
    var textures: [String: TextureResource] = [:]
}

@MainActor
struct Bay {
    let group: Entity
    let bust: ModelEntity
    let cameo: ModelEntity
    let plinth: ModelEntity
    let light: ModelEntity
}


/// Every mesh in the hall, generated once.
///
/// A struct rather than loose statics so it is obvious at the call site that
/// this is built one time in `build` and never touched again - and so that
/// nothing in this file can accidentally generate geometry from a
/// `RealityView`'s `update:`.
@MainActor
struct Meshes {
    let floorSlab: MeshResource
    let medallion: MeshResource
    let kerb: MeshResource
    let arcadeLine: MeshResource
    let outerWall: MeshResource
    let entablature: MeshResource
    let cornice: MeshResource
    let dome: MeshResource
    let oculusRing: MeshResource
    let oculusDisc: MeshResource
    let pier: MeshResource
    let arch: MeshResource
    let alcoveGlow: MeshResource
    let plinthBase: MeshResource
    let plinthShaft: MeshResource
    let plinthCap: MeshResource
    let bust: MeshResource
    let cameo: MeshResource
    /// How far the dome's lip is above its springing line, before the squash.
    let oculusHeight: Float

    init(arcadeR: Float, wallR: Float, wallH: Float, pierH: Float, bays: Int) {
        let domeR = arcadeR - 0.18
        // The dome is cut off short of the pole; this is where the cut lands.
        let top = (Float.pi / 2) * (1 - 0.16)
        let lip = cos(top) * domeR
        oculusHeight = sin(top) * domeR

        floorSlab = .generateCylinder(height: 0.10, radius: wallR + 0.45)
        medallion = HallMesh.annulus(inner: 0.04, outer: 0.86)
        kerb = HallMesh.annulus(inner: 2.30, outer: 2.46)
        arcadeLine = HallMesh.annulus(inner: arcadeR - 0.05, outer: arcadeR + 0.05)
        outerWall = HallMesh.shell(radius: wallR, height: wallH)
        entablature = HallMesh.shell(radius: domeR, height: 0.27)
        cornice = HallMesh.annulus(inner: domeR, outer: wallR, facingUp: false)
        dome = HallMesh.dome(radius: domeR)
        oculusRing = HallMesh.annulus(inner: lip, outer: lip + 0.20, facingUp: false)
        oculusDisc = HallMesh.annulus(inner: 0.02, outer: lip + 0.02, facingUp: false)

        // The bay opening is the arc between two piers, measured on the
        // arcade line. Derived rather than typed, so changing the bay count
        // does not silently leave the arches overlapping the piers.
        let bayArc = 2 * Float.pi * arcadeR / Float(bays)
        let pierW: Float = 0.34
        pier = .generateBox(width: pierW, height: pierH, depth: 0.42,
                            cornerRadius: 0.02)
        arch = HallMesh.arch(span: bayArc - pierW, thickness: 0.20, depth: 0.42)

        alcoveGlow = .generatePlane(width: bayArc * 0.46, height: 2.10,
                                    cornerRadius: 0.62)
        plinthBase = .generateCylinder(height: 0.14, radius: 0.44)
        plinthShaft = .generateCylinder(height: 0.90, radius: 0.30)
        plinthCap = .generateCylinder(height: 0.10, radius: 0.38)
        bust = HallMesh.lathe(HallMesh.bustProfile)
        cameo = HallMesh.cameo(width: 0.84, height: 0.61, bulge: 0.065)
    }
}


/// How much of the wearer's room the hall is allowed to take.
///
/// A separate enum from SwiftUI's `ImmersionStyle` because the space has to
/// *read* the current choice to decide what to draw, and an existential
/// `any ImmersionStyle` cannot be compared. `FantasyEdgeApp` maps between the
/// two at the one place the scene is declared.
enum RoomStyle: String, CaseIterable, Identifiable {
    case full, progressive, mixed
    var id: String { rawValue }
    var label: String {
        switch self {
        case .full:        return "Full"
        case .progressive: return "Dial in"
        case .mixed:       return "Your room"
        }
    }
    var note: String {
        switch self {
        case .full:
            return "The hall, and nothing else. Look around; there are ten alcoves."
        case .progressive:
            return "Turn the Digital Crown to bring the hall in over your room."
        case .mixed:
            return "Your room, with the gallery ring standing in it at model "
                + "scale. The architecture is dropped rather than pushed "
                + "through your walls."
        }
    }
}
