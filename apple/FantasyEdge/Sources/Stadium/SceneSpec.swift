import Foundation

// The scene contract, as the API serves it from `fantasyedge/scene.py`.
//
// Everything in `Stadium/` renders this and nothing else. There is no fantasy
// type in here and no football rule either: where a pass peaks, which lane a
// run takes, when a section lights up and what colour a chip is were all
// decided on the server, once, for every client. A web or Android renderer
// decodes the same JSON; the college app serves the same shape.
//
// Coordinates are yards. x runs from the home goal line (0) to the away goal
// line (100), end zones -10..0 and 100..110; z is across the field, positive
// toward the home sideline; y is up.

public struct SceneSpec: Decodable, Equatable, Sendable {
    public let version: String
    public let kind: String
    public let league: String
    public let event: String
    public let source: String
    public let speed: Double
    public let field: Field
    public let teams: Teams
    public let status: Status
    public let ball: Ball?
    public let lasers: [Laser]
    public let drives: [Drive]
    public let currentDrive: Int?
    public let winProbability: WinProbability
    public let moments: [Moment]
    public let activeMoment: Moment?
    /// 1.3: the game's other beats - quarter ends, the two-minute warning,
    /// red-zone crossings, the final - and the one for this instant.
    public let cues: [Cue]?
    public let activeCue: Cue?
    public let bowl: Bowl
    public let presentation: Presentation
    public let palette: [String: String]
    /// Shader Graph materials and their portable fallbacks (docs/SHADERGRAPH.md).
    public let shaderGraph: ShaderGraphSpec?
    public let motion: Motion
    /// 1.1: every visual-only number a renderer reads. Nil from a 1.0 server,
    /// in which case the renderer uses `Look.fallback`, a copy of the tokens.
    public let look: Look?
    public let replayControl: ReplayState?

    enum CodingKeys: String, CodingKey {
        case version, kind, league, event, source, speed, field, teams, status, ball, lasers, drives
        case currentDrive, winProbability, moments, activeMoment, cues, activeCue, bowl, presentation, palette, motion
        case shaderGraph
        case replayControl
        /// The contract calls it `visual`; the renderer reads it as its look.
        case look = "visual"
    }

    public var isReplay: Bool { source == "replay" }

    /// The drive a renderer should draw: the one in progress, or the last one
    /// once the game has stopped.
    public var shownDrive: Drive? {
        if let i = currentDrive, drives.indices.contains(i) { return drives[i] }
        return drives.last
    }

    public struct Field: Decodable, Equatable, Sendable {
        public let length: Double
        public let endZone: Double
        public let width: Double
        public let hashFromSideline: Double
        public let goalPostWidth: Double
        public let stripeEvery: Double
        public let numbersEvery: Double
        /// 1.1: goal posts, pylons, benches and chains, by league.
        public let props: Props?
        /// 1.2: where each club's name and the midfield ring are painted
        /// (`FieldArt`, Actors/Field), and the folder of this league's baked
        /// markings under assets/.
        public let art: FieldArt?
        public let markings: String?
    }

    public struct PostRadius: Decodable, Equatable, Sendable {
        public let base: Double
        public let crossbar: Double
        public let upright: Double
    }

    public struct Goalpost: Decodable, Equatable, Sendable {
        public let baseBehind: Double
        public let crossbar: Double
        public let uprightAbove: Double
        public let radius: PostRadius
        public let padHeight: Double
        public let padWidth: Double
        public let color: String
    }

    public struct Pylon: Decodable, Equatable, Sendable {
        public let size: Double
        public let height: Double
        public let color: String
        /// 1.2: every pylon's centre as [x, z] yards, by league.
        public let at: [[Double]]?
    }

    public struct Benches: Decodable, Equatable, Sendable {
        public let fromX: Double
        public let toX: Double
        public let offset: Double
        public let height: Double
        public let depth: Double
        public let backHeight: Double
        public let color: String
    }

    public struct Chains: Decodable, Equatable, Sendable {
        public let length: Double
        public let offset: Double
        public let poleHeight: Double
        public let markerWidth: Double
        public let side: String
        public let color: String
    }

