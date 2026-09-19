import SwiftUI

/// Drives, win probability, box score and leaders for one game. Everything
/// is read from /api/game/{id}; the chart plots ESPN's published series and
/// says so.
struct GameDetailView: View {
    @Environment(SaturdayStore.self) private var store
    @Environment(\.horizontalSizeClass) private var sizeClass
    let gameID: String
    @Binding var path: NavigationPath
    @State private var flourish: Change?

    private var detail: GameDetail? { store.details[gameID] }
    private var error: String? { store.detailErrors[gameID] }

    var body: some View {
        ScrollView {
            if let d = detail {
                VStack(alignment: .leading, spacing: 22) {
                    header(d)
                    Divider()
                    if d.status.state == "pre" {
                        // Nothing has been played: a drive list, a win-probability
                        // chart and a box score would all be empty headings.
                        BoxColumn(detail: d)
                    } else if threeColumns {
                        HStack(alignment: .top, spacing: 34) {
                            DrivesColumn(detail: d).frame(maxWidth: .infinity, alignment: .topLeading)
                            VStack(alignment: .leading, spacing: 18) { WinChart(detail: d); ScoringList(detail: d) }
                                .frame(maxWidth: .infinity, alignment: .topLeading)
                            BoxColumn(detail: d).frame(maxWidth: .infinity, alignment: .topLeading)
                        }
                    } else if wide {
                        HStack(alignment: .top, spacing: 28) {
                            DrivesColumn(detail: d).frame(maxWidth: .infinity, alignment: .topLeading)
                            VStack(alignment: .leading, spacing: 22) { WinChart(detail: d); ScoringList(detail: d); BoxColumn(detail: d) }
                                .frame(maxWidth: .infinity, alignment: .topLeading)
                        }
                    } else {
                        WinChart(detail: d)
                        ScoringList(detail: d)
                        DrivesColumn(detail: d)
                        BoxColumn(detail: d)
                    }
                }
                .padding(wide ? 34 : 16)
            } else if let error {
                ContentUnavailableView("Game unavailable", systemImage: "exclamationmark.triangle", description: Text(error))
            } else {
                ProgressView().padding(60)
            }
        }
        .navigationTitle(title)
        // Open while on screen: the stream fetches this game's summary only
        // while somebody is looking at it.
        .onAppear { store.openGame(gameID) }
        .onDisappear { store.closeGame(gameID) }
        .modifier(OptionalFlourish(game: store.game(gameID), active: $flourish))
    }

    /// Three columns need the visionOS window's width; an iPad gets two.
    private var threeColumns: Bool {
        #if os(visionOS)
        true
        #else
        false
        #endif
    }

    private var wide: Bool {
        #if os(visionOS)
        true
        #else
        sizeClass == .regular
        #endif
    }

    private var title: String {
        guard let g = store.game(gameID) else { return "Game" }
        return "\(g.away.abbr) at \(g.home.abbr)"
    }

    @ViewBuilder private func header(_ d: GameDetail) -> some View {
        let slateGame = store.game(gameID)
        let status = VStack(spacing: 6) {
            ZStack {
                // Before kickoff the heading is the slate's own kickoff label,
                // not ESPN's "9/19 - 7:30 PM EDT" in the device's zone.
                Text(d.status.state == "pre" ? (store.game(gameID)?.kickoffLabel ?? d.status.detail)
                                             : d.status.detail.replacingOccurrences(of: " - ", with: " · "))
                    .font(Typeface.display(30, .heavy))
                    .opacity(flourish == nil ? 1 : 0)
                if let flourish {
                    ChangeBadge(change: flourish, game: slateGame, size: 17)
                        .transition(.asymmetric(insertion: .push(from: .bottom), removal: .opacity))
                }
            }
            if flourish?.kind == .score { LightBank(count: 10, dot: 7, lit: true) }
            HStack(spacing: 8) {
                if slateGame?.flags.redZone == true { StateBadge(text: "Red zone", fill: Tokens.redFill, glyph: Glyph.redZone, size: 13) }
                if slateGame?.flags.upset == true { StateBadge(text: "Upset", fill: Tokens.goldFill, glyph: Glyph.upset, size: 13) }
                if d.status.overtimes > 0 { StateBadge(text: "\(d.status.overtimes)OT", fill: Tokens.otFill, glyph: Glyph.overtime, size: 13) }
            }
        }
        VStack(alignment: .leading, spacing: 14) {
            if wide {
                HStack(alignment: .center) {
                    ScoreSide(team: d.away, side: slateGame?.away, mirrored: false)
                    Spacer()
                    status
                    Spacer()
                    ScoreSide(team: d.home, side: slateGame?.home, mirrored: true)
                }
            } else {
                status.frame(maxWidth: .infinity)
                ScoreSide(team: d.away, side: slateGame?.away, mirrored: false)
                ScoreSide(team: d.home, side: slateGame?.home, mirrored: false)
            }
            ViewThatFits(in: .horizontal) {
                HStack { meta(d); Spacer(); actions }
                VStack(alignment: .leading, spacing: 12) { meta(d); actions }
            }
        }
    }

