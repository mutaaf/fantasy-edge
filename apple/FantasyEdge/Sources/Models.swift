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
    let record: Record?
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
    /// Points week by week. The only series on the card that can support a
    /// floor and a ceiling, because it is the only one with a distribution.
    let weekly: [Double]?
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
    let recentRanks: [RankRow]?
    let career: Career?
    let opportunity: Opportunity?
}


// MARK: - the command centre's other panels
//
// Everything below is already served by the read API and was simply never
// asked for by this app. Nothing here is invented for the layout: a field
// that has no source does not appear, because a dashboard that fills a gap
// with a plausible number is worse than one with a gap in it.

struct Record: Decodable, Hashable {
    let wins: Int?, losses: Int?, ties: Int?
    let rank: Int?, of: Int?
    let pointsFor: Double?

    var line: String {
        guard let w = wins, let l = losses else { return "" }
        let t = (ties ?? 0) > 0 ? "-\(ties!)" : ""
        return "\(w)-\(l)\(t)"
    }
    var place: String {
        guard let r = rank, let n = of else { return "" }
        return "\(ordinal(r)) of \(n)"
    }
    private func ordinal(_ n: Int) -> String {
        switch (n % 100, n % 10) {
        case (11...13, _): return "\(n)th"
        case (_, 1): return "\(n)st"
        case (_, 2): return "\(n)nd"
        case (_, 3): return "\(n)rd"
        default: return "\(n)th"
        }
    }
}

/// One league a player is rostered in, from `/api/players`.
struct Ownership: Decodable, Hashable {
    let league: String?, id: String?, team: String?
    let slot: String?, started: Bool?
}

/// A player you roster somewhere, collapsed across leagues.
struct RosteredPlayer: Decodable, Identifiable, Hashable {
    let id: String, name: String, pos: String, team: String
    let color: String?, img: String?, logo: String?
    let projected: Double?
    let leagues: [Ownership]?

    var exposure: Int { leagues?.count ?? 0 }
    var startedIn: Int { (leagues ?? []).filter { $0.started == true }.count }
}
struct PlayersPayload: Decodable { let players: [RosteredPlayer] }

/// A player on today's slate, ranked. `owned` empty means nobody in any
/// league you follow has him - which is exactly what makes him a target.
struct RankedPlayer: Decodable, Identifiable, Hashable {
    let id: String, name: String, pos: String, team: String
    let projected: Double?, scored: Double?, state: String?
    let lastRank: Int?, lastSeason: Int?, lastPpg: Double?
    let owned: [String]?
    let rank: Int?
    var isFree: Bool { (owned ?? []).isEmpty }
}
struct RankingsPayload: Decodable { let players: [RankedPlayer] }

struct InjuryItem: Decodable, Identifiable, Hashable {
    let id: String, name: String, pos: String?
    let severity: String?, label: String?
    let headline: String?, url: String?
    let roast: String?
}
struct InjuriesPayload: Decodable { let injuries: [InjuryItem]; let count: Int? }

/// What a player is being given, rather than what it came to. From nflverse.
struct Opportunity: Decodable, Hashable {
    let games: Int?, targets: Int?, carries: Int?
    let targetShare: Double?, airYardsShare: Double?
    let wopr: Double?, adot: Double?, yac: Double?, ppg: Double?
}

struct RankRow: Decodable, Hashable {
    let season: Int, rank: Int, field: Int, label: String
}
struct Career: Decodable, Hashable {
    let seasons: Int?, best: Double?, totalWeeks: Int?
}
