import Foundation
import RealityKit
import simd

extension MeshBuilder {
    /// A flat strip through points, turned at every point to face `view`, so
    /// a trail reads as a line of light with soft edges from wherever it is
    /// seen. u runs `uRange` along the strip by length; v crosses it 0..1.
    mutating func facingStrip(_ pts: [SIMD3<Float>], halfWidth: Float,
                              view: (SIMD3<Float>) -> SIMD3<Float>,
                              uRange: ClosedRange<Float> = 0...1) {
        guard pts.count > 1, halfWidth > 0 else { return }
        var lengths: [Float] = [0]
        for i in 1..<pts.count { lengths.append(lengths[i - 1] + simd_distance(pts[i - 1], pts[i])) }
        let total = max(1e-6, lengths.last!)
        let base = UInt32(positions.count)
        var lastSide = SIMD3<Float>(0, 1, 0)
        for (i, p) in pts.enumerated() {
            let ahead = pts[min(i + 1, pts.count - 1)] - pts[max(i - 1, 0)]
            let t = simd_length(ahead) > 1e-6 ? simd_normalize(ahead) : SIMD3(1, 0, 0)
            let toEye = view(p)
            var side = simd_cross(t, toEye)
            if simd_length(side) < 1e-4 { side = lastSide } else { side = simd_normalize(side) }
            // Keep the strip from flipping over as the view swings past it.
            if simd_dot(side, lastSide) < 0, i > 0 { side = -side }
            lastSide = side
            let u = uRange.lowerBound + (uRange.upperBound - uRange.lowerBound) * lengths[i] / total
            let n = toEye
            positions += [p - side * halfWidth, p + side * halfWidth]
            normals += [n, n]
            uvs += [SIMD2(u, 0), SIMD2(u, 1)]
        }
        for i in 0..<UInt32(pts.count - 1) {
            let a = base + i * 2, b = a + 1, c = a + 2, d = a + 3
            indices += [a, c, b, b, c, d]
        }
    }
}

/// The drive drawn in light: one trail per play, the newest bright, the rest
/// ghosting and thinning with age (`visual.broadcast.trail`).
@MainActor
final class BroadcastTrails {
    let root = Entity()
    private(set) var order: [String] = []
    private var arcs: [String: SceneSpec.Arc] = [:]
    private var entities: [String: Entity] = [:]
    /// Kicks laid while watching, and when: they fade to `kick.restOpacity`.
    private var kicks: [String: (born: Double, colour: String, core: Double, halo: Double)] = [:]
    /// Kicks that have finished fading: a rebuild keeps them at rest.
    private var rested: Set<String> = []

    init() { root.name = "broadcast.trails" }

    var count: Int { order.count }
    func has(_ id: String) -> Bool { arcs[id] != nil }

    func clear() {
        root.children.removeAll()
        live = nil
        liveDrawn = -1
        order.removeAll()
        arcs.removeAll()
        entities.removeAll()
        kicks.removeAll()
        rested.removeAll()
    }

    /// Lay a play down and re-age the drive behind it.
    func add(_ arc: SceneSpec.Arc, _ c: StadiumContext) {
        guard arcs[arc.id] == nil else { return }
        arcs[arc.id] = arc
        order.append(arc.id)
        if arc.shape == "kick" { kicks[arc.id] = (c.shared.time, "", 0, 0) }
        rebuild(c)
    }

    /// A whole drive laid down at rest, aged once rather than once per play.
    func set(_ list: [SceneSpec.Arc], _ c: StadiumContext) {
        for arc in list where arcs[arc.id] == nil {
            arcs[arc.id] = arc
            order.append(arc.id)
        }
        rebuild(c)
    }

