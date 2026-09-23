// swift-tools-version: 6.0
import PackageDescription

// The stadium, as a library both products link.
//
// It was always meant to lift out of the app: its surface is public, its only
// inputs are a scene spec and a base URL, and `docs/ART_BIBLE.md`'s ten actors
// each own a folder inside it. Here it is one module, so a college Saturday
// and an NFL Sunday are drawn by the same renderer rather than by two copies.
//
// visionOS only, on purpose. The stadium is RealityKit volumes and immersive
// spaces; there is no iPhone version of it to keep honest. An app that runs on
// several platforms links this one for visionOS and draws its own 2D field
// elsewhere.
let package = Package(
    name: "StadiumKit",
    platforms: [.visionOS(.v2)],
    products: [.library(name: "StadiumKit", targets: ["StadiumKit"])],
    targets: [
        .target(
            name: "StadiumKit",
            path: "Sources/StadiumKit",
            // The same language mode the app target builds in. A tools-6.0
            // package would otherwise compile this in Swift 6 mode, and the
            // move is meant to change where the renderer lives, not what the
            // compiler makes of it.
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
