#if os(visionOS)
import StadiumKit
import SwiftUI

/// A seat at the fifty, for one college game.
///
/// The walk in and back out is `StadiumKit`'s `StadiumPassage`, the same one
/// fantasy-edge uses, because the rules it holds were learnt the hard way and
/// are not Saturday's to re-decide: full immersion hides other apps but not
/// this one, so the wall and any tabletop are written down, closed on the way
/// in, and reopened on the way out - and a window that opens while the stadium
/// is up closes itself rather than standing in the stands.
struct StadiumSpace: View {
    @Environment(SaturdayStore.self) private var store
    @Environment(SceneFeed.self) private var feed
    @Environment(StadiumPassage.self) private var passage
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    @Binding var immersion: StadiumImmersion

    var body: some View {
        StadiumSpaceView(
            feed: feed,
            immersion: $immersion,
            look: .zero,
            trailingTitle: nil,
            leave: {
                let passage = passage, open = openWindow, dismiss = dismissImmersiveSpace
                Task { @MainActor in await passage.leave(openWindow: open, dismissSpace: dismiss) }
            }
        ) {
            EmptyView()
        }
        .onDisappear {
            // The Digital Crown, or the system: the windows still have to come
            // back, and only the passage knows which they were.
            passage.spaceDisappeared(openWindow: openWindow)
        }
    }
}
#endif
