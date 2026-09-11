import SwiftUI

/// One league, in full: the line-up, the week's matchups, and the table.
///
/// The command centre answers "how am I doing everywhere". This answers "what
/// is happening here", which is a different question and needs the thing the
/// other view deliberately does not show - every slot, including the bench.
struct LeagueView: View {
    @Environment(Board.self) private var board
    @Binding var focus: String?
    @State private var tab: Sub = .roster
    @State private var group: Group_ = .starters

    enum Sub: String, CaseIterable, Identifiable {
        case overview = "Overview", roster = "Roster"
        case matchups = "Matchups", standings = "Standings"
        var id: String { rawValue }
    }
    enum Group_: String, CaseIterable, Identifiable {
        case starters = "Starters", bench = "Bench", ir = "IR"
        var id: String { rawValue }
    }

    private var L: LeaguePayload? { board.league }

    var body: some View {
        VStack(spacing: 14) {
            if let L {
                header(L)
                statStrip(L)
                switch tab {
                case .overview:  overview(L)
                case .roster:    rosterTable(L)
                case .matchups:  matchups(L)
                case .standings: standingsTable(L)
                }
            } else {
                Panel(title: "League") { NoSource(what: "No league selected.") }
            }
        }
        .task(id: L?.id) { if let L { await board.loadStandings(L) } }
    }

    // MARK: - header

