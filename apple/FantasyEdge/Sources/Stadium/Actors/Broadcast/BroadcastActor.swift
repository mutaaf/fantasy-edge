import RealityKit
import UIKit
import simd

/// The broadcast package drawn into the stadium: the drive's flight trails,
/// the ball that flies them, the beacon over it, the line of scrimmage and
/// the line to gain painted in light with the down-and-distance tag beside
/// them, the ribbon board's crawl, the moment graphic and the win-probability
/// horizon.
/// Reads the scene's drives, ball, lasers and win probability, and
/// `visual.broadcast`. The parts live beside this file: BroadcastTrails,
/// BroadcastHorizon, BroadcastBoards (ribbon and tag), BroadcastBanner and
/// BroadcastFlight.
@MainActor
final class BroadcastActor: StadiumActor {
    let name = "broadcast"
    let root = Entity()
    private(set) var tabletop = false
    let ball = ModelEntity()
    private let beacon = Entity()
    private let lines = Entity()
    private let tag = ModelEntity()
    private let trails = BroadcastTrails()
    private let horizon = BroadcastHorizon()
    private let ribbon = BroadcastRibbon()
    private let banner = BroadcastBanner()
    private let board = BroadcastVideoBoard()
    private var laserEntities: [String: Entity] = [:]
    private var beaconKey = ""
    private var tagKey = ""

    private var driveID = ""
    private var motion = PlayMotion()
    private var flight: (arc: SceneSpec.Arc, elapsed: Double, duration: Double, manner: BallFlight.Manner)?

    init() {
        root.name = "actor.broadcast"
        [trails.root, lines, tag, horizon.root, beacon, ball, ribbon.root, banner.root, board.root].forEach { root.addChild($0) }
        ball.isEnabled = false
        beacon.isEnabled = false
        tag.isEnabled = false
    }

    // MARK: the ball

    private func buildBall(_ c: StadiumContext) {
        let s = c.spec, look = c.look.broadcast.ball
        ball.children.removeAll()
        ball.model = nil
        let key = s.league == "college-football" ? "broadcast.footballCollege" : "broadcast.footballNFL"
        if let model = c.assets.model(key) {
            // Authored in metres with its long axis on +x and laces up.
            model.scale = SIMD3(repeating: Float(1 / look.modelMetersPerYard))
            model.name = "football"
            ball.addChild(model)
        } else {
            // Without the asset: the old lathed spheroid, so the ball is never missing.
            var b = MeshBuilder()
            let L = Float(look.lengthYards / 2), R = Float(look.widthYards / 2)
            let profile: [(Float, Float)] = (0...20).map { i in
                let x = -L + 2 * L * Float(i) / 20
                return (x, max(0.002, R * (max(0, 1 - (x / L) * (x / L))).squareRoot()))
            }
            b.lathe(profile, sides: 24)
            var leather = PhysicallyBasedMaterial()
            if let t = c.assets.texture("broadcast.football") {
                leather.baseColor = .init(tint: .white, texture: StadiumLook.clamped(t))
            } else {
                leather.baseColor = .init(tint: StadiumLook.color(look.color))
            }
            leather.roughness = .init(floatLiteral: Float(look.roughness))
            leather.faceCulling = .none
            if let mesh = b.resource("football") { ball.model = ModelComponent(mesh: mesh, materials: [leather]) }
        }
        // A soft light on the ball, so at fifty yards you can still find it.
        let scale = Float(look.scale.value(tabletop: tabletop))
        let glowSize = Float(look.glow.yards.value(tabletop: tabletop)) / max(1e-3, scale)
        let glow = ModelEntity(mesh: .generatePlane(width: glowSize, height: glowSize),
                               materials: [StadiumLook.glow(s.palette["beacon"] ?? "#BFE3FF", opacity: look.glow.opacity,
                                                            texture: c.assets.texture("broadcast.glow"))])
        glow.name = "football.glow"
        glow.components.set(BillboardComponent())
        ball.addChild(glow)
        ball.scale = SIMD3(repeating: scale)
    }

