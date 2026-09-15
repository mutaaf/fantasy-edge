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

        public struct CrowdTint: Decodable, Equatable, Sendable {
            public let normal: Double
            public let dim: Double
            public let bright: Double
        }

        public struct Clearance: Decodable, Equatable, Sendable {
            public let radius: Double
            public let height: Double
        }

        /// The Blender crowd kit's images, composed per matchup rather than
        /// sampled directly, so they are not loaded as textures up front.
        public struct CrowdKit: Decodable, Equatable, Sendable {
            public let fanAlbedo: String
            public let fanMask: String
            public let impostorAlbedo: String
            public let impostorMask: String
            public let manifest: String
        }

        public struct CrowdImpostor: Decodable, Equatable, Sendable {
            public let cellPixels: [Int]
            public let blockCells: [Int]
            public let blocksPerRow: Int
            public let worldMetres: [Double]
            public let viewsYaw: [Double]
            public let scale: PerMode<Double>
            public let alphaCutoff: Double
            public let pairOffsetMetres: Double
        }

        public struct CrowdRings: Decodable, Equatable, Sendable {
            public let lod0Yards: Double
            public let lod1Yards: Double
            public let lod0Max: Int
            public let lod1Max: Int
        }

        public struct CrowdLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let kit: CrowdKit
            public let fans: Int
            public let fanGrid: [Int]
            public let poses: [String]
            public let impostor: CrowdImpostor
            public let metresPerYard: Double
            public let seed: UInt64
            public let fill: Double
            public let seatPitchYards: PerMode<Double>
            public let clearance: Clearance
            public let rings: CrowdRings
            public let slices: Int
            public let cardVariants: Int
            public let sliceJitter: Double
            public let secondary: String
            public let shirtShade: [Double]
            public let rawShare: Double
            public let neutralShare: Double
            public let neutrals: [String]
            public let desaturate: [Double]
            public let cardContrast: Double
            public let tint: CrowdTint
            public let roughness: Double
            public let standingShare: Double
            public let idleSeconds: [Double]
            public let waveSeconds: Double
            public let waveWidth: Double
            public let surgeHz: Double
            public let groanSeconds: Double
            public let thirdDownStand: Bool
            public let sideJitter: Double
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
        }

        public struct Rim: Decodable, Equatable, Sendable {
            public let phase: Double
            public let farSideMaxZ: Double
            public let lampYards: PerMode<[Double]>
            public let heightAbove: PerMode<Double>
            public let poleYards: Double
            public let glowYards: PerMode<Double>
            public let glowOpacity: Double
            public let hazeLength: PerMode<Double>
            public let hazeRadius: Double
            public let hazeOpacity: Double
            public let coreGlowScale: Double
            public let coreGlowOpacity: Double
            public let hazeStartScale: Double
        }

        public struct LightingLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let probeIntensityExponent: Double
            public let flood: Flood
            public let rim: Rim
        }

        // MARK: sky

        public struct SkyLook: Decodable, Equatable, Sendable {
            public let assets: [String: String]
            public let models: [String: String]
            public let radiusYards: Double
            public let domeHeight: Double
            public let domeOpacity: Double
            public let domeColor: String
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
