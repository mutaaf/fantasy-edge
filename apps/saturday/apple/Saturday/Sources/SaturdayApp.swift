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
    }
}
