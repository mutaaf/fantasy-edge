import Foundation
import simd

/// How a football moves along a play's arc: pure functions of the arc, the
/// time into its flight and `visual.broadcast.ball.flight`, so the headset,
/// `verify_scene.swift` and a port all put the ball in the same place.
///
/// The ball's model has its long axis on local +x and its laces on +y.
public enum BallFlight {
    public enum Manner: String, Sendable {
        case spiral, wobble, tumble, carry, bounce
    }

    public struct Pose: Sendable {
        public var position: SIMD3<Float>
        public var orientation: simd_quatf
    }

    /// A play's manner: its style first (an incompletion wobbles), then its
    /// type (a punt tumbles, a fumble bounces), then its shape.
    public static func manner(_ arc: SceneSpec.Arc, _ f: SceneSpec.Look.BallFlight) -> Manner {
        if let m = f.byStyle[arc.style], let manner = Manner(rawValue: m) { return manner }
        let type = arc.type.lowercased()
        for (key, value) in f.byType.sorted(by: { $0.key.count > $1.key.count }) where type.contains(key) {
            if let manner = Manner(rawValue: value) { return manner }
        }
        return Manner(rawValue: f.byShape[arc.shape] ?? "") ?? .carry
    }

    /// Where the ball is and how it is turned `t` of the way along its arc
    /// (already eased), `elapsed` seconds after the snap.
    public static func pose(_ arc: SceneSpec.Arc, t: Double, elapsed: Double, manner: Manner,
                            flight f: SceneSpec.Look.BallFlight, lift: Float) -> Pose {
        let u = max(0, min(1, t))
        var p = SceneMath.point(on: arc, at: u)
        let ahead = SceneMath.point(on: arc, at: min(1, u + 0.02))
        let behind = SceneMath.point(on: arc, at: max(0, u - 0.02))
        let sign: Float = arc.toX >= arc.fromX ? 1 : -1
        var dir = ahead - behind
        if simd_length(dir) < 1e-5 { dir = SIMD3(sign, 0, 0) }
        dir = simd_normalize(dir)
        var flat = SIMD3<Float>(dir.x, 0, dir.z)
        if simd_length(flat) < 1e-5 { flat = SIMD3(sign, 0, 0) }
        flat = simd_normalize(flat)

        // Heading by yaw about +y, then nose up or down by pitch about the
        // ball's own z: never `from:to:`, which turns the laces under when a
        // play runs toward -x.
        let yaw = simd_quatf(angle: atan2(-flat.z, flat.x), axis: SIMD3(0, 1, 0))
        let pitch = simd_quatf(angle: asin(max(-1, min(1, dir.y))), axis: SIMD3(0, 0, 1))
        let time = Float(elapsed)
        let spin = Float(f.spiralPerSecond) * 2 * .pi * time
        let turn = Float(f.tumblePerSecond) * 2 * .pi * time
        var q: simd_quatf

        switch manner {
        case .spiral:
            q = yaw * pitch * simd_quatf(angle: spin, axis: SIMD3(1, 0, 0))
        case .wobble:
            let w = Float(f.wobbleDegrees * .pi / 180) * sin(2 * .pi * Float(f.wobbleHz) * time)
            q = yaw * pitch * simd_quatf(angle: w, axis: SIMD3(0, 1, 0))
                * simd_quatf(angle: spin * 0.55, axis: SIMD3(1, 0, 0))
        case .tumble:
            q = yaw * simd_quatf(angle: turn, axis: SIMD3(0, 0, 1))
        case .carry:
            q = yaw * simd_quatf(angle: Float(f.carryTiltDegrees * .pi / 180), axis: SIMD3(0, 0, 1))
            p.y += Float(f.carryBobYards) * abs(sin(2 * .pi * Float(f.carryBobHz) * time))
        case .bounce:
            let start = 1 - max(0.05, min(0.95, f.bounceShare))
            if u <= start {
                q = yaw * simd_quatf(angle: Float(f.carryTiltDegrees * .pi / 180), axis: SIMD3(0, 0, 1))
            } else {
                let s = Float((u - start) / (1 - start))
                p.y = Float(f.bounceYards) * abs(sin(.pi * Float(max(1, f.bounces)) * s)) * (1 - s)
                q = yaw * simd_quatf(angle: turn * 1.7, axis: SIMD3(0, 0, 1))
                    * simd_quatf(angle: spin * 0.4, axis: SIMD3(0, 1, 0))
            }
        }
        return Pose(position: p + SIMD3(0, lift, 0), orientation: q)
    }
}
