import Foundation
import Observation

/// The red-zone channel: which live game the stadium is showing, and why.
///
/// The ranking is not here. `/api/redzone` decides it, in whichever code of
/// football the server is serving - `fantasyedge/whip.py` scores a Sunday on
/// proximity, down, consequence and aftermath; `cfb/leverage.py` scores a
/// Saturday on closeness, the clock, the AP poll and an upset in the making -
/// and both hold the choice steady with the same hysteresis, so two drives in
/// the red zone at once do not trade the bowl every poll. This asks for that
/// answer and follows it.
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
        /// Where the polls had this club, when the code of football has polls.
        public let rank: Int?

        /// "#16 SMU" on a Saturday, "SMU" without a poll behind it, and always
        /// "DAL" on a Sunday.
        public var badge: String { rank.map { "#\($0) \(abbr)" } ?? abbr }
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
        /// What happened last, as the server cleaned it. Empty where the feed
        /// has not said.
        public let lastPlay: String?
        /// Whether the bowl can be stood in for this game from this source:
        /// "available", "afterFinal", or "unavailable". Absent from a server
        /// that can always answer, which is the same as available.
        public let detail: String?

        /// Whether walking into this game would land somewhere. A recorded
        /// night that sampled its snapshots has games it can list and cannot
        /// draw, and offering one of those opens onto a black stadium.
        public var openable: Bool { (detail ?? "available") == "available" }
        public var id: String { event }
        public var live: Bool { state == "in" }
        public var line: String { "\(away.badge) @ \(home.badge)" }
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

    /// What the server says when the slate it is serving was rebuilt from
    /// play timestamps rather than watched. Absent on a live Sunday.
    public struct Day: Decodable {
        public let date: String
        public let label: String
        public let provenance: String
        public let caveats: [String]
    }

    struct Payload: Decodable {
        let league: String
        let focus: String
        let counts: Counts
        let games: [Game]
        let error: String?
        let day: Day?
    }

    public private(set) var games: [Game] = []
    public private(set) var counts = Counts(live: 0, total: 0, final: 0, redZone: 0)
    public private(set) var league = ""
    /// Set when the slate is a rebuilt day. The panel must say so: a wearer
    /// sitting in the stadium has no other way to tell a Sunday being played
    /// back from one happening now, and letting them assume is the one thing
    /// a reconstruction must never do.
    public private(set) var day: Day?
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
    @ObservationIgnored private var query: () -> String
    @ObservationIgnored private var poll: Task<Void, Never>?
    @ObservationIgnored private var watchers = 0

    /// `query` is appended to the request, for a server being replayed at a
    /// moment ("?at=..."). It is asked each poll rather than captured, because
    /// a wearer scrubbing a recorded night moves it under us.
    public init(base: @escaping () -> String, query: @escaping () -> String = { "" }) {
        self.base = base
        self.query = query
    }

    /// Ask about this moment from now on. A replayed night is served frame by
    /// frame, and a channel asking about "now" while the wall is parked on
    /// 11:42 PM would put the bowl in a different half of the evening from
    /// everything else on screen.
    public func ask(at moment: @escaping () -> String?) {
        query = { moment().map { "?at=\($0)" } ?? "" }
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
        guard let url = URL(string: base() + "/api/redzone" + query()) else { return }
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
            day = fresh.day
            focus = fresh.focus
            error = fresh.error
        } catch is CancellationError {
        } catch {
            self.error = "Could not reach the channel: \(error.localizedDescription)"
        }
    }
}
