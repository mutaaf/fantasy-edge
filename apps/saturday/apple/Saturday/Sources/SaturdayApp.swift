import SwiftUI

/// One codebase for visionOS, iPadOS and iOS. The layouts adapt; the data,
/// the decisions and the design tokens do not.
@main
struct SaturdayApp: App {
    @State private var store = SaturdayStore()

    var body: some Scene {
        WindowGroup {
            SaturdayWall()
                .environment(store)
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
            StadiumVolume(gameID: value ?? "").environment(store)
        }
        .windowStyle(.volumetric)
        .defaultSize(width: 1.12, height: 0.45, depth: 0.86, in: .meters)
        #endif
    }
}
