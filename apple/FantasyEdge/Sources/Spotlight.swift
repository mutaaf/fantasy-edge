import Foundation

/// Who the room arranges itself around.
///
/// The middle of the arc used to belong to nobody in particular. Cells came
/// out of `Leverage.evaluate` sorted by share and were laid row-major over
/// five columns, so the centre of the top row went to whoever happened to
/// sort third - a position with no meaning, in the one place a wearer is
/// already looking. This decides it: the man who most recently *did
/// something* stands in the middle, and the arrangement re-forms around him.
///
/// ## Why the reaction and not the gamecast
///
/// Two signals in this app could claim to be "what just happened", and only
/// one of them is about a man on your board.
///
///   * `Board.reactions` is a diff of the live payload's per-player totals
///     across a poll. It fires when somebody *you are starting* moves by half
///     a point or more, and it carries the delta, the new total and when it
///     landed. That is exactly the question the centre is asking.
///   * `Gamecast.lastPlay` is the other one, and it is weaker in three
///     separate ways. It names a play rather than a fantasy scorer - "Maye
///     pass complete to Boutte for 9 yards" scores nobody in most leagues and
///     scores two men in a PPR one. It carries no player id, so joining it to
///     a roster row would mean matching on names out of prose. And it is per
///     event, so reading it would mean a gamecast fetch for every game on the
///     slate to learn about the one man in twelve who is yours.
///
/// So the reaction is the signal and the last play is a description of it. If
/// this ever needs to say *what* he did rather than how big it was, that is
/// the moment to join the two - and it will be a join, not a replacement.
struct Spotlight: Equatable {

    /// Why this man has the middle. Three states, and the middle of the room
    /// must not look the same in all three: a board that stands somebody in
    /// the centre before kickoff, with the same treatment it gives a man who
    /// just scored, is claiming an event that did not happen.
    enum Reason: Equatable {
        /// He scored, and this is what landed.
        case scored(Board.Reaction)
        /// Nobody has scored in this matchup yet. Every week opens here.
        case waiting
        /// Somebody did score, long enough ago that it is no longer news, so
        /// the centre has gone back to the resting rule. The reaction is kept
        /// to say what the last thing to happen was.
        case settled(Board.Reaction)
    }

    let cell: Cell
    let reason: Reason

    /// Whether this is a moment or a resting state.
    var erupting: Bool {
        if case .scored = reason { return true }
        return false
    }

    /// What the centre is claiming, in words. Here rather than in the view so
    /// the three states cannot each be phrased by a different hand.
    var headline: String {
        switch reason {
        case .scored:  return "JUST SCORED"
        case .waiting, .settled: return "MOST AT STAKE"
        }
    }

    /// The sentence under the name. A resting centre says out loud that it is
    /// resting and why it picked this man, because "he is in the middle" is
    /// otherwise indistinguishable from "he just did something".
    var caption: String {
        func points(_ v: Double) -> String {
            v.formatted(.number.precision(.fractionLength(1)))
        }
        switch reason {
        case .scored(let r):
            return "+\(points(r.delta)) just landed · now \(points(r.total))"
        case .waiting:
            return "Nothing has landed yet. The centre holds the man with the "
                 + "most of this week still riding on him."
        case .settled(let r):
            return "Nothing since \(r.name)'s +\(points(r.delta)). The centre "
                 + "holds the man with the most still riding on him."
        }
    }

    /// The rule, whole.
    ///
    /// `cells` arrives sorted by share descending out of `Leverage.evaluate`,
    /// so `first` is the man carrying the most of what is still in doubt -
    /// and that is the resting rule. Before kickoff nobody has made a play,
    /// and standing the highest-leverage man in the middle is the only
    /// arrangement that is defensible without inventing an event.
    ///
    /// `holding` is the reaction the space is currently giving the centre to,
    /// and the age check is repeated here rather than left to the timer that
    /// drives it. A headset that was asleep, or a poll that took a long time,
    /// would otherwise leave a two-minute-old touchdown standing in the middle
    /// of the room still labelled as though it had just happened.
    static func decide(cells: [Cell], recent: [Board.Reaction],
                       holding: Board.Reaction?, now: Date,
                       dwell: TimeInterval) -> Spotlight? {
        guard let top = cells.first else { return nil }
        if let r = holding, now.timeIntervalSince(r.at) < dwell,
           // He has to still be on this board. Picking another league in the
           // attention panel replaces every cell while `recent` keeps the
           // reactions from the league you left, and centring the room on
           // somebody who is not in the matchup is worse than not centring it.
           let his = cells.first(where: { $0.id == r.id }) {
            return Spotlight(cell: his, reason: .scored(r))
        }
        return Spotlight(cell: top,
                         reason: recent.first.map(Reason.settled) ?? .waiting)
    }
}