    // MARK: lines, tag, beacon

    func settle(_ c: StadiumContext, animated: Bool) {
        let s = c.spec, look = c.look
        let duration = animated ? 0.35 : 0
        guard let b = s.ball else {
            ball.isEnabled = false
            beacon.isEnabled = false
            tag.isEnabled = false
            for (_, e) in laserEntities { e.isEnabled = false }
            return
        }
        ball.isEnabled = true
        let rest = SceneMath.local(x: b.x, y: look.broadcast.ball.liftYards * 0.5, z: b.z)
        // Orientation first: writing a transform while move(to:) runs cancels
        // the animation, and the ball stayed wherever it started - the fifty.
        ball.orientation = simd_quatf(angle: 0, axis: SIMD3(0, 1, 0))
        move(ball, to: rest, duration: simd_distance(ball.position, rest) > 15 ? 0 : duration)

        let height = b.beacon.height
        let key = "\(height)|\(b.beacon.color)"
        if key != beaconKey {
            beaconKey = key
            beacon.children.removeAll()
            let w = Float(look.broadcast.beacon.width.value(tabletop: tabletop))
            let colour = s.palette[b.beacon.color] ?? "#BFE3FF"
            let material = StadiumLook.glow(colour, opacity: look.broadcast.beacon.opacity, texture: c.assets.texture("broadcast.beam"))
            // Two crossed cards in one mesh: one draw part, not two.
            var q = MeshBuilder()
            for k in 0..<2 {
                let a = Float(k) * .pi / 2
                let side = SIMD3(cos(a), 0, sin(a)) * (w / 2)
                let top = SIMD3<Float>(0, Float(height), 0)
                q.quad(-side, side, side + top, -side + top, uv: (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, 1), SIMD2(0, 1)))
            }
            beacon.addChild(q.entity("beacon", material))
        }
        beacon.isEnabled = true
        move(beacon, to: SceneMath.local(x: b.x, y: 0, z: b.z), duration: duration)

