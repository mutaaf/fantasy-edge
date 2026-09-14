import Foundation
import OSLog
import RealityKit
import simd

enum StadiumLog {
    static let log = Logger(subsystem: "com.mutaaf.fantasyedge", category: "stadium")
}

/// Draws a `SceneSpec` into one entity tree, at tabletop or stadium scale.
///
/// The recorded lessons of the old immersive board still set its shape:
///
///   * Everything static - field, bowl, crowd, lights, sky - is built once per
///     pair of teams and never again. A poll changes numbers, not the stadium.
///   * Anything that moves is placed once and moved: the ball, the lasers,
///     the beacon, the chains. Nothing is torn down to be redrawn.
///   * A drive's trails are laid down as plays arrive, after the ball has
///     flown them, so the drive visibly grows.
///
/// New in the look pass: the ball flies on the frame clock rather than a
/// sleeping task, so its path and spin are smooth at any replay speed; assets
/// load asynchronously before the first build; and a seat change turns and
/// moves the world about the wearer, never the wearer.
///
/// It knows nothing about fantasy football and holds no network code.
@MainActor
@Observable
public final class StadiumRenderer {
    public enum Mode: Sendable { case tabletop, stadium }

    public let root = Entity()
    public let mode: Mode
    @ObservationIgnored public private(set) var spec: SceneSpec?
    /// The seat the stadium is drawn from. Nil means the scene's default.
    public private(set) var seatID: String?
    public private(set) var muted = false
    /// Retained here so the frame clock stops with the renderer.
    @ObservationIgnored public var subscription: EventSubscription?

    private var tabletop: Bool { mode == .tabletop }
    @ObservationIgnored private let world = Entity()
    @ObservationIgnored private let assets = StadiumAssets.shared
    @ObservationIgnored private var look: SceneSpec.Look?
    @ObservationIgnored private var statics: StadiumStatic?
    @ObservationIgnored private var crowd: StadiumCrowd?
    @ObservationIgnored private let broadcast: StadiumBroadcast
    @ObservationIgnored private let moments: StadiumMoments
    @ObservationIgnored private var staticKey = ""
    @ObservationIgnored private var preparing = false
    @ObservationIgnored private var reduceMotion = false

    @ObservationIgnored private var driveID = ""
    @ObservationIgnored private var motion = PlayMotion()
    @ObservationIgnored private var flight: (arc: SceneSpec.Arc, elapsed: Double, duration: Double)?
    @ObservationIgnored private var fade: (elapsed: Double, duration: Double, swapped: Bool, seat: String?)?

    public init(mode: Mode) {
        self.mode = mode
        broadcast = StadiumBroadcast(tabletop: mode == .tabletop)
        moments = StadiumMoments(tabletop: mode == .tabletop)
        root.name = "stadium.root"
        root.addChild(world)
    }

    // MARK: apply

    public func apply(_ next: SceneSpec, reduceMotion: Bool) {
        let previous = spec
        spec = next
        self.reduceMotion = reduceMotion
        guard let look = next.look ?? look ?? SceneSpec.Look.bundled() else { return }
        self.look = look
        guard assets.ready else {
            prepare(look)
            return
        }
        if fade == nil { place(next) }
        let key = [next.league, next.teams.home.chip, next.teams.away.chip,
                   next.teams.home.abbr, next.teams.away.abbr].joined(separator: "|")
        if key != staticKey {
            buildStatic(next, look: look)
            staticKey = key
        }
        guard let statics else { return }
        updateDrive(next, previous: previous, look: look)
        broadcast.updateHorizon(next, look: look, assets: assets)
        crowd?.applyTint(next)
        moments.update(next, look: look, assets: assets, statics: statics, crowd: crowd, reduceMotion: reduceMotion)
        if let tex = statics.ribbon {
            let k = StadiumText.ribbonKey(next)
            if k != statics.ribbonKey {
                statics.ribbonKey = k
                StadiumText.updateRibbon(tex, next, look: look)
            }
        }
        if flight == nil { broadcast.settle(next, look: look, assets: assets, animated: !reduceMotion) }
    }

