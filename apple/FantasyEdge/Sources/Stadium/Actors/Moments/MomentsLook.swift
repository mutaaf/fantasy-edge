import Foundation

// visual.moments: Moments's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Moments specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct MomentsLook: Decodable, Equatable, Sendable {
        public let celebrate: [String]
        public let strobeHz: Double
        public let fireworks: Int
        public let particlesPerBurst: Int
        public let strobeGain: Double
        public let fireworksLift: Double
        public let fireworksScale: Double
        public let fireworksSeconds: Double
    }
}

// LOOK-END