    /// Everything again - after a seat change the strips must face the new eye.
    ///
    /// The newest `age.individual` plays are drawn one by one, each in its
    /// style's colour and faded by its age. Everything older is merged into a
    /// single ghost in `age.historyColor`: two draw parts for the whole back
    /// of the drive rather than two per play, which a fifteen-play drive would
    /// otherwise spend past the actor's budget.
    func rebuild(_ c: StadiumContext) {
        for e in entities.values { e.removeFromParent() }
        entities.removeAll()
        let look = c.look.broadcast.trail
        var historyCore = MeshBuilder(), historyHalo = MeshBuilder()
        var historyLowered = false
        for (index, id) in order.enumerated() {
            guard var arc = arcs[id] else { continue }
            let age = order.count - 1 - index
            if age > 0, let lowered = Self.lowered(arc, c) {
                arc = lowered
                if age >= max(1, look.age.individual) { historyLowered = true }
            }
            let g = geometry(arc, age: age, c)
            if age < max(1, look.age.individual) {
                let e = entity(arc, geometry: g, c)
                entities[id] = e
                root.addChild(e)
            } else {
                historyCore.append(g.core)
                historyHalo.append(g.halo)
            }
        }
        if !historyCore.isEmpty {
            let colour = c.spec.palette[look.age.historyColor] ?? "#C9CCD1"
            let ghost = historyLowered ? min(look.age.historyOpacity, look.lowSeat.historyOpacity) : look.age.historyOpacity
            let holder = Entity()
            holder.name = "trail.history"
            holder.addChild(historyHalo.entity("trail.history.halo",
                StadiumLook.glow(colour, opacity: look.haloOpacity * ghost, texture: c.assets.texture("broadcast.trailHalo"))))
            holder.addChild(historyCore.entity("trail.history.core",
                StadiumLook.glow(colour, opacity: look.coreOpacity * ghost, texture: c.assets.texture("broadcast.trailCore"))))
            entities["history"] = holder
            root.addChild(holder)
        }
    }

    /// A play already done, laid lower for a seat whose eye is below its
    /// flight. From the field or the front rows every pass of a drive stands
    /// up over the far stands, and five of them read as a wall of wire arches
    /// rather than a drive. The newest play keeps its real height - that is
    /// the one being watched, and the one the ball flew - and the ones before
    /// it lie down to `lowSeat.apexOverEye` of the eye's height (never under
    /// `minApexYards`), where they read as the drive's path along the grass.
    /// Where the eye is already above the flights, nothing changes. Nil when
    /// the arc keeps its height.
    static func lowered(_ arc: SceneSpec.Arc, _ c: StadiumContext) -> SceneSpec.Arc? {
        guard let seat = c.shared.seat, !c.tabletop else { return nil }
        let rule = c.look.broadcast.trail.lowSeat
        let cap = max(rule.minApexYards, Double(seat.y) * rule.apexOverEye)
        guard arc.apex > cap else { return nil }
        return SceneSpec.Arc(id: arc.id, style: arc.style, shape: arc.shape, type: arc.type, fromX: arc.fromX,
                             toX: arc.toX, lane: arc.lane, apex: cap, color: arc.color, dash: arc.dash,
                             seconds: arc.seconds, duration: arc.duration, side: arc.side, text: arc.text,
                             period: arc.period, clock: arc.clock, down: arc.down, distance: arc.distance)
    }

    private struct Geometry {
        var core = MeshBuilder()
        var halo = MeshBuilder()
        var fade: Double = 1
        var emphasis = false
    }