    private func prepare(_ look: SceneSpec.Look) {
        guard !preparing else { return }
        preparing = true
        Task { [weak self] in
            await StadiumLook.prepare()
            await StadiumAssets.shared.prepare(look)
            guard let self else { return }
            self.preparing = false
            if let s = self.spec { self.apply(s, reduceMotion: self.reduceMotion) }
        }
    }

    // MARK: seats

    public func setMuted(_ on: Bool) {
        muted = on
        moments.muted = on
    }

    public func seat(_ s: SceneSpec) -> SceneSpec.SeatOption {
        s.presentation.stadium.seat(seatID)
    }

    /// Sit somewhere else. The world fades down, turns and moves about the
    /// wearer, and fades back; reduce motion cuts.
    public func sit(_ id: String?) {
        guard id != seatID else { return }
        guard let s = spec, let look, mode == .stadium, !reduceMotion else {
            seatID = id
            if let s = spec { place(s) }
            return
        }
        _ = s
        fade = (0, max(0.1, look.camera.seatFadeSeconds * 2), false, id)
    }

    private func place(_ s: SceneSpec) {
        switch mode {
        case .tabletop:
            let t = s.presentation.tabletop
            root.scale = SIMD3(repeating: Float(t.metersPerYard))
            root.position = SIMD3(0, Float(t.floor), 0)
            root.orientation = simd_quatf(angle: 0, axis: SIMD3(0, 1, 0))
        case .stadium:
            let st = s.presentation.stadium
            let eye = look?.camera.eyeMeters ?? 1.2
            let placed = SceneMath.seatRoot(st.seat(seatID), metersPerYard: st.metersPerYard, eye: eye)
            root.scale = SIMD3(repeating: Float(st.metersPerYard))
            root.orientation = placed.orientation
            root.position = placed.position
        }
    }

    private var seatLocal: SIMD3<Float>? {
        guard let s = spec, mode == .stadium else { return nil }
        let seat = s.presentation.stadium.seat(seatID)
        let eyeYards = (look?.camera.eyeMeters ?? 1.2) / s.presentation.stadium.metersPerYard
        return SceneMath.local(x: seat.x, y: seat.y + eyeYards, z: seat.z)
    }

    // MARK: static

    private var tiers: [SceneSpec.Tier] {
        guard let s = spec else { return [] }
        let names = tabletop ? s.presentation.tabletop.bowlTiers : s.presentation.stadium.bowlTiers
        return s.bowl.tiers.filter { names.contains($0.name) }
    }

    private func buildStatic(_ s: SceneSpec, look: SceneSpec.Look) {
        world.children.removeAll()
        let tiers = self.tiers
        let built = StadiumBowl.build(s, look: look, assets: assets, tabletop: tabletop, tiers: tiers)
        world.addChild(built.root)
        statics = built
        let c = StadiumCrowd(s, look: look, assets: assets, tiers: tiers, tabletop: tabletop)
        world.addChild(c.root)
        crowd = c
        broadcast.build(s, look: look, assets: assets)
        broadcast.clearDrive()
        world.addChild(broadcast.root)
        moments.build(s, look: look, assets: assets, statics: built, tiers: tiers)
        world.addChild(moments.root)
        if let env = assets.environment {
            root.components.set(ImageBasedLightComponent(source: .single(env),
                                                         intensityExponent: Float(look.light.probeIntensityExponent)))
            for child in world.children {
                child.components.set(ImageBasedLightReceiverComponent(imageBasedLight: root))
            }
            applyReceivers(world)
        }
        motion.reset()
        driveID = ""
        flight = nil
        if ProcessInfo.processInfo.arguments.contains("-stadiumStats") {
            StadiumStats.report(root, fans: c.fans, label: tabletop ? "tabletop" : "stadium", assets: assets)
        }
    }

    /// IBL receivers do not inherit, so every model gets one.
    private func applyReceivers(_ e: Entity) {
        for child in e.children {
            if child.components.has(ModelComponent.self) {
                child.components.set(ImageBasedLightReceiverComponent(imageBasedLight: root))
            }
            applyReceivers(child)
        }
    }

    // MARK: the drive

