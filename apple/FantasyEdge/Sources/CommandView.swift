import SwiftUI

/// The command centre: every league at once, on one surface.
///
/// Three rails. The left is standing - where you are, across all of it. The
/// middle is happening - this week, this slate, these men. The right is one
/// player in depth, because the question a board raises is always about
/// somebody in particular.
///
/// Every number here comes from the read API. Where there is no source for
/// something the layout wants, the panel says so rather than showing a
/// plausible figure: a dashboard that fills its own gaps is worse than one
/// with gaps, because you cannot tell which parts to trust.
struct CommandView: View {
    @Environment(Board.self) var board
    @Environment(\.openImmersiveSpace) private var openImmersive
    @Environment(\.dismissWindow) private var dismissWindow
    @State private var showSettings = false
    @State var focus: String?
    @State var tab: Tab = .command
    /// Whether the ranked rail and the week digest are showing everything.
    /// Only reachable at five leagues and up; below that there is nothing
    /// folded away for them to unfold.
    @State var railExpanded = false
    @State var weekExpanded = false
    /// Which game the Live tab has open. Held here rather than inside
    /// `LiveView` so a scoreline anywhere on the surface can open the field
    /// this app already draws, instead of each panel growing its own smaller
    /// copy of one.
    @State var liveEvent = ""

    enum Tab: String, CaseIterable, Identifiable {
        case command = "Command", leagues = "Leagues", players = "Players"
        case live = "Live", moves = "Moves", intel = "Intel"
        var id: String { rawValue }
        var icon: String {
            switch self {
            case .command: return "house.fill"
            case .leagues: return "trophy.fill"
            case .players: return "person.2.fill"
            case .live:    return "dot.radiowaves.left.and.right"
            case .moves:   return "arrow.left.arrow.right"
            case .intel:   return "chart.bar.doc.horizontal"
            }
        }
    }

    private var m: Mosaic { board.mosaic }

