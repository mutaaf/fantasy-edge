import RealityKit
import simd

/// Draws a `SceneSpec` into one entity tree, at tabletop or stadium scale.
///
/// The recorded lessons of the old immersive board apply here too, and are
/// the reason for the shape of this class:
///
///   * Everything static - the field, the bowl, the crowd, the rim lights - is
///     built once per pair of teams and never again. A poll changes numbers,
///     not the stadium.
///   * Anything that moves is placed once and moved with `move(to:)`: the
///     ball, the lasers, the beacon. Nothing is torn down to be redrawn.
///   * A drive's arcs are added as plays arrive, after the ball has flown
///     them, so the drive visibly grows.
///
/// It knows nothing about fantasy football and holds no network code: the
/// view hands it a scene and it draws that scene.
@MainActor
public final class StadiumRenderer {
    public enum Mode: Sendable { case tabletop, stadium }

    public let root = Entity()
    public let mode: Mode
    public private(set) var spec: SceneSpec?

    private let content = Entity()
    private let dynamic = Entity()
    private var staticKey = ""
    private var crowd: [String: [String: ModelEntity]] = [:]
    private var driveRoot = Entity()
    private var driveID = ""
    private var arcEntities: [String: Entity] = [:]
    private let ball = ModelEntity()
    private let beacon = ModelEntity()
    private var lasers: [String: ModelEntity] = [:]
    private var horizon = Entity()
    private var horizonKey = ""
    private var tintKey = "unset"
    private var beaconKey = ""
    private var motion = PlayMotion()
    private var flight: Task<Void, Never>?

    public init(mode: Mode) {
        self.mode = mode
        root.name = "stadium.root"
        root.addChild(content)
        content.addChild(dynamic)
        dynamic.addChild(driveRoot)
        dynamic.addChild(ball)
        dynamic.addChild(beacon)
        dynamic.addChild(horizon)
        ball.isEnabled = false
        beacon.isEnabled = false
    }

    // MARK: apply

    public func apply(_ next: SceneSpec, reduceMotion: Bool) {
        let previous = spec
        spec = next
        place(next)
        let key = [next.league, next.teams.home.chip, next.teams.away.chip,
                   next.teams.home.abbr, next.teams.away.abbr].joined(separator: "|")
        if key != staticKey {
            buildStatic(next)
            staticKey = key
        }
        updateDrive(next, previous: previous, reduceMotion: reduceMotion)
        updateHorizon(next)
        updateTint(next)
        if flight == nil { settle(next, animated: !reduceMotion) }
    }

    private func place(_ s: SceneSpec) {
        switch mode {
        case .tabletop:
            let t = s.presentation.tabletop
            root.scale = SIMD3(repeating: Float(t.metersPerYard))
            root.position = SIMD3(0, Float(t.floor), 0)
        case .stadium:
            let st = s.presentation.stadium
            root.scale = SIMD3(repeating: Float(st.metersPerYard))
            root.position = SceneMath.stadiumRoot(seat: st.seat, metersPerYard: st.metersPerYard)
        }
    }

    // MARK: static

    private var tierNames: [String] {
        guard let s = spec else { return [] }
        return mode == .tabletop ? s.presentation.tabletop.bowlTiers : s.presentation.stadium.bowlTiers
    }

    private func buildStatic(_ s: SceneSpec) {
        for child in content.children where child !== dynamic { child.removeFromParent() }
        content.addChild(StadiumMeshes.field(s))
        let tiers = s.bowl.tiers.filter { tierNames.contains($0.name) }
        for t in tiers {
            content.addChild(StadiumMeshes.tier(t, shape: s.bowl.shape,
                                                color: s.palette[t.color] ?? "#302722"))
        }
        crowd = StadiumMeshes.crowd(s, tiers: tiers, count: mode == .tabletop ? 1800 : 6000)
        for section in crowd.values { for e in section.values { content.addChild(e) } }
        if let outer = tiers.last {
            let rim = outer.outer + 1
            let height = outer.rise[1] + (mode == .tabletop ? 4 : 9)
            // On the table a lamp the size of a stadium's reads as a pebble,
            // and a nine-yard glow as a glass marble, so both are cut down.
            content.addChild(StadiumMeshes.rimLights(
                s, rim: rim, height: height,
                glow: mode == .tabletop ? 4 : 9,
                lamp: mode == .tabletop ? SIMD2(6, 2) : SIMD2(10, 4)))
        }
        if mode == .stadium {
            // The night. A sphere seen from inside, far enough out that the
            // bowl never reaches it.
            let sky = ModelEntity(mesh: .generateSphere(radius: 700),
                                  materials: [StadiumMeshes.material(s.palette["sky.top"] ?? "#03050A")])
            sky.scale = SIMD3(-1, 1, 1)
            content.addChild(sky)
        }
        ball.model = ModelComponent(mesh: .generateSphere(radius: mode == .tabletop ? 1.2 : 0.6),
                                    materials: [StadiumMeshes.material("#7A3E17")])
        ball.scale = SIMD3(1.6, 1, 1)
        tintKey = "unset"
        tearDownDrive()
    }

