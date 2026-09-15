import Foundation

// visual.crowd: Crowd's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Crowd specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
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
        public let scale: SceneSpec.PerMode<Double>
        public let alphaCutoff: Double
        public let pairOffsetMetres: Double
    }

    public struct CrowdRings: Decodable, Equatable, Sendable {
        public let lod0Yards: Double
        public let lod1Yards: Double
        public let lod2Yards: Double
        public let ditherYards: Double
        public let lod0Max: Int
        public let lod1Max: Int
        public let lod2Max: Int
    }

    /// How a fan sits in Bowl's chair (visual.crowd.chair).
    public struct CrowdChair: Decodable, Equatable, Sendable {
        public let sitPoses: [String]
        public let sitForwardMetres: Double
        public let standForwardMetres: Double
        public let cardForwardMetres: Double
        public let pelvisMetres: Double
        public let referenceHeightMetres: Double
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
        public let seatPitchYards: SceneSpec.PerMode<Double>
        public let clearance: Clearance
        public let chair: CrowdChair
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
}

// LOOK-END
