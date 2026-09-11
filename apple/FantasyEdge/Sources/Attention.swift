import Foundation
import SwiftUI

// What changes between one league and ten, and the ranking that makes ten
// readable. Kept out of the views because it is arithmetic over the same
// payload every rail reads, and because "which league needs me" is a claim
// worth being able to argue with on its own.

/// How many leagues the console is actually about.
///
/// Read off what the board returned rather than set anywhere, because the
/// right layout for one league is not the layout for ten with fewer rows in
/// it. Three cases and no more: below two there is nothing to compare, up to
/// four everything fits at once, and past that an exhaustive list stops being
/// a list and becomes a wall.
enum LeagueScale {
    case single, few, many

    init(_ count: Int) {
        switch count {
        case ...1:  self = .single
        case 2...4: self = .few
        default:    self = .many
        }
    }
    var single: Bool { self == .single }
    var many: Bool { self == .many }
}

/// One league, with what is at stake in it this week and why.
struct LeagueFocus: Identifiable {
    let league: LeaguePayload
    let mosaic: Mosaic
    let score: Double
    let reason: Reason
    /// Your starters in this league who are on the injury wire.
    let hurt: Int
    /// Change in your win probability since the last time any number moved.
    /// Zero on the first sight of a league, which is honest: nothing has
    /// happened yet that this could be the size of.
    let swing: Double
    var id: String { league.id }

    /// Whether the week here still has a question in it. A collapsed row is
    /// not a hidden one - a matchup that is over, or that a fifteen-point
    /// swing would not turn, has an answer, and answers belong on one line.
    var decided: Bool {
        mosaic.phase == "final" || mosaic.winProb >= 0.9 || mosaic.winProb <= 0.1
    }

    /// The single most useful thing to say about this league in three words.
    /// Ordered by what would make you open it: somebody hurt beats a close
    /// game, a close game beats a comfortable one.
    enum Reason {
        case hurt(Int), slipping, coinFlip, behind, comfortable
        case finished, notStarted, inPlay

        var label: String {
            switch self {
            case .hurt(let n): return n == 1 ? "1 on the wire" : "\(n) on the wire"
            case .slipping:    return "lead slipping"
            case .coinFlip:    return "too close to call"
            case .behind:      return "needs a swing"
            case .comfortable: return "comfortable"
            case .finished:    return "final"
            case .notStarted:  return "not started"
            case .inPlay:      return "in play"
            }
        }
        var tint: Color {
            switch self {
            case .hurt, .behind:            return Theme.red
            case .slipping, .coinFlip:      return Theme.gold
            case .comfortable:              return Theme.green
            case .finished, .notStarted, .inPlay: return .secondary
            }
        }
    }
}

extension Board {

    var scale: LeagueScale { LeagueScale(leagues.count) }

