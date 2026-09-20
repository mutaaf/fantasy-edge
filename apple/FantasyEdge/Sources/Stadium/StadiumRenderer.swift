import Foundation
import OSLog
import RealityKit
import simd

enum StadiumLog {
    static let log = Logger(subsystem: "com.mutaaf.fantasyedge", category: "stadium")
}

/// Where the seconds go between opening the stadium and its first frame.
/// Every step logs a `[stadium-timing]` line (the look-dev harness keeps them
/// in stats.txt) and an OSSignposter interval Instruments shows on a device.
/// The simulator's numbers are its own: load order and ratios transfer, the
/// absolute seconds need a headset.
enum StadiumTiming {
    static let signposter = OSSignposter(subsystem: "com.mutaaf.fantasyedge", category: "stadium")

    static func seconds(since start: ContinuousClock.Instant) -> String {
        let d = ContinuousClock.now - start
        let s = Double(d.components.seconds) + Double(d.components.attoseconds) / 1e18
        return String(format: "%.3f s", s)
    }

    static func log(_ what: String, since start: ContinuousClock.Instant) {
        let line = "[stadium-timing] \(what): \(seconds(since: start))"
        StadiumLog.log.notice("\(line, privacy: .public)")
    }

    /// Run `body` inside a signpost interval and log how long it took.
    @MainActor
    static func measure<T>(_ what: String, _ body: () throws -> T) rethrows -> T {
        let state = signposter.beginInterval("stadium", id: signposter.makeSignpostID(), "\(what, privacy: .public)")
        let start = ContinuousClock.now
        defer {
            signposter.endInterval("stadium", state)
            log(what, since: start)
        }
        return try body()
    }
}

