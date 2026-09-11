import Foundation
import Observation

/// Talks to `python3 -m fantasyedge api --host 0.0.0.0`.
///
/// Read-only and credential-free by design - the board holds no cookie, which
/// is exactly why it is safe to point a headset on the living-room network at
/// it. The host is settable because a real Vision Pro is not on the Mac's
/// loopback the way the simulator is.
@Observable
final class Board {
    var host: String {
        didSet { UserDefaults.standard.set(host, forKey: "fe.host") }
    }
    /// Whatever you want playing in the middle of the room. Nothing is bundled
    /// and nothing is guessed at - a stream URL or a local file, your choice.
    var watchURL: String {
        didSet { UserDefaults.standard.set(watchURL, forKey: "fe.watch") }
    }
    var leagues: [LeaguePayload] = []
    var live: LivePayload?
    var selected: String?
    var status: String = "Connecting…"
    var lastError: String?

    /// Points that have landed since the last poll, per player. A board that
    /// only shows a new total makes you diff it in your head; this is what a
    /// room full of your players should actually react to.
    var reactions: [String: Reaction] = [:]
    /// Newest first, for the feed that runs beside the board.
    var recent: [Reaction] = []
    private var lastScores: [String: Double] = [:]

    struct Reaction: Identifiable, Equatable {
        let id: String            // player id
        let name: String
        let delta: Double
        let total: Double
        let side: String
        let at: Date
        /// Roughly what a jump of this size was. Not play-by-play - the feed
        /// gives totals, not events - so it is described as a size, not
        /// claimed as a touchdown.
        var headline: String {
            switch delta {
            case 6...:  return "big play"
            case 3..<6: return "chunk"
            default:    return "moved"
            }
        }
    }

    private var poll: Task<Void, Never>?

    init() {
        host = UserDefaults.standard.string(forKey: "fe.host") ?? "127.0.0.1:8770"
        watchURL = UserDefaults.standard.string(forKey: "fe.watch") ?? ""
    }

    var league: LeaguePayload? {
        leagues.first { $0.id == selected } ?? leagues.first
    }

    /// The cells for whichever league is on screen, already joined to the feed.
    var cells: [Cell] {
        guard let L = league else { return [] }
        let players = live?.players ?? [:]
        var out = L.you.starters.map { Cell.make($0, side: "you", live: players[$0.id]) }
        if let opp = L.opp {
            out += opp.starters.map { Cell.make($0, side: "opp", live: players[$0.id]) }
        }
        return out
    }

    var mosaic: Mosaic { Leverage.evaluate(cells) }

    func url(_ path: String) -> URL? { URL(string: "http://\(host)\(path)") }

    @MainActor
    func load() async {
        do {
            guard let u = url("/api/mosaic") else { return }
            let (data, _) = try await URLSession.shared.data(from: u)
            leagues = try JSONDecoder().decode(MosaicsPayload.self, from: data).leagues
            if selected == nil { selected = leagues.first?.id }
            status = "\(leagues.count) leagues"
            lastError = nil
        } catch {
            status = "Cannot reach \(host)"
            lastError = error.localizedDescription
        }
    }

    // MARK: - the other panels

    var roster: [RosteredPlayer] = []
    var ranked: [RankedPlayer] = []
    var injuries: [InjuryItem] = []
    /// Everything the command centre needs beyond the board itself. Fetched
    /// once on open and refreshed on the slow clock: a season log and an
    /// injury wire do not move at the pace a scoreline does.
    @MainActor
    func loadContext() async {
        async let a: () = fetch("/api/players", into: PlayersPayload.self) {
            self.roster = $0.players
        }
        async let b: () = fetch("/api/rankings", into: RankingsPayload.self) {
            self.ranked = $0.players
        }
        async let c: () = fetch("/api/injuries", into: InjuriesPayload.self) {
            self.injuries = $0.injuries
        }
        _ = await (a, b, c)
    }

    private func fetch<T: Decodable>(_ path: String, into: T.Type,
                                     apply: @MainActor (T) -> Void) async {
        guard let u = url(path) else { return }
        guard let (d, _) = try? await URLSession.shared.data(from: u),
              let v = try? JSONDecoder().decode(T.self, from: d) else { return }
        await MainActor.run { apply(v) }
    }

    // MARK: - cross-league totals
    //
    // Computed here rather than asked for, because every input is already on
    // this device: asking the server to re-derive them would be a round trip
    // to add four numbers.

