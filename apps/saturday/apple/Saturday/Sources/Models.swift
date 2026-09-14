import Foundation

// Decodable mirrors of contracts/*.schema.json. Nothing here computes: every
// flag, section, chip colour and ordering arrives decided by the API, so this
// app, the web port and the Android port cannot drift apart.

struct Slate: Decodable {
    let version: Int
    let league: String
    let asOf: String
    let source: String
    let replay: Bool
    let counts: Counts
    let spotlight: String?
    let sections: [WallSection]
    let leverageCaveat: String
    let games: [Game]

    struct Counts: Decodable, Hashable {
        let live: Int, pre: Int, post: Int, delayed: Int
    }
}

struct WallSection: Decodable, Identifiable, Hashable {
    let id: String
    let title: String
    let overline: String
    let games: [String]
}

struct Game: Decodable, Identifiable, Hashable {
    let id: String
    let kickoff: String
    let status: GameStatus
    let away: Side
    let home: Side
    let situation: Situation?
    let tv: String?
    let venue: Venue
    let flags: Flags
    let leverage: Leverage

    func side(id teamID: String?) -> Side? {
        guard let teamID else { return nil }
        return away.id == teamID ? away : home.id == teamID ? home : nil
    }
}

struct GameStatus: Decodable, Hashable {
    let state: String          // pre | in | post
    let name: String
    let detail: String
    let period: Int
    let clock: String
    let completed: Bool
    let delayed: Bool
    let overtimes: Int
    let halftime: Bool
}

struct Side: Decodable, Hashable {
    let id: String
    let abbr: String
    let name: String
    let location: String
    let color: String
    let logo: String
    let rank: Int?
    let record: String
    let score: Int?
    let fill: String
    let hatch: Bool
}

struct Situation: Decodable, Hashable {
    let possession: String?
    let down: Int?
    let distance: Int?
    let text: String?
    let yardsToGoal: Int?
    let redZone: Bool
}

struct Venue: Decodable, Hashable {
    let name: String, city: String, state: String
}

struct Flags: Decodable, Hashable {
    let live: Bool, redZone: Bool, overtime: Bool, delayed: Bool
    let upset: Bool, upsetAlert: Bool, oneScore: Bool, ranked: Bool
}

struct Leverage: Decodable, Hashable {
    let score: Double
    let reasons: [String]
    let rank: Int
}

// MARK: - game detail (GET /api/game/{id})

struct GameDetail: Decodable {
    let event: String
    let replay: Bool
    let status: GameStatus
    let home: DetailTeam
    let away: DetailTeam
    let possession: String?
    let lastPlay: Play?
    let drives: [Drive]
    let winProbability: [WinPoint]
    let winProbabilityCaveat: String
    let scoringPlays: [ScoringPlay]
    let boxscore: [TeamBox]
    let leaders: [Leader]
    let venue: String?
}

struct DetailTeam: Decodable, Hashable {
    let id: String
    let abbr: String
    let name: String
    let location: String
    let rank: Int?
    let record: String
    let score: Int?
    let linescores: [Int]
    let fill: String?
    let hatch: Bool?
}

struct Play: Decodable, Identifiable, Hashable {
    let id: String
    let text: String
    let type: String
    let clock: String
    let period: Int
    let downText: String?
    let from: Int?
    let to: Int?
    let yards: Int?
    let scoring: Bool
    let turnover: Bool
    let penalty: Bool
}

struct Drive: Decodable, Hashable {
    let id: String
    let team: String
    let description: String
    let result: String
    let scored: Bool
    let turnover: Bool
    let current: Bool
    let plays: [Play]
}

struct WinPoint: Decodable, Hashable {
    let play: String
    let home: Double
}

struct ScoringPlay: Decodable, Hashable {
    let text: String, clock: String, team: String
    let period: Int, home: Int, away: Int
}

struct TeamBox: Decodable, Hashable {
    let team: String
    let stats: [Stat]
    struct Stat: Decodable, Hashable { let label: String, value: String }
}

struct Leader: Decodable, Hashable {
    let team: String, category: String, name: String
    let labels: [String], stats: [String]

    var line: String {
        let pairs = Dictionary(zip(labels, stats), uniquingKeysWith: { a, _ in a })
        switch category {
        case "passing": return "\(pairs["C/ATT"] ?? "–"), \(pairs["YDS"] ?? "0") yds"
        case "rushing": return "\(pairs["CAR"] ?? "0") car, \(pairs["YDS"] ?? "0") yds"
        case "receiving": return "\(pairs["REC"] ?? "0") rec, \(pairs["YDS"] ?? "0") yds"
        default: return stats.prefix(2).joined(separator: " · ")
        }
    }
}
