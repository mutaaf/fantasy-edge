import AVKit
import RealityKit
import SwiftUI

/// The board, placed in the room.
///
/// An immersive space's origin is the floor under the wearer, so everything
/// here is positioned in metres rather than nudged with view offsets - the
/// first version used `offset(z:)` from a ZStack and rendered the whole board
/// at your feet, which is why turning it on appeared to do nothing.
///
/// Two arrangements. Normally the cells sit on an arc in front of you and
/// leverage is distance: a player who can still change your week stands
/// nearer, a decided one falls back. Put a game on and they open into a ring
/// around the screen, so you are watching with your line-up around you rather
/// than beside a list.
///
/// ## What is in here and what is not
///
/// The window has five tabs. Three of them have something that is genuinely
/// better in a room, and two do not, and the difference is whether the content
/// is a *state* you want in your peripheral vision or a *document* you sit and
/// read:
///
///   * **Command** and **Leagues** arrive as the left wing - the attention
///     ranking, which is the one thing a wearer with four leagues cannot get
///     from the arc in front of them, because the arc only ever shows one.
///     Picking a league there re-lays the whole board around it.
///   * **Live** arrives as the slate under it and as the reaction feed on the
///     right. Both are ambient by nature: they are worth glancing at while you
///     are looking at something else, which is exactly what a room is for.
///   * **Intel** arrives as the brief on the right. Prose and a caveat, set
///     large enough to read at a metre and a half.
///   * **Players** does not arrive. It is a filter sidebar over a table of six
///     hundred rows; hanging a spreadsheet in someone's living room is not an
///     improvement on a spreadsheet. Everything it leads to - one man in depth
///     - is one long press away from any face on this board.
///   * The **play-by-play and the gamecast field** do not arrive either. A
///     hundred and seventy rows of nine-point text is a document. The slate
///     panel carries the half of that tab that is a state - which games are
///     running and what the score is - and the window keeps the half that is
///     reading.
///
/// ## Legibility in a room
///
/// A room is a worse backdrop than glass, because glass at least sits over
/// *something* the compositor has already dimmed. Two rules, both of which
/// `apple/contrast_check.py` measures:
///
///   * Colour never carries a word. Every state on this surface is a `Chip` or
///     a `MarkChip` - an opaque `Theme.*Fill` with a glyph on it - and the
///     figures beside them are drawn in ink. The old scoreline tinted a 54pt
///     number, which measured 1.02:1 over a bright wall.
///   * Type is set larger than the window's. The window is read at arm's
///     length; these panels stand at 1.9 metres, so the sizes here are roughly
///     the window's plus a half. The old reaction feed was set at 10 and 11
///     point, which is a caption on a laptop and a smudge on a wall.
struct ImmersiveBoard: View {
    @Environment(Board.self) private var board
    @Environment(\.dismissImmersiveSpace) private var dismissImmersive
    @Environment(\.openWindow) private var openWindow

    @State private var detail: Cell?
    /// A man opened by a long press who is not a starter in the matchup on
    /// screen - somebody off the attention rail or out of the brief. The
    /// hologram takes an id alone, so the cell is not needed to draw him.
    @State private var detailID: String?
    @State private var player = AVPlayer()
    @State private var watching = false

    private let radius: Float = 1.9
    private let eyeHeight: Float = 1.35
    private let columns = 5
    private let columnAngle: Float = 17 * .pi / 180
    private let rowDrop: Float = 0.37
    /// Where the top row sits, relative to eye height.
    ///
    /// Above it, not at it. Eighteen cells at five columns is four rows, and
    /// hanging the first one at eye level put the last one at ankle height -
    /// the bottom row of the board was down by the sofa. Starting a fifth of a
    /// metre high centres the arc on the wearer instead.
    private let arcTop: Float = 0.18
    /// Wider when a game is on, so the screen has the middle to itself.
    private var ringAngle: Float { watching ? 28 * .pi / 180 : columnAngle }

