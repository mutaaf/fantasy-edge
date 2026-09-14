import Foundation
import Observation

/// The one network client. It fetches, decodes and keeps the last good slate;
/// it decides nothing about football.
///
/// The poll is reference-counted rather than tied to a view's lifetime: on
/// visionOS opening a space can dismiss the window whose `onDisappear` would
/// otherwise cancel the only poll (a bug fantasy-edge shipped and fixed).
@MainActor
@Observable
final class SaturdayStore {
    private(set) var slate: Slate?
    private(set) var error: String?
    private(set) var updatedAt: Date?
    private(set) var host: String
    private(set) var favorites: Set<String>

    @ObservationIgnored private var watchers = 0
    @ObservationIgnored private var poll: Task<Void, Never>?
    @ObservationIgnored private var inFlight = false
    @ObservationIgnored private var byID: [String: Game] = [:]

    static let hostKey = "saturday.host"
    static let favoritesKey = "saturday.favorites"
    static let interval: Duration = .seconds(25)

    init() {
        host = UserDefaults.standard.string(forKey: Self.hostKey) ?? "127.0.0.1:8780"
        favorites = Set(UserDefaults.standard.stringArray(forKey: Self.favoritesKey) ?? [])
    }

    func setHost(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        host = trimmed
        UserDefaults.standard.set(trimmed, forKey: Self.hostKey)
        Task { await refresh() }
    }

    func toggleFavorite(_ teamID: String) {
        if favorites.contains(teamID) { favorites.remove(teamID) } else { favorites.insert(teamID) }
        UserDefaults.standard.set(Array(favorites).sorted(), forKey: Self.favoritesKey)
    }

    func game(_ id: String) -> Game? { byID[id] }

    func games(in section: WallSection) -> [Game] { section.games.compactMap { byID[$0] } }

    // MARK: polling

    func watch() {
        watchers += 1
        guard poll == nil else { return }
        poll = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: Self.interval)
            }
        }
    }

    func unwatch() {
        watchers = max(0, watchers - 1)
        if watchers == 0 {
            poll?.cancel()
            poll = nil
        }
    }

    func refresh() async {
        guard !inFlight else { return }
        inFlight = true
        defer { inFlight = false }
        do {
            let next: Slate = try await get("/api/slate")
            slate = next
            byID = Dictionary(next.games.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
            updatedAt = Date()
            error = nil
        } catch {
            // Keep the last good slate on screen; say what failed beside it.
            self.error = Self.describe(error, host: host)
        }
    }

    func detail(_ id: String) async throws -> GameDetail {
        try await get("/api/game/\(id)")
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: "http://\(host)\(path)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url, timeoutInterval: 12)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw APIError.status(http.statusCode)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    enum APIError: Error { case status(Int) }

    static func describe(_ error: Error, host: String) -> String {
        switch error {
        case APIError.status(let code): return "The API at \(host) answered \(code)."
        case is DecodingError: return "The API at \(host) sent a slate this app cannot read. Is it a Saturday API?"
        case let url as URLError where url.code == .cannotConnectToHost || url.code == .timedOut:
            return "Nothing is answering at \(host). Start it with `make serve`, or set the host in Settings."
        default: return error.localizedDescription
        }
    }
}
