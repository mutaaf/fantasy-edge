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
        case mine = "My Team", game = "Game"
        var id: String { rawValue }
        var icon: String { self == .mine ? "person.2.badge.gearshape" : "sportscourt" }
    }

    var body: some View {
        VStack(spacing: 12) {
            switcher
            switch mode {
            case .mine: MyTeamField(focus: $focus)
            case .game: GameFieldView(event: $event, focus: $focus)
            }
            Spacer(minLength: 0)
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
                        .background(RoundedRectangle(cornerRadius: 12)
                            .fill(mode == m ? Theme.green.opacity(0.18) : .white.opacity(0.05)))
                        .foregroundStyle(mode == m ? AnyShapeStyle(Theme.green)
                                                   : AnyShapeStyle(.secondary))
                        .contentShape(.rect)
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
            }
            Spacer(minLength: 0)
            Text(board.live?.source.map { "source: \($0)" } ?? "")
                .font(.system(size: 9)).foregroundStyle(.tertiary)
        }
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
            ScrollView {
                VStack(spacing: 12) {
                    bench(byStation[.bench] ?? [])
                    sideline(byStation[.sideline] ?? [])
                    finished(byStation[.done] ?? [])
                }
            }
            .frame(maxHeight: 360)
            .scrollIndicators(.hidden)
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
                .background((s.redZone ? Theme.red : Color.black).opacity(0.72), in: .capsule)
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
                Text("\(crowded) more of your men have the ball than the field "
                     + "can hold. Drawn: the \(men.count) in most of your line-ups.")
                    .font(.system(size: 9)).foregroundStyle(Theme.gold)
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
            tally(g[.field]?.count ?? 0, "ON", Theme.green)
            tally(g[.bench]?.count ?? 0, "BENCHED", Theme.red)
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

    /// Bounded above by the scroll view this lives in, which is the point:
    /// a lazy grid handed unbounded height builds every row and fires every
    /// headshot request at once, which is exactly the bug this app had.
    ///
    /// Bounded again by `lane` once the roster is a portfolio. Sixty finished
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
                                Text("\(m.pos) · \(m.fixture)")
                                    .font(.system(size: 9, weight: .semibold))
                                    .foregroundStyle(Theme.position(m.pos))
                                Text(note(m)).font(.system(size: 9))
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(2)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, 5).padding(.horizontal, 7)
                        .background(RoundedRectangle(cornerRadius: 12)
                            .fill(focus == m.id ? Theme.green.opacity(0.14)
                                                : .white.opacity(0.05)))
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
            }
            if ranked.count > lane {
                Button {
                    if open { opened.remove(key) } else { opened.insert(key) }
                } label: {
                    Text(open ? "Show fewer" : "\(ranked.count - lane) more")
                        .font(.system(size: 10, weight: .medium))
                        .padding(.horizontal, 11).padding(.vertical, 5)
                        .background(RoundedRectangle(cornerRadius: 10)
                            .fill(.white.opacity(0.06)))
                        .contentShape(.rect)
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
            }
        }
    }
}
