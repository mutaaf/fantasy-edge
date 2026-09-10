import SwiftUI

@main
struct FantasyEdgeApp: App {
    @State private var board = Board()

    var body: some Scene {
        WindowGroup {
            BoardView().environment(board)
        }
        .windowStyle(.plain)
        .defaultSize(width: 1180, height: 760)

        // The board around you, for when the games are actually running.
        ImmersiveSpace(id: "board-space") {
            ImmersiveBoard().environment(board)
        }
        .immersionStyle(selection: .constant(.mixed), in: .mixed, .progressive, .full)
    }
}
