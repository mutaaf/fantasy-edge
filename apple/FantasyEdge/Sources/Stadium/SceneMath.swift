import Foundation
import simd

/// Pure geometry for a scene: yards in, local points out.
///
/// No RealityKit, so `apple/verify_scene.swift` compiles it on a Mac and
/// checks it against a real replayed game. A renderer on another platform
/// reproduces exactly this file and nothing more.
public enum SceneMath {

    /// Where a field coordinate lands in the renderer's local space, before
    /// the root's scale. Midfield is the origin, so the field sits centred in
    /// a volume and a seat can be placed relative to it.
    public static func local(x: Double, y: Double = 0, z: Double = 0) -> SIMD3<Float> {
        SIMD3(Float(x - 50), Float(y), Float(z))
    }

    /// A point on a play's arc, `t` from 0 at the snap spot to 1 where it ended.
    ///
    /// The arc is a parabola with its peak at the apex the scene states, so
    /// height at the middle of the play is exactly `arc.apex`.
    public static func point(on arc: SceneSpec.Arc, at t: Double) -> SIMD3<Float> {
        let u = max(0, min(1, t))
        let x = arc.fromX + (arc.toX - arc.fromX) * u
        let y = arc.apex * 4 * u * (1 - u)
        return local(x: x, y: y, z: arc.lane)
    }

    /// Evenly spaced points along an arc, ends included.
    public static func samples(_ arc: SceneSpec.Arc, count: Int = 24) -> [SIMD3<Float>] {
        let n = max(2, count)
        return (0..<n).map { point(on: arc, at: Double($0) / Double(n - 1)) }
    }

    /// The arc split into the pieces a dashed style draws. `dash` is
    /// [on, off] in yards along the field; a solid arc is one piece.
    public static func dashes(_ arc: SceneSpec.Arc, count: Int = 48) -> [[SIMD3<Float>]] {
        dashes(samples(arc, count: count), dash: arc.dash)
    }

    /// Any line split into the pieces a dash pattern draws.
    public static func dashes(_ pts: [SIMD3<Float>], dash: [Double]?) -> [[SIMD3<Float>]] {
        guard let pattern = dash, pattern.count == 2, pattern[0] > 0, pts.count > 1 else { return [pts] }
        var pieces: [[SIMD3<Float>]] = []
        var current: [SIMD3<Float>] = [pts[0]]
        var travelled: Float = 0
        let on = Float(pattern[0]), period = Float(pattern[0] + pattern[1])
        for i in 1..<pts.count {
            travelled += simd_distance(pts[i - 1], pts[i])
            let drawing = travelled.truncatingRemainder(dividingBy: period) < on
            if drawing {
                current.append(pts[i])
            } else if current.count > 1 {
                pieces.append(current)
                current = [pts[i]]
            } else {
                current = [pts[i]]
            }
        }
        if current.count > 1 { pieces.append(current) }
        return pieces
    }

    // MARK: how a play moves (scene.play_path)

    /// Where the ball is on a play `seconds` of real time after the presnap
    /// began, and which segment it is in. Without a path, the parabola.
    /// A carry eases gently in and out; an air segment keeps level ground
    /// speed under its gravity parabola, exactly scene.air_point.
    public static func ball(on arc: SceneSpec.Arc, at seconds: Double) -> (position: SIMD3<Float>, segment: SceneSpec.PathSegment?, u: Double) {
        guard let path = arc.path, !path.segments.isEmpty else {
            let t = arc.seconds > 0 ? seconds / arc.seconds : 1
            return (point(on: arc, at: t), nil, max(0, min(1, t)))
        }
        var start = 0.0
        for seg in path.segments {
            let end = start + seg.seconds
            if seconds < end || seg == path.segments.last! {
                let u = seg.seconds > 0 ? max(0, min(1, (seconds - start) / seg.seconds)) : 1
                return (segmentPoint(seg, u: u), seg, u)
            }
            start = end
        }
        return (point(on: arc, at: 1), nil, 1)
    }

