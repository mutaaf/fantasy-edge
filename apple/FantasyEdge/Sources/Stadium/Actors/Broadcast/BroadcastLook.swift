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

    public struct TrailEdge: Decodable, Equatable, Sendable {
        public let fullDegrees: Double
        public let goneDegrees: Double
        public let minOpacity: Double
        public let minScale: Double
        public let shapes: [String]

        public init(fullDegrees: Double, goneDegrees: Double, minOpacity: Double, minScale: Double, shapes: [String] = []) {
            self.fullDegrees = fullDegrees
            self.goneDegrees = goneDegrees
            self.minOpacity = minOpacity
            self.minScale = minScale
            self.shapes = shapes
        }
    }

    public struct TrailKick: Decodable, Equatable, Sendable {
        public let fadeSeconds: Double
        public let restOpacity: Double
        public let fullDegrees: Double
        public let goneDegrees: Double
    }

    public struct TrailLive: Decodable, Equatable, Sendable {
        public let opacity: Double
        public let intervalSeconds: Double
    }

    public struct TrailLowSeat: Decodable, Equatable, Sendable {
        public let apexOverEye: Double
        public let minApexYards: Double
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
        public let edge: TrailEdge
        public let kick: TrailKick
        public let live: TrailLive
        public let lowSeat: TrailLowSeat
    }

    public struct BallGlow: Decodable, Equatable, Sendable {
        public let yards: SceneSpec.PerMode<Double>
        public let opacity: Double
        /// The light never subtends less than this at the wearer's eye, and
        /// never grows past `maxYards`; it sits `coverYards` toward them, so
        /// far off it covers the dark leather rather than ringing it.
        public let minArcMinutes: Double
        public let maxYards: Double
        public let coverYards: Double
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
        /// The magnification at `farYards` and beyond.
        public let scale: SceneSpec.PerMode<Double>
        /// Life size within `nearYards`, easing to `scale` by `farYards`.
        public let nearScale: Double
        public let nearYards: Double
        public let farYards: Double
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
        public let edge: HorizonEdge
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
        /// The clock and the down may narrow to this share of their size to
        /// fit a segment before a word is dropped.
        public let fitFloor: Double
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

    public struct VideoBoardLegibility: Decodable, Equatable, Sendable {
        public let minArcMinutes: Double
    }

    public struct VideoBoardLook: Decodable, Equatable, Sendable {
        public let pixels: [Int]
        public let brightness: Double
        public let offset: Double
        public let scorebugShare: Double
        /// Each club's block across the top, as a share of the board's width.
        public let sideShare: Double
        /// The down-and-distance strip under the score, a share of the height.
        public let downShare: Double
        public let smallTextShare: Double
        public let textShare: Double
        public let lines: Int
        public let plays: Int
        public let legibility: VideoBoardLegibility
    }

    public struct HorizonEdge: Decodable, Equatable, Sendable {
        public let fullDegrees: Double
        public let goneDegrees: Double
    }

    public struct DriveLogLook: Decodable, Equatable, Sendable {
        public let rows: Int
        public let newestLines: Int
        public let olderLines: Int
    }

    /// The play's ground card: a ring on the snap, then the ball's shadow.
    public struct PlayMarker: Decodable, Equatable, Sendable {
        public let pulseSeconds: Double
        public let pulseYards: SceneSpec.PerMode<Double>
        public let pulseOpacity: Double
        public let pulseColor: String
        public let shadowYards: SceneSpec.PerMode<Double>
        public let shadowOpacity: Double
        public let shadowFadeYards: Double
    }

    public struct PlayHeights: Decodable, Equatable, Sendable {
        /// How high over the grass a carried leg of a trail lies.
        public let trailLift: Double
    }

    /// What the renderer reads of `visual.broadcast.play`; the path itself
    /// is laid out by scene.play_path and arrives on every arc.
    /// What the renderer needs of a kick: where the ball leaves play.
    public struct PlayGoalKick: Decodable, Equatable, Sendable {
        public let netYards: Double
    }

    public struct PlayLook: Decodable, Equatable, Sendable {
        public let heights: PlayHeights
        public let goalKick: PlayGoalKick
        /// How long a new drive waits for the play on the field to finish
        /// before it takes the stage.
        public let holdSwitchSeconds: Double
        /// The rest between one play landing and the next snap, in real seconds.
        public let beatSeconds: Double
        public let marker: PlayMarker
        /// The ball's glow grows by this while it is in the air.
        public let flightGlowScale: Double
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
        public let videoBoard: VideoBoardLook
        public let driveLog: DriveLogLook
        public let play: PlayLook
    }
}

// LOOK-END
