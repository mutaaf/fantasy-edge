import Foundation

// visual.broadcast: Broadcast's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Broadcast specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct NearSeat: Decodable, Equatable, Sendable {
        public let yards: Double
        public let minScale: Double
    }

    public struct Emphasis: Decodable, Equatable, Sendable {
        public let core: Double
        public let halo: Double
    }

    public struct Trail: Decodable, Equatable, Sendable {
        public let core: SceneSpec.PerMode<Double>
        public let haloScale: Double
        public let haloOpacity: Double
        public let ghostOpacity: Double
        public let nearSeat: NearSeat
        public let scoreEmphasis: Emphasis
    }

    public struct BallGlow: Decodable, Equatable, Sendable {
        public let yards: SceneSpec.PerMode<Double>
        public let opacity: Double
    }

    public struct BallLook: Decodable, Equatable, Sendable {
        public let lengthYards: Double
        public let widthYards: Double
        public let scale: SceneSpec.PerMode<Double>
        public let liftYards: Double
        public let spinPerSecond: Double
        public let color: String
        public let roughness: Double
        public let glow: BallGlow
    }

    public struct BeaconLook: Decodable, Equatable, Sendable {
        public let width: SceneSpec.PerMode<Double>
        public let opacity: Double
    }

    public struct LaserLook: Decodable, Equatable, Sendable {
        public let width: Double
        public let glowWidth: Double
        public let glowOpacity: Double
        public let lift: Double
    }

    public struct HorizonLook: Decodable, Equatable, Sendable {
        public let thickness: SceneSpec.PerMode<Double>
        public let railOpacity: Double
        public let opacity: Double
        public let fillOpacity: Double
        public let labelHeight: SceneSpec.PerMode<Double>
        public let labelOpacity: Double
    }

    public struct RibbonLook: Decodable, Equatable, Sendable {
        public let heightPixels: Int
        public let segmentYards: Double
        public let segments: Int
    }

    public struct BroadcastLook: Decodable, Equatable, Sendable {
        public let assets: [String: String]
        public let models: [String: String]
        public let trail: Trail
        public let ball: BallLook
        public let beacon: BeaconLook
        public let laser: LaserLook
        public let horizon: HorizonLook
        public let ribbon: RibbonLook
    }
}

// LOOK-END