    /// Points per degree, here against the window.
    ///
    /// Measured off a simulator capture rather than guessed: the window's
    /// 1680pt subtends about 53 degrees of the wearer's view and a 330pt cell
    /// standing at 1.9 metres subtends 6.5, which is 31.7 points per degree
    /// against 50.8. Everything in this space was drawn at the window's point
    /// sizes, so all of it arrived 1.6 times smaller than the same thing on
    /// the console - which is what "unreadable text and such" was, and it was
    /// never a resolution problem. Every size in this file is a window size
    /// multiplied through here.
    private let roomScale: CGFloat = 1.6
    private func s(_ v: CGFloat) -> CGFloat { v * roomScale }

    /// Where the wings hang, in radians off straight ahead.
    ///
    /// Just outside the arc, which reaches 34 degrees at five columns of 17.
    /// Further out and they are a shoulder turn rather than a glance; nearer
    /// and they overlap the outermost cell.
    private let wingAngle: Float = 46 * .pi / 180
    private var panelWidth: CGFloat { s(290) }

    var body: some View {
        RealityView { content, attachments in
            let root = Entity()
            root.name = "root"
            content.add(root)
            layout(into: root, attachments: attachments)
        } update: { content, attachments in
            guard let root = content.entities.first(where: { $0.name == "root" })
            else { return }
            // Idempotent: entities are added once and moved thereafter. Tearing
            // them down each pass is what made this seize up.
            layout(into: root, attachments: attachments)
        } attachments: {
            ForEach(board.mosaic.cells) { cell in
                Attachment(id: cell.id) {
                    CellView(cell: cell, scale: roomScale,
                             reaction: board.reactions[cell.id]) {
                        open(cell)
                    }
                }
            }
            Attachment(id: "scoreline") { scoreline }
            Attachment(id: "controls") { controls }
            Attachment(id: "attention") { attentionPanel }
            Attachment(id: "slate") { slatePanel }
            Attachment(id: "reactions") { reactionFeed }
            Attachment(id: "brief") { briefPanel }
            if let id = openID {
                Attachment(id: "detail") {
                    // 760, not the 640 this used to be. `PlayerHologram`
                    // declares `minWidth: 700`, so the old frame was narrower
                    // than the card's own minimum and the season log ran off
                    // the right-hand edge of the panel it was pinned in.
                    PlayerHologram(id: id, cell: detail) { closeDetail() }
                        .frame(width: max(760, s(700)), height: s(560))
                        .glassBackgroundEffect(in: .rect(cornerRadius: 34))
                }
            }
            if watching {
                Attachment(id: "screen") { screen }
            }
        }
        // The window calls `board.stop()` when it disappears, and entering
        // this space dismisses the window - so without this the room showed a
        // board that had quietly stopped being live the moment you opened it.
        .task {
            board.start()
            await board.loadPrefs()
            await board.loadProjections()
            await board.loadIntel()
        }
        .onDisappear { board.stop() }
    }

    // MARK: - what a tap and a long press mean here

    /// A tap on any face opens him in depth, wherever the face was drawn -
    /// on the arc, or in the brief. The window raises a sheet for this; a
    /// sheet cannot be presented into an immersive space, so here the card is
    /// an attachment placed in front of the arc.
    ///
    /// The cell is carried alongside the id when there is one, because the
    /// leverage figures on that card - his share of what is still in doubt -
    /// are the one part of it that needs the live cell. A man opened out of
    /// the brief has no cell and the card draws the rest of itself from
    /// `/api/player/<id>` exactly as it does in the window.
    private var openID: String? { detailID }

    private func open(id: String) {
        if detailID == id { closeDetail(); return }
        detail = board.mosaic.cells.first { $0.id == id }
        detailID = id
    }
    private func open(_ cell: Cell) {
        if detailID == cell.id { closeDetail() } else { detail = cell; detailID = cell.id }
    }
    private func closeDetail() { detail = nil; detailID = nil }

    // MARK: - placement

