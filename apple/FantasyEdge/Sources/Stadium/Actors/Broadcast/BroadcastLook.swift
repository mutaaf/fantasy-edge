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

    public struct TrailTail: Decodable, Equatable, Sendable {
        public let opacity: Double
        public let power: Double
    }

    public struct TrailAge: Decodable, Equatable, Sendable {
        public let decay: Double
        public let minOpacity: Double
        public let thin: Double
        public let minScale: Double
        public let individual: Int
        public let historyColor: String
        public let historyOpacity: Double
    }

    public struct Trail: Decodable, Equatable, Sendable {
        public let core: SceneSpec.PerMode<Double>
        public let coreOpacity: Double
        public let haloScale: Double
        public let haloOpacity: Double
        public let tail: TrailTail
        public let age: TrailAge
        public let nearSeat: NearSeat
        public let scoreEmphasis: Emphasis
        public let tabletopView: [Double]
    }

    public struct BallGlow: Decodable, Equatable, Sendable {
        public let yards: SceneSpec.PerMode<Double>
        public let opacity: Double
    }

    public struct BallFlight: Decodable, Equatable, Sendable {
        public let byStyle: [String: String]
        public let byType: [String: String]
        public let byShape: [String: String]
        public let spiralPerSecond: Double
        public let wobbleDegrees: Double
        public let wobbleHz: Double
        public let tumblePerSecond: Double
        public let carryTiltDegrees: Double
        public let carryBobYards: Double
        public let carryBobHz: Double
        public let bounces: Int
        public let bounceYards: Double
        public let bounceShare: Double
    }

    public struct BallLook: Decodable, Equatable, Sendable {
        public let lengthYards: Double
        public let widthYards: Double
        public let scale: SceneSpec.PerMode<Double>
        public let modelMetersPerYard: Double
        public let liftYards: Double
        public let color: String
        public let roughness: Double
        public let glow: BallGlow
        public let flight: BallFlight
    }

    public struct BeaconLook: Decodable, Equatable, Sendable {
        public let width: SceneSpec.PerMode<Double>
        public let opacity: Double
    }

    public struct LineTexture: Decodable, Equatable, Sendable {
        public let feather: Double
        public let grass: Double
    }

    public struct LineTag: Decodable, Equatable, Sendable {
        public let heightYards: SceneSpec.PerMode<Double>
        public let fromSideline: Double
        public let aheadYards: Double
        public let opacity: Double
        public let pixels: Int
    }

    public struct LaserLook: Decodable, Equatable, Sendable {
        public let width: Double
        public let opacity: Double
        public let lift: Double
        public let texture: LineTexture
        public let tag: LineTag
    }

    public struct HorizonMarker: Decodable, Equatable, Sendable {
        public let yards: SceneSpec.PerMode<Double>
        public let opacity: Double
    }

    public struct HorizonLabel: Decodable, Equatable, Sendable {
        public let heightYards: SceneSpec.PerMode<Double>
        public let gapYards: Double
        public let opacity: Double
        public let pixels: Int
    }

    public struct HorizonLook: Decodable, Equatable, Sendable {
        public let thickness: SceneSpec.PerMode<Double>
        public let swell: Double
        public let haloScale: Double
        public let opacity: Double
        public let haloOpacity: Double
        public let inkMix: Double
        public let tintGain: Double
        public let smoothing: Double
        public let endFade: Double
        public let textureWidth: Int
        public let marker: HorizonMarker
        public let label: HorizonLabel
    }

    public struct RibbonLegibility: Decodable, Equatable, Sendable {
        public let minArcMinutes: Double
    }

    public struct RibbonScroll: Decodable, Equatable, Sendable {
        public let yardsPerSecond: Double
    }

    public struct RibbonFlash: Decodable, Equatable, Sendable {
        public let seconds: Double
        public let words: [String: String]
    }

    public struct RibbonLook: Decodable, Equatable, Sendable {
        public let heightPixels: Int
        public let segmentYards: Double
        public let segments: Int
        public let offset: Double
        public let textShare: Double
        public let legibility: RibbonLegibility
        public let scroll: RibbonScroll
        public let flash: RibbonFlash
    }

    /// How the moment banner looks. Its size, height, timing and kinds are
    /// Moments' contract, `visual.moments.banner`.
    public struct BannerLook: Decodable, Equatable, Sendable {
        public let widthYards: SceneSpec.PerMode<Double>
        public let pixels: [Int]
        public let glowOpacity: Double
        public let glowScale: Double
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
        public let banner: BannerLook
    }
}

// LOOK-END
