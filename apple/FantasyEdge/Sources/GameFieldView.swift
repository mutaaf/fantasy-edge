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
    @Environment(\.openWindow) private var openWindow
    @State private var showReplays = false
    @Binding var event: String
    @Binding var focus: String?
    /// The play the field is showing. Nil means "the latest one", which is
    /// what a running game should do on its own as plays arrive.
    @State private var playID: String?
    /// Whether the feed is showing every drive or only the recent ones. See
    /// `feed` for why this is a cap rather than a lazy stack.
    @State private var allDrives = false
    private static let drivesShown = 6

    /// Whether the field stays put while the feed below it is read. Owned by
    /// `LiveView`, so it is one setting across both fields.
    var pinned: Bool = true

    /// Whose men the list under the field is about, and which positions.
    ///
    /// "Mine" is the question a cross-league board exists to answer. "Everyone"
    /// is the one it could not answer until the gamecast started carrying the
    /// whole box score: a game scores twenty-odd men and a four-league board
    /// names a dozen of them, so the rest were invisible - you could see your
    /// receiver's eight catches and not the nine by the man opposite him.
    @State private var everyone = false
    @State private var wantPos = ""

    /// Playing the game out, one play a beat.
    ///
    /// It drives `playID`, which is the same thing tapping a row in the feed
    /// sets, so the ball, the situation line, the win-probability cursor and
    /// the selected row all follow it - there is no second copy of "where are
    /// we" for them to disagree about.
    @State private var walking = false
    @State private var speed = 1
    private static let beat: Duration = .milliseconds(1100)

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
        .onChange(of: chosen) { _, _ in
            // A walk that survived a change of game would be moving a
            // different field out from under the reader.
            playID = nil; allDrives = false; walking = false
        }
        .task(id: walkKey) { await walk() }
    }

    /// Restarted whenever anything the walk depends on changes: switching it
    /// off, changing speed, or picking another game all cancel the sleep in
    /// flight rather than letting it land one more play late.
    private var walkKey: String { "\(walking)|\(speed)|\(chosen)" }

    private func walk() async {
        guard walking else { return }
        while !Task.isCancelled && walking {
            try? await Task.sleep(for: Self.beat / speed)
            guard !Task.isCancelled, walking,
                  let gc = board.gamecasts[chosen] else { return }
            let all = gc.playsNewestFirst
            let at = playID.flatMap { id in all.firstIndex { $0.play.id == id } } ?? 0
            // Newest first, so walking forwards in the game is walking
            // backwards through the list. Index zero is the live play: there
            // is nowhere left to go, so the walk stops and hands the field
            // back to following the game.
            guard at > 0 else { playID = nil; walking = false; return }
            let next = all[at - 1]
            playID = next.play.id
            // A score gets a beat longer. It is the one thing on the field a
            // reader wants a moment with, and at 4x a drive goes past
            // otherwise.
            if next.play.scoring {
                try? await Task.sleep(for: Self.beat / speed)
            }
        }
    }

    private func load() async {
        guard !chosen.isEmpty else { return }
        await board.loadGamecast(chosen, finished: game?.finished ?? false)
    }

    // MARK: - the slate

    private var picker: some View {
        HStack(spacing: 8) {
            slateStrip
            // A real 3D field for the chosen game, on the table in front of
            // you; from there the stadium is one tap away.
            Button {
                openWindow(id: "tabletop", value: chosen)
            } label: {
                Label("View in 3D", systemImage: "cube.transparent")
                    .font(.system(size: 13, weight: .semibold)).frame(minHeight: 44)
            }
            .disabled(chosen.isEmpty)
            Button { showReplays = true } label: {
                Label("Replay a game", systemImage: "gobackward")
                    .font(.system(size: 13, weight: .semibold)).frame(minHeight: 44)
            }
        }
        .sheet(isPresented: $showReplays) {
            ReplayPicker { openWindow(id: "tabletop", value: StadiumHost.replayWindow) }
        }
    }

    private var slateStrip: some View {
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
            if pinned { grass(gc, now, ball, men) }
            ScrollView(.vertical) {
                VStack(spacing: 12) {
                    if !pinned { grass(gc, now, ball, men) }
                    who(gc, men)
                    HStack(alignment: .top, spacing: 12) {
                        winProbability(gc, now?.play)
                            .frame(maxWidth: .infinity)
                    }
                    feed(gc)
                }
            }
            .scrollIndicators(.visible)
        }
    }

    /// The field and everything read off the same snap. Pinned or not, this
    /// is one unit: a scoreboard showing a play the field is not drawing
    /// would be two answers to one question.
    private func grass(_ gc: Gamecast, _ now: (drive: Drive, play: GamePlay)?,
                       _ ball: (drive: Drive, play: GamePlay)?,
                       _ men: Squad) -> some View {
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
            walkBar(gc, now)
            showing(now, ball)
        }
    }

    // MARK: - walking the game

    /// Play out every play, or step to one.
    ///
    /// A slider over the play *index* rather than the clock: plays are what
    /// the feed publishes and what the field can be placed at, and scrubbing
    /// a clock would mean interpolating between two of them and putting the
    /// ball somewhere the game never had it.
    @ViewBuilder
    private func walkBar(_ gc: Gamecast,
                         _ now: (drive: Drive, play: GamePlay)?) -> some View {
        let all = gc.playsNewestFirst
        if all.count > 1 {
            let at = playID.flatMap { id in all.firstIndex { $0.play.id == id } } ?? 0
            // The slider reads oldest-first, which is how a game is watched.
            let ord = Double(all.count - 1 - at)
            HStack(spacing: 10) {
                Button { walking.toggle() } label: {
                    Image(systemName: walking ? "pause.fill" : "play.fill")
                        .font(.system(size: 11, weight: .bold))
                        .frame(width: 30, height: 26)
                        .plate(8, walking ? Theme.greenFill : .white.opacity(0.06))
                        .foregroundStyle(walking ? AnyShapeStyle(.white)
                                                 : AnyShapeStyle(.secondary))
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
                .help(walking ? "Stop" : "Play out every play from here")

                // Continuous, and rounded in the setter. A `step:` of one
                // over a hundred and seventy plays makes SwiftUI draw a tick
                // per play, which on a 300pt track is a dotted line rather
                // than a scale.
                Slider(value: Binding(
                    get: { ord },
                    set: { v in
                        walking = false
                        let idx = all.count - 1 - Int(v.rounded())
                        playID = idx <= 0 ? nil : all[max(0, min(all.count - 1, idx))].play.id
                    }), in: 0...Double(all.count - 1))
                    .tint(Theme.green)
                    .frame(minWidth: 120)

                Text("\(Int(ord) + 1)/\(all.count)")
                    .font(.system(size: 10)).monospacedDigit()
                    .foregroundStyle(.tertiary)

                Button { speed = speed == 4 ? 1 : speed * 2 } label: {
                    Text("\(speed)×").font(.system(size: 10, weight: .bold))
                        .frame(width: 30, height: 26)
                        .plate(8, .white.opacity(0.06))
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
                .help("Playback speed")

                Button { walking = false; playID = nil } label: {
                    Text("LIVE").font(.system(size: 9, weight: .heavy))
                        .padding(.horizontal, 9).frame(height: 26)
                        .plate(8, playID == nil ? Theme.greenFill : .white.opacity(0.06))
                        .foregroundStyle(playID == nil ? AnyShapeStyle(.white)
                                                       : AnyShapeStyle(.secondary))
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
                .disabled(playID == nil)
                .help("Follow the live play")
            }
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

    // MARK: - who is in this game

    /// Two scopes over one list. Mine is the men off the grass and why they
    /// are off it; Everyone is the whole box score, which is the only place
    /// the men on nobody's roster exist.
    @ViewBuilder
    private func who(_ gc: Gamecast, _ men: Squad) -> some View {
        VStack(spacing: 8) {
            // All of it left-aligned. Pushed to the trailing edge with a
            // Spacer, the last position chip sat flush against the window's
            // rounded edge and the K was clipped in half - this row is not
            // inside a Panel, so it has none of a panel's inset to save it.
            HStack(spacing: 7) {
                scopeChip("My men", on: !everyone) { everyone = false }
                scopeChip("Everyone", on: everyone) { everyone = true }
                if everyone {
                    Rectangle().fill(.white.opacity(0.14))
                        .frame(width: 1, height: 16).padding(.horizontal, 3)
                    ForEach(["", "QB", "RB", "WR", "TE", "K"], id: \.self) { p in
                        scopeChip(p.isEmpty ? "All" : p, on: wantPos == p) { wantPos = p }
                    }
                }
                Spacer(minLength: 0)
            }
            if everyone { everybody(gc) } else { mine(gc, men) }
        }
    }

    private func scopeChip(_ label: String, on: Bool,
                           _ tap: @escaping () -> Void) -> some View {
        Button(action: tap) {
            Text(label).font(.system(size: 10, weight: .semibold))
                .padding(.horizontal, 9).padding(.vertical, 4)
                .plate(9, on ? Theme.greenFill : .white.opacity(0.05))
                .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.secondary))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    /// The whole box score, mine marked.
    ///
    /// Which of these men are yours is personal and static between
    /// transactions; the box score is shared and changes every poll. So they
    /// are intersected here, on ids, rather than the server computing a
    /// different gamecast for every reader - which is the rule the whole live
    /// tier is built on.
    ///
    /// The points differ by whose man it is, on purpose. One of yours shows
    /// what his own league scored him, because that is the number that
    /// decides your week; everyone else shows this install's scoring, which
    /// is the only rule available to score a stranger under.
    @ViewBuilder
    private func everybody(_ gc: Gamecast) -> some View {
        let ours = Dictionary(board.lineup().map { ($0.id, $0) },
                              uniquingKeysWith: { a, _ in a })
        let rows = gc.players.filter { $0.skill && $0.matches(wantPos) }
        Panel(title: "Everyone in This Game · \(rows.count)",
              trailing: AnyView(Text(gc.state == "post" ? "final" : "so far")
                .font(.system(size: 9)).foregroundStyle(.tertiary))) {
            if gc.players.isEmpty {
                NoSource(what: gc.state == "pre"
                         ? "No box score until this game is under way."
                         : "The feed published no box score for this game.")
            } else if rows.isEmpty {
                Text("Nobody in this game plays that position.")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(rows) { r in
                        strangerRow(r, mine: ours[r.id],
                                    tint: r.team == gc.home.mark
                                          ? Color(feed: gc.home.color, fallback: Theme.green)
                                          : Color(feed: gc.away.color, fallback: Theme.navy))
                    }
                }
            }
        }
    }

    private func strangerRow(_ r: GamePlayer, mine: FieldMan?,
                             tint: Color) -> some View {
        Button { focus = r.id } label: {
            HStack(spacing: 9) {
                Headshot(url: r.img, name: r.name, tint: tint, size: 30)
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 5) {
                        Text(r.name).font(.system(size: 11, weight: .semibold))
                            .lineLimit(1)
                        if mine != nil {
                            Chip(text: "YOURS", fill: Theme.greenFill, size: 8)
                        }
                    }
                    Text("\(r.badge) · \(r.team) · \(r.line)")
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
                Text(mine?.points ?? r.points,
                     format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 13, weight: .bold)).monospacedDigit()
                    .foregroundStyle((mine?.points ?? r.points) > 0
                                     ? AnyShapeStyle(.primary) : AnyShapeStyle(.tertiary))
            }
            .padding(.vertical, 5).padding(.horizontal, 8)
            .plate(10, focus == r.id ? Theme.green.opacity(0.16)
                       : mine != nil ? Theme.green.opacity(0.07) : .white.opacity(0.04))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
        .revealsHologram(r.id)
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

    /// The play-by-play, newest drive first.
    ///
    /// No scroller of its own. It used to have one, 200pt tall, and that is
    /// what hid the real bug: this whole view is taller than the window and
    /// had nothing above it that scrolled, so the feed was below the fold and
    /// unreachable - and its inner scroller made the mistake look deliberate.
    /// `LiveView` owns the one vertical scroller now, and nesting a second on
    /// the same axis inside it would let the inner one swallow the drag while
    /// the outer stayed put.
    ///
    /// Which leaves the laziness question the old `LazyVStack` was answering.
    /// It is answered by the cap instead: a full game is about a hundred and
    /// seventy rows, and this shows the most recent `Self.drivesShown` drives
    /// until asked for the rest. That is the same "N more" idiom the line-up
    /// lanes use, and unlike a lazy stack it is honest about how much is
    /// hidden. The rows themselves are plain text - no headshots - so the
    /// 18%-CPU incident that made this app wary of eager stacks does not
    /// apply here; that was a hundred and twenty rows each firing two image
    /// requests.
    private func feed(_ gc: Gamecast) -> some View {
        let drives = Array(gc.drives.reversed())
        let shown = allDrives ? drives : Array(drives.prefix(Self.drivesShown))
        let hidden = drives.count - shown.count
        return Panel(title: "Play by Play",
              trailing: AnyView(Text(playID == nil ? "latest" : "tap a play to move the ball")
                .font(.system(size: 9)).foregroundStyle(.tertiary))) {
            if gc.drives.isEmpty {
                NoSource(what: "No drives in this game yet.")
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(shown) { d in
                        driveHeader(d)
                        ForEach(d.plays.reversed()) { p in row(p) }
                    }
                    if hidden > 0 || allDrives {
                        Button {
                            allDrives.toggle()
                        } label: {
                            Text(allDrives
                                 ? "Show the latest \(Self.drivesShown) drives"
                                 : "\(hidden) earlier \(hidden == 1 ? "drive" : "drives")")
                                .font(.system(size: 11, weight: .medium))
                                .padding(.horizontal, 12).padding(.vertical, 6)
                                .plate(10, .white.opacity(0.06))
                        }
                        .buttonStyle(.plain).hoverEffect(.highlight)
                        .padding(.top, 6)
                    }
                }
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
