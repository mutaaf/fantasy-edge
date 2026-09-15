import RealityKit
import simd

/// The night: the star dome, and the warm light dome a floodlit bowl throws
/// into the air above its rim. Stadium only; the table has the room. Reads
/// `visual.sky`, and the rim from `bowl` so the dome sits on it.
@MainActor
final class SkyActor: StadiumActor {
    let name = "sky"
    let root = Entity()

    init() { root.name = "actor.sky" }

    func build(_ c: StadiumContext) {
        clear()
        guard !c.tabletop else { return }
        let V = c.look.sky, s = c.spec
        let r = Float(V.radiusYards)
        let sky = ModelEntity(mesh: .generateSphere(radius: r),
                              materials: [StadiumLook.emissive("#FFFFFF", scale: 1, texture: c.assets.texture("sky.sky"), tile: false)])
        sky.name = "sky.stars"
        sky.scale = SIMD3(-1, 1, 1)
        root.addChild(sky)

        guard let top = c.tiers.last else { return }
        let rimOffset = top.outer + (s.bowl.rimLights.beyondOuter ?? 1)
        let standTop = top.rise[1]
        var dome = MeshBuilder()
        let S = 96
        for k in 0..<S {
            let t0 = Double(k) / Double(S) * 2 * .pi, t1 = Double(k + 1) / Double(S) * 2 * .pi
            let a = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset + 4, angle: t0)
            let b = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset + 4, angle: t1)
            let y0 = Float(standTop), y1 = Float(standTop + V.domeHeight)
            let u0 = Float(k) / Float(S), u1 = Float(k + 1) / Float(S)
            dome.quad(SIMD3(Float(a.x), y0, Float(a.z)), SIMD3(Float(b.x), y0, Float(b.z)),
                      SIMD3(Float(b.x), y1, Float(b.z)), SIMD3(Float(a.x), y1, Float(a.z)),
                      uv: (SIMD2(u0, 1), SIMD2(u1, 1), SIMD2(u1, 0), SIMD2(u0, 0)))
        }
        root.addChild(dome.entity("sky.dome", StadiumLook.glow(V.domeColor, opacity: V.domeOpacity,
                                                              texture: c.assets.texture("sky.haze"))))
    }
}
