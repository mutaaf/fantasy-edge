import SwiftUI

@main
struct FantasyEdgeApp: App {
    @State private var board = Board()

    var body: some Scene {
        WindowGroup(id: "board") {
            BoardView().environment(board)
        }
        // .plain would mean painting our own background, which is exactly what
        // made the first version fight the room. Let the system own the glass.
        .windowStyle(.plain)
        .defaultSize(width: 1200, height: 780)

        ImmersiveSpace(id: "board-space") {
            // The space owns its own detail panel now: a sheet cannot be
            // presented into an immersive space, so the card is placed in it.
            ImmersiveBoard().environment(board)
        }
        // Mixed keeps the room; progressive lets the wearer dial it up with the
        // crown. Full is available but a fantasy board has no business blacking
        // out someone's living room on a Sunday.
        .immersionStyle(selection: .constant(.mixed), in: .mixed, .progressive)
    }
}