    // MARK: the drive

    private func tearDownDrive() {
        flight?.cancel()
        flight = nil
        driveRoot.children.removeAll()
        arcEntities.removeAll()
        motion.reset()
        driveID = ""
    }

    private func arcEntity(_ arc: SceneSpec.Arc, spec s: SceneSpec) -> Entity {
        let colour = s.palette[arc.color] ?? "#FFFFFF"
        let radius: Float = mode == .tabletop ? 0.45 : 0.22
        let holder = Entity()
        holder.name = "arc.\(arc.id)"
        let emphasis = arc.style == "score"
        let core = StadiumMeshes.tubeEntity(SceneMath.dashes(arc), radius: radius * (emphasis ? 1.5 : 1),
                                            color: colour, name: "arc.core")
        let halo = StadiumMeshes.tubeEntity([SceneMath.samples(arc)], radius: radius * 3.2,
                                            color: colour, opacity: emphasis ? 0.3 : 0.14,
                                            name: "arc.halo")
        holder.addChild(halo)
        holder.addChild(core)
        return holder
    }

    private func updateDrive(_ s: SceneSpec, previous: SceneSpec?, reduceMotion: Bool) {
        guard let drive = s.shownDrive else {
            tearDownDrive()
            return
        }
        let oldIDs = Set(previous?.shownDrive?.arcs.map(\.id) ?? [])
        let lostAPlay = !oldIDs.isEmpty && drive.id == driveID
            && !oldIDs.isSubset(of: Set(drive.arcs.map(\.id)))
        // A new drive right after the old one is the game moving on, and its
        // plays fly. Anything else - a scrub, a jump to another quarter, the
        // first scene of all - is history, and is laid down at rest.
        let nextDrive = previous.map { p in
            drive.id != driveID && s.drives.count >= p.drives.count
                && s.drives.firstIndex(where: { $0.id == drive.id }) == (p.drives.firstIndex(where: { $0.id == driveID }) ?? -2) + 1
        } ?? false
        if drive.id != driveID || lostAPlay {
            tearDownDrive()
            driveID = drive.id
            let initial = !nextDrive
            _ = motion.arrive(drive, initial: initial)
            if initial {
                for arc in drive.arcs { addArc(arc, s) }
                return
            }
        } else {
            _ = motion.arrive(drive, initial: false)
        }
        fly(reduceMotion: reduceMotion)
    }

    private func addArc(_ arc: SceneSpec.Arc, _ s: SceneSpec) {
        guard arcEntities[arc.id] == nil else { return }
        let e = arcEntity(arc, spec: s)
        arcEntities[arc.id] = e
        driveRoot.addChild(e)
    }

    /// The ball flies each queued play along its own arc, then the arc is
    /// laid down and the lasers move up. Reduce motion lands it instead.
    private func fly(reduceMotion: Bool) {
        guard flight == nil else { return }
        flight = Task { [weak self] in
            while let self, !Task.isCancelled {
                guard let s = self.spec,
                      let (arc, seconds) = self.motion.next(reduceMotion: reduceMotion,
                                                            floor: s.motion.floorSeconds)
                else { break }
                self.ball.isEnabled = true
                if seconds <= 0 {
                    self.ball.position = SceneMath.point(on: arc, at: 1)
                } else {
                    let steps = max(8, Int(seconds * 30))
                    self.ball.position = SceneMath.point(on: arc, at: 0)
                    for i in 1...steps {
                        if Task.isCancelled { return }
                        let at = SceneMath.point(on: arc, at: Double(i) / Double(steps))
                        self.ball.move(to: Transform(scale: self.ball.scale, rotation: self.ball.orientation,
                                                     translation: at),
                                       relativeTo: self.dynamic, duration: seconds / Double(steps),
                                       timingFunction: .linear)
                        try? await Task.sleep(for: .seconds(seconds / Double(steps)))
                    }
                }
                self.addArc(arc, s)
            }
            guard let self else { return }
            self.flight = nil
            if let s = self.spec { self.settle(s, animated: !reduceMotion) }
        }
    }