    private func meta(_ d: GameDetail) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text([d.venue, store.game(gameID)?.tv, store.slate?.clock.map { "Replay · \($0.label)" }].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                .font(Typeface.sans(14)).foregroundStyle(.secondary)
            if store.game(gameID)?.provenance == .reconstructed {
                Label("Rebuilt from timestamps, not recorded", systemImage: Glyph.rebuilt)
                    .font(Typeface.sans(13, .medium)).foregroundStyle(.secondary)
            }
            if let last = d.lastPlay, !d.status.completed {
                Label { Text(last.text).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: last.scoring ? Glyph.score : "text.alignleft") }
                    .font(Typeface.sans(14, .medium))
                    .contentTransition(.opacity)
                    .animation(.easeInOut(duration: 0.3), value: last.id)
            }
        }
    }

    private var actions: some View {
        HStack(spacing: 12) {
            Button { path.append(Route.tabletop(gameID)) } label: {
                Label("View in 3D", systemImage: Glyph.tabletop)
            }
            .buttonStyle(PillButtonStyle(primary: true))
            Button { path.append(Route.stadium(gameID)) } label: {
                Label("Enter stadium", systemImage: Glyph.stadium)
            }
            .buttonStyle(PillButtonStyle())
        }
        .font(Typeface.sans(17, .semibold))
    }
}

private struct ScoreSide: View {
    @Environment(SaturdayStore.self) private var store
    let team: DetailTeam
    let side: Side?
    /// The home side on a wide header reads right to left: score nearest the middle.
    let mirrored: Bool

    var body: some View {
        HStack(spacing: 14) {
            if mirrored { favorite; score; names; chip } else { chip; names; Spacer(minLength: 8); score; favorite }
        }
    }

    private var chip: some View {
        TeamChip(abbr: team.abbr, fill: team.fill ?? side?.fill ?? "#666666", hatch: team.hatch ?? false, width: 84, height: 40, fontSize: 23)
    }

    private var names: some View {
        VStack(alignment: mirrored ? .trailing : .leading, spacing: 2) {
            HStack(spacing: 6) {
                if let r = team.rank { Text("#\(r)").font(Typeface.display(20, .bold)).foregroundStyle(.secondary).fixedSize(horizontal: true, vertical: false) }
                TeamName(location: team.location, shortName: team.shortName, font: Typeface.sans(19, .semibold), fills: false)
                    .layoutPriority(1)
            }
            ViewThatFits(in: .horizontal) {
                Text(([team.record] + (quarters.map { [$0] } ?? [])).joined(separator: " · "))
                    .fixedSize(horizontal: true, vertical: false)
                // Overtime adds a column per period: quarters move to their own
                // line as one unit rather than breaking mid-row or being cut.
                VStack(alignment: mirrored ? .trailing : .leading, spacing: 0) {
                    Text(team.record)
                    // The digits alone, kept whole: a phone has room for six periods, not the label.
                    if !team.linescores.isEmpty {
                        Text(team.linescores.map(String.init).joined(separator: " "))
                            .fixedSize(horizontal: true, vertical: false)
                            .accessibilityLabel("by quarter " + team.linescores.map(String.init).joined(separator: ", "))
                    }
                }
            }
            .font(Typeface.sans(13)).foregroundStyle(.secondary).monospacedDigit()
        }
    }

