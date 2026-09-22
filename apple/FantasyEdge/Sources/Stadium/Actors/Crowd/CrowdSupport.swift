import Foundation
import simd

/// Whose crowd it is, and how full the bowl is: the crowd's other pure decision, beside
/// `CrowdChoreography`. No RealityKit, so `apple/verify_crowd_support.swift` compiles it on a Mac
/// and checks it against real scenes - which matters because this is the code that decided, at
/// integration-13, that a whole section of the bowl wore one colour.
///
/// Everything comes from the scene: the home and away chips, `bowl.crowd.awaySection`, the bench
/// range in `field.props`, the seating, and the score and clock in `status`. No club is named.
public enum CrowdSupport {
    /// Whose colours a seat wears. Support cannot vary freely per seat: a group of fans shares one
    /// texture, so the cost of a mixture is the number of (slice, support, variant) groups it makes.
    public enum Kind: Int, Hashable, Sendable {
        case home = 0, away = 1, neutral = 2
        public var name: String { self == .home ? "home" : self == .away ? "away" : "neutral" }
    }

    public struct SectionKey: Hashable, Sendable {
        public let tier: String
        public let section: Int
        public init(tier: String, section: Int) {
            self.tier = tier
            self.section = section
        }
    }

    /// How strongly each section of the bowl pulls toward the visitors, and toward neither club.
    ///
    /// A home game is the home club's, overwhelmingly. The visitors get a core behind their own
    /// bench and a tail into the upper corners, in the order a real away support fills a ground:
    /// the scene's own `bowl.crowd.awaySection` first, then behind their bench (their sideline,
    /// between `field.props.benches` fromX and toX), then the upper corners on that side, until
    /// `support.visitingShare` of the sections carry them. `support.neutralShare` more, taken from
    /// the corners farthest from the visitors, wear neither club. Nothing here is assumed about
    /// which club is which: home, away and the away section all come from the scene.
    ///
    /// The verdict is a pull rather than a colour, because a section painted one colour is what
    /// read as a wedge at integration-13. `supportAt` draws each seat against it.
    public static func supportBySection(_ s: SceneSpec, look C: SceneSpec.Look.CrowdLook,
                                             drawn: Set<String>) -> [SectionKey: Double] {
        guard let seating = s.bowl.seating else { return [:] }
        let shape = s.bowl.shape
        let visitorsFar = (s.bowl.crowd.awaySection?.side ?? "far") == "far"
        let fromX = (s.bowl.crowd.awaySection?.fromX ?? 90) - 50
        let bench = s.field.props?.benches
        let benchFrom = (bench?.fromX ?? 30) - 50, benchTo = (bench?.toX ?? 70) - 50
        let corner = Double(C.support.cornerFrom)
        var scored: [(key: SectionKey, visitor: Double, neutral: Double)] = []
        for tier in seating.tiers where drawn.contains(tier.tier) {
            let sections = tier.sections ?? []
            guard !tier.rows.isEmpty else { continue }
            let row = tier.rows[tier.rows.count / 2]
            let ring = SceneMath.Ring(shape, offset: row.feet)
            for (index, sec) in sections.enumerated() {
                let mid = sec.to > sec.from ? (sec.from + sec.to) / 2 : ((sec.from + sec.to + 1) / 2).truncatingRemainder(dividingBy: 1)
                let t = ring.angle(at: mid * row.length)
                let p = SceneMath.bowlPoint(shape, offset: row.feet, angle: t)
                let onVisitorsSide = visitorsFar ? p.z < 0 : p.z > 0
                let cornerness = min(1, max(0, (abs(p.x) / max(1, shape.halfLength) - corner) / max(0.01, 1 - corner)))
                let upper = tier.tier != C.support.benchRowsTier
                var visitor = 0.0
                if onVisitorsSide && p.x >= Double(fromX) { visitor = 1.0 }                 // the scene's own away section
                else if onVisitorsSide && !upper && p.x >= Double(benchFrom) && p.x <= Double(benchTo) { visitor = 0.8 }  // behind their bench
                else if onVisitorsSide && upper && cornerness > 0.3 { visitor = 0.55 + 0.2 * cornerness }                 // the tail, upper corners
                else if onVisitorsSide { visitor = 0.15 }
                // The unaligned sit in the corners, high up, away from the visitors - never at
                // midfield, where they ended up beside the wearer at crowd-r6's first pass because
                // a flat term outscored a corner.
                let neutral = cornerness * (upper ? 1.0 : 0.55) - (onVisitorsSide ? 0.4 : 0)
                scored.append((SectionKey(tier: tier.tier, section: index), visitor, neutral))
            }
        }
        guard !scored.isEmpty else { return [:] }
        var out: [SectionKey: Double] = [:]
        let visiting = Int((Double(scored.count) * C.support.visitingShare).rounded())
        let neutrals = Int((Double(scored.count) * C.support.neutralShare).rounded())
        // The strongest pulls carry the visitors; the weakest of those is the block's edge.
        let ranked = scored.sorted { $0.visitor > $1.visitor }
        for (n, entry) in ranked.prefix(visiting).enumerated() where entry.visitor > 0 {
            // 1 at the core of the block, tapering toward its last section: the tail.
            out[entry.key] = 1 - 0.75 * Double(n) / Double(max(1, visiting - 1))
        }
        for entry in scored.sorted(by: { $0.neutral > $1.neutral }) where out.count < visiting + neutrals {
            // Only a corner takes them: a section with no corner to it stays the home club's.
            if out[entry.key] == nil, entry.neutral > 0.25 { out[entry.key] = -1 }            // negative: the unaligned
        }
        return out
    }

