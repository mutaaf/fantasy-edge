import Foundation

// visual.lighting: Lighting's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Lighting specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
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
    }

    public struct Rim: Decodable, Equatable, Sendable {
        public let phase: Double
        public let farSideMaxZ: Double
        public let lampYards: SceneSpec.PerMode<[Double]>
        public let heightAbove: SceneSpec.PerMode<Double>
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
        public let coreYards: SceneSpec.PerMode<Double>
        public let haloYards: SceneSpec.PerMode<Double>
        public let bloomYards: SceneSpec.PerMode<Double>
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

    public struct LightingBeamShader: Decodable, Equatable, Sendable {
        public let file: String
        public let prim: String
        public let color: String
        public let opacity: SceneSpec.PerMode<Double>
        public let dustRepeat: Double
        public let dustSpeed: Double
        public let dustFloor: Double
        public let dustAmount: Double
        public let viewPower: Double
        public let additive: Double
    }

    public struct LightingBeams: Decodable, Equatable, Sendable {
        public let perBank: Int
        public let fanYards: Double
        public let lengthYards: SceneSpec.PerMode<Double>
        public let startWidthYards: Double
        public let endWidthYards: Double
        public let opacity: SceneSpec.PerMode<Double>
        public let color: String
        public let overdrawCapScreens: Double
        public let startInsideOffsetYards: Double
        public let endHeightYards: SceneSpec.PerMode<Double>
        public let shader: LightingBeamShader
        public let dustOpacity: SceneSpec.PerMode<Double>
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
        public let beamGainMax: Double
        public let hazeGainMax: Double
        public let fieldWashGain: Double
    }

    public struct LightingWash: Decodable, Equatable, Sendable {
        public let glowTint: Double
        public let beamTint: Double
    }

    public struct LightingFill: Decodable, Equatable, Sendable {
        public let wallOffsetYards: Double
        public let wallRise: [Double]
        public let standOffYards: Double
        public let repeatsAround: Double
        public let tunnelScale: Double
        public let opacity: Double
        public let color: String
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
        public let fill: LightingFill
    }
}

// LOOK-END
