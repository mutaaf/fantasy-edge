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
    /// The play under way: `elapsed` animation seconds into `duration`, and
    /// where a kick at the posts leaves play.
    private var flight: (arc: SceneSpec.Arc, elapsed: Double, duration: Double, cut: Double?)?
    /// A drive waiting for the play on the field to finish before it shows.
    private var heldSince: Double?
    /// When the next play may snap: plays keep a beat between them.
    private var beatUntil: Double?
    /// One card on the grass under the play: the snap's ring, then the ball's shadow.
    private let marker = ModelEntity()
    private var markerMode = ""

    init() {
        root.name = "actor.broadcast"
        [trails.root, lines, tag, horizon.root, beacon, marker, ball, ribbon.root, banner.root, board.root].forEach { root.addChild($0) }
        ball.isEnabled = false
        beacon.isEnabled = false
        tag.isEnabled = false
        marker.isEnabled = false
        marker.name = "play.marker"
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
        beatUntil = nil
        heldSince = nil
        buildMarker(c)
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
        guard var f = flight else {
            if let until = beatUntil, c.shared.time >= until {
                beatUntil = nil
                startNextFlight(c)
            }
            // The drive that was waiting for this play can come on now.
            if heldSince != nil, flight == nil, motion.queue.isEmpty, beatUntil == nil {
                heldSince = nil
                updateDrive(c, previous: nil)
                settle(c, animated: !c.reduceMotion)
            }
            return
        }
        f.elapsed += frame.dt
        var t = min(1, f.elapsed / max(1e-3, f.duration))
        // The path is timed in real seconds; a fast replay plays it faster.
        let real = f.arc.path?.seconds ?? f.arc.seconds
        // A kick is over when it passes the posts, wherever its arc ends.
        if let cut = f.cut, real > 0, t * real >= cut { t = 1 }
        let seconds = min(t * real, f.cut ?? real)
        let look = c.look.broadcast.ball
        let scale = Float(look.scale.value(tabletop: tabletop))
        let pose = BallFlight.pose(f.arc, seconds: seconds, flight: look.flight,
                                   floor: Float(look.widthYards) * scale / 2)
        ball.isEnabled = true
        ball.position = pose.position
        ball.orientation = pose.orientation
        placeMarker(f.arc, seconds: seconds, ball: pose.position, c)
        if t >= 1 {
            Self.trace(c, "land \(f.arc.id) at y \(ball.position.y) cut=\(f.cut.map { String(format: "%.1f", $0) } ?? "-")")
            trails.clearLive()
            trails.add(f.arc, c, cut: f.cut)
            flight = nil
            marker.isEnabled = false
            setGlow(airborne: false, c)
            // A kick that has passed the posts is out of play: the ball is
            // gone until the next snap gives it a spot on the field.
            if f.cut != nil { ball.isEnabled = false }
            // A beat before the next snap, shortened as a fast replay shortens the play.
            let beat = c.look.broadcast.play.beatSeconds * (f.duration / max(1e-3, real))
            if motion.queue.isEmpty || c.reduceMotion {
                startNextFlight(c)
            } else {
                settle(c, animated: true)
                beatUntil = c.shared.time + beat
            }
        } else {
            // The trail grows behind the ball as far as it has gone.
            trails.grow(f.arc, seconds: seconds, c)
            setGlow(airborne: SceneMath.ball(on: f.arc, at: seconds).segment?.kind == "air", c)
            flight = f
        }
    }

    // MARK: the snap ring and the ball's shadow

    private func buildMarker(_ c: StadiumContext) {
        markerMode = ""
        marker.isEnabled = false
        var q = MeshBuilder()
        q.quad(SIMD3(-0.5, 0, 0.5), SIMD3(0.5, 0, 0.5), SIMD3(0.5, 0, -0.5), SIMD3(-0.5, 0, -0.5),
               uv: (SIMD2(0, 0), SIMD2(1, 0), SIMD2(1, 1), SIMD2(0, 1)), normal: SIMD3(0, 1, 0))
        if let mesh = q.resource("play.marker") { marker.model = ModelComponent(mesh: mesh, materials: []) }
        StadiumLook.ground(marker, order: 7)
    }

    /// Under the play: a ring that swells and fades from the snap spot while
    /// the ball sits there and is snapped, then the ball's soft shadow on the
    /// grass, smaller and fainter the higher it flies, so depth reads.
    private func placeMarker(_ arc: SceneSpec.Arc, seconds: Double, ball at: SIMD3<Float>, _ c: StadiumContext) {
        let look = c.look.broadcast.play.marker
        let segment = SceneMath.ball(on: arc, at: seconds).segment
        let lift = Float(c.look.broadcast.laser.lift) * 3
        guard arc.path != nil, !c.reduceMotion else { marker.isEnabled = false; return }
        let pulse = seconds < (arc.path?.segments.first?.seconds ?? 0) + look.pulseSeconds
        let mode = pulse ? "pulse" : "shadow"
        if mode != markerMode, var model = marker.model {
            markerMode = mode
            let tex = c.assets.texture("broadcast.glow")
            if pulse {
                var m = StadiumLook.glow(c.spec.palette[look.pulseColor] ?? "#A6D0FF", opacity: 1, texture: tex)
                m.faceCulling = .none
                model.materials = [m]
            } else {
                var m = UnlitMaterial(applyPostProcessToneMap: false)
                m.color = .init(tint: .black)
                if let tex {
                    m.blending = .transparent(opacity: .init(scale: 1, texture: StadiumLook.clamped(tex)))
                } else {
                    m.blending = .transparent(opacity: .init(floatLiteral: 1))
                }
                m.writesDepth = false
                m.faceCulling = .none
                model.materials = [m]
            }
            marker.model = model
        }
        marker.isEnabled = true
        if pulse {
            let start = arc.path?.segments.first?.seconds ?? 0
            // A small glow on the spot while the ball waits; it swells and fades on the snap.
            let k = Float(max(0, min(1, (seconds - start + look.pulseSeconds * 0.35) / look.pulseSeconds)))
            let size = Float(look.pulseYards.value(tabletop: tabletop)) * (0.35 + 0.65 * k)
            marker.scale = SIMD3(size, 1, size)
            marker.position = SIMD3(at.x, lift, at.z)
            marker.components.set(OpacityComponent(opacity: Float(look.pulseOpacity) * (1 - k * k)))
            setGlow(airborne: false, c)
        } else {
            let height = max(0, at.y)
            let fade = max(0, 1 - height / Float(max(0.1, look.shadowFadeYards)))
            let size = Float(look.shadowYards.value(tabletop: tabletop)) * (1 + height * 0.06)
            marker.scale = SIMD3(size, 1, size)
            marker.position = SIMD3(at.x, lift, at.z)
            marker.components.set(OpacityComponent(opacity: Float(look.shadowOpacity) * fade))
            setGlow(airborne: segment?.kind == "air", c)
        }
    }

    /// The ball's light: bigger while it flies, and never smaller at the eye
    /// than `glow.minArcMinutes`, so it reads from the upper deck as well as
    /// from the front row. It also sits `glow.coverYards` toward the wearer:
    /// at a hundred yards the leather is a third of a degree wide and a halo
    /// behind it reads as a dark dot ringed with light (integration-12).
    private func setGlow(airborne: Bool, _ c: StadiumContext) {
        guard let glow = ball.children.first(where: { $0.name == "football.glow" }) else { return }
        let look = c.look.broadcast.ball.glow
        let base = look.yards.value(tabletop: tabletop)
        var want = base * (airborne ? c.look.broadcast.play.flightGlowScale : 1)
        var toward = SIMD3<Float>(0, 0, 0)
        if let seat = c.shared.seat, !c.tabletop {
            let away = seat - ball.position
            let distance = Double(simd_length(away))
            if distance > 1e-3 {
                let floorYards = 2 * distance * tan(look.minArcMinutes / 60 * .pi / 180 / 2)
                want = min(look.maxYards, max(want, floorYards))
                toward = simd_normalize(away) * Float(look.coverYards)
            }
        }
        let scale = Float(want / max(1e-3, base))
        if abs(glow.scale.x - scale) > 1e-3 { glow.scale = SIMD3(repeating: scale) }
        // The child sits in the ball's own space, which spins with the
        // spiral: without undoing that rotation the light swam behind the
        // leather and back, and the ball read as a dark dot in a ring.
        let local = ball.orientation.inverse.act(toward) / max(1e-3, ball.scale.x)
        if simd_distance(glow.position, local) > 1e-3 { glow.position = local }
    }

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
        beatUntil = nil
        marker.isEnabled = false
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
            beatUntil = nil
            marker.isEnabled = false
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
        // A punt is its drive's last play, and the scene moves to the
        // receiving team's drive about six seconds later - while the punt is
        // still in the air. Switching then cleared the trails and cancelled
        // the flight, so a punt never once played. The new drive waits for
        // the field to be quiet, up to `play.holdSwitchSeconds`.
        if drive.id != driveID, !driveID.isEmpty, flight != nil || !motion.queue.isEmpty {
            let held = heldSince ?? c.shared.time
            heldSince = held
            if c.shared.time - held < c.look.broadcast.play.holdSwitchSeconds {
                Self.trace(c, "hold drive=\(drive.id) for \(flight?.arc.id ?? "queue")")
                return
            }
        }
        heldSince = nil
        if drive.id != driveID || lostAPlay {
            trails.clear()
            motion.reset()
            flight = nil
            beatUntil = nil
            marker.isEnabled = false
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
        guard flight == nil, beatUntil == nil else { return }
        guard let (arc, seconds) = motion.next(reduceMotion: c.reduceMotion, floor: c.spec.motion.floorSeconds) else {
            settle(c, animated: !c.reduceMotion)
            return
        }
        if seconds <= 0 {
            trails.add(arc, c)
            startNextFlight(c)
        } else {
            flight = (arc, 0, seconds, SceneMath.kickCut(arc, field: c.spec.field, netYards: c.look.broadcast.play.goalKick.netYards))
            // The beacon marks where the ball rests; while a play is on, the ball is the mark.
            beacon.isEnabled = false
            Self.trace(c, "fly \(arc.id) \(arc.type) \(seconds)s")
        }
    }
}
