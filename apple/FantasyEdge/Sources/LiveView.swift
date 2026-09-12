import SwiftUI

/// The live tab. Two questions, and they are different enough to be two modes.
///
/// "My Team" is the one worth having: your men come from four or five games
/// running at once, and the only thing that decides whether any of them can
/// score in the next ten seconds is who has the ball in *his* game. So they
/// stand on one field, and a man whose club is defending is on the bench -
/// not as a styling choice, but because that is what is true of him.
///
/// "Game" is the ordinary one: pick a game off the slate and watch the ball.
struct LiveView: View {
    @Environment(Board.self) private var board
    @Binding var focus: String?
    /// Owned by the command centre, because a scoreline tapped on another tab
    /// has to be able to say which game it meant before this view exists.
    @Binding var event: String
    @State private var mode: Mode = .mine

    enum Mode: String, CaseIterable, Identifiable {
        case mine = "My Team", game = "Game", red = "Red Zone"
        var id: String { rawValue }
        var icon: String {
            switch self {
            case .mine: return "person.2.badge.gearshape"
            case .game: return "sportscourt"
            case .red:  return "target"
            }
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            switcher
            scope
            // One vertical scroller, here, for all three modes.
            //
            // `CommandView` hands this tab a fixed height and no scroll of its
            // own, and every mode is taller than it: the Game mode alone is a
            // slate strip, a scoreboard, a field, a bench row, a win
            // probability chart and a play-by-play. Without this the
            // play-by-play could not be reached at all - it had an inner
            // scroller of its own, which is precisely what disguised the bug,
            // because the part you could not get to was the part that scrolled.
            //
            // One axis, one scroller. The modes below therefore carry no
            // vertical ScrollView of their own: two of the same axis nested
            // means the inner one eats the drag and the outer never moves,
            // which on visionOS is a worse bug than the one being fixed.
            ScrollView(.vertical) {
                switch mode {
                case .mine: MyTeamField(focus: $focus)
                case .game: GameFieldView(event: $event, focus: $focus)
                case .red:  RedZoneField(focus: $focus)
                }
            }
            .scrollIndicators(.visible)
        }
        // Arriving with a game already named means somebody tapped a
        // scoreline to get here, so the field they asked for is what opens -
        // landing on "My Team" would silently ignore the tap.
        .onAppear { if !event.isEmpty { mode = .game } }
        .onChange(of: event) { _, new in if !new.isEmpty { mode = .game } }
    }

    private var switcher: some View {
        HStack(spacing: 8) {
            ForEach(Mode.allCases) { m in
                Button { mode = m } label: {
                    Label(m.rawValue, systemImage: m.icon)
                        .font(.system(size: 12, weight: .semibold))
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .plate(12, mode == m ? Theme.greenFill
                                             : .white.opacity(0.05))
                        .foregroundStyle(mode == m ? AnyShapeStyle(.white)
                                                   : AnyShapeStyle(.secondary))
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
            }
            Spacer(minLength: 0)
            Text(board.live?.source.map { "source: \($0)" } ?? "")
                .font(.system(size: 9)).foregroundStyle(.tertiary)
            LiveRefresh()
        }
    }

    /// Which line-up these fields are about.
    ///
    /// Absent rather than disabled with one league, the same rule the bottom
    /// bar follows: a picker offering a choice you do not have is chrome that
    /// exists to say the app was built for somebody else. It writes
    /// `board.lineupScope`, which is in the placement memo's key, so every
    /// mode narrows together rather than each keeping its own idea.
    @ViewBuilder
    private var scope: some View {
        if board.leagues.count > 1 {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    chip("All my line-ups", "")
                    ForEach(board.leagues, id: \.id) { L in chip(L.league, L.id) }
                }
            }
        }
    }

    private func chip(_ label: String, _ id: String) -> some View {
        let on = board.lineupScope == id
        return Button { board.lineupScope = id } label: {
            Text(label).font(.system(size: 10, weight: .semibold))
                .lineLimit(1)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .plate(10, on ? Theme.greenFill : .white.opacity(0.05))
                .foregroundStyle(on ? AnyShapeStyle(.white)
                                    : AnyShapeStyle(.secondary))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }
}