    private func header(_ L: LeaguePayload) -> some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: "trophy.fill").font(.system(size: 22))
                    .foregroundStyle(Theme.gold)
                VStack(alignment: .leading, spacing: 2) {
                    Text(L.league).font(.system(size: 21, weight: .bold))
                        .lineLimit(1).minimumScaleFactor(0.6)
                    // Only what the payload actually knows. Scoring format is
                    // not in it, so it is not claimed.
                    Text("\(L.teams?.count ?? 0) team · \(L.provider.uppercased()) · \(String(L.season))")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                HStack(spacing: 10) {
                    Text("Week \(L.week)").font(.system(size: 13, weight: .semibold))
                }
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(Capsule().fill(.white.opacity(0.08)))
            }
            HStack(spacing: 6) {
                ForEach(Sub.allCases) { s in
                    Button { tab = s } label: {
                        Text(s.rawValue).font(.system(size: 12, weight: .medium))
                            .padding(.horizontal, 14).padding(.vertical, 7)
                            .background(Capsule().fill(tab == s ? Theme.green.opacity(0.20)
                                                                : .white.opacity(0.05)))
                            .foregroundStyle(tab == s ? AnyShapeStyle(Theme.green)
                                                      : AnyShapeStyle(.secondary))
                            .contentShape(.capsule)
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
                Spacer(minLength: 0)
            }
        }
        .padding(16)
        .glassBackgroundEffect(in: .rect(cornerRadius: 22))
    }

    private func statStrip(_ L: LeaguePayload) -> some View {
        let m = board.mosaic(for: L)
        return HStack(spacing: 10) {
            strip(L.record?.line ?? "—", L.record?.place ?? "record")
            strip(m.yourProjected.formatted(.number.precision(.fractionLength(1))),
                  "proj points")
            strip(m.oppProjected.formatted(.number.precision(.fractionLength(1))),
                  "opponent proj")
            VStack(alignment: .leading, spacing: 5) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 22, weight: .bold)).monospacedDigit()
                    .foregroundStyle(m.winProb >= 0.5 ? Theme.green : Theme.red)
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(.white.opacity(0.14))
                        Capsule().fill(m.winProb >= 0.5 ? Theme.green : Theme.red)
                            .frame(width: max(3, g.size.width * m.winProb))
                    }
                }
                .frame(height: 4)
                Text("WIN PROBABILITY").font(.system(size: 8, weight: .heavy))
                    .kerning(0.8).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14).padding(.vertical, 11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 16).fill(.white.opacity(0.05)))
        }
    }

    private func strip(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value).font(.system(size: 22, weight: .bold)).monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.6)
            Text(label.uppercased()).font(.system(size: 8, weight: .heavy))
                .kerning(0.8).foregroundStyle(.tertiary).lineLimit(1)
        }
        .padding(.horizontal, 14).padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16).fill(.white.opacity(0.05)))
    }

    // MARK: - roster

    /// Your side of the league, every slot. Starters and bench come from the
    /// provider's own started flag rather than being inferred from the slot
    /// name, because a FLEX and a BN look alike to anything that guesses.
    private func rosterTable(_ L: LeaguePayload) -> some View {
        let mine = (L.roster ?? []).filter { $0.teamId == L.you.teamId }
        let rows: [RosterEntry]
        switch group {
        case .starters: rows = mine.filter { $0.started == true }
        case .bench:    rows = mine.filter { $0.started != true && !isIR($0) }
        case .ir:       rows = mine.filter(isIR)
        }
        return Panel(title: "Line-up", trailing: AnyView(groupPicker)) {
            if rows.isEmpty {
                NoSource(what: group == .ir ? "Nobody on injured reserve."
                                            : "No players stored for this slot.")
            } else {
                VStack(spacing: 0) {
                    headerRow
                    ForEach(sorted(rows)) { r in rosterRow(r) }
                }
            }
        }
    }

    private func isIR(_ r: RosterEntry) -> Bool {
        let s = (r.slot ?? "").uppercased()
        return s == "IR" || s == "INJURY RESERVE"
    }

    /// Slot order the way a line-up card reads, not alphabetically.
    private func sorted(_ rows: [RosterEntry]) -> [RosterEntry] {
        let order = ["QB": 0, "RB": 1, "WR": 2, "TE": 3, "FLEX": 4, "OP": 4,
                     "D/ST": 5, "DEF": 5, "K": 6]
        return rows.sorted {
            let a = order[($0.slot ?? "").uppercased()] ?? 9
            let b = order[($1.slot ?? "").uppercased()] ?? 9
            if a != b { return a < b }
            return ($0.projected ?? 0) > ($1.projected ?? 0)
        }
    }

    private var groupPicker: some View {
        HStack(spacing: 5) {
            ForEach(Group_.allCases) { g in
                Button { group = g } label: {
                    Text(g.rawValue).font(.system(size: 10, weight: .semibold))
                        .padding(.horizontal, 11).padding(.vertical, 5)
                        .background(Capsule().fill(group == g ? Theme.green.opacity(0.22)
                                                              : .white.opacity(0.06)))
                        .foregroundStyle(group == g ? AnyShapeStyle(Theme.green)
                                                    : AnyShapeStyle(.secondary))
                        .contentShape(.capsule)
                }
                .buttonStyle(.plain).hoverEffect(.highlight)
            }
        }
    }

    private var headerRow: some View {
        HStack(spacing: 10) {
            Text("POS").frame(width: 46, alignment: .leading)
            Text("PLAYER").frame(maxWidth: .infinity, alignment: .leading)
            Text("OPP").frame(width: 74, alignment: .leading)
            Text("PROJ").frame(width: 52, alignment: .trailing)
            Text("ACTUAL").frame(width: 58, alignment: .trailing)
            Text("STATUS").frame(width: 92, alignment: .trailing)
        }
        .font(.system(size: 8, weight: .heavy)).kerning(0.8)
        .foregroundStyle(.tertiary)
        .padding(.vertical, 7).padding(.horizontal, 4)
    }

    private func rosterRow(_ r: RosterEntry) -> some View {
        let fx = board.fixtures[r.team]
        let live = board.live?.players[r.id]
        return Button { focus = r.id } label: {
            HStack(spacing: 10) {
                Text((r.slot ?? "").uppercased())
                    .font(.system(size: 10, weight: .heavy))
                    .frame(width: 46, alignment: .leading)
                    .foregroundStyle(Theme.position(r.pos))

                HStack(spacing: 9) {
                    Headshot(url: r.img, name: r.name,
                             tint: Theme.position(r.pos), size: 30)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(r.name).font(.system(size: 12, weight: .medium))
                            .lineLimit(1).minimumScaleFactor(0.7)
                        Text("\(r.pos) · \(r.team)").font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Text(fx?.line ?? "—").font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(width: 74, alignment: .leading)

                Text((r.projected ?? 0), format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 12)).monospacedDigit()
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .trailing)

                // A dash, not a zero, before his game has started. Zero is a
                // score; "has not played" is not.
                Group {
                    if let s = live?.s, (fx?.state ?? "pre") != "pre" {
                        Text(s, format: .number.precision(.fractionLength(1)))
                            .foregroundStyle(s > 0 ? AnyShapeStyle(Theme.green)
                                                   : AnyShapeStyle(.secondary))
                    } else {
                        Text("–").foregroundStyle(.tertiary)
                    }
                }
                .font(.system(size: 13, weight: .semibold)).monospacedDigit()
                .frame(width: 58, alignment: .trailing)

                Text(status(fx)).font(.system(size: 10))
                    .foregroundStyle(fx?.live == true ? AnyShapeStyle(Theme.green)
                                                      : AnyShapeStyle(.tertiary))
                    .lineLimit(1)
                    .frame(width: 92, alignment: .trailing)
            }
            .padding(.vertical, 6).padding(.horizontal, 4)
            .background {
                RoundedRectangle(cornerRadius: 10)
                    .fill(focus == r.id ? Theme.green.opacity(0.12) : .clear)
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    private func status(_ fx: Board.Fixture?) -> String {
        guard let fx else { return "—" }
        if fx.final { return "Final \(fx.score)–\(fx.oppScore)" }
        if fx.live { return fx.label }
        return kickoff(fx.kickoff)
    }

    /// The stored kickoff is an ISO instant truncated to the minute -
    /// "2026-09-13T20:15", with no seconds and no zone - so an
    /// ISO8601DateFormatter set to `.withInternetDateTime` rejects every one
    /// of them and the column renders the raw string. It is UTC; say so
    /// explicitly and give the reader a local day and time.
    private func kickoff(_ raw: String) -> String {
        guard let d = KickoffFormatter.shared.date(from: raw) else { return raw }
        return d.formatted(.dateTime.weekday(.abbreviated).hour().minute())
    }

    // MARK: - the other tabs

    private func overview(_ L: LeaguePayload) -> some View {
        let m = board.mosaic(for: L)
        return Panel(title: "This Week") {
            HStack(spacing: 18) {
                sideBlock(L.you.name, m.yourScore, m.yourProjected, Theme.green)
                VStack(spacing: 3) {
                    Text("vs").font(.system(size: 11)).foregroundStyle(.tertiary)
                    Text("Week \(L.week)").font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
                sideBlock(L.opp?.name ?? "Opponent", m.oppScore, m.oppProjected, Theme.red)
            }
        }
    }

    private func sideBlock(_ name: String, _ score: Double, _ proj: Double,
                           _ tint: Color) -> some View {
        VStack(spacing: 4) {
            Text(name).font(.system(size: 12, weight: .semibold))
                .lineLimit(1).minimumScaleFactor(0.7)
            Text(score, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 40, weight: .bold)).monospacedDigit()
                .foregroundStyle(tint)
            Text("proj \(proj, format: .number.precision(.fractionLength(1)))")
                .font(.system(size: 11)).foregroundStyle(.tertiary).monospacedDigit()
        }
        .frame(maxWidth: .infinity)
    }

    /// Every matchup in the league this week, totalled from the same roster
    /// rows the board already has - no request per team.
    private func matchups(_ L: LeaguePayload) -> some View {
        let totals = board.teamTotals(L)
        let names = Dictionary(uniqueKeysWithValues:
            (L.teams ?? []).map { ($0.teamId, $0.display) })
        var seen = Set<String>()
        var pairs: [(String, String)] = []
        for (a, b) in (L.matchups ?? [:]).sorted(by: { $0.key < $1.key })
        where !seen.contains(a) && !seen.contains(b) {
            seen.insert(a); seen.insert(b); pairs.append((a, b))
        }
        return Panel(title: "Week \(L.week) Matchups") {
            if pairs.isEmpty {
                NoSource(what: "No matchups stored for this week.")
            } else {
                VStack(spacing: 7) {
                    ForEach(pairs, id: \.0) { a, b in
                        let ta = totals[a] ?? 0, tb = totals[b] ?? 0
                        HStack(spacing: 10) {
                            matchSide(names[a] ?? a, ta, ta >= tb,
                                      mine: a == L.you.teamId, .trailing)
                            Text("–").font(.system(size: 11)).foregroundStyle(.quaternary)
                            matchSide(names[b] ?? b, tb, tb > ta,
                                      mine: b == L.you.teamId, .leading)
                        }
                        .padding(.vertical, 7).padding(.horizontal, 11)
                        .background(RoundedRectangle(cornerRadius: 12)
                            .fill((a == L.you.teamId || b == L.you.teamId)
                                  ? Theme.green.opacity(0.10) : .white.opacity(0.05)))
                    }
                }
            }
        }
    }

    private func matchSide(_ name: String, _ total: Double, _ ahead: Bool,
                           mine: Bool, _ align: HorizontalAlignment) -> some View {
        HStack(spacing: 8) {
            if align == .leading {
                Text(total, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 13, weight: ahead ? .bold : .regular))
                    .monospacedDigit()
            }
            Text(name).font(.system(size: 11, weight: mine ? .semibold : .regular))
                .foregroundStyle(mine ? AnyShapeStyle(Theme.green) : AnyShapeStyle(.primary))
                .lineLimit(1).minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity,
                       alignment: align == .leading ? .leading : .trailing)
            if align == .trailing {
                Text(total, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 13, weight: ahead ? .bold : .regular))
                    .monospacedDigit()
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func standingsTable(_ L: LeaguePayload) -> some View {
        let rows = board.standings[L.id] ?? []
        return Panel(title: "Standings") {
            if rows.isEmpty {
                NoSource(what: "No standings stored for this season yet.")
            } else {
                VStack(spacing: 0) {
                    HStack(spacing: 10) {
                        Text("#").frame(width: 26, alignment: .leading)
                        Text("TEAM").frame(maxWidth: .infinity, alignment: .leading)
                        Text("REC").frame(width: 54, alignment: .trailing)
                        Text("PF").frame(width: 62, alignment: .trailing)
                        Text("PA").frame(width: 62, alignment: .trailing)
                    }
                    .font(.system(size: 8, weight: .heavy)).kerning(0.8)
                    .foregroundStyle(.tertiary).padding(.vertical, 7)

                    ForEach(rows.sorted { ($0.rank ?? 99) < ($1.rank ?? 99) }) { r in
                        let mine = r.teamId == L.you.teamId
                        HStack(spacing: 10) {
                            Text("\(r.rank ?? 0)").font(.system(size: 11, weight: .bold))
                                .frame(width: 26, alignment: .leading)
                                .foregroundStyle(.secondary)
                            Text(r.team ?? r.teamId)
                                .font(.system(size: 12, weight: mine ? .semibold : .regular))
                                .foregroundStyle(mine ? AnyShapeStyle(Theme.green)
                                                      : AnyShapeStyle(.primary))
                                .lineLimit(1).minimumScaleFactor(0.7)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(r.record).font(.system(size: 11)).monospacedDigit()
                                .frame(width: 54, alignment: .trailing)
                            Text((r.pointsFor ?? 0), format: .number.precision(.fractionLength(1)))
                                .font(.system(size: 11)).monospacedDigit()
                                .foregroundStyle(.secondary)
                                .frame(width: 62, alignment: .trailing)
                            Text((r.pointsAgainst ?? 0), format: .number.precision(.fractionLength(1)))
                                .font(.system(size: 11)).monospacedDigit()
                                .foregroundStyle(.tertiary)
                                .frame(width: 62, alignment: .trailing)
                        }
                        .padding(.vertical, 6)
                        .background {
                            RoundedRectangle(cornerRadius: 9)
                                .fill(mine ? Theme.green.opacity(0.10) : .clear)
                        }
                    }
                }
            }
        }
    }
}

/// One formatter, made once. Building a DateFormatter per table row is a
/// classic way to make a list stutter, and a roster table is a lot of rows
/// times a lot of polls.
///
/// Fixed format, fixed locale, fixed zone. A user-facing locale here would
/// change how the *input* is parsed on some devices, which is the classic way
/// a date column works everywhere except on somebody else's phone.
enum KickoffFormatter {
    static let shared: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm"
        return f
    }()
}
