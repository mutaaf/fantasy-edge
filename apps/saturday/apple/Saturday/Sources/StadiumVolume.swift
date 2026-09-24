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
    @Environment(SceneFeed.self) private var feed
    @Environment(StadiumPassage.self) private var passage
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    let gameID: String

    var body: some View {
        TabletopView(feed: feed) {
            // The dial, not a blackout: the Crown takes you the rest of the
            // way in, and the passage puts the wall and this table away until
            // you come back out.
            let passage = passage, open = openImmersiveSpace, dismiss = dismissWindow
            Task { @MainActor in await passage.enter(openSpace: open, dismissWindow: dismiss) }
        }
        .onAppear {
            feed.target = .live(event: gameID)
            passage.appeared(.init(id: "tabletop", value: gameID))
            if passage.appearedInside(.init(id: "tabletop", value: gameID)) {
                dismissWindow(id: "tabletop", value: gameID)
                dismissWindow(id: "tabletop")
            }
        }
        .onDisappear { passage.disappeared(.init(id: "tabletop", value: gameID)) }
        .navigationTitle(title)
    }

    private var title: String {
        guard let g = store.game(gameID) else { return "On the table" }
        return "\(g.away.abbr) at \(g.home.abbr)"
    }
}
#endif