    /// A segment `u` of the way through its time, in local space.
    public static func segmentPoint(_ seg: SceneSpec.PathSegment, u: Double) -> SIMD3<Float> {
        func v(_ a: [Double]?) -> SIMD3<Double> {
            guard let a, a.count == 3 else { return .zero }
            return SIMD3(a[0], a[1], a[2])
        }
        let p: SIMD3<Double>
        switch seg.kind {
        case "air":
            let a = v(seg.from), b = v(seg.to)
            var q = a + (b - a) * u
            q.y += (seg.rise ?? 0) * 4 * u * (1 - u)
            p = q
        case "carry":
            let pts = (seg.points ?? []).map { v($0) }
            guard pts.count > 1 else { p = pts.first ?? .zero; break }
            // Smoothstep in time, walked by length, so a run leaves and
            // arrives without a jolt and speeds the same along each leg.
            let e = u * u * (3 - 2 * u)
            var lengths: [Double] = [0]
            for i in 1..<pts.count { lengths.append(lengths[i - 1] + simd_distance(pts[i - 1], pts[i])) }
            let want = e * lengths.last!
            var i = 1
            while i < pts.count - 1 && lengths[i] < want { i += 1 }
            let span = max(1e-9, lengths[i] - lengths[i - 1])
            p = pts[i - 1] + (pts[i] - pts[i - 1]) * max(0, min(1, (want - lengths[i - 1]) / span))
        default:
            p = v(seg.at)
        }
        return local(x: p.x, y: p.y, z: p.z)
    }

    /// The line a play's trail draws, snap to finish: what was carried lies
    /// on the grass at `lift`, what flew keeps its height. Holds draw nothing.
    /// `until` stops it at that many real seconds, for a trail growing behind
    /// the ball. Without a path, the parabola.
    public static func trace(_ arc: SceneSpec.Arc, count: Int = 72, lift: Double, until: Double? = nil) -> [SIMD3<Float>] {
        guard let path = arc.path, !path.segments.isEmpty else {
            let n = max(2, count)
            let top = until.map { arc.seconds > 0 ? max(0, min(1, $0 / arc.seconds)) : 1 } ?? 1
            return (0..<n).map { point(on: arc, at: top * Double($0) / Double(n - 1)) }
        }
        let lengths = path.segments.map { seg -> Double in
            guard seg.kind != "hold" else { return 0 }
            let a = segmentPoint(seg, u: 0), b = segmentPoint(seg, u: 1)
            let flat = Double(simd_distance(SIMD2(a.x, a.z), SIMD2(b.x, b.z)))
            return seg.kind == "air" ? flat + 2 * (seg.rise ?? 0) : flat
        }
        let total = max(1e-6, lengths.reduce(0, +))
        var out: [SIMD3<Float>] = []
        var start = 0.0
        for (k, seg) in path.segments.enumerated() {
            defer { start += seg.seconds }
            if let until, start >= until { break }
            guard seg.kind != "hold" else { continue }
            let n = max(2, Int((Double(count) * lengths[k] / total).rounded()) + 1)
            let stop = until.map { seg.seconds > 0 ? max(0, min(1, ($0 - start) / seg.seconds)) : 1 } ?? 1
            for i in 0..<n {
                let f = Double(i) / Double(n - 1)
                var p: SIMD3<Float>
                if seg.kind == "carry" {
                    // A carry eases in time, not in shape: lay its line by
                    // length, as far as the ball has run by `stop`.
                    let reached = stop * stop * (3 - 2 * stop)
                    p = segmentPoint(seg, u: invertSmoothstep(reached * f))
                    p.y = Float(lift)
                } else {
                    // A flight's line leaves and meets the grass, as a replay
                    // graphic draws a throw from passer to catch, rather than
                    // standing up from the carry line at release height. The
                    // ends ease down to `lift`; the middle keeps its height.
                    let u = stop * f
                    p = segmentPoint(seg, u: u)
                    let w = Float(4 * u * (1 - u))
                    p.y = Float(lift) + w * (p.y - Float(lift))
                    if seg.phase == "snap" { p.y = Float(lift) }
                }
                if let last = out.last, simd_distance(last, p) < 1e-4 { continue }
                out.append(p)
            }
        }
        if out.count == 1 { out.append(out[0] + SIMD3(0.01, 0, 0)) }
        return out
    }

    /// u such that smoothstep(u) = e: laying a carry's points by length.
    static func invertSmoothstep(_ e: Double) -> Double {
        let e = max(0, min(1, e))
        return 0.5 - sin(asin(1 - 2 * e) / 3)
    }

