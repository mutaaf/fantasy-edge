import Foundation
import Observation

/// Where a scene comes from, and the remote control for a replay.
///
/// Generic on purpose: a base URL and a path. The tabletop and the stadium
/// both read one feed, so opening the stadium from the tabletop hands over the
/// same scene rather than starting a second poll.
///
/// Watchers are counted, for the reason the board's own poll is: opening the
/// stadium dismisses nothing, but closing the tabletop window while the
/// stadium is open fires `onDisappear` *after* the space's `task`, and an
/// unconditional stop would freeze the stadium at the moment you walked in.
@MainActor
@Observable
public final class SceneFeed {
    public enum Target: Equatable, Sendable {
        case live(event: String)
        case replay
    }

    public private(set) var spec: SceneSpec?
    public private(set) var replay: ReplayState?
    public private(set) var lastWeek: LastWeek?
    public private(set) var markers: ReplayMarkers?
    public private(set) var error: String?
    public var target: Target? {
        didSet { if target != oldValue { spec = nil; error = nil; restart() } }
    }

    @ObservationIgnored private let base: () -> String
    @ObservationIgnored private var poll: Task<Void, Never>?
    @ObservationIgnored private var watchers = 0

    /// `base` is read on every request, so a changed host takes effect on the
    /// next poll without rebuilding the feed.
    public init(base: @escaping () -> String) {
        self.base = base
    }

    private var interval: Duration {
        // A replay moves at up to 300x; a live game's scene changes a few times
        // a minute. The live tier caches for two seconds either way.
        target == .replay ? .milliseconds(700) : .seconds(3)
    }

    public func start() {
        watchers += 1
        restart(onlyIfIdle: true)
    }

    public func stop() {
        watchers = max(0, watchers - 1)
        guard watchers == 0 else { return }
        poll?.cancel()
        poll = nil
    }

    private func restart(onlyIfIdle: Bool = false) {
        if onlyIfIdle && poll != nil { return }
        poll?.cancel()
        poll = nil
        guard watchers > 0, target != nil else { return }
        poll = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                guard let wait = self?.interval else { return }
                try? await Task.sleep(for: wait)
            }
        }
    }

    private func path(for target: Target) -> String {
        switch target {
        case .live(let event): return "/api/scene/\(event)"
        case .replay: return "/api/replay/scene"
        }
    }

    public func refresh() async {
        guard let target, let url = URL(string: base() + path(for: target)) else { return }
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await URLSession.shared.data(for: request)
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200 else {
                error = Self.failure(data) ?? "The scene is unavailable (\(code))."
                return
            }
            let fresh = try JSONDecoder().decode(SceneSpec.self, from: data)
            if fresh != spec { spec = fresh }
            if let control = fresh.replayControl, control != replay { replay = control }
            error = nil
        } catch is CancellationError {
        } catch {
            self.error = "Could not read the scene: \(error.localizedDescription)"
        }
    }

    // MARK: replay controls

    public func loadGames() async {
        guard let url = URL(string: base() + "/api/replay") else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: url),
              let state = try? JSONDecoder().decode(ReplayState.self, from: data) else { return }
        replay = state
    }

    /// POST one action. The server refuses a remote caller unless
    /// FANTASYEDGE_ALLOW_REMOTE_REPLAY is set, and says so; that message is
    /// shown as it is rather than as a generic failure.
    public func control(_ body: [String: Any]) async {
        guard let url = URL(string: base() + "/api/replay") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            if code == 200, let state = try? JSONDecoder().decode(ReplayState.self, from: data) {
                replay = state
                error = nil
                if target == .replay { await refresh() }
            } else {
                error = Self.failure(data) ?? "The replay refused that (\(code))."
            }
        } catch {
            self.error = "Could not reach the replay: \(error.localizedDescription)"
        }
    }

    /// Last week's slate. `spoilers` is the viewer's choice, not a default:
    /// the picker opens with scores hidden and asks the server again when it
    /// is turned on, so a hidden row never holds a score the UI is trusted to
    /// keep off screen.
    public func loadLastWeek(spoilers: Bool = false) async {
        let query = spoilers ? "?spoilers=1" : ""
        guard let url = URL(string: base() + "/api/lastweek" + query) else { return }
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200 else {
                error = Self.failure(data) ?? "The week could not be read (\(code))."
                return
            }
            lastWeek = try JSONDecoder().decode(LastWeek.self, from: data)
            error = nil
        } catch {
            self.error = "Could not reach the week: \(error.localizedDescription)"
        }
    }

    /// The loaded replay's scores and drives, for skipping and jumping.
    public func loadMarkers() async {
        guard let url = URL(string: base() + "/api/replay/markers") else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: url),
              let marks = try? JSONDecoder().decode(ReplayMarkers.self, from: data)
        else { return }
        markers = marks
    }

    public func load(_ event: String) async {
        await control(["action": "load", "event": event])
        target = .replay
        await loadMarkers()
    }
    public func nextScore() async { await control(["action": "next"]) }
    public func previousScore() async { await control(["action": "previous"]) }
    public func play() async { await control(["action": "play"]) }
    public func pause() async { await control(["action": "pause"]) }
    public func seek(_ seconds: Int) async { await control(["action": "seek", "at": seconds]) }
    public func setSpeed(_ speed: Double) async { await control(["action": "speed", "speed": speed]) }

    private static func failure(_ data: Data) -> String? {
        struct Failure: Decodable { let error: String?; let fix: String? }
        guard let f = try? JSONDecoder().decode(Failure.self, from: data), let e = f.error else { return nil }
        return [e, f.fix].compactMap { $0 }.joined(separator: " ")
    }
}
