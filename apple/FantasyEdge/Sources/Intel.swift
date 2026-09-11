import Foundation

// The shapes `GET /api/intel` serves, and the grouping the view reads them
// through. Mirrors `intel.Brief.as_dict()` in the Python; nothing here is
// derived and nothing is filled in.
//
// Every field is decoded with a default rather than as a requirement. The
// three intel routes were still being written when this client was, so a
// brief arriving without `available`, or with a `narration` slot carrying
// only a prompt, has to render rather than throw - a decoding failure here
// would blank a tab whose whole content was otherwise present.

/// One fact's value. Python types it `Any` because a fact is as likely to be
/// "FINAL" or "OUT" as it is to be 15.6, so the decoder has to take either.
enum FactValue: Decodable, Hashable {
    case number(Double)
    case text(String)
    case flag(Bool)

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        // Bool before Double: JSON `true` decodes happily as 1 on some
        // platforms, and a fact reading "1 pts" where the server said "true"
        // is a wrong number rather than an ugly one.
        if let b = try? c.decode(Bool.self) { self = .flag(b) }
        else if let d = try? c.decode(Double.self) { self = .number(d) }
        else if let s = try? c.decode(String.self) { self = .text(s) }
        else { self = .text("") }
    }

    /// What to draw. A whole number loses its ".0" and nothing else changes:
    /// JSON gives no way to tell 62 from 62.0 once both are Doubles, so the
    /// alternative is the same figure printed two ways on one card.
    var display: String {
        switch self {
        case .flag(let b):   return b ? "yes" : "no"
        case .text(let s):   return s
        case .number(let d):
            if d == d.rounded() && abs(d) < 1e12 {
                return String(Int(d))
            }
            return d.formatted(.number.precision(.fractionLength(1)))
        }
    }
}

/// One number and the table or function it came from.
///
/// `source` is what makes an insight arguable rather than merely assertive -
/// `Fact.__post_init__` on the Python side refuses to construct one without
/// it - so it is drawn on every row rather than tucked behind a disclosure.
struct IntelFact: Decodable, Hashable, Identifiable {
    let label: String
    let value: FactValue
    let unit: String
    let source: String

    var id: String { label + "|" + source }
    var figure: String { unit.isEmpty ? value.display : "\(value.display) \(unit)" }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        label = (try? c.decode(String.self, forKey: .label)) ?? ""
        value = (try? c.decode(FactValue.self, forKey: .value)) ?? .text("")
        unit = (try? c.decode(String.self, forKey: .unit)) ?? ""
        source = (try? c.decode(String.self, forKey: .source)) ?? ""
    }
    private enum K: String, CodingKey { case label, value, unit, source }
}

/// A player an insight is about. Ids so a card can open the hologram this app
/// already draws, rather than growing a second player view of its own.
struct IntelPlayerRef: Decodable, Hashable, Identifiable {
    let id: String, name: String, pos: String, team: String
}

/// One computed finding.
struct IntelInsight: Decodable, Identifiable, Hashable {
    let key: String
    let kind: String
    let title: String
    let detail: String
    /// Copied verbatim from the analysis that produced it. Never shortened,
    /// never re-worded and never behind a tap: `history_insights` copies the
    /// analysis's own caveat character for character precisely so a client
    /// cannot be the layer that loses the qualification, and a truncated
    /// caveat is a paraphrase with extra steps.
    let caveat: String
    /// Always "computed" on this route - it is a read-only property on the
    /// Python class, so no round trip through a dict can dress model prose as
    /// arithmetic. Kept and checked rather than assumed.
    let origin: String
    let sources: [String]
    let facts: [IntelFact]
    let league: String
    let leagueId: String
    let weight: Double
    let players: [IntelPlayerRef]

    var id: String { key }
    var computed: Bool { origin == "computed" }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        key = (try? c.decode(String.self, forKey: .key)) ?? UUID().uuidString
        kind = (try? c.decode(String.self, forKey: .kind)) ?? ""
        title = (try? c.decode(String.self, forKey: .title)) ?? ""
        detail = (try? c.decode(String.self, forKey: .detail)) ?? ""
        caveat = (try? c.decode(String.self, forKey: .caveat)) ?? ""
        origin = (try? c.decode(String.self, forKey: .origin)) ?? "computed"
        sources = (try? c.decode([String].self, forKey: .sources)) ?? []
        facts = (try? c.decode([IntelFact].self, forKey: .facts)) ?? []
        league = (try? c.decode(String.self, forKey: .league)) ?? ""
        leagueId = (try? c.decode(String.self, forKey: .leagueId)) ?? ""
        weight = (try? c.decode(Double.self, forKey: .weight)) ?? 0
        players = (try? c.decode([IntelPlayerRef].self, forKey: .players)) ?? []
    }
    private enum K: String, CodingKey {
        case key, kind, title, detail, caveat, origin, sources, facts
        case league, leagueId, weight, players
    }
}

