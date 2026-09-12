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
                                HStack(spacing: 3) {
                                    if g.live { MarkDot(mark: .live, size: 5) }
                                    Text(g.label).font(.system(size: 8))
                                        .foregroundStyle(g.live ? AnyShapeStyle(.primary)
                                                                : AnyShapeStyle(.tertiary))
                                        .lineLimit(1)
                                }
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
        let ball = snap(gc)
        let men = placed(gc, ball)
        VStack(spacing: 12) {
            Panel(title: "\(gc.away.mark) at \(gc.home.mark)",
                  trailing: AnyView(HStack(spacing: 5) {
                    if gc.state == "in" { MarkDot(mark: .live, size: 6) }
                    Text(gc.clockLine)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(gc.state == "in" ? AnyShapeStyle(.primary)
                                                          : AnyShapeStyle(.secondary))
                  })) {
                scoreboard(gc, now?.play)
                field(gc, ball, men.on)
                situation(gc, ball)
                showing(now, ball)
            }
            mine(gc, men)
            HStack(alignment: .top, spacing: 12) {
                winProbability(gc, now?.play)
                    .frame(maxWidth: .infinity)
            }
            feed(gc)
        }
    }

    /// Your men in this game, stood where the play on screen puts them.
    ///
    /// The placement rule is `Gridiron.place`, the same one the cross-league
    /// field uses, rather than a second arrangement written for one game. What
    /// a single game adds is a real line of scrimmage: the shared live payload
    /// has one ball for the whole slate and this has the exact snap, so the
    /// offence lines up against it and the defence six yards the other side.
    ///
    /// State is taken from the play rather than from the club's live entry on
    /// purpose. Walking back through a finished game asks where a man stood
    /// *then*; reading `state` off the feed would answer "post" for every play
    /// and empty the field for the whole of a game that has been played.
    private func placed(_ gc: Gamecast,
                        _ ball: (drive: Drive, play: GamePlay)?) -> Squad {
        let men = board.lineup().filter { $0.event == gc.event }
        guard let ball, let from = ball.play.from else {
            return Squad(on: [], off: men)
        }
        let offence = ball.drive.team
        var taken: [String: Int] = [:]
        var on: [FieldMan] = [], off: [FieldMan] = []
        // Sorted before lanes are handed out, so a man keeps his lane from one
        // play to the next instead of swapping with whoever sorted beside him.
        for m in men.sorted(by: { ($0.pos, $0.name, $0.id) < ($1.pos, $1.name, $1.id) }) {
            let lane = taken[m.pos.uppercased(), default: 0]
            taken[m.pos.uppercased()] = lane + 1
            let spot = Gridiron.place(
                .init(pos: m.pos, state: "in",
                      attacking: m.team == offence, toEndzone: from),
                index: lane)
            let stood = m.standing(spot)
            if spot.station == .field { on.append(stood) } else { off.append(stood) }
        }
        return Squad(on: on, off: off)
    }

    struct Squad { let on: [FieldMan], off: [FieldMan] }

    /// The play on the field. Latest until the reader taps one, so a running
    /// game keeps up with itself and a finished one can be walked through.
    ///
    /// "Latest" means the latest *snap*, not the latest row. The feed's last
    /// entry in a finished game is END GAME, which carries `down 0, from 0,
    /// to 13`; timeouts and the two-minute warning come through the same
    /// shape. Handing those to the geometry puts the line of scrimmage on the
    /// goal line and stretches the gain line most of the way down the field,
    /// which is exactly the stray marker this view was reported for. So the
    /// ball falls back to the last row that was actually snapped, and
    /// `showing` says so in words rather than pretending the two are the same.
    private func current(_ gc: Gamecast) -> (drive: Drive, play: GamePlay)? {
        let all = gc.playsNewestFirst
        if let id = playID, let hit = all.first(where: { $0.play.id == id }) { return hit }
        return all.first
    }

    /// The play the *ball* is drawn from: the one on screen if it was a snap,
    /// else the most recent snap before it.
    private func snap(_ gc: Gamecast) -> (drive: Drive, play: GamePlay)? {
        let all = gc.playsNewestFirst
        let start = playID.flatMap { id in all.firstIndex { $0.play.id == id } } ?? 0
        return all[start...].first {
            Gridiron.isSnap(down: $0.play.down, from: $0.play.from)
        }
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
                        // The ball on an opaque disc: a gold glyph beside a
                        // club abbreviation is the smallest and faintest mark
                        // on the scoreboard, and it says who has possession.
                        Image(systemName: "football.fill")
                            .font(.system(size: 7)).foregroundStyle(.white)
                            .frame(width: 14, height: 14)
                            .background(Theme.goldFill, in: .circle)
                    }
                }
                Text(Int(score ?? 0), format: .number)
                    .font(.system(size: 24, weight: .heavy)).monospacedDigit()
                    .contentTransition(.numericText())
                    .animation(.easeInOut(duration: 0.4), value: score ?? 0)
            }
        }
    }

    /// The field, with the ball where this play left it and your men on it.
    ///
    /// The drive's club always attacks to the right, so the end zones are
    /// labelled by who is going which way rather than by home and away - which
    /// is also what clubs actually do, they swap ends every quarter.
    ///
    /// Three marks, all off one mapping in `Gridiron.marks`: the line of
    /// scrimmage at `from`, the line to gain at `from - distance`, and the
    /// ball at `to`. The arithmetic is out in `Gridiron` rather than in here
    /// because `verify_placement.swift` asserts it numerically - a snap from
    /// the 63 with three to gain lands at 470, 500 and 550 in a twelve-hundred
    /// unit box - and a field checked by eye is how the stray marker that
    /// prompted this got through in the first place.
    private func field(_ gc: Gamecast, _ ball: (drive: Drive, play: GamePlay)?,
                       _ men: [FieldMan]) -> some View {
        let offence = ball?.drive.team ?? gc.home.mark
        let defence = offence == gc.home.mark ? gc.away.mark : gc.home.mark
        let tints = [gc.home.mark: Color(feed: gc.home.color),
                     gc.away.mark: Color(feed: gc.away.color)]
        let p = ball?.play
        // Nil rather than a guess when the feed has not reported a snap. A
        // ball drawn on the fifty because there was nowhere else to put it is
        // a drawing of a number nobody published.
        let marks = p?.from.map {
            Gridiron.marks(from: $0, to: p?.to, down: p?.down, distance: p?.distance)
        }
        return GeometryReader { g in
            ZStack(alignment: .topLeading) {
                FieldTurf(left: offence, right: defence,
                          leftTint: tints[offence] ?? Color(white: 0.15),
                          rightTint: tints[defence] ?? Color(white: 0.15))

                if let m = marks {
                    let los = FieldGeometry.px(m.los, g.size.width)
                    let end = FieldGeometry.px(m.ball, g.size.width)
                    FieldMarker(tint: .white, width: 2)
                        .frame(height: g.size.height)
                        .position(x: los, y: g.size.height / 2)
                    if let gain = m.toGain {
                        FieldMarker(tint: Theme.gold, width: 2, strength: 0.8)
                            .frame(height: g.size.height)
                            .position(x: FieldGeometry.px(gain, g.size.width),
                                      y: g.size.height / 2)
                    }
                    Capsule()
                        .fill((m.ball >= m.los ? Theme.green : Theme.red).opacity(0.55))
                        .frame(width: max(2, abs(end - los)), height: 3)
                        .position(x: (end + los) / 2, y: g.size.height * 0.5)
                    // Gold as ink, and legitimately: the pitch under it is
                    // an opaque dark green this app paints, not the wearer's
                    // room, so the ground is known. 8.92:1 there against
                    // 1.02:1 on glass - the difference the whole palette rule
                    // is about. Measured by `apple/contrast_check.py`.
                    Image(systemName: "football.fill")
                        .font(.system(size: 17))
                        .foregroundStyle(Theme.gold)
                        .shadow(color: .black.opacity(0.6), radius: 4, y: 2)
                        .position(x: end, y: g.size.height / 2)
                }

                // Your men, on the grass rather than in a strip underneath it.
                // The strip was the whole of the original bug: it was the only
                // FieldToken in this file, it sat below the turf, and the
                // panel's height clipped it to a sliver.
                ForEach(men.filter { $0.spot.x != nil }) { m in
                    FieldToken(man: m, selected: focus == m.id, size: 38) { focus = m.id }
                        .revealsHologram(m.id)
                        .position(x: FieldGeometry.px(m.spot.x ?? 0.5, g.size.width),
                                  y: CGFloat(m.spot.y) * g.size.height)
                        .animation(.spring(response: 0.6, dampingFraction: 0.85),
                                   value: m.spot)
                }
            }
            // One animation for the whole arrangement: tapping a play twenty
            // rows back walks the ball there rather than teleporting it.
            .animation(.spring(response: 0.55, dampingFraction: 0.85), value: p)
        }
        // Taller than the 148 it was, because there are now men standing on
        // it: five lanes of tokens at 38 points need the room, and a field
        // that clips its own players is the bug this replaces.
        .frame(height: 210)
    }

    /// Which play the ball is drawn from, when that is not the row on screen.
    ///
    /// Said out loud rather than silently substituted. "END GAME" is a real
    /// row a reader can tap, and a field that quietly showed the snap before
    /// it while the feed row said something else would be a field disagreeing
    /// with the list beside it.
    @ViewBuilder
    private func showing(_ now: (drive: Drive, play: GamePlay)?,
                         _ ball: (drive: Drive, play: GamePlay)?) -> some View {
        if ball == nil {
            Text("No snap in this game yet, so there is no ball to place.")
                .font(.system(size: 10)).foregroundStyle(.tertiary)
        } else if let n = now, let b = ball, n.play.id != b.play.id {
            HStack(spacing: 6) {
                Image(systemName: "info.circle").font(.system(size: 9))
                Text("“\(n.play.text.prefix(40))” is not a snap, so the ball is "
                     + "where the last one left it.")
                    .font(.system(size: 10))
            }
            .foregroundStyle(.tertiary)
        }
    }

    /// Down, distance and spot, read off the snap the ball is drawn from.
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
                HStack(spacing: 4) {
                    MarkChip(mark: .of(Double(y), level: 0.5), size: 8)
                    Text(y >= 0 ? "+\(y) yds" : "\(y) yds")
                        .font(.system(size: 11, weight: .semibold))
                }
            }
            Spacer(minLength: 0)
            if let d = now?.drive, !d.description.isEmpty {
                Text("\(d.team) drive · \(d.description) · \(d.result)")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
    }

    /// The men who are not on the grass, and why not.
    ///
    /// Its own panel rather than a strip inside the field's: the strip was
    /// clipped to a sliver by the panel's height, which is what "cutting off
    /// the onfield players" was. Everyone who can score on this snap is now
    /// standing on the turf above; this is the rest of them, each carrying the
    /// reason he is not.
    @ViewBuilder
    private func mine(_ gc: Gamecast, _ squad: Squad) -> some View {
        let men = squad.off
        Panel(title: squad.on.isEmpty
              ? "Your Men in This Game"
              : "Not on This Snap · \(men.count)",
              trailing: AnyView(Text(squad.on.isEmpty ? ""
                                     : "\(squad.on.count) on the field")
                .font(.system(size: 9)).foregroundStyle(.tertiary))) {
        if men.isEmpty && squad.on.isEmpty {
            Text("None of your starters are in this game.")
                .font(.system(size: 10)).foregroundStyle(.tertiary)
        } else if men.isEmpty {
            Text("Every one of your men in this game can score on the next snap.")
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
                                        .foregroundStyle(m.points > 0 ? AnyShapeStyle(.primary)
                                                                      : AnyShapeStyle(.tertiary))
                                    // The reason, in words. A man off the
                                    // grass is a claim about his game, and a
                                    // claim the reader cannot see the grounds
                                    // for is one they have to take on trust.
                                    Text(m.defence ? "\(m.team) have the ball"
                                                   : "\(m.opp) have the ball")
                                        .font(.system(size: 8))
                                        .foregroundStyle(.tertiary).lineLimit(1)
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
            // Room for a whole chip. Left to itself inside a panel that is
            // also drawing a field, this row was given a sliver of height and
            // the tokens were cut in half.
            .frame(height: 46)
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
            if d.scored {
                Chip(text: (d.result.isEmpty ? "DRIVE" : d.result.uppercased()),
                     fill: Theme.goldFill, size: 9)
            } else {
                Text(d.result.isEmpty ? "Drive" : d.result)
                    .font(.system(size: 10, weight: .heavy))
                    .foregroundStyle(.secondary)
            }
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
                    Chip(text: p.scoring ? "SCORE" : "TURNOVER",
                         fill: p.scoring ? Theme.goldFill : Theme.redFill, size: 8)
                }
            }
            .padding(.vertical, 5).padding(.horizontal, 7)
            .plate(10, playID == p.id ? Theme.green.opacity(0.16)
                       : (p.scoring || p.turnover) ? tint.opacity(0.10) : .clear)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }
}
