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
struct StadiumLaunchArguments: ViewModifier {
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @State private var done = false

    func body(content: Content) -> some View {
        content.task {
            guard !done else { return }
            done = true
            let args = ProcessInfo.processInfo.arguments
            if let i = args.firstIndex(of: "-openTabletop"), i + 1 < args.count {
                openWindow(id: "tabletop", value: args[i + 1])
            }
            if args.contains("-openStadium") {
                try? await Task.sleep(for: .seconds(2))
                _ = await openImmersiveSpace(id: "stadium")
            }
        }
    }
}

/// The tabletop window for one event, or for the replay.
struct TabletopHost: View {
    let value: String
    @Environment(SceneFeed.self) private var feed
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace

    var body: some View {
        TabletopView(feed: feed) {
            Task { _ = await openImmersiveSpace(id: "stadium") }
        }
        .onAppear {
            feed.target = value == StadiumHost.replayWindow ? .replay : .live(event: value)
        }
        .onChange(of: value) { _, new in
            feed.target = new == StadiumHost.replayWindow ? .replay : .live(event: new)
        }
    }
}

/// The stadium, with the rest of the live slate at the wearer's right hand.
struct StadiumHostSpace: View {
    @Environment(SceneFeed.self) private var feed
    @Environment(Board.self) private var board
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace

    var body: some View {
        StadiumSpaceView(feed: feed, leave: {
            Task { await dismissImmersiveSpace() }
        }) {
            Elsewhere(games: board.slate.filter { $0.event != currentEvent })
        }
        .task { board.start() }
        .onDisappear { board.stop() }
    }

    private var currentEvent: String { feed.spec?.event ?? "" }
}

/// The other games, live ones first. A replay is never mixed in here: this
/// panel reads the real slate and says so.
private struct Elsewhere: View {
    let games: [Board.SlateGame]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Elsewhere, live").font(.system(size: 20, weight: .semibold))
            if games.isEmpty {
                Text("No other games on the slate.").font(.system(size: 15)).foregroundStyle(.secondary)
            }
            ForEach(games.sorted { ($0.live ? 0 : 1, $0.event) < ($1.live ? 0 : 1, $1.event) }.prefix(6)) { g in
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

/// Every captured game, loaded into the replay with one tap.
struct ReplayPicker: View {
    let opened: () -> Void
    @Environment(SceneFeed.self) private var feed
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                if let games = feed.replay?.games, !games.isEmpty {
                    ForEach(games) { g in
                        Button {
                            Task {
                                await feed.load(g.event)
                                await feed.play()
                                opened()
                                dismiss()
                            }
                        } label: {
                            HStack {
                                Text("\(g.away.abbr) \(Int(g.away.score)) @ \(g.home.abbr) \(Int(g.home.score))")
                                    .font(.system(size: 17, weight: .semibold)).monospacedDigit()
                                Spacer()
                                Text(g.final).foregroundStyle(.secondary)
                                Text(String(g.date.prefix(10))).foregroundStyle(.tertiary)
                            }
                            .frame(minHeight: 60)
                        }
                    }
                } else {
                    Text("No games captured yet. On the Mac: python3 -m fantasyedge replay "
                         + "--season 2025 --week 1 --team PHI --at 0")
                        .foregroundStyle(.secondary)
                }
                if let error = feed.error {
                    Text(error).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Replay a game")
            .toolbar { Button("Done") { dismiss() } }
        }
        .task { await feed.loadGames() }
        .frame(minWidth: 620, minHeight: 520)
    }
}
