import CoreGraphics
import Foundation

/// Where a man is standing on a field, and why.
///
/// Arithmetic over the live payload with no SwiftUI in it, so the rule that
/// decides "on the field or on the bench" can be exercised on its own -
/// `apple/verify_placement.swift` replays a finished game's drives through
/// exactly this code. Worth the separation because the rule is not symmetric:
/// a defence earns its points on the snaps its club is *not* attacking on, so
/// the obvious one-liner benches every D/ST that is actually playing and
/// walks every one that is watching onto the field.
enum Gridiron {

    /// Where the layout puts a man. The difference between these four is a
    /// fact about his game, not a styling choice - which is the whole point
    /// of the view: a man on the bench here cannot score for you right now.
    enum Station: String, Hashable, CaseIterable {
        case field      // his club can score him points on the next snap
        case bench      // his game is running, but the wrong side has the ball
        case sideline   // not kicked off, or nobody has the ball yet
        case done       // finished
    }

    /// The half of one club's live entry that decides any of this.
    struct Situation: Hashable {
        var pos: String
        var state: String        // "pre" | "in" | "post"
        /// True when his club has the ball, false when the other one does,
        /// nil when nobody does - before a kickoff, or after the whistle.
        var attacking: Bool?
        /// Yards from the ball to the end zone the attacking club is driving
        /// on, 0...100. Served rather than derived from a yard line, whose
        /// direction is ambiguous without knowing which way the club is going.
        var toEndzone: Int?
    }

    /// A place in field coordinates: `x` runs 0 at the attacking side's own
    /// goal line to 1 at the end zone it is driving on, `y` 0 to 1 across the
    /// width. `x` is nil when a man is on the field but the feed gave no ball
    /// spot - he is out there, we simply cannot say where, and putting him on
    /// the fifty would be a drawing of a number nobody reported.
    struct Spot: Hashable {
        var station: Station
        var x: Double?
        var y: Double
    }

    /// ESPN calls it DEF, other feeds D/ST. Both are the unit that scores when
    /// its club is defending.
    static func isDefence(_ pos: String) -> Bool {
        let p = pos.uppercased()
        return p == "DEF" || p == "DST" || p == "D/ST" || p == "DEFENSE"
    }

    /// The whole rule, in one place so there is one of it.
    static func station(_ s: Situation) -> Station {
        switch s.state {
        case "post": return .done
        case "in":
            // No situation in the feed means nobody has the ball: a kickoff,
            // a timeout, the gap between possessions. Saying "he is on the
            // field" there would be a claim the feed has not made.
            guard let attacking = s.attacking else { return .sideline }
            // The inversion a defence needs, written out rather than hidden
            // in a `!=`, because it is the one line in this file that is easy
            // to get backwards and expensive when you do.
            return attacking == !isDefence(s.pos) ? .field : .bench
        default: return .sideline
        }
    }

    /// Yards behind (negative) or beyond (positive) the line of scrimmage a
    /// position lines up at. A rough alignment and not a play call - nothing
    /// in this feed says where a man actually stood. What it has to get right
    /// is which side of the ball he is on.
    static func depth(_ pos: String) -> Double {
        switch pos.uppercased() {
        case "QB": return -7        // shotgun
        case "RB": return -7        // beside him
        case "K":  return -8        // the holder's spot
        case "TE": return 0         // inline
        case "WR": return 0         // on the line, split wide
        default:   return 6         // a defence, six yards the other side
        }
    }

    /// The lanes across the field a position can take, in preference order.
    /// Handed out by index rather than at random for two reasons: a man keeps
    /// his lane between polls instead of jumping, and two receivers from two
    /// different games do not land on top of each other at the same yardline.
    static func lanes(_ pos: String) -> [Double] {
        switch pos.uppercased() {
        case "QB": return [0.50, 0.43, 0.57]
        case "RB": return [0.63, 0.37, 0.70, 0.30]
        case "WR": return [0.07, 0.93, 0.17, 0.83]
        case "TE": return [0.29, 0.71, 0.23, 0.77]
        case "K":  return [0.16, 0.84]
        default:   return [0.50, 0.33, 0.67, 0.22, 0.78]
        }
    }

