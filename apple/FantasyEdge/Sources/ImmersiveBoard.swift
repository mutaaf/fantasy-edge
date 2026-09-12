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
/// ## The middle belongs to whoever just did something
///
/// Both arrangements now form around a centre rather than filling row by row.
/// `Spotlight` decides who stands there - the man who most recently scored
/// while that is still news, and the man with the most at stake the rest of
/// the time - and the remaining cells fill the slots outward from him in
/// leverage order. So the middle of the wearer's view is the one place on the
/// board that is always about the present tense, and the arc still says
/// importance with distance.
///
/// The re-forming is a movement, not a cut. Entities are told where to go with
/// `move(to:)` and only when the place they were last *told* about actually
/// changed - see `place(_:_:_:_:)`, which is where the difference between an
/// animation and a stutter lives.
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
    @State private var feed = GameFeed()
    @State private var watching = false

    /// The reaction the centre of the room is currently given to, and the
    /// timer that hands the middle back when it stops being news.
    ///
    /// State rather than a computed read of `board.recent.first`, because
    /// something has to *move* when the dwell runs out. Nothing else changes
    /// at that instant - no poll has landed, no number is different - so
    /// without a piece of state to invalidate on, the room would keep the old
    /// man in the middle until the next poll happened to arrive, which is up
    /// to thirty-five seconds later.
    @State private var held: Board.Reaction?
    @State private var dwell: Task<Void, Never>?
    @State private var placed = Placement()

    /// How long the centre keeps a man who has just scored.
    ///
    /// Longer than the longest poll interval, deliberately. `Board.beat()`
    /// draws 25 to 35 seconds, so a dwell shorter than that would hand the
    /// middle back before the next poll could either confirm the man or
    /// replace him - the centre would spend most of a live afternoon in its
    /// resting state with a flicker of news between polls, which is the
    /// opposite of what it is for. Forty-five seconds means a score holds the
    /// room until at least one further poll has had its say.
    private static let dwellFor: TimeInterval = 45

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
    /// Wider when a game is on, so the screen has the middle to itself, and
    /// wider again when a hologram is up: the card is placed dead ahead and
    /// half a metre nearer than the arc, so the cells on either side of it
    /// have to give it air rather than crowd its edges. The middle three of
    /// the top row are hidden outright below; this is what happens to the rest.
    private var ringAngle: Float {
        if watching { return 28 * .pi / 180 }
        if openID != nil { return 25 * .pi / 180 }
        return columnAngle
    }
    /// How much nearer the wearer the man in the middle stands than his band
    /// alone would put him. Enough to read as forward - the arc's own bands
    /// span 0.46 metres end to end - and not so much that he overlaps his
    /// neighbours: at 17 degrees of separation a cell has about 11 degrees of
    /// angular width to spend and 17 to spend it in.
    private let focusLift: Float = 0.25

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
            if centre != nil {
                Attachment(id: "spotlight") { spotlightBanner }
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
        // The start below was not enough on its own: the window's
        // `onDisappear` runs *after* this task, so it cancelled the poll this
        // had just begun. `Board` counts its watchers now; see the note there.
        .task {
            // A score that landed while the wearer was still in the window
            // should be in the middle of the room when they walk into it.
            // `onChange` cannot see one that fired before this view existed.
            hold(board.recent.first)
            board.start()
            await board.loadPrefs()
            await board.loadProjections()
            await board.loadIntel()
        }
        // Newest first, so `first` is the newest thing to land. Within one
        // poll the batch is sorted by size, which is the right tie-break: two
        // men who scored in the same thirty seconds are equally recent, and
        // the bigger play is the one worth turning the room around.
        .onChange(of: board.recent.first) { _, fresh in hold(fresh) }
        .onDisappear { board.stop(); dwell?.cancel() }
    }

    /// Give the middle of the room to a reaction, and set the clock that takes
    /// it back.
    ///
    /// The task is cancelled and replaced rather than left to expire, so a
    /// second score inside the window resets the dwell instead of inheriting
    /// the remains of the first man's - which would have handed the room back
    /// seconds after the second man arrived in it.
    ///
    /// What is left of the dwell is computed from when the reaction actually
    /// landed rather than from now, because this is also called as the space
    /// opens, with whatever the window had already collected. Sleeping the
    /// full forty-five seconds there would give a two-minute-old touchdown a
    /// fresh spell in the middle of the room.
    private func hold(_ r: Board.Reaction?) {
        guard let r else { return }
        let left = Self.dwellFor - Date.now.timeIntervalSince(r.at)
        guard left > 0 else { return }
        dwell?.cancel()
        held = r
        dwell = Task {
            try? await Task.sleep(for: .seconds(left))
            guard !Task.isCancelled else { return }
            await MainActor.run { held = nil }
        }
    }

    /// Who has the middle, and why. Recomputed on every pass because the
    /// resting half of the rule follows leverage, which moves with the poll.
    private var centre: Spotlight? {
        Spotlight.decide(cells: board.mosaic.cells, recent: board.recent,
                         holding: held, now: .now, dwell: Self.dwellFor)
    }

    // MARK: - what a tap and a long press mean here

    /// A tap on anything that represents a man opens him in depth - a cell on
    /// the arc, the banner over the middle of the room, a face in the brief, a
    /// row in the reaction feed. The window raises a sheet for this; a sheet
    /// cannot be presented into an immersive space, so here the card is an
    /// attachment placed in front of the arc.
    ///
    /// It is placed *dead ahead*, never where the thing that opened it was
    /// drawn. A card that appeared over the cell you tapped would put itself
    /// forty degrees off centre for anything on the outer columns and behind
    /// your shoulder for anything in a wing, and a wearer would have to turn
    /// their head to read the deepest surface in the app. Straight ahead and
    /// half a metre nearer than the arc is the one placement that is the same
    /// wherever the tap came from - and the arc widens and the middle of the
    /// top row hides while it is up, so the card has air rather than cells
    /// crowding its edges.
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
        let order = arranged(board.mosaic.cells)
        let slots = seats(order.count)
        for (k, cell) in order.enumerated() {
            guard let view = attachments.entity(for: cell.id) else { continue }
            let i = slots[k]
            let col = Float(i % columns) - Float(columns - 1) / 2
            let row = Float(i / columns)
            let angle = col * ringAngle
            // The man in the middle stands forward of his own band. Distance
            // is still importance on this arc; this is the one cell allowed to
            // borrow a little of it to say "now" instead.
            let depth = radius - cell.band.depth - (k == 0 ? focusLift : 0)
            // A detail panel is open in the middle; get the near cells out of
            // it. Assigned before the placement below, because a disabled
            // entity is placed rather than animated - an animation on
            // something nobody can see is a frame budget spent on nothing, and
            // it would still be playing when the panel closed.
            view.isEnabled = !(openID != nil && abs(col) < 1.2 && row < 1)
            place(cell.id, view, root,
                  SIMD3(x: sin(angle) * depth,
                        y: eyeHeight + arcTop - row * rowDrop,
                        z: -cos(angle) * depth),
                  yaw: -angle)
        }
        if let c = centre {
            // Above the man it is about, in front of him so his own cell
            // cannot occlude it. The height clears the tallest band - an xl
            // cell is 215 points, which is 344 in the room and about a quarter
            // of a metre - and still sits well under the scoreline at +0.66.
            pin("spotlight", attachments, root,
                SIMD3(0, eyeHeight + arcTop + 0.19,
                      -(radius - c.cell.band.depth - focusLift - 0.03)))
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
        // Dead ahead, at eye level, whichever man was tapped and wherever he
        // was drawn when he was. See the note on `open(_:)`.
        pin("detail", attachments, root, SIMD3(0, eyeHeight - 0.02, -radius + 0.55))
        pin("screen", attachments, root, SIMD3(0, eyeHeight, -radius - 0.25))
    }

    /// The cells in the order the seats want them: the man in the middle
    /// first, then everybody else in the leverage order the model already
    /// sorted them into.
    ///
    /// He is *moved* rather than swapped with whoever held the middle seat.
    /// Swapping would send one man across the whole board every time somebody
    /// scored; moving shuffles everybody behind him by one seat, which is a
    /// row of small movements rather than one long one, and reads as the board
    /// re-forming instead of two cells trading places.
    private func arranged(_ cells: [Cell]) -> [Cell] {
        guard let id = centre?.cell.id,
              let i = cells.firstIndex(where: { $0.id == id }), i != 0
        else { return cells }
        var out = cells
        out.insert(out.remove(at: i), at: 0)
        return out
    }

    /// The grid positions, ranked by how central they are.
    ///
    /// `seats(n)[k]` is the row-major slot the k-th most important cell gets,
    /// so seat 0 is the middle of the top row and the rest spread outward from
    /// it. A row costs less than a column because it *is* less: the rows are
    /// 0.37 metres apart and the columns about 0.55 at seventeen degrees, so a
    /// step down is two thirds of a step sideways. The ratio is fixed rather
    /// than derived from `ringAngle`, which widens when a hologram opens -
    /// deriving it would re-rank every seat at that moment and send the whole
    /// board shuffling for a reason that has nothing to do with the board.
    private func seats(_ n: Int) -> [Int] {
        let rowCost: Float = 0.37 / 0.55
        func cost(_ i: Int) -> Float {
            abs(Float(i % columns) - Float(columns - 1) / 2)
                + Float(i / columns) * rowCost
        }
        // The index is the tie-break, so two seats of equal cost keep the same
        // order every pass. Without it `sorted` is free to hand back either,
        // and a pair of cells would swap places on nothing.
        return (0..<n).sorted { (cost($0), $0) < (cost($1), $1) }
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
        place(id, e, root, position, yaw: yaw)
    }

    /// Put an entity where it now belongs, moving it if it is already
    /// somewhere else.
    ///
    /// Three things this has to get right, and each of them is a bug that
    /// happens the moment it is dropped:
    ///
    ///   * **The first placement is a cut.** An entity that has just been
    ///     added sits at the root's origin, which in an immersive space is the
    ///     floor between the wearer's feet. Animating from there means the
    ///     whole board flies up off the carpet on every open.
    ///   * **A move is compared against the last place this asked for, not
    ///     against where the entity currently is.** Mid-animation
    ///     `entity.position` reads as wherever the movement has got to, and
    ///     `update:` runs on the compositor's clock rather than on the poll -
    ///     so comparing against it re-issues `move(to:)` sixty times a second,
    ///     each call restarting the animation from a hair further along. The
    ///     cell creeps and never arrives.
    ///   * **A disabled entity is cut, not moved.** It is behind the hologram
    ///     and nobody can see it; an animation there is frame budget spent on
    ///     nothing, and it would still be running when the panel closed.
    ///
    /// The yaw is assigned along with the position rather than only when it is
    /// non-zero. The old version skipped `yaw == 0`, so a panel that had once
    /// been turned kept its old rotation if it was later placed straight, and
    /// the two wings swapped sides during the rebuild that introduced them.
    private func place(_ id: String, _ e: Entity, _ root: Entity,
                       _ position: SIMD3<Float>, yaw: Float = 0) {
        let target = Transform(
            scale: .one,
            rotation: simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0)),
            translation: position)
        let arriving = e.parent !== root
        if arriving { root.addChild(e) }
        let told = placed.at[id].map { (at: $0, yaw: placed.yaw[id] ?? 0) }
        if arriving || !e.isEnabled || told == nil {
            e.transform = target
        } else if let t = told,
                  // A third of a centimetre, or a tenth of a degree. Below
                  // that nothing is visible at a metre and a half and the
                  // animation is only work.
                  simd_distance(t.at, position) > 0.003
                    || abs(t.yaw - yaw) > 0.002 {
            e.move(to: target, relativeTo: root, duration: 0.55,
                   timingFunction: .easeInOut)
        } else {
            return                      // already there, or already on its way
        }
        placed.at[id] = position
        placed.yaw[id] = yaw
    }

    /// Where each entity was last *told* to go.
    ///
    /// A plain class held in `@State` rather than anything observable: it is
    /// written from inside `RealityView`'s update closure, and a stored
    /// property SwiftUI tracked would invalidate the view that is mid-update
    /// and loop - the same reason every memo on `Board` is
    /// `@ObservationIgnored`.
    private final class Placement {
        var at: [String: SIMD3<Float>] = [:]
        var yaw: [String: Float] = [:]
    }

    // MARK: - furniture

    /// Who has the middle, said out loud above him.
    ///
    /// The cell itself cannot say this. It is the same `CellView` the window
    /// draws and it carries what is true of the man - his points, his
    /// position, his share - not what is true of his *place in the room*, and
    /// a reader looking at the middle of an arc is owed the reason it is the
    /// middle. Two states have to be separable at a glance and never merge: a
    /// green live chip over "+6.5 just landed" is an event, and a slate chip
    /// over "nothing has landed yet" is an arrangement. Both are opaque chips
    /// with a glyph, so neither depends on the colour surviving the room.
    ///
    /// Tapping it opens the same hologram tapping his cell does. It sits over
    /// a man, so it is one of the things on this surface that represents a
    /// person, and every one of those leads to the card.
    @ViewBuilder
    private var spotlightBanner: some View {
        if let c = centre {
            Button { open(c.cell) } label: {
                HStack(spacing: s(14)) {
                    Headshot(id: c.cell.id, name: c.cell.name,
                             tint: Theme.positionFill(c.cell.pos), size: s(44))
                    VStack(alignment: .leading, spacing: s(4)) {
                        HStack(spacing: s(7)) {
                            if case .scored(let r) = c.reason {
                                MarkChip(mark: .live, text: c.headline,
                                         size: s(10))
                                Chip(text: r.headline.uppercased(),
                                     fill: Theme.sideFill(r.side), size: s(10))
                            } else {
                                Chip(text: c.headline,
                                     fill: Theme.positionFill("DEF"),
                                     size: s(10))
                            }
                            Text(c.cell.name)
                                .font(.system(size: s(19), weight: .bold))
                                .lineLimit(1).minimumScaleFactor(0.7)
                        }
                        Text(c.caption)
                            .font(.system(size: s(13)))
                            .foregroundStyle(.secondary)
                            .lineLimit(2).fixedSize(horizontal: false,
                                                    vertical: true)
                    }
                    Image(systemName: "chevron.right")
                        .font(.system(size: s(13), weight: .bold))
                        .foregroundStyle(.tertiary)
                }
                .frame(width: s(430), alignment: .leading)
                .padding(.horizontal, s(18)).padding(.vertical, s(12))
                .glassBackgroundEffect(in: .rect(cornerRadius: s(24)))
            }
            .buttonStyle(.plain).hoverEffect(.highlight)
            .accessibilityLabel("\(c.cell.name). \(c.caption)")
            .animation(.smooth(duration: 0.4), value: c)
        }
    }

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
                if watching { feed.start(board.watchURL) } else { feed.stop() }
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

            // Full is offered here now, and mixed is still what you get by
            // default. See the note on the scene in `FantasyEdgeApp`.
            Picker("", selection: Binding(get: { board.boardStyle },
                                          set: { board.boardStyle = $0 })) {
                ForEach(RoomStyle.allCases) { r in Text(r.label).tag(r) }
            }
            .pickerStyle(.segmented).frame(width: s(280))

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
    ///
    /// Every row is a man, so every row opens him. This was the last thing on
    /// the surface that named a player and did nothing when you looked at it
    /// and pinched - which on a headset reads as broken rather than as
    /// read-only, because the row beside it in the brief and every cell on the
    /// arc do open.
    private var reactionFeed: some View {
        roomPanel("AS IT HAPPENS") {
            if board.recent.isEmpty {
                Text("Nothing yet").font(.system(size: s(15)))
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: s(6)) {
                    ForEach(board.recent.prefix(5)) { r in
                        Button { open(id: r.id) } label: { reactionRow(r) }
                            .buttonStyle(.plain).hoverEffect(.highlight)
                            .transition(.move(edge: .top).combined(with: .opacity))
                    }
                }
                .animation(.smooth, value: board.recent)
            }
        }
    }

    /// One landing. The whole row is the target rather than the words in it,
    /// for the reason `leagueRow` is: a pinch lands where the wearer was
    /// looking, which is rarely the sixteen points of a name.
    private func reactionRow(_ r: Board.Reaction) -> some View {
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
            Spacer(minLength: 0)
        }
        .padding(.horizontal, s(8)).padding(.vertical, s(7))
        .frame(maxWidth: .infinity, alignment: .leading)
        // The man currently standing in the middle of the room is marked
        // here, so the feed and the centre are legibly the same claim. Marked
        // with a lighter ground and an edge rather than with a tint: this row
        // carries secondary ink, and the one colour that would mean anything
        // here - his side - is a fill built for white text, not for grey.
        .plate(s(11), .white.opacity(r.id == centre?.cell.id ? 0.16 : 0.06))
        .overlay {
            RoundedRectangle(cornerRadius: s(11))
                .strokeBorder(.white.opacity(r.id == centre?.cell.id ? 0.5 : 0),
                              lineWidth: 1)
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
            switch feed.state {
            case .playing, .opening:
                VideoPlayer(player: feed.player)
                    .frame(width: 900, height: 506)
                    .overlay(alignment: .top) {
                        // Said out loud until the first frame arrives. A
                        // stream that is still opening and one that has died
                        // look identical, and the whole point of this rewrite
                        // is that they no longer read the same.
                        if feed.state == .opening {
                            Label("Opening the stream…", systemImage: "clock")
                                .font(.system(size: s(15), weight: .medium))
                                .padding(.horizontal, s(16)).padding(.vertical, s(9))
                                .glassBackgroundEffect(in: .capsule)
                                .padding(.top, s(18))
                        }
                    }
            case .failed(let why):
                trouble(why)
            case .idle:
                trouble(GameFeed.verdict(board.watchURL))
            }
        }
        .glassBackgroundEffect(in: .rect(cornerRadius: 26))
    }

    /// Why there is no picture, in a sentence, at the size of the thing it
    /// replaced. A black rectangle is not an error message.
    private func trouble(_ why: String) -> some View {
        VStack(spacing: 14) {
            MarkChip(mark: .caution, text: "NO PICTURE", size: s(12))
            Text(why)
                .font(.system(size: s(19), weight: .semibold))
                .multilineTextAlignment(.center).frame(maxWidth: s(560))
                .fixedSize(horizontal: false, vertical: true)
            if !board.watchURL.isEmpty {
                Text(board.watchURL)
                    .font(.system(size: s(13), design: .monospaced))
                    .foregroundStyle(.tertiary).lineLimit(2).truncationMode(.middle)
                    .frame(maxWidth: s(560))
            }
            Text("Set it in the window's settings. Nothing is bundled - point "
                 + "it at whatever you are already watching.")
                .font(.system(size: s(14))).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).frame(maxWidth: s(460))
        }
        .frame(width: 900, height: 506)
    }
}