        let want = Dictionary(uniqueKeysWithValues: s.lasers.map { ($0.kind, $0) })
        for (kind, e) in laserEntities where want[kind] == nil { e.isEnabled = false }
        for (kind, laser) in want {
            let e = laserEntities[kind] ?? makeLine(laser, c)
            laserEntities[kind] = e
            e.isEnabled = true
            move(e, to: SceneMath.local(x: laser.x, y: look.broadcast.laser.lift), duration: duration)
        }
        // The physical chains and down box are Sideline's; Broadcast only paints.
        placeTag(c, scrimmage: want["scrimmage"], gain: want["lineToGain"], duration: duration)
    }

    /// A line in light on the grass: feathered, broken by blades, sorted
    /// after the paint so it never flickers through it.
    private func makeLine(_ laser: SceneSpec.Laser, _ c: StadiumContext) -> Entity {
        let s = c.spec, look = c.look.broadcast.laser
        let holder = Entity()
        holder.name = "line.\(laser.kind)"
        let colour = s.palette[laser.color] ?? "#FFD400"
        let half = s.field.width / 2
        let tex = c.assets.texture("broadcast.line")
        // No glow strip under it: a painted line does not glow, and at 10%
        // it cost a draw part per line for nothing anyone could see.
        var core = MeshBuilder()
        core.stripe(from: SIMD2(50, -half), to: SIMD2(50, half), width: look.width, y: 0, tile: 2)
        var paint = UnlitMaterial(applyPostProcessToneMap: false)
        if let tex {
            let t = StadiumLook.repeating(tex)
            paint.color = .init(tint: StadiumLook.color(colour), texture: t)
            paint.blending = .transparent(opacity: .init(scale: Float(look.opacity), texture: t))
        } else {
            paint.color = .init(tint: StadiumLook.color(colour))
            paint.blending = .transparent(opacity: .init(floatLiteral: Float(look.opacity)))
        }
        paint.writesDepth = false
        paint.faceCulling = .none
        let p = core.entity("line.paint", paint)
        StadiumLook.ground(p, order: 5)
        holder.addChild(p)
        lines.addChild(holder)
        return holder
    }

    /// "3RD & 6" painted on the far half of the field beside the line of
    /// scrimmage, reading toward whoever is watching.
    private func placeTag(_ c: StadiumContext, scrimmage: SceneSpec.Laser?, gain: SceneSpec.Laser?, duration: Double) {
        let s = c.spec, look = c.look.broadcast.laser.tag
        let text = s.status.downDistance.components(separatedBy: " at ").first ?? ""
        guard let scrimmage, !text.isEmpty else {
            tag.isEnabled = false
            return
        }
        let h = Float(look.heightYards.value(tabletop: tabletop))
        let eye = c.shared.seat.flatMap { tabletop ? nil : $0 }
        let viewZ: Float = eye.map { $0.z >= 0 ? 1 : -1 } ?? 1
        let k = "\(text)|\(h)|\(viewZ)"
        if k != tagKey, let img = BroadcastGraphics.tag(text, look: look),
           let m = BroadcastGraphics.overlay(img, opacity: look.opacity) {
            tagKey = k
            let w = h * Float(img.width) / Float(max(1, img.height))
            // Lying on the grass: text runs along +x, its top points away from the seat.
            var q = MeshBuilder()
            let up = SIMD3<Float>(0, 0, -viewZ) * (h / 2), right = SIMD3<Float>(viewZ, 0, 0) * (w / 2)
            q.quad(-right - up, right - up, right + up, -right + up,
                   uv: (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, 1), SIMD2(0, 1)), normal: SIMD3(0, 1, 0))
            if let mesh = q.resource("tag") { tag.model = ModelComponent(mesh: mesh, materials: [m]) }
            StadiumLook.ground(tag, order: 6)
            tag.name = "line.tag"
        }
        let ahead = gain.map { $0.x >= scrimmage.x ? 1.0 : -1.0 } ?? 1.0
        let z = -Double(viewZ) * (s.field.width / 2 - look.fromSideline)
        let wYards = Double(tag.model?.mesh.bounds.extents.x ?? 0)
        let x = scrimmage.x + ahead * (look.aheadYards + wYards / 2)
        tag.isEnabled = true
        move(tag, to: SceneMath.local(x: x, y: c.look.broadcast.laser.lift * 2, z: z), duration: duration)
    }

    private func move(_ e: Entity, to at: SIMD3<Float>, duration: Double) {
        // An entity not yet in a scene ignores move(to:) without a word: on a
        // paused replay the first scene arrives before the stadium is on
        // stage, no second one follows, and the ball sat at the origin - the
        // fifty - sunk in the grass. Place it outright until there is a scene.
        if duration <= 0 || !e.isEnabled || e.scene == nil {
            e.position = at
        } else {
            e.move(to: Transform(scale: e.scale, rotation: e.orientation, translation: at),
                   relativeTo: e.parent, duration: duration, timingFunction: .easeInOut)
        }
    }
}

// MARK: - actor

extension BroadcastActor {
    func build(_ c: StadiumContext) {
        tabletop = c.tabletop
        trails.clear()
        horizon.clear()
        banner.clear()
        motion.reset()
        driveID = ""
        flight = nil
        beaconKey = ""
        tagKey = ""
        laserEntities.values.forEach { $0.removeFromParent() }
        laserEntities.removeAll()
        buildBall(c)
        ribbon.build(c)
        board.build(c)
    }

