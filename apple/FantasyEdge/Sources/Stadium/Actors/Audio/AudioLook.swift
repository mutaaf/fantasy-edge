import Foundation

// visual.audio: Audio's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Audio specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct AudioLook: Decodable, Equatable, Sendable {
        /// Sound id -> the .caf the headset plays (the .ogg twin sits beside it).
        public let assets: [String: String]
        public let models: [String: String]
        /// The mix, in dB, by sound id.
        public let gains: [String: Double]
        public let masterGain: Double
        public let bedEmitters: Int
        /// Extra dB for the bed emitter nearest the wearer, inside `nearYards`.
        public let nearBoost: Double
        public let nearYards: Double
        public let rolloff: Double
        /// A RealityKit reverb preset name (outside, concertHall, ...).
        public let reverb: String
        public let reverbLevel: Double
        public let maxSources: Int
        public let playWhistle: AudioWhistle
        public let tabletop: AudioTabletop
    }

    public struct AudioWhistle: Decodable, Equatable, Sendable {
        public let gain: Double
        /// Whistle one play in `every`; 0 turns it off.
        public let every: Int
        /// Seconds after the ball's flight ends.
        public let afterFlight: Double
    }

    public struct AudioTabletop: Decodable, Equatable, Sendable {
        public let gain: Double
        public let bedEmitters: Int
        public let rolloff: Double
        public let effects: Bool
    }
}

// LOOK-END
