import SwiftUI

// Where Fantasy Edge meets the stadium. Everything under `Stadium/` is generic
// and knows nothing about leagues; this file is the app's side of the seam:
// which game to open, how to pick a replay, and what goes in the stadium's
// right-hand panel.

enum StadiumHost {
    /// The tabletop window's value when it is showing the replay rather than
    /// a live event id.
    static let replayWindow = "replay"
}

/// `-openTabletop <event id | replay>` and `-openStadium` on the launch
/// arguments open the 3D views without a tap. A simulator cannot pinch, so
/// this is how the tabletop and the stadium are screenshotted at all:
///
///     xcrun simctl launch booted com.mutaaf.fantasyedge -openTabletop replay -openStadium
///
/// `-stadiumStyle full` opens the stadium at 100% instead of on the dial, and
/// in a debug build `-stadiumLook <degrees>` turns the bowl so a panel off to
/// one side can be captured head-on: the simulator's camera cannot be aimed
/// from a script.
struct StadiumLaunchArguments: ViewModifier {
    @Environment(Board.self) private var board
    @Environment(StadiumPassage.self) private var passage
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    /// Once per process, not per window. Leaving the stadium reopens the
    /// board, a fresh window with fresh `@State`; a per-view flag let that
    /// window read `-openStadium` again and walk straight back in, forever.
    @MainActor private static var done = false

    func body(content: Content) -> some View {
        content.task {
            guard !Self.done else { return }
            Self.done = true
            // `-shot <name>` fills in any of these (StadiumShots).
            if let value = StadiumShots.argument("-openTabletop") {
                openWindow(id: "tabletop", value: value)
            }
            guard StadiumShots.opensStadium else { return }
            let style: RoomStyle = StadiumHost.argument("-stadiumStyle") == "full" ? .full : .progressive
            // Unstructured: entering closes this very window, and a `.task`
            // tied to it would be cancelled halfway through closing the rest.
            let passage = passage, board = board
            let open = openImmersiveSpace, dismiss = dismissWindow
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                await passage.enter(style: style, board: board, openSpace: open, dismissWindow: dismiss)
            }
        }
    }
}

extension StadiumHost {
    static func argument(_ name: String) -> String? {
        StadiumShots.argument(name)
    }
}

/// The tabletop window for one event, or for the replay.
struct TabletopHost: View {
    let value: String
    @Environment(SceneFeed.self) private var feed
    @Environment(Board.self) private var board
    @Environment(StadiumPassage.self) private var passage
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow

    var body: some View {
        TabletopView(feed: feed) {
            let passage = passage, board = board
            let open = openImmersiveSpace, dismiss = dismissWindow
            // The dial, not a blackout: the Crown takes you the rest of the way.
            Task { @MainActor in
                await passage.enter(style: .progressive, board: board, openSpace: open, dismissWindow: dismiss)
            }
        }
        .onAppear {
            feed.target = value == StadiumHost.replayWindow ? .replay : .live(event: value)
            passage.appeared(.tabletop(value))
            if passage.appearedInside(.tabletop(value)) {
                dismissWindow(id: "tabletop", value: value)
                dismissWindow(id: "tabletop")
            }
        }
        .onDisappear { passage.disappeared(.tabletop(value)) }
        // The launch arguments run from whichever window the system restores
        // first. On a relaunch visionOS can bring back only the tabletop the
        // last session left open, and with the hook on the board alone the
        // stadium never opened (once per process either way).
        .modifier(StadiumLaunchArguments())
        .onChange(of: value) { old, new in
            passage.renamed(from: .tabletop(old), to: .tabletop(new))
            feed.target = new == StadiumHost.replayWindow ? .replay : .live(event: new)
        }
    }
}

/// The stadium, with the rest of the live slate at the wearer's right hand.
struct StadiumHostSpace: View {
    @Environment(SceneFeed.self) private var feed
    @Environment(Board.self) private var board
    @Environment(StadiumPassage.self) private var passage
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace

    var body: some View {
        // Only games the board has actually read. An unreachable board shows
        // no tab here rather than an empty panel in the stands.
        let others = board.slate.filter { $0.event != currentEvent }
        let rows = feed.spec?.look?.experience.panels?.elsewhereRows
            ?? SceneSpec.Look.bundled()?.experience.panels?.elsewhereRows ?? 6
        StadiumSpaceView(
            feed: feed,
            immersion: Binding(
                get: { board.stadiumStyle == .full ? .full : .dial },
                set: { board.stadiumStyle = $0 == .full ? .full : .progressive }),
            look: Self.look,
            trailingTitle: others.isEmpty ? nil : "Elsewhere",
            leave: {
                let passage = passage, open = openWindow, dismiss = dismissImmersiveSpace
                Task { @MainActor in await passage.leave(openWindow: open, dismissSpace: dismiss) }
            }
        ) {
            if !others.isEmpty { Elsewhere(games: others, rows: rows) }
        }
        .task { board.start() }
        .task {
            #if DEBUG
            // `-stadiumLeaveAfter <seconds>`: press Leave without a pinch, so
            // the way back out can be captured in the simulator.
            if let s = Double(StadiumHost.argument("-stadiumLeaveAfter") ?? "") {
                try? await Task.sleep(for: .seconds(s))
                await passage.leave(openWindow: openWindow, dismissSpace: dismissImmersiveSpace)
            }
            #endif
        }
        .onDisappear {
            board.stop()
            passage.spaceDisappeared(openWindow: openWindow)
        }
    }

