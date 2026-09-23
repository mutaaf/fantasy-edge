import Foundation

// visual.sky: Sky's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Sky specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct SkyLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let radiusYards: Double
        public let skyGain: Double
        public let yawDegrees: Double
        public let cloudRadiusYards: Double
        public let cloudColor: String
        public let cloudOpacity: Double
        public let cloudDriftDegreesPerMinute: Double
        public let domeHeight: Double
        public let domeOpacity: Double
        public let domeColor: String
        public let domeInsetYards: Double
    }
}

// LOOK-END