    var body: some View {
        Group {
            if board.leagues.isEmpty { empty } else { rails }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // `contentAlignment` decides which part of the ornament lands on the
        // anchor, and `.center` straddles it - half the pill outside the scene
        // and half of it on top of the first panel of every rail. On a window
        // with system glass that reads as a toolbar overlapping its own
        // chrome; on `.plain`, which this app uses so the room shows through,
        // there is no chrome to overlap and it simply sat on the content.
        // Aligning the far edge to the anchor puts each bar wholly outside the
        // scene, which is what an ornament is for.
        .ornament(attachmentAnchor: .scene(.top), contentAlignment: .bottom) { topBar }
        .ornament(attachmentAnchor: .scene(.bottom), contentAlignment: .top) { bottomBar }
        .sheet(isPresented: $showSettings) { HostSheet() }
        .task {
            board.start()
            await board.loadPrefs()
            await board.loadContext()
        }
        // A man you opened stays open when he is in the league you just moved
        // to - watching his slot change from START to BENCH league to league
        // is the point of a cross-league card. When he is not in it the rail
        // falls back to whoever has the most at stake here, because otherwise
        // choosing a league leaves the right rail on somebody who is not in
        // that league at all.
        .onChange(of: board.selected) { _, _ in
            if let f = focus, !board.rosterHere.contains(where: { $0.id == f }) {
                focus = nil
            }
        }
        .onDisappear { board.stop() }
    }

    private var rails: some View {
        HStack(alignment: .top, spacing: 16) {
            leftRail.frame(width: 300)
            // The middle rail is whichever question the tab is asking. The
            // rails either side do not change, because "where do I stand" and
            // "who is this player" are true regardless.
            Group {
                switch tab {
                case .leagues: ScrollView { LeagueView(focus: $focus) }
                        .scrollIndicators(.hidden)
                // Not wrapped in a ScrollView: this one scrolls its own
                // table. Nesting gives the inner LazyVStack unbounded height,
                // which defeats the laziness entirely - every row builds at
                // once and each fires its own image requests.
                case .players: PlayersView(focus: $focus)
                // Same reason as above: the live tab scrolls its own play
                // feed and its own lanes, both with a ceiling on them.
                case .live:    LiveView(focus: $focus, event: $liveEvent)
                default:       centre
                }
            }
            .frame(maxWidth: .infinity)
            rightRail.frame(width: 340)
        }
        .padding(.horizontal, 20).padding(.vertical, 14)
    }

    // MARK: - where a tap goes
    //
    // One place per kind of thing, so the same datum cannot lead somewhere
    // different depending on which panel it was tapped in.

    /// A league row, anywhere on the surface.
    ///
    /// The first tap selects, and selecting is what every other rail now
    /// follows - that is the bug this fixes, because before it the rails read
    /// the cross-league payloads and a tap changed one highlight and nothing
    /// else. A second tap on the row that is already selected opens the
    /// league's own page, since by then "show me this one" cannot mean
    /// anything smaller. The selected row carries a chevron so the second tap
    /// is offered rather than discovered.
    func choose(_ id: String) {
        if board.selected == id { tab = .leagues } else { board.selected = id }
    }

    /// A scoreline is a game, and this app draws a game in exactly one place.
    /// Sending the slate tiles there beats growing a second, smaller field
    /// inside the command centre.
    func openGame(_ event: String) {
        guard !event.isEmpty else { return }
        liveEvent = event
        tab = .live
    }

    // MARK: - chrome

    /// Three pills rather than one bar.
    ///
    /// One bar made the tabs compete with the brand and the clock for the
    /// same width, and the active tab's highlight swallowed its own label.
    /// Separating them lets each be sized for what it is, and lets the tabs
    /// sit centred - which is where the eye goes.
    private var topBar: some View {
        HStack(spacing: 14) {
            HStack(spacing: 11) {
                Image(systemName: "football.fill").font(.system(size: 21))
                    .foregroundStyle(Theme.green)
                VStack(alignment: .leading, spacing: 0) {
                    Text("Fantasy Command").font(.system(size: 17, weight: .bold))
                    // With one league the strapline was a claim about a
                    // plural that did not exist, so it names the league
                    // instead: the single league is the subject here, not a
                    // member of a set.
                    Text(board.scale.single
                         ? (board.league?.league ?? "One league.")
                         : "One game. All your leagues.")
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 18).padding(.vertical, 10)
            .glassBackgroundEffect(in: .capsule)

            HStack(spacing: 6) {
                ForEach(Tab.allCases) { t in
                    Button { tab = t } label: {
                        VStack(spacing: 4) {
                            Image(systemName: t.icon).font(.system(size: 17))
                            Text(t.rawValue).font(.system(size: 10, weight: .medium))
                        }
                        .frame(width: 72, height: 50)
                        // The label rides on top of the highlight rather than
                        // under it, so the selected tab can still be read.
                        .foregroundStyle(tab == t ? AnyShapeStyle(Theme.green)
                                                  : AnyShapeStyle(.secondary))
                        .background {
                            RoundedRectangle(cornerRadius: 13)
                                .fill(tab == t ? Theme.green.opacity(0.18) : .clear)
                        }
                        .contentShape(.rect)
                    }
                    .buttonStyle(.plain)
                    .hoverEffect(.highlight)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .glassBackgroundEffect(in: .capsule)

            HStack(spacing: 11) {
                Circle().fill(board.lastError == nil ? Theme.green : Theme.red)
                    .frame(width: 7, height: 7)
                VStack(alignment: .trailing, spacing: 1) {
                    Text(Date.now, format: .dateTime.weekday(.abbreviated)
                            .month(.abbreviated).day())
                        .font(.system(size: 13, weight: .semibold))
                    Text(board.status).font(.system(size: 9)).foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 18).padding(.vertical, 10)
            .glassBackgroundEffect(in: .capsule)
        }
    }

    private var bottomBar: some View {
        HStack(spacing: 14) {
            // Absent rather than disabled when there is one league. A greyed
            // menu offering a choice you do not have is chrome that exists
            // only to say the app was built for somebody else.
            if !board.scale.single {
                chooser(icon: "trophy", label: "LEAGUE",
                        value: board.league?.league ?? "—") {
                    // Ordered by what needs you once there are enough leagues
                    // for the order to matter, so the menu agrees with the
                    // rail rather than offering a second, different ranking.
                    ForEach(leagueOptions, id: \.id) { L in
                        Button { board.selected = L.id } label: {
                            if L.id == board.league?.id {
                                Label(L.league, systemImage: "checkmark")
                            } else { Text(L.league) }
                        }
                    }
                }
            }

            chooser(icon: "person.crop.circle", label: "MY TEAM",
                    value: board.league?.you.name ?? "—") {
                ForEach(teamOptions, id: \.id) { t in
                    Button {
                        if let lid = board.league?.id {
                            Task { await board.pickTeam(t.teamId, in: lid) }
                        }
                    } label: {
                        if t.teamId == board.league?.you.teamId {
                            Label(t.display, systemImage: "checkmark")
                        } else { Text(t.display) }
                    }
                }
            }
            .disabled(teamOptions.count < 2)

            Divider().frame(height: 26)

            Button {
                Task {
                    if await openImmersive(id: "board-space") == .opened {
                        dismissWindow(id: "board")
                    }
                }
            } label: { Label("Immersive", systemImage: "visionpro") }
                .buttonStyle(.borderedProminent).tint(Theme.green)

            Button { showSettings = true } label: {
                Image(systemName: "gearshape").font(.system(size: 17))
            }
        }
        .padding(.horizontal, 20).padding(.vertical, 11)
        .glassBackgroundEffect(in: .capsule)
    }

    private var teamOptions: [TeamRef] {
        (board.league?.teams ?? []).sorted { $0.display < $1.display }
    }

    private var leagueOptions: [LeaguePayload] {
        board.scale.many ? board.attention().map(\.league) : board.leagues
    }

    private func chooser<C: View>(icon: String, label: String, value: String,
                                  @ViewBuilder content: () -> C) -> some View {
        Menu { content() } label: {
            HStack(spacing: 9) {
                Image(systemName: icon).font(.system(size: 14)).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 1) {
                    Text(label).font(.system(size: 8, weight: .heavy)).kerning(1.1)
                        .foregroundStyle(.tertiary)
                    Text(value).font(.system(size: 14, weight: .medium))
                        .lineLimit(1).minimumScaleFactor(0.75)
                }
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            .frame(minWidth: 148, alignment: .leading).contentShape(.rect)
        }
        .menuStyle(.button).buttonStyle(.bordered)
    }

    private var empty: some View {
        ContentUnavailableView {
            Label("No board yet", systemImage: "sportscourt")
        } description: {
            Text(board.lastError.map { "Cannot reach \(board.host).\n\($0)" }
                 ?? "Start the API on your Mac:\npython3 -m fantasyedge api --host 0.0.0.0")
        } actions: {
            Button("Set address") { showSettings = true }.buttonStyle(.borderedProminent)
            Button("Retry") { Task { await board.load() } }
        }
    }
}
