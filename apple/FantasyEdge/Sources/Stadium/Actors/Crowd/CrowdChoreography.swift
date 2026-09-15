import Foundation

/// What a group of fans does this frame, as a pure decision: no RealityKit,
/// so `apple/verify_crowd.swift` compiles it on a Mac and checks it.
///
/// The rule that matters most: a side watching the other team score never
/// looks like it is celebrating. It stays in its seats. A standing groan -
/// hands on heads - reads as cheering from across a bowl, which is how the
/// home crowd appeared to celebrate the visitors' field goal (integration-9).
public enum CrowdChoreography {
    public enum Pose: String, CaseIterable, Sendable {
        case sit, sitB = "sit_b", stand, clap = "clap_b", cheer = "cheer_a", groan
    }

    public enum CueKind: Int, Sendable { case sit = 0, stand = 1, clap = 2, groan = 3 }

    public struct Input: Sendable {
        /// This group sits in the away section.
        public var away: Bool
        public var isCard: Bool
        public var phase: Double
        public var standing: Bool
        public var slice: Int
        public var slices: Int
        public var time: Double
        public var reduceMotion: Bool
        /// `bowl.sectionTint.side`: whose moment is on, if any.
        public var tintSide: String?
        /// The side whose moment just ended, and when.
        public var lastScoringAway: Bool?
        public var lastScoringEnded: Double
        public var settleSeconds: (Double, Double)
        public var surgeAway: Bool?
        public var standingSideAway: Bool?
        public var idleSeconds: (Double, Double)
        public var waveSeconds: Double
        public var waveWidth: Double
        public var surgeHz: Double
        /// Cues that reach this group.
        public var cues: [CueKind]

        public init(away: Bool, isCard: Bool = false, phase: Double = 0, standing: Bool = false, slice: Int = 0, slices: Int = 12,
                    time: Double = 0, reduceMotion: Bool = false, tintSide: String? = nil, lastScoringAway: Bool? = nil,
                    lastScoringEnded: Double = 0, settleSeconds: (Double, Double) = (2.5, 5), surgeAway: Bool? = nil,
                    standingSideAway: Bool? = nil, idleSeconds: (Double, Double) = (2.5, 6.5), waveSeconds: Double = 16,
                    waveWidth: Double = 0.045, surgeHz: Double = 1.6, cues: [CueKind] = []) {
            self.away = away; self.isCard = isCard; self.phase = phase; self.standing = standing; self.slice = slice
            self.slices = slices; self.time = time; self.reduceMotion = reduceMotion; self.tintSide = tintSide
            self.lastScoringAway = lastScoringAway; self.lastScoringEnded = lastScoringEnded; self.settleSeconds = settleSeconds
            self.surgeAway = surgeAway; self.standingSideAway = standingSideAway; self.idleSeconds = idleSeconds
            self.waveSeconds = waveSeconds; self.waveWidth = waveWidth; self.surgeHz = surgeHz; self.cues = cues
        }
    }

    /// Is this group's side the one celebrating (true), the one that was scored on (false), or neither (nil)?
    public static func scoring(_ i: Input) -> Bool? {
        if let tint = i.tintSide, tint == "home" || tint == "away" { return (tint == "away") == i.away }
        if let last = i.lastScoringAway, last == i.away {
            let settle = i.settleSeconds.0 + (i.settleSeconds.1 - i.settleSeconds.0) * i.phase
            if i.time - i.lastScoringEnded < settle { return true }
        }
        return nil
    }

    public static func pose(_ i: Input) -> Pose {
        let scoring = Self.scoring(i)
        let seated: Pose = i.phase < 0.5 ? .sit : .sitB
        // Scored on: in the seats, whatever else is asking. Not negotiable by cues.
        if scoring == false { return seated }
        var pose: Pose
        if i.reduceMotion {
            pose = scoring == true ? .stand : (i.standing ? .stand : .sit)
        } else {
            let span = i.idleSeconds.0 + (i.idleSeconds.1 - i.idleSeconds.0) * i.phase
            let beat = Int((i.time / span + i.phase * 7).rounded(.down))
            pose = i.standing ? (beat % 3 == 0 ? .clap : .stand) : (beat % 2 == 0 ? .sit : .sitB)
            if let side = i.standingSideAway, side == i.away { pose = .stand }
            if i.isCard {
                let wavePhase = (i.time / max(1, i.waveSeconds)).truncatingRemainder(dividingBy: 2.5)
                if wavePhase < 1 {
                    let a = (Double(i.slice) + 0.5) / Double(max(1, i.slices))
                    let d = min(abs(a - wavePhase), 1 - abs(a - wavePhase))
                    if d < i.waveWidth { pose = .cheer } else if d < i.waveWidth * 2 { pose = .stand }
                }
            }
            if scoring == true {
                let peak = i.surgeAway == i.away
                let rate = peak ? i.surgeHz : i.surgeHz * 0.5
                let b = Int(((i.time + i.phase * 3) * rate).rounded(.down))
                pose = peak ? [.cheer, .cheer, .clap, .cheer][b % 4] : [.stand, .cheer, .clap, .stand, .cheer][b % 5]
            } else if let surge = i.surgeAway, surge == i.away {
                let b = Int(((i.time + i.phase) * i.surgeHz).rounded(.down))
                pose = [.cheer, .clap, .cheer, .stand][b % 4]
            }
        }
        // Cues win while they last, except that stand/clap never calm a celebration.
        if let cue = i.cues.max(by: { $0.rawValue < $1.rawValue }),
           !(scoring == true && !i.reduceMotion && (cue == .stand || cue == .clap)) {
            let b = Int(((i.time + i.phase * 2) * i.surgeHz).rounded(.down))
            switch cue {
            // Dismay reads from the seats: slumped, not standing with hands up.
            case .groan: pose = seated
            case .sit: pose = seated
            case .stand: pose = i.reduceMotion ? .stand : (b % 7 == 0 ? .cheer : .stand)
            case .clap: pose = i.reduceMotion ? .stand : (b % 2 == 0 ? .clap : .stand)
            }
        }
        return pose
    }

    /// Poses that read as celebrating from across the bowl.
    public static func celebrates(_ p: Pose) -> Bool { p != .sit && p != .sitB }
}