    func apply(_ c: StadiumContext, previous: SceneSpec?) {
        updateDrive(c, previous: previous)
        horizon.update(c)
        ribbon.apply(c, previous: previous)
        board.apply(c)
        if flight == nil { settle(c, animated: !c.reduceMotion) }
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        ribbon.moment(event, c)
        if case .moment(let m) = event { banner.arrive(m, c) }
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        ribbon.update(frame, c)
        banner.update(c)
        trails.update(c)
        guard var f = flight else { return }
        f.elapsed += frame.dt
        let t = min(1, f.elapsed / f.duration)
        // Ease the flight: quick off the snap, settling into the catch.
        let eased = 1 - pow(1 - t, c.spec.motion.flightEase ?? 1.6)
        let look = c.look.broadcast.ball
        let pose = BallFlight.pose(f.arc, t: eased, elapsed: c.reduceMotion ? 0 : f.elapsed, manner: f.manner,
                                   flight: look.flight, lift: Float(look.liftYards) * 0.25)
        ball.isEnabled = true
        ball.position = pose.position
        ball.orientation = pose.orientation
        if t >= 1 {
            Self.trace(c, "land \(f.arc.id) at y \(ball.position.y)")
            trails.clearLive()
            trails.add(f.arc, c)
            flight = nil
            startNextFlight(c)
        } else {
            // The trail grows behind the ball as far as it has flown.
            trails.grow(f.arc, to: eased, c)
            flight = f
        }
    }

    func hasTrail(_ id: String) -> Bool { trails.has(id) }

    /// Look-dev only (`-trailTrace`, DEBUG builds): what the drive did and when.
    static func trace(_ c: StadiumContext, _ what: String) {
        #if DEBUG
        guard ProcessInfo.processInfo.arguments.contains("-trailTrace") else { return }
        let line = String(format: "[stadium-trace] t=%.2f ", c.shared.time) + what
        StadiumLog.log.notice("\(line, privacy: .public)")
        #endif
    }

    /// Lay the drive again from scratch - after a seat change, say.
    func redrawDrive(_ c: StadiumContext) {
        trails.clear()
        motion.reset()
        driveID = ""
        flight = nil
        tagKey = ""
        updateDrive(c, previous: nil)
        settle(c, animated: false)
        // The seat moved: the horizon's edge-on fade is per seat.
        horizon.update(c)
    }

    // MARK: the drive

    private func updateDrive(_ c: StadiumContext, previous: SceneSpec?) {
        let s = c.spec
        guard let drive = s.shownDrive else {
            trails.clear()
            motion.reset()
            driveID = ""
            flight = nil
            return
        }
        let oldIDs = Set(previous?.shownDrive?.arcs.map(\.id) ?? [])
        let lostAPlay = !oldIDs.isEmpty && drive.id == driveID
            && !oldIDs.isSubset(of: Set(drive.arcs.map(\.id)))
        // A new drive right after the old one is the game moving on, and its
        // plays fly. Anything else - a scrub, a jump, the first scene of all -
        // is history, and is laid down at rest.
        let nextDrive = previous.map { p in
            drive.id != driveID && s.drives.count >= p.drives.count
                && s.drives.firstIndex(where: { $0.id == drive.id }) == (p.drives.firstIndex(where: { $0.id == driveID }) ?? -2) + 1
        } ?? false
        Self.trace(c, "scene drive=\(drive.id) shown=\(driveID) arcs=\(drive.arcs.count) last=\(drive.arcs.last?.id ?? "-") lost=\(lostAPlay) next=\(nextDrive) flight=\(flight?.arc.id ?? "-")")
        if drive.id != driveID || lostAPlay {
            trails.clear()
            motion.reset()
            flight = nil
            driveID = drive.id
            let initial = !nextDrive
            _ = motion.arrive(drive, initial: initial)
            if initial {
                trails.set(drive.arcs, c)
                return
            }
        } else {
            _ = motion.arrive(drive, initial: false)
        }
        startNextFlight(c)
    }

    private func startNextFlight(_ c: StadiumContext) {
        guard flight == nil else { return }
        guard let (arc, seconds) = motion.next(reduceMotion: c.reduceMotion, floor: c.spec.motion.floorSeconds) else {
            settle(c, animated: !c.reduceMotion)
            return
        }
        if seconds <= 0 {
            trails.add(arc, c)
            startNextFlight(c)
        } else {
            flight = (arc, 0, seconds, BallFlight.manner(arc, c.look.broadcast.ball.flight))
            Self.trace(c, "fly \(arc.id) \(arc.type) \(seconds)s")
        }
    }
}
