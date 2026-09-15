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
    }

    public struct Rim: Decodable, Equatable, Sendable {
        public let phase: Double
        public let farSideMaxZ: Double
        public let lampYards: SceneSpec.PerMode<[Double]>
        public let heightAbove: SceneSpec.PerMode<Double>
        public let poleYards: Double
        public let glowYards: SceneSpec.PerMode<Double>
        public let glowOpacity: Double
        public let hazeLength: SceneSpec.PerMode<Double>
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
}

// LOOK-END
