import Foundation

/// When a moment is allowed to happen.
///
/// The scene announces a touchdown the instant the play arrives, but Broadcast
/// flies that play over about five seconds. Fired on arrival, the banner, the
/// score flash, the strobe, the fireworks and the section's surge all landed
/// while the ball was still in the air - integration-12 measured the banner
/// 5.1 s early, and gone before the return finished.
///
/// So the composer holds the moment until Broadcast says that play has landed,
/// and every consumer downstream starts counting from there. `landed` is
/// `BroadcastActor.hasTrail`, which turns true exactly when a play's trail is
/// laid: at the end of its flight, or at once for a drive laid down at rest -
/// a scrub, a seat change, or reduce motion, where nothing ever flies.
///
/// Nothing may wait forever. A scene from before play paths, a moment whose
/// play is not in the drive at all, or a flight cut short leaves the gate
/// holding something that will never land, so every hold carries a deadline of
/// the play's own flight plus `motion.momentHoldGraceSeconds`. The deadline is
/// a safety net, not the mechanism: a play that lands early (a fast replay
/// divides its duration) fires on landing, not on the clock.
///
/// Pure logic, no RealityKit: `apple/verify_moment.swift` sweeps it.
public struct MomentGate: Sendable {
    /// Used when the scene carries no `motion.momentHoldGraceSeconds`.
    public static let defaultGraceSeconds = 1.0

    /// A moment waiting for its play, and the time it gives up waiting.
    public struct Held: Equatable, Sendable {
        public let playId: String
        public let deadline: Double
    }

    public private(set) var held: Held?
    /// The last moment the gate accepted, fired or still waiting. A scene
    /// re-announcing the same moment every poll must not queue it twice.
    public private(set) var taken: String?

    public init() {}

    /// A moment arrived. Returns true if it fires now, false if it is held.
    ///
    /// `flightSeconds` is how long its play animates; pass 0 when the drive
    /// holds no such play, so only the grace is waited out.
    public mutating func arrive(playId: String, flightSeconds: Double, now: Double,
                                grace: Double, landed: Bool) -> Bool {
        guard playId != taken else { return false }
        taken = playId
        if landed {
            held = nil
            return true
        }
        held = Held(playId: playId, deadline: now + max(0, flightSeconds) + max(0, grace))
        return false
    }

    /// On the frame clock: the moment to fire now, if the play has landed or
    /// the hold has run out. Returns it once and forgets it.
    public mutating func due(now: Double, landed: (String) -> Bool) -> String? {
        guard let h = held else { return nil }
        guard landed(h.playId) || now >= h.deadline else { return nil }
        held = nil
        return h.playId
    }

    /// The scene no longer has a moment - scrubbed away, or a new game. A held
    /// moment is dropped rather than fired late over a play nobody is watching.
    public mutating func clear() {
        held = nil
        taken = nil
    }

    /// Whether this moment is the one currently waiting.
    public func isHolding(_ playId: String) -> Bool { held?.playId == playId }

    /// Take a moment as already dealt with, without firing it: the stadium was
    /// just built for a different game, and whatever the first scene happens to
    /// carry is history, not something to celebrate on arrival.
    public mutating func suppress(_ playId: String?) {
        held = nil
        taken = playId
    }
}

/// What the stadium is allowed to say the score is.
///
/// The same mismatch as `MomentGate`, one layer down. A scene arrives carrying
/// the state *after* its newest play - the score, the down and distance, the
/// red-zone flag - and Broadcast then flies that play for seconds. Drawn on
/// arrival, the board read CHI 17 with the return still running
/// (integration-13), and the down turned over before the ball got there.
///
/// So the drawn status lags the scene by exactly one play: the composer holds
/// the arriving status until Broadcast says that play has landed, and only then
/// does the ribbon, the video board, the scorebug and the crowd see it. What is
/// shown is never wrong for what has been watched.
///
/// Generic over the status so the rule stays pure logic with no scene type
/// behind it: `apple/verify_moment.swift` sweeps it with an `Int`.
public struct StatusGate<Status>: Sendable where Status: Sendable & Equatable {
    /// What the stadium draws. Nil only before the first scene.
    public private(set) var shown: Status?
    /// Waiting behind a play, with the time it gives up waiting.
    private var pending: (status: Status, playId: String, deadline: Double)?

    public init() {}

    public var isHolding: Bool { pending != nil }
    /// The play the drawn status is waiting on, for logs.
    public var waitingOn: String? { pending?.playId }

    /// Show this status now: the first scene, a scrub, a seat change, a new
    /// game - anywhere there is no flight between what was drawn and what is
    /// true.
    public mutating func adopt(_ status: Status) {
        shown = status
        pending = nil
    }

    /// A new play arrived with this status. It is held until that play lands;
    /// `deadline` is the frame clock at which it is shown regardless, so a
    /// play that never flies can never freeze the board.
    ///
    /// Nothing is held before the first scene: there is no earlier state to
    /// keep showing, and a blank board is worse than an early score.
    public mutating func hold(_ status: Status, playId: String, until deadline: Double) {
        guard shown != nil else { return adopt(status) }
        pending = (status, playId, deadline)
    }

    /// A scene arrived carrying no new play: the clock ticked, a timeout, a
    /// stoppage. It replaces whatever is waiting, or is shown at once.
    public mutating func arrive(_ status: Status) {
        if var p = pending {
            p.status = status
            pending = p
        } else {
            shown = status
        }
    }

    /// On the frame clock: the status to draw now, if its play has landed or
    /// the hold has run out. Returns it once, when it changes what is drawn.
    public mutating func due(now: Double, landed: (String) -> Bool) -> Status? {
        guard let p = pending else { return nil }
        guard landed(p.playId) || now >= p.deadline else { return nil }
        pending = nil
        guard p.status != shown else { return nil }
        shown = p.status
        return p.status
    }
}
