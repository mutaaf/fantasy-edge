import Foundation
import OSLog
import RealityKit
import simd

enum StadiumLog {
    static let log = Logger(subsystem: "com.mutaaf.fantasyedge", category: "stadium")
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
    @ObservationIgnored private var lastMoment: String?
    @ObservationIgnored private var lastRedZone = false
    @ObservationIgnored private var lastCue: String?
    /// With -stadiumStats, the frame-clock times at which to count again, and
    /// what to call the count: mid-moment, when particles and cards are live.
    @ObservationIgnored private var statsDue: [(at: Double, label: String)] = []

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
        let previous = spec
        spec = next
        pendingReduceMotion = reduceMotion
        guard let look = next.look ?? context?.look ?? SceneSpec.Look.bundled() else { return }
        guard assets.ready else {
            prepare(look)
            return
        }
        let c: StadiumContext
        if let existing = context {
            existing.update(spec: next, look: look, reduceMotion: reduceMotion)
            c = existing
        } else {
            c = StadiumContext(lod: mode == .tabletop ? .tabletop : .stadium, spec: next, look: look, assets: assets,
                               stage: root, world: world, reduceMotion: reduceMotion)
            c.shared.muted = muted
            context = c
            experience.onSeatChanged = { [weak self] in
                guard let self, let c = self.context else { return }
                self.broadcast.redrawDrive(c)
            }
        }
        let key = [next.league, next.teams.home.chip, next.teams.away.chip,
                   next.teams.home.abbr, next.teams.away.abbr].joined(separator: "|")
        if key != staticKey {
            build(c)
            staticKey = key
            lastMoment = next.activeMoment?.playId
            lastCue = next.activeCue?.id
            lastRedZone = next.status.redZone
        }
        for actor in actors { actor.apply(c, previous: previous) }
        dispatchEvents(c)
        // Trails, banners and flags an actor adds after build would cast by default.
        optOutOfShadows(world)
    }

    private func prepare(_ look: SceneSpec.Look) {
        guard !preparing else { return }
        preparing = true
        Task { [weak self] in
            await StadiumLook.prepare()
            await StadiumAssets.shared.prepare(look)
            guard let self else { return }
            self.preparing = false
            if let s = self.spec { self.apply(s, reduceMotion: self.pendingReduceMotion) }
        }
    }

    private func build(_ c: StadiumContext) {
        c.shared.time = 0
        for actor in actors { actor.build(c) }
        // Image-based light does not inherit, so every model points at the probe.
        if lighting.root.components.has(ImageBasedLightComponent.self) {
            applyReceivers(world)
        }
        optOutOfShadows(world)
        if ProcessInfo.processInfo.arguments.contains("-stadiumStats") {
            StadiumStats.report(actors, label: c.tabletop ? "tabletop" : "stadium", assets: assets)
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
    /// and the composer repeats the pass on every scene, so pieces added after
    /// build are caught within one update.
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
            lastMoment = nil
            return
        }
        guard m.playId != lastMoment else { return }
        lastMoment = m.playId
        for actor in actors { actor.moment(.moment(m), c) }
        if ProcessInfo.processInfo.arguments.contains("-stadiumStats") {
            let base = c.tabletop ? "tabletop" : "stadium"
            statsDue += [0.5, 3, 6].map { (c.shared.time + $0, "\(base)@\(m.kind)+\($0)s") }
        }
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
        let frame = StadiumFrame(dt: dt, time: c.shared.time)
        for actor in actors { actor.update(frame, c) }
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