    /// Where a kick at the posts leaves play: the seconds at which the ball
    /// passes `netYards` beyond the plane of the posts it was aimed at, or nil
    /// for anything that is not such a kick. A goal kick's arc carries ten
    /// yards past the posts so that it plainly crosses them; flown the whole
    /// way, the ball hung lit over the far stands with its trail behind it
    /// (integration-12). The ball and the trail stop here instead.
    public static func kickCut(_ arc: SceneSpec.Arc, field: SceneSpec.Field, netYards: Double) -> Double? {
        let type = arc.type.lowercased()
        guard type.contains("field goal") || type.contains("extra point"),
              let path = arc.path, arc.toX != arc.fromX else { return nil }
        let attack: Double = arc.toX > arc.fromX ? 1 : -1
        let plane = attack > 0 ? field.length + field.endZone : -field.endZone
        let stop = plane + attack * netYards
        var start = 0.0
        for seg in path.segments {
            defer { start += seg.seconds }
            guard seg.kind == "air", seg.phase == "kick", let from = seg.from, let to = seg.to,
                  abs(to[0] - from[0]) > 1e-6 else { continue }
            let u = (stop - from[0]) / (to[0] - from[0])
            guard u > 0, u < 1 else { return nil }
            return start + u * seg.seconds
        }
        return nil
    }

    /// The highest point anything on a play reaches.
    public static func peak(_ arc: SceneSpec.Arc) -> Double {
        guard let path = arc.path else { return arc.apex }
        return path.segments.map { seg -> Double in
            switch seg.kind {
            case "air": return max(seg.from?[1] ?? 0, seg.to?[1] ?? 0) + (seg.rise ?? 0)
            case "carry": return (seg.points ?? []).map { $0.count == 3 ? $0[1] : 0 }.max() ?? 0
            default: return seg.at?[1] ?? 0
            }
        }.max() ?? 0
    }

    /// A play laid lower: every flight's peak held to `cap` yards. A carry
    /// already lies on the grass, so only air segments change.
    public static func lowered(_ arc: SceneSpec.Arc, cap: Double) -> SceneSpec.Arc {
        var a = arc
        guard var path = arc.path else { return arc }
        for i in path.segments.indices where path.segments[i].kind == "air" {
            let s = path.segments[i]
            let top = max(s.from?[1] ?? 0, s.to?[1] ?? 0)
            path.segments[i].rise = max(0, min(s.rise ?? 0, cap - top))
        }
        a.path = path
        return a
    }

    /// A point on the superellipse the bowl is built from, `m` yards out from
    /// the field's edge, at angle `t`.
    public static func bowlPoint(_ shape: SceneSpec.Shape, offset m: Double, angle t: Double) -> (x: Double, z: Double) {
        let a = shape.halfLength + m, b = shape.halfWidth + m
        let e = 2 / shape.exponent
        let c = cos(t), s = sin(t)
        let x = a * (c < 0 ? -1 : 1) * pow(abs(c), e)
        let z = b * (s < 0 ? -1 : 1) * pow(abs(s), e)
        return (x, z)
    }

    /// Height of a tier at an offset between its inner and outer edge.
    public static func tierHeight(_ tier: SceneSpec.Tier, offset m: Double) -> Double {
        let span = max(1e-6, tier.outer - tier.inner)
        let f = max(0, min(1, (m - tier.inner) / span))
        return tier.rise[0] + (tier.rise[1] - tier.rise[0]) * f
    }

    /// The win-probability horizon as points, for the side the scene names.
    public static func horizon(_ wp: SceneSpec.WinProbability) -> [SIMD3<Float>] {
        let s = wp.series
        guard s.count > 1 else { return [] }
        let h = wp.horizon
        return s.enumerated().map { i, p in
            let x = h.x0 + (h.x1 - h.x0) * Double(i) / Double(s.count - 1)
            return local(x: x, y: h.y0 + (h.y1 - h.y0) * p, z: h.z)
        }
    }

    /// Where the renderer's root goes so a seat in the stands is where the
    /// wearer is: the seat's floor on the floor of the space, which puts their
    /// eyes, `eye` metres up, where a seated fan's are.
    ///
    /// Until the integration-1 pass this lifted the seat floor to `eye`, so
    /// the wearer's eyes sat on the tread and every seat looked out from
    /// inside the row in front of it.
    public static func stadiumRoot(seat: SceneSpec.Seat, metersPerYard s: Double, eye: Double = 1.2) -> SIMD3<Float> {
        let at = local(x: seat.x, y: seat.y, z: seat.z) * Float(s)
        return SIMD3(-at.x, -at.y, -at.z)
    }

    // MARK: 1.1 - seats, rows, trails