    var totalProjected: Double {
        leagues.reduce(0) { $0 + $1.you.starters.reduce(0) { $0 + ($1.projected ?? 0) } }
    }
    var edgeOverOpponents: Double {
        leagues.reduce(0) { acc, L in
            let you = L.you.starters.reduce(0) { $0 + ($1.projected ?? 0) }
            let opp = (L.opp?.starters ?? []).reduce(0) { $0 + ($1.projected ?? 0) }
            return acc + (you - opp)
        }
    }
    /// Projected win-loss this week, one per league, by who is ahead on
    /// projection. Not a forecast of the season - just this Sunday.
    var projectedRecord: (Int, Int) {
        var w = 0, l = 0
        for L in leagues {
            let you = L.you.starters.reduce(0) { $0 + ($1.projected ?? 0) }
            let opp = (L.opp?.starters ?? []).reduce(0) { $0 + ($1.projected ?? 0) }
            if you >= opp { w += 1 } else { l += 1 }
        }
        return (w, l)
    }
    var averageRank: Double? {
        let ranks = leagues.compactMap { $0.record?.rank }
        guard !ranks.isEmpty else { return nil }
        return Double(ranks.reduce(0, +)) / Double(ranks.count)
    }
    /// Distinct men across every league.
    var distinctPlayers: Int { roster.count }

    // MARK: - standings

    @ObservationIgnored private var standingsInFlight: Set<String> = []
    var standings: [String: [StandingRow]] = [:]

    /// Fetched once per league and kept. A standings table is a weekly fact;
    /// re-asking on the live clock would be a request every two seconds for
    /// a number that moves on Tuesdays.
    @MainActor
    func loadStandings(_ L: LeaguePayload) async {
        guard standings[L.id] == nil, !standingsInFlight.contains(L.id) else { return }
        standingsInFlight.insert(L.id)
        defer { standingsInFlight.remove(L.id) }
        guard let u = url("/api/leagues/\(L.provider)/\(L.leagueId)/standings"),
              let (d, _) = try? await URLSession.shared.data(from: u),
              let p = try? JSONDecoder().decode(StandingsPayload.self, from: d)
        else { return }
        standings[L.id] = p.standings
    }

        // MARK: - memoised derivations
    //
    // `@ObservationIgnored` is load-bearing, not an optimisation. These are
    // caches written during a view's body evaluation; if the observation
    // machinery tracked them, writing one would invalidate the view that just
    // read it and the render would loop forever.

    @ObservationIgnored private var mosaicCache: [String: (key: String, value: Mosaic)] = [:]
    @ObservationIgnored private var opponentCache: (key: String, value: [String: Fixture])?
    @ObservationIgnored private var totalsCache: [String: (key: String, value: [String: Double])] = [:]

    /// What every cached derivation is keyed on.
    ///
    /// The live payload is content-addressed by the server - `version` is a
    /// hash of the players block - so it changes exactly when a number
    /// changed, and not on every poll that returned the same thing. Which
    /// team is yours is in the key too, because picking a different team
    /// rebuilds the board around a different roster.
    private func stamp(_ L: LeaguePayload) -> String {
        "\(live?.version ?? "-")|\(L.you.teamId)|\(L.opp?.teamId ?? "-")"
    }

    /// The board for one league, so the rail can show a win probability per
    /// league rather than only for the one on screen.
    ///
    /// Memoised because it is not cheap and it is asked for constantly: the
    /// league rail and the week header each want one per league, and SwiftUI
    /// re-evaluates a body whenever anything observable moves. Without this,
    /// three leagues cost six full evaluations of the leverage model on every
    /// pass rather than three on the polls that actually changed something.
    func mosaic(for L: LeaguePayload) -> Mosaic {
        let key = stamp(L)
        if let hit = mosaicCache[L.id], hit.key == key { return hit.value }
        let players = live?.players ?? [:]
        var cells = L.you.starters.map { Cell.make($0, side: "you", live: players[$0.id]) }
        cells += (L.opp?.starters ?? []).map {
            Cell.make($0, side: "opp", live: players[$0.id])
        }
        let m = Leverage.evaluate(cells)
        mosaicCache[L.id] = (key, m)
        return m
    }

    /// One club's game: who they are playing, which end of it, and where it
    /// has got to. Served by the live tier now rather than guessed at by
    /// pairing clubs on kickoff time, which gets it wrong the moment two
    /// games start together.
    struct Fixture: Hashable {
        let opp: String, home: Bool, state: String, label: String
        let kickoff: String, score: String, oppScore: String
        var away: Bool { !home }
        /// "@ MIA" or "vs ATL" - the distinction a roster table needs.
        var line: String { (home ? "vs " : "@ ") + opp }
        var live: Bool { state == "in" }
        var final: Bool { state == "post" }
    }

