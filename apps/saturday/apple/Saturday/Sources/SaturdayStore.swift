import Foundation
import Observation

/// The one network client. It fetches, decodes and keeps the last good slate;
/// it decides nothing about football.
///
/// Live, it holds one server-sent event stream (`/api/stream`) naming the
/// games that are open, so the API fetches summaries only for those. On a
/// replay the position is view state, like a filter: paused, the store reads
/// the frame it is parked on with `?at=`; playing, it streams from that frame
/// at the chosen speed and follows the stream's clock.
///
/// Watching is reference-counted rather than tied to a view's lifetime: on
/// visionOS opening a space can dismiss the window whose `onDisappear` would
/// otherwise cancel the only connection (a bug fantasy-edge shipped and fixed).
@MainActor
@Observable
final class SaturdayStore {
    private(set) var slate: Slate?
    private(set) var timeline: ReplayTimeline?
    private(set) var details: [String: GameDetail] = [:]
    private(set) var detailErrors: [String: String] = [:]
    private(set) var error: String?
    private(set) var updatedAt: Date?
    private(set) var host: String
    private(set) var favorites: Set<String>
    private(set) var playing = false
    private(set) var speed: Double = 30
    private(set) var connection: Connection = .idle

    enum Connection: Equatable { case idle, streaming, polling }

    @ObservationIgnored private var watchers = 0
    @ObservationIgnored private var worker: Task<Void, Never>?
    @ObservationIgnored private var byID: [String: Game] = [:]
    @ObservationIgnored private var open: [String: Int] = [:]
    @ObservationIgnored private var claimed: Set<String> = []
    @ObservationIgnored private var seeded = false
    /// The frame a replay is parked on or playing from; nil means the source's own.
    @ObservationIgnored private var position: String?

    static let hostKey = "saturday.host"
    static let favoritesKey = "saturday.favorites"
    static let pollInterval: Duration = .seconds(20)
    static let speeds: [Double] = [1, 10, 30, 60]

    init() {
        let defaults = UserDefaults.standard
        host = defaults.string(forKey: Self.hostKey) ?? "127.0.0.1:8780"
        favorites = Set(defaults.stringArray(forKey: Self.favoritesKey) ?? [])
        // Screenshot hooks: `-replayAt <stamp>` parks a replay on a frame,
        // `-replayPlay YES` starts it playing, `-replaySpeed 60` sets the speed.
        position = defaults.string(forKey: "replayAt")
        if defaults.object(forKey: "replaySpeed") != nil { speed = max(1, defaults.double(forKey: "replaySpeed")) }
        playing = defaults.bool(forKey: "replayPlay")
    }

    // MARK: settings

    func setHost(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        host = trimmed
        UserDefaults.standard.set(trimmed, forKey: Self.hostKey)
        timeline = nil
        restart()
    }

    func toggleFavorite(_ teamID: String) {
        if favorites.contains(teamID) { favorites.remove(teamID) } else { favorites.insert(teamID) }
        UserDefaults.standard.set(Array(favorites).sorted(), forKey: Self.favoritesKey)
    }

    // MARK: reading

    func game(_ id: String) -> Game? { byID[id] }

    func games(in section: WallSection) -> [Game] { section.games.compactMap { byID[$0] } }

    /// This frame's changes to one game, most important first (the API's order).
    func changes(for gameID: String) -> [Change] { slate?.changes.filter { $0.game == gameID } ?? [] }

    /// True the first time a change is claimed, so a flourish plays once
    /// however often the tile showing it is rebuilt.
    func claim(_ change: Change) -> Bool { claimed.insert(change.id).inserted }

    var isReplay: Bool { slate?.clock != nil }

    // MARK: watching

    func watch() {
        watchers += 1
        if worker == nil { restart() }
    }

    func unwatch() {
        watchers = max(0, watchers - 1)
        if watchers == 0 {
            worker?.cancel()
            worker = nil
            connection = .idle
        }
    }

    /// A game view is on screen: its summary is now worth fetching.
    func openGame(_ id: String) {
        open[id, default: 0] += 1
        if open[id] == 1 { restart() }
    }

    func closeGame(_ id: String) {
        guard let n = open[id] else { return }
        if n <= 1 { open[id] = nil; restart() } else { open[id] = n - 1 }
    }

    // MARK: replay controls

    func play() {
        guard isReplay else { return }
        if let clock = slate?.clock, clock.index == clock.frames - 1 { position = timeline?.frames.first?.stamp }
        playing = true
        restart()
    }

    func pause() {
        playing = false
        restart()
    }

    func setSpeed(_ value: Double) {
        speed = value
        if playing { restart() }
    }

    /// Park on a frame. Scrubbing always pauses; the user picked a moment.
    func seek(to stamp: String) {
        guard stamp != slate?.clock?.stamp else { return }
        position = stamp
        playing = false
        restart()
    }

    func refresh() async {
        await readOnce()
    }