    /// Every league, ordered by what actually needs you.
    ///
    /// Ten leagues in the order the server happened to send them is ten rows
    /// to read; ten in this order is one to read and nine to ignore. Nothing
    /// here is new data - it is the leverage model, the injury wire and the
    /// win probability this app already had, weighed against each other once.
    ///
    /// Memoised, and that matters more here than anywhere else on the surface:
    /// this is the only caller of `mosaic(for:)` that the rails go through, so
    /// ten leagues cost ten leverage evaluations per content change rather
    /// than ten per rail per body pass. The key carries the live version - the
    /// server content-addresses that block - plus which team is yours in each
    /// league and how many injuries have landed, which are the only other
    /// inputs. `focusCache` is `@ObservationIgnored` for the reason every
    /// cache on this class is: it is written during a body evaluation, and a
    /// tracked write would invalidate the view that just read it.
    func attention() -> [LeagueFocus] {
        let key = leagues.reduce("\(live?.version ?? "-")|\(injuries.count)") {
            $0 + "|\($1.id):\($1.you.teamId)"
        }
        if let hit = focusCache, hit.key == key { return hit.value }

        let wired = Set(injuries.map(\.id))
        var out: [LeagueFocus] = []
        for L in leagues {
            let m = mosaic(for: L)
            let hurt = L.you.starters.reduce(0) { $0 + (wired.contains($1.id) ? 1 : 0) }
            // Keyed on the team as well as the league: picking a different
            // team rebuilds the board around a different roster, and the drop
            // from the old team's win probability to the new one is not a
            // swing, it is a different question.
            let trailKey = "\(L.id)|\(L.you.teamId)"
            let swing = winProbTrail[trailKey].map { m.winProb - $0 } ?? 0
            winProbTrail[trailKey] = m.winProb

            // A close game is the base of it; the top man's leverage is how
            // much of that is still in front of you rather than banked; a
            // lead going the wrong way is the thing you would want to be told
            // about even when the number still says you are ahead.
            var score = 100 * m.intensity
                + 260 * (m.cells.first?.leverage ?? 0)
                + 30 * Double(hurt)
                + (swing < 0 ? 180 * -swing : 0)
            switch m.phase {
            case "live": score += 45
            case "pre":  score += 10
            // A finished week is a fact, not a question. Damped rather than
            // dropped, so a league still sorts above one that has not loaded.
            default:     score *= 0.15
            }

            let reason: LeagueFocus.Reason
            if hurt > 0                                  { reason = .hurt(hurt) }
            else if m.phase == "final"                   { reason = .finished }
            else if swing <= -0.06 && m.winProb >= 0.5   { reason = .slipping }
            else if m.intensity >= 0.6                   { reason = .coinFlip }
            else if m.winProb <= 0.25                    { reason = .behind }
            else if m.winProb >= 0.80                    { reason = .comfortable }
            else if m.phase == "pre"                     { reason = .notStarted }
            else                                         { reason = .inPlay }

            out.append(LeagueFocus(league: L, mosaic: m, score: score,
                                   reason: reason, hurt: hurt, swing: swing))
        }
        // League id breaks the tie so the rail does not shuffle between polls
        // when two leagues score identically, which they do all pre-game.
        out.sort { ($0.score, $1.league.id) > ($1.score, $0.league.id) }
        focusCache = (key, out)
        return out
    }

    /// One league's place in that ranking, for the rails that want to keep
    /// your own arrangement and only borrow the reasoning.
    func focus(_ L: LeaguePayload) -> LeagueFocus? {
        attention().first { $0.id == L.id }
    }

    /// The one line a ten-league week header leads with. The three counts add
    /// up to the number of leagues, whatever that number is, which is the only
    /// way a summary is allowed to replace a list.
    func weekTally() -> (ahead: Int, doubt: Int, behind: Int) {
        var a = 0, d = 0, b = 0
        for f in attention() {
            if f.mosaic.winProb >= 0.6 { a += 1 }
            else if f.mosaic.winProb <= 0.4 { b += 1 }
            else { d += 1 }
        }
        return (a, d, b)
    }
}

// MARK: - seeing a league count this install does not have

/// A test affordance, and nothing else reads it.
///
/// This install follows three leagues, so neither end of the range the
/// console has to work at can be reached by waiting. `FE_LEAGUE_COUNT` caps
/// or repeats the decoded list *in the client only* - nothing is written, no
/// preference is touched, and no number is invented: a repeat is the same
/// real league again under a distinct id, so a screenshot of ten shows ten
/// real boards rather than ten made-up ones.
///
/// ```
/// xcrun simctl launch --console <device> com.mutaaf.fantasyedge  # normal
/// FE_LEAGUE_COUNT=10  # set in the scheme, or SIMCTL_CHILD_FE_LEAGUE_COUNT
/// ```
enum Debug {
    static func resize(_ leagues: [LeaguePayload]) -> [LeaguePayload] {
        #if DEBUG
        guard let raw = ProcessInfo.processInfo.environment["FE_LEAGUE_COUNT"],
              let want = Int(raw), want > 0, !leagues.isEmpty,
              want != leagues.count else { return leagues }
        if want < leagues.count { return Array(leagues.prefix(want)) }
        return (0..<want).map { i in
            let src = leagues[i % leagues.count]
            guard i >= leagues.count else { return src }
            let copy = i / leagues.count + 1
            return src.relabelled(id: "\(src.id)#\(copy)",
                                  league: "\(src.league) \(copy + 1)")
        }
        #else
        return leagues
        #endif
    }
}
