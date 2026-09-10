import SwiftUI

// The three rails of the command centre. Split from `CommandView` only so
// neither file becomes the kind of thing nobody opens.

extension CommandView {

    // MARK: - left: where you stand

    var leftRail: some View {
        ScrollView {
            VStack(spacing: 14) {
                myLeagues
                crossLeague
                needsAttention
            }
        }
        .scrollIndicators(.hidden)
    }

    var myLeagues: some View {
        Panel(title: "My Leagues") {
            VStack(spacing: 8) {
                ForEach(board.leagues, id: \.id) { L in
                    let mo = board.mosaic(for: L)
                    Button { board.selected = L.id } label: {
                        HStack(spacing: 11) {
                            ClubMark(abbr: "nfl", size: 0).frame(width: 0)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(L.league).font(.system(size: 13, weight: .semibold))
                                    .lineLimit(1).minimumScaleFactor(0.7)
                                HStack(spacing: 5) {
                                    if let r = L.record, !r.line.isEmpty {
                                        Text(r.line).font(.system(size: 10, weight: .bold))
                                            .monospacedDigit()
                                        Text("·").foregroundStyle(.quaternary)
                                        Text(r.place).font(.system(size: 10))
                                    }
                                }
                                .foregroundStyle(.secondary)
                                Text("\(mo.yourProjected, format: .number.precision(.fractionLength(1))) proj")
                                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                                    .monospacedDigit()
                            }
                            Spacer(minLength: 4)
                            ProbRing(value: mo.winProb, size: 42)
                        }
                        .padding(.vertical, 8).padding(.horizontal, 10)
                        .background {
                            RoundedRectangle(cornerRadius: 14)
                                .fill(L.id == board.league?.id
                                      ? Theme.green.opacity(0.14) : .white.opacity(0.05))
                        }
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain)
                    .hoverEffect(.highlight)
                }
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
                    StatTile(value: board.totalProjected
                                .formatted(.number.precision(.fractionLength(1))),
                             label: "PROJ POINTS")
                    StatTile(value: (board.edgeOverOpponents >= 0 ? "+" : "")
                             + board.edgeOverOpponents
                                .formatted(.number.precision(.fractionLength(1))),
                             label: "VS OPPONENTS",
                             tint: board.edgeOverOpponents >= 0 ? Theme.green : Theme.red)
                    StatTile(value: board.averageRank.map {
                        "#" + $0.formatted(.number.precision(.fractionLength(1)))
                    } ?? "—", label: "AVG RANK")
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
                    NoSource(what: "Nobody in your line-ups is on the injury wire.")
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
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 10)],
                      spacing: 10) {
                ForEach(board.leagues, id: \.id) { L in
                    let mo = board.mosaic(for: L)
                    VStack(alignment: .leading, spacing: 7) {
                        Text(L.league).font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.secondary).lineLimit(1)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(mo.yourScore, format: .number.precision(.fractionLength(1)))
                                .font(.system(size: 26, weight: .bold)).monospacedDigit()
                            Spacer(minLength: 0)
                            Text(mo.oppScore, format: .number.precision(.fractionLength(1)))
                                .font(.system(size: 15, weight: .medium))
                                .foregroundStyle(.secondary).monospacedDigit()
                        }
                        GeometryReader { g in
                            ZStack(alignment: .leading) {
                                Capsule().fill(.white.opacity(0.14))
                                Capsule()
                                    .fill(mo.winProb >= 0.5 ? Theme.green : Theme.red)
                                    .frame(width: max(3, g.size.width * mo.winProb))
                            }
                        }
                        .frame(height: 4)
                        Text("\(Int(mo.winProb * 100))% win prob")
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                    }
                    .padding(11)
                    .background(RoundedRectangle(cornerRadius: 15).fill(.white.opacity(0.05)))
                }
            }
        }
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
    var playersInAction: some View {
        Panel(title: "My Players in Action") {
            let live = board.live?.players ?? [:]
            let men = board.roster.sorted { a, b in
                let la = live[a.id]?.s ?? -1, lb = live[b.id]?.s ?? -1
                if la != lb { return la > lb }
                return (a.projected ?? 0) > (b.projected ?? 0)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 168), spacing: 10)],
                      spacing: 10) {
                ForEach(men.prefix(8)) { p in
                    Button { focus = p.id } label: {
                        HStack(spacing: 9) {
                            Headshot(url: p.img, name: p.name,
                                     tint: Theme.position(p.pos), size: 40)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(p.name).font(.system(size: 11, weight: .semibold))
                                    .lineLimit(1).minimumScaleFactor(0.7)
                                Text("\(p.pos) · \(p.team)")
                                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                                Text("\((p.projected ?? 0), format: .number.precision(.fractionLength(1))) proj")
                                    .font(.system(size: 9)).foregroundStyle(.secondary)
                                    .monospacedDigit()
                                if let s = live[p.id]?.s, s > 0 {
                                    Text("\(s, format: .number.precision(.fractionLength(1))) live")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(Theme.green).monospacedDigit()
                                }
                                Text(p.exposure == 1 ? "1 league" : "\(p.exposure) leagues")
                                    .font(.system(size: 8, weight: .heavy))
                                    .foregroundStyle(.tertiary)
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
                NoSource(what: "Everybody on today's slate is rostered in your leagues.")
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
                                    Text("free in all \(board.leagues.count)")
                                        .font(.system(size: 8, weight: .heavy))
                                        .foregroundStyle(.tertiary)
                                    Text("+\((p.projected ?? 0), format: .number.precision(.fractionLength(1))) proj")
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
