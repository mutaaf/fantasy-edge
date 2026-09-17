import Foundation

// What the scene says about the painted art that changes per game
// (fantasyedge/scene.py `field_art`). Types only, with no RealityKit, so
// apple/verify_scene.swift can decode a scene with them.

extension SceneSpec {
    /// A line of text on the grass. A glyph point (gx, gy), in em units with
    /// cap height 1, lands at origin + (gx * along + gy * up) * capHeight in
    /// (x, z) yards.
    public struct ArtText: Decodable, Equatable, Sendable {
        public let text: String
        public let capHeight: Double
        public let origin: [Double]
        public let along: [Double]
        public let up: [Double]
        public let tint: String
    }

    public struct EndZoneArt: Decodable, Equatable, Sendable {
        /// Which end of the field this is, by the side that defends it.
        public let side: String
        public let text: String
        public let capHeight: Double
        public let origin: [Double]
        public let along: [Double]
        public let up: [Double]
        public let tint: String
        /// Whose colour paints this end: the home club, at both ends.
        public let fill: String

        var layout: ArtText {
            ArtText(text: text, capHeight: capHeight, origin: origin, along: along, up: up, tint: tint)
        }
    }

    public struct MidfieldArt: Decodable, Equatable, Sendable {
        public let center: [Double]
        public let outer: Double
        public let inner: Double
        public let tint: String
        public let text: ArtText?
    }

    public struct FieldArt: Decodable, Equatable, Sendable {
        public let glyphs: String
        public let tracking: Double
        public let endZones: [EndZoneArt]
        public let midfield: MidfieldArt
    }
}
