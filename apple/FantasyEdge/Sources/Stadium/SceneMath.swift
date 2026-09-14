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
        let pts = samples(arc, count: count)
        guard let pattern = arc.dash, pattern.count == 2, pattern[0] > 0 else { return [pts] }
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
    /// wearer is, their eyes `eye` metres above the floor of the space.
    public static func stadiumRoot(seat: SceneSpec.Seat, metersPerYard s: Double, eye: Double = 1.2) -> SIMD3<Float> {
        let at = local(x: seat.x, y: seat.y, z: seat.z) * Float(s)
        return SIMD3(-at.x, Float(eye) - at.y, -at.z)
    }

    // MARK: 1.1 - seats, rows, trails

    /// The root transform that puts the wearer in a seat: the seat's floor
    /// `eye` metres below the eyes, facing the seat's `lookAt` down -z.
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
        return (SIMD3(-scaled.x, Float(eye) - scaled.y, -scaled.z), turn)
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
        return (arc, max(floor, arc.duration * squeeze))
    }
}
