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
    /// How much of the room the hall of fame takes, and the one piece of
    /// scene state the app's `ImmersiveSpace` declaration and the space itself
    /// both have to see. It lives here rather than in either because
    /// `.immersionStyle(selection:)` is declared on the scene and the picker
    /// that drives it is inside the space, and `any ImmersionStyle` cannot be
    /// compared or stored in a `@State` the two share.
    var hallStyle: RoomStyle = .full
    /// The same choice for the board space, which defaults the other way: a
    /// board is a thing you have *while* watching a real game in a real room,
    /// so blacking the room out is the wrong default even though it is now
    /// offered.
    var boardStyle: RoomStyle = .mixed

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
        var out = L.you.starters.map {
            Cell.make($0, side: "you", live: players[$0.id],
                      projected: projected($0.id, fallback: $0.projected))
        }
        if let opp = L.opp {
            out += opp.starters.map {
                Cell.make($0, side: "opp", live: players[$0.id],
                          projected: projected($0.id, fallback: $0.projected))
            }
        }
        return out
    }

    /// The board for whichever league is on screen.
    ///
    /// Routed through the memoised `mosaic(for:)` rather than evaluating the
    /// leverage model afresh. It reads as a cheap property and is not: the
    /// immersive space asks for it three times per pass - once to build the
    /// attachments, once to place them, once for the scoreline - and a
    /// `RealityView` update runs on the compositor's clock, not on a poll.
    var mosaic: Mosaic { league.map { mosaic(for: $0) } ?? Leverage.evaluate([]) }

    // MARK: - the league that is selected
    //
    // These exist because choosing a league in the rail used to change one
    // highlight and nothing else. The command centre's centre and right rails
    // read `roster` and `ranked`, both of which are collapsed across every
    // league you follow, so `selected` had no reader outside the Leagues tab
    // and the tap looked broken. Everything below is a filter over payloads
    // already on the device - no extra request, and nothing invented.

    /// The league a rail row is really about.
    ///
    /// `Debug.resize` clones a real league under "<id>#2" so a three-league
    /// install can be made to render ten. Every join that keys on a league -
    /// which of your men are in it, who owns a free agent - has to go through
    /// the original, or a clone renders as a league nobody is in and the
    /// selection looks broken at exactly the scale it was written to test.
    func origin(_ L: LeaguePayload) -> LeaguePayload {
        guard let hash = L.id.firstIndex(of: "#") else { return L }
        let base = String(L.id[L.id.startIndex..<hash])
        return leagues.first { $0.id == base } ?? L
    }

    /// Your men in the selected league, with their cross-league facts intact.
    ///
    /// `/api/players` collapses a man across every league you follow and
    /// carries the league ids he is rostered in, so this is a filter rather
    /// than another request, and `exposure` on each row still counts all of
    /// them - which is the point of a cross-league board.
    var rosterHere: [RosteredPlayer] {
        guard let L = league.map(origin) else { return roster }
        let mine = roster.filter { p in
            (p.leagues ?? []).contains { $0.id == L.id }
        }
        // A league whose ownership rows have not arrived yet would otherwise
        // blank the centre rail. Falling back to everything is the honest
        // failure: it is what the panel showed before, not an empty claim.
        return mine.isEmpty ? roster : mine
    }

    /// Where one of your men sits in the selected league. A man can be a
    /// starter in one league and on the bench in another, so "started" is
    /// only true of a league, never of a man.
    func here(_ p: RosteredPlayer) -> Ownership? {
        guard let L = league.map(origin) else { return nil }
        return (p.leagues ?? []).first { $0.id == L.id }
    }

    /// Men on today's slate that nobody in the selected league rosters.
    ///
    /// `/api/rankings` names the leagues each man is owned in, so this is a
    /// fact about that league rather than a guess. The cross-league version -
    /// free in *every* league - is `RankedPlayer.isFree`, and the two differ
    /// the moment one league's waiver wire is deeper than another's.
    var freeHere: [RankedPlayer] {
        guard let name = league.map(origin)?.league else {
            return ranked.filter(\.isFree)
        }
        return ranked.filter { !($0.owned ?? []).contains(name) }
    }

    /// Whoever in the selected league has the most at stake right now.
    ///
    /// Lives here rather than in the view so the right rail follows the
    /// league you picked: it was `roster.max` across everything, which is the
    /// same man whichever league is selected.
    var defaultFocus: String? {
        let scored = live?.players ?? [:]
        return rosterHere.max {
            let a = scored[$0.id]?.s ?? ($0.projected ?? 0)
            let b = scored[$1.id]?.s ?? ($1.projected ?? 0)
            return a < b
        }?.id
    }

    func url(_ path: String) -> URL? { URL(string: "http://\(host)\(path)") }

    @MainActor
    func load() async {
        do {
            guard let u = url("/api/mosaic") else { return }
            let (data, _) = try await URLSession.shared.data(from: u)
            leagues = Debug.resize(
                try JSONDecoder().decode(MosaicsPayload.self, from: data).leagues)
            // A league that went away - hidden, or gone from the database -
            // must not stay selected, or every rail keeps rendering a board
            // the server no longer sends.
            if selected == nil || !leagues.contains(where: { $0.id == selected }) {
                selected = leagues.first?.id
            }
            status = leagues.count == 1 ? "1 league" : "\(leagues.count) leagues"
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

    /// Internal rather than private only because `Projections.swift` fetches
    /// through it; an extension cannot see a private member of the class.
    func fetch<T: Decodable>(_ path: String, into: T.Type,
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

    /// Every total on this surface goes through `side(_:)` so the cross-league
    /// tiles cannot come to disagree with the cells they are a sum of. Adding
    /// the payload's inline figure here while the board was sized by Sleeper
    /// would have put two different projected totals on the same screen.
    private func side(_ men: [Starter]) -> Double {
        men.reduce(0) { $0 + projected($1.id, fallback: $1.projected) }
    }
    var totalProjected: Double {
        leagues.reduce(0) { $0 + side($1.you.starters) }
    }
    var edgeOverOpponents: Double {
        leagues.reduce(0) { acc, L in
            acc + (side(L.you.starters) - side(L.opp?.starters ?? []))
        }
    }
    /// Projected win-loss this week, one per league, by who is ahead on
    /// projection. Not a forecast of the season - just this Sunday.
    var projectedRecord: (Int, Int) {
        var w = 0, l = 0
        for L in leagues {
            if side(L.you.starters) >= side(L.opp?.starters ?? []) { w += 1 } else { l += 1 }
        }
        return (w, l)
    }
    /// Where you are placed, said in whatever way is true of the number of
    /// leagues there actually are.
    ///
    /// An average over one league is not an average, it is that league's rank,
    /// and "#4.0 AVG RANK" over a single league reads as a derived statistic
    /// when it is a plain fact. It is also an average over however many
    /// leagues *reported* a rank, which is not always all of them, so the
    /// label carries that count whenever the two differ - otherwise the tile
    /// quietly changes meaning as leagues load.
    var rankSummary: (value: String, label: String) {
        let ranks = leagues.compactMap { $0.record?.rank }
        guard !ranks.isEmpty else { return ("—", "RANK") }
        if ranks.count == 1, let only = leagues.first(where: { $0.record?.rank != nil }) {
            let of = only.record?.of
            return ("#\(ranks[0])" + (of.map { " of \($0)" } ?? ""), "LEAGUE RANK")
        }
        let mean = Double(ranks.reduce(0, +)) / Double(ranks.count)
        let label = ranks.count == leagues.count
            ? "AVG RANK" : "AVG RANK · \(ranks.count) OF \(leagues.count)"
        return ("#" + mean.formatted(.number.precision(.fractionLength(1))), label)
    }
    /// Distinct men across every league.
    var distinctPlayers: Int { roster.count }

    // MARK: - the player universe

    var universe: UniversePayload?
    var universeLoading = false
    @ObservationIgnored private var universeKey = ""

    /// Every player, filtered by the server.
    ///
    /// The predicate runs there rather than here so a headset, a television
    /// and a browser do not each ship their own copy of it and drift. The
    /// result is keyed on the query, so flipping back to a filter you have
    /// already seen is free.
    @ObservationIgnored private var universeCache: [String: UniversePayload] = [:]

    @MainActor
    func loadUniverse(pos: String = "", scope: String = "", q: String = "") async {
        var parts: [String] = []
        if !pos.isEmpty { parts.append("pos=\(pos)") }
        if !scope.isEmpty { parts.append("scope=\(scope)") }
        if !q.isEmpty,
           let e = q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            parts.append("q=\(e)")
        }
        let key = parts.joined(separator: "&")
        universeKey = key
        if let hit = universeCache[key] { universe = hit; return }
        universeLoading = true
        defer { universeLoading = false }
        guard let u = url("/api/universe" + (key.isEmpty ? "" : "?" + key)),
              let (d, _) = try? await URLSession.shared.data(from: u),
              let p = try? JSONDecoder().decode(UniversePayload.self, from: d)
        else { return }
        universeCache[key] = p
        // A slower request that finished after the user moved on must not
        // replace what they are looking at now.
        if universeKey == key { universe = p }
    }

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

        // MARK: - one game, on a field

    var gamecasts: [String: Gamecast] = [:]
    /// What the server said when it had no play data. Kept rather than
    /// swallowed: "this game has not kicked off" is an answer, and a field
    /// that shows it is telling the truth about why it is empty.
    var gamecastMissing: [String: String] = [:]
    @ObservationIgnored private var gamecastStamp: [String: String] = [:]
    @ObservationIgnored private var gamecastInFlight: Set<String> = []

    /// One gamecast per game, and a finished game exactly once.
    ///
    /// Every club in a game carries the same `event`, so a field that opened
    /// one per club would fetch the same drives twice; the caller passes an
    /// event, never a club. A finished game is stamped "post" and never asked
    /// for again, because its drives cannot change. A running one re-fetches
    /// only when the shared live payload's content hash moved, so a field left
    /// open costs a request when something happened rather than every poll.
    @MainActor
    func loadGamecast(_ event: String, finished: Bool) async {
        let stamp = finished ? "post" : (live?.version ?? "-")
        if gamecastStamp[event] == stamp || gamecastInFlight.contains(event) { return }
        gamecastInFlight.insert(event)
        defer { gamecastInFlight.remove(event) }
        guard let u = url("/api/gamecast/\(event)") else { return }
        do {
            let (d, resp) = try await URLSession.shared.data(from: u)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                struct Failure: Decodable { let error: String?; let fix: String? }
                let f = try? JSONDecoder().decode(Failure.self, from: d)
                gamecastMissing[event] = f?.error ?? "No play data for this game."
                gamecastStamp[event] = stamp
                return
            }
            gamecasts[event] = try JSONDecoder().decode(Gamecast.self, from: d)
            gamecastMissing[event] = nil
            gamecastStamp[event] = stamp
        } catch { lastError = error.localizedDescription }
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
    @ObservationIgnored private var lineupCache: (key: String, value: [FieldMan])?
    @ObservationIgnored private var slateCache: (key: String, value: [SlateGame])?
    @ObservationIgnored private var winProbCache: (key: String, value: WinProbSeries)?
    /// The ranked rail, and the win probabilities it compares against. Stored
    /// here rather than beside the code that fills them in `Attention.swift`
    /// only because Swift will not let an extension add stored properties.
    @ObservationIgnored var focusCache: (key: String, value: [LeagueFocus])?
    @ObservationIgnored var winProbTrail: [String: Double] = [:]

    /// What every cached derivation is keyed on.
    ///
    /// The live payload is content-addressed by the server - `version` is a
    /// hash of the players block - so it changes exactly when a number
    /// changed, and not on every poll that returned the same thing. Which
    /// team is yours is in the key too, because picking a different team
    /// rebuilds the board around a different roster.
    /// Which source is quoted is in the key because the board is *sized* by
    /// it: without this the memoised mosaic would keep handing back cells
    /// built from the source you just moved off, and the picker would change
    /// a label and nothing behind it.
    private func stamp(_ L: LeaguePayload) -> String {
        "\(live?.version ?? "-")|\(L.you.teamId)|\(L.opp?.teamId ?? "-")|\(projectionStamp)"
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
        var cells = L.you.starters.map {
            Cell.make($0, side: "you", live: players[$0.id],
                      projected: projected($0.id, fallback: $0.projected))
        }
        cells += (L.opp?.starters ?? []).map {
            Cell.make($0, side: "opp", live: players[$0.id],
                      projected: projected($0.id, fallback: $0.projected))
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
            out[r.teamId ?? "", default: 0] += projected(r.id, fallback: r.projected)
        }
        totalsCache[L.id] = (stamp(L), out)
        return out
    }

    /// The win-probability series a chart draws, walked out of the gamecast
    /// once rather than on every body pass. Keyed on the point count, which
    /// is the only thing that changes about it: the feed appends a point per
    /// play and never rewrites the ones behind it.
    func winProb(_ gc: Gamecast) -> WinProbSeries {
        let key = "\(gc.event)|\(gc.winProbability.count)"
        if let hit = winProbCache, hit.key == key { return hit.value }
        var scored: Set<String> = []
        for d in gc.drives { for p in d.plays where p.scoring { scored.insert(p.id) } }
        let points = gc.winProbability.filter { $0.home != nil }
        let out = WinProbSeries(
            home: points.map { $0.home ?? 0.5 },
            plays: points.map(\.play),
            scoring: points.indices.filter { scored.contains(points[$0].play) })
        winProbCache = (key, out)
        return out
    }

    /// One game, out of the two club entries the live tier reports it as.
    struct SlateGame: Identifiable, Hashable {
        let event: String
        let home: String, away: String
        let homeScore: String, awayScore: String
        let state: String, label: String, kickoff: String
        /// The club with the ball, empty when nobody has it.
        let possession: String
        let down: Int?, distance: Int?, toEndzone: Int?, redZone: Bool
        var id: String { event }
        var live: Bool { state == "in" }
        var finished: Bool { state == "post" }
        var line: String { "\(away) @ \(home)" }
    }

    /// The slate, paired back up by event id.
    ///
    /// The old pairing keyed on kickoff time, which is fine until two games
    /// start in the same minute - which on a Sunday is most of them. Every
    /// club now carries the event it is in, so this groups on that and is
    /// right by construction. Memoised: it is asked for by a picker that
    /// rebuilds on every body pass.
    var slate: [SlateGame] {
        let key = live?.version ?? "-"
        if let hit = slateCache, hit.key == key { return hit.value }
        var byEvent: [String: [(String, GameState)]] = [:]
        for (ab, g) in live?.games ?? [:] {
            guard let ev = g.event, !ev.isEmpty else { continue }
            byEvent[ev, default: []].append((ab, g))
        }
        let out = byEvent.compactMap { ev, sides -> SlateGame? in
            guard sides.count == 2 else { return nil }
            let h = sides.first { $0.1.home == true } ?? sides[0]
            let a = sides.first { $0.0 != h.0 } ?? sides[1]
            return SlateGame(
                event: ev, home: h.0, away: a.0,
                homeScore: h.1.score ?? "0", awayScore: a.1.score ?? "0",
                state: h.1.state ?? "pre", label: h.1.label ?? "",
                kickoff: h.1.kickoff ?? "",
                possession: h.1.possession ?? "",
                down: h.1.down, distance: h.1.distance,
                toEndzone: h.1.toEndzone, redZone: h.1.redZone ?? false)
        }
        // Running games first, then the ones already in the books, then what
        // has not kicked off. That is the order a field can actually use: a
        // game with no plays in it yet has nothing to draw, so it should not
        // be the first thing a picker offers.
        .sorted {
            let rank = { (g: SlateGame) in g.live ? 0 : (g.finished ? 1 : 2) }
            return rank($0) == rank($1)
                ? ($0.kickoff, $0.away) < ($1.kickoff, $1.away)
                : rank($0) < rank($1)
        }
        slateCache = (key, out)
        return out
    }

    /// Every man you are starting anywhere, placed on one field by what is
    /// happening in his own game.
    ///
    /// Memoised on the live version for the same reason everything else here
    /// is: the arrangement can only change when the live payload does, and a
    /// body that re-derives twenty placements on every SwiftUI pass is doing
    /// it a dozen times a second for a field that moved once a minute. The
    /// roster count is in the key because a league loading late adds men.
    /// Narrow every field on the Live tab to one league's starters. Empty is
    /// all of them, which is what a cross-league board is for; naming a league
    /// is what you want the moment one of them is the one you care about
    /// today. In the memo key below because it changes who is on the field.
    var lineupScope: String = ""

    func lineup() -> [FieldMan] {
        let key = "\(live?.version ?? "-")|\(roster.count)|\(leagues.count)|\(lineupScope)"
        if let hit = lineupCache, hit.key == key { return hit.value }
        let games = live?.games ?? [:]
        let scored = live?.players ?? [:]
        // Sorted before lanes are handed out, so a man keeps the same lane
        // from one poll to the next instead of swapping with whoever happened
        // to sort beside him and sliding across the field for no reason.
        //
        // "Started" is only ever true of a league, never of a man: scoping to
        // one league asks whether he is in *that* line-up, not whether he is
        // in any of them.
        let men = roster.filter { p in
            guard !lineupScope.isEmpty else { return p.startedIn > 0 }
            return (p.leagues ?? []).contains {
                $0.id == lineupScope && $0.started == true
            }
        }
            .sorted { ($0.pos, $0.name, $0.id) < ($1.pos, $1.name, $1.id) }
        var taken: [String: Int] = [:]
        var out: [FieldMan] = []
        for p in men {
            let g = games[p.team]
            let lane = taken[p.pos.uppercased(), default: 0]
            taken[p.pos.uppercased()] = lane + 1
            let spot = Gridiron.place(
                .init(pos: p.pos, state: g?.state ?? "pre",
                      attacking: g?.attacking, toEndzone: g?.toEndzone),
                index: lane)
            out.append(FieldMan(
                id: p.id, name: p.name, pos: p.pos, team: p.team,
                img: p.img, logo: p.logo, spot: spot,
                opp: g?.opp ?? "", home: g?.home ?? true, event: g?.event ?? "",
                state: g?.state ?? "pre", label: g?.label ?? "",
                kickoff: g?.kickoff ?? "",
                score: g?.score ?? "", oppScore: games[g?.opp ?? ""]?.score ?? "",
                attacking: g?.attacking,
                down: g?.down, distance: g?.distance, toEndzone: g?.toEndzone,
                redZone: g?.redZone ?? false,
                points: scored[p.id]?.s ?? 0, lineups: p.startedIn))
        }
        lineupCache = (key, out)
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
    /// The two other things the same file holds: which leagues you have put
    /// away, and the order you arranged the rest in. `/api/mosaic` already
    /// honours both; the app could not read them back, so it had no way to
    /// show you what you had hidden or to let you undo it.
    var hiddenLeagues: [String] = []
    var leagueOrder: [String] = []
    /// Every league in the database, hidden ones included - the only place a
    /// hidden league's name can come from, since the board stops sending it.
    var catalogue: [LeagueRef] = []

    // MARK: - whose projections
    //
    // Stored here rather than beside the code that uses them in
    // `Projections.swift` only because Swift will not let an extension add
    // stored properties - the same reason `focusCache` lives up here.

    /// The saved choice, verbatim. Empty means nobody has chosen; it is
    /// resolved against the sources actually loaded by `projectionChoice`,
    /// never defaulted to a source name here.
    var projectionPref: String = ""
    var projectionCatalog: [ProjectionSource] = []
    /// Every source's number per player, keyed on the ESPN player id the
    /// mosaic and the roster rows already use.
    var projectionIndex: [String: ProjectionRow] = [:]
    var projectionSeason = 0
    var projectionWeek = 0
    /// Fetched once, off the slow clock. `@ObservationIgnored` because it is
    /// read and set from a `.task` that a body starts, and tracking it would
    /// invalidate the view that just triggered the fetch.
    @ObservationIgnored var projectionsLoaded = false
    /// Positional orderings per source, written during a body evaluation - so
    /// `@ObservationIgnored` for the same load-bearing reason as every other
    /// cache on this class.
    @ObservationIgnored var posRankCache: [String: [String: String]] = [:]

    @MainActor
    func loadPrefs() async {
        guard let u = url("/api/prefs") else { return }
        struct P: Decodable {
            let teams: [String: String]?
            let hidden: [String]?, order: [String]?
            let projection: String?
        }
        if let (d, _) = try? await URLSession.shared.data(from: u),
           let p = try? JSONDecoder().decode(P.self, from: d) {
            teamPrefs = p.teams ?? [:]
            hiddenLeagues = p.hidden ?? []
            leagueOrder = p.order ?? []
            projectionPref = p.projection ?? ""
        }
        await fetch("/api/leagues", into: LeagueCatalogue.self) {
            self.catalogue = $0.leagues
        }
    }

    /// A hidden league by name, for the row that offers it back.
    func name(ofHidden id: String) -> String {
        catalogue.first { "\($0.provider)-\($0.leagueId)" == id }?.name ?? id
    }

    /// Put a league away, or bring every one of them back.
    ///
    /// A hide with no way out is a bug rather than a feature: the install this
    /// was written against already had a league hidden by hand months earlier
    /// and nothing on any surface admitted it existed. The whole list is sent
    /// because the server replaces a key it is given rather than merging into
    /// it - a patch of one id would drop everything else you had put away.
    @MainActor
    func hide(_ id: String) async {
        guard !hiddenLeagues.contains(id) else { return }
        await writePrefs(["hidden": hiddenLeagues + [id]])
    }
    @MainActor
    func unhideAll() async {
        guard !hiddenLeagues.isEmpty else { return }
        await writePrefs(["hidden": []])
    }
    /// Move one league to the front of the arrangement. The rest keep their
    /// relative order, and leagues the server has not sent yet are appended so
    /// a pin made today survives a league loading tomorrow.
    @MainActor
    func pin(_ id: String) async {
        let known = leagues.map(\.id)
        let rest = (leagueOrder + known).reduce(into: [String]()) { acc, x in
            if x != id, !acc.contains(x) { acc.append(x) }
        }
        await writePrefs(["order": [id] + rest])
    }

    /// Internal for the same reason `fetch` is: the projection picker writes
    /// through this one merge path rather than growing a second POST.
    @MainActor
    func writePrefs(_ patch: [String: Any]) async {
        guard let u = url("/api/prefs") else { return }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: patch)
        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            prefsWritable = (200..<300).contains(
                (resp as? HTTPURLResponse)?.statusCode ?? 0)
        } catch { prefsWritable = false }
        guard prefsWritable else { return }
        await loadPrefs()
        await load()
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

    /// Whether a live fetch is in flight, for the refresh control to trace.
    var liveRefreshing = false
    /// Guards the timer and the button against each other. Two overlapping
    /// requests for the same snapshot cost two round trips and can land out of
    /// order, which shows as a scoreline going backwards.
    @ObservationIgnored private var liveInFlight = false
    var liveFetchedAt: Date?

    @MainActor
    func refreshLive() async {
        guard !liveInFlight, let u = url("/api/live") else { return }
        liveInFlight = true
        liveRefreshing = true
        defer { liveInFlight = false; liveRefreshing = false }
        do {
            let (data, _) = try await URLSession.shared.data(from: u)
            let fresh = try JSONDecoder().decode(LivePayload.self, from: data)
            noteChanges(fresh)
            // Assigned only on success. A failed poll must not blank a board
            // that already has a snapshot on it: the last known scoreline is
            // stale, an empty one is wrong, and the error line says which.
            live = fresh
            liveFetchedAt = .now
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

    /// How long to wait before asking again.
    ///
    /// Thirty seconds with jitter, drawn fresh every cycle rather than once at
    /// launch. A fixed interval is the problem: every client that opened
    /// during the same commercial break stays in step for the rest of the
    /// afternoon and arrives at the origin together, and one that seeded its
    /// offset at launch keeps whatever phase it happened to start in. Drawing
    /// per cycle is what actually spreads them, and re-drawing costs nothing.
    private static func beat() -> Duration {
        .seconds(Double.random(in: 25...35))
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

    // MARK: - the intel brief
    //
    // Two things are cached here and they are cached for different reasons.
    //
    // The brief is expensive on the Mac and slow-moving: it is built from
    // `mosaics()`, which honours `prefs.json`, so the server caches it on the
    // config clock rather than the live one. Refetching it on the five-second
    // poll would run nine analyses and an nflverse join against a payload that
    // changes when a line-up changes, which is not on a Sunday-afternoon
    // timescale. So it has a life, and a poll never touches it.
    //
    // The narration is expensive *here* - on-device inference is battery and
    // thermals on a headset, and money on a hosted key. It is never run from a
    // poll and never from a body evaluation; only from a button. What it is
    // keyed on is the prompt the brief carried, which is a flattening of every
    // finding and every caveat, so it survives a refetch that changed nothing
    // and is dropped the moment a number underneath it moved.

    var intel: IntelBrief?
    /// Why there is no brief, in plain language. Kept rather than swallowed:
    /// "this server has no intel route yet" is an answer, and a tab that says
    /// it is telling the truth about why it is empty.
    var intelNote: String?
    var intelLoading = false
    var aiProviders: [ModelProvider] = []

    /// Bookkeeping written from tasks and read from bodies. `@ObservationIgnored`
    /// for the same reason every memo above is - see the note on the memoised
    /// derivations.
    @ObservationIgnored private var intelAt: Date?
    @ObservationIgnored private var intelInFlight = false
    @ObservationIgnored private var modelsLoaded = false

    /// How long a brief is treated as current. Two minutes rather than a
    /// version stamp because this payload carries no content hash of its own:
    /// the live tier is content-addressed, the config tier is not, and keying
    /// a brief on `live.version` would refetch it every time a score moved,
    /// which is the exact thing this must not do.
    private static let briefLife: TimeInterval = 120

    var briefWrittenAt: Date? { intelAt }

    @MainActor
    func loadIntel(force: Bool = false) async {
        guard !intelInFlight else { return }
        if !force, intel != nil, let at = intelAt,
           Date.now.timeIntervalSince(at) < Self.briefLife { return }
        guard let u = url("/api/intel") else { return }
        intelInFlight = true
        intelLoading = true
        defer { intelInFlight = false; intelLoading = false }
        do {
            let (d, resp) = try await URLSession.shared.data(from: u)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200 else {
                intelNote = code == 404
                    ? "This server has no /api/intel route. The insight engine "
                    + "runs on the Mac; update fantasy-edge there and it will "
                    + "appear."
                    : "The server answered \(code) for /api/intel."
                return
            }
            let fresh = try JSONDecoder().decode(IntelBrief.self, from: d)
            dropStaleNarration(against: fresh)
            intel = fresh
            // The brief folds the catalogue in, so the common case is one
            // request rather than two. `loadModels` stays for a server that
            // does not, and it is a no-op once this has run.
            if !fresh.models.isEmpty {
                aiProviders = fresh.models
                modelsLoaded = true
            }
            intelAt = .now
            intelNote = nil
        } catch {
            intelNote = "Cannot reach \(host). \(error.localizedDescription)"
        }
    }

    /// Which providers the server holds a key for. Booleans; the route has no
    /// field that could carry a key back out, and this app never asks for one
    /// - a key typed into a headset would have to live somewhere, and the only
    /// somewhere on this platform that is not a mistake is the Keychain. The
    /// server already has the credential posture for this, so it keeps it.
    @MainActor
    func loadModels() async {
        guard !modelsLoaded, let u = url("/api/intel/models") else { return }
        modelsLoaded = true
        guard let (d, resp) = try? await URLSession.shared.data(from: u),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let p = try? JSONDecoder().decode(ModelsPayload.self, from: d)
        else { return }
        aiProviders = p.providers
    }

    // MARK: the model-written half

    var narration: IntelNarration?
    /// The state of the narrator when there is no prose: unsupported, switched
    /// off, still downloading, or a server that would not verify the text.
    /// Plain language, never a dialog - the computed brief is complete.
    var narrationNote: String?
    var narrationRunning = false
    /// Whether the prose on screen cost an inference just now, or is the one
    /// already written for these same facts. The reader is entitled to know
    /// which, because one of them spent their battery and the other did not.
    var narrationFresh = false
    var narrationAt: Date?
    @ObservationIgnored private var narratedFrom = ""

    /// True when asking again would reuse rather than run.
    var narrationCurrent: Bool {
        narration != nil && !narratedFrom.isEmpty
            && narratedFrom == (intel?.narrationKey ?? "")
    }

    /// Entering the tab and finding prose already written is a reuse, whatever
    /// it was when it was made. Called from the view's task, never from a body.
    @MainActor
    func noteNarrationSeen() { if narration != nil { narrationFresh = false } }

    /// Prose written for facts that have since moved is dropped rather than
    /// dimmed. Model sentences sitting above numbers they no longer describe
    /// is the one failure this whole view is arranged to prevent, and there is
    /// no styling that makes it safe.
    @MainActor
    private func dropStaleNarration(against fresh: IntelBrief) {
        guard narration != nil, narratedFrom != fresh.narrationKey else { return }
        narration = nil
        narrationAt = nil
        narratedFrom = ""
        narrationNote = "The findings changed, so the summary written for the "
            + "old ones was dropped. Ask again to have these written up."
    }

    /// Write the brief up on device, then hand the text to the server to check.
    ///
    /// Explicit only. Never called from `start()`, never from a body, and it
    /// returns without touching the model when a narration for these exact
    /// findings already exists.
    @MainActor
    func narrate(force: Bool = false) async {
        guard !narrationRunning, let brief = intel else { return }
        if !force, narrationCurrent {
            narrationFresh = false             // reused: nothing was run
            return
        }
        guard let prompt = brief.promptable else {
            narrationNote = "The server sent no prompt block with this brief, "
                + "so there is nothing a model is allowed to see. Building one "
                + "here from the raw payload is the thing that must not happen."
            return
        }
        let ready = AppleIntelligence.readiness
        guard ready.usable else {
            narration = nil
            narrationNote = ready.line
            return
        }
        narrationRunning = true
        defer { narrationRunning = false }
        let written: String
        do {
            written = try await AppleIntelligence.write(system: prompt.system,
                                                        user: prompt.user)
        } catch {
            narrationNote = error.localizedDescription
            return
        }
        await submit(written, for: brief)
    }

    /// Post the text to `/api/intel/narrate` and render what comes back.
    ///
    /// Deliberately not what was sent. Only the server's copy has been through
    /// `verify_numbers` and `mentions_unavailable`, so only the server's copy
    /// carries `unverified`, `flaggedMetrics` and `trustworthy`. Text this side
    /// has checked nothing about is prose with no provenance, which is exactly
    /// what the rest of this view exists to be distinguishable from - so when
    /// the route is missing or refuses, nothing is shown and the reason is.
    @MainActor
    private func submit(_ text: String, for brief: IntelBrief) async {
        guard let u = url("/api/intel/narrate") else { return }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(
            withJSONObject: ["provider": "apple", "text": text])
        do {
            let (d, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200 else {
                narrationNote = note(for: code)
                return
            }
            narration = try JSONDecoder().decode(NarrateReply.self, from: d).narration
            narratedFrom = brief.narrationKey
            narrationAt = .now
            narrationFresh = true
            narrationNote = nil
        } catch {
            narrationNote = "The summary was written on this device but could "
                + "not be sent to \(host) to be checked, so it is not shown. "
                + error.localizedDescription
        }
    }

    private func note(for code: Int) -> String {
        switch code {
        case 403:
            return "The summary was written on this device, but "
                 + "/api/intel/narrate only answers on loopback, so it could "
                 + "not be checked and is not shown. Everything below is "
                 + "computed and needs no model."
        case 404:
            return "The summary was written on this device, but this server "
                 + "has no /api/intel/narrate route to check it against, so it "
                 + "is not shown. Only the server's copy carries the "
                 + "number-verification flags."
        default:
            return "The summary was written on this device, but the server "
                 + "answered \(code) when asked to check it, so it is not "
                 + "shown."
        }
    }

    func start() {
        poll?.cancel()
        poll = Task { [weak self] in
            await self?.load()
            while !Task.isCancelled {
                await self?.refreshLive()
                try? await Task.sleep(for: Board.beat())
            }
        }
    }
    func stop() { poll?.cancel(); poll = nil }
}