    public struct Props: Decodable, Equatable, Sendable {
        public let goalpost: Goalpost
        public let pylon: Pylon
        public let benches: Benches
        public let chains: Chains
    }

    public struct Team: Decodable, Equatable, Sendable {
        public let abbr: String
        public let name: String
        public let id: String
        public let color: String
        public let chip: String
        public let chipText: String
        public let hatch: Bool
        public let score: Double
    }

    public struct Teams: Decodable, Equatable, Sendable {
        public let home: Team
        public let away: Team
        public func side(_ s: String?) -> Team? { s == "home" ? home : s == "away" ? away : nil }
    }

    public struct Status: Decodable, Equatable, Sendable {
        public let state: String
        public let label: String
        public let clock: String
        public let period: Int
        public let homeScore: Double
        public let awayScore: Double
        public let possession: String?
        public let down: Int?
        public let distance: Int?
        public let downDistance: String
        public let redZone: Bool
    }

    public struct Beacon: Decodable, Equatable, Sendable {
        public let height: Double
        public let color: String
    }

    public struct Ball: Decodable, Equatable, Sendable {
        public let x: Double
        public let y: Double
        public let z: Double
        public let beacon: Beacon
    }

    public struct Laser: Decodable, Equatable, Sendable {
        public let kind: String
        public let x: Double
        public let color: String
    }

    public struct Arc: Decodable, Equatable, Sendable, Identifiable {
        public let id: String
        public let style: String
        public let shape: String
        public let type: String
        public let fromX: Double
        public let toX: Double
        public let lane: Double
        public let apex: Double
        public let color: String
        public let dash: [Double]?
        public let seconds: Double
        public let duration: Double
        public let side: String?
        public let text: String
        public let period: Int?
        public let clock: String
        public let down: Int?
        public let distance: Int?
        /// How the ball moves, as scene.play_path lays it out. Optional: a
        /// scene from before the path flies the parabola `apex` describes.
        public var path: PlayPath? = nil

        /// Where this play's geometry came from: `live` is ESPN's text and
        /// spots with the rest estimated, `corrected` is nflverse's published
        /// row, which states where the ball was caught.
        ///
        /// Optional, like `path`, and for the same reason: a synthesized
        /// `Decodable` ignores a default value and throws on a missing key,
        /// so a non-optional `= "live"` would refuse every scene built before
        /// this field existed. Read `provenance`, which supplies the default.
        public var source: String? = nil

        /// The fields nflverse stated, when `source` is `corrected`.
        public var corrected: [String]? = nil

        /// Where this play's geometry came from, defaulting to a live estimate.
        public var provenance: String { source ?? "live" }

        /// Whether the ball flies where it actually went, rather than where
        /// the text implied.
        public var isCorrected: Bool { provenance == "corrected" }

        /// The fields nflverse stated for this play.
        public var correctedFields: [String] { corrected ?? [] }

        /// How long this play animates at the scene's speed.
        public var flightSeconds: Double { path?.duration ?? duration }
    }

    /// A play as timed segments (`visual.broadcast.play`): `hold` keeps the
    /// ball `at` a spot, `carry` runs it along `points`, `air` flies it
    /// `from` → `to` on a gravity parabola `rise` yards over the chord.
    /// Times are real seconds; `duration` is the whole at the scene's speed.
    public struct PlayPath: Decodable, Equatable, Sendable {
        public let seconds: Double
        public let duration: Double
        public let snap: [Double]
        public var segments: [PathSegment]
    }

    public struct PathSegment: Decodable, Equatable, Sendable {
        public let kind: String
        public let phase: String
        public let seconds: Double
        public let at: [Double]?
        public let points: [[Double]]?
        public let from: [Double]?
        public let to: [Double]?
        public var rise: Double?
    }

    public struct Drive: Decodable, Equatable, Sendable, Identifiable {
        public let id: String
        public let team: String
        public let side: String?
        public let result: String
        public let arcs: [Arc]
    }

    public struct Horizon: Decodable, Equatable, Sendable {
        public let z: Double
        public let y0: Double
        public let y1: Double
        public let x0: Double
        public let x1: Double
    }

    public struct WinProbability: Decodable, Equatable, Sendable {
        public let side: String
        public let series: [Double]
        public let horizon: Horizon
    }

