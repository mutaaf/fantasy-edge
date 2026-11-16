import Foundation

/// Usage events (1.0.1, the owner's call 2026-11-16, "update the native apps
/// too"; Box Office rule 6), sent to Box Office's first-party relay the way
/// Cold Gas's iPhone app does. This is the pure half; `Usage.swift` in the app
/// only moves the bytes it makes, and nothing else in the app names an event.
///
/// The rules are the privacy label's: props are numbers and enums only (never
/// a league, team, player, address or anything typed); the one id is a random
/// install id made on this device, which a reinstall or the switch in "Where is
/// the board?" resets; the queue is capped, oldest first, and a batch leaves
/// the queue only once the relay has taken it.
public enum Insights {
    /// `/boxoffice/e/*` forwards PostHog's capture API and admits an event only
    /// when its Referer is a general-audience page in Cast List. That page is
    /// this app's own (Cast List slug `fantasy-edge`).
    public static let endpoint = "https://mutaafaziz.com/boxoffice/e/batch/"
    public static let referer = "https://mutaaf.github.io/fantasy-edge/"
    /// PostHog's public ingest key, the one Box Office's loader serves to every
    /// page: write-only, made for clients.
    public static let token = "phc_pj2w4pWnPNUNK5hZK5TX35tNRFa9skJQrGmZNbHVHr9m"
    public static let QUEUE_CAP = 300
    public static let BATCH_MAX = 50

    public enum Prop: Equatable, Sendable {
        case number(ClosedRange<Double>)
        case oneOf([String])
    }
    /// The four places the app opens: the command centre window, the immersive
    /// board, the tabletop volume and the stadium. The scene ids, as names.
    public static let SPACES = ["board", "board_space", "tabletop", "stadium"]
    /// Every event the app may send and every prop it may carry. The web pages
    /// send no events of their own, so this is Cold Gas's `session_start` and
    /// one product-interaction count.
    public static let EVENTS: [String: [String: Prop]] = [
        "session_start": ["returning": .number(0...1), "days_since_last": .number(0...3650)],
        "space_open": ["space": .oneOf(SPACES)],
    ]
    /// The props every event carries, as Box Office's loader registers them.
    public static func base(release: String) -> [String: Value] {
        ["app": .text("fantasy-edge"), "surface": .text("app"), "platform": .text("visionos"),
         "audience": .text("general"), "site": .text("mutaaf.github.io"), "release": .text(release)]
    }

    public enum Value: Codable, Equatable, Sendable {
        case num(Double), text(String)
        public init(from d: Decoder) throws {
            let c = try d.singleValueContainer()
            if let v = try? c.decode(Double.self) { self = .num(v) } else { self = .text(try c.decode(String.self)) }
        }
        public func encode(to e: Encoder) throws {
            var c = e.singleValueContainer()
            switch self { case let .num(v): try c.encode(v); case let .text(s): try c.encode(s) }
        }
        var any: Any { switch self { case let .num(v): return v; case let .text(s): return s } }
    }

    /// The event if it is in the vocabulary, with only its known props, each in
    /// range or one of its values; nil for an unknown name. A prop that breaks
    /// its rule is dropped, never sent.
    public static func clean(_ name: String, _ props: [String: Value]) -> [String: Value]? {
        guard let spec = EVENTS[name] else { return nil }
        var out: [String: Value] = [:]
        for (k, v) in props {
            guard let rule = spec[k] else { continue }
            switch (rule, v) {
            case let (.number(r), .num(x)) where x.isFinite && r.contains(x): out[k] = .num(x)
            case let (.oneOf(vals), .text(s)) where vals.contains(s): out[k] = .text(s)
            default: continue
            }
        }
        return out
    }

    public struct Event: Codable, Equatable, Sendable {
        public var name: String
        public var props: [String: Value]
        /// Milliseconds since 1970, by the device clock.
        public var at: Double
        public init(name: String, props: [String: Value], at: Double) { self.name = name; self.props = props; self.at = at }
    }

