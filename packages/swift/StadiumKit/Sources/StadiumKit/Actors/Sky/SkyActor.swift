import RealityKit
import simd

/// The night: a star dome with city glow on the horizon, a thin veil of cloud
/// that drifts slowly across it, and the warm light dome a floodlit bowl
/// throws into the air above its rim. Stadium only; the table has the room.
/// Reads `visual.sky`, and the rim from `bowl` so the dome sits on it.
///
/// The images come from `tools/blender/lighting/textures.py`: equirectangular,
/// zenith on the top row. Three draws: stars, clouds, dome; under 5,000 triangles.
@MainActor
final class SkyActor: StadiumActor {
    let name = "sky"
    let root = Entity()
    private var clouds: ModelEntity?
    private var cloudYaw: Float = 0

    init() { root.name = "actor.sky" }

    func build(_ c: StadiumContext) {
        clear()
        clouds = nil
        guard !c.tabletop else { return }
        let V = c.look.sky, s = c.spec
        let yaw = simd_quatf(angle: Float(V.yawDegrees * .pi / 180), axis: SIMD3(0, 1, 0))
        // `-lightSkip stars,clouds,dome`: the same debug set Lighting reads, so
        // the three layers that brighten the band above the rim can be measured
        // one at a time. See LightingActor.skipped.
        let skip = LightingActor.skipped

        if !skip.contains("stars") {
            var starMaterial = StadiumLook.emissive("#FFFFFF", scale: V.skyGain, texture: c.assets.texture("sky.sky"), tile: false)
            starMaterial.faceCulling = .none
            let stars = Self.dome(radius: Float(V.radiusYards)).entity("sky.stars", starMaterial)
            stars.orientation = yaw
            root.addChild(stars)
        }

        if !skip.contains("clouds"), let texture = c.assets.texture("sky.clouds") {
            // Clouds cover stars rather than add to them: alpha-blended, dark,
            // lifted a little by the colour the tokens give them.
            var m = UnlitMaterial(applyPostProcessToneMap: false)
            let sampled = StadiumLook.clamped(texture)
            m.color = .init(tint: StadiumLook.color(V.cloudColor), texture: sampled)
            m.blending = .transparent(opacity: .init(scale: Float(V.cloudOpacity), texture: sampled))
            m.writesDepth = false
            m.faceCulling = .none
            let veil = Self.dome(radius: Float(V.cloudRadiusYards), fromElevation: 0).entity("sky.clouds", m)
            veil.orientation = yaw
            root.addChild(veil)
            clouds = veil
        }

        guard !skip.contains("dome"), let top = c.tiers.last else { return }
        let rimOffset = top.outer + (s.bowl.rimLights.beyondOuter ?? 1) + V.domeInsetYards
        let standTop = top.rise[1]
        var dome = MeshBuilder()
        let segments = 96
        for k in 0..<segments {
            let t0 = Double(k) / Double(segments) * 2 * .pi, t1 = Double(k + 1) / Double(segments) * 2 * .pi
            let a = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset, angle: t0)
            let b = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset, angle: t1)
            let y0 = Float(standTop), y1 = Float(standTop + V.domeHeight)
            // The dome image tiles four times round the bowl; v = 1 at the rim.
            let u0 = Float(k) / Float(segments) * 4, u1 = Float(k + 1) / Float(segments) * 4
            dome.quad(SIMD3(Float(a.x), y0, Float(a.z)), SIMD3(Float(b.x), y0, Float(b.z)),
                      SIMD3(Float(b.x), y1, Float(b.z)), SIMD3(Float(a.x), y1, Float(a.z)),
                      uv: (SIMD2(u0, 1), SIMD2(u1, 1), SIMD2(u1, 0), SIMD2(u0, 0)))
        }
        root.addChild(dome.entity("sky.dome", StadiumLook.glow(V.domeColor, opacity: V.domeOpacity,
                                                              texture: c.assets.texture("sky.dome"), tile: true)))
    }

    /// An inward-facing sphere in the equirect convention the sky images use:
    /// v = 1 at the zenith, u = 0.5 toward -Z, +X a quarter turn to the right.
    /// 48 x 24 is about 2,300 triangles - RealityKit's default sphere was 8,000,
    /// and a sky this far away shows no facets either way.
    static func dome(radius: Float, fromElevation: Float = -.pi / 2, around: Int = 48, rings: Int = 24) -> MeshBuilder {
        var mesh = MeshBuilder()
        let top: Float = .pi / 2
        func point(_ u: Float, _ el: Float) -> SIMD3<Float> {
            let phi = (u - 0.5) * 2 * .pi
            return SIMD3(cos(el) * sin(phi), sin(el), -cos(el) * cos(phi)) * radius
        }
        for r in 0..<rings {
            let e0 = fromElevation + (top - fromElevation) * Float(r) / Float(rings)
            let e1 = fromElevation + (top - fromElevation) * Float(r + 1) / Float(rings)
            let v0 = 0.5 + e0 / .pi, v1 = 0.5 + e1 / .pi
            for k in 0..<around {
                let u0 = Float(k) / Float(around), u1 = Float(k + 1) / Float(around)
                let a = point(u0, e0), b = point(u1, e0), cc = point(u1, e1), d = point(u0, e1)
                let inward = -simd_normalize((a + cc) / 2)
                mesh.quad(a, d, cc, b, uv: (SIMD2(u0, v0), SIMD2(u0, v1), SIMD2(u1, v1), SIMD2(u1, v0)), normal: inward)
            }
        }
        return mesh
    }

    /// The veil drifts; with reduce motion it holds still.
    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard let clouds, !c.reduceMotion else { return }
        let V = c.look.sky
        cloudYaw += Float(V.cloudDriftDegreesPerMinute / 60 * .pi / 180 * frame.dt)
        clouds.orientation = simd_quatf(angle: Float(V.yawDegrees * .pi / 180) + cloudYaw, axis: SIMD3(0, 1, 0))
    }
}