    private var currentEvent: String { feed.spec?.event ?? "" }

    /// (yaw, pitch) from `-stadiumLook` and `-stadiumPitch`, debug builds only.
    private static var look: SIMD2<Float> {
        #if DEBUG
        return SIMD2(Float(StadiumHost.argument("-stadiumLook") ?? "") ?? 0,
                     Float(StadiumHost.argument("-stadiumPitch") ?? "") ?? 0)
        #else
        return .zero
        #endif
    }
}

/// The other games, live ones first. A replay is never mixed in here: this
/// panel reads the real slate and says so.
private struct Elsewhere: View {
    let games: [Board.SlateGame]
    var rows = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Elsewhere, live").font(.system(size: 20, weight: .semibold))
            if games.isEmpty {
                Text("No other games on the slate.").font(.system(size: 15)).foregroundStyle(.secondary)
            }
            ForEach(games.sorted { ($0.live ? 0 : 1, $0.event) < ($1.live ? 0 : 1, $1.event) }.prefix(rows)) { g in
                HStack(spacing: 10) {
                    Text(g.line).font(.system(size: 16, weight: .semibold))
                    Spacer()
                    Text(g.state == "pre" ? g.kickoff : "\(g.awayScore)–\(g.homeScore)")
                        .font(.system(size: 16, weight: .bold)).monospacedDigit()
                    Text(g.label).font(.system(size: 13)).foregroundStyle(.secondary).lineLimit(1)
                }
                .frame(minHeight: 44)
            }
        }
        .padding(22)
        .frame(width: 420, alignment: .leading)
        .glassBackgroundEffect()
    }
}

/// Last week's games, and one tap into the stadium at kickoff.
///
/// The picker this replaced listed the games somebody had already captured on
/// a Mac, with their final scores across the row. Both halves were wrong: what
/// you want to watch is usually the game nobody has pulled yet, and a list of
/// last week's results is the one thing a replay picker must not be. This
/// lists the whole week - pulled or not - and says why each game is worth an
/// hour without saying how it ended.
///
/// Scores are off. Turning them on re-asks the server rather than unhiding a
/// field, so a hidden row never carries the number it is hiding.
struct ReplayPicker: View {
    let opened: () -> Void
    @Environment(SceneFeed.self) private var feed
    @Environment(\.dismiss) private var dismiss
    @State private var spoilers = false
    @State private var opening: String?

    private var week: LastWeek? { feed.lastWeek }

    var body: some View {
        NavigationStack {
            List {
                if let week, !week.games.isEmpty {
                    Section {
                        ForEach(week.games) { g in row(g) }
                    } header: {
                        HStack {
                            Text("\(week.season) · Week \(week.week)")
                            Spacer()
                            Text("\(week.pulled) of \(week.total) ready to watch")
                                .foregroundStyle(.tertiary)
                        }
                        .font(.system(size: 13))
                    } footer: {
                        Text(week.pulled == week.total
                             ? "Every game is on this Mac and opens without a request."
                             : "A game that is not ready is fetched when you open it. "
                               + "Pull the week in one go with: "
                               + "python3 -m fantasyedge last-week --pull")
                        .font(.system(size: 12)).foregroundStyle(.tertiary)
                    }
                } else if feed.error == nil {
                    HStack(spacing: 12) {
                        ProgressView()
                        Text("Reading last week …").foregroundStyle(.secondary)
                    }
                    .frame(minHeight: 60)
                }
                if let error = feed.error {
                    Text(error).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Last week")
            .toolbar {
                Toggle("Scores", isOn: $spoilers)
                    .toggleStyle(.switch)
                    .onChange(of: spoilers) { _, on in
                        Task { await feed.loadLastWeek(spoilers: on) }
                    }
                Button("Done") { dismiss() }
            }
        }
        .task { await feed.loadLastWeek(spoilers: spoilers) }
        .frame(minWidth: 680, minHeight: 560)
    }

    /// One game. The reason is the loudest thing after the clubs, because it
    /// is what the choice is actually made on.
    private func row(_ g: LastWeek.Game) -> some View {
        Button {
            opening = g.event
            Task {
                await feed.load(g.event)
                await feed.play()
                opening = nil
                opened()
                dismiss()
            }
        } label: {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(g.name).font(.system(size: 17, weight: .semibold))
                        if let a = g.away.score, let h = g.home.score {
                            Text("\(Int(a))–\(Int(h))")
                                .font(.system(size: 17, weight: .bold)).monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                        if let final = g.final {
                            Text(final).font(.system(size: 12)).foregroundStyle(.tertiary)
                        }
                    }
                    Text(g.reason).font(.system(size: 14)).foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 12)
                if opening == g.event {
                    ProgressView()
                } else if g.pulled {
                    Label("Ready", systemImage: "arrow.down.circle.fill")
                        .labelStyle(.iconOnly).foregroundStyle(.green)
                        .accessibilityLabel("Ready to watch")
                } else {
                    Image(systemName: "icloud.and.arrow.down")
                        .foregroundStyle(.tertiary)
                        .accessibilityLabel("Will be fetched")
                }
            }
            .frame(minHeight: 60)
        }
        .accessibilityHint(g.reason)
    }
}
