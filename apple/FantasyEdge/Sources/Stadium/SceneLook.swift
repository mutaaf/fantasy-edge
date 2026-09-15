import Foundation

// The scene's `look`: every visual-only number the renderer reads, decoded
// from `design/tokens.json` as the API embeds it, one section per actor.
//
// This file is the renderer's whole vocabulary of appearance. A size, an
// opacity, a light's lumens or a crowd's density that is not a field here is
// not allowed in `Stadium/`, and `tests/test_replay_scene.py` holds that line:
// it reads every `let` between the markers below and fails if tokens.json does
// not carry the same key, so a web or Android renderer can always reach the
// value the headset used.
//
// Each actor owns its section (docs/ART_BIBLE.md). A specialist adds fields to
// their own struct and their own block of tokens.json, and nothing else.

// LOOK-BEGIN

extension SceneSpec {
    /// A value that differs between the stadium and the tabletop.
    public struct PerMode<T: Decodable & Equatable & Sendable>: Decodable, Equatable, Sendable {
        public let stadium: T
        public let tabletop: T
        public func value(tabletop isTabletop: Bool) -> T { isTabletop ? tabletop : stadium }
    }

    public struct Look: Decodable, Equatable, Sendable {
        public let experience: ExperienceLook
        public let field: FieldLook
        public let sideline: SidelineLook
        public let bowl: BowlLook
        public let crowd: CrowdLook
        public let lighting: LightingLook
        public let sky: SkyLook
        public let broadcast: BroadcastLook
        public let moments: MomentsLook
        public let audio: AudioLook

        // MARK: experience

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

        // MARK: field

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

        // MARK: sideline

        public struct Boards: Decodable, Equatable, Sendable {
            public let brightness: Double
            public let panelYards: Double
        }

        public struct SidelineLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let boards: Boards
        }

        // MARK: bowl