    private func layout(into root: Entity, attachments: RealityViewAttachments) {
        let cells = board.mosaic.cells
        for (i, cell) in cells.enumerated() {
            guard let view = attachments.entity(for: cell.id) else { continue }
            if view.parent !== root { root.addChild(view) }
            let col = Float(i % columns) - Float(columns - 1) / 2
            let row = Float(i / columns)
            let angle = col * ringAngle
            let depth = radius - cell.band.depth
            view.position = SIMD3(x: sin(angle) * depth,
                                  y: eyeHeight + arcTop - row * rowDrop,
                                  z: -cos(angle) * depth)
            view.orientation = simd_quatf(angle: -angle, axis: SIMD3(0, 1, 0))
            // A detail panel is open in the middle; get the near cells out of it.
            view.isEnabled = !(openID != nil && abs(col) < 1.2 && row < 1)
        }
        pin("scoreline", attachments, root, SIMD3(0, eyeHeight + 0.66, -radius + 0.1))
        // Low, and nearer than the arc so it reads as a bar under the board
        // rather than a fifth row of it. Any lower and it leaves the wearer's
        // comfortable downward field of view entirely - measured off a capture,
        // that runs out at about 33 degrees below eye level, and this sits at 31.
        pin("controls", attachments, root, SIMD3(0, eyeHeight - 0.90, -radius + 0.40))
        // Two wings, each on the same arc as the cells and turned in to face
        // the wearer. Left is where you stand - which league needs you, and
        // what is on today. Right is what is happening and what it means.
        //
        // Placed by angle rather than by hand-picked x and z. The hand-picked
        // pair the reaction feed used put it at 67 degrees off centre, which
        // is behind your shoulder: it had been in the room for as long as the
        // room had and could not be seen without turning round.
        wing("attention", attachments, root, angle: -wingAngle, y: eyeHeight + 0.42)
        wing("slate", attachments, root, angle: -wingAngle, y: eyeHeight - 0.46)
        wing("reactions", attachments, root, angle: wingAngle, y: eyeHeight + 0.42)
        wing("brief", attachments, root, angle: wingAngle, y: eyeHeight - 0.44)
        pin("detail", attachments, root, SIMD3(0, eyeHeight - 0.02, -radius + 0.55))
        pin("screen", attachments, root, SIMD3(0, eyeHeight, -radius - 0.25))
    }

    /// A side panel, on the arc at a given angle and height. Same convention
    /// as the cells: positive is to your right, and the panel is yawed by the
    /// negative of its own angle so it squares up to the wearer rather than
    /// standing side-on.
    private func wing(_ id: String, _ attachments: RealityViewAttachments,
                      _ root: Entity, angle: Float, y: Float) {
        pin(id, attachments, root,
            SIMD3(sin(angle) * radius, y, -cos(angle) * radius), yaw: -angle)
    }