    static func place(_ s: Situation, index: Int = 0) -> Spot {
        let st = station(s)
        let ls = lanes(s.pos)
        let y = ls[((index % ls.count) + ls.count) % ls.count]
        guard st == .field, let tz = s.toEndzone else {
            return Spot(station: st, x: nil, y: y)
        }
        let x = alongField(tz) + depth(s.pos) / 100.0
        return Spot(station: st, x: min(0.995, max(0.005, x)), y: y)
    }

    /// A yards-to-the-end-zone reading as the same 0-to-1 the tokens use.
    ///
    /// Every offence on these fields attacks left to right, whichever club it
    /// is and whichever way it is actually facing in its stadium. That one
    /// convention is what lets men from four different games stand on one
    /// field and still be somewhere meaningful relative to each other.
    static func alongField(_ toEndzone: Int) -> Double {
        (100.0 - Double(min(100, max(0, toEndzone)))) / 100.0
    }

    /// Whether a play is a snap that moved the ball.
    ///
    /// It is not enough to test the down. In the SF-at-LAR feed a timeout
    /// comes through as `down 3, distance 1, from 0, to 48` and the two-minute
    /// warning as `down 1, distance 10, from 0, to 80`: the down is the one
    /// that was about to be played, and `from` is zero because no ball was
    /// snapped. END GAME is the same shape with `down 0, from 0, to 13`. Read
    /// straight into geometry those put the line of scrimmage on the goal line
    /// and draw a gain line most of the length of the field - which is the
    /// stray red line on the screenshot this was written from.
    ///
    /// `from` is yards to the defending end zone, so a real snap is always at
    /// least 1: a snap from the zero yard line is a play that has already
    /// scored. Kickoffs carry `down 0` with a genuine `from`, and they are
    /// excluded too - there is no line of scrimmage on a kickoff and no down
    /// to report.
    static func isSnap(down: Int?, from: Int?) -> Bool {
        (down ?? 0) > 0 && (from ?? 0) > 0
    }

    /// The three marks a play puts on the field, in field coordinates.
    ///
    /// One function so the drawing and `verify_placement.swift` cannot get
    /// different answers, which is the whole reason the arithmetic is out here
    /// rather than inside a `GeometryReader`.
    struct Marks: Hashable {
        /// Where the ball was snapped from.
        let los: Double
        /// The line to gain. Nil on a play with no down to gain against.
        let toGain: Double?
        /// Where the whistle went. Equal to `los` when the feed gave no `to`.
        let ball: Double
    }

    static func marks(from: Int, to: Int?, down: Int?, distance: Int?) -> Marks {
        Marks(los: alongField(from),
              // Clamped at the goal line: on 3rd and 12 from the eight, the
              // line to gain is the end zone, not four yards behind it.
              toGain: ((down ?? 0) > 0 && (distance ?? 0) > 0)
                  ? alongField(max(0, from - (distance ?? 0))) : nil,
              ball: alongField(to ?? from))
    }

    /// "LAR 28", the way a scoreboard says it. Yards-to-the-end-zone is the
    /// exact number and nobody reads a game in it.
    static func spot(toEndzone: Int, offence: String, defence: String) -> String {
        if toEndzone == 50 { return "50" }
        if toEndzone > 50 { return "\(offence) \(100 - toEndzone)" }
        return "\(defence) \(toEndzone)"
    }

    /// "3rd & 7". Nil when there is no down to report, which is a real state:
    /// kickoffs and extra points come through carrying down 0 or -1.
    static func down(_ down: Int?, _ distance: Int?, toEndzone: Int? = nil) -> String? {
        guard let d = down, d > 0 else { return nil }
        let name = ["", "1st", "2nd", "3rd", "4th"]
        let label = d < name.count ? name[d] : "\(d)th"
        guard let dist = distance else { return label }
        if let tz = toEndzone, tz > 0, dist >= tz { return "\(label) & Goal" }
        return dist <= 0 ? "\(label) & inches" : "\(label) & \(dist)"
    }
}