    /// A beat that is not a score or a turnover. `treatment` names the
    /// entry in `visual.moments.cues`; `id` is stable while the cue holds.
    public struct Cue: Decodable, Equatable, Sendable {
        public let kind: String
        public let id: String
        public let playId: String?
        public let side: String?
        public let detail: String?
        public let treatment: String
        public let source: String?
        public let period: Int?
        public let clock: String?
        public let sequence: Int?
    }

    public struct Point: Decodable, Equatable, Sendable {
        public let x: Double
        public let y: Double
        public let z: Double
    }

    public struct Moment: Decodable, Equatable, Sendable {
        public let kind: String
        public let side: String
        public let team: String
        public let points: Double
        public let playId: String
        public let text: String
        public let period: Int?
        public let clock: String
        /// 1.1: the scene says whether it celebrates, and where its banner,
        /// light and sound go.
        public let anchor: Point?
        /// 1.3: interception, fumble, puntReturn, kickReturn, blocked, or nil.
        public let detail: String?
        private let decidedCelebrates: Bool?

        enum CodingKeys: String, CodingKey {
            case kind, side, team, points, playId, text, period, clock, anchor, detail
            case decidedCelebrates = "celebrates"
        }

        /// A moment worth stopping the stadium for. A turnover changes the
        /// drive; it does not light a section. The server decides from 1.1 on;
        /// the rule below is only what a 1.0 server meant.
        public var celebrates: Bool {
            decidedCelebrates ?? (kind == "touchdown" || kind == "fieldGoal" || kind == "safety")
        }

        /// Field x the moment's effects gather over.
        public var anchorX: Double { anchor?.x ?? (side == "home" ? 105 : -5) }
    }

    public struct Tier: Decodable, Equatable, Sendable {
        public let name: String
        public let inner: Double
        public let outer: Double
        public let rise: [Double]
        public let color: String
    }

    public struct Shape: Decodable, Equatable, Sendable {
        public let type: String
        public let exponent: Double
        public let halfLength: Double
        public let halfWidth: Double
    }

    public struct RimLights: Decodable, Equatable, Sendable {
        public let count: Int
        /// Yards beyond the outermost drawn tier. 1.0 servers sent absolute
        /// `offset`/`height` that no renderer honoured; 1.1 replaced them.
        public let beyondOuter: Double?
        public let side: String
        public let color: String
    }

    public struct SectionTint: Decodable, Equatable, Sendable {
        public let side: String?
        public let color: String?
        public let dim: Double
    }

    public struct AwaySection: Decodable, Equatable, Sendable {
        public let side: String
        public let fromX: Double
    }

    public struct Crowd: Decodable, Equatable, Sendable {
        public let home: String
        public let away: String
        public let neutral: String
        public let dark: String
        public let awaySection: AwaySection?
    }

    public struct Wall: Decodable, Equatable, Sendable {
        public let offset: Double
        public let height: Double
        public let color: String
    }

    public struct Ribbon: Decodable, Equatable, Sendable {
        public let offset: Double
        public let rise: [Double]
        public let color: String
        public let text: String
    }

    public struct PressBox: Decodable, Equatable, Sendable {
        public let side: String
        public let fromX: Double
        public let toX: Double
        public let offset: Double
        public let depth: Double
        public let rise: [Double]
        public let mullionEvery: Double
        public let glass: String
        public let glassBrightness: Double
    }

    public struct Tunnel: Decodable, Equatable, Sendable {
        public let x: Double
        public let width: Double
        public let height: Double
    }

    /// A seating section, by arc-length fraction of its tier's middle ring.
    public struct SeatingSection: Decodable, Equatable, Sendable {
        public let id: String
        public let from: Double
        public let to: Double
        public let side: String?
        public let vomitory: Bool?
    }

    /// A row's seats as runs: `[firstArc, count]`, `pitch` yards apart along
    /// the ring at offset `feet`, walked from angle 0. See `SceneMath.seat`.
    public struct SeatingRow: Decodable, Equatable, Sendable {
        public let row: Int
        public let floor: Double
        public let feet: Double
        public let length: Double
        public let pitch: Double
        public let seats: Int
        public let runs: [[Double]]
    }