    private var quarters: String? {
        team.linescores.isEmpty ? nil : "by quarter " + team.linescores.map(String.init).joined(separator: " ")
    }

    private var score: some View {
        Text(team.score.map(String.init) ?? "–").font(Typeface.display(64, .black)).monospacedDigit()
            .fixedSize(horizontal: true, vertical: false)
            .contentTransition(.numericText())
            .animation(.spring(response: 0.5, dampingFraction: 0.7), value: team.score)
    }

    private var favorite: some View {
        Button { store.toggleFavorite(team.id) } label: {
            Image(systemName: store.favorites.contains(team.id) ? Glyph.favorite : Glyph.notFavorite)
                .frame(minWidth: Tokens.target, minHeight: Tokens.target)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(store.favorites.contains(team.id) ? "Remove \(team.location) from my teams" : "Add \(team.location) to my teams")
    }
}

private struct DrivesColumn: View {
    let detail: GameDetail
    @Environment(\.horizontalSizeClass) private var sizeClass
    private var wideIndent: CGFloat { sizeClass == .compact ? 16 : 80 }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionHeading(title: "Drives", overline: detail.status.completed ? "all \(detail.drives.count)" : "\(detail.drives.count) so far")
            ForEach(Array(detail.drives.enumerated()), id: \.offset) { _, drive in
                HStack(spacing: 12) {
                    TeamChip(abbr: drive.team, fill: fill(for: drive.team), width: 52, height: 24, fontSize: 15)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(drive.result.isEmpty ? "In progress" : drive.result).font(Typeface.sans(15, .semibold))
                        Text(drive.description).font(Typeface.sans(13)).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: drive.scored ? Glyph.score : drive.turnover ? Glyph.turnover : drive.current ? Glyph.possession : Glyph.final)
                }
                .padding(.horizontal, 14).frame(minHeight: 60)
                .background(drive.current ? .white.opacity(0.1) : .clear, in: RoundedRectangle(cornerRadius: 16))
                if drive.current {
                    ForEach(drive.plays.suffix(4)) { play in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(play.downText ?? "").font(Typeface.sans(13, .semibold)).fixedSize(horizontal: true, vertical: false)
                            Text(play.text).font(Typeface.sans(13)).foregroundStyle(.secondary)
                        }
                        .padding(.leading, wideIndent)
                    }
                }
            }
        }
    }

    private func fill(for abbr: String) -> String {
        abbr == detail.away.abbr ? (detail.away.fill ?? "#666666") : (detail.home.fill ?? "#666666")
    }
}

private struct WinChart: View {
    let detail: GameDetail

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Win probability", overline: "ESPN's model, not ours")
            if detail.winProbability.count > 1 {
                Canvas { ctx, size in
                    let pts = detail.winProbability.enumerated().map { i, p in
                        CGPoint(x: size.width * CGFloat(i) / CGFloat(detail.winProbability.count - 1), y: size.height * CGFloat(p.home))
                    }
                    var mid = Path(); mid.move(to: CGPoint(x: 0, y: size.height / 2)); mid.addLine(to: CGPoint(x: size.width, y: size.height / 2))
                    ctx.stroke(mid, with: .color(.white.opacity(0.35)), style: StrokeStyle(lineWidth: 1, dash: [4, 5]))
                    var line = Path(); line.addLines(pts)
                    var area = line; area.addLine(to: CGPoint(x: size.width, y: size.height / 2)); area.addLine(to: CGPoint(x: 0, y: size.height / 2)); area.closeSubpath()
                    ctx.fill(area, with: .color(Color(hex: detail.away.fill ?? "#666666").opacity(0.5)))
                    ctx.stroke(line, with: .color(.primary), lineWidth: 2.5)
                }
                .frame(height: 220)
                .overlay(alignment: .topLeading) { Text(detail.away.abbr).font(Typeface.sans(12)).foregroundStyle(.secondary) }
                .overlay(alignment: .bottomLeading) { Text(detail.home.abbr).font(Typeface.sans(12)).foregroundStyle(.secondary) }
                .accessibilityLabel("Win probability: \(detail.away.abbr) \(Int(((1 - (detail.winProbability.last?.home ?? 0.5)) * 100).rounded())) percent")
            }
            Text(detail.winProbabilityCaveat).font(Typeface.sans(12)).foregroundStyle(.secondary)
        }
    }
}