    /// The queue as it sits in UserDefaults. A value: the app keeps one, saves
    /// it, and hands the sender a batch to try.
    public struct Queue: Codable, Equatable, Sendable {
        public var events: [Event] = []
        /// A random UUID made the first time an event is kept; nil once cleared.
        public var installId: String?
        public init() {}
        enum CodingKeys: String, CodingKey { case events, installId }
        public init(from d: Decoder) throws {
            let c = try d.container(keyedBy: CodingKeys.self)
            events = (try? c.decodeIfPresent([Event].self, forKey: .events)).flatMap { $0 } ?? []
            installId = (try? c.decodeIfPresent(String.self, forKey: .installId)).flatMap { $0 }
            if events.count > QUEUE_CAP { events.removeFirst(events.count - QUEUE_CAP) }
        }

        /// Keep an event, checked against the vocabulary. Off keeps nothing.
        @discardableResult
        public mutating func add(_ name: String, _ props: [String: Value] = [:], at: Double, on: Bool) -> Bool {
            guard on, let p = Insights.clean(name, props) else { return false }
            if installId == nil { installId = UUID().uuidString.lowercased() }
            events.append(Event(name: name, props: p, at: at))
            if events.count > QUEUE_CAP { events.removeFirst(events.count - QUEUE_CAP) }
            return true
        }
        /// The oldest events, at most BATCH_MAX; nothing when off.
        public func next(on: Bool) -> [Event] {
            guard on, installId != nil else { return [] }
            return Array(events.prefix(BATCH_MAX))
        }
        /// The relay took these. By value, so what arrived meanwhile stays.
        public mutating func sent(_ batch: [Event]) {
            var drop = batch.count
            events.removeAll { e in
                guard drop > 0, batch.contains(e) else { return false }
                drop -= 1; return true
            }
        }
        /// The switch turned off: nothing kept, and the id gone. Turning it on
        /// again makes a new one.
        public mutating func clear() { events.removeAll(); installId = nil }

        public static func decode(_ data: Data?) -> Queue {
            guard let data, let q = try? JSONDecoder().decode(Queue.self, from: data) else { return Queue() }
            return q
        }
        public func encoded() -> Data? { try? JSONEncoder().encode(self) }
    }

    /// The body of one POST, in PostHog's `/batch/` shape. `$geoip_disable`:
    /// no location is derived (the label declares none).
    public static func body(_ batch: [Event], installId: String, release: String) -> Data? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let shared = base(release: release)
        let items: [[String: Any]] = batch.map { e in
            var p: [String: Any] = ["distinct_id": installId, "$lib": "fantasyedge-visionos", "$geoip_disable": true]
            for (k, v) in shared { p[k] = v.any }
            for (k, v) in e.props { p[k] = v.any }
            return ["event": e.name, "properties": p, "timestamp": iso.string(from: Date(timeIntervalSince1970: e.at / 1000))]
        }
        return try? JSONSerialization.data(withJSONObject: ["api_key": token, "batch": items], options: [.sortedKeys])
    }

    /// Days since 1970, UTC.
    public static func day(_ ms: Double) -> Int { Int((ms / 86_400_000).rounded(.down)) }

    /// The visit counters `session_start` reads. Local only: nothing here is
    /// sent except as that event's two numbers.
    public struct Visits: Codable, Equatable, Sendable {
        public var sessions = 0
        public var lastDay: Int?
        public init() {}
        public static func decode(_ data: Data?) -> Visits {
            guard let data, let v = try? JSONDecoder().decode(Visits.self, from: data) else { return Visits() }
            return v
        }
        public func encoded() -> Data? { try? JSONEncoder().encode(self) }
        public mutating func start(at ms: Double) -> [String: Value] {
            let today = Insights.day(ms)
            let before = sessions
            let since = lastDay.map { max(0, today - $0) } ?? 0
            sessions = before + 1; lastDay = today
            return ["returning": .num(before > 0 ? 1 : 0), "days_since_last": .num(Double(min(3650, since)))]
        }
    }

    /// The switch, as stored: absent means on (the default), so an install
    /// from before the switch existed sends unless somebody turns it off.
    public static let switchKey = "fe.usage"
    public static func isOn(stored: Any?) -> Bool { (stored as? Bool) ?? true }
}
