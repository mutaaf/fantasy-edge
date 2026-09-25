import SwiftUI
import StadiumKit

@main
struct FantasyEdgeApp: App {
    @State private var board: Board
    /// One scene feed for the tabletop and the stadium together, so walking
    /// from one into the other keeps the same game and the same poll.
    @State private var scene: SceneFeed
    /// Which live game deserves the stadium right now. One for the app, so the
    /// channel's memory of what it is showing survives leaving the space.
    @State private var channel: RedZoneChannel
    /// What was open before the stadium, so leaving it restores exactly that.
    @State private var passage = StadiumPassage(frontDoor: .id("board"))

    init() {
        let b = Board()
        _board = State(initialValue: b)
        _scene = State(initialValue: SceneFeed(base: { "http://\(b.host)" }))
        _channel = State(initialValue: RedZoneChannel(base: { "http://\(b.host)" }))
    }

    var body: some Scene {
        WindowGroup(id: "board") {
            // The environment goes outermost: the two modifiers read the board
            // and the passage themselves, and an environment applied inside
            // them is invisible to them (the first launch trapped on exactly
            // that).
            CommandView()
                .tracksWindow(.id("board"))
                .modifier(StadiumLaunchArguments())
                .environment(board).environment(scene).environment(passage).environment(channel)
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
            ImmersiveBoard().environment(board).environment(scene).environment(passage).environment(channel)
        }
        // Mixed keeps the room; progressive lets the wearer dial it up with
        // the crown; full is there now too. Mixed stays the *default* for the
        // board, and that is not timidity - a board is a thing you have while
        // a real game is on in a real room, and blacking the room out is the
        // wrong thing to do to somebody on a Sunday afternoon. The hall is the
        // other way round, because a hall is somewhere you go.
        .immersionStyle(selection: style(\.boardStyle), in: .mixed, .progressive, .full)

        // A game on the table: a real 3D field in a volume.
        WindowGroup(id: "tabletop", for: String.self) { $value in
            TabletopHost(value: value ?? StadiumHost.replayWindow)
                .environment(board).environment(scene).environment(passage).environment(channel)
        }
        .windowStyle(.volumetric)
        // presentation.tabletop.volume: sized for the two-deck bowl on its
        // plinth (fantasyedge/scene.py). Change both together.
        .defaultSize(width: 1.12, height: 0.45, depth: 0.86, in: .meters)

        // Seated at the fifty. From the tabletop it opens progressive, so the
        // Digital Crown walks you from the room into the bowl; the ornament
        // offers 100% full as well. The dial never goes below 40%: under that
        // the room is the scene and the stadium is a smear at its edge.
        ImmersiveSpace(id: "stadium") {
            StadiumHostSpace().environment(board).environment(scene).environment(passage).environment(channel)
        }
        .immersionStyle(selection: style(\.stadiumStyle, progressive: Self.stadiumDial),
                        in: Self.stadiumDial, .full)
    }

    /// The stadium's Crown dial: 40% to 100%, opening at 85%.
    static let stadiumDial = ProgressiveImmersionStyle.progressive(0.4...1.0, initialAmount: 0.85)

    /// Bridge between the app's stored choice and SwiftUI's existential.
    ///
    /// `.immersionStyle(selection:)` wants a `Binding<any ImmersionStyle>` and
    /// the picker inside the space wants something it can compare, so the
    /// truth is the enum on `Board` and this converts in both directions. The
    /// getter is what makes the in-space picker work at all: a `.constant`
    /// here, which is what this used to be, means the scene never re-reads the
    /// choice and the control does nothing.
    private func style(
        _ key: ReferenceWritableKeyPath<Board, RoomStyle>,
        progressive: ProgressiveImmersionStyle = .progressive
    ) -> Binding<any ImmersionStyle> {
        Binding(
            get: {
                switch board[keyPath: key] {
                case .full:        return .full
                case .progressive: return progressive
                case .mixed:       return .mixed
                }
            },
            set: { new in
                // The system can hand this back when the wearer changes
                // immersion themselves, so it is written through rather than
                // dropped - otherwise the space's own picker would drift out
                // of step with the room it is describing.
                if new is FullImmersionStyle { board[keyPath: key] = .full }
                else if new is ProgressiveImmersionStyle { board[keyPath: key] = .progressive }
                else if new is MixedImmersionStyle { board[keyPath: key] = .mixed }
            })
    }
}
