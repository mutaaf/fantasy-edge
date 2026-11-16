// swift-tools-version: 6.0
import PackageDescription

// Usage events for Box Office (mutaaf/box-office rule 6), the pure half: the
// vocabulary and its check, the on-disk queue and the bytes of one batch. The
// app's own `Usage.swift` only moves those bytes. macOS is listed so `swift
// test` runs on the Mac, as WhatsNewKit's does.
let package = Package(
    name: "UsageKit",
    platforms: [.visionOS(.v2), .iOS(.v17), .macOS(.v14)],
    products: [.library(name: "UsageKit", targets: ["UsageKit"])],
    targets: [
        .target(name: "UsageKit", path: "Sources/UsageKit", swiftSettings: [.swiftLanguageMode(.v5)]),
        .testTarget(name: "UsageKitTests", dependencies: ["UsageKit"], path: "Tests/UsageKitTests",
                    swiftSettings: [.swiftLanguageMode(.v5)]),
    ]
)