/// Composes the stadium's actors into one entity tree, at tabletop or stadium
/// scale. See `Actors/StadiumActor.swift` for the actors and the rules between
/// them, and docs/ART_BIBLE.md for what each is responsible for looking like.
///
/// The composer does four things and nothing else: waits for assets, builds
/// every actor when the clubs change, hands every new scene and every frame to
/// every actor, and turns the scene's newest moment into one event. It draws
/// nothing itself. Only the director edits it.
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

    @ObservationIgnored private let world = Entity()
    @ObservationIgnored private let assets = StadiumAssets.shared
    @ObservationIgnored private var context: StadiumContext?
    @ObservationIgnored private let experience = ExperienceActor()
    @ObservationIgnored private let lighting = LightingActor()
    @ObservationIgnored private let broadcast = BroadcastActor()
    @ObservationIgnored private let actors: [any StadiumActor]
    @ObservationIgnored private var staticKey = ""
    @ObservationIgnored private var preparing = false
    @ObservationIgnored private var pendingReduceMotion = false
    @ObservationIgnored private var lastRedZone = false
    @ObservationIgnored private var lastCue: String?
    /// Holds a moment until Broadcast has flown its play. See `MomentGate`.
    @ObservationIgnored private var gate = MomentGate()
    /// Holds the score, the down and the red-zone flag behind the ball in the
    /// same way. See `StatusGate`.
    @ObservationIgnored private var status = StatusGate<SceneSpec.Status>()
    /// The newest play the shown drive has carried, so a scene that brings one
    /// is told apart from a scene that only moved the clock.
    @ObservationIgnored private var lastArrivedPlay: String?
    /// What the boards, the crowd and the scorebug are drawing: the scene's
    /// status once its play has landed. The views read it, so the glass
    /// scorebug and the video board never disagree.
    public private(set) var shownStatus: SceneSpec.Status?
    /// The drive as the views may list it: the plays the viewer has seen land.
    /// The scene announces a play as it arrives and the ball lands seconds
    /// later, so the log would otherwise name a play - and a drive result -
    /// while it was still in the air, beside a score correctly waiting for it.
    /// One answer, from the gate that holds the score, so the log, the scrubber
    /// and the video board cannot disagree.
    public private(set) var shownDrive: SceneSpec.Drive?
    /// The last drive-log line written, so the log says what changed rather
    /// than repeating itself every frame. A `--times` frame is its own launch,
    /// so what the log lists against what the ball is doing is read from these
    /// lines, not from two screenshots.
    @ObservationIgnored private var lastDriveLine = ""
    /// The scene the actors were last handed, which is `spec` with `status`
    /// replaced by `shownStatus`. Actors compare against it, not against the
    /// scene as it arrived, so a change is seen once and at the right moment.
    @ObservationIgnored private var shownSpec: SceneSpec?
    /// The frame clock when the held moment arrived, for the log line that says
    /// how long it waited.
    @ObservationIgnored private var momentArrivedAt = 0.0
    /// The same for the drawn status, so how far the board lags the feed is a
    /// measured number rather than a claim.
    @ObservationIgnored private var statusHeldAt = 0.0
    /// The moment the stadium is celebrating right now, which is not the
    /// scene's newest: the scene announces a touchdown as the play arrives and
    /// the ball lands about five seconds later. The views follow this, so the
    /// panels yield and the celebration shows with the stadium, not ahead of it.
    public private(set) var liveMoment: SceneSpec.Moment?
    /// With -stadiumStats, the frame-clock times at which to count again, and
    /// what to call the count: mid-moment, when particles and cards are live.
    @ObservationIgnored private var statsDue: [(at: Double, label: String)] = []
    /// When this renderer was first handed a scene, and whether its first
    /// frame after a build has been logged against it.
    @ObservationIgnored private var openedAt: ContinuousClock.Instant?
    @ObservationIgnored private var firstFrameDue = false
    /// With -stadiumStats, the CPU cost of `tick` over the 120 frames after a build.
    @ObservationIgnored private var statsFrames = 0
    @ObservationIgnored private var frameCost: Duration = .zero
    /// With -stadiumStats, how fast the stadium actually runs and how much it
    /// holds. Only worth reading on a headset; the line says which machine it
    /// came from (StadiumDeviceStats).
    @ObservationIgnored private var deviceStats: StadiumDeviceStats.Sampler?

    public init(mode: Mode) {
        self.mode = mode
        // Build order matters only for the blackboard: Bowl and Lighting
        // publish positions that Moments and Audio read.
        actors = [experience, FieldActor(), SidelineActor(), BowlActor(), lighting, SkyActor(),
                  CrowdActor(), broadcast, MomentsActor(), AudioActor()]
        root.name = "stadium.root"
        root.addChild(world)
        for actor in actors { world.addChild(actor.root) }
    }

    // MARK: apply

    public func apply(_ next: SceneSpec, reduceMotion: Bool) {
        let previous = shownSpec
        spec = next
        if openedAt == nil { openedAt = .now }
        pendingReduceMotion = reduceMotion
        guard let look = next.look ?? context?.look ?? SceneSpec.Look.bundled() else { return }
        guard assets.ready else {
            prepare(look)
            return
        }
        // What the actors are handed is the scene with the status the stadium
        // is allowed to show: everything else is the scene as it arrived. A
        // new matchup rebuilds, so there is nothing on screen to lag behind.
        let key = [next.league, next.teams.home.chip, next.teams.away.chip,
                   next.teams.home.abbr, next.teams.away.abbr].joined(separator: "|")
        let shown = showing(next, fresh: key != staticKey)
        let c: StadiumContext
        if let existing = context {
            existing.update(spec: shown, look: look, reduceMotion: reduceMotion)
            c = existing
        } else {
            c = StadiumContext(lod: mode == .tabletop ? .tabletop : .stadium, spec: shown, look: look, assets: assets,
                               stage: root, world: world, reduceMotion: reduceMotion)
            c.shared.muted = muted
            context = c
            experience.onSeatChanged = { [weak self] in
                guard let self, let c = self.context else { return }
                self.broadcast.redrawDrive(c)
            }
        }
        if key != staticKey {
            if let openedAt { StadiumTiming.log("\(label) assets ready after open", since: openedAt) }
            build(c)
            staticKey = key
            gate.suppress(next.activeMoment?.playId)
            liveMoment = nil
            lastCue = next.activeCue?.id
            lastRedZone = c.spec.status.redZone
        }
        shownSpec = c.spec
        let applying = firstFrameDue
        for actor in actors {
            if applying {
                StadiumTiming.measure("\(label) apply.\(actor.name)") { actor.apply(c, previous: previous) }
            } else {
                actor.apply(c, previous: previous)
            }
        }
        dispatchEvents(c)
        // Trails, banners and flags an actor adds after build would cast by default.
        optOutOfShadows(world)
    }

    /// The scene as the stadium may show it: its own status while the play it
    /// describes is still in the air, the scene's once that play has landed.
    ///
    /// A status belongs to the newest play in the drive on screen. A scene that
    /// brings one is held behind it; a scene that brings none - the clock
    /// ticking, a timeout, a stoppage - is shown at once. The deadline is the
    /// flight still owed by every play not yet laid, plus the grace, so a
    /// queue of plays is waited out and a play that never flies cannot freeze
    /// the board.
    private func showing(_ next: SceneSpec, fresh: Bool) -> SceneSpec {
        let newest = next.shownDrive?.arcs.last
        if fresh {
            lastArrivedPlay = newest?.id
            status.adopt(next.status)
        } else if newest?.id != lastArrivedPlay {
            lastArrivedPlay = newest?.id
            if let a = newest, !broadcast.hasTrail(a.id) {
                let owed = (next.shownDrive?.arcs ?? []).reduce(0.0) {
                    $0 + (broadcast.hasTrail($1.id) ? 0 : $1.flightSeconds)
                }
                let grace = next.motion.momentHoldGraceSeconds ?? MomentGate.defaultGraceSeconds
                let now = context?.shared.time ?? 0
                if !status.isHolding { statusHeldAt = now }
                status.hold(next.status, playId: a.id, until: now + owed + grace)
            } else {
                status.adopt(next.status)
            }
        } else {
            status.arrive(next.status)
        }
        shownStatus = status.shown
        setShownDrive(next.shownDrive)
        var s = next
        s.status = status.shown ?? next.status
        return s
    }

    /// The drive as the views may list it, and a line saying so when it
    /// changes: which play the log ends on, and which one it is waiting for.
    private func setShownDrive(_ drive: SceneSpec.Drive?) {
        let shown = LaidPlay.through(drive, held: status.waitingOn)
        shownDrive = shown
        let line = "[stadium] drive log lists \(shown?.arcs.count ?? 0) of "
            + "\(drive?.arcs.count ?? 0) plays, newest \(shown?.arcs.last?.id ?? "-"), "
            + "waiting on \(status.waitingOn ?? "-")"
        guard line != lastDriveLine else { return }
        lastDriveLine = line
        StadiumLog.log.notice("\(line, privacy: .public)")
    }

    /// On the frame clock: the drawn status catches up the frame its play
    /// lands. The boards draw in `apply`, so catching up means applying the
    /// scene again - one redraw per play, which is what a scene arriving used
    /// to cost.
    private func releaseStatus(_ c: StadiumContext) {
        let waitingOn = status.waitingOn
        guard let caught = status.due(now: c.shared.time, landed: { [broadcast] in broadcast.hasTrail($0) }),
              let latest = spec else { return }
        let line = String(format: "[stadium] score %@ %d - %@ %d drawn at t=%.2f, held %.2f s behind %@",
                          latest.teams.away.abbr, Int(caught.awayScore),
                          latest.teams.home.abbr, Int(caught.homeScore),
                          c.shared.time, max(0, c.shared.time - statusHeldAt), waitingOn ?? "-")
        StadiumLog.log.notice("\(line, privacy: .public)")
        shownStatus = caught
        setShownDrive(latest.shownDrive)
        var s = latest
        s.status = caught
        let previous = shownSpec
        c.update(spec: s, look: c.look, reduceMotion: c.reduceMotion)
        shownSpec = s
        for actor in actors { actor.apply(c, previous: previous) }
        if s.status.redZone != lastRedZone {
            lastRedZone = s.status.redZone
            if s.status.redZone { for actor in actors { actor.moment(.redZoneEntered, c) } }
        }
        optOutOfShadows(world)
    }

    private func prepare(_ look: SceneSpec.Look) {
        guard !preparing else { return }
        preparing = true
        Task { [weak self] in
            let start = ContinuousClock.now
            await StadiumLook.prepare()
            StadiumTiming.log("look programs", since: start)
            await StadiumAssets.shared.prepare(look)
            guard let self else { return }
            self.preparing = false
            if let s = self.spec { self.apply(s, reduceMotion: self.pendingReduceMotion) }
        }
    }

    /// `stadium` or `tabletop`, for logs.
    private var label: String { mode == .tabletop ? "tabletop" : "stadium" }

    private func build(_ c: StadiumContext) {
        let start = ContinuousClock.now
        c.shared.time = 0
        for actor in actors {
            StadiumTiming.measure("\(label) build.\(actor.name)") { actor.build(c) }
        }
        // Image-based light does not inherit, so every model points at the probe.
        if lighting.root.components.has(ImageBasedLightComponent.self) {
            StadiumTiming.measure("\(label) build.probeReceivers") { applyReceivers(world) }
        }
        optOutOfShadows(world)
        StadiumTiming.log("\(label) build total", since: start)
        firstFrameDue = true
        if ProcessInfo.processInfo.arguments.contains("-stadiumStats") {
            StadiumStats.report(actors, label: c.tabletop ? "tabletop" : "stadium", assets: assets)
            statsFrames = 120
            frameCost = .zero
            if deviceStats == nil {
                StadiumDeviceStats.announce(label)
                deviceStats = StadiumDeviceStats.Sampler(label: label)
            }
        }
        if ProcessInfo.processInfo.arguments.contains("-shaderGraphProof") { shaderGraphProof(c) }
    }

    /// `-shaderGraphProof`: three spheres over midfield, left to right the
    /// token-driven Fresnel material, the same with Invert = 1, and the portable
    /// fallback every client can draw. Proves the Shader Graph pipeline end to end.
    private func shaderGraphProof(_ c: StadiumContext) {
        guard let spec = c.spec.shaderGraph?.materials?["fresnel"] else {
            StadiumLog.log.error("[shadergraph] no shaderGraph.materials.fresnel in the scene")
            return
        }
        let holder = Entity()
        holder.name = "shadergraph.proof"
        world.addChild(holder)
        Task { @MainActor in
            let sphere = MeshResource.generateSphere(radius: 4)
            var fallback = UnlitMaterial(color: StadiumLook.color(
                { if case .string(let s) = spec.fallback["color"] { return s }; return "#FFFFFF" }()))
            if case .number(let o) = spec.fallback["opacity"] { fallback.blending = .transparent(opacity: .init(floatLiteral: Float(o))) }
            var materials: [any Material] = [fallback, fallback]
            if let base = await StadiumShaderGraph.material(spec.prim, file: spec.file) {
                var normal = base, inverted = base
                for (k, v) in spec.parameters {
                    StadiumShaderGraph.set(&normal, k, v.any)
                    StadiumShaderGraph.set(&inverted, k, v.any)
                }
                StadiumShaderGraph.set(&inverted, "Invert", 1.0)
                materials = [normal, inverted]
            }
            for (i, m) in (materials + [fallback]).enumerated() {
                let e = ModelEntity(mesh: sphere, materials: [m])
                e.position = SceneMath.local(x: 38 + Double(i) * 12, y: 9, z: 0)
                holder.addChild(e)
            }
        }
    }

    /// A spot light's shadow falls from every model that does not say
    /// otherwise, so ~45k fans and every seat once cast into Lighting's single
    /// shadow. Casting is opt-in: an actor that wants a shadow (Sideline's
    /// goalposts) sets `DynamicLightShadowComponent(castsShadow: true)` itself,
    /// and the composer repeats the pass after every scene and every frame, so
    /// pieces added after build never reach a rendered frame casting.
    private func optOutOfShadows(_ e: Entity) {
        for child in e.children {
            if child.components.has(ModelComponent.self), !child.components.has(DynamicLightShadowComponent.self) {
                child.components.set(DynamicLightShadowComponent(castsShadow: false))
            }
            optOutOfShadows(child)
        }
    }

    private func applyReceivers(_ e: Entity) {
        for child in e.children {
            if child.components.has(ModelComponent.self) {
                child.components.set(ImageBasedLightReceiverComponent(imageBasedLight: lighting.root))
            }
            applyReceivers(child)
        }
    }

    /// The scene's newest moment and the red-zone crossing, once each.
    private func dispatchEvents(_ c: StadiumContext) {
        let s = c.spec
        if s.status.redZone && !lastRedZone {
            for actor in actors { actor.moment(.redZoneEntered, c) }
        }
        lastRedZone = s.status.redZone
        if let cue = s.activeCue, cue.id != lastCue {
            lastCue = cue.id
            for actor in actors { actor.moment(.cue(cue), c) }
        }
        guard let m = s.activeMoment else {
            // Scrubbed off the moment, or a stoppage ended it: a moment nobody
            // is watching any more must not fire late.
            gate.clear()
            liveMoment = nil
            return
        }
        // The scene announces the moment when the play arrives; Broadcast flies
        // that play for seconds afterwards. Hold it until the ball lands.
        let arc = s.shownDrive?.arcs.first { $0.id == m.playId }
        if !gate.isHolding(m.playId) { momentArrivedAt = c.shared.time }
        if gate.arrive(playId: m.playId, flightSeconds: arc?.flightSeconds ?? 0, now: c.shared.time,
                       grace: s.motion.momentHoldGraceSeconds ?? MomentGate.defaultGraceSeconds,
                       landed: broadcast.hasTrail(m.playId)) {
            fire(m, c)
        }
    }

    /// The moment happens now: every actor hears it, and everything timed from
    /// it - `motion.momentSeconds`, the surge, the fireworks, the strobe, the
    /// audio cues, the stats counts - starts from this frame, not from the
    /// frame the play arrived in.
    private func fire(_ m: SceneSpec.Moment, _ c: StadiumContext) {
        liveMoment = m
        let waited = c.shared.time - momentArrivedAt
        let line = String(format: "[stadium] moment %@ fired at t=%.2f, held %.2f s for its play to land",
                          m.kind, c.shared.time, max(0, waited))
        StadiumLog.log.notice("\(line, privacy: .public)")
        for actor in actors { actor.moment(.moment(m), c) }
        if ProcessInfo.processInfo.arguments.contains("-stadiumStats") {
            let base = c.tabletop ? "tabletop" : "stadium"
            statsDue += [0.5, 3, 6].map { (c.shared.time + $0, "\(base)@\(m.kind)+\($0)s") }
        }
    }

    /// On the frame clock: release a held moment the frame its play lands, or
    /// when its hold runs out.
    private func releaseMoment(_ c: StadiumContext) {
        guard let id = gate.due(now: c.shared.time, landed: { [broadcast] in broadcast.hasTrail($0) }),
              let m = c.spec.activeMoment, m.playId == id else { return }
        fire(m, c)
    }

    // MARK: seats and sound

    public func setMuted(_ on: Bool) {
        muted = on
        context?.shared.muted = on
    }

    public func seat(_ s: SceneSpec) -> SceneSpec.SeatOption {
        s.presentation.stadium.seat(seatID)
    }

    /// Sit somewhere else. The world fades down, turns and moves about the
    /// wearer, and fades back; reduce motion cuts.
    public func sit(_ id: String?) {
        guard id != seatID else { return }
        seatID = id
        experience.sit(id, context)
    }

    // MARK: the frame clock

    public func tick(_ dt: TimeInterval) {
        guard let c = context, !staticKey.isEmpty else { return }
        c.shared.time += dt
        // Before the actors update, so a moment released this frame is acted on
        // in the same frame the ball lands. The score first, so the banner that
        // moment puts up carries the score the ball just made.
        releaseStatus(c)
        releaseMoment(c)
        let frame = StadiumFrame(dt: dt, time: c.shared.time)
        let first = firstFrameDue
        firstFrameDue = false
        let start = ContinuousClock.now
        for actor in actors {
            if first {
                StadiumTiming.measure("\(label) first update.\(actor.name)") { actor.update(frame, c) }
            } else {
                actor.update(frame, c)
            }
        }
        // Actors rebuild trail meshes on the frame clock; opt them out the
        // frame they appear.
        optOutOfShadows(world)
        if first, let openedAt {
            StadiumTiming.log("\(label) first tick after open", since: openedAt)
        }
        if statsFrames > 0, !first {
            statsFrames -= 1
            frameCost += ContinuousClock.now - start
            if statsFrames == 0 {
                let ms = (Double(frameCost.components.attoseconds) / 1e15 + Double(frameCost.components.seconds) * 1e3) / 120
                let line = "[stadium-timing] \(label) main-thread tick: \(String(format: "%.3f", ms)) ms mean over 120 frames"
                StadiumLog.log.notice("\(line, privacy: .public)")
            }
        }
        if let line = deviceStats?.tick(), !line.isEmpty {
            StadiumLog.log.notice("\(line, privacy: .public)")
        }
        while let next = statsDue.first, next.at <= c.shared.time {
            statsDue.removeFirst()
            StadiumStats.report(actors, label: next.label, assets: assets)
        }
    }
}

