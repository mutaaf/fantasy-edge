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
    var leagues: [LeaguePayload] = []
    var live: LivePayload?
    var selected: String?
    var status: String = "Connecting…"
    var lastError: String?

    private var poll: Task<Void, Never>?

    init() {
        host = UserDefaults.standard.string(forKey: "fe.host") ?? "127.0.0.1:8770"
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
            live = try JSONDecoder().decode(LivePayload.self, from: data)
            lastError = nil
        } catch { lastError = error.localizedDescription }
    }

    /// Polling rather than SSE: the shared snapshot is cached for a couple of
    /// seconds at the edge anyway, so a poll costs a revalidation and keeps the
    /// client simple. Cancelled when the scene goes away.
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
