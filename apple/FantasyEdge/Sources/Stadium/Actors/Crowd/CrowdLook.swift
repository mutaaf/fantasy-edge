import Foundation
import simd

// visual.crowd: Crowd's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Crowd specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct CrowdTint: Decodable, Equatable, Sendable {
        public let normal: Double
        public let dim: Double
        public let meshDim: Double
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
        public let floodFill: Double
        public let floodFillAbout: String
    }

    public struct CrowdRings: Decodable, Equatable, Sendable {
        public let lod0Yards: Double
        public let lod1Yards: Double
        public let lod2Yards: Double
        public let ditherYards: Double
        public let minCardYards: Double
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
        public let kitPelvisMetres: Double
        public let referenceHeightMetres: Double
    }

    /// One pose and the share of a near slot's fans who wear it.
    public struct CrowdMixShare: Decodable, Equatable, Sendable {
        public let pose: String
        public let share: Double
    }

    /// Whose crowd it is: how much of the bowl the visitors and the unaligned fill.
    public struct CrowdSupport: Decodable, Equatable, Sendable {
        public let visitingShare: Double
        public let neutralShare: Double
        public let benchRowsTier: String
        public let cornerFrom: Double
        /// Inside a visiting block, how many of the seats are theirs; at its edge, how few.
        public let coreProbability: Double
        public let edgeProbability: Double
        /// The grain the draw is made on, so support comes in blocks rather than salt and pepper.
        public let blockRows: Int
        public let blockSeats: Int
        /// How far up a tier the block reaches at its core, tapering to nothing at the tail.
        public let tailRows: Double
        /// A few of the other club, sitting where they should not be.
        public let strayProbability: Double
    }

    public struct CrowdBlowout: Decodable, Equatable, Sendable {
        public let margin: Double
        public let fromPeriod: Int
        public let clockSeconds: Double
        public let upperFactor: Double
        public let lowerFactor: Double
    }

    public struct CrowdEmpty: Decodable, Equatable, Sendable {
        public let upperFactor: Double
        public let cornerFactor: Double
        public let endZoneFactor: Double
        /// Empties come in blocks of this size, and along the ends of a run.
        public let blockRows: Int
        public let blockSeats: Int
        public let blockEmptiness: Double
        public let runEndSeats: Int
        public let runEndFactor: Double
        public let blowout: CrowdBlowout
    }

    public struct CrowdIdleStand: Decodable, Equatable, Sendable {
        public let early: Double
        public let late: Double
        public let aboutPeriod: Int
    }

    public struct CrowdLuma: Decodable, Equatable, Sendable {
        public let min: Double
        public let max: Double
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
        public let clubLuma: CrowdLuma
        public let cardContrast: Double
        public let tint: CrowdTint
        public let roughness: Double
        public let castShadows: Bool
        public let castShadowsAbout: String
        public let standingShare: Double
        public let idleSeconds: [Double]
        public let waveSeconds: Double
        public let waveWidth: Double
        public let surgeHz: Double
        public let groanSeconds: Double
        public let settleSeconds: [Double]
        public let thirdDownStand: Bool
        public let sideJitter: Double
        public let nearPoses: [String]
        public let nearPhases: Int
        public let nearMixAbout: String
        public let nearMix: [String: [CrowdMixShare]]
        public let chatShare: Double
        public let lookYards: Double
        public let rippleSeconds: Double
        public let rippleYards: Double
        public let riseStageSeconds: Double
        public let supportAbout: String
        public let support: CrowdSupport
        public let emptySeatsAbout: String
        public let emptySeats: CrowdEmpty
        public let reactionsAbout: String
        public let hushOwnOffence: Bool
        public let visitorCelebration: Double
        public let idleStandShare: CrowdIdleStand
        public let settleStageSeconds: Double
        public let momentRippleAbout: String
        public let tintRiseSeconds: Double
        public let tintJitter: Double
    }
}

// LOOK-END

/// How a frozen kit fan is turned onto its seat. The kit faces +Z (manifest
/// `forward`, measured at export); this turns +Z onto the seat's facing. One
/// definition, used by CrowdActor to place fans and by apple/verify_scene.swift
/// to check that every placed fan faces the field.
public enum CrowdFacing {
    public static let kitForward = SIMD3<Float>(0, 0, 1)

    public static func rotation(facing: SIMD3<Float>) -> simd_quatf {
        simd_quatf(angle: atan2(facing.x, facing.z), axis: SIMD3(0, 1, 0))
    }

    /// Where a fan placed on this facing actually looks.
    public static func placedForward(facing: SIMD3<Float>) -> SIMD3<Float> {
        rotation(facing: facing).act(kitForward)
    }
}
