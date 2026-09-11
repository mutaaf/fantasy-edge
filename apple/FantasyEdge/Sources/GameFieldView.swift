import SwiftUI

/// One game, on a field, with its play-by-play and the win probability the
/// feed published beside it.
///
/// Exactly one gamecast is open at a time and it is fetched per *event*, never
/// per club: both clubs in a game carry the same event id, so asking per club
/// would fetch the same drives twice. A finished game is fetched once and kept,
/// because its drives cannot change.
struct GameFieldView: View {
    @Environment(Board.self) private var board
    @Binding var event: String
    @Binding var focus: String?
    /// The play the field is showing. Nil means "the latest one", which is
    /// what a running game should do on its own as plays arrive.
    @State private var playID: String?

    /// Nothing is picked until the reader picks it, so the default is the
    /// game most worth looking at: one that is running, else the last one
    /// that finished.
    private var chosen: String {
        if !event.isEmpty { return event }
        let s = board.slate
        return (s.first { $0.live } ?? s.last { $0.finished } ?? s.first)?.event ?? ""
    }
    private var game: Board.SlateGame? { board.slate.first { $0.event == chosen } }

    var body: some View {
        VStack(spacing: 12) {
            picker
            if chosen.isEmpty {
                Panel(title: "Game") { NoSource(what: "No slate reported yet.") }
            } else if let gc = board.gamecasts[chosen] {
                cast(gc)
            } else if let why = board.gamecastMissing[chosen] {
                Panel(title: game?.line ?? "Game") {
                    NoSource(what: why)
                    if let g = game, !g.finished {
                        Text("Kickoff \(g.kickoff). Drives appear once the game "
                             + "is under way.")
                            .font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                }
            } else {
                Panel(title: game?.line ?? "Game") {
                    HStack { Spacer(); ProgressView(); Spacer() }.padding(.vertical, 24)
                }
            }
        }
        .task(id: chosen) { await load() }
        // A running game gets new drives when the shared live payload moves,
        // and only then - polling the gamecast on its own clock would ask for
        // a field of plays that had not changed.
        .onChange(of: board.live?.version ?? "") { _, _ in Task { await load() } }
        .onChange(of: chosen) { _, _ in playID = nil }
    }

    private func load() async {
        guard !chosen.isEmpty else { return }
        await board.loadGamecast(chosen, finished: game?.finished ?? false)
    }

    // MARK: - the slate

    private var picker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(board.slate) { g in
                    Button { event = g.event } label: {
                        HStack(spacing: 7) {
                            ClubMark(abbr: g.away, size: 18)
                            VStack(spacing: 1) {
                                Text(g.state == "pre" ? "vs" : "\(g.awayScore)–\(g.homeScore)")
                                    .font(.system(size: 11, weight: .bold)).monospacedDigit()
                                Text(g.label).font(.system(size: 8))
                                    .foregroundStyle(g.live ? AnyShapeStyle(Theme.green)
                                                            : AnyShapeStyle(.tertiary))
                                    .lineLimit(1)
                            }
                            .frame(minWidth: 48)
                            ClubMark(abbr: g.home, size: 18)
                        }
                        .padding(.horizontal, 9).padding(.vertical, 6)
                        .plate(12, g.event == chosen ? Theme.green.opacity(0.16)
                                                     : .white.opacity(0.05))
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
            }
            .padding(.vertical, 1)
        }
    }

    // MARK: - the game

    @ViewBuilder
    private func cast(_ gc: Gamecast) -> some View {
        let now = current(gc)
        VStack(spacing: 12) {
            Panel(title: "\(gc.away.mark) at \(gc.home.mark)",
                  trailing: AnyView(Text(gc.clockLine)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(gc.state == "in" ? AnyShapeStyle(Theme.green)
                                                      : AnyShapeStyle(.secondary)))) {
                scoreboard(gc, now?.play)
                field(gc, now)
                situation(gc, now)
                mine(gc)
            }
            HStack(alignment: .top, spacing: 12) {
                winProbability(gc, now?.play)
                    .frame(maxWidth: .infinity)
            }
            feed(gc)
        }
    }

    /// The play on the field. Latest until the reader taps one, so a running
    /// game keeps up with itself and a finished one can be walked through.
    private func current(_ gc: Gamecast) -> (drive: Drive, play: GamePlay)? {
        let all = gc.playsNewestFirst
        if let id = playID, let hit = all.first(where: { $0.play.id == id }) { return hit }
        return all.first
    }

    private func scoreboard(_ gc: Gamecast, _ p: GamePlay?) -> some View {
        HStack(spacing: 14) {
            side(gc.away, score: p?.away ?? gc.away.score, ball: hasBall(gc, gc.away))
            Text("–").font(.system(size: 18)).foregroundStyle(.tertiary)
            side(gc.home, score: p?.home ?? gc.home.score, ball: hasBall(gc, gc.home))
            Spacer(minLength: 0)
        }
    }

