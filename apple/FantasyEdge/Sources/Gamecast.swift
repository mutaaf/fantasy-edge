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
