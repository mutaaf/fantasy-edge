import Foundation

// visual.audio: Audio's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Audio specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct AudioLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let bedGain: Double
        public let roarGain: Double
        public let groanGain: Double
        public let chimeGain: Double
        public let bedEmitters: Int
    }
}

// LOOK-END
