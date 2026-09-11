import SwiftUI

// The three rails of the command centre. Split from `CommandView` only so
// neither file becomes the kind of thing nobody opens.
//
// Most of what is here forks on `board.scale`, and the fork is the point. A
// person with one league was being shown a rail listing one row, a picker with
// nothing to pick, and a cross-league panel whose three figures all restated
// the same league; a person with ten was being shown all ten of everything and
// could read none of it. Neither is a settings problem - the honest layout for
// one is not the layout for ten with a different row count.

extension CommandView {

    // MARK: - left: where you stand

    var leftRail: some View {
        ScrollView {
            VStack(spacing: 14) {
                switch board.scale {
                case .single:
                    thisLeague
                case .few:
                    myLeagues
                    crossLeague
                case .many:
                    attentionRail
                    crossLeague
                }
                needsAttention
                putAway
            }
        }
        .scrollIndicators(.hidden)
    }

    // MARK: one league

    /// With one league there is nothing to compare, so the league stops being
    /// a row in a list and becomes the subject: your seat in it, this week's
    /// margin, and where you sit in the table. Every figure here is about one
    /// team, which is the only thing that is true when there is one team.
    var thisLeague: some View {
        Group {
            if let f = board.attention().first {
                let m = f.mosaic
                Panel(title: f.league.league) {
                    VStack(spacing: 13) {
                        HStack(spacing: 13) {
                            ProbRing(value: m.winProb, size: 64)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(f.league.you.name)
                                    .font(.system(size: 15, weight: .bold))
                                    .lineLimit(1).minimumScaleFactor(0.7)
                                if let r = f.league.record, !r.line.isEmpty {
                                    Text("\(r.line) · \(r.place)")
                                        .font(.system(size: 11))
                                        .foregroundStyle(.secondary)
                                }
                                ReasonChip(reason: f.reason)
                            }
                            Spacer(minLength: 0)
                        }
                        Divider().opacity(0.2)
                        HStack(spacing: 6) {
                            StatTile(value: figure(m.yourProjected), label: "YOU")
                            StatTile(value: figure(m.oppProjected),
                                     label: (f.league.opp?.name ?? "OPPONENT")
                                        .uppercased())
                            StatTile(value: (m.margin >= 0 ? "+" : "") + figure(m.margin),
                                     label: "MARGIN",
                                     tint: m.margin >= 0 ? Theme.green : Theme.red)
                        }
                        HStack(spacing: 6) {
                            StatTile(value: board.rankSummary.value,
                                     label: board.rankSummary.label)
                            StatTile(value: f.league.record?.pointsFor
                                        .map { figure($0) } ?? "—", label: "POINTS FOR")
                            StatTile(value: "\(board.distinctPlayers)", label: "ROSTERED")
                        }
                    }
                }
            }
        }
    }

    // MARK: two to four

    /// Every league, in the order you arranged them. At this size the whole
    /// list fits and ranking it would only make it move about.
    var myLeagues: some View {
        Panel(title: "My Leagues") {
            VStack(spacing: 8) {
                ForEach(board.leagues, id: \.id) { L in
                    if let f = board.focus(L) { leagueRow(f) }
                }
            }
        }
    }

    // MARK: five and up

    /// The rail stops being a list of your leagues and becomes a list of the
    /// ones that need you. Ten rows in the order the server sent them is ten
    /// rows to read; ten in this order is one to read and nine to ignore. The
    /// rest are still there, one tap down, because "not urgent" is not the
    /// same as "gone".
    var attentionRail: some View {
        let ranked = board.attention()
        let head = railExpanded ? ranked : Array(ranked.prefix(4))
        return Panel(title: "Needs You First",
                     trailing: AnyView(
                        Text("\(ranked.count) leagues")
                            .font(.system(size: 10)).foregroundStyle(.tertiary))) {
            VStack(spacing: 8) {
                ForEach(head) { leagueRow($0) }
                if ranked.count > 4 {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            railExpanded.toggle()
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: railExpanded
                                  ? "chevron.up" : "chevron.down")
                                .font(.system(size: 9, weight: .bold))
                            Text(railExpanded ? "Show fewer"
                                 : ranked.count == 5 ? "1 quieter league"
                                 : "\(ranked.count - 4) quieter leagues")
                                .font(.system(size: 11, weight: .medium))
                        }
                        .frame(maxWidth: .infinity).padding(.vertical, 7)
                        .background(RoundedRectangle(cornerRadius: 11)
                            .fill(.white.opacity(0.05)))
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
            }
        }
    }

    /// One league in the rail. The same row at every scale, so a number does
    /// not change appearance depending on how many leagues sit beside it.
    func leagueRow(_ f: LeagueFocus) -> some View {
        Button { board.selected = f.league.id } label: {
            HStack(spacing: 11) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(f.league.league).font(.system(size: 13, weight: .semibold))
                        .lineLimit(1).minimumScaleFactor(0.7)
                    HStack(spacing: 5) {
                        if let r = f.league.record, !r.line.isEmpty {
                            Text(r.line).font(.system(size: 10, weight: .bold))
                                .monospacedDigit()
                            Text("·").foregroundStyle(.quaternary)
                            Text(r.place).font(.system(size: 10))
                        }
                    }
                    .foregroundStyle(.secondary)
                    ReasonChip(reason: f.reason)
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 2) {
                    ProbRing(value: f.mosaic.winProb, size: 42)
                    Text("\(figure(f.mosaic.yourProjected)) proj")
                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                        .monospacedDigit()
                }
            }
            .padding(.vertical, 8).padding(.horizontal, 10)
            .background {
                RoundedRectangle(cornerRadius: 14)
                    .fill(f.league.id == board.league?.id
                          ? Theme.green.opacity(0.14) : .white.opacity(0.05))
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .hoverEffect(.highlight)
        // Order and hidden are the two things the preferences file already
        // carries and the app could never write. Pinning and putting away are
        // the arrangement a ten-league rail needs, and neither invents a new
        // piece of state to hold it.
        .contextMenu {
            Button { Task { await board.pin(f.league.id) } } label: {
                Label("Pin to top", systemImage: "pin")
            }
            Button(role: .destructive) {
                Task { await board.hide(f.league.id) }
            } label: { Label("Hide this league", systemImage: "eye.slash") }
        }
    }

    /// What you have put away, and the way back. A hide with no undo is a bug:
    /// the board simply stops sending the league and nothing on any surface
    /// admits it exists.
    var putAway: some View {
        Group {
            if !board.hiddenLeagues.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "eye.slash").font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                    Text(board.hiddenLeagues.map(board.name(ofHidden:))
                            .joined(separator: ", "))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .lineLimit(2)
                    Spacer(minLength: 4)
                    Button("Show") { Task { await board.unhideAll() } }
                        .font(.system(size: 10, weight: .semibold))
                        .buttonStyle(.plain).foregroundStyle(Theme.green)
                }
                .padding(.horizontal, 14).padding(.vertical, 9)
                .background(RoundedRectangle(cornerRadius: 14).fill(.white.opacity(0.04)))
            }
        }
    }

    var crossLeague: some View {
        Panel(title: "Cross-League Overview") {
            let (w, l) = board.projectedRecord
            VStack(spacing: 12) {
                HStack(spacing: 6) {
                    StatTile(value: "\(board.leagues.count)", label: "LEAGUES")
                    StatTile(value: "\(board.distinctPlayers)", label: "PLAYERS")
                    StatTile(value: "\(w) - \(l)", label: "PROJECTED",
                             tint: w >= l ? Theme.green : Theme.red)
                }
                Divider().opacity(0.2)
                HStack(spacing: 6) {
                    StatTile(value: figure(board.totalProjected), label: "PROJ POINTS")
                    StatTile(value: (board.edgeOverOpponents >= 0 ? "+" : "")
                             + figure(board.edgeOverOpponents),
                             label: "VS OPPONENTS",
                             tint: board.edgeOverOpponents >= 0 ? Theme.green : Theme.red)
                    // Says "league rank" over one league and "avg rank" over
                    // several, and names how many reported one when they
                    // differ - a tile whose meaning drifts with the league
                    // count is worse than no tile.
                    StatTile(value: board.rankSummary.value,
                             label: board.rankSummary.label)
                }
            }
        }
    }

    /// Only what there is a source for. The injury wire is real; pending
    /// waiver claims and trade offers are not in any feed this reads, so they
    /// are absent rather than invented.
    var needsAttention: some View {
        Panel(title: "Needs Attention", badge: board.injuries.count) {
            VStack(spacing: 8) {
                if board.injuries.isEmpty {
                    NoSource(what: board.scale.single
                             ? "Nobody in your line-up is on the injury wire."
                             : "Nobody in your line-ups is on the injury wire.")
                }
                ForEach(board.injuries.prefix(5)) { inj in
                    HStack(spacing: 10) {
                        ZStack {
                            Circle().fill(severityTint(inj.severity).opacity(0.22))
                            Image(systemName: "cross.case.fill")
                                .font(.system(size: 12))
                                .foregroundStyle(severityTint(inj.severity))
                        }
                        .frame(width: 30, height: 30)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(inj.name).font(.system(size: 12, weight: .semibold))
                                    .lineLimit(1)
                                if let lab = inj.label {
                                    Text(lab).font(.system(size: 8, weight: .heavy))
                                        .padding(.horizontal, 5).padding(.vertical, 1)
                                        .background(severityTint(inj.severity).opacity(0.25),
                                                    in: .capsule)
                                        .foregroundStyle(severityTint(inj.severity))
                                }
                            }
                            Text(inj.headline ?? "")
                                .font(.system(size: 10)).foregroundStyle(.tertiary)
                                .lineLimit(2)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 6).padding(.horizontal, 9)
                    .background(RoundedRectangle(cornerRadius: 12).fill(.white.opacity(0.05)))
                }
            }
        }
    }

    func severityTint(_ s: String?) -> Color {
        switch (s ?? "").lowercased() {
        case "out", "ir": return Theme.red
        case "doubtful":  return Color.orange
        case "questionable": return Theme.gold
        default: return .secondary
        }
    }

    /// One decimal, which is the precision every score on this surface is at.
    func figure(_ v: Double) -> String {
        v.formatted(.number.precision(.fractionLength(1)))
    }

    // MARK: - centre: what is happening

    var centre: some View {
        ScrollView {
            VStack(spacing: 14) {
                weekHeader
                liveGames
                playersInAction
                opportunities
            }
        }
        .scrollIndicators(.hidden)
    }

    var weekHeader: some View {
        Panel(title: "Week \(board.league?.week ?? 0) Command Center") {
            switch board.scale {
            case .single: singleWeek
            case .few:    weekCards(board.attention())
            case .many:   weekDigest
            }
        }
    }

    /// One league, one matchup, drawn at the size it deserves rather than as
    /// a grid with one cell in it.
    var singleWeek: some View {
        Group {
            if let f = board.attention().first {
                let m = f.mosaic
                VStack(spacing: 12) {
                    HStack(alignment: .firstTextBaseline, spacing: 14) {
                        side(f.league.you.name, m.yourScore, m.yourProjected, lead: true)
                        Text("vs").font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(.tertiary)
                        side(f.league.opp?.name ?? "Opponent",
                             m.oppScore, m.oppProjected, lead: false)
                    }
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Capsule().fill(.white.opacity(0.14))
                            Capsule().fill(m.winProb >= 0.5 ? Theme.green : Theme.red)
                                .frame(width: max(4, g.size.width * m.winProb))
                        }
                    }
                    .frame(height: 6)
                    HStack {
                        Text("\(Int(m.winProb * 100))% win probability")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(m.winProb >= 0.5 ? Theme.green : Theme.red)
                        Spacer(minLength: 0)
                        Text(phrase(m)).font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                    }
                }
            } else {
                NoSource(what: "No matchup loaded for this week yet.")
            }
        }
    }

    private func side(_ name: String, _ score: Double, _ projected: Double,
                      lead: Bool) -> some View {
        VStack(alignment: lead ? .leading : .trailing, spacing: 2) {
            Text(name).font(.system(size: 11, weight: .semibold))
                .foregroundStyle(lead ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                .lineLimit(1).minimumScaleFactor(0.7)
            Text(figure(score))
                .font(.system(size: lead ? 40 : 32, weight: .bold)).monospacedDigit()
            Text("\(figure(projected)) projected")
                .font(.system(size: 10)).foregroundStyle(.tertiary).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: lead ? .leading : .trailing)
    }

    /// How far through the week this matchup is, said in words rather than as
    /// a phase string nobody outside the model would recognise.
    private func phrase(_ m: Mosaic) -> String {
        switch m.phase {
        case "pre":   return "nothing has kicked off"
        case "final": return "final"
        default:      return "live"
        }
    }

    /// The grid five leagues and up cannot use: it is exhaustive, and past
    /// four cards that stops being a header and becomes a wall.
    private func weekCards(_ focuses: [LeagueFocus]) -> some View {
        // Lazy inside the centre's ScrollView would be the bug this app
        // already shipped once - unbounded height defeats the laziness and
        // builds every row at once. It is safe here only because the caller
        // hard-bounds the count before it arrives.
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 10)],
                  spacing: 10) {
            ForEach(focuses) { f in weekCard(f) }
        }
    }

    private func weekCard(_ f: LeagueFocus) -> some View {
        let m = f.mosaic
        return Button { board.selected = f.league.id } label: {
            VStack(alignment: .leading, spacing: 7) {
                Text(f.league.league).font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary).lineLimit(1)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(figure(m.yourScore))
                        .font(.system(size: 26, weight: .bold)).monospacedDigit()
                    Spacer(minLength: 0)
                    Text(figure(m.oppScore))
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.secondary).monospacedDigit()
                }
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(.white.opacity(0.14))
                        Capsule().fill(m.winProb >= 0.5 ? Theme.green : Theme.red)
                            .frame(width: max(3, g.size.width * m.winProb))
                    }
                }
                .frame(height: 4)
                Text("\(Int(m.winProb * 100))% win prob")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 15)
                .fill(f.league.id == board.league?.id
                      ? Theme.green.opacity(0.12) : .white.opacity(0.05)))
            .contentShape(.rect)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    /// Ten scorelines summarised, then the ones still in question drawn in
    /// full and the ones already answered folded onto one line each.
    ///
    /// The three counts add up to the league count, whatever it is. That is
    /// the condition a summary has to meet before it may replace a list:
    /// nothing has been dropped, only collapsed.
    var weekDigest: some View {
        let ranked = board.attention()
        let (ahead, doubt, behind) = board.weekTally()
        let open = ranked.filter { !$0.decided }
        let shut = ranked.filter(\.decided)
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                StatTile(value: "\(ahead)", label: "AHEAD", tint: Theme.green)
                StatTile(value: "\(doubt)", label: "IN DOUBT", tint: Theme.gold)
                StatTile(value: "\(behind)", label: "BEHIND", tint: Theme.red)
            }
            if weekExpanded {
                weekCards(ranked)
            } else {
                if open.isEmpty {
                    NoSource(what: "Every matchup this week has an answer already.")
                } else {
                    // Bounded before it reaches the grid: past six cards the
                    // header is a wall again, and the rest are one tap away.
                    // They are the six that need you most, because `open`
                    // arrives in attention order.
                    weekCards(Array(open.prefix(6)))
                    if open.count > 6 {
                        // Deliberately not "still in question": the tile above
                        // reads IN DOUBT and counts a different thing - a
                        // matchup inside four-to-six on win probability - and
                        // two phrases that sound the same must not mean two
                        // different sets on one panel.
                        Text(open.count - 6 == 1
                             ? "1 quieter matchup, not shown"
                             : "\(open.count - 6) quieter matchups, not shown")
                            .font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                }
                if !shut.isEmpty {
                    VStack(spacing: 5) {
                        ForEach(shut) { decidedRow($0) }
                    }
                }
            }
            // Offered only when something is actually folded away, so the
            // button never promises to reveal nothing.
            if weekExpanded || open.count > 6 || !shut.isEmpty {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { weekExpanded.toggle() }
                } label: {
                    Text(weekExpanded ? "Summarise" : "Show all \(ranked.count) matchups")
                        .font(.system(size: 11, weight: .medium))
                        .frame(maxWidth: .infinity).padding(.vertical, 7)
                        .background(RoundedRectangle(cornerRadius: 11)
                            .fill(.white.opacity(0.05)))
                        .contentShape(.rect)
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
            }
        }
    }

    /// A matchup with an answer, on one line. It keeps its scoreline - it is
    /// collapsed, not hidden.
    private func decidedRow(_ f: LeagueFocus) -> some View {
        let m = f.mosaic
        let won = m.winProb >= 0.5
        return Button { board.selected = f.league.id } label: {
            HStack(spacing: 9) {
                Circle().fill(won ? Theme.green : Theme.red).frame(width: 6, height: 6)
                Text(f.league.league).font(.system(size: 11))
                    .lineLimit(1).minimumScaleFactor(0.7)
                Spacer(minLength: 6)
                Text("\(figure(m.yourScore)) – \(figure(m.oppScore))")
                    .font(.system(size: 11, weight: .semibold)).monospacedDigit()
                Text(f.reason.label).font(.system(size: 9))
                    .foregroundStyle(.tertiary).frame(width: 74, alignment: .trailing)
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 10).fill(.white.opacity(0.04)))
            .contentShape(.rect)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    /// The slate. Abbreviations, score and clock all come from the shared live
    /// tier, which is the same payload for everybody - that is what makes it
    /// cacheable, and why it costs nothing to show all of it.
    var liveGames: some View {
        Panel(title: "Live Games") {
            let games = (board.live?.games ?? [:])
                .sorted { ($0.value.kickoff ?? "") < ($1.value.kickoff ?? "") }
            if games.isEmpty {
                NoSource(what: "No slate reported yet.")
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(pairs(games), id: \.key) { g in
                            HStack(spacing: 9) {
                                ClubMark(abbr: g.home, size: 24)
                                VStack(spacing: 1) {
                                    Text(g.score).font(.system(size: 13, weight: .bold))
                                        .monospacedDigit()
                                    Text(g.label).font(.system(size: 8))
                                        .foregroundStyle(g.live ? AnyShapeStyle(Theme.green) : AnyShapeStyle(.tertiary))
                                        .lineLimit(1)
                                }
                                .frame(minWidth: 54)
                                ClubMark(abbr: g.away, size: 24)
                            }
                            .padding(.horizontal, 11).padding(.vertical, 8)
                            .background(RoundedRectangle(cornerRadius: 13)
                                .fill(.white.opacity(0.05)))
                        }
                    }
                }
            }
        }
    }

    /// The live tier reports per club, so a game is two club entries that
    /// share a kickoff and a label. Pairing them back up here keeps that
    /// shape out of the payload, which other surfaces rely on.
    struct GamePair: Hashable {
        let key: String, home: String, away: String
        let score: String, label: String, live: Bool
    }
    func pairs(_ games: [(key: String, value: GameState)]) -> [GamePair] {
        var byKick: [String: [(String, GameState)]] = [:]
        for (ab, g) in games {
            byKick[(g.kickoff ?? "") + (g.label ?? ""), default: []].append((ab, g))
        }
        return byKick.compactMap { _, v -> GamePair? in
            guard v.count == 2 else { return nil }
            let a = v[0], b = v[1]
            let sa = a.1.score ?? "0", sb = b.1.score ?? "0"
            let state = a.1.state ?? "pre"
            return GamePair(key: a.0 + b.0, home: a.0, away: b.0,
                            score: state == "pre" ? "vs" : "\(sa) – \(sb)",
                            label: a.1.label ?? "", live: state == "in")
        }
        .sorted { $0.key < $1.key }
    }

    /// Your men, across every league, ordered by what is at stake now.
    ///
    /// The cap and the order both move with the league count. One league has
    /// nine starters and showing eight of them is an arbitrary truncation of
    /// a list that fits; ten leagues have sixty-odd, and the ones worth the
    /// space are the men you are exposed to more than once, because those are
    /// the ones a single afternoon decides several weeks with.
    var playersInAction: some View {
        Panel(title: "My Players in Action") {
            let live = board.live?.players ?? [:]
            let many = board.scale.many
            let men = board.roster.sorted { a, b in
                if many, a.startedIn != b.startedIn { return a.startedIn > b.startedIn }
                let la = live[a.id]?.s ?? -1, lb = live[b.id]?.s ?? -1
                if la != lb { return la > lb }
                return (a.projected ?? 0) > (b.projected ?? 0)
            }
            let cap = board.scale.single ? 9 : (many ? 12 : 8)
            // Bounded by `cap` before the grid sees it - see `weekCards`.
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 168), spacing: 10)],
                      spacing: 10) {
                ForEach(men.prefix(cap)) { p in
                    Button { focus = p.id } label: {
                        HStack(spacing: 9) {
                            Headshot(url: p.img, name: p.name,
                                     tint: Theme.position(p.pos), size: 40)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(p.name).font(.system(size: 11, weight: .semibold))
                                    .lineLimit(1).minimumScaleFactor(0.7)
                                Text("\(p.pos) · \(p.team)")
                                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                                Text("\(figure(p.projected ?? 0)) proj")
                                    .font(.system(size: 9)).foregroundStyle(.secondary)
                                    .monospacedDigit()
                                if let s = live[p.id]?.s, s > 0 {
                                    Text("\(figure(s)) live")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(Theme.green).monospacedDigit()
                                }
                                // Exposure is only a fact worth the line when
                                // there is more than one league to be exposed
                                // to. "1 league" under every man is noise.
                                if !board.scale.single {
                                    Text(p.exposure == 1 ? "1 league"
                                                         : "\(p.exposure) leagues")
                                        .font(.system(size: 8, weight: .heavy))
                                        .foregroundStyle(p.exposure > 1
                                                         ? AnyShapeStyle(Theme.gold)
                                                         : AnyShapeStyle(.tertiary))
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(9)
                        .background(RoundedRectangle(cornerRadius: 14)
                            .fill(focus == p.id ? Theme.green.opacity(0.14)
                                                : .white.opacity(0.05)))
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
            }
            if men.count > cap {
                Text(men.count - cap == 1
                     ? "1 more of your men is playing today."
                     : "\(men.count - cap) more of your men are playing today.")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
            }
        }
    }

    /// Men on today's slate that nobody in any league you follow rosters.
    /// "Available" here is a fact about your leagues, not a guess: the
    /// rankings payload carries who owns each player, and this is the empty
    /// set of that.
    var opportunities: some View {
        Panel(title: "Today's Top Opportunities") {
            let free = board.ranked.filter(\.isFree)
                .sorted { ($0.projected ?? 0) > ($1.projected ?? 0) }
            if free.isEmpty {
                NoSource(what: board.scale.single
                         ? "Everybody on today's slate is rostered in your league."
                         : "Everybody on today's slate is rostered in your leagues.")
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 168), spacing: 10)],
                          spacing: 10) {
                    ForEach(free.prefix(4)) { p in
                        Button { focus = p.id } label: {
                            HStack(spacing: 9) {
                                Headshot(url: "https://a.espncdn.com/i/headshots/nfl/players/full/\(p.id).png",
                                         name: p.name, tint: Theme.position(p.pos), size: 38)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(p.name).font(.system(size: 11, weight: .semibold))
                                        .lineLimit(1).minimumScaleFactor(0.7)
                                    Text("\(p.pos) · \(p.team)")
                                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                                    // "free in all 1" is not a sentence.
                                    Text(board.scale.single ? "free in your league"
                                         : "free in all \(board.leagues.count)")
                                        .font(.system(size: 8, weight: .heavy))
                                        .foregroundStyle(.tertiary)
                                    Text("+\(figure(p.projected ?? 0)) proj")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(Theme.green).monospacedDigit()
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(9)
                            .background(RoundedRectangle(cornerRadius: 14)
                                .fill(.white.opacity(0.05)))
                            .contentShape(.rect)
                        }
                        .buttonStyle(.plain).hoverEffect(.highlight)
                    }
                }
            }
        }
    }
}

/// Why a league is where it is in the rail, in three words and a colour.
struct ReasonChip: View {
    let reason: LeagueFocus.Reason
    var body: some View {
        Text(reason.label)
            .font(.system(size: 9, weight: .heavy)).kerning(0.3)
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(reason.tint.opacity(0.18), in: .capsule)
            .foregroundStyle(reason.tint)
    }
}
