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
                                .explains(Explain.winProbability,
                                          in: AnyShape(.circle))
                            // Your team, and the row is the way into its
                            // line-up - which is what a manager's name in a
                            // list is for. The record beside it is a separate
                            // datum with its own note, so it takes its own
                            // small target rather than swallowing the row.
                            VStack(alignment: .leading, spacing: 3) {
                                Button { tab = .leagues } label: {
                                    Text(f.league.you.name)
                                        .font(.system(size: 15, weight: .bold))
                                        .lineLimit(1).minimumScaleFactor(0.7)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        // Nothing is drawn under this one, so
                                        // the hover highlight is the only
                                        // shape there is - and a square one
                                        // in a rail of rounded cards reads as
                                        // a mistake.
                                        .contentShape(.rect(cornerRadius: 8))
                                }
                                .buttonStyle(.plain).hoverEffect(.highlight)
                                if let r = f.league.record, !r.line.isEmpty {
                                    Text("\(r.line) · \(r.place)")
                                        .font(.system(size: 11))
                                        .foregroundStyle(.secondary)
                                        .explains(Explain.record,
                                                  in: AnyShape(.rect(cornerRadius: 6)))
                                }
                                ReasonChip(reason: f.reason)
                            }
                            Spacer(minLength: 0)
                        }
                        Divider().opacity(0.2)
                        HStack(spacing: 6) {
                            StatTile(value: figure(m.yourProjected), label: "YOU",
                                     detail: Explain.projected(board))
                            StatTile(value: figure(m.oppProjected),
                                     label: (f.league.opp?.name ?? "OPPONENT")
                                        .uppercased(),
                                     detail: Explain.opponentProjected(board))
                            StatTile(value: (m.margin >= 0 ? "+" : "") + figure(m.margin),
                                     label: "MARGIN",
                                     mark: .of(m.margin),
                                     detail: Explain.margin(board))
                        }
                        HStack(spacing: 6) {
                            StatTile(value: board.rankSummary.value,
                                     label: board.rankSummary.label,
                                     detail: Explain.rank(board.rankSummary,
                                                          leagues: board.leagues.count))
                            StatTile(value: f.league.record?.pointsFor
                                        .map { figure($0) } ?? "—", label: "POINTS FOR",
                                     detail: Explain.pointsFor)
                            StatTile(value: "\(board.distinctPlayers)", label: "ROSTERED",
                                     detail: Explain.rostered)
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
                        .plate(11, .white.opacity(0.05))
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
            }
        }
    }

    /// One league in the rail. The same row at every scale, so a number does
    /// not change appearance depending on how many leagues sit beside it.
    func leagueRow(_ f: LeagueFocus) -> some View {
        let here = f.league.id == board.league?.id
        // One target for the whole row. Nothing inside it is a control of its
        // own - not the ring, not the chip - because a second target inside a
        // tappable row is how a pinch ends up doing nothing.
        return Button { choose(f.league.id) } label: {
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
                // Offered rather than discovered: once a league is selected
                // the rails are already showing it, so the only thing left to
                // ask for is its own page, and the chevron says a second tap
                // is what asks.
                if here {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 8).padding(.horizontal, 10)
            .plate(14, here ? Theme.green.opacity(0.14) : .white.opacity(0.05))
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
                    // A chip rather than green words: this is the only way
                    // back from a hidden league and it has to be visible over
                    // a bright room, where green text measures 1.6:1.
                    Button { Task { await board.unhideAll() } } label: {
                        Chip(text: "SHOW", fill: Theme.greenFill)
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
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
                    StatTile(value: "\(board.leagues.count)", label: "LEAGUES",
                             detail: Explain.leaguesFollowed)
                    StatTile(value: "\(board.distinctPlayers)", label: "PLAYERS",
                             detail: Explain.rostered)
                    StatTile(value: "\(w) - \(l)", label: "PROJECTED",
                             mark: .of(Double(w - l), level: 0.5),
                             detail: Explain.projectedRecord(board))
                }
                Divider().opacity(0.2)
                HStack(spacing: 6) {
                    StatTile(value: figure(board.totalProjected), label: "PROJ POINTS",
                             detail: Explain.totalProjected(board))
                    StatTile(value: (board.edgeOverOpponents >= 0 ? "+" : "")
                             + figure(board.edgeOverOpponents),
                             label: "VS OPPONENTS",
                             mark: .of(board.edgeOverOpponents),
                             detail: Explain.edge(board))
                    // Says "league rank" over one league and "avg rank" over
                    // several, and names how many reported one when they
                    // differ - a tile whose meaning drifts with the league
                    // count is worse than no tile. The popover carries the
                    // same warning, because the label has no room for it.
                    StatTile(value: board.rankSummary.value,
                             label: board.rankSummary.label,
                             detail: Explain.rank(board.rankSummary,
                                                  leagues: board.leagues.count))
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
                // An injury row is about a player, so it opens the player -
                // the card in the right rail already carries his week, his
                // exposure and his opportunity, which is exactly what the
                // question "how bad is this for me" needs.
                ForEach(board.injuries.prefix(5)) { inj in
                    Button { focus = inj.id } label: {
                        HStack(spacing: 10) {
                            // Opaque disc, white cross. The old version drew
                            // a coloured glyph on a 22% wash, so on a bright
                            // room the injury icon was a faint smudge on the
                            // one panel whose whole job is to be noticed.
                            ZStack {
                                Circle().fill(severityFill(inj.severity))
                                Image(systemName: "cross.case.fill")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.white)
                            }
                            .frame(width: 30, height: 30)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(inj.name)
                                        .font(.system(size: 12, weight: .semibold))
                                        .lineLimit(1)
                                    if let lab = inj.label {
                                        Chip(text: lab.uppercased(),
                                             fill: severityFill(inj.severity), size: 8)
                                    }
                                }
                                Text(inj.headline ?? "")
                                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                                    .lineLimit(2)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.vertical, 6).padding(.horizontal, 9)
                        .plate(12, focus == inj.id ? Theme.green.opacity(0.14)
                                                   : .white.opacity(0.05))
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                    .revealsHologram(inj.id)
                }
            }
        }
    }

    /// How bad it is, as an opaque ground for white text.
    ///
    /// Doubtful sits between out and questionable by hue *and* by being the
    /// one solved for at runtime, so the three are ordered rather than merely
    /// different - a reader who cannot separate red from amber still gets the
    /// wording, which is what the chip actually says.
    func severityFill(_ s: String?) -> Color {
        switch (s ?? "").lowercased() {
        case "out", "ir":    return Theme.redFill
        case "doubtful":     return Theme.chipFill(hue: 0.055)
        case "questionable": return Theme.goldFill
        default:             return Theme.positionFill("DEF")
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
                // Directly under the men it is about. It draws nothing when
                // one source is loaded, which is not agreement - it is
                // nobody to disagree with.
                DisagreementPanel(focus: $focus)
                opportunities
            }
        }
        .scrollIndicators(.hidden)
    }

    var weekHeader: some View {
        // One chip for the whole header rather than one per scoreline: every
        // projected total under it is built from the same source, and saying
        // so four times would be four copies of one sentence.
        Panel(title: "Week \(board.league?.week ?? 0) Command Center",
              trailing: board.loadedSources.isEmpty ? nil
                : AnyView(SourceTag(text: board.projectionTag))) {
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
                            .explains(Explain.projected(board))
                        Text("vs").font(.system(size: 11, weight: .heavy))
                            .foregroundStyle(.tertiary)
                        side(f.league.opp?.name ?? "Opponent",
                             m.oppScore, m.oppProjected, lead: false)
                            .explains(Explain.opponentProjected(board))
                    }
                    // The bar and the percentage under it are one figure, so
                    // they are one target: tapping the bar and tapping the
                    // words should not be two different gestures.
                    VStack(spacing: 8) {
                        GeometryReader { g in
                            ZStack(alignment: .leading) {
                                Capsule().fill(.white.opacity(0.14))
                                Capsule().fill(m.winProb >= 0.5 ? Theme.green : Theme.red)
                                    .frame(width: max(4, g.size.width * m.winProb))
                            }
                        }
                        .frame(height: 6)
                        HStack {
                            // The bar above already draws the lean in
                            // colour, where colour is a shape rather than a
                            // glyph. The sentence is ink, with the arrow
                            // saying which way it leans.
                            MarkChip(mark: .of(m.winProb - 0.5, level: 0.005), size: 8)
                            Text("\(Int(m.winProb * 100))% win probability")
                                .font(.system(size: 11, weight: .semibold))
                            Spacer(minLength: 0)
                            Text(phrase(m)).font(.system(size: 10))
                                .foregroundStyle(.tertiary)
                        }
                    }
                    .explains(Explain.winProbability)
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
        return Button { choose(f.league.id) } label: {
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
            .plate(15, f.league.id == board.league?.id
                       ? Theme.green.opacity(0.12) : .white.opacity(0.05))
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
                StatTile(value: "\(ahead)", label: "AHEAD", mark: .ahead,
                         detail: Explain.tally("Ahead"))
                StatTile(value: "\(doubt)", label: "IN DOUBT", mark: .level,
                         detail: Explain.tally("In doubt"))
                StatTile(value: "\(behind)", label: "BEHIND", mark: .behind,
                         detail: Explain.tally("Behind"))
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
                        .plate(11, .white.opacity(0.05))
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
        return Button { choose(f.league.id) } label: {
            HStack(spacing: 9) {
                MarkChip(mark: won ? .ahead : .behind, size: 7)
                Text(f.league.league).font(.system(size: 11))
                    .lineLimit(1).minimumScaleFactor(0.7)
                Spacer(minLength: 6)
                Text("\(figure(m.yourScore)) – \(figure(m.oppScore))")
                    .font(.system(size: 11, weight: .semibold)).monospacedDigit()
                Text(f.reason.label).font(.system(size: 9))
                    .foregroundStyle(.tertiary).frame(width: 74, alignment: .trailing)
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .plate(10, .white.opacity(0.04))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    /// The slate. Abbreviations, score and clock all come from the shared live
    /// tier, which is the same payload for everybody - that is what makes it
    /// cacheable, and why it costs nothing to show all of it.
    var liveGames: some View {
        Panel(title: "Live Games") {
            // `board.slate` rather than a second pairing of the same clubs.
            // The old one here grouped on kickoff time plus label, which is
            // fine until two games start in the same minute - on a Sunday,
            // most of them - and it had no event id, so a tile could not lead
            // anywhere. The slate is keyed on the event the feed reports, so
            // it is right by construction and every tile knows its own game.
            let games = board.slate
            if games.isEmpty {
                NoSource(what: "No slate reported yet.")
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(games) { g in
                            Button { openGame(g.event) } label: {
                                HStack(spacing: 9) {
                                    ClubMark(abbr: g.away, size: 24)
                                    VStack(spacing: 1) {
                                        Text(g.state == "pre" ? "vs"
                                             : "\(g.awayScore) – \(g.homeScore)")
                                            .font(.system(size: 13, weight: .bold))
                                            .monospacedDigit()
                                        HStack(spacing: 3) {
                                            if g.live { MarkDot(mark: .live, size: 5) }
                                            Text(g.label).font(.system(size: 8))
                                                .foregroundStyle(g.live
                                                    ? AnyShapeStyle(.primary)
                                                    : AnyShapeStyle(.tertiary))
                                                .lineLimit(1)
                                        }
                                    }
                                    .frame(minWidth: 54)
                                    ClubMark(abbr: g.home, size: 24)
                                }
                                .padding(.horizontal, 11).padding(.vertical, 8)
                                .plate(13, .white.opacity(0.05))
                            }
                            .buttonStyle(.plain).hoverEffect(.highlight)
                        }
                    }
                }
            }
        }
    }

    /// Your men, across every league, ordered by what is at stake now.
    ///
    /// The cap and the order both move with the league count. One league has
    /// nine starters and showing eight of them is an arbitrary truncation of
    /// a list that fits; ten leagues have sixty-odd, and the ones worth the
    /// space are the men you are exposed to more than once, because those are
    /// the ones a single afternoon decides several weeks with.
    var playersInAction: some View {
        // Scoped to the league that is selected, which is the whole of the
        // bug the rail had: this read the cross-league roster, so picking a
        // league in the rail changed a highlight and left the centre showing
        // the same twelve men. `rosterHere` is a filter over the ownership
        // rows `/api/players` already carries - no extra request - and each
        // man keeps his exposure across every league, because that is the
        // fact a cross-league board exists to show.
        Panel(title: board.scale.single ? "My Players in Action"
              : "In Action · \(board.league?.league ?? "")") {
            let live = board.live?.players ?? [:]
            let many = board.scale.many
            let men = board.rosterHere.sorted { a, b in
                if many, a.startedIn != b.startedIn { return a.startedIn > b.startedIn }
                let la = live[a.id]?.s ?? -1, lb = live[b.id]?.s ?? -1
                if la != lb { return la > lb }
                return board.projected(a.id, fallback: a.projected)
                     > board.projected(b.id, fallback: b.projected)
            }
            let cap = board.scale.single ? 9 : (many ? 12 : 8)
            // Bounded by `cap` before the grid sees it - see `weekCards`.
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 168), spacing: 10)],
                      spacing: 10) {
                ForEach(men.prefix(cap)) { p in
                    Button { focus = p.id } label: {
                        HStack(spacing: 9) {
                            Headshot(url: p.img, name: p.name,
                                     tint: Theme.positionFill(p.pos), size: 40)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(p.name).font(.system(size: 11, weight: .semibold))
                                    .lineLimit(1).minimumScaleFactor(0.7)
                                Text("\(p.pos) · \(p.team)")
                                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                                // The number, and a mark only when the
                                // sources are far enough apart on him for the
                                // choice of source to change a decision. A
                                // source name on every tile would be the same
                                // word forty times; the ornament and the panel
                                // head already say it once.
                                let pick = board.projectionPick(
                                    p.id, fallback: p.projected)
                                HStack(spacing: 4) {
                                    Text("\(figure(pick?.value ?? 0)) proj")
                                        .font(.system(size: 9))
                                        .foregroundStyle(.secondary)
                                        .monospacedDigit()
                                    if let sp = pick?.spread, pick?.disputed == true {
                                        SpreadChip(spread: sp, compact: true)
                                    }
                                }
                                if let s = live[p.id]?.s, s > 0 {
                                    // The word "live" is the message; the dot
                                    // agrees with it. Green digits said it
                                    // only in a colour that vanishes over a
                                    // bright wall.
                                    HStack(spacing: 4) {
                                        MarkDot(mark: .live, size: 5)
                                        Text("\(figure(s)) live")
                                            .font(.system(size: 10, weight: .bold))
                                            .monospacedDigit()
                                    }
                                }
                                // Where he sits in *this* league, which is a
                                // different fact from where he sits in the
                                // others - and the one that changes when you
                                // pick a different league in the rail.
                                if !board.scale.single, let o = board.here(p) {
                                    HStack(spacing: 5) {
                                        if o.started == true {
                                            Chip(text: "START",
                                                 fill: Theme.greenFill, size: 8)
                                        } else {
                                            Text(o.slot ?? "BENCH")
                                                .font(.system(size: 8, weight: .heavy))
                                                .foregroundStyle(.secondary)
                                        }
                                        Text(p.exposure == 1 ? "1 league"
                                                             : "\(p.exposure) leagues")
                                            .font(.system(size: 8, weight: .heavy))
                                            .foregroundStyle(p.exposure > 1
                                                             ? AnyShapeStyle(.primary)
                                                             : AnyShapeStyle(.tertiary))
                                    }
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(9)
                        .plate(14, focus == p.id ? Theme.green.opacity(0.14)
                                                 : .white.opacity(0.05))
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                    .revealsHologram(p.id)
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
            // Free in the league that is selected, not free in all of them.
            // The rankings payload names the leagues each man is owned in, so
            // this is a fact about that league; the cross-league version hid
            // every man who happened to be rostered in one other league,
            // which is not a reason he is unavailable to you here.
            let free = board.freeHere
                .sorted { board.projected($0.id, fallback: $0.projected)
                        > board.projected($1.id, fallback: $1.projected) }
            if free.isEmpty {
                NoSource(what: board.scale.single
                         ? "Everybody on today's slate is rostered in your league."
                         : "Everybody on today's slate is rostered in "
                           + (board.league?.league ?? "this league") + ".")
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 168), spacing: 10)],
                          spacing: 10) {
                    ForEach(free.prefix(4)) { p in
                        Button { focus = p.id } label: {
                            HStack(spacing: 9) {
                                Headshot(id: p.id,
                                         name: p.name, tint: Theme.positionFill(p.pos), size: 38)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(p.name).font(.system(size: 11, weight: .semibold))
                                        .lineLimit(1).minimumScaleFactor(0.7)
                                    Text("\(p.pos) · \(p.team)")
                                        .font(.system(size: 9)).foregroundStyle(.tertiary)
                                    // Says which league he is free in, since
                                    // that is now the claim being made. "Free
                                    // in your league" is the same sentence
                                    // when there is only one.
                                    Text(board.scale.single
                                         ? "free in your league"
                                         : "free in \(board.league?.league ?? "")")
                                        .font(.system(size: 8, weight: .heavy))
                                        .foregroundStyle(.tertiary)
                                        .lineLimit(1).minimumScaleFactor(0.7)
                                    Text("+\(figure(board.projected(p.id, fallback: p.projected))) proj")
                                        .font(.system(size: 10, weight: .bold))
                                        .monospacedDigit()
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(9)
                            .plate(14, .white.opacity(0.05))
                        }
                        .buttonStyle(.plain).hoverEffect(.highlight)
                        .revealsHologram(p.id)
                    }
                }
            }
        }
    }
}

/// Why a league is where it is in the rail, in three words and a mark.
///
/// Opaque, and with a glyph. It was coloured text on an 18% wash, which put
/// the wearer's wall behind the one sentence in the rail that says which
/// league to open - and made "needs a swing" and "comfortable" the same shape
/// in two hues a deuteranope reads alike.
struct ReasonChip: View {
    let reason: LeagueFocus.Reason
    var body: some View {
        if let m = reason.mark {
            MarkChip(mark: m, text: reason.label.uppercased())
        } else {
            Chip(text: reason.label.uppercased(),
                 fill: Theme.positionFill("DEF"))
        }
    }
}