/// A metric the design asks for that no feed within reach publishes, and why.
struct UnavailableMetric: Decodable, Hashable, Identifiable {
    let metric: String, reason: String
    var id: String { metric }
}

/// A metric nflverse does publish, named by the server so the client does not
/// keep its own list and drift from it.
struct AvailableMetric: Decodable, Hashable, Identifiable {
    let key: String, label: String, unit: String
    var id: String { key }
}

/// The system instruction and the user content a narrator is allowed to see.
///
/// Built by the server from the brief's own findings. The Swift side must not
/// assemble its own from rosters or scores: the guarantee that a narrator
/// cannot cite a number nobody computed rests entirely on it having been
/// shown only findings.
struct NarrationPrompt: Decodable, Hashable {
    let system: String, user: String
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        system = (try? c.decode(String.self, forKey: .system)) ?? ""
        user = (try? c.decode(String.self, forKey: .user)) ?? ""
    }
    private enum K: String, CodingKey { case system, user }
}

/// Why there is no prose, in the server's words. A missing key, a rate limit
/// and an unreachable host are ordinary states of this view rather than
/// errors, because the computed brief above is already complete.
struct NarrationError: Decodable, Hashable {
    let state: String, message: String, remedy: String
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        state = (try? c.decode(String.self, forKey: .state)) ?? "failed"
        message = (try? c.decode(String.self, forKey: .message)) ?? ""
        remedy = (try? c.decode(String.self, forKey: .remedy)) ?? ""
    }
    private enum K: String, CodingKey { case state, message, remedy }
}

/// Model-written prose about findings somebody else computed.
///
/// One type covers both places the key appears: the brief's slot, which
/// carries the prompt and the shape stamp, and the body
/// `POST /api/intel/narrate` returns, which carries the checked text. Only
/// the latter has `unverified` and `trustworthy`, which is exactly why this
/// client renders the server's copy rather than the text it sent - see
/// `Board.narrate`.
struct IntelNarration: Decodable, Hashable {
    let origin: String
    let text: String
    let provider: String
    let model: String
    let groundedIn: [String]
    let unverified: [String]
    let flaggedMetrics: [String]
    let trustworthy: Bool
    let label: String
    let error: NarrationError?
    let prompt: NarrationPrompt?
    /// The server's own content hash of the findings. Short, and it moves
    /// exactly when a number does, which makes it a better cache key for
    /// expensive prose than the prompt it was built from.
    let shape: String
    let chat: ChatSlot?

    var hasProse: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        origin = (try? c.decode(String.self, forKey: .origin)) ?? "model"
        text = (try? c.decode(String.self, forKey: .text)) ?? ""
        provider = (try? c.decode(String.self, forKey: .provider)) ?? ""
        model = (try? c.decode(String.self, forKey: .model)) ?? ""
        groundedIn = (try? c.decode([String].self, forKey: .groundedIn)) ?? []
        unverified = (try? c.decode([String].self, forKey: .unverified)) ?? []
        flaggedMetrics = (try? c.decode([String].self, forKey: .flaggedMetrics)) ?? []
        // Absent means "the server did not run its check", which is not the
        // same as "the check passed". Defaulting to false keeps the flag
        // meaning what it says.
        trustworthy = (try? c.decode(Bool.self, forKey: .trustworthy)) ?? false
        label = (try? c.decode(String.self, forKey: .label))
            ?? "Written by a model from the computed findings below. "
             + "Not itself a source."
        error = try? c.decode(NarrationError.self, forKey: .error)
        prompt = try? c.decode(NarrationPrompt.self, forKey: .prompt)
        shape = (try? c.decode(String.self, forKey: .shape)) ?? ""
        chat = try? c.decode(ChatSlot.self, forKey: .chat)
    }
    private enum K: String, CodingKey {
        case origin, text, provider, model, groundedIn, unverified
        case flaggedMetrics, trustworthy, label, error, prompt, shape, chat
    }
}

/// Whether there is a conversational endpoint. There is not, and the server
/// says so itself rather than this client asserting it - if one is ever added,
/// the note changes here rather than in a string on the headset.
struct ChatSlot: Decodable, Hashable {
    let available: Bool, note: String
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        available = (try? c.decode(Bool.self, forKey: .available)) ?? false
        note = (try? c.decode(String.self, forKey: .note)) ?? ""
    }
    private enum K: String, CodingKey { case available, note }
}

/// What `POST /api/intel/narrate` hands back. The route may return the
/// narration bare or under a key; both are accepted because this client was
/// written before the route was.
struct NarrateReply: Decodable {
    let narration: IntelNarration
    init(from decoder: Decoder) throws {
        if let c = try? decoder.container(keyedBy: K.self),
           let n = try? c.decode(IntelNarration.self, forKey: .narration) {
            narration = n
        } else {
            narration = try IntelNarration(from: decoder)
        }
    }
    private enum K: String, CodingKey { case narration }
}

