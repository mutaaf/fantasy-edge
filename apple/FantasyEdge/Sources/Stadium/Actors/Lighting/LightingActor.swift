import RealityKit
import simd

/// The light: image-based light from the night probe, the rim light banks
/// with their burning lamp faces, bloom and haze, and the floodlights that
/// actually light the field and cast the goal posts' shadows. Strobes when
/// Moments asks. Reads `bowl.rimLights` and `visual.lighting`.
///
/// The composer points every model at `root` for image-based light, so the
/// probe hangs here. Publishes the bank positions to the blackboard.
@MainActor
final class LightingActor: StadiumActor {
    let name = "lighting"
    let root = Entity()
    private var glows: [ModelEntity] = []

    init() { root.name = "actor.lighting" }

    func build(_ c: StadiumContext) {
        clear()
        glows.removeAll()
        let s = c.spec, V = c.look.lighting, rim = V.rim, lights = s.bowl.rimLights
        let tabletop = c.tabletop
        if let env = c.assets.environment {
            root.components.set(ImageBasedLightComponent(source: .single(env),
                                                         intensityExponent: Float(V.probeIntensityExponent)))
        }
        let colour = s.palette[lights.color] ?? "#FFF8E6"
        guard let top = c.tiers.last else { return }
        let rimOffset = top.outer + (lights.beyondOuter ?? 1)
        let standTop = top.rise[1]
        let height = standTop + rim.heightAbove.value(tabletop: tabletop)
        let lamp = rim.lampYards.value(tabletop: tabletop)
        let glowSize = Float(rim.glowYards.value(tabletop: tabletop))
        let hazeLength = Float(rim.hazeLength.value(tabletop: tabletop))

        var positions: [SIMD3<Float>] = []
        for k in 0..<lights.count {
            let t = Double(k) * .pi / Double(max(1, lights.count / 2)) + rim.phase
            let p = SceneMath.bowlPoint(s.bowl.shape, offset: rimOffset, angle: t)
            if lights.side == "far" && p.z > rim.farSideMaxZ { continue }
            positions.append(SIMD3(Float(p.x), Float(height), Float(p.z)))
        }
        c.shared.banks = positions

        var poles = MeshBuilder(), faces = MeshBuilder(), haze = MeshBuilder()
        let glowTexture = c.assets.texture("lighting.glow")
        let glowMaterial = StadiumLook.glow(colour, opacity: rim.glowOpacity, texture: glowTexture)
        let hazeMaterial = StadiumLook.glow(colour, opacity: rim.hazeOpacity, texture: c.assets.texture("lighting.haze"))
        let coreMaterial = StadiumLook.glow(colour, opacity: rim.coreGlowOpacity, texture: glowTexture)
        let target = SIMD3<Float>(0, 0, 0)
        for p in positions {
            let pole = Float(rim.poleYards / 2)
            poles.box(min: SIMD3(p.x - pole, Float(standTop), p.z - pole), max: SIMD3(p.x + pole, p.y, p.z + pole))
            // The lamp face, turned to the field.
            let flat = simd_normalize(SIMD3(target.x - p.x, 0, target.z - p.z))
            let side = simd_normalize(simd_cross(SIMD3(0, 1, 0), flat))
            let w = Float(lamp[0] / 2), h = Float(lamp[1] / 2)
            let tilt = SIMD3<Float>(0, 1, 0) * h
            let at = p + flat * 0.4
            faces.quad(at - side * w - tilt, at + side * w - tilt, at + side * w + tilt, at - side * w + tilt, normal: flat)
            // The bloom, a wide halo and a hot core, always facing the eye.
            for (size, material, lift) in [(glowSize, glowMaterial, Float(0.6)),
                                           (glowSize * Float(rim.coreGlowScale), coreMaterial, Float(0.8))] {
                let g = ModelEntity(mesh: .generatePlane(width: size, height: size), materials: [material])
                g.position = at + flat * lift
                g.components.set(BillboardComponent())
                root.addChild(g)
                glows.append(g)
            }
            // A haze cone from the lamp toward the field.
            let aim = simd_normalize(target - p)
            var basisA = simd_cross(aim, SIMD3(0, 1, 0))
            if simd_length(basisA) < 1e-3 { basisA = SIMD3(1, 0, 0) }
            basisA = simd_normalize(basisA)
            let basisB = simd_normalize(simd_cross(aim, basisA))
            let sides = 12
            let far = p + aim * hazeLength
            let r0 = Float(max(lamp[0], lamp[1]) * rim.hazeStartScale)
            let r1 = Float(rim.hazeRadius) * (tabletop ? 0.45 : 1)
            for k in 0..<sides {
                let a0 = Float(k) / Float(sides) * 2 * .pi, a1 = Float(k + 1) / Float(sides) * 2 * .pi
                let d0 = basisA * cos(a0) + basisB * sin(a0), d1 = basisA * cos(a1) + basisB * sin(a1)
                let u0 = Float(k) / Float(sides), u1 = Float(k + 1) / Float(sides)
                haze.quad(p + d0 * r0, p + d1 * r0, far + d1 * r1, far + d0 * r1,
                          uv: (SIMD2(u0, 1), SIMD2(u1, 1), SIMD2(u1, 0), SIMD2(u0, 0)))
            }
        }
        root.addChild(poles.entity("rim.poles", StadiumLook.solid("#2B2E33", roughness: 0.5, metallic: 0.6)))
        // The lamps themselves blend additively, so they burn rather than sit.
        root.addChild(faces.entity("rim.lamps", StadiumLook.glow(colour, opacity: 1.0, texture: c.assets.texture("lighting.lampFace"))))
        root.addChild(haze.entity("rim.haze", hazeMaterial))

        // Floodlights that actually light: a few spots from the banks, aimed at
        // midfield, the first of them casting shadows.
        let flood = V.flood
        let chosen = stride(from: 0, to: positions.count, by: max(1, positions.count / max(1, flood.count)))
            .prefix(flood.count).map { positions[$0] }
        for (i, p) in chosen.enumerated() {
            let e = Entity()
            e.name = "flood.\(i)"
            e.position = p
            e.look(at: SIMD3(0, 0, 0), from: p, relativeTo: nil)
            let spot = SpotLightComponent(color: StadiumLook.color(colour),
                                          intensity: Float(tabletop ? flood.tabletopLumens : flood.lumens),
                                          innerAngleInDegrees: Float(flood.innerDegrees),
                                          outerAngleInDegrees: Float(flood.outerDegrees),
                                          attenuationRadius: Float(tabletop ? flood.tabletopReach : flood.reach))
            e.components.set(spot)
            if i < flood.shadows { e.components.set(SpotLightComponent.Shadow()) }
            root.addChild(e)
        }
    }

    /// The banks pulse while Moments has asked for a strobe, then settle.
    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        let m = c.look.moments
        let strobing = !c.reduceMotion && frame.time < c.shared.strobeUntil
        let pulse: Float
        if strobing {
            let wave = 0.5 + 0.5 * sin(frame.time * 2 * .pi * m.strobeHz)
            pulse = 1 + Float(wave * m.strobeGain)
        } else {
            pulse = 1
        }
        for g in glows where g.scale.x != pulse { g.scale = SIMD3(repeating: pulse) }
    }
}
