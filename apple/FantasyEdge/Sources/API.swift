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
