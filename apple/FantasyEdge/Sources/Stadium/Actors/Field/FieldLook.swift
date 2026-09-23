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
        /// How much sheen a grazing blade takes on the turf graph, per stripe
        /// (with the mower, against it) and on the surround.
        public let stripeSheen: [Double]
        public let surroundSheen: Double
    }

    public struct FieldPaint: Decodable, Equatable, Sendable {
        public let white: String
        public let yellow: String
        public let roughness: Double
        public let threshold: Double
        public let endZoneOpacity: Double
        /// The border and end lines: off-white, duller than the grass, more grass through.
        public let border: String
        public let borderRoughness: Double
        public let borderGrassCut: Double
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

    public struct FieldShaderTextures: Decodable, Equatable, Sendable {
        /// Blade height on the turf tile, raw, for the paint graph's blade-through.
        public let blades: String
        /// Low-frequency paint wear, raw, on the paint graph's wear tile.
        public let wear: String
        /// The turf's packed occlusion, roughness and height, raw, for the turf graph.
        public let turfOrm: String
    }

    public struct FieldShells: Decodable, Equatable, Sendable {
        /// Off until the patch stops reading as a rectangle (docs/actors/field-sideline.md).
        public let enabled: Bool
        /// shaderGraph.materials id.
        public let material: String
        /// 4 x 2 coverage atlas, raw.
        public let atlas: String
        /// The patch, in field yards: x range, and how far in from the home sideline.
        public let fromX: Double
        public let toX: Double
        public let depth: Double
        /// Blades thin out over this many yards inside the patch edge.
        public let fade: Double
        /// Layers drawn, counted up from the ground (the densest bottom ones
        /// are left to the flat turf).
        public let firstLayer: Int
        public let lastLayer: Int
    }

    public struct FieldLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let perLeague: FieldPerLeague
        public let canvas: FieldCanvas
        public let turf: FieldTurf
        public let paint: FieldPaint
        public let lift: FieldLift
        /// shaderGraph.materials id the paint and lettering use when it loads.
        public let paintMaterial: String
        /// shaderGraph.materials id the turf uses when it loads.
        public let turfMaterial: String
        public let shaderTextures: FieldShaderTextures
        public let shells: FieldShells
    }
}

// LOOK-END
