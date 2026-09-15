import Foundation

// visual.crowd: Crowd's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Crowd specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
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
        public let seatsPerRow: SceneSpec.PerMode<Int>
        public let fanYards: SceneSpec.PerMode<[Double]>
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
}

// LOOK-END
