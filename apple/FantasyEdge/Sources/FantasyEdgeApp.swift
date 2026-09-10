import SwiftUI

@main
struct FantasyEdgeApp: App {
    @State private var board = Board()
    @State private var immersiveDetail: Cell?

    var body: some Scene {
        WindowGroup {
            BoardView().environment(board)
        }
        // .plain would mean painting our own background, which is exactly what
        // made the first version fight the room. Let the system own the glass.
        .windowStyle(.plain)
        .defaultSize(width: 1200, height: 780)

        ImmersiveSpace(id: "board-space") {
            ImmersiveBoard { immersiveDetail = $0 }
                .environment(board)
        }
        // Mixed keeps the room; progressive lets the wearer dial it up with the
        // crown. Full is available but a fantasy board has no business blacking
        // out someone's living room on a Sunday.
        .immersionStyle(selection: .constant(.mixed), in: .mixed, .progressive)
    }
}