    // MARK: ball, beacon, lasers

    private func settle(_ s: SceneSpec, animated: Bool) {
        let duration = animated ? 0.35 : 0
        if let b = s.ball {
            ball.isEnabled = true
            beacon.isEnabled = true
            let at = SceneMath.local(x: b.x, y: 0.8, z: b.z)
            move(ball, to: at, duration: duration)
            let height = Float(b.beacon.height)
            let key = "\(height)|\(b.beacon.color)"
            if key != beaconKey {
                beaconKey = key
                beacon.model = ModelComponent(
                    mesh: .generateCylinder(height: height, radius: mode == .tabletop ? 1.4 : 0.7),
                    materials: [StadiumMeshes.material(s.palette[b.beacon.color] ?? "#BFE3FF", opacity: 0.35)])
            }
            move(beacon, to: SceneMath.local(x: b.x, y: Double(height) / 2, z: b.z), duration: duration)
        } else {
            ball.isEnabled = false
            beacon.isEnabled = false
        }
        let want = Dictionary(uniqueKeysWithValues: s.lasers.map { ($0.kind, $0) })
        for (kind, e) in lasers where want[kind] == nil {
            e.removeFromParent()
            lasers[kind] = nil
        }
        for (kind, laser) in want {
            let e = lasers[kind] ?? {
                let made = ModelEntity(mesh: .generateBox(width: 0.35, height: 0.08,
                                                         depth: Float(s.field.width)),
                                       materials: [StadiumMeshes.material(s.palette[laser.color] ?? "#FFD400")])
                made.position = SceneMath.local(x: laser.x, y: 0.05)
                dynamic.addChild(made)
                lasers[kind] = made
                return made
            }()
            move(e, to: SceneMath.local(x: laser.x, y: 0.05), duration: duration)
        }
    }

    private func move(_ e: Entity, to at: SIMD3<Float>, duration: Double) {
        if duration <= 0 || !e.isEnabled {
            e.position = at
        } else {
            e.move(to: Transform(scale: e.scale, rotation: e.orientation, translation: at),
                   relativeTo: e.parent, duration: duration, timingFunction: .easeInOut)
        }
    }

    // MARK: horizon and tint

    private func updateHorizon(_ s: SceneSpec) {
        let key = "\(s.winProbability.series.count)|\(s.winProbability.series.last ?? -1)"
        guard key != horizonKey else { return }
        horizonKey = key
        horizon.children.removeAll()
        let pts = SceneMath.horizon(s.winProbability)
        guard pts.count > 1 else { return }
        let h = s.winProbability.horizon
        let rail = { (y: Double) -> [SIMD3<Float>] in
            [SceneMath.local(x: h.x0, y: y, z: h.z), SceneMath.local(x: h.x1, y: y, z: h.z)]
        }
        let thin: Float = mode == .tabletop ? 0.35 : 0.18
        horizon.addChild(StadiumMeshes.tubeEntity([rail(h.y0), rail(h.y1)], radius: thin,
                                                  color: "#FFFFFF", opacity: 0.18, name: "horizon.rails"))
        horizon.addChild(StadiumMeshes.tubeEntity([rail((h.y0 + h.y1) / 2)], radius: thin * 0.7,
                                                  color: "#FFFFFF", opacity: 0.3, name: "horizon.even"))
        horizon.addChild(StadiumMeshes.tubeEntity([pts], radius: thin * 2.2,
                                                  color: s.palette["ink"] ?? "#F7F6F2", name: "horizon.line"))
    }

    /// The scoring side's crowd lights up in its own colour; the other side
    /// dims. Materials are swapped only when the tint changes.
    private func updateTint(_ s: SceneSpec) {
        let tint = s.bowl.sectionTint
        let key = tint.side ?? "none"
        guard key != tintKey else { return }
        tintKey = key
        let teamColours: Set<String> = [s.bowl.crowd.home, s.bowl.crowd.away]
        for (section, colours) in crowd {
            for (colour, e) in colours {
                let material: UnlitMaterial
                if tint.side == nil {
                    material = StadiumMeshes.material(colour)
                } else if tint.side == section {
                    // The fans in club colours take the scoring chip; the rest
                    // of the section keeps its own colour at full strength.
                    let fill = teamColours.contains(colour) ? (tint.color ?? colour) : colour
                    material = StadiumMeshes.material(fill)
                } else {
                    material = StadiumMeshes.material(colour, opacity: tint.dim)
                }
                e.model?.materials = [material]
            }
        }
    }
}