    private func geometry(_ arc: SceneSpec.Arc, age: Int, _ c: StadiumContext) -> Geometry {
        let look = c.look.broadcast.trail
        var g = Geometry()
        g.emphasis = arc.style == "score"
        var width = look.core.value(tabletop: c.tabletop)
        if let seat = c.shared.seat, !c.tabletop {
            width *= SceneMath.nearSeatScale(SceneMath.samples(arc, count: 32), seat: seat, rule: look.nearSeat)
        }
        let a = Double(age)
        g.fade = age == 0 ? 1 : max(look.age.minOpacity, pow(look.age.decay, a))
        // Seen along its own length - a kick from behind the posts - a trail
        // stands up as a streak. Thin it and fade it toward a subtle core.
        // Only arcs that stand up can streak: runs and penalties hug the grass,
        // and read foreshortened, not end-on, from the sideline seats.
        if let seat = c.shared.seat, !c.tabletop, look.edge.shapes.contains(arc.shape) {
            // A kick stands tall, so it fades over a steeper range than a play along the grass.
            let rule = arc.shape == "kick" ? SceneSpec.Look.TrailEdge(fullDegrees: look.kick.fullDegrees,
                goneDegrees: look.kick.goneDegrees, minOpacity: look.edge.minOpacity, minScale: look.edge.minScale) : look.edge
            let seen = Self.sideOn(arc, seat: seat, edge: rule)
            g.fade *= look.edge.minOpacity + (1 - look.edge.minOpacity) * seen
            width *= look.edge.minScale + (1 - look.edge.minScale) * seen
        }
        width *= age == 0 ? 1 : max(look.age.minScale, pow(look.age.thin, a))
        let core = Float(width * (g.emphasis ? look.scoreEmphasis.core : 1))
        let halo = Float(width * look.haloScale * (g.emphasis ? look.scoreEmphasis.halo : 1))
        let view = Self.view(c)
        let pieces = SceneMath.dashes(arc, count: 72)
        let total = Float(pieces.count)
        for (i, piece) in pieces.enumerated() {
            let lo = pieces.count == 1 ? 0 : Float(i) / total
            let hi = pieces.count == 1 ? 1 : Float(i + 1) / total
            g.core.facingStrip(piece, halfWidth: core / 2, view: view, uRange: lo...hi)
        }
        g.halo.facingStrip(SceneMath.samples(arc, count: 72), halfWidth: halo / 2, view: view)
        return g
    }

    private func entity(_ arc: SceneSpec.Arc, geometry g: Geometry, _ c: StadiumContext) -> Entity {
        let look = c.look.broadcast.trail
        let colour = c.spec.palette[arc.color] ?? "#FFFFFF"
        var g = g
        if rested.contains(arc.id) { g.fade *= look.kick.restOpacity }
        if let k = kicks[arc.id] {
            kicks[arc.id] = (k.born, colour, look.coreOpacity * g.fade,
                             look.haloOpacity * g.fade * (g.emphasis ? look.scoreEmphasis.halo : 1))
        }
        let holder = Entity()
        holder.name = "trail.\(arc.id)"
        holder.addChild(g.halo.entity("trail.halo",
            StadiumLook.glow(colour, opacity: look.haloOpacity * g.fade * (g.emphasis ? look.scoreEmphasis.halo : 1),
                             texture: c.assets.texture("broadcast.trailHalo"))))
        holder.addChild(g.core.entity("trail.core",
            StadiumLook.glow(colour, opacity: look.coreOpacity * g.fade, texture: c.assets.texture("broadcast.trailCore"))))
        return holder
    }

    /// Kicks just laid fade to a rest level over `kick.fadeSeconds`, so the
    /// flight reads while it happens and does not stand over the posts after.
    /// Reduce motion lands them at rest at once.
    func update(_ c: StadiumContext) {
        guard !kicks.isEmpty, !Self.holdTrails else { return }
        let rule = c.look.broadcast.trail.kick
        for (id, k) in kicks {
            guard let holder = entities[id], holder.children.count == 2, !k.colour.isEmpty else { continue }
            let t = c.reduceMotion ? 1 : min(1, (c.shared.time - k.born) / max(0.05, rule.fadeSeconds))
            let f = 1 - (1 - rule.restOpacity) * t
            if let halo = holder.children[0] as? ModelEntity {
                halo.model?.materials = [StadiumLook.glow(k.colour, opacity: k.halo * f, texture: c.assets.texture("broadcast.trailHalo"))]
            }
            if let core = holder.children[1] as? ModelEntity {
                core.model?.materials = [StadiumLook.glow(k.colour, opacity: k.core * f, texture: c.assets.texture("broadcast.trailCore"))]
            }
            if t >= 1 { kicks[id] = nil; rested.insert(id) }
        }
    }

    private var live: Entity?
    private var liveDrawn: Double = -1

