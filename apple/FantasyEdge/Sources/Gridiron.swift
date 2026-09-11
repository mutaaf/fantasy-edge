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
