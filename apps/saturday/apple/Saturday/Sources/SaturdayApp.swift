import SwiftUI
#if os(visionOS)
import StadiumKit
#endif

/// One codebase for visionOS, iPadOS and iOS. The layouts adapt; the data,
/// the decisions and the design tokens do not.
@main
struct SaturdayApp: App {
    @State private var store = SaturdayStore()
    #if os(visionOS)
    // One feed for the table and the stadium: walking in hands the scene over
    // rather than starting a second poll of the same game.
    @State private var scene = SceneFeed(base: { "http://" + (UserDefaults.standard.string(forKey: "saturday.host") ?? "127.0.0.1:8780") })
    @State private var passage = StadiumPassage(frontDoor: .id("wall"))
    // The red-zone channel, shared with fantasy-edge: it asks the server which
    // game deserves the bowl and follows that answer. The moment comes from
    // the store so a replayed night is asked about the frame the wall is on.
    @State private var channel = RedZoneChannel(
        base: { "http://" + (UserDefaults.standard.string(forKey: SaturdayStore.hostKey) ?? "127.0.0.1:8780") })
    @State private var immersion: StadiumImmersion = .dial
    #endif

    var body: some Scene {
        WindowGroup(id: "wall") {
            SaturdayWall()
                .environment(store)
                #if os(visionOS)
                // tracksWindow reads the passage, so it goes inside the
                // .environment that provides it: environment flows down to
                // children, not out to a modifier wrapped around them.
                .tracksWindow(.id("wall"))
                .environment(scene).environment(passage)
                #endif
                #if !os(visionOS)
                // Stadium lights at night: tiles are dark plates, and system
                // ink has to be light on them in every appearance.
                .preferredColorScheme(.dark)
                #endif
        }
        #if os(visionOS)
        .defaultSize(width: 1680, height: 940)
        #endif

        #if os(visionOS)
        // A game on the table: a real 3D field in a volume, drawn by
        // StadiumKit. The size is the shared stadium's own
        // (presentation.tabletop.volume in fantasyedge/scene.py); change both
        // together. In a flat window the bowl renders unbounded and spills
        // out past the window's edges.
        WindowGroup(id: "tabletop", for: String.self) { $value in
            StadiumVolume(gameID: value ?? "")
                .environment(store).environment(scene).environment(passage)
        }
        .windowStyle(.volumetric)
        .defaultSize(width: 1.12, height: 0.45, depth: 0.86, in: .meters)

        // A seat at the fifty. It opens progressive from the table, so the
        // Digital Crown walks you from the room into the bowl; the dial never
        // goes below 40%, under which the room is the scene and the stadium is
        // a smear at its edge. The numbers are the shared stadium's.
        ImmersiveSpace(id: "stadium") {
            StadiumSpace(immersion: $immersion)
                .environment(store).environment(scene).environment(passage)
                .environment(channel)
        }
        .immersionStyle(selection: style, in: Self.dial, .full)
        #endif
    }

    #if os(visionOS)
    /// The stadium's Crown dial: 40% to 100%, opening at 85%.
    static let dial = ProgressiveImmersionStyle.progressive(0.4...1.0, initialAmount: 0.85)

    /// `.immersionStyle(selection:)` wants a `Binding<any ImmersionStyle>` and
    /// the picker inside the space wants something it can compare, so the
    /// truth is the enum and this converts both ways. A `.constant` here means
    /// the scene never re-reads the choice and the in-space control does
    /// nothing.
    private var style: Binding<any ImmersionStyle> {
        Binding(
            get: { () -> any ImmersionStyle in immersion == .full ? .full : Self.dial },
            set: { new in
                // The system hands this back when the wearer turns the Crown
                // themselves; writing it through keeps the picker in step with
                // the room it describes.
                immersion = new is FullImmersionStyle ? .full : .dial
            })
    }
    #endif
}
