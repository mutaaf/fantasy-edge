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

    /// What a near group shows: a pose, or one of the near-only stills around it.
    /// Each slot is a merged mesh in which every fan wears their own mix of poses
    /// (visual.crowd.nearMix), so a group changing slot changes some of its people, not all of them.
    public enum Slot: String, CaseIterable, Sendable {
        case sit, sitB = "sit_b", stand, clap = "clap_b", cheer = "cheer_a", groan
        case lookLeft = "look_l", lookRight = "look_r"
        /// A score, in stages: the quickest are half up, then the first are cheering.
        case rise1 = "rise_1", rise2 = "rise_2"

        public init(_ pose: Pose) { self = Slot(rawValue: pose.rawValue) ?? .sit }
    }

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
        /// When the current moment began (nil when none is on, or unknown).
        public var momentStarted: Double?
        /// This group's ripple: seconds after the moment begins before it moves, larger farther from the play.
        public var delay: Double
        /// Seconds each stage of a near group's rise holds.
        public var riseStageSeconds: Double
        /// Where the play is, across this group: +1 to the fans' left, -1 to their right, 0 in front.
        public var look: Int

        public init(away: Bool, isCard: Bool = false, phase: Double = 0, standing: Bool = false, slice: Int = 0, slices: Int = 12,
                    time: Double = 0, reduceMotion: Bool = false, tintSide: String? = nil, lastScoringAway: Bool? = nil,
                    lastScoringEnded: Double = 0, settleSeconds: (Double, Double) = (2.5, 5), surgeAway: Bool? = nil,
                    standingSideAway: Bool? = nil, idleSeconds: (Double, Double) = (2.5, 6.5), waveSeconds: Double = 16,
                    waveWidth: Double = 0.045, surgeHz: Double = 1.6, cues: [CueKind] = [],
                    momentStarted: Double? = nil, delay: Double = 0, riseStageSeconds: Double = 0.35, look: Int = 0) {
            self.away = away; self.isCard = isCard; self.phase = phase; self.standing = standing; self.slice = slice
            self.slices = slices; self.time = time; self.reduceMotion = reduceMotion; self.tintSide = tintSide
            self.lastScoringAway = lastScoringAway; self.lastScoringEnded = lastScoringEnded; self.settleSeconds = settleSeconds
            self.surgeAway = surgeAway; self.standingSideAway = standingSideAway; self.idleSeconds = idleSeconds
            self.waveSeconds = waveSeconds; self.waveWidth = waveWidth; self.surgeHz = surgeHz; self.cues = cues
            self.momentStarted = momentStarted; self.delay = delay; self.riseStageSeconds = riseStageSeconds; self.look = look
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

    /// Seconds into this group's own reaction to the moment, or nil when none is running.
    static func intoMoment(_ i: Input) -> Double? {
        guard let start = i.momentStarted, i.tintSide == "home" || i.tintSide == "away" else { return nil }
        return i.time - start - i.delay
    }

    public static func pose(_ i: Input) -> Pose {
        let scoring = Self.scoring(i)
        let seated: Pose = i.phase < 0.5 ? .sit : .sitB
        // Scored on: in the seats, whatever else is asking. Not negotiable by cues.
        if scoring == false { return seated }
        // The ripple: until the reaction reaches this group it is still watching the play.
        if scoring == true, !i.reduceMotion, let e = intoMoment(i), e < 0 { return seated }
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

    /// A near group's slot: the pose, staged on the way up and turned toward the play while seated.
    public static func slot(_ i: Input) -> Slot {
        let p = pose(i)
        if Self.scoring(i) == true, !i.reduceMotion, let e = intoMoment(i), e >= 0 {
            if e < i.riseStageSeconds { return .rise1 }
            if e < 2 * i.riseStageSeconds { return .rise2 }
        }
        // Heads follow the play; `sit_b` stays as it is, so a turn never moves every fan at once.
        if p == .sit, !i.reduceMotion, i.look != 0 { return i.look > 0 ? .lookLeft : .lookRight }
        return Slot(p)
    }

    /// Slots that read as celebrating (rise_2 has some fans cheering).
    public static func celebrates(_ s: Slot) -> Bool {
        switch s {
        case .sit, .sitB, .lookLeft, .lookRight, .rise1: return false
        default: return true
        }
    }

    /// Poses that read as celebrating from across the bowl.
    public static func celebrates(_ p: Pose) -> Bool { p != .sit && p != .sitB }
}