/// Counts what the stadium costs to draw, per actor, against the budget in
/// docs/ART_BIBLE.md. Launch with `-stadiumStats`.
@MainActor
enum StadiumStats {
    static func report(_ actors: [any StadiumActor], label: String, assets: StadiumAssets) {
        var totals = (models: 0, parts: 0, triangles: 0)
        for actor in actors {
            var models = 0, parts = 0, triangles = 0, lights = 0, emitters = 0, casters = 0
            func walk(_ e: Entity) {
                if let model = e.components[ModelComponent.self] {
                    models += 1
                    if e.components[DynamicLightShadowComponent.self]?.castsShadow ?? true { casters += 1 }
                    for m in model.mesh.contents.models {
                        for p in m.parts {
                            parts += 1
                            triangles += (p.triangleIndices?.count ?? 0) / 3
                        }
                    }
                }
                if e.components.has(SpotLightComponent.self) { lights += 1 }
                if e.components.has(ParticleEmitterComponent.self) { emitters += 1 }
                e.children.forEach(walk)
            }
            walk(actor.root)
            totals.models += models
            totals.parts += parts
            totals.triangles += triangles
            let line = "[stadium-stats] \(label).\(actor.name): draw parts \(parts), triangles \(triangles), "
                + "spot lights \(lights), emitters \(emitters), shadow casters \(casters)"
            StadiumLog.log.notice("\(line, privacy: .public)")
        }
        let line = "[stadium-stats] \(label): models \(totals.models), draw parts \(totals.parts), "
            + "triangles \(totals.triangles), texture memory ~\(assets.bytes / 1_048_576) MB"
        StadiumLog.log.notice("\(line, privacy: .public)")
    }
}