    private func hasBall(_ gc: Gamecast, _ s: GameSide) -> Bool {
        guard let poss = gc.possession, !poss.isEmpty else { return false }
        return poss == s.id
    }

    private func side(_ s: GameSide, score: Double?, ball: Bool) -> some View {
        HStack(spacing: 8) {
            ClubMark(abbr: s.mark, size: 28)
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 4) {
                    Text(s.mark).font(.system(size: 12, weight: .bold))
                    if ball {
                        Image(systemName: "football.fill")
                            .font(.system(size: 9)).foregroundStyle(Theme.gold)
                    }
                }
                Text(Int(score ?? 0), format: .number)
                    .font(.system(size: 24, weight: .heavy)).monospacedDigit()
                    .contentTransition(.numericText())
                    .animation(.easeInOut(duration: 0.4), value: score ?? 0)
            }
        }
    }

    /// The field, with the ball where this play left it.
    ///
    /// The drive's club always attacks to the right, so the end zones are
    /// labelled by who is going which way rather than by home and away - which
    /// is also what clubs actually do, they swap ends every quarter.
    private func field(_ gc: Gamecast, _ now: (drive: Drive, play: GamePlay)?) -> some View {
        let offence = now?.drive.team ?? gc.home.mark
        let defence = offence == gc.home.mark ? gc.away.mark : gc.home.mark
        let tints = [gc.home.mark: Color(feed: gc.home.color),
                     gc.away.mark: Color(feed: gc.away.color)]
        let p = now?.play
        return GeometryReader { g in
            ZStack(alignment: .topLeading) {
                FieldTurf(left: offence, right: defence,
                          leftTint: tints[offence] ?? Color(white: 0.15),
                          rightTint: tints[defence] ?? Color(white: 0.15))

                if let from = p?.from {
                    let los = FieldGeometry.px(Gridiron.alongField(from), g.size.width)
                    FieldMarker(tint: .white, width: 2)
                        .frame(height: g.size.height)
                        .position(x: los, y: g.size.height / 2)
                    if let dist = p?.distance, (p?.down ?? 0) > 0 {
                        FieldMarker(tint: Theme.gold, width: 2, strength: 0.8)
                            .frame(height: g.size.height)
                            .position(x: FieldGeometry.px(
                                Gridiron.alongField(max(0, from - dist)), g.size.width),
                                      y: g.size.height / 2)
                    }
                    if let to = p?.to {
                        let end = FieldGeometry.px(Gridiron.alongField(to), g.size.width)
                        Capsule()
                            .fill((to <= from ? Theme.green : Theme.red).opacity(0.55))
                            .frame(width: max(2, abs(end - los)), height: 3)
                            .position(x: (end + los) / 2, y: g.size.height / 2)
                        Image(systemName: "football.fill")
                            .font(.system(size: 17))
                            .foregroundStyle(Theme.gold)
                            .shadow(color: .black.opacity(0.6), radius: 4, y: 2)
                            .position(x: end, y: g.size.height / 2)
                    }
                }
            }
            // One animation for the whole arrangement: tapping a play twenty
            // rows back walks the ball there rather than teleporting it.
            .animation(.spring(response: 0.55, dampingFraction: 0.85), value: p)
        }
        .frame(height: 148)
    }

    private func situation(_ gc: Gamecast,
                           _ now: (drive: Drive, play: GamePlay)?) -> some View {
        let p = now?.play
        let offence = now?.drive.team ?? ""
        let defence = offence == gc.home.mark ? gc.away.mark : gc.home.mark
        return HStack(spacing: 10) {
            if let dd = Gridiron.down(p?.down, p?.distance, toEndzone: p?.from) {
                Text(dd).font(.system(size: 12, weight: .bold))
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(Theme.navy.opacity(0.7), in: .capsule)
            }
            if let from = p?.from, !offence.isEmpty, (p?.down ?? 0) > 0 {
                Text("at " + Gridiron.spot(toEndzone: from, offence: offence,
                                           defence: defence))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            if let y = p?.yards, (p?.down ?? 0) > 0 {
                Text(y >= 0 ? "+\(y) yds" : "\(y) yds")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(y >= 0 ? Theme.green : Theme.red)
            }
            Spacer(minLength: 0)
            if let d = now?.drive, !d.description.isEmpty {
                Text("\(d.team) drive · \(d.description) · \(d.result)")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
    }

    /// Whichever of your men are in this game. The point of a cross-league
    /// board is that a game only matters through the men you own in it.
    @ViewBuilder
    private func mine(_ gc: Gamecast) -> some View {
        let men = board.lineup().filter { $0.event == gc.event }
        if men.isEmpty {
            Text("None of your starters are in this game.")
                .font(.system(size: 10)).foregroundStyle(.tertiary)
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    // One target per man, on the whole chip. The face was the
                    // only tappable part before, which put a small control
                    // inside a larger thing that looked like one.
                    ForEach(men) { m in
                        Button { focus = m.id } label: {
                            HStack(spacing: 7) {
                                FieldToken(man: m, selected: focus == m.id,
                                           size: 28, named: false)
                                VStack(alignment: .leading, spacing: 0) {
                                    Text(m.name).font(.system(size: 10, weight: .semibold))
                                        .lineLimit(1)
                                    Text("\(m.pos) · \(m.points, format: .number.precision(.fractionLength(1))) pts")
                                        .font(.system(size: 9)).monospacedDigit()
                                        .foregroundStyle(m.points > 0 ? AnyShapeStyle(Theme.green)
                                                                      : AnyShapeStyle(.tertiary))
                                }
                            }
                            .padding(.horizontal, 7).padding(.vertical, 4)
                            .plate(11, focus == m.id ? Theme.green.opacity(0.14)
                                                     : .white.opacity(0.05))
                        }
                        .buttonStyle(.plain).hoverEffect(.highlight)
                        .revealsHologram(m.id)
                    }
                }
            }
        }
    }

    // MARK: - win probability

    @ViewBuilder
    private func winProbability(_ gc: Gamecast, _ p: GamePlay?) -> some View {
        let wp = board.winProb(gc)
        Panel(title: "Win Probability") {
            if wp.home.count < 2 {
                NoSource(what: "The feed published no win probability for this game.")
            } else {
                WinProbChart(series: wp.home, home: gc.home.mark, away: gc.away.mark,
                             homeTint: Color(feed: gc.home.color, fallback: Theme.green),
                             awayTint: Color(feed: gc.away.color, fallback: Theme.red),
                             scores: wp.scoring,
                             cursor: p.flatMap { play in
                                 wp.plays.firstIndex(of: play.id) })
                    .frame(height: 78)
                HStack(spacing: 8) {
                    if let last = wp.last {
                        Text("\(gc.home.mark) \(Int((last * 100).rounded()))%")
                            .font(.system(size: 12, weight: .bold)).monospacedDigit()
                        Text("\(gc.away.mark) \(Int(((1 - last) * 100).rounded()))%")
                            .font(.system(size: 12, weight: .bold)).monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Text("ESPN's series, one point per play. Gold ticks are scores.")
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                }
            }
        }
    }

    // MARK: - play by play

    private func feed(_ gc: Gamecast) -> some View {
        Panel(title: "Play by Play",
              trailing: AnyView(Text(playID == nil ? "latest" : "tap a play to move the ball")
                .font(.system(size: 9)).foregroundStyle(.tertiary))) {
            if gc.drives.isEmpty {
                NoSource(what: "No drives in this game yet.")
            } else {
                // Bounded on purpose. A lazy stack inside a parent offering
                // unbounded height builds every one of a hundred and seventy
                // rows before the first frame.
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(gc.drives.reversed()) { d in
                            driveHeader(d)
                            ForEach(d.plays.reversed()) { p in row(p) }
                        }
                    }
                }
                .frame(maxHeight: 200)
                .scrollIndicators(.visible)
            }
        }
    }

    private func driveHeader(_ d: Drive) -> some View {
        HStack(spacing: 7) {
            ClubMark(abbr: d.team, size: 15)
            Text(d.result.isEmpty ? "Drive" : d.result)
                .font(.system(size: 10, weight: .heavy))
                .foregroundStyle(d.scored ? Theme.gold : .secondary)
            Text(d.description).font(.system(size: 9)).foregroundStyle(.tertiary)
            Spacer(minLength: 0)
        }
        .padding(.top, 6).padding(.horizontal, 4)
    }

    private func row(_ p: GamePlay) -> some View {
        let tint: Color = p.scoring ? Theme.gold : (p.turnover ? Theme.red : .clear)
        return Button { playID = p.id } label: {
            HStack(alignment: .top, spacing: 9) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(p.period.map { $0 > 4 ? "OT" : "Q\($0)" } ?? "")
                        .font(.system(size: 8, weight: .heavy)).foregroundStyle(.tertiary)
                    Text(p.clock).font(.system(size: 10)).monospacedDigit()
                        .foregroundStyle(.secondary)
                }
                .frame(width: 34, alignment: .leading)
                if let dd = Gridiron.down(p.down, p.distance, toEndzone: p.from) {
                    Text(dd).font(.system(size: 9, weight: .bold))
                        .frame(width: 52, alignment: .leading)
                        .foregroundStyle(.secondary)
                } else {
                    Spacer().frame(width: 52)
                }
                Text(p.text).font(.system(size: 11))
                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if p.scoring || p.turnover {
                    Text(p.scoring ? "SCORE" : "TURNOVER")
                        .font(.system(size: 8, weight: .heavy))
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(tint.opacity(0.25), in: .capsule)
                        .foregroundStyle(tint)
                }
            }
            .padding(.vertical, 5).padding(.horizontal, 7)
            .plate(10, playID == p.id ? Theme.green.opacity(0.16)
                       : (p.scoring || p.turnover) ? tint.opacity(0.10) : .clear)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }
}