/// Everything the Intel view shows.
struct IntelBrief: Decodable {
    let season: Int
    let week: Int
    let insights: [IntelInsight]
    let narration: IntelNarration?
    let unavailable: [UnavailableMetric]
    let available: [AvailableMetric]
    let notes: [String]
    /// The server folds the model catalogue into the brief, so the common
    /// case costs one request rather than two.
    let models: [ModelProvider]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: K.self)
        season = (try? c.decode(Int.self, forKey: .season)) ?? 0
        week = (try? c.decode(Int.self, forKey: .week)) ?? 0
        insights = (try? c.decode([IntelInsight].self, forKey: .insights)) ?? []
        narration = try? c.decode(IntelNarration.self, forKey: .narration)
        unavailable = (try? c.decode([UnavailableMetric].self, forKey: .unavailable)) ?? []
        available = (try? c.decode([AvailableMetric].self, forKey: .available)) ?? []
        notes = (try? c.decode([String].self, forKey: .notes)) ?? []
        models = (try? c.decode([ModelProvider].self, forKey: .models)) ?? []
    }
    private enum K: String, CodingKey {
        case season, week, insights, narration, unavailable, available
        case notes, models
    }

    /// What a narration is cached against.
    ///
    /// The server stamps the brief with a hash of its findings; failing that,
    /// the prompt itself is a flattening of every finding, its numbers and its
    /// caveats, so either changes exactly when the facts do and not when a
    /// weight or an ordering shifts. That makes it the right key for prose
    /// that cost battery to produce: reused while the facts hold, dropped the
    /// moment they do not.
    var narrationKey: String {
        let shape = narration?.shape ?? ""
        return shape.isEmpty ? (narration?.prompt?.user ?? "") : shape
    }

    /// A narrator can only be run on a brief that carries the prompt block.
    var promptable: NarrationPrompt? {
        guard let p = narration?.prompt, !p.user.isEmpty else { return nil }
        return p
    }
}

/// Which model providers the server has a key for. Booleans only - there is
/// no field on this route that could carry a key back out, which is the point
/// of it.
struct ModelProvider: Decodable, Identifiable, Hashable {
    let provider: String, label: String
    let configured: Bool
    let env: String, model: String
    var id: String { provider }
}

struct ModelsPayload: Decodable {
    let providers: [ModelProvider]
    init(from decoder: Decoder) throws {
        if let c = try? decoder.container(keyedBy: K.self) {
            providers = (try? c.decode([ModelProvider].self, forKey: .providers))
                ?? (try? c.decode([ModelProvider].self, forKey: .models)) ?? []
        } else {
            providers = (try? [ModelProvider](from: decoder)) ?? []
        }
    }
    private enum K: String, CodingKey { case providers, models }
}


// MARK: - how the findings are grouped

/// The sub-tabs, built from what the data actually supports.
///
/// The design this view is modelled on had eight: All, Start-Sit, Waivers,
/// Trades, Matchups, Injuries, Trends and League Insights. Waivers and Trades
/// are not here because no insight kind produces one - there is no pending
/// claim or offer in any feed this reads - and a tab that opens on nothing is
/// a worse answer than no tab. `other` exists so a kind added on the server
/// after this client shipped is still shown rather than silently dropped.
enum IntelSection: String, CaseIterable, Identifiable {
    case matchup = "Matchups"
    case lineup = "Start-Sit"
    case injury = "Injuries"
    case opportunity = "Opportunity"
    case league = "League Insights"
    case other = "Other"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .matchup:     return "shield.lefthalf.filled"
        case .lineup:      return "arrow.left.arrow.right"
        case .injury:      return "cross.case.fill"
        case .opportunity: return "chart.line.uptrend.xyaxis"
        case .league:      return "trophy"
        case .other:       return "questionmark.circle"
        }
    }

    /// Which sub-tab an insight belongs under. The kinds are the ones
    /// `intel.py` emits; anything else lands in `other`.
    static func of(_ kind: String) -> IntelSection {
        switch kind {
        case "carrying", "fragility", "decider", "pregame": return .matchup
        case "conflict", "exposure":                        return .lineup
        case "injury":                                      return .injury
        case "opportunity":                                 return .opportunity
        case "history":                                     return .league
        default:                                            return .other
        }
    }
}

extension IntelInsight {
    var section: IntelSection { IntelSection.of(kind) }

    /// The kind, in the words the reader of a card needs rather than the key
    /// the engine sorts on.
    var kindLabel: String {
        switch kind {
        case "carrying":    return "CARRYING YOU"
        case "fragility":   return "LEAD AT RISK"
        case "decider":     return "DECIDER"
        case "pregame":     return "BEFORE KICKOFF"
        case "conflict":    return "BOTH SIDES"
        case "exposure":    return "EXPOSURE"
        case "injury":      return "INJURY WIRE"
        case "opportunity": return "USAGE"
        case "history":     return "LEAGUE HISTORY"
        default:            return kind.uppercased()
        }
    }
}
