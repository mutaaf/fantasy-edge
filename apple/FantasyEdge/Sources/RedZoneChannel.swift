import Foundation
import Observation

/// The red-zone channel: which live game the stadium is showing, and why.
///
/// The ranking is not here. `/api/redzone` decides it - `fantasyedge/whip.py`
/// scores every game on proximity, down, consequence and aftermath, and holds
/// the choice steady with hysteresis so two drives in the red zone at once do
/// not trade the screen every poll. This asks for that answer and follows it.
///
/// Three reasons the decision stays on the server rather than being ported:
/// the arithmetic exists once, in the language the recording harness can test
/// it in; the score-hold needs to remember the previous poll, which a
/// stateless client cannot; and two headsets in the same room see the same
/// game, which is the difference between a channel and sixteen private ones.
///
/// What *is* here is the part that is about this wearer: whether they have
/// pinned a game, and moving the bowl from one game to the next without
/// yanking it out from under them.
@MainActor
@Observable
public final class RedZoneChannel {
    public struct Side: Decodable, Equatable, Sendable {
        public let abbr: String
        public let score: Double
        public let color: String
        public let hasBall: Bool
    }

    public struct Game: Decodable, Equatable, Sendable, Identifiable {
        public let event: String
        public let state: String
        public let label: String
        public let kickoff: String
        public let league: String
        public let situation: String
        public let redZone: Bool
        public let urgency: Double
        public let reason: String
        public let home: Side
        public let away: Side
        public var id: String { event }
        public var live: Bool { state == "in" }
        public var line: String { "\(away.abbr) @ \(home.abbr)" }
        public var score: String { "\(Int(away.score))–\(Int(home.score))" }

        /// Kickoff as a clock time in the wearer's own zone. ESPN sends an
        /// instant ("2026-09-20T17:00Z"), which is the right thing to send and
        /// the wrong thing to show: a row of those reads as machine output.
        public var kickoffShort: String {
            guard let at = ISO8601DateFormatter().date(from: kickoff) else { return kickoff }
            let f = DateFormatter()
            f.dateFormat = "h:mm a"
            return f.string(from: at)
        }
    }

    public struct Counts: Decodable, Equatable, Sendable {
        public let live: Int
        public let total: Int
        public let final: Int
        public let redZone: Int
    }

    struct Payload: Decodable {
        let league: String
        let focus: String
        let counts: Counts
        let games: [Game]
        let error: String?
    }

    public private(set) var games: [Game] = []
    public private(set) var counts = Counts(live: 0, total: 0, final: 0, redZone: 0)
    public private(set) var league = ""
    public private(set) var error: String?
    /// The server's choice: the game the channel is on.
    public private(set) var focus = ""
    /// The wearer's choice, which outranks it. Nil means automatic.
    public private(set) var pinned: String?
    /// What the stadium is actually showing, once a changeover has completed.
    public private(set) var showing = ""

    /// Whether the channel is following the ball or holding where it was put.
    public var automatic: Bool { pinned == nil }

    /// The game the wearer should be looking at: their pin, or the channel's
    /// own choice. A pinned game that has finished releases the pin rather
    /// than stranding the wearer on a final.
    public var wanted: String {
        if let pinned, games.first(where: { $0.event == pinned })?.live == true { return pinned }
        return focus
    }

    public func game(_ event: String) -> Game? { games.first { $0.event == event } }

    /// Why the channel is on this game, in the words the caption shows.
    public var reason: String { game(showing)?.reason ?? "" }

    @ObservationIgnored private let base: () -> String
    @ObservationIgnored private var poll: Task<Void, Never>?
    @ObservationIgnored private var watchers = 0

    public init(base: @escaping () -> String) {
        self.base = base
    }

    /// The live tier caches for two seconds; asking faster buys nothing and
    /// costs a request per viewer.
    private static let interval = Duration.seconds(3)

    public func start() {
        watchers += 1
        guard poll == nil else { return }
        poll = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: Self.interval)
            }
        }
    }

    public func stop() {
        watchers = max(0, watchers - 1)
        guard watchers == 0 else { return }
        poll?.cancel()
        poll = nil
    }

    /// Hold this game until the wearer says otherwise. Pinning the game
    /// already on screen is how "stop moving" is expressed, so it is allowed
    /// and does nothing visible.
    public func pin(_ event: String) {
        pinned = event
    }

    /// Follow the ball again.
    public func auto() {
        pinned = nil
    }

    public func toggle(_ event: String) {
        if pinned == event { auto() } else { pin(event) }
    }

    /// The stadium has arrived at this game. Called once a changeover lands,
    /// so the caption and the pin control describe what is on screen rather
    /// than what is on its way.
    public func arrived(_ event: String) {
        showing = event
    }

    public func refresh() async {
        guard let url = URL(string: base() + "/api/redzone") else { return }
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                error = "The channel is unavailable."
                return
            }
            let fresh = try JSONDecoder().decode(Payload.self, from: data)
            games = fresh.games
            counts = fresh.counts
            league = fresh.league
            focus = fresh.focus
            error = fresh.error
        } catch is CancellationError {
        } catch {
            self.error = "Could not reach the channel: \(error.localizedDescription)"
        }
    }
}
