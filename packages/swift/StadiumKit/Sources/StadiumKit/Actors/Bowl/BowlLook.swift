import Foundation

// visual.bowl: Bowl's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Bowl specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct BowlLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let seatColor: String
        public let yardMeters: Double
        public let nearLift: Double
        public let nearDeckLift: Double
        public let nearDeckColor: String
        /// Undersides - the deck's overhang, the fascia, the lip - carry a low
        /// self-light. Nothing in a night bowl lights a surface that faces the
        /// ground, so without this they render black whatever their albedo.
        public let soffitLift: Double
        public let soffitColor: String
        public let pressRoomLift: Double
        /// Fractions of `pressRoomLift` the room's own surfaces take from its
        /// ceiling strips: the desk catches the most, the carpet the least.
        public let pressDeskLift: Double
        public let pressChairLift: Double
        public let pressFloorLift: Double
        public let glassOpacity: Double
        public let rows: [String: Int]
        public let segments: Int
        public let aisleEvery: Int
        public let aisleYards: Double
        public let railYards: Double
        public let railRadius: Double
        public let wallTopBand: Double
        public let aisleOffset: Int
    }
}

// LOOK-END
