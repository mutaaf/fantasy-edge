import Foundation

/// Mirrors the JSON the credential-free read API already serves. Nothing here
/// is Vision-specific: the same shapes drive the web board.
struct Starter: Decodable {
    let id: String, name: String, pos: String, team: String
    let slot: String?, projected: Double?
    let color: String?, img: String?, logo: String?
}
struct Side: Decodable { let teamId: String; let name: String; let starters: [Starter] }
struct LeaguePayload: Decodable {
    let id: String, provider: String, leagueId: String, league: String
    let season: Int, week: Int
    let you: Side, opp: Side?
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
             remaining: live?.r ?? 1, state: live?.g ?? "PRE")
    }
}