/// A hundred yards between two ten-yard end zones, which is why every
/// conversion here divides by a hundred and twenty.
///
/// Here rather than beside the turf that draws it so the mapping can be
/// checked without a renderer: `verify_placement.swift` asserts that a snap
/// from the 63 with three to gain puts the line of scrimmage at 470, the line
/// to gain at 500 and the ball at 550 in a twelve-hundred-unit box. Checking
/// a field by eye is how a stray line survives a review.
enum FieldGeometry {
    static let endzone = 10.0 / 120.0

    /// Field coordinate (0 at the attacking side's own goal line, 1 at the
    /// end zone it is driving on) to a point across a view of this width.
    static func px(_ x: Double, _ width: CGFloat) -> CGFloat {
        CGFloat(endzone + max(0, min(1, x)) * (1 - 2 * endzone)) * width
    }

    /// The last twenty yards, stretched over the whole width.
    ///
    /// A rescale of the same coordinate rather than a second placement rule:
    /// the red-zone field draws men `Gridiron.place` has already positioned,
    /// so one arrangement is shown at two zooms instead of two arrangements
    /// having to agree. Clamped at the bottom because a man lines up behind
    /// the ball - a quarterback in shotgun on the eighteen is seven yards
    /// further back than the ball is, and off the left edge of this view.
    static func redZone(_ x: Double) -> Double {
        min(1, max(0, (x - 0.80) / 0.20))
    }
}

/// One of your men, placed. Flattened out of the roster and the live payload
/// so a view can draw him without reaching back into either, and so the whole
/// arrangement can be memoised as one value.
struct FieldMan: Identifiable, Hashable {
    let id: String, name: String, pos: String, team: String
    let img: String?, logo: String?
    let spot: Gridiron.Spot
    /// His club's game, as the live tier reports it.
    let opp: String, home: Bool, event: String
    let state: String, label: String, kickoff: String
    let score: String, oppScore: String
    let attacking: Bool?
    let down: Int?, distance: Int?, toEndzone: Int?, redZone: Bool
    /// What he has scored for you so far, and in how many of your line-ups he
    /// is starting. Both are facts about your leagues, not about the game.
    let points: Double, lineups: Int

    var station: Gridiron.Station { spot.station }
    var defence: Bool { Gridiron.isDefence(pos) }
    var fixture: String { (home ? "vs " : "@ ") + opp }

    /// Said in words, because the position on the field is the claim and the
    /// reader deserves to see what it rests on.
    var why: String {
        switch station {
        case .field:
            return defence ? "\(opp) have the ball" : "\(team) have the ball"
        case .bench:
            return defence ? "\(team) have the ball - a defence cannot score on its own offence"
                           : "\(opp) have the ball"
        case .sideline:
            return state == "in" ? "between possessions" : "kickoff \(kickoffTime)"
        case .done:
            return "final, \(score)-\(oppScore) \(fixture)"
        }
    }

    /// "1:00 PM" out of the "2026-09-13T17:00" the slate carries. The feed
    /// gives kickoff in UTC with no zone marker, so it is parsed as UTC and
    /// shown in the reader's own time - the alternative is a headset in
    /// California telling you the game starts at five.
    var kickoffTime: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm"
        f.timeZone = TimeZone(identifier: "UTC")
        guard let d = f.date(from: kickoff) else { return kickoff }
        return d.formatted(.dateTime.weekday(.abbreviated).hour().minute())
    }
}

extension FieldMan {
    /// The same man, stood somewhere else.
    ///
    /// The live board places everyone from the shared snapshot, which is the
    /// only ball position it has. A single game knows more: the play on screen
    /// carries its own line of scrimmage, and walking back through a finished
    /// game means asking where a man stood *then* rather than where the feed
    /// says he is now. Rebuilt rather than mutated because `spot` is the one
    /// thing about him that is a derivation, and a var would invite a second
    /// place that decides it.
    func standing(_ spot: Gridiron.Spot) -> FieldMan {
        FieldMan(id: id, name: name, pos: pos, team: team, img: img, logo: logo,
                 spot: spot, opp: opp, home: home, event: event, state: state,
                 label: label, kickoff: kickoff, score: score,
                 oppScore: oppScore, attacking: attacking, down: down,
                 distance: distance, toEndzone: toEndzone, redZone: redZone,
                 points: points, lineups: lineups)
    }
}
