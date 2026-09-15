import Foundation

// visual.field: Field's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Field specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct Turf: Decodable, Equatable, Sendable {
        public let tileYards: Double
        public let stripeTint: [String]
        public let stripeRoughness: [Double]
        public let surroundTint: String
        public let normalScale: Double
        public let paintOpacity: Double
        public let endZonePaintOpacity: Double
        public let paintRoughness: Double
    }

    public struct Lines: Decodable, Equatable, Sendable {
        public let tenWidth: Double
        public let fiveWidth: Double
        public let hashWidth: Double
        public let hashLength: Double
        public let border: Double
        public let numberHeight: Double
        public let numberInset: Double
        public let endZoneTextHeight: Double
        public let lift: Double
    }

    public struct FieldLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let turf: Turf
        public let lines: Lines
    }
}

// LOOK-END
