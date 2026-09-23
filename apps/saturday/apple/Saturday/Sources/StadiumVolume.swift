#if os(visionOS)
import StadiumKit
import SwiftUI

/// One college game on the table, drawn by the shared stadium.
///
/// Everything here is plumbing: which game, and where the API is. The field,
/// the bowl, the arcs and the moments are `StadiumKit`'s, built from the scene
/// `/api/scene/{event}` serves - the same renderer that draws an NFL Sunday,
/// reading a college field because the payload says college.
///
/// visionOS only, like the package: the stadium is volumes and immersive
/// spaces, and there is no iPhone version of it to keep honest. The phone and
/// the iPad draw the 2D field they always did.
struct StadiumVolume: View {
    @Environment(SaturdayStore.self) private var store
    let gameID: String
    var onEnterStadium: () -> Void = {}

    @State private var feed: SceneFeed?

    var body: some View {
        Group {
            if let feed {
                TabletopView(feed: feed, enterStadium: onEnterStadium)
            } else {
                ProgressView("Setting the table…")
            }
        }
        .onAppear {
            // The host is read on every request, so changing it in Settings
            // reaches the scene without rebuilding the feed.
            let made = feed ?? SceneFeed(base: { "http://\(store.host)" })
            made.target = .live(event: gameID)
            feed = made
        }
        .onDisappear { feed?.target = nil }
        .navigationTitle(title)
    }

    private var title: String {
        guard let g = store.game(gameID) else { return "On the table" }
        return "\(g.away.abbr) at \(g.home.abbr)"
    }
}
#endif