    // MARK: the connection

    private func restart() {
        worker?.cancel()
        guard watchers > 0 else { worker = nil; return }
        worker = Task { [weak self] in await self?.run() }
    }

    private var openIDs: [String] { open.keys.sorted() }

    private func run() async {
        await readOnce()
        if isReplay {
            if timeline == nil { timeline = try? await get("/api/replay") }
            guard playing else { connection = .idle; return }
        }
        var failures = 0
        while !Task.isCancelled {
            do {
                try await stream()
                if isReplay { playing = false; connection = .idle; return }   // the night ended
                failures = 0
            } catch is CancellationError {
                return
            } catch {
                if Task.isCancelled { return }
                failures += 1
                // A proxy or an old API without /api/stream: poll instead, and
                // try the stream again later.
                connection = .polling
                self.error = failures > 2 ? Self.describe(error, host: host) : nil
                await readOnce()
                try? await Task.sleep(for: Self.pollInterval)
            }
        }
    }

    /// The moment everything else should be asked about: the frame a replay is
    /// parked on, or nothing at all when the source is live. Anything that
    /// polls the API on its own - the red-zone channel does - has to ask about
    /// the same moment, or the bowl and the wall are in different halves of
    /// the night.
    var moment: String? {
        isReplay || position != nil ? (position ?? slate?.clock?.stamp) : nil
    }

    private func readOnce() async {
        let at = moment
        do {
            let next: Slate = try await get("/api/slate", at: at)
            apply(next)
            error = nil
        } catch is CancellationError {
            return
        } catch {
            // Keep the last good slate on screen; say what failed beside it.
            self.error = Self.describe(error, host: host)
        }
        for id in openIDs {
            do {
                let d: GameDetail = try await get("/api/game/\(id)", at: at)
                details[id] = d
                detailErrors[id] = nil
            } catch is CancellationError {
                return
            } catch {
                detailErrors[id] = Self.describe(error, host: host)
            }
        }
    }

    private func stream() async throws {
        var parts = URLComponents()
        parts.scheme = "http"
        let hostParts = host.split(separator: ":", maxSplits: 1)
        parts.host = String(hostParts.first ?? "127.0.0.1")
        if hostParts.count == 2 { parts.port = Int(hostParts[1]) }
        parts.path = "/api/stream"
        var query: [URLQueryItem] = []
        if !openIDs.isEmpty { query.append(URLQueryItem(name: "games", value: openIDs.joined(separator: ","))) }
        if isReplay {
            if let at = position ?? slate?.clock?.stamp { query.append(URLQueryItem(name: "at", value: at)) }
            query.append(URLQueryItem(name: "speed", value: String(speed)))
        }
        parts.queryItems = query.isEmpty ? nil : query
        guard let url = parts.url else { throw URLError(.badURL) }

        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 90
        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 { throw APIError.status(http.statusCode) }
        connection = .streaming
        var event = "message"
        for try await line in bytes.lines {
            try Task.checkCancellation()
            if line.hasPrefix("event: ") {
                event = String(line.dropFirst(7))
            } else if line.hasPrefix("data: ") {
                handle(event, Data(line.dropFirst(6).utf8))
                event = "message"
            }
        }
    }

    private func handle(_ event: String, _ data: Data) {
        let decoder = JSONDecoder()
        switch event {
        case "slate":
            if let next = try? decoder.decode(Slate.self, from: data) {
                apply(next)
                error = nil
            }
        case "game":
            if let d = try? decoder.decode(GameDetail.self, from: data), open[d.event] != nil {
                details[d.event] = d
                detailErrors[d.event] = nil
            }
        case "clock":
            if let frame = try? decoder.decode(ReplayFrame.self, from: data) { position = frame.stamp }
        default:
            break   // ping, budget, end
        }
    }

    private func apply(_ next: Slate) {
        // The changes on the first board anyone sees happened before they
        // arrived; flourishing them all at once would be noise, not news.
        if !seeded {
            seeded = true
            claimed.formUnion(next.changes.map(\.id))
        }
        slate = next
        byID = Dictionary(next.games.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        if let clock = next.clock { position = clock.stamp }
        updatedAt = Date()
    }

    private func get<T: Decodable>(_ path: String, at: String? = nil) async throws -> T {
        var text = "http://\(host)\(path)"
        if let at { text += "?at=\(at)" }
        guard let url = URL(string: text) else { throw URLError(.badURL) }
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
        case APIError.status(404): return "The API at \(host) has nothing for this game at this moment."
        case APIError.status(let code): return "The API at \(host) answered \(code)."
        case is DecodingError: return "The API at \(host) sent a payload this app cannot read. Is it a Saturday API of this version?"
        case let url as URLError where url.code == .cannotConnectToHost || url.code == .timedOut:
            return "Nothing is answering at \(host). Start it with `make replay`, or set the host in Settings."
        default: return error.localizedDescription
        }
    }
}
