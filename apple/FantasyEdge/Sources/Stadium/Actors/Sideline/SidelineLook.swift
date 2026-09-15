import Foundation

// visual.sideline: Sideline's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Sideline specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct Boards: Decodable, Equatable, Sendable {
        public let brightness: Double
        public let panelYards: Double
    }

    public struct PropMaterial: Decodable, Equatable, Sendable {
        public let color: String
        public let roughness: Double
        public let metallic: Double
        /// "team": the club whose side the prop stands on wears it.
        public let tint: String?
        /// An asset id whose grey channel cuts the surface out (nets).
        public let mask: String?
    }

    public struct SidelineLodSuffix: Decodable, Equatable, Sendable {
        public let stadium: String
        public let tabletop: String
    }

    public struct SidelineBenches: Decodable, Equatable, Sendable {
        public let count: Int
        public let spacing: Double
        public let centreGap: Double
    }

    public struct PropPlacement: Decodable, Equatable, Sendable {
        public let model: String
        /// Yards along the line from the team area's centre (sideline) or
        /// across the field from its centre (end line).
        public let along: Double
        /// Yards beyond the sideline or end line.
        public let offset: Double
    }

    public struct SidelineChains: Decodable, Equatable, Sendable {
        public let set: String
        public let box: String
        public let ground: String
        public let offset: Double
        public let boxOffset: Double
    }

    public struct SidelineLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let boards: Boards
        public let palette: [String: PropMaterial]
        public let lodSuffix: SidelineLodSuffix
        public let metresPerYard: Double
        public let benches: SidelineBenches
        public let dressing: [PropPlacement]
        public let endLine: [PropPlacement]
        public let chains: SidelineChains
    }
}

// LOOK-END