// MARK: - asking again, by hand

/// The manual refresh, and the only place on this tab that says a request is
/// happening.
///
/// The traced lattice is borrowed from the coming-soon screen rather than a
/// second loading language being invented for one button - that view's whole
/// argument for the effect is that it is honest over something that has no
/// figures of its own, and a control mid-request is exactly that. It is built
/// only while a fetch is in flight, so there is no schedule left holding a
/// frame callback the rest of the time, and it takes the same Reduce Motion
/// path: `NeuralTrace` draws one composed still instead.
struct LiveRefresh: View {
    @Environment(Board.self) private var board
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Button {
            // No stacking: `refreshLive` returns immediately when the timer
            // already has one in the air, so a fast double tap is one request.
            Task { await board.refreshLive() }
        } label: {
            HStack(spacing: 7) {
                ZStack {
                    if board.liveRefreshing {
                        NeuralTrace(animating: !reduceMotion, tint: Theme.green)
                            .frame(width: 34, height: 16)
                    }
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 10, weight: .semibold))
                        .opacity(board.liveRefreshing ? 0.25 : 1)
                }
                .frame(width: 34, height: 16)
                VStack(alignment: .leading, spacing: 0) {
                    Text(board.liveRefreshing ? "Reading" : "Refresh")
                        .font(.system(size: 10, weight: .semibold))
                    // What it is actually doing, not a spinner. The poll runs
                    // itself on a jittered half-minute; this says when the
                    // figures on screen were last true.
                    Text(board.liveFetchedAt.map {
                        $0.formatted(.dateTime.hour().minute().second())
                    } ?? "not yet")
                        .font(.system(size: 8)).foregroundStyle(.tertiary)
                        .monospacedDigit()
                }
            }
            .padding(.horizontal, 9).padding(.vertical, 5)
            .plate(10, board.liveRefreshing ? Theme.green.opacity(0.12)
                                            : .white.opacity(0.05))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
        .disabled(board.liveRefreshing)
    }
}


// MARK: - mode three: the twenty

/// Only the men whose game is inside the twenty.
///
/// No new endpoint and no new arithmetic: `/api/live` already carries
/// `redZone` per club, and `Gridiron.station` already knows whether a man can
/// score on the next snap - which for a defence is the snaps his club is not
/// attacking on, so a D/ST whose opponent is first and goal belongs here
/// exactly as much as the running back does.
struct RedZoneField: View {
    @Environment(Board.self) private var board
    @Binding var focus: String?

    var body: some View {
        let men = board.lineup().filter { $0.redZone }
        let live = men.filter { $0.station == .field }
        let waiting = men.filter { $0.station != .field }
        return VStack(spacing: 12) {
            Panel(title: "In the Twenty",
                  trailing: AnyView(Text(live.count == 1 ? "1 can score now"
                                         : "\(live.count) can score now")
                    .font(.system(size: 10)).foregroundStyle(.tertiary))) {
                if men.isEmpty {
                    // Said plainly rather than drawn as an empty field. For
                    // most of a Sunday this is the true answer, and a bare
                    // patch of grass reads as a view that failed to load.
                    NoSource(what: board.lineupScope.isEmpty
                             ? "Nobody you are starting is in a red zone right "
                               + "now. The feed reports one per game, so this "
                               + "fills the moment a drive reaches the twenty."
                             : "Nobody in this line-up is in a red zone right "
                               + "now.")
                } else {
                    field(live)
                }
            }
            if !waiting.isEmpty {
                Panel(title: "In the twenty, cannot score on this snap · \(waiting.count)") {
                    VStack(alignment: .leading, spacing: 7) {
                        ForEach(waiting) { m in row(m) }
                    }
                }
            }
        }
    }

