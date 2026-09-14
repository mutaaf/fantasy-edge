import RealityKit
import UIKit
import simd

/// The broadcast package drawn into the stadium: the drive's flight trails,
/// the ball, the beacon over it, the line of scrimmage and the line to gain,
/// the chains, and the win-probability ribbon.
@MainActor
final class StadiumBroadcast {
    let root = Entity()
    let tabletop: Bool
    let ball = ModelEntity()
    private let beacon = Entity()
    private let drive = Entity()
    private let lines = Entity()
    private let chains = Entity()
    private let horizon = Entity()
    private var trails: [String: (core: ModelEntity, halo: ModelEntity, style: String, color: String)] = [:]
    private var lastTrail: String?
    private var laserEntities: [String: Entity] = [:]
    private var chainParts: (scrimmage: Entity, gain: Entity, link: ModelEntity)?
    private var horizonKey = ""
    private var beaconKey = ""
    private var spin: Float = 0

    init(tabletop: Bool) {
        self.tabletop = tabletop
        root.name = "broadcast"
        [drive, lines, chains, horizon, beacon, ball].forEach { root.addChild($0) }
        ball.isEnabled = false
        beacon.isEnabled = false
        chains.isEnabled = false
    }

    // MARK: static parts, built with the stadium

    func build(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets) {
        // The football: a prolate spheroid in pebbled leather.
        var b = MeshBuilder()
        let L = Float(look.ball.lengthYards / 2), R = Float(look.ball.widthYards / 2)
        let profile: [(Float, Float)] = (0...20).map { i in
            let x = -L + 2 * L * Float(i) / 20
            let r = R * (max(0, 1 - (x / L) * (x / L))).squareRoot()
            return (x, max(0.002, r))
        }
        b.lathe(profile, sides: 24)
        var leather = PhysicallyBasedMaterial()
        if let t = assets.texture("football") {
            leather.baseColor = .init(tint: .white, texture: StadiumLook.clamped(t))
        } else {
            leather.baseColor = .init(tint: StadiumLook.color(look.ball.color))
        }
        leather.roughness = .init(floatLiteral: Float(look.ball.roughness))
        leather.faceCulling = .none
        if let mesh = b.resource("football") { ball.model = ModelComponent(mesh: mesh, materials: [leather]) }
        // A soft light on the ball, so at fifty yards you can still find it.
        ball.children.removeAll()
        let scale = Float(look.ball.scale.value(tabletop: tabletop))
        let glowSize = Float(look.ball.glow.yards.value(tabletop: tabletop)) / max(1e-3, scale)
        let glow = ModelEntity(mesh: .generatePlane(width: glowSize, height: glowSize),
                               materials: [StadiumLook.glow(s.palette["beacon"] ?? "#BFE3FF", opacity: look.ball.glow.opacity,
                                                            texture: assets.texture("glow"))])
        glow.components.set(BillboardComponent())
        ball.addChild(glow)
        ball.scale = SIMD3(repeating: Float(look.ball.scale.value(tabletop: tabletop)))
        ball.components.set(GroundingShadowComponent(castsShadow: true))
    }

    // MARK: the drive

    func clearDrive() {
        drive.children.removeAll()
        trails.removeAll()
        lastTrail = nil
    }

    func hasTrail(_ id: String) -> Bool { trails[id] != nil }