    public struct SeatingAccessible: Decodable, Equatable, Sendable {
        public let row: Int
        public let arc: Double
        public let length: Double
    }

    public struct SeatingTier: Decodable, Equatable, Sendable {
        public let tier: String
        public let sections: [SeatingSection]?
        public let rows: [SeatingRow]
        public let accessible: [SeatingAccessible]?
    }

    /// Every seat in the bowl (`bowl.seating`, from Bowl). Unknown keys are
    /// ignored and the config keys are optional while Bowl iterates.
    public struct Seating: Decodable, Equatable, Sendable {
        public let pitch: Double
        public let total: Int
        public let tiers: [SeatingTier]
        public let aisle: Double?
        public let feetDepth: Double?
        public let tunnelClear: Double?
        public let startAngle: Double?
    }

    public struct Bowl: Decodable, Equatable, Sendable {
        /// Absent on scenes older than Bowl's seat-by-seat layout.
        public let seating: Seating?
        public let shape: Shape
        public let tiers: [Tier]
        public let rimLights: RimLights
        public let crowd: Crowd
        public let sectionTint: SectionTint
        public let wall: Wall?
        public let ribbon: Ribbon?
        public let pressBox: PressBox?
        public let tunnels: [Tunnel]?
        /// Bowl's LED face behind the east end zone, which Broadcast draws on.
        /// Optional: absent on scenes from before Bowl built it.
        public let videoBoard: VideoBoard?
    }

    /// `bowl.videoBoard`: the face's centre in field yards, the unit
    /// direction it looks along, and its width x height in yards.
    public struct VideoBoard: Decodable, Equatable, Sendable {
        public let centre: [Double]
        public let facing: [Double]
        public let size: [Double]
        public let screen: String
    }

    public struct Seat: Decodable, Equatable, Sendable {
        public let x: Double
        public let y: Double
        public let z: Double
    }

    /// 1.1: a place to sit. The floor under the wearer, and what they face.
    public struct SeatOption: Decodable, Equatable, Sendable, Identifiable {
        public let id: String
        public let label: String
        public let x: Double
        public let y: Double
        public let z: Double
        public let lookAt: Point
        /// What the seat picker says about it. Worked out by scene.py so
        /// every client describes the same seat the same way.
        public let view: SeatView?
    }

    public struct SeatView: Decodable, Equatable, Sendable {
        /// "lower", "upper", "club", "field", "endzone", "pressBox": the picker's groups.
        public let group: String
        /// From the nearest edge of the field.
        public let distanceYards: Double
        public let heightYards: Double
    }

    public struct Tabletop: Decodable, Equatable, Sendable {
        public let metersPerYard: Double
        public let volume: [Double]
        public let floor: Double
        public let bowlTiers: [String]
    }

    public struct Stadium: Decodable, Equatable, Sendable {
        public let metersPerYard: Double
        public let seat: Seat
        public let bowlTiers: [String]
        public let seats: [SeatOption]?
        public let defaultSeat: String?

        /// The seat with this id, else the default, else the 1.0 `seat`
        /// facing midfield.
        public func seat(_ id: String?) -> SeatOption {
            let all = seats ?? []
            return all.first(where: { $0.id == id })
                ?? all.first(where: { $0.id == defaultSeat })
                ?? SeatOption(id: "seat", label: "Seat", x: seat.x, y: seat.y, z: seat.z,
                              lookAt: Point(x: 50, y: 0, z: 0), view: nil)
        }
    }

    public struct Presentation: Decodable, Equatable, Sendable {
        public let tabletop: Tabletop
        public let stadium: Stadium
        public let beaconHeight: Double
    }

    public struct Motion: Decodable, Equatable, Sendable {
        public let minSeconds: Double
        public let maxSeconds: Double
        public let referenceSpeed: Double
        public let floorSeconds: Double
        public let sectionDim: Double
        /// How long a celebration stays up. Optional until `design/tokens.json`
        /// carries it; the views fall back to `MomentHold.defaultSeconds`.
        public let momentSeconds: Double?
        /// 1.1: the ball's flight eases out by this power, quick off the snap.
        public let flightEase: Double?
        /// How long past a play's own flight the composer waits for it to land
        /// before firing its moment anyway. Optional until `design/tokens.json`
        /// carries it; `MomentGate.defaultGraceSeconds` stands in.
        public let momentHoldGraceSeconds: Double?
    }
}