        public struct BowlLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let rows: [String: Int]
            public let segments: Int
            public let aisleEvery: Int
            public let aisleYards: Double
            public let railYards: Double
            public let railRadius: Double
            public let wallTopBand: Double
            public let aisleOffset: Int
        }

        // MARK: crowd

        public struct Atlas: Decodable, Equatable, Sendable {
            public let columns: Int
            public let rows: Int
            public let armsUpFromRow: Int
            public let cellPixels: [Int]
        }

        public struct Shirts: Decodable, Equatable, Sendable {
            public let team: Double
            public let neutral: Double
            public let dark: Double
        }

        public struct CrowdTint: Decodable, Equatable, Sendable {
            public let normal: Double
            public let dim: Double
            public let bright: Double
        }

        public struct Clearance: Decodable, Equatable, Sendable {
            public let radius: Double
            public let height: Double
        }

        public struct CrowdLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let seed: UInt64
            public let fill: Double
            public let seatsPerRow: PerMode<Int>
            public let fanYards: PerMode<[Double]>
            public let atlas: Atlas
            public let shirts: Shirts
            public let skin: [String]
            public let hair: [String]
            public let slices: Int
            public let bobYards: Double
            public let surgeYards: Double
            public let waveSeconds: Double
            public let tint: CrowdTint
            public let standingShare: Double
            public let scaleJitter: Double
            public let sideJitter: Double
            public let clearance: Clearance
            public let bobHz: Double
            public let surgeHz: Double
            public let waveWidth: Double
            public let shirtShade: [Double]
            public let rawShare: Double
        }

        // MARK: lighting

        public struct Flood: Decodable, Equatable, Sendable {
            public let count: Int
            public let lumens: Double
            public let innerDegrees: Double
            public let outerDegrees: Double
            public let reach: Double
            public let shadows: Int
            public let tabletopLumens: Double
            public let tabletopReach: Double
            public let color: String
            public let aimZ: [Double]
        }

        public struct Rim: Decodable, Equatable, Sendable {
            public let phase: Double
            public let farSideMaxZ: Double
            public let lampYards: PerMode<[Double]>
            public let heightAbove: PerMode<Double>
            /// How wide the bank model is authored, so it scales to `lampYards`.
            public let modelWidthYards: Double
        }

        public struct LightingBank: Decodable, Equatable, Sendable {
            public let housing: String
            public let housingRoughness: Double
            public let housingMetallic: Double
            public let steel: String
            public let steelRoughness: Double
            public let steelMetallic: Double
            public let lensColor: String
            public let lensGain: Double
            public let faceGain: Double
        }

        public struct LightingGlow: Decodable, Equatable, Sendable {
            public let coreYards: PerMode<Double>
            public let haloYards: PerMode<Double>
            public let bloomYards: PerMode<Double>
            public let coreOpacity: Double
            public let haloOpacity: Double
            public let bloomOpacity: Double
            public let liftYards: Double
            public let color: String
            public let spillYards: [Double]
            public let spillForwardYards: Double
            public let spillDropYards: Double
            public let spillOpacity: Double
        }

        public struct LightingBeams: Decodable, Equatable, Sendable {
            public let perBank: Int
            public let fanYards: Double
            public let lengthYards: PerMode<Double>
            public let startWidthYards: Double
            public let endWidthYards: Double
            public let opacity: PerMode<Double>
            public let color: String
            public let overdrawCapScreens: Double
            public let dustOpacity: PerMode<Double>
            public let dustTileYards: Double
            public let dustScrollPerSecond: Double
        }

        public struct LightingHaze: Decodable, Equatable, Sendable {
            public let heights: [Double]
            public let inner: Double
            public let outer: Double
            public let repeatsAround: Double
            public let opacity: Double
            public let color: String
        }

        public struct LightingStrobe: Decodable, Equatable, Sendable {
            public let lensGain: Double
            public let glowGain: Double
            public let beamGain: Double
        }

        public struct LightingWash: Decodable, Equatable, Sendable {
            public let glowTint: Double
            public let beamTint: Double
        }

        public struct LightingLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let probeIntensityExponent: Double
            public let probeOnTabletop: Bool
            public let flood: Flood
            public let rim: Rim
            public let bank: LightingBank
            public let glow: LightingGlow
            public let beams: LightingBeams
            public let haze: LightingHaze
            public let strobe: LightingStrobe
            public let wash: LightingWash
        }

        // MARK: sky

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

        // MARK: broadcast

        public struct NearSeat: Decodable, Equatable, Sendable {
            public let yards: Double
            public let minScale: Double
        }

        public struct Emphasis: Decodable, Equatable, Sendable {
            public let core: Double
            public let halo: Double
        }

        public struct Trail: Decodable, Equatable, Sendable {
            public let core: PerMode<Double>
            public let haloScale: Double
            public let haloOpacity: Double
            public let ghostOpacity: Double
            public let nearSeat: NearSeat
            public let scoreEmphasis: Emphasis
        }

        public struct BallGlow: Decodable, Equatable, Sendable {
            public let yards: PerMode<Double>
            public let opacity: Double
        }

        public struct BallLook: Decodable, Equatable, Sendable {
            public let lengthYards: Double
            public let widthYards: Double
            public let scale: PerMode<Double>
            public let liftYards: Double
            public let spinPerSecond: Double
            public let color: String
            public let roughness: Double
            public let glow: BallGlow
        }

        public struct BeaconLook: Decodable, Equatable, Sendable {
            public let width: PerMode<Double>
            public let opacity: Double
        }

        public struct LaserLook: Decodable, Equatable, Sendable {
            public let width: Double
            public let glowWidth: Double
            public let glowOpacity: Double
            public let lift: Double
        }

        public struct HorizonLook: Decodable, Equatable, Sendable {
            public let thickness: PerMode<Double>
            public let railOpacity: Double
            public let opacity: Double
            public let fillOpacity: Double
            public let labelHeight: PerMode<Double>
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

        // MARK: moments

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

        // MARK: audio

        public struct AudioLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let bedGain: Double
            public let roarGain: Double
            public let groanGain: Double
            public let chimeGain: Double
            public let bedEmitters: Int
        }
    }
}

// LOOK-END

extension SceneSpec.Look {
    /// Every section's asset map, keyed by actor, for the loader.
    public var assetSections: [(String, [String: String])] {
        [("experience", experience.assets), ("field", field.assets), ("sideline", sideline.assets),
         ("bowl", bowl.assets), ("crowd", crowd.assets), ("lighting", lighting.assets),
         ("sky", sky.assets), ("broadcast", broadcast.assets), ("audio", audio.assets)]
    }

    /// Every section's model map (`.usdz` for Apple, a `.glb` sibling for the
    /// web and Android), keyed by actor.
    public var modelSections: [(String, [String: String])] {
        [("experience", experience.models), ("field", field.models), ("sideline", sideline.models),
         ("bowl", bowl.models), ("crowd", crowd.models), ("lighting", lighting.models),
         ("sky", sky.models), ("broadcast", broadcast.models), ("audio", audio.models)]
    }

    /// The look the app bundles, for a 1.0 server that sends none. It is the
    /// same tokens.json file, so there is still one source.
    public static func bundled(_ bundle: Bundle = .main) -> SceneSpec.Look? {
        guard let url = bundle.url(forResource: "tokens", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        struct Tokens: Decodable { let visual: SceneSpec.Look }
        return try? JSONDecoder().decode(Tokens.self, from: data).visual
    }
}