    /// Lay a play's trail down. The newest is bright; the rest of the drive
    /// ghosts behind it.
    func addTrail(_ arc: SceneSpec.Arc, spec s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets,
                  seat: SIMD3<Float>?) {
        guard trails[arc.id] == nil else { return }
        let colour = s.palette[arc.color] ?? "#FFFFFF"
        var core = look.trail.core.value(tabletop: tabletop)
        if let seat, !tabletop {
            core *= SceneMath.nearSeatScale(SceneMath.samples(arc, count: 32), seat: seat, rule: look.trail.nearSeat)
        }
        let emphasis = arc.style == "score"
        var coreB = MeshBuilder(), haloB = MeshBuilder()
        let pieces = SceneMath.dashes(arc, count: 64)
        let total = Float(pieces.count)
        for (i, piece) in pieces.enumerated() {
            let lo = Float(i) / total, hi = Float(i + 1) / total
            coreB.tube(piece, radius: Float(core * (emphasis ? look.trail.scoreEmphasis.core : 1)), sides: 8, uRange: lo...hi)
        }
        haloB.tube(SceneMath.samples(arc, count: 64), radius: Float(core * look.trail.haloScale * (emphasis ? look.trail.scoreEmphasis.halo : 1)), sides: 8)
        let holder = Entity()
        holder.name = "trail.\(arc.id)"
        let coreE = coreB.entity("trail.core", StadiumLook.glow(colour, opacity: 1, texture: assets.texture("trail")))
        let haloE = haloB.entity("trail.halo", StadiumLook.glow(colour, opacity: look.trail.haloOpacity * (emphasis ? look.trail.scoreEmphasis.halo : 1),
                                                                texture: assets.texture("trail")))
        holder.addChild(haloE)
        holder.addChild(coreE)
        drive.addChild(holder)
        if let last = lastTrail, let prev = trails[last] {
            let ghost = look.trail.ghostOpacity
            let c = s.palette[prev.color] ?? "#FFFFFF"
            prev.core.model?.materials = [StadiumLook.glow(c, opacity: ghost, texture: assets.texture("trail"))]
            prev.halo.model?.materials = [StadiumLook.glow(c, opacity: look.trail.haloOpacity * ghost, texture: assets.texture("trail"))]
        }
        trails[arc.id] = (coreE, haloE, arc.style, arc.color)
        lastTrail = arc.id
    }

    /// Put the ball at a point on an arc, nose along its flight, spinning.
    func placeBall(on arc: SceneSpec.Arc, at t: Double, dt: Double, look: SceneSpec.Look) {
        ball.isEnabled = true
        let p = SceneMath.point(on: arc, at: t)
        let q = SceneMath.point(on: arc, at: min(1, t + 0.02))
        let back = SceneMath.point(on: arc, at: max(0, t - 0.02))
        var dir = q - back
        if simd_length(dir) < 1e-5 { dir = SIMD3(Float(arc.toX >= arc.fromX ? 1 : -1), 0, 0) }
        spin += Float(look.ball.spinPerSecond * dt) * 2 * .pi
        let aim = simd_quatf(from: SIMD3(1, 0, 0), to: simd_normalize(dir))
        ball.orientation = aim * simd_quatf(angle: spin, axis: SIMD3(1, 0, 0))
        ball.position = p + SIMD3(0, Float(look.ball.liftYards) * 0.25, 0)
    }

    // MARK: lines, beacon, chains

    func settle(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, animated: Bool) {
        let duration = animated ? 0.35 : 0
        guard let b = s.ball else {
            ball.isEnabled = false
            beacon.isEnabled = false
            chains.isEnabled = false
            for (_, e) in laserEntities { e.isEnabled = false }
            return
        }
        ball.isEnabled = true
        let rest = SceneMath.local(x: b.x, y: look.ball.liftYards * 0.5, z: b.z)
        move(ball, to: rest, duration: duration)
        ball.orientation = simd_quatf(angle: 0, axis: SIMD3(0, 1, 0))

        let height = b.beacon.height
        let key = "\(height)|\(b.beacon.color)"
        if key != beaconKey {
            beaconKey = key
            beacon.children.removeAll()
            let w = Float(look.beacon.width.value(tabletop: tabletop))
            let colour = s.palette[b.beacon.color] ?? "#BFE3FF"
            let material = StadiumLook.glow(colour, opacity: look.beacon.opacity, texture: assets.texture("beam"))
            for k in 0..<2 {
                var q = MeshBuilder()
                let a = Float(k) * .pi / 2
                let side = SIMD3(cos(a), 0, sin(a)) * (w / 2)
                let top = SIMD3<Float>(0, Float(height), 0)
                q.quad(-side, side, side + top, -side + top, uv: (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, 1), SIMD2(0, 1)))
                beacon.addChild(q.entity("beacon.\(k)", material))
            }
        }
        beacon.isEnabled = true
        move(beacon, to: SceneMath.local(x: b.x, y: 0, z: b.z), duration: duration)

