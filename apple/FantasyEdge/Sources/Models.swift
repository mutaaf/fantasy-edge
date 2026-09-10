import Foundation

/// Mirrors the JSON the credential-free read API already serves. Nothing here
/// is Vision-specific: the same shapes drive the web board.
struct Starter: Decodable {
    let id: String, name: String, pos: String, team: String
    let slot: String?, projected: Double?
    let color: String?, img: String?, logo: String?
}
struct Side: Decodable { let teamId: String; let name: String; let starters: [Starter] }

/// One manager in a league, for the picker. The board has always carried these
/// in its payload; nothing on this side could read them, so the headset had no
/// way to say which team was yours.
struct TeamRef: Decodable, Identifiable, Hashable {
    let teamId: String, name: String
    var id: String { teamId }
    var display: String { name.trimmingCharacters(in: .whitespacesAndNewlines) }
}

struct LeaguePayload: Decodable {
    let id: String, provider: String, leagueId: String, league: String
    let season: Int, week: Int
    let you: Side, opp: Side?
    let teams: [TeamRef]?
}
struct MosaicsPayload: Decodable { let leagues: [LeaguePayload] }

struct LiveState: Decodable { let s: Double; let r: Double; let g: String }
struct GameState: Decodable {
    let played: Double?; let state: String?; let label: String?
    let kickoff: String?; let score: String?
}
struct LivePayload: Decodable {
    let source: String?
    let games: [String: GameState]?
    let players: [String: LiveState]
    let version: String?
}

extension Cell {
    /// One place where a starter plus its live line becomes a cell, so the
    /// window and the immersive space cannot drift apart.
    static func make(_ s: Starter, side: String, live: LiveState?) -> Cell {
        Cell(id: s.id, name: s.name, pos: s.pos, team: s.team, side: side,
             scored: live?.s ?? 0, projected: s.projected ?? 0,
             remaining: live?.r ?? 1, state: live?.g ?? "PRE",
             img: s.img ?? "")
    }
}


// MARK: - the deep profile behind a card

struct SeasonRow: Decodable, Identifiable {
    let season: Int, weeks: Int
    let total: Double, ppg: Double, best: Double
    let rank: Int?, field: Int
    let started: Bool
    var id: Int { season }
}
struct DraftRow: Decodable, Identifiable {
    let season: Int, league: String?, teams: Int?, team: String?
    let round: Int?, overall: Int?, adp: Double?, reach: Double?
    var id: String { "\(season)-\(league ?? "")-\(overall ?? 0)" }
}
struct FormatRow: Decodable, Identifiable {
    let name: String, points: Double
    var id: String { name }
}
struct Profile: Decodable {
    let id: String, name: String, pos: String, team: String
    let img: String?, logo: String?
    let seasons: [SeasonRow]
    let draft: [DraftRow]
    let formats: [FormatRow]
}
