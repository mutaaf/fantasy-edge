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

    public struct SidelineLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let boards: Boards
    }
}

// LOOK-END