    /// The last twenty yards, drawn at the size they deserve.
    ///
    /// `Gridiron.place` puts a man in the same 0-to-1 the full field uses, so
    /// this rescales that range to the twenty rather than re-deriving a
    /// position: one placement rule, two zooms.
    private func field(_ men: [FieldMan]) -> some View {
        GeometryReader { g in
            ZStack(alignment: .topLeading) {
                // Twenty yards, not a hundred rescaled: the numbers on the
                // grass have to agree with where the men are standing.
                FieldTurf(left: "THE 20", right: "END ZONE",
                          leftTint: Color(white: 0.13), rightTint: Theme.red,
                          yards: 20)
                ForEach(men.filter { $0.spot.x != nil }) { m in
                    FieldToken(man: m, selected: focus == m.id, size: 40) { focus = m.id }
                        .revealsHologram(m.id)
                        .position(x: FieldGeometry.px(
                                    FieldGeometry.redZone(m.spot.x ?? 0.9), g.size.width),
                                  y: CGFloat(m.spot.y) * g.size.height)
                        .animation(.spring(response: 0.6, dampingFraction: 0.85),
                                   value: m.spot)
                }
            }
        }
        .frame(height: 190)
    }

    private func row(_ m: FieldMan) -> some View {
        Button { focus = m.id } label: {
            HStack(spacing: 8) {
                FieldToken(man: m, selected: focus == m.id, size: 30, named: false)
                VStack(alignment: .leading, spacing: 1) {
                    Text("\(m.name) · \(m.pos) \(m.fixture)")
                        .font(.system(size: 10, weight: .semibold)).lineLimit(1)
                    Text(m.why).font(.system(size: 9)).foregroundStyle(.tertiary)
                        .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 5).padding(.horizontal, 8)
            .plate(11, focus == m.id ? Theme.green.opacity(0.14) : .white.opacity(0.05))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
        .revealsHologram(m.id)
    }
}

// MARK: - mode one: your men, on one field

/// Every man you are starting, anywhere, on a single field.
///
/// The field is the claim and the lanes underneath are the rest of it. A man
/// is only drawn on the grass when the feed says his club has the ball - or,
/// for a defence, that it does not - and every man off it carries the reason
/// in words, so the view can be disagreed with rather than just believed.
struct MyTeamField: View {
    @Environment(Board.self) private var board
    @Binding var focus: String?
    /// Which lanes the reader has unfolded. Per lane rather than one flag, so
    /// opening the finished list does not also unroll every kickoff window.
    @State private var opened: Set<String> = []

    /// One game's ball, for as many games as have men on this field. Drawn
    /// per game rather than once, because four of your men can be attacking
    /// four different lines of scrimmage at the same moment.
    struct Scrimmage: Identifiable, Hashable {
        let event: String, club: String, against: String
        let toEndzone: Int, down: Int?, distance: Int?, redZone: Bool
        var id: String { event }
        var at: String { Gridiron.spot(toEndzone: toEndzone, offence: club, defence: against) }
        var situation: String {
            [Gridiron.down(down, distance, toEndzone: toEndzone), "at \(at)"]
                .compactMap { $0 }.joined(separator: " ")
        }
    }

    /// How many tokens the grass can hold before it stops being a field.
    ///
    /// One league starts nine men and every one of them fits. Ten leagues
    /// start sixty-odd, and `Gridiron.lanes` hands out three to five lanes per
    /// position - past that they wrap onto each other and a field of faces is
    /// not readable at any size. So the grass takes the men with the most of
    /// your weeks riding on them and says in words how many it left off,
    /// rather than drawing a crowd or silently dropping anybody.
    private static let crowd = 18

    var body: some View {
        let men = board.lineup()
        let byStation = Dictionary(grouping: men, by: \.station)
        // Exposure first, then what he has actually scored: with one league
        // every man is in one line-up and this is just his points, which is
        // the right order there too.
        let onField = (byStation[.field] ?? [])
            .sorted { ($0.lineups, $0.points) > ($1.lineups, $1.points) }
        let drawn = Array(onField.prefix(Self.crowd))

        return VStack(spacing: 12) {
            Panel(title: "Your Men, Right Now", trailing: AnyView(counts(byStation))) {
                if men.isEmpty {
                    NoSource(what: board.scale.single
                             ? "No line-up loaded yet. The field fills from whoever "
                               + "you are starting this week."
                             : "No line-ups loaded yet. The field fills from "
                               + "whoever you are starting across your leagues.")
                } else {
                    field(drawn)
                    legend(drawn, crowded: onField.count - drawn.count)
                }
            }
            // Plain stack. This was a 360pt scroller inside a view that had
            // no scroller above it, which meant three lanes reachable and the
            // rest of the tab not; the tab's own scroller now carries all of
            // it. Each lane is still capped by `lane` with a "N more" button,
            // so the grids below stay bounded whoever is hosting them.
            bench(byStation[.bench] ?? [])
            sideline(byStation[.sideline] ?? [])
            finished(byStation[.done] ?? [])
        }
    }

    /// How long a lane may run before it folds. Bounded at every scale, and
    /// tighter once the roster is a portfolio: sixty rows under a field is a
    /// list nobody reads to the end of, and the tallies at the top already
    /// say how many there are.
    private var lane: Int { board.scale.many ? 12 : 24 }

    // MARK: the grass

    private func field(_ men: [FieldMan]) -> some View {
        GeometryReader { g in
            ZStack(alignment: .topLeading) {
                FieldTurf(left: "OWN GOAL", right: "END ZONE",
                          leftTint: Color(white: 0.13),
                          rightTint: Theme.navy)

                ForEach(scrimmages(men)) { s in
                    marker(s, in: g.size)
                }

                ForEach(men.filter { $0.spot.x != nil }) { m in
                    FieldToken(man: m, selected: focus == m.id, size: 42) { focus = m.id }
                        .revealsHologram(m.id)
                        .position(x: FieldGeometry.px(m.spot.x ?? 0.5, g.size.width),
                                  y: CGFloat(m.spot.y) * g.size.height)
                        // Spot is the whole placement, so a man slides when
                        // either the ball or his lane moves, rather than
                        // snapping to the next poll's arrangement.
                        .animation(.spring(response: 0.65, dampingFraction: 0.82),
                                   value: m.spot)
                }

                if men.isEmpty { quiet }
            }
        }
        .frame(height: 292)
    }

    /// What an empty field means, which for most of a week is the honest
    /// state of it. Nothing is invented here: the count and the kickoff are
    /// both read off the same slate the field is.
    private var quiet: some View {
        let waiting = board.lineup().filter { $0.station == .sideline }
        let next = waiting.min { $0.kickoff < $1.kickoff }
        let inThat = waiting.filter { $0.kickoff == next?.kickoff }.count
        return VStack(spacing: 7) {
            Image(systemName: "football")
                .font(.system(size: 26)).foregroundStyle(.white.opacity(0.35))
            Text("Nobody on your roster has the ball.")
                .font(.system(size: 14, weight: .semibold))
            if let n = next {
                Text("First ball at \(n.kickoffTime) — \(inThat) of your starters "
                     + "\(inThat == 1 ? "is" : "are") in that window.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Text("When a club takes possession its men walk on here, "
                 + "laid out by position against that game's line of scrimmage.")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).frame(maxWidth: 380)
        }
        // Backed rather than laid straight on the grass: white type over yard
        // numbers is unreadable at the exact size the numbers are drawn.
        .padding(.horizontal, 22).padding(.vertical, 16)
        .background(.black.opacity(0.55), in: .rect(cornerRadius: 18))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The line of scrimmage in one game, with the chain marker beside it.
    private func marker(_ s: Scrimmage, in size: CGSize) -> some View {
        let los = FieldGeometry.px(Gridiron.alongField(s.toEndzone), size.width)
        let chain = s.distance.map {
            FieldGeometry.px(Gridiron.alongField(max(0, s.toEndzone - $0)), size.width)
        }
        return ZStack(alignment: .topLeading) {
            FieldMarker(tint: .white, width: 2, strength: 0.85)
                .frame(height: size.height)
                .position(x: los, y: size.height / 2)
            if let c = chain {
                FieldMarker(tint: Theme.gold, width: 2, strength: 0.75)
                    .frame(height: size.height)
                    .position(x: c, y: size.height / 2)
            }
            Text("\(s.club) · \(s.situation)")
                .font(.system(size: 9, weight: .bold))
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(s.redZone ? AnyShapeStyle(Theme.redFill)
                                      : AnyShapeStyle(Color.black.opacity(0.72)),
                            in: .capsule)
                .fixedSize()
                .position(x: min(size.width - 60, max(60, los)), y: 10)
        }
        .animation(.spring(response: 0.65, dampingFraction: 0.85), value: s)
    }

    /// Distinct games, from the men standing in them. A defence on the field
    /// means the *other* club has the ball, which is why the attacking club
    /// is read off the man rather than assumed to be his own.
    private func scrimmages(_ men: [FieldMan]) -> [Scrimmage] {
        var seen: [String: Scrimmage] = [:]
        for m in men {
            guard let tz = m.toEndzone, !m.event.isEmpty, seen[m.event] == nil else { continue }
            seen[m.event] = Scrimmage(
                event: m.event,
                club: m.defence ? m.opp : m.team,
                against: m.defence ? m.team : m.opp,
                toEndzone: tz, down: m.down, distance: m.distance, redZone: m.redZone)
        }
        return seen.values.sorted { $0.event < $1.event }
    }

    private func legend(_ men: [FieldMan], crowded: Int = 0) -> some View {
        let unplaced = men.filter { $0.spot.x == nil }
        return VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 12) {
                key(.white, "line of scrimmage")
                key(Theme.gold, "line to gain")
                Text("every offence attacks to the right")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                Spacer(minLength: 0)
            }
            if crowded > 0 {
                HStack(alignment: .top, spacing: 6) {
                    MarkChip(mark: .caution, size: 8)
                    Text("\(crowded) more of your men have the ball than the field "
                         + "can hold. Drawn: the \(men.count) in most of your line-ups.")
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                }
            }
            if !unplaced.isEmpty {
                Text("On the field, spot not reported: "
                     + unplaced.map(\.name).joined(separator: ", "))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
    }

    private func key(_ c: Color, _ s: String) -> some View {
        HStack(spacing: 4) {
            Rectangle().fill(c).frame(width: 2, height: 10)
            Text(s).font(.system(size: 9)).foregroundStyle(.tertiary)
        }
    }

    private func counts(_ g: [Gridiron.Station: [FieldMan]]) -> some View {
        HStack(spacing: 10) {
            // The counts are ink; which state each is stays in the word
            // beside it. Four numbers in four hues was four things to decode
            // and none of them readable over a bright room.
            tally(g[.field]?.count ?? 0, "ON", .primary)
            tally(g[.bench]?.count ?? 0, "BENCHED", .primary)
            tally(g[.sideline]?.count ?? 0, "TO COME", .secondary)
            tally(g[.done]?.count ?? 0, "DONE", .tertiary)
        }
    }
    private func tally(_ n: Int, _ label: String, _ tint: some ShapeStyle) -> some View {
        HStack(spacing: 4) {
            Text("\(n)").font(.system(size: 13, weight: .bold)).monospacedDigit()
                .foregroundStyle(tint)
            Text(label).font(.system(size: 8, weight: .heavy)).kerning(0.7)
                .foregroundStyle(.tertiary)
        }
    }

    // MARK: the lanes

    private func bench(_ men: [FieldMan]) -> some View {
        Group {
            if !men.isEmpty {
                Panel(title: "Benched by possession · \(men.count)") {
                    Text("Their games are running, but they cannot score on the "
                         + "next snap.")
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                    grid(men, lane: "bench")
                }
            }
        }
    }

    /// Men whose games have not started, grouped by kickoff. For most of a
    /// week this is the whole view, so it is the part worth getting right:
    /// the useful question before Sunday is not "who is out" but "what goes
    /// off next, and how much of my team is in it".
    private func sideline(_ men: [FieldMan]) -> some View {
        let windows = Dictionary(grouping: men, by: \.kickoff)
            .sorted { $0.key < $1.key }
        return Group {
            if !men.isEmpty {
                Panel(title: "Yet to kick off · \(men.count)") {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(windows, id: \.key) { _, group in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(spacing: 8) {
                                    Image(systemName: "clock")
                                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                                    Text(group.first?.kickoffTime ?? "")
                                        .font(.system(size: 11, weight: .semibold))
                                    Text("\(group.count) of your starters")
                                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                                    Spacer(minLength: 0)
                                }
                                grid(group, lane: "kick-\(group.first?.kickoff ?? "")") { m in
                                    m.lineups == 1 ? "in 1 of your line-ups"
                                                   : "in \(m.lineups) of your line-ups"
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private func finished(_ men: [FieldMan]) -> some View {
        Group {
            if !men.isEmpty {
                Panel(title: "Done for the day · \(men.count)") {
                    grid(men, lane: "done", dim: true)
                }
            }
        }
    }

    /// Bounded by `lane`, which is now the only thing bounding it: a lazy
    /// grid handed unbounded height builds every row and fires every headshot
    /// request at once, which is exactly the bug this app had, and the 360pt
    /// scroller that used to sit above these lanes has gone so that the tab
    /// can scroll as one. The cap plus the "N more" button is the bound. Sixty finished
    /// men under a field is not a lane, it is a directory - and every one of
    /// those rows is a headshot request. Ordered by how many of your line-ups
    /// he is in before it folds, so what survives the fold is what matters
    /// most rather than whatever sorted first.
    private func grid(_ men: [FieldMan], lane key: String, dim: Bool = false,
                      note: @escaping (FieldMan) -> String = { $0.why }) -> some View {
        let ranked = board.scale.many
            ? men.sorted { ($0.lineups, $0.points) > ($1.lineups, $1.points) }
            : men
        let open = opened.contains(key)
        let shown = open ? ranked : Array(ranked.prefix(lane))
        return VStack(alignment: .leading, spacing: 8) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 196), spacing: 8)], spacing: 8) {
                // The whole card opens the man, and the face inside it is not
                // a control of its own - see the note on `FieldToken.tap`.
                // Off the grass this is a row about a player, and a row about
                // a player should be tappable everywhere on it, including the
                // half that is words.
                ForEach(shown) { m in
                    Button { focus = m.id } label: {
                        HStack(spacing: 8) {
                            FieldToken(man: m, selected: focus == m.id,
                                       size: 36, dimmed: dim)
                            VStack(alignment: .leading, spacing: 1) {
                                HStack(spacing: 5) {
                                    Chip(text: m.pos,
                                         fill: Theme.positionFill(m.pos), size: 8)
                                    Text(m.fixture)
                                        .font(.system(size: 9, weight: .semibold))
                                        .foregroundStyle(.secondary)
                                }
                                Text(note(m)).font(.system(size: 9))
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(2)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, 5).padding(.horizontal, 7)
                        .plate(12, focus == m.id ? Theme.green.opacity(0.14)
                                                 : .white.opacity(0.05))
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                    .revealsHologram(m.id)
                }
            }
            if ranked.count > lane {
                Button {
                    if open { opened.remove(key) } else { opened.insert(key) }
                } label: {
                    Text(open ? "Show fewer" : "\(ranked.count - lane) more")
                        .font(.system(size: 10, weight: .medium))
                        .padding(.horizontal, 11).padding(.vertical, 5)
                        .plate(10, .white.opacity(0.06))
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
            }
        }
    }
}