private struct ScoringList: View {
    let detail: GameDetail

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Scoring", overline: "")
            ForEach(Array(detail.scoringPlays.enumerated()), id: \.offset) { _, s in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    TeamChip(abbr: s.team, fill: s.team == detail.away.abbr ? (detail.away.fill ?? "#666666") : (detail.home.fill ?? "#666666"), width: 48, height: 22, fontSize: 14)
                    Text(periodLabel(s.period) + " " + s.clock).font(Typeface.sans(14)).foregroundStyle(.secondary).frame(width: 74, alignment: .leading)
                    Text(s.text).font(Typeface.sans(14))
                }
            }
        }
    }

    private func periodLabel(_ p: Int) -> String { p > 4 ? (p == 5 ? "OT" : "\(p - 4)OT") : "Q\(p)" }
}

private struct BoxColumn: View {
    let detail: GameDetail
    private let rows = ["Total Yards", "1st Downs", "3rd down efficiency", "Turnovers", "Possession"]
    private var played: Bool { !detail.boxscore.isEmpty }
    private let seasonRows = ["Points Per Game", "Total Yards", "Yards Passing", "Yards Rushing",
                              "Points Allowed Per Game", "Yards Allowed"]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if played { SectionHeading(title: "Box score", overline: "") }
            if detail.boxscore.count == 2 {
                let away = Dictionary(detail.boxscore[0].stats.map { ($0.label, $0.value) }, uniquingKeysWith: { a, _ in a })
                let home = Dictionary(detail.boxscore[1].stats.map { ($0.label, $0.value) }, uniquingKeysWith: { a, _ in a })
                ForEach(rows, id: \.self) { label in
                    HStack {
                        Text(away[label] ?? "–").font(Typeface.sans(14, .bold))
                        Spacer()
                        Text(label).font(Typeface.sans(14)).foregroundStyle(.secondary)
                        Spacer()
                        Text(home[label] ?? "–").font(Typeface.sans(14, .bold))
                    }
                }
            }
            if !detail.seasonAverages.isEmpty {
                // Before kickoff ESPN publishes the season, not the game. It is
                // worth showing, as long as it is never called a box score.
                SectionHeading(title: "Season so far", overline: "per game, before kickoff")
                let away = Dictionary(detail.seasonAverages[0].stats.map { ($0.label, $0.value) }, uniquingKeysWith: { a, _ in a })
                let home = Dictionary(detail.seasonAverages.count > 1
                                      ? detail.seasonAverages[1].stats.map { ($0.label, $0.value) } : [],
                                      uniquingKeysWith: { a, _ in a })
                ForEach(seasonRows, id: \.self) { label in
                    HStack {
                        Text(away[label] ?? "–").font(Typeface.sans(14, .bold)).monospacedDigit()
                        Spacer()
                        Text(label).font(Typeface.sans(14)).foregroundStyle(.secondary)
                        Spacer()
                        Text(home[label] ?? "–").font(Typeface.sans(14, .bold)).monospacedDigit()
                    }
                }
            }
            if !detail.leaders.isEmpty { SectionHeading(title: "Leaders", overline: "") }
            ForEach(Array(detail.leaders.enumerated()), id: \.offset) { _, l in
                HStack(spacing: 10) {
                    TeamChip(abbr: l.team, fill: l.team == detail.away.abbr ? (detail.away.fill ?? "#666666") : (detail.home.fill ?? "#666666"), width: 44, height: 20, fontSize: 13)
                    Text(l.name).font(Typeface.sans(14, .semibold))
                    Spacer()
                    Text(l.line).font(Typeface.sans(14)).foregroundStyle(.secondary).fixedSize(horizontal: true, vertical: false)
                }
            }
        }
    }
}

/// A detail view can open before the slate has its game; flourish once it does.
private struct OptionalFlourish: ViewModifier {
    let game: Game?
    @Binding var active: Change?

    func body(content: Content) -> some View {
        if let game { content.modifier(Flourish(game: game, active: $active)) } else { content }
    }
}