/// The remote control's view of a replay: `GET /api/replay`.
/// Last week's slate, as `/api/lastweek` serves it.
///
/// Every game of the week, not only the ones already captured: a picker that
/// listed captures alone could never be the thing you pick *from*, because
/// what you want to watch is usually the one nobody has pulled yet.
///
/// Scores are absent unless they were asked for, which is why `Club.score` is
/// optional and the row carries `spoiler` to say which kind of row it is. A
/// view must never fill that gap with a zero.
public struct LastWeek: Decodable, Equatable, Sendable {
    public let season: Int
    public let week: Int
    public let games: [Game]
    public let pulled: Int
    public let total: Int
    public let spoilers: Bool
    public let offline: Bool?

    public struct Club: Decodable, Equatable, Sendable {
        public let abbr: String
        public let name: String
        public let score: Double?
    }

    public struct Game: Decodable, Equatable, Sendable, Identifiable {
        public let event: String
        public let name: String
        public let kickoff: String
        public let away: Club
        public let home: Club
        /// The one line under the matchup: why this game is worth an hour.
        public let reason: String
        public let reasons: [String]
        /// "quarter" from the slate alone, "play" once the game is pulled.
        public let precision: String
        public let caveat: String
        public let watchability: Double
        public let pulled: Bool
        public let spoiler: Bool
        public let plays: Int?
        public let length: Int?
        public let final: String?
        public var id: String { event }
    }
}

/// Where the scores and drives sit in a loaded replay, in game seconds.
public struct ReplayMarkers: Decodable, Equatable, Sendable {
    public let scores: [Score]
    public let drives: [Drive]
    public let length: Int

    public struct Score: Decodable, Equatable, Sendable, Identifiable {
        public let at: Int
        public let playAt: Int
        public let team: String
        public let period: Int
        public let clock: String
        public var id: Int { playAt }
    }

    public struct Drive: Decodable, Equatable, Sendable, Identifiable {
        public let at: Int
        public let team: String
        public let result: String
        public let plays: Int
        public var id: Int { at }
    }
}

public struct ReplayState: Decodable, Equatable, Sendable {
    public let replay: Bool
    public let loaded: Bool
    public let playing: Bool
    public let speed: Double
    public let speeds: [Double]
    public let event: String?
    public let gameSeconds: Int?
    public let length: Int?
    public let progress: Double?
    public let label: String?
    public let homeScore: Double?
    public let awayScore: Double?
    public let matchup: Matchup?
    public let games: [Game]?
    /// Game second of the shown drive's first snap; only on a replay scene.
    public let driveStart: Int?

    public struct Side: Decodable, Equatable, Sendable {
        public let abbr: String
        public let score: Double
    }

    public struct Matchup: Decodable, Equatable, Sendable {
        public let away: Side
        public let home: Side
        public let date: String
        public let final: String
        public let complete: Bool
    }

    public struct Game: Decodable, Equatable, Sendable, Identifiable {
        public let event: String
        public let away: Side
        public let home: Side
        public let date: String
        public let final: String
        public let complete: Bool
        public let plays: Int
        public let length: Int
        public var id: String { event }
    }
}

/// A number or a string from tokens: what a Shader Graph parameter is set to.
public enum TokenValue: Decodable, Equatable, Sendable {
    case number(Double)
    case string(String)

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let n = try? c.decode(Double.self) { self = .number(n) } else { self = .string(try c.decode(String.self)) }
    }

    public var any: Any {
        switch self {
        case .number(let n): return n
        case .string(let s): return s
        }
    }
}

public struct ShaderGraphSpec: Decodable, Equatable, Sendable {
    public struct Material: Decodable, Equatable, Sendable {
        public let file: String
        public let prim: String
        public let parameters: [String: TokenValue]
        public let fallback: [String: TokenValue]
    }
    public let materials: [String: Material]?
}