    private func updateDrive(_ s: SceneSpec, previous: SceneSpec?, look: SceneSpec.Look) {
        guard let drive = s.shownDrive else {
            broadcast.clearDrive()
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
        if drive.id != driveID || lostAPlay {
            broadcast.clearDrive()
            motion.reset()
            flight = nil
            driveID = drive.id
            let initial = !nextDrive
            _ = motion.arrive(drive, initial: initial)
            if initial {
                for arc in drive.arcs { broadcast.addTrail(arc, spec: s, look: look, assets: assets, seat: seatLocal) }
                return
            }
        } else {
            _ = motion.arrive(drive, initial: false)
        }
        startNextFlight()
    }

    private func startNextFlight() {
        guard flight == nil, let s = spec, let look else { return }
        guard let (arc, seconds) = motion.next(reduceMotion: reduceMotion, floor: s.motion.floorSeconds) else {
            broadcast.settle(s, look: look, assets: assets, animated: !reduceMotion)
            return
        }
        if seconds <= 0 {
            broadcast.addTrail(arc, spec: s, look: look, assets: assets, seat: seatLocal)
            startNextFlight()
        } else {
            flight = (arc, 0, seconds)
        }
    }

    // MARK: the frame clock

    public func tick(_ dt: TimeInterval) {
        guard let look, let statics else { return }
        if var f = flight {
            f.elapsed += dt
            let t = min(1, f.elapsed / f.duration)
            // Ease the flight: quick off the snap, settling into the catch.
            let eased = 1 - pow(1 - t, spec?.motion.flightEase ?? 1.6)
            broadcast.placeBall(on: f.arc, at: eased, dt: dt, look: look)
            if t >= 1, let s = spec {
                broadcast.addTrail(f.arc, spec: s, look: look, assets: assets, seat: seatLocal)
                flight = nil
                startNextFlight()
            } else {
                flight = f
            }
        }
        if var fd = fade, let s = spec {
            fd.elapsed += dt
            let half = fd.duration / 2
            let opacity: Float
            if fd.elapsed < half {
                opacity = Float(1 - fd.elapsed / half)
            } else {
                if !fd.swapped {
                    seatID = fd.seat
                    place(s)
                    broadcast.clearDrive()
                    driveID = ""
                    updateDrive(s, previous: nil, look: look)
                    fd.swapped = true
                }
                opacity = Float(min(1, (fd.elapsed - half) / half))
            }
            world.components.set(OpacityComponent(opacity: opacity))
            if fd.elapsed >= fd.duration {
                world.components.remove(OpacityComponent.self)
                fade = nil
            } else {
                fade = fd
            }
        }
        crowd?.tick(dt, look: look, reduceMotion: reduceMotion)
        moments.tick(dt, statics: statics, look: look)
    }
}

/// Counts what the stadium costs to draw, against the budget in
/// docs/IMMERSIVE_QUALITY.md. Launch with `-stadiumStats`.
@MainActor
enum StadiumStats {
    static func report(_ root: Entity, fans: Int, label: String, assets: StadiumAssets) {
        var entities = 0, models = 0, parts = 0, triangles = 0, lights = 0, emitters = 0, glows = 0
        func walk(_ e: Entity) {
            entities += 1
            if let model = e.components[ModelComponent.self] {
                models += 1
                for m in model.mesh.contents.models {
                    for p in m.parts {
                        parts += 1
                        triangles += (p.triangleIndices?.count ?? 0) / 3
                    }
                }
                if model.materials.contains(where: { ($0 as? UnlitMaterial)?.writesDepth == false }) { glows += 1 }
            }
            if e.components.has(SpotLightComponent.self) { lights += 1 }
            if e.components.has(ParticleEmitterComponent.self) { emitters += 1 }
            e.children.forEach(walk)
        }
        walk(root)
        let line = "[stadium-stats] \(label): entities \(entities), models \(models), draw parts \(parts), "
            + "triangles \(triangles), fans \(fans), glow models \(glows), spot lights \(lights), "
            + "emitters \(emitters), texture memory ~\(assets.bytes / 1_048_576) MB"
        StadiumLog.log.notice("\(line, privacy: .public)")
    }
}
