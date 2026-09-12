import Foundation

// Whose projection this board is quoting, and where the sources disagree.
//
// The read API has served several sources for a while - `/api/projections`
// sends every loaded one's number per player alongside the consensus - and
// this app drew a single bare figure with no name on it. That figure was
// ESPN's, because ESPN's is what rides inline on the mosaic payload, but
// nothing said so and nothing offered the alternative. An unattributed
// projection is the same failure as an invented one: the reader cannot tell
// whose opinion they are being sized by.

/// One projection source as the server describes it, loaded or not.
///
/// The pending ones travel with the loaded ones deliberately. A picker built
/// from what is loaded silently drops CBS, FantasyPros and Yahoo, and a source
/// missing from a menu reads as one that returned nothing - which is a claim
/// about the players rather than about the licence. `needs` is what each is
/// actually waiting on, and the menu says it out loud.
struct ProjectionSource: Decodable, Identifiable, Hashable {
    let source: String, label: String, status: String
    let needs: String, detail: String, attribution: String
    let loaded: Bool
    let rows: Int, weeks: Int
    var id: String { source }
}

struct ProjectionSourcesPayload: Decodable {
    let season: Int, week: Int
    let sources: [ProjectionSource]
    let loaded: [String]
    let n: Int
}

/// One man, with every loaded source's number for him.
///
/// `id` is the ESPN player id the mosaic, the roster rows and `/api/player`
/// all already key on, which is what lets this join onto the board with no
/// name matching at all.
struct ProjectionRow: Decodable, Identifiable, Hashable {
    let id: String, name: String, pos: String, team: String
    /// Source key to points. A source that is not loaded is absent rather
    /// than zero, because it cannot produce a number and a zero would be one.
    let by: [String: Double]
    let consensus: Double?
    /// How many sources contributed to that consensus. Quoted with it
    /// everywhere: a mean of two and a mean of five are not the same claim.
    let n: Int
    /// Highest source minus lowest. Nil when only one source has him, which
    /// is an absence of disagreement rather than agreement.
    let spread: Double?
}
struct ProjectionsPayload: Decodable {
    let season: Int, week: Int
    let players: [ProjectionRow]
    let total: Int
}

/// The number one surface should show for one man, and whose it is.
struct ProjectionPick: Hashable {
    let value: Double
    /// The source key it came from, "consensus", or "league" for the fallback.
    let source: String
    let label: String
    /// True when the chosen source has nothing for this man and the figure is
    /// the one the league's own board shipped inline instead. Never
    /// substituted silently: the tag reads LEAGUE so nobody is shown Sleeper's
    /// opinion of a player Sleeper has never rated.
    let fallback: Bool
    let spread: Double?
    let n: Int
    let by: [String: Double]

    /// Whether the loaded sources are far enough apart on him to be worth
    /// drawing on a tile that has room for one mark. Two points on a weekly
    /// projection is roughly the gap between a flex start and a bench; below
    /// that the disagreement is rounding and a badge on every row would train
    /// the reader to ignore the badge.
    static let disputedAt = 2.0
    var disputed: Bool { (spread ?? 0) >= Self.disputedAt }
}

extension Board {

    // MARK: - which source, resolved

    /// Every source the server knows about, loaded first.
    var loadedSources: [ProjectionSource] { projectionCatalog.filter(\.loaded) }
    var pendingSources: [ProjectionSource] { projectionCatalog.filter { !$0.loaded } }

    /// Whether a consensus is even a thing to offer. A "mean" of one source is
    /// that source under a second name, and offering it would be two menu
    /// entries for one number.
    var consensusOffered: Bool { loadedSources.count >= 2 }
    var consensusN: Int { loadedSources.count }

    /// The source the whole surface is quoting.
    ///
    /// The preference is empty until somebody picks one, and it can also name
    /// a source that has since stopped being loaded - a key expiring, a season
    /// with no rows. Either way this resolves to the first source actually
    /// loaded rather than to a hardcoded name: an install holding Sleeper and
    /// not ESPN would otherwise be told it was reading ESPN while showing
    /// Sleeper's numbers.
    var projectionChoice: String {
        if projectionPref == "consensus", consensusOffered { return "consensus" }
        if loadedSources.contains(where: { $0.source == projectionPref }) {
            return projectionPref
        }
        return loadedSources.first?.source ?? ""
    }

    /// The chosen source's name, as a person would say it.
    var projectionLabel: String {
        if projectionChoice == "consensus" { return "Consensus" }
        return projectionCatalog.first { $0.source == projectionChoice }?.label
            ?? (projectionChoice.isEmpty ? "—" : projectionChoice)
    }

    /// The same, short and shouted, for a column head or a chip. The consensus
    /// always carries its count, because a consensus that does not say how
    /// many agreed is the one number on this surface most likely to be read as
    /// authority it has not earned.
    var projectionTag: String {
        projectionChoice == "consensus"
            ? "CONSENSUS · \(consensusN)" : projectionLabel.uppercased()
    }

    /// Whether anything is loaded at all. Below this every surface says so
    /// rather than drawing an unlabelled figure again.
    var hasProjections: Bool { !loadedSources.isEmpty && !projectionIndex.isEmpty }

