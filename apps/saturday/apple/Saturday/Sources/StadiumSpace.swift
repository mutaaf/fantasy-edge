#if os(visionOS)
import StadiumKit
import SwiftUI

/// A seat at the fifty - for one college game, or for the Saturday.
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
    @Environment(RedZoneChannel.self) private var channel
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissImmersiveSpace) private var dismissImmersiveSpace
    @Binding var immersion: StadiumImmersion
    /// Whether the Saturday is driving the bowl. Off by default, as it is on a
    /// Sunday and for the same reason: a wearer who walked in from one game's
    /// table came to watch that game, and moving them off it unasked is a
    /// theft rather than a feature. The switch is in the panel, and
    /// `-followBall YES` turns it on for a screenshot.
    @State private var following = UserDefaults.standard.bool(forKey: "followBall")

    var body: some View {
        StadiumSpaceView(
            feed: feed,
            immersion: $immersion,
            look: StadiumShots.look,
            trailingTitle: channel.games.isEmpty ? nil : "Red Zone",
            leave: {
                let passage = passage, open = openWindow, dismiss = dismissImmersiveSpace
                Task { @MainActor in await passage.leave(openWindow: open, dismissSpace: dismiss) }
            }
        ) {
            if !channel.games.isEmpty {
                RedZonePanel(channel: channel, showing: currentEvent,
                             following: $following, watch: watch)
            }
        }
        .task {
            channel.ask { store.moment }
            channel.start()
        }
        // Following the Saturday. The server decides which game deserves the
        // bowl and how long it holds it; this only carries that decision to
        // the feed, and the renderer fades the world down and back when the
        // new scene lands. Nothing moves while a game is pinned or the wearer
        // has not asked to follow.
        .onChange(of: channel.wanted) { _, wanted in
            guard following, !wanted.isEmpty, wanted != currentEvent else { return }
            feed.target = .live(event: wanted)
        }
        .onChange(of: following) { _, on in
            guard on, !channel.wanted.isEmpty, channel.wanted != currentEvent else { return }
            feed.target = .live(event: channel.wanted)
        }
        .onChange(of: currentEvent, initial: true) { _, event in
            channel.arrived(event)
        }
        .onDisappear {
            channel.stop()
            // The Digital Crown, or the system: the windows still have to come
            // back, and only the passage knows which they were.
            passage.spaceDisappeared(openWindow: openWindow)
        }
    }

    /// Watch this game now: pin it, and go. Tapping the game already in the
    /// bowl is how "stay here" is said, so it pins without moving anything.
    private func watch(_ event: String) {
        channel.pin(event)
        guard event != currentEvent else { return }
        feed.target = .live(event: event)
    }

    private var currentEvent: String { feed.spec?.event ?? "" }
}
#endif