    /// Which club this seat wears, drawn against its section's pull on a block grain.
    ///
    /// Blocks of `support.blockRows` x `support.blockSeats`, not single seats: a dither at seat
    /// scale is noise, and a whole section in one colour is a wedge. Inside the block the draw is
    /// `coreProbability`, at the edge of the support `edgeProbability`, and `strayProbability` of
    /// the home ground carries a visitor anyway - a few always get in.
    public static func supportAt(pull: Double?, tierRows: Int, row: Int, seat: Int, section: Int,
                                      look C: SceneSpec.Look.CrowdLook) -> Kind {
        let block = UInt64(truncatingIfNeeded: (row / max(1, C.support.blockRows)) &* 733
                           &+ (seat / max(1, C.support.blockSeats)) &* 1571 &+ section &* 31)
        var h = block &* 0x9E3779B97F4A7C15
        h ^= h >> 29; h = h &* 0xBF58476D1CE4E5B9; h ^= h >> 31
        let draw = Double(h % 10_000) / 10_000
        // No pull, no visitors: a stray away shirt in a home section would cost a whole draw part,
        // because a group of fans shares one texture, and there are 45 parts for the whole crowd.
        guard let pull else { return .home }
        if pull < 0 { return draw < 0.85 ? .neutral : .home }
        // The block thins as it climbs its tier: a travelling support fills the front of what it has.
        let height = tierRows > 1 ? Double(row) / Double(tierRows - 1) : 0
        let reach = max(0, 1 - max(0, height - C.support.tailRows) / max(0.05, 1 - C.support.tailRows))
        let chance = (C.support.edgeProbability + (C.support.coreProbability - C.support.edgeProbability) * pull) * reach
        if draw < chance { return .away }
        // The far corner of a visiting block is where the unaligned end up.
        return draw > 1 - C.support.strayProbability * (1 - pull) ? .neutral : .home
    }

    /// How likely this seat is to be taken: the upper deck thinner than the lower, the corners
    /// thinner than midfield, and thinner again high up once the game is decided. The scene knows
    /// the score, the period and the clock; it knows nothing about attendance, so nothing else is inferred.
    public static func keepChance(at p: SIMD3<Float>, tier: String, row: Int, seat: Int, seats: Int,
                                       look C: SceneSpec.Look.CrowdLook, spec s: SceneSpec) -> Double {
        let shape = s.bowl.shape
        let upper = tier != C.support.benchRowsTier
        var keep = upper ? C.emptySeats.upperFactor : 1
        let corner = Double(C.support.cornerFrom)
        let alongEnd = min(1, max(0, (Double(abs(p.x)) / max(1, shape.halfLength) - corner) / max(0.01, 1 - corner)))
        keep *= 1 - alongEnd * (1 - C.emptySeats.cornerFactor)
        if Double(abs(p.x)) > shape.halfLength * 0.9 { keep *= C.emptySeats.endZoneFactor }
        if decided(s, C) { keep *= upper ? C.emptySeats.blowout.upperFactor : C.emptySeats.blowout.lowerFactor }
        // Empties come in blocks and along the ends of a run, the way a stand actually empties:
        // at integration-13 they were scattered one seat at a time, which reads as noise.
        var h = UInt64(truncatingIfNeeded: (row / max(1, C.emptySeats.blockRows)) &* 9_173
                       &+ (seat / max(1, C.emptySeats.blockSeats)) &* 6_211) &* 0x9E3779B97F4A7C15
        h ^= h >> 27; h = h &* 0xD6E8FEB86659FD93; h ^= h >> 32
        let block = Double(h % 10_000) / 10_000
        if block < 1 - keep {
            // A thinned block empties from its middle out: an aisle seat is the last a stand
            // gives up, so what is left is a ragged edge along the gangway. At integration-14
            // the thinning was even inside the block, which read as scatter.
            let span = max(1, seats - 1)
            let toAisle = Double(min(seat, span - seat)) / Double(max(1, span / 2))
            keep *= C.emptySeats.blockEmptiness + C.emptySeats.aislePull * (1 - min(1, toAisle))
        }
        let ends = C.emptySeats.runEndSeats
        if ends > 0, seat < ends || seat >= seats - ends { keep *= C.emptySeats.runEndFactor }
        return min(1, keep)
    }

    /// Is this game over bar the clock? Margin, period and the clock the scene carries.
    public static func decided(_ s: SceneSpec, _ C: SceneSpec.Look.CrowdLook) -> Bool {
        let b = C.emptySeats.blowout
        guard s.status.state == "in", abs(s.status.homeScore - s.status.awayScore) >= b.margin else { return false }
        if s.status.period > b.fromPeriod { return true }
        guard s.status.period == b.fromPeriod else { return false }
        return clockSeconds(s.status.clock).map { $0 <= b.clockSeconds } ?? false
    }

    /// "12:40" as seconds. The scene carries the clock as the broadcast writes it.
    public static func clockSeconds(_ clock: String) -> Double? {
        let parts = clock.split(separator: ":")
        guard parts.count == 2, let m = Double(parts[0]), let sec = Double(parts[1]) else { return nil }
        return m * 60 + sec
    }

    /// How many fans are on their feet between plays: fewer in the first half than the fourth quarter.
    public static func standingShare(_ C: SceneSpec.Look.CrowdLook, spec s: SceneSpec) -> Double {
        s.status.period >= C.idleStandShare.aboutPeriod ? C.idleStandShare.late : C.idleStandShare.early
    }


}