    /// The root transform that puts the wearer in a seat: the seat's floor on
    /// the space's floor, so the eyes are `eye` metres above it, facing the
    /// seat's `lookAt` down -z.
    ///
    /// The world turns about the wearer; the wearer never moves. That is the
    /// comfort rule for every seat change.
    public static func seatRoot(_ seat: SceneSpec.SeatOption, metersPerYard s: Double,
                                eye: Double) -> (position: SIMD3<Float>, orientation: simd_quatf) {
        let at = local(x: seat.x, y: seat.y, z: seat.z)
        let target = local(x: seat.lookAt.x, y: seat.lookAt.y, z: seat.lookAt.z)
        let d = target - at
        // Yaw that carries the seat's facing onto -z.
        let yaw = atan2(d.x, -d.z)
        let turn = simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0))
        let scaled = turn.act(at * Float(s))
        return (SIMD3(-scaled.x, -scaled.y, -scaled.z), turn)
    }

    /// Row `r` of `rows` on a tier, as the stepped seating is built: the
    /// tread runs from `front` to `back` (offsets from the field's edge) at
    /// height `tread`, and the riser in front of it climbs from `riserFrom`.
    public static func row(_ tier: SceneSpec.Tier, _ r: Int, of rows: Int)
        -> (front: Double, back: Double, tread: Double, riserFrom: Double) {
        let n = Double(max(1, rows))
        let depth = (tier.outer - tier.inner) / n
        let front = tier.inner + depth * Double(r)
        let back = front + depth
        let rise = tier.rise[1] - tier.rise[0]
        let tread = tier.rise[0] + rise * Double(r + 1) / n
        let riserFrom = tier.rise[0] + rise * Double(r) / n
        return (front, back, tread, riserFrom)
    }

    /// Angles around a superellipse at even spacing along its length, so a
    /// row of seats or a ribbon board's text does not bunch at the corners.
    public static func evenAngles(_ shape: SceneSpec.Shape, offset m: Double, count: Int,
                                  resolution: Int = 1440) -> (angles: [Double], length: Double) {
        var cumulative = [0.0]
        var prev = bowlPoint(shape, offset: m, angle: 0)
        for i in 1...resolution {
            let t = Double(i) / Double(resolution) * 2 * .pi
            let p = bowlPoint(shape, offset: m, angle: t)
            cumulative.append(cumulative[i - 1] + hypot(p.x - prev.x, p.z - prev.z))
            prev = p
        }
        let total = cumulative[resolution]
        var angles: [Double] = []
        var j = 0
        for k in 0..<max(0, count) {
            let want = total * Double(k) / Double(max(1, count))
            while j < resolution - 1 && cumulative[j + 1] < want { j += 1 }
            let span = max(1e-9, cumulative[j + 1] - cumulative[j])
            let f = (want - cumulative[j]) / span
            angles.append((Double(j) + f) / Double(resolution) * 2 * .pi)
        }
        return (angles, total)
    }

    /// A bowl ring walked by arc length from angle 0 - `BowlRing` in
    /// scene.py, exactly: the same resolution and the same interpolation, so a
    /// seat's arc turns into the same angle on every client.
    public struct Ring: Sendable {
        public static let resolution = 2880
        public let offset: Double
        public let length: Double
        private let cumulative: [Double]

        public init(_ shape: SceneSpec.Shape, offset m: Double) {
            offset = m
            let n = Ring.resolution
            var cum = [0.0]
            cum.reserveCapacity(n + 1)
            var prev = SceneMath.bowlPoint(shape, offset: m, angle: 0)
            for i in 1...n {
                let p = SceneMath.bowlPoint(shape, offset: m, angle: 2 * .pi * Double(i) / Double(n))
                cum.append(cum[i - 1] + hypot(p.x - prev.x, p.z - prev.z))
                prev = p
            }
            cumulative = cum
            length = cum[n]
        }

        /// The angle at arc `s` along the ring, wrapped.
        public func angle(at s: Double) -> Double {
            let n = Ring.resolution
            var a = s.truncatingRemainder(dividingBy: length)
            if a < 0 { a += length }
            var lo = 0, hi = n
            while hi - lo > 1 {
                let mid = (lo + hi) / 2
                if cumulative[mid] <= a { lo = mid } else { hi = mid }
            }
            let span = cumulative[hi] - cumulative[lo]
            let t0 = 2 * .pi * Double(lo) / Double(n), t1 = 2 * .pi * Double(hi) / Double(n)
            return t0 + (t1 - t0) * (a - cumulative[lo]) / (span == 0 ? 1e-9 : span)
        }
    }

    /// Seat `k` of run `run` in a row: where it is (local yards, feet on its
    /// tread) and which way it faces (unit x-z, toward the field). Build the
    /// `ring` once per row with `Ring(shape, offset: row.feet)`.
    public static func seat(_ row: SceneSpec.SeatingRow, run: Int, k: Int, shape: SceneSpec.Shape,
                            ring: Ring) -> (position: SIMD3<Float>, facing: SIMD2<Double>, angle: Double) {
        let first = row.runs[run][0]
        let t = ring.angle(at: first + Double(k) * row.pitch)
        let p = bowlPoint(shape, offset: row.feet, angle: t)
        return (SIMD3(Float(p.x), Float(row.floor), Float(p.z)), inward(shape, offset: row.feet, angle: t), t)
    }

    /// Unit vector from a bowl point back toward the field, in the x-z plane.
    public static func inward(_ shape: SceneSpec.Shape, offset m: Double, angle t: Double) -> SIMD2<Double> {
        let e = 1e-3
        let a = bowlPoint(shape, offset: m, angle: t - e), b = bowlPoint(shape, offset: m, angle: t + e)
        var n = SIMD2(-(b.z - a.z), b.x - a.x)       // tangent turned a quarter
        let here = bowlPoint(shape, offset: m, angle: t)
        if n.x * here.x + n.y * here.z > 0 { n = -n }
        let len = max(1e-9, (n.x * n.x + n.y * n.y).squareRoot())
        return n / len
    }

    /// How much of its core thickness a trail keeps, given how close it comes
    /// to the seat: full beyond `yards`, thinning in proportion inside it, and
    /// never below `minScale`. Distances in yards, points in local space.
    public static func nearSeatScale(_ points: [SIMD3<Float>], seat: SIMD3<Float>,
                                     rule: SceneSpec.Look.NearSeat) -> Double {
        guard let nearest = points.map({ simd_distance($0, seat) }).min() else { return 1 }
        return max(rule.minScale, min(1, Double(nearest) / max(1e-6, rule.yards)))
    }

    /// Hex "#RRGGBB" or "#RRGGBBAA" as linear-ish sRGB components and alpha.
    public static func rgba(_ hex: String) -> SIMD4<Float> {
        var h = hex.trimmingCharacters(in: .whitespaces)
        if h.hasPrefix("#") { h.removeFirst() }
        guard h.count == 6 || h.count == 8, let v = UInt64(h, radix: 16) else {
            return SIMD4(0.5, 0.5, 0.5, 1)
        }
        let n = h.count == 8 ? v : (v << 8) | 0xFF
        return SIMD4(Float((n >> 24) & 0xFF) / 255, Float((n >> 16) & 0xFF) / 255,
                     Float((n >> 8) & 0xFF) / 255, Float(n & 0xFF) / 255)
    }
}

