import Foundation

/// Which fans a cue is for: a whole side, or named sections (`bowl.seating`
/// section ids such as "112" or "305").
public enum CrowdTarget: Equatable, Sendable {
    case side(String)            // "home" or "away"
    case sections([String])
}

/// What the crowd is asked to do, and until when on the frame clock.
struct CrowdCue: Equatable {
    enum Kind: Int { case sit = 0, stand = 1, clap = 2, groan = 3 }   // later kinds win a tie
    let kind: Kind
    let target: CrowdTarget
    let until: Double
}

/// The crowd's hooks on the blackboard, for Moments and any cue to call:
///
///     c.shared.stand(.side("home"), until: now + 6)              // red zone: the home crowd rises
///     c.shared.stand(.side("home"), until: now + 8, clap: true)  // third down on defence
///     c.shared.groan("away", until: now + 3.5)                   // a turnover: the losing side
///     c.shared.stand(.sections(["112", "113"]), until: .infinity)// the final: the winners stay up
///     c.shared.sit(.side("away"), until: now + 10)
///
/// Cues live on the blackboard as `shared.crowdCues`, so they end with the
/// stadium that set them; Crowd reads them every frame. A cue overrides idle
/// motion and the scoring celebration while it lasts; reduce motion turns
/// every cue into a still pose.
@MainActor
enum CrowdCues {
    static func add(_ cue: CrowdCue, to shared: StadiumShared) {
        shared.crowdCues.removeAll { $0.target == cue.target && $0.kind == cue.kind }
        shared.crowdCues.append(cue)
    }

    /// The live cues, expired ones dropped.
    static func live(_ shared: StadiumShared, at time: Double) -> [CrowdCue] {
        shared.crowdCues.removeAll { $0.until <= time }
        return shared.crowdCues
    }

    static func clear(_ shared: StadiumShared) { shared.crowdCues = [] }
}

extension StadiumShared {
    /// The target gets to its feet; `clap` keeps its hands going.
    func stand(_ target: CrowdTarget, until: Double, clap: Bool = false) {
        CrowdCues.add(CrowdCue(kind: clap ? .clap : .stand, target: target, until: until), to: self)
    }

    /// The target sits back down (and stays down) until then.
    func sit(_ target: CrowdTarget, until: Double) {
        CrowdCues.add(CrowdCue(kind: .sit, target: target, until: until), to: self)
    }

    /// Hands on heads: a side watching its team give the ball away.
    func groan(_ side: String, until: Double) {
        CrowdCues.add(CrowdCue(kind: .groan, target: .side(side), until: until), to: self)
    }
}
