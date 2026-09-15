import Foundation

// visual.experience: Experience's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Experience specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct Camera: Decodable, Equatable, Sendable {
        public let eyeMeters: Double
        public let seatFadeSeconds: Double
    }

    public struct Baseplate: Decodable, Equatable, Sendable {
        public let marginScale: Double
        public let thicknessMeters: Double
        public let rimOpacity: Double
        public let rimRadiusYards: Double
    }

    public struct Cutaway: Decodable, Equatable, Sendable {
        public let side: String
        public let from: Double
        public let to: Double
    }

    public struct TabletopLook: Decodable, Equatable, Sendable {
        public let cutaway: Cutaway
    }

    public struct ExperienceLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let camera: Camera
        public let baseplate: Baseplate
        public let tabletop: TabletopLook
    }
}

// LOOK-END
