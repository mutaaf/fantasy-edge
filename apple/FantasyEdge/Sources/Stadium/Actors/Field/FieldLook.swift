import Foundation

// visual.field: Field's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Field specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct FieldPerLeague: Decodable, Equatable, Sendable {
        public let paintWhite: String
        public let paintYellow: String
        public let variation: String
    }

    public struct FieldCanvas: Decodable, Equatable, Sendable {
        public let x0: Double
        public let x1: Double
        public let y0: Double
        public let y1: Double
        public let halfX1: Double
        /// The half textures run past midfield to here (mip padding).
        public let halfTextureX1: Double
    }

    public struct FieldTurf: Decodable, Equatable, Sendable {
        public let tileYards: Double
        public let stripeTint: [String]
        public let stripeRoughness: [Double]
        public let surroundTint: String
        public let wearTint: String
        /// Scales the wear map; it also lies over the paint.
        public let wearStrength: Double
        public let specular: Double
    }

    public struct FieldPaint: Decodable, Equatable, Sendable {
        public let white: String
        public let yellow: String
        public let roughness: Double
        public let threshold: Double
        public let endZoneOpacity: Double
        /// How strongly blades show through paint and lettering.
        public let grassThrough: Double
    }

    public struct FieldLift: Decodable, Equatable, Sendable {
        public let wear: Double
        public let endZone: Double
        public let ring: Double
        public let paint: Double
        public let art: Double
    }

    public struct FieldLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let perLeague: FieldPerLeague
        public let canvas: FieldCanvas
        public let turf: FieldTurf
        public let paint: FieldPaint
        public let lift: FieldLift
    }
}

// LOOK-END
