// swift-tools-version: 6.0
import PackageDescription

// The "What's new" sheet, as a library any app in this repo can link.
//
// Unlike StadiumKit this is not visionOS-only: it is plain SwiftUI, so the
// iPhone and iPad builds of a sibling app can take it as it is. macOS is listed
// for one reason - `swift test` runs on the Mac, and the once-per-version rule
// is the part worth testing without a simulator.
let package = Package(
    name: "WhatsNewKit",
    platforms: [.visionOS(.v2), .iOS(.v17), .macOS(.v14)],
    products: [.library(name: "WhatsNewKit", targets: ["WhatsNewKit"])],
    targets: [
        .target(
            name: "WhatsNewKit",
            path: "Sources/WhatsNewKit",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "WhatsNewKitTests",
            dependencies: ["WhatsNewKit"],
            path: "Tests/WhatsNewKitTests",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
