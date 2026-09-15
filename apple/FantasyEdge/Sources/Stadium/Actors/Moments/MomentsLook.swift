import Foundation

// visual.moments: Moments's whole vocabulary of appearance, decoded from
// design/tokens.json. Owned by the Moments specialist (docs/ART_BIBLE.md).
// tests/test_replay_scene.py fails if any `let` here is a key tokens.json
// does not carry, so every client can reach the value the headset used.

// LOOK-BEGIN

extension SceneSpec.Look {
    public struct MomentsLook: Decodable, Equatable, Sendable {
        public let celebrate: [String]
        public let strobeHz: Double
        public let strobeGain: Double
        /// Seconds after arrival for each step of a moment, by kind; -1 skips it.
        public let timeline: [String: MomentTimeline]
        /// Which burst a kind fires ("none" for no particles).
        public let burstFor: [String: String]
        public let bursts: [String: MomentBurst]
        /// The contract for whoever draws the banner: size, dwell, where.
        public let banner: MomentBanner
        public let reduceMotion: MomentReduceMotion
        /// How the stadium treats each cue, keyed by the cue's `treatment`.
        public let cues: [String: CueTreatment]
    }

    public struct MomentTimeline: Decodable, Equatable, Sendable {
        public let whistle: Double
        public let surge: Double
        public let strobe: Double
        public let strobeSeconds: Double
        public let particles: Double
        public let banner: Double
        public let chime: Double
        public let settle: Double
        /// How long the side that scored (or took the ball) stands; -1 not at all.
        public let standSeconds: Double
        /// How long the side that lost the ball groans; -1 not at all.
        public let groanSeconds: Double
    }

    public struct MomentBurst: Decodable, Equatable, Sendable {
        /// How many rim positions fire (confetti: one sheet over the field).
        public let shells: Int
        public let birthRate: Double
        public let burstSeconds: Double
        public let lifeSpan: Double
        /// Yards per second, and the cone the shell opens into.
        public let speed: Double
        public let spreadDegrees: Double
        public let size: Double
        /// Yards above the bank (or the field, for confetti) the shell opens at.
        public let lift: Double
        public let gravity: Double
        /// Drag: how quickly a shell's sparks slow, which is what opens it into a ring.
        public let damping: Double
        /// Radius of the sphere sparks are born on; 0 for a sheet.
        public let radius: Double
        /// How far a spark smears along its motion (1 is a round dot).
        public let streak: Double
        /// Seconds between shells.
        public let stagger: Double
        /// Share of particles that spawn a glitter trail; 0 for none.
        public let sparkle: Double
        public let additive: Bool
        /// Width of an emitting sheet, in yards; 0 is a point shell.
        public let widthYards: Double
    }

    public struct MomentBanner: Decodable, Equatable, Sendable {
        public let widthDegrees: Double
        public let minHeightDegrees: Double
        public let dwellSeconds: Double
        public let enterSeconds: Double
        public let exitSeconds: Double
        public let heightYards: Double
        public let anchor: String
        public let kinds: [String]
        public let subtitleDegrees: Double
    }

    public struct MomentReduceMotion: Decodable, Equatable, Sendable {
        public let glowSeconds: Double
        public let swellDb: Double
        public let strobe: Bool
        public let particles: Bool
    }

    public struct CueTreatment: Decodable, Equatable, Sendable {
        /// A key of visual.audio.assets, or "none".
        public let audio: String
        /// What the crowd does: stand, clap, final (winners stand, losers sit), none.
        public let crowd: String
        /// A key of bursts, or "none".
        public let burst: String
        public let strobeSeconds: Double
        public let seconds: Double
    }
}

// LOOK-END
