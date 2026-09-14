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
