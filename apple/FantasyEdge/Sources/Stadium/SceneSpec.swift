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
    public let bowl: Bowl
    public let presentation: Presentation
    public let palette: [String: String]
    public let motion: Motion
    public let replayControl: ReplayState?

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

    public struct Moment: Decodable, Equatable, Sendable {
        public let kind: String
        public let side: String
        public let team: String
        public let points: Double
        public let playId: String
        public let text: String
        public let period: Int?
        public let clock: String

        /// A moment worth stopping the stadium for. A turnover changes the
        /// drive; it does not light a section.
        public var celebrates: Bool { kind == "touchdown" || kind == "fieldGoal" || kind == "safety" }
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
        public let offset: Double
        public let height: Double
        public let side: String
        public let color: String
    }

    public struct SectionTint: Decodable, Equatable, Sendable {
        public let side: String?
        public let color: String?
        public let dim: Double
    }

    public struct Crowd: Decodable, Equatable, Sendable {
        public let home: String
        public let away: String
        public let neutral: String
        public let dark: String
    }

    public struct Bowl: Decodable, Equatable, Sendable {
        public let shape: Shape
        public let tiers: [Tier]
        public let rimLights: RimLights
        public let crowd: Crowd
        public let sectionTint: SectionTint
    }

    public struct Seat: Decodable, Equatable, Sendable {
        public let x: Double
        public let y: Double
        public let z: Double
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
    }
}

/// The remote control's view of a replay: `GET /api/replay`.
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
