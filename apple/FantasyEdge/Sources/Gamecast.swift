import Foundation

/// One game, in the shape a field wants to draw it. Mirrors
/// `GET /api/gamecast/{event}`, which does the flattening server-side on
/// purpose: a field is the same field on a television, a headset and a
/// browser, and three implementations of "where is the ball" would be three
/// chances to put it somewhere different.
struct Gamecast: Decodable {
    let event: String
    let state: String           // "pre" | "in" | "post"
    let label: String
    let clock: String?
    let period: Int?
    let home: GameSide
    let away: GameSide
    /// Club id, not abbreviation - matched against `GameSide.id`.
    let possession: String?
    let lastPlay: GamePlay?
    /// Everyone this game scored a fantasy line for, whether or not anybody
    /// rosters them - see `GamePlayer`. Defaulted rather than required so a
    /// headset talking to an older API still draws its field.
    var players: [GamePlayer] = []
    let drives: [Drive]
    /// Already one point per play, from the feed. Not modelled here: a win
    /// probability this app invented would look exactly like one ESPN
    /// published, which is the reason not to.
    let winProbability: [WinProbPoint]
    let scoringPlays: [ScoringPlay]

    /// Newest first, which is the order a feed is read in.
    var playsNewestFirst: [(drive: Drive, play: GamePlay)] {
        drives.reversed().flatMap { d in d.plays.reversed().map { (d, $0) } }
    }
    var clockLine: String {
        let p = period.map { $0 > 4 ? "OT" : "Q\($0)" } ?? ""
        let c = clock ?? ""
        return state == "post" ? "FINAL" : [p, c].filter { !$0.isEmpty }.joined(separator: " ")
    }
}

struct GameSide: Decodable, Hashable {
    let id: String?, abbr: String?, name: String?
    let logo: String?, color: String?
    let score: Double?
    var mark: String { abbr ?? "" }
    var points: Int { Int(score ?? 0) }
}

struct Drive: Decodable, Identifiable, Hashable {
    let id: String
    /// The club with the ball for this drive - which is what makes every
    /// play in it placeable, since `from` and `to` are measured towards the
    /// end zone *this* club is attacking.
    let team: String
    let description: String
    let result: String
    let scored: Bool
    let yards: Int?
    let plays: [GamePlay]
}

struct GamePlay: Decodable, Identifiable, Hashable {
    let id: String
    let text: String
    let clock: String
    let period: Int?
    let down: Int?
    let distance: Int?
    /// Yards to the defending end zone at the snap and when the whistle went.
    let from: Int?
    let to: Int?
    let yards: Int?
    let scoring: Bool
    let turnover: Bool
    let penalty: Bool
    let home: Double?
    let away: Double?
}

/// One athlete's line in this game, from the box score the scoring already
/// parsed. Twenty-odd men score a fantasy line in a game and a four-league
/// board names a dozen of them; this is the other two-thirds.
///
/// `pos` and `role` are different claims and the view must not blur them.
/// `pos` is a position somebody told us - ESPN's leaders block, or a player
/// row - and is empty when nobody did. `role` is what the stat line says he
/// did, which a box score can always answer because it groups by exactly
/// that. So a man reads "WR" when his position is known and "REC" when only
/// his line is, and the two vocabularies do not overlap by design.
struct GamePlayer: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let team: String
    let jersey: String?
    let img: String?
    /// A position, from a source that knew one. Empty otherwise.
    let pos: String
    /// Which source. "espn" or "roster".
    let posFrom: String
    /// PASS / RUSH / REC / KICK / RET, read off the line.
    let role: String
    /// Whether that role is one a fantasy line-up starts.
    let skill: Bool
    /// The line itself, already rendered: "8 REC, 122 YDS, 1 TD, 11 TGTS".
    let line: String
    let points: Double

    /// What to show where a position goes. Never invents one.
    var badge: String { pos.isEmpty ? role : pos }

    /// Does this man answer a position chip? On `pos` where there is one; on
    /// the role the line implies where there is not, which can put a tight
    /// end under WR - hence a fallback rather than the rule.
    func matches(_ want: String) -> Bool {
        if want.isEmpty { return true }
        if !pos.isEmpty { return pos == want }
        switch role {
        case "PASS": return want == "QB"
        case "RUSH": return want == "RB"
        case "REC":  return want == "WR" || want == "TE"
        case "KICK": return want == "K"
        default:     return false
        }
    }
}

struct WinProbPoint: Decodable, Hashable {
    let play: String
    /// The home club's chance of winning, 0...1.
    let home: Double?
}

/// The win-probability series, flattened to what a chart draws: the values,
/// the play each one belongs to, and which of those plays scored.
struct WinProbSeries: Hashable {
    let home: [Double]
    let plays: [String]
    let scoring: [Int]
    var last: Double? { home.last }
}

struct ScoringPlay: Decodable, Hashable, Identifiable {
    let text: String, clock: String, team: String
    let period: Int?
    let home: Double?, away: Double?
    var id: String { "\(team)-\(period ?? 0)-\(clock)-\(text.prefix(24))" }
}
