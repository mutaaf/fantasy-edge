import SwiftUI

@main
struct FantasyEdgeApp: App {
    @State private var board = Board()

    var body: some Scene {
        WindowGroup(id: "board") {
            CommandView().environment(board)
        }
        // .plain would mean painting our own background, which is exactly what
        // made the first version fight the room. Let the system own the glass.
        .windowStyle(.plain)
        // Three rails need the width; the command centre is a wall, not a card.
        //
        // This is honoured, and it was worth proving rather than assuming,
        // because "the text is blurry" was chased here first. Instrumented
        // with a GeometryReader and `\.displayScale` on a clean install: the
        // scene comes up at the system default 1280x720 for one frame and then
        // settles at 1680x940, with a display scale of exactly 2.0 and a pixel
        // length of 0.5. So there is no fractional scale factor anywhere in
        // this window, nothing is rasterised and then resampled, and a 1:1 crop
        // of a simulator capture shows clean glyph edges. Whatever reads as
        // soft on this surface is type size and ink weight - the console is set
        // at 8 to 10 point in places, which is a caption on a laptop - and not
        // resolution. Do not go looking for a scale factor again; there is not
        // one.
        .defaultSize(width: 1680, height: 940)

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