    /// Each team's projected total this week, from the starters on its own
    /// roster rows. Memoised per league: a matchups tab asks for every team
    /// at once, and recomputing that on each body pass would walk a
    /// hundred-and-sixty-row array a dozen times a second.
    func teamTotals(_ L: LeaguePayload) -> [String: Double] {
        if let hit = totalsCache[L.id], hit.key == stamp(L) { return hit.value }
        var out: [String: Double] = [:]
        for r in L.roster ?? [] where r.started == true {
            out[r.teamId ?? "", default: 0] += r.projected ?? 0
        }
        totalsCache[L.id] = (stamp(L), out)
        return out
    }

    /// Every club's fixture, built once per distinct slate rather than per row
    /// of a roster table.
    var fixtures: [String: Fixture] {
        let key = live?.version ?? "-"
        if let hit = opponentCache, hit.key == key { return hit.value }
        var out: [String: Fixture] = [:]
        let games = live?.games ?? [:]
        for (ab, g) in games {
            let opp = g.opp ?? ""
            out[ab] = Fixture(opp: opp, home: g.home ?? true,
                              state: g.state ?? "pre", label: g.label ?? "",
                              kickoff: g.kickoff ?? "",
                              score: g.score ?? "",
                              oppScore: opp.isEmpty ? "" : (games[opp]?.score ?? ""))
        }
        opponentCache = (key, out)
        return out
    }

        // MARK: - which team is yours

    /// Saved per league on the server, not on this device, because the choice
    /// has to be the same one the laptop and the television already see.
    /// `POST /api/prefs` is loopback-only unless the server is told otherwise,
    /// so a real headset on the house network is told plainly when it could
    /// not save rather than appearing to and forgetting.
    var teamPrefs: [String: String] = [:]
    var prefsWritable = true

    @MainActor
    func loadPrefs() async {
        guard let u = url("/api/prefs") else { return }
        struct P: Decodable { let teams: [String: String]? }
        if let (d, _) = try? await URLSession.shared.data(from: u),
           let p = try? JSONDecoder().decode(P.self, from: d) {
            teamPrefs = p.teams ?? [:]
        }
    }

    @MainActor
    func pickTeam(_ teamId: String, in leagueId: String) async {
        teamPrefs[leagueId] = teamId
        guard let u = url("/api/prefs") else { return }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(
            withJSONObject: ["teams": [leagueId: teamId]])
        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            prefsWritable = (200..<300).contains(code)
        } catch {
            prefsWritable = false
        }
        await load()          // the server re-sizes the board around your team
    }

        @MainActor
    func refreshLive() async {
        guard let u = url("/api/live") else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: u)
            let fresh = try JSONDecoder().decode(LivePayload.self, from: data)
            noteChanges(fresh)
            live = fresh
            lastError = nil
        } catch { lastError = error.localizedDescription }
    }

    /// Work out what moved. Only for players in the league on screen, because
    /// a reaction to somebody you do not own is noise.
    @MainActor
    private func noteChanges(_ fresh: LivePayload) {
        guard let L = league else { return }
        var mine: [String: (String, String)] = [:]
        for s in L.you.starters { mine[s.id] = (s.name, "you") }
        for s in L.opp?.starters ?? [] { mine[s.id] = (s.name, "opp") }

        var fired: [Reaction] = []
        for (id, state) in fresh.players {
            guard let (name, side) = mine[id] else { continue }
            let before = lastScores[id]
            lastScores[id] = state.s
            guard let was = before else { continue }        // first sight: no diff
            let delta = state.s - was
            if delta >= 0.5 {
                fired.append(Reaction(id: id, name: name, delta: delta,
                                      total: state.s, side: side, at: .now))
            }
        }
        guard !fired.isEmpty else { return }
        for r in fired { reactions[r.id] = r }
        recent = (fired.sorted { $0.delta > $1.delta } + recent).prefix(12).map { $0 }
        // A reaction is a moment, not a state: clear it so the cell settles.
        let ids = fired.map(\.id)
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(8))
            await MainActor.run { for id in ids { self?.reactions[id] = nil } }
        }
    }

    /// Polling rather than SSE: the shared snapshot is cached for a couple of
    /// seconds at the edge anyway, so a poll costs a revalidation and keeps the
    /// client simple. Cancelled when the scene goes away.
    /// The deep profile behind a card. Cached, because opening the same player
    /// twice should not cost two round trips.
    private var profiles: [String: Profile] = [:]

    @MainActor
    func profile(_ id: String) async -> Profile? {
        if let hit = profiles[id] { return hit }
        guard let u = url("/api/player/\(id)") else { return nil }
        do {
            let (data, _) = try await URLSession.shared.data(from: u)
            let p = try JSONDecoder().decode(Profile.self, from: data)
            profiles[id] = p
            return p
        } catch { return nil }
    }

    func start() {
        poll?.cancel()
        poll = Task { [weak self] in
            await self?.load()
            while !Task.isCancelled {
                await self?.refreshLive()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }
    func stop() { poll?.cancel(); poll = nil }
}