        let want = Dictionary(uniqueKeysWithValues: s.lasers.map { ($0.kind, $0) })
        for (kind, e) in laserEntities where want[kind] == nil { e.isEnabled = false }
        for (kind, laser) in want {
            let e = laserEntities[kind] ?? makeLaser(laser, s: s, look: look, assets: assets)
            laserEntities[kind] = e
            e.isEnabled = true
            move(e, to: SceneMath.local(x: laser.x, y: look.laser.lift), duration: duration)
        }

        if let props = s.field.props, let scrimmage = want["scrimmage"] {
            let parts = chainParts ?? makeChains(s, props: props, look: look)
            chainParts = parts
            chains.isEnabled = true
            let z = (props.chains.side == "away" ? -1 : 1) * (s.field.width / 2 + props.chains.offset)
            move(parts.scrimmage, to: SceneMath.local(x: scrimmage.x, z: z), duration: duration)
            if let gain = want["lineToGain"] {
                parts.gain.isEnabled = true
                parts.link.isEnabled = true
                move(parts.gain, to: SceneMath.local(x: gain.x, z: z), duration: duration)
                let lo = min(scrimmage.x, gain.x), len = abs(gain.x - scrimmage.x)
                parts.link.scale = SIMD3(Float(max(0.01, len)), 1, 1)
                move(parts.link, to: SceneMath.local(x: lo, y: props.chains.poleHeight * 0.85, z: z), duration: duration)
            } else {
                parts.gain.isEnabled = false
                parts.link.isEnabled = false
            }
        } else {
            chains.isEnabled = false
        }
    }

    private func makeLaser(_ laser: SceneSpec.Laser, s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets) -> Entity {
        let holder = Entity()
        holder.name = "laser.\(laser.kind)"
        let colour = s.palette[laser.color] ?? "#FFD400"
        let half = s.field.width / 2
        var core = MeshBuilder(), glow = MeshBuilder()
        core.stripe(from: SIMD2(50, -half), to: SIMD2(50, half), width: look.laser.width, y: 0, tile: 1)
        glow.stripe(from: SIMD2(50, -half), to: SIMD2(50, half), width: look.laser.glowWidth, y: -0.002, tile: 1)
        let c = core.entity("laser.core", StadiumLook.emissive(colour, scale: 1))
        let g = glow.entity("laser.glow", StadiumLook.glow(colour, opacity: look.laser.glowOpacity, texture: assets.texture("paint"), tile: true))
        StadiumLook.ground(g, order: 4)
        StadiumLook.ground(c, order: 5)
        holder.addChild(g)
        holder.addChild(c)
        lines.addChild(holder)
        return holder
    }

    private func makeChains(_ s: SceneSpec, props: SceneSpec.Props, look: SceneSpec.Look)
        -> (scrimmage: Entity, gain: Entity, link: ModelEntity) {
        let colour = s.palette[props.chains.color] ?? "#FF6A13"
        let material = StadiumLook.solid(colour, roughness: 0.5)
        func pole(_ name: String) -> Entity {
            var p = MeshBuilder()
            let h = Float(props.chains.poleHeight), w = Float(props.chains.markerWidth / 2)
            p.box(min: SIMD3(-0.04, 0, -0.04), max: SIMD3(0.04, h, 0.04))
            p.box(min: SIMD3(-w, h - 0.15, -0.05), max: SIMD3(w, h + 0.25, 0.05))
            let e = p.entity(name, material)
            chains.addChild(e)
            return e
        }
        var link = MeshBuilder()
        link.box(min: SIMD3(0, -0.02, -0.02), max: SIMD3(1, 0.02, 0.02))
        let l = link.entity("chains.link", StadiumLook.solid("#B8B4AE", roughness: 0.4, metallic: 0.8))
        chains.addChild(l)
        return (pole("chains.scrimmage"), pole("chains.gain"), l)
    }

    // MARK: horizon

    func updateHorizon(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets) {
        let key = "\(s.winProbability.series.count)|\(s.winProbability.series.last ?? -1)"
        guard key != horizonKey else { return }
        horizonKey = key
        horizon.children.removeAll()
        let pts = SceneMath.horizon(s.winProbability)
        guard pts.count > 1 else { return }
        let h = s.winProbability.horizon
        let thick = Float(look.horizon.thickness.value(tabletop: tabletop))
        let ink = s.palette["ink"] ?? "#F7F6F2"
        var ribbon = MeshBuilder()
        for i in 0..<(pts.count - 1) {
            let a = pts[i], b = pts[i + 1]
            let up = SIMD3<Float>(0, thick / 2, 0)
            ribbon.quad(a - up, b - up, b + up, a + up,
                        uv: (SIMD2(0.5, 0), SIMD2(0.5, 0), SIMD2(0.5, 1), SIMD2(0.5, 1)), normal: SIMD3(0, 0, 1))
        }
        horizon.addChild(ribbon.entity("horizon.line", StadiumLook.glow(ink, opacity: look.horizon.opacity, texture: assets.texture("glow"))))
        // The area between even and the line, in the colour of whoever it favours.
        let mid = Float((h.y0 + h.y1) / 2)
        var homeFill = MeshBuilder(), awayFill = MeshBuilder()
        let series = s.winProbability.series
        for i in 0..<(pts.count - 1) {
            let a = pts[i], b = pts[i + 1]
            let favoursHome = (series[i] + series[i + 1]) / 2 >= 0.5
            let quadA = SIMD3(a.x, mid, a.z), quadB = SIMD3(b.x, mid, b.z)
            if favoursHome == (s.winProbability.side == "home") {
                homeFill.quad(quadA, quadB, b, a, normal: SIMD3(0, 0, 1))
            } else {
                awayFill.quad(quadA, quadB, b, a, normal: SIMD3(0, 0, 1))
            }
        }
        let fill = look.horizon.fillOpacity
        horizon.addChild(homeFill.entity("horizon.fill.home", StadiumLook.glow(s.teams.home.chip, opacity: fill, texture: nil)))
        horizon.addChild(awayFill.entity("horizon.fill.away", StadiumLook.glow(s.teams.away.chip, opacity: fill, texture: nil)))
        // Say what it is: the club at the top rail is the one the line climbs toward.
        let size = CGFloat(look.horizon.labelHeight.value(tabletop: tabletop))
        let labelMaterial = StadiumLook.glow(ink, opacity: look.horizon.labelOpacity, texture: nil)
        let top = s.winProbability.side == "home" ? s.teams.home : s.teams.away
        let bottom = s.winProbability.side == "home" ? s.teams.away : s.teams.home
        for (text, y) in [(top.abbr, h.y1), (bottom.abbr, h.y0), ("WIN PROBABILITY", (h.y0 + h.y1) / 2)] {
            let mesh = MeshResource.generateText(text, extrusionDepth: 0.01, font: .systemFont(ofSize: size, weight: .bold),
                                                 containerFrame: .zero, alignment: .right, lineBreakMode: .byClipping)
            let label = ModelEntity(mesh: mesh, materials: [labelMaterial])
            let bounds = mesh.bounds
            label.position = SceneMath.local(x: h.x0, y: y, z: h.z) - SIMD3(bounds.max.x + Float(size) * 0.8, bounds.center.y, 0)
            horizon.addChild(label)
        }
        var rails = MeshBuilder()
        for y in [h.y0, (h.y0 + h.y1) / 2, h.y1] {
            let a = SceneMath.local(x: h.x0, y: y, z: h.z), b = SceneMath.local(x: h.x1, y: y, z: h.z)
            let up = SIMD3<Float>(0, thick * 0.12, 0)
            rails.quad(a - up, b - up, b + up, a + up, normal: SIMD3(0, 0, 1))
        }
        horizon.addChild(rails.entity("horizon.rails", StadiumLook.glow(ink, opacity: look.horizon.railOpacity, texture: nil)))
    }

    private func move(_ e: Entity, to at: SIMD3<Float>, duration: Double) {
        if duration <= 0 || !e.isEnabled {
            e.position = at
        } else {
            e.move(to: Transform(scale: e.scale, rotation: e.orientation, translation: at),
                   relativeTo: e.parent, duration: duration, timingFunction: .easeInOut)
        }
    }
}