/// How the ball travels each new play, in order.
///
/// A poll can bring several plays at once - at 60x a drive's worth - so they
/// queue, and each is animated for the duration the scene gave it. A queue
/// that falls behind halves what is left rather than letting the ball lag the
/// game, and reduce motion skips the flight altogether and lands the ball.
public struct PlayMotion {
    public private(set) var queue: [SceneSpec.Arc] = []
    public private(set) var seen: Set<String> = []

    public init() {}

    /// New arcs in this drive that have not been shown, oldest first. The
    /// first scene a renderer receives is history, not news: it is marked
    /// seen and nothing animates.
    public mutating func arrive(_ drive: SceneSpec.Drive?, initial: Bool) -> [SceneSpec.Arc] {
        guard let drive else { return [] }
        let fresh = drive.arcs.filter { !seen.contains($0.id) }
        for a in drive.arcs { seen.insert(a.id) }
        if initial { return [] }
        queue.append(contentsOf: fresh)
        return fresh
    }

    public mutating func reset() {
        queue.removeAll()
        seen.removeAll()
    }

    /// The next arc and how long to fly it. Nil when there is nothing to do.
    public mutating func next(reduceMotion: Bool, floor: Double) -> (SceneSpec.Arc, Double)? {
        guard !queue.isEmpty else { return nil }
        let arc = queue.removeFirst()
        if reduceMotion { return (arc, 0) }
        let backlog = queue.count
        let squeeze = backlog > 3 ? 0.5 : 1.0
        return (arc, max(floor, arc.flightSeconds * squeeze))
    }
}