    /// The play in the air, drawn behind the ball as far as it has flown, so
    /// a trail grows with the flight instead of appearing only on landing.
    /// Redrawn at most every `live.intervalSeconds`; `clearLive` when it lands.
    func grow(_ arc: SceneSpec.Arc, to t: Double, _ c: StadiumContext) {
        let look = c.look.broadcast.trail
        guard c.shared.time - liveDrawn >= look.live.intervalSeconds || t >= 1 else { return }
        liveDrawn = c.shared.time
        live?.removeFromParent()
        let u = max(0.02, min(1, t))
        let n = max(4, Int(48 * u))
        let pts = (0...n).map { SceneMath.point(on: arc, at: u * Double($0) / Double(n)) }
        var width = look.core.value(tabletop: c.tabletop)
        var fade = look.live.opacity
        if let seat = c.shared.seat, !c.tabletop, look.edge.shapes.contains(arc.shape) {
            let rule = arc.shape == "kick" ? SceneSpec.Look.TrailEdge(fullDegrees: look.kick.fullDegrees,
                goneDegrees: look.kick.goneDegrees, minOpacity: look.edge.minOpacity, minScale: look.edge.minScale) : look.edge
            let seen = Self.sideOn(arc, seat: seat, edge: rule)
            fade *= look.edge.minOpacity + (1 - look.edge.minOpacity) * seen
            width *= look.edge.minScale + (1 - look.edge.minScale) * seen
        }
        let view = Self.view(c)
        var core = MeshBuilder(), halo = MeshBuilder()
        core.facingStrip(pts, halfWidth: Float(width) / 2, view: view)
        halo.facingStrip(pts, halfWidth: Float(width * look.haloScale) / 2, view: view)
        let colour = c.spec.palette[arc.color] ?? "#FFFFFF"
        let holder = Entity()
        holder.name = "trail.live"
        holder.addChild(halo.entity("trail.live.halo", StadiumLook.glow(colour, opacity: look.haloOpacity * fade,
                                                                         texture: c.assets.texture("broadcast.trailHalo"))))
        holder.addChild(core.entity("trail.live.core", StadiumLook.glow(colour, opacity: look.coreOpacity * fade,
                                                                         texture: c.assets.texture("broadcast.trailCore"))))
        root.addChild(holder)
        live = holder
    }

    func clearLive() {
        live?.removeFromParent()
        live = nil
        liveDrawn = -1
    }

    /// Look-dev only: `-trailHold` freezes a kick's fade so a shot taken when
    /// the moment fires still sees the trail at full strength. Never in release.
    static let holdTrails: Bool = {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("-trailHold")
        #else
        return false
        #endif
    }()

    /// How side-on a seat sees an arc, 0...1: the mean angle between each
    /// piece of the arc and the sightline to it, mapped from
    /// `edge.goneDegrees` (0, end-on) to `edge.fullDegrees` (1).
    nonisolated static func sideOn(_ arc: SceneSpec.Arc, seat: SIMD3<Float>, edge: SceneSpec.Look.TrailEdge) -> Double {
        let n = 32
        var total = 0.0
        for i in 0..<n {
            let p = SceneMath.point(on: arc, at: Double(i) / Double(n))
            let q = SceneMath.point(on: arc, at: Double(i + 1) / Double(n))
            let t = q - p, d = seat - (p + q) / 2
            let tl = simd_length(t), dl = simd_length(d)
            guard tl > 1e-5, dl > 1e-5 else { total += 90; continue }
            total += acos(Double(min(1, abs(simd_dot(t, d)) / (tl * dl)))) * 180 / .pi
        }
        let deg = total / Double(n)
        return max(0, min(1, (deg - edge.goneDegrees) / max(1e-6, edge.fullDegrees - edge.goneDegrees)))
    }

    /// The direction a strip faces at a point: the wearer's eyes in the
    /// stadium, the tokens' fixed view over the table.
    static func view(_ c: StadiumContext) -> (SIMD3<Float>) -> SIMD3<Float> {
        if let seat = c.shared.seat, !c.tabletop {
            return { p in
                let d = seat - p
                return simd_length(d) > 1e-4 ? simd_normalize(d) : SIMD3(0, 0, 1)
            }
        }
        let v = c.look.broadcast.trail.tabletopView
        let fixed = v.count == 3 ? SIMD3(Float(v[0]), Float(v[1]), Float(v[2])) : SIMD3<Float>(0, 0.85, 1)
        let n = simd_length(fixed) > 1e-6 ? simd_normalize(fixed) : SIMD3(0, 0, 1)
        return { _ in n }
    }
}