    /// One token naming everything a cached derivation depends on here.
    ///
    /// Folded into `stamp(_:)` and into the attention key, because switching
    /// source re-sizes the board: without it the memoised mosaic would keep
    /// handing back cells sized by the source you just moved off, and the
    /// picker would change a label and nothing else.
    var projectionStamp: String { "\(projectionChoice)|\(projectionIndex.count)" }

    // MARK: - the number for one man

    /// What to show for him, and whose it is.
    ///
    /// `fallback` is the figure the payload already carried inline - the
    /// league's own provider number. It is used only when the chosen source
    /// has nothing for him, and the pick says so, so a gap in Sleeper's board
    /// reads as a gap rather than as Sleeper agreeing with ESPN.
    func projectionPick(_ id: String, fallback: Double?) -> ProjectionPick? {
        let row = projectionIndex[id]
        let choice = projectionChoice
        if choice == "consensus", let c = row?.consensus {
            return ProjectionPick(value: c, source: "consensus",
                                  label: "Consensus", fallback: false,
                                  spread: row?.spread, n: row?.n ?? 0,
                                  by: row?.by ?? [:])
        }
        if !choice.isEmpty, let v = row?.by[choice] {
            return ProjectionPick(value: v, source: choice, label: projectionLabel,
                                  fallback: false, spread: row?.spread,
                                  n: row?.n ?? 0, by: row?.by ?? [:])
        }
        guard let f = fallback else { return nil }
        return ProjectionPick(value: f, source: "league", label: "League",
                              fallback: true, spread: row?.spread,
                              n: row?.n ?? 0, by: row?.by ?? [:])
    }

    /// The bare number, for the arithmetic the board is built out of.
    func projected(_ id: String, fallback: Double?) -> Double {
        projectionPick(id, fallback: fallback)?.value ?? fallback ?? 0
    }

    // MARK: - where they disagree

    /// His position rank under one source, "QB2" style.
    ///
    /// Computed here rather than taken from the payload's `posRank`, which is
    /// ranked for whichever source was asked for - quoting it beside a
    /// different source's points would put ESPN's rank next to Sleeper's
    /// number. Memoised because the disagreement panel wants two full
    /// orderings and would otherwise sort three hundred rows twice per body
    /// pass; `@ObservationIgnored` for the reason every cache on this class
    /// is, since it is written during a body evaluation.
    func posRanks(_ source: String) -> [String: String] {
        let key = "\(source)|\(projectionIndex.count)"
        if let hit = posRankCache[key] { return hit }
        let men = projectionIndex.values.compactMap { r -> (ProjectionRow, Double)? in
            let v = source == "consensus" ? r.consensus : r.by[source]
            return v.map { (r, $0) }
        }.sorted { $0.1 > $1.1 }
        var seen: [String: Int] = [:]
        var out: [String: String] = [:]
        for (r, _) in men where !r.pos.isEmpty {
            let n = seen[r.pos, default: 0] + 1
            seen[r.pos] = n
            out[r.id] = "\(r.pos)\(n)"
        }
        posRankCache[key] = out
        return out
    }

    /// Your starters in the selected league, worst disagreement first.
    ///
    /// Scoped to men you are actually starting because that is where a
    /// disagreement costs something: the sources arguing about a bench tight
    /// end is trivia, the same argument about your flex is a decision. Empty
    /// when only one source is loaded, which is not agreement - it is nobody
    /// to disagree with.
    func disagreements(in L: LeaguePayload?) -> [(ProjectionRow, Double)] {
        guard consensusOffered, let L else { return [] }
        let mine = L.you.starters.map(\.id)
        return mine.compactMap { id -> (ProjectionRow, Double)? in
            guard let r = projectionIndex[id], let s = r.spread, s > 0 else { return nil }
            return (r, s)
        }
        .sorted { $0.1 > $1.1 }
    }

    // MARK: - fetching, and choosing

    /// The catalogue and the whole board, once.
    ///
    /// Once, not per body pass and not on the live clock: a weekly projection
    /// is republished on a slow schedule and the rows carry *every* source's
    /// number, so switching source is arithmetic already on the device rather
    /// than another request. Three hundred rows is one small response, which
    /// is why no `limit` is sent - paging the fetch would only mean the board
    /// could not size a starter who happened to fall off the end.
    @MainActor
    func loadProjections(force: Bool = false) async {
        guard force || !projectionsLoaded else { return }
        projectionsLoaded = true
        await fetch("/api/projections/sources", into: ProjectionSourcesPayload.self) {
            self.projectionCatalog = $0.sources
            self.projectionSeason = $0.season
            self.projectionWeek = $0.week
        }
        await fetch("/api/projections", into: ProjectionsPayload.self) {
            self.projectionIndex = Dictionary($0.players.map { ($0.id, $0) },
                                              uniquingKeysWith: { a, _ in a })
            self.posRankCache = [:]
        }
    }

    /// Save the choice where the laptop and the television will see it too.
    ///
    /// Same merge path `POST /api/prefs` has always used for the team picker,
    /// so the one file that holds which team is yours is not written any other
    /// way. Applied locally first because the board must move on the pinch
    /// rather than on the round trip; `prefsWritable` still records whether it
    /// actually persisted, exactly as picking a team does.
    @MainActor
    func pickProjectionSource(_ key: String) async {
        guard key != projectionPref else { return }
        projectionPref = key
        await writePrefs(["projection": key])
    }
}