    private func pin(_ id: String, _ attachments: RealityViewAttachments,
                     _ root: Entity, _ position: SIMD3<Float>, yaw: Float = 0) {
        guard let e = attachments.entity(for: id) else { return }
        if e.parent !== root { root.addChild(e) }
        e.position = position
        // Assigned every pass rather than only when non-zero. The old version
        // skipped `yaw == 0`, which meant a panel that had once been turned
        // kept its old rotation if it was later placed straight - and the two
        // wings swapped sides during the rebuild that introduced them.
        e.orientation = simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0))
    }

    // MARK: - furniture

    /// Where this matchup stands, and whose numbers say so.
    ///
    /// Both scores in ink, with a chip naming which side is which. Tinting a
    /// 54pt figure was the single largest thing on this surface that a bright
    /// room erased. The mark between them is the state as a glyph, so ahead
    /// and behind are separable without the colour - and the source tag is
    /// there because the projected totals underneath are one source's opinion
    /// and the board's whole geometry is sized by them.
    private var scoreline: some View {
        let m = board.mosaic
        let mark = Theme.Mark.of(m.yourProjected - m.oppProjected, level: 0.5)
        return HStack(spacing: 30) {
            VStack(spacing: 5) {
                Text(m.yourScore, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: s(56), weight: .bold))
                    .contentTransition(.numericText())
                Chip(text: "YOU", fill: Theme.greenFill, size: s(12))
                Text("\(m.yourProjected, format: .number.precision(.fractionLength(1))) proj")
                    .font(.system(size: 13)).foregroundStyle(.secondary)
            }
            VStack(spacing: 5) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: s(34), weight: .bold))
                MarkChip(mark: mark, text: marked(m), size: s(11))
                HStack(spacing: 7) {
                    Text(board.league?.league ?? "").font(.system(size: s(14)))
                        .foregroundStyle(.secondary).lineLimit(1)
                    if let L = board.league {
                        Text("WK \(L.week)").font(.system(size: s(12), weight: .heavy))
                            .foregroundStyle(.tertiary)
                    }
                }
                SourceTag(text: board.loadedSources.isEmpty ? "LEAGUE"
                          : board.projectionTag)
            }
            .frame(maxWidth: s(320))
            VStack(spacing: 5) {
                Text(m.oppScore, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 56, weight: .bold))
                    .contentTransition(.numericText())
                Chip(text: "THEM", fill: Theme.redFill, size: s(12))
                Text("\(m.oppProjected, format: .number.precision(.fractionLength(1))) proj")
                    .font(.system(size: 13)).foregroundStyle(.secondary)
            }
        }
        .monospacedDigit()
        .padding(.horizontal, s(40)).padding(.vertical, s(24))
        .glassBackgroundEffect(in: .capsule)
    }

    /// The projected margin, said in words beside the glyph that carries it.
    private func marked(_ m: Mosaic) -> String {
        let d = m.yourProjected - m.oppProjected
        if abs(d) < 0.5 { return "LEVEL" }
        return (d > 0 ? "+" : "") + d.formatted(.number.precision(.fractionLength(1)))
    }

    private var controls: some View {
        HStack(spacing: 14) {
            Button {
                watching.toggle()
                if watching { startWatching() } else { player.pause() }
            } label: {
                Label(watching ? "Close game" : "Watch the game",
                      systemImage: watching ? "xmark.circle" : "play.tv")
                    .font(.system(size: s(17), weight: .medium))
            }
            // The `*Fill` hues, not the brand ones. `borderedProminent` puts a
            // white label on whatever it is tinted with, and white on
            // `Theme.red` measures 2.34:1 - this control was the only thing in
            // the room whose own label failed the check the palette exists to
            // enforce. See `apple/contrast_check.py`.
            .buttonStyle(.borderedProminent)
            .tint(watching ? Theme.redFill : Theme.greenFill)

            Button {
                Task { await dismissImmersive(); openWindow(id: "board") }
            } label: {
                Label("Back to the window", systemImage: "rectangle.on.rectangle")
                    .font(.system(size: s(17), weight: .medium))
            }
            .buttonStyle(.bordered)
        }
        .padding(.horizontal, s(22)).padding(.vertical, s(16))
        .glassBackgroundEffect(in: .capsule)
        .hoverEffect(.highlight)
    }

    // MARK: - the left wing: where you stand

    /// Which of your leagues needs you, in the order `Attention.swift` ranks
    /// them, and picking one re-lays the arc around it.
    ///
    /// This is the one thing the room could not do before. The arc draws a
    /// single matchup, so a wearer with four leagues had no way to see the
    /// other three and no way to change which one was in front of them
    /// without going back to the window. Nothing here is new arithmetic - it
    /// is the same ranking the window's left rail reads.
    private var attentionPanel: some View {
        roomPanel("WHICH LEAGUE NEEDS YOU") {
            if board.leagues.isEmpty {
                Text("No leagues loaded.").font(.system(size: s(15)))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: s(8)) {
                    ForEach(board.attention().prefix(5)) { f in
                        Button { board.selected = f.id } label: { leagueRow(f) }
                            .buttonStyle(.plain).hoverEffect(.highlight)
                    }
                }
            }
        }
    }

    private func leagueRow(_ f: LeagueFocus) -> some View {
        let here = f.id == board.league?.id
        return HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(f.league.league).font(.system(size: s(15), weight: .semibold))
                    .lineLimit(1).minimumScaleFactor(0.75)
                HStack(spacing: 5) {
                    if let m = f.reason.mark {
                        MarkChip(mark: m, text: f.reason.label.uppercased(), size: s(9))
                    } else {
                        Chip(text: f.reason.label.uppercased(),
                             fill: Theme.positionFill("DEF"), size: s(9))
                    }
                }
            }
            Spacer(minLength: 0)
            Text(f.mosaic.winProb, format: .percent.precision(.fractionLength(0)))
                .font(.system(size: s(19), weight: .bold)).monospacedDigit()
        }
        // The whole row, not the words in it. A tap in a room is a gaze plus a
        // pinch and it lands where you were looking, which is rarely the
        // eleven points of text - see the note on `CellView`.
        .padding(.horizontal, s(12)).padding(.vertical, s(10))
        .frame(maxWidth: .infinity, alignment: .leading)
        .plate(s(13), here ? Theme.greenFill : .white.opacity(0.07))
        .overlay {
            RoundedRectangle(cornerRadius: s(13))
                .strokeBorder(.white.opacity(here ? 0.55 : 0.16), lineWidth: 1)
        }
    }

    /// Today's games. Read-only on purpose: the field and the play-by-play
    /// this would otherwise lead to are a document, and there is nowhere in a
    /// room to read one. What is useful here is the state - who is playing,
    /// who is running, what the score is - which is a glance.
    private var slatePanel: some View {
        let games = board.slate
        return roomPanel("TODAY") {
            if games.isEmpty {
                Text("No slate reported yet.").font(.system(size: s(15)))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: s(7)) {
                    ForEach(games.prefix(6)) { g in
                        HStack(spacing: s(9)) {
                            ClubMark(abbr: g.away, size: s(22))
                            Text(g.state == "pre" ? "vs"
                                 : "\(g.awayScore)–\(g.homeScore)")
                                .font(.system(size: s(15), weight: .bold))
                                .monospacedDigit().frame(minWidth: s(62))
                            ClubMark(abbr: g.home, size: s(22))
                            Spacer(minLength: 0)
                            if g.redZone {
                                Chip(text: "RZ", fill: Theme.goldFill, size: s(10))
                            } else if g.live {
                                MarkChip(mark: .live, text: g.label.uppercased(),
                                         size: s(9))
                            } else {
                                Text(g.label).font(.system(size: s(12)))
                                    .foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                    }
                    if games.count > 6 {
                        Text("\(games.count - 6) more on the slate")
                            .font(.system(size: s(12))).foregroundStyle(.tertiary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        }
    }

    // MARK: - the right wing: what happened, and what it means

    /// A live feed of what just landed, at the edge of vision, so a big play
    /// registers even while you are looking at the game rather than the board.
    private var reactionFeed: some View {
        roomPanel("AS IT HAPPENS") {
            if board.recent.isEmpty {
                Text("Nothing yet").font(.system(size: s(15)))
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: s(10)) {
                    ForEach(board.recent.prefix(5)) { r in
                        HStack(spacing: s(10)) {
                            HStack(spacing: 0) {
                                Chip(text: "+" + r.delta.formatted(
                                        .number.precision(.fractionLength(1))),
                                     fill: Theme.sideFill(r.side), size: s(13))
                                Spacer(minLength: 0)
                            }
                            .frame(width: s(74), alignment: .leading)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(r.name).font(.system(size: s(16), weight: .semibold))
                                    .lineLimit(1).minimumScaleFactor(0.8)
                                Text("\(r.headline) · now \(r.total, format: .number.precision(.fractionLength(1)))")
                                    .font(.system(size: s(13)))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .transition(.move(edge: .top).combined(with: .opacity))
                    }
                }
                .animation(.smooth, value: board.recent)
            }
        }
    }

    /// The computed brief, at the size of something meant to be read.
    ///
    /// Two findings, not the whole tab: the window's Intel view is a long list
    /// of cards with facts and sources under each, and that is a thing to sit
    /// with. What belongs on a wall is the headline finding and the
    /// qualification that comes with it - and the caveat is carried verbatim
    /// here for the same reason it is everywhere else in this app, because a
    /// number without its caveat is a claim the analysis never made.
    private var briefPanel: some View {
        let found = (board.intel?.insights ?? [])
            .sorted { $0.weight > $1.weight }.prefix(2)
        return roomPanel("THE BRIEF") {
            if board.intelLoading && board.intel == nil {
                ProgressView().padding(.vertical, 8)
            } else if let note = board.intelNote, board.intel == nil {
                Text(note).font(.system(size: s(13))).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else if found.isEmpty {
                Text("Nothing computed for this week yet.")
                    .font(.system(size: s(15))).foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: s(12)) {
                    ForEach(found) { i in
                        VStack(alignment: .leading, spacing: s(5)) {
                            Chip(text: i.kindLabel,
                                 fill: Theme.positionFill("DEF"), size: s(9))
                            Text(i.title).font(.system(size: s(16), weight: .semibold))
                                .fixedSize(horizontal: false, vertical: true)
                            Text(i.detail).font(.system(size: s(13)))
                                .foregroundStyle(.secondary)
                                .lineLimit(3)
                                .fixedSize(horizontal: false, vertical: true)
                            if !i.caveat.isEmpty {
                                HStack(alignment: .top, spacing: s(6)) {
                                    MarkChip(mark: .caution, size: s(8))
                                    Text(i.caveat).font(.system(size: s(12)))
                                        .foregroundStyle(.tertiary)
                                        .lineLimit(3)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            // The men a finding is about, as a way into the
                            // card. Same gesture as everywhere else.
                            if !i.players.isEmpty {
                                HStack(spacing: s(6)) {
                                    ForEach(i.players.prefix(2)) { p in
                                        Button { open(id: p.id) } label: {
                                            HStack(spacing: s(6)) {
                                                Headshot(id: p.id, name: p.name,
                                                         tint: Theme.positionFill(p.pos),
                                                         size: s(26))
                                                Text(p.name)
                                                    .font(.system(size: s(12), weight: .semibold))
                                                    .lineLimit(1)
                                            }
                                            .padding(.horizontal, s(8))
                                            .padding(.vertical, s(5))
                                            .plate(s(10), .white.opacity(0.07))
                                        }
                                        .buttonStyle(.plain).hoverEffect(.highlight)
                                    }
                                }
                            }
                        }
                        if i.id != found.last?.id { Divider().opacity(0.3) }
                    }
                }
            }
        }
    }

    /// One panel of the wings, so the four of them share an edge, a padding
    /// and a type scale rather than each re-deciding.
    private func roomPanel<C: View>(_ title: String,
                                    @ViewBuilder _ body: () -> C) -> some View {
        VStack(alignment: .leading, spacing: s(11)) {
            Text(title).font(.system(size: s(12), weight: .heavy)).kerning(1.4)
                .foregroundStyle(.secondary)
            body()
        }
        .frame(width: panelWidth, alignment: .leading)
        .padding(s(20))
        .glassBackgroundEffect(in: .rect(cornerRadius: s(26)))
    }

    /// The game itself, in the middle, with the line-up opened into a ring
    /// around it. The source is whatever you point it at - there is no stream
    /// bundled here and inventing one would be worse than asking.
    private var screen: some View {
        VStack(spacing: 0) {
            if board.watchURL.isEmpty {
                VStack(spacing: 14) {
                    Image(systemName: "play.tv").font(.system(size: s(44)))
                        .foregroundStyle(.secondary)
                    Text("No video source set")
                        .font(.system(size: s(21), weight: .semibold))
                    Text("Add a stream or file URL in the window's settings and it "
                         + "will play here, with your line-up around it.")
                        .font(.system(size: s(16))).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center).frame(maxWidth: s(460))
                }
                .frame(width: 900, height: 506)
            } else {
                VideoPlayer(player: player)
                    .frame(width: 900, height: 506)
            }
        }
        .glassBackgroundEffect(in: .rect(cornerRadius: 26))
    }

    private func startWatching() {
        guard let url = URL(string: board.watchURL), !board.watchURL.isEmpty
        else { return }
        player.replaceCurrentItem(with: AVPlayerItem(url: url))
        player.play()
    }
}
