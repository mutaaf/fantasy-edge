import RealityKit
import simd
import UIKit

/// The bowl: tiers, seats, aisles and stairs, rails, vomitories, the wall
/// cap, the concourse, the club and press box under the upper deck, the
/// ribbon fascia and the lip over it, tunnels, the parapet. The ribbon's
/// content is Broadcast's; the boards on the wall face are Sideline's. Reads
/// `bowl` and `visual.bowl`.
///
/// Draws the kit from tools/blender/bowl (`visual.bowl.models`):
///   - stands     the structure, always.
///   - seatsFar   `bands` for every seat outside the preset regions, and a
///                `fill_<preset>` for each region.
///   - near       `near_<preset>`: stairs, rails and modelled chairs in front
///                of the wearer.
///   - table      the tabletop model, cut away on the home side.
/// Only what is drawn is attached: the wearer's near patch, every other
/// preset's fill. A seat change swaps them, so `-stadiumStats` counts exactly
/// what is on screen. Without the kit it falls back to `buildProcedural`.
///
/// Publishes to the blackboard: where the press box is, and a point in the
/// stands behind each end zone.
@MainActor
final class BowlActor: StadiumActor {
    let name = "bowl"
    let root = Entity()

    /// Near patches and fills by preset id, held off-stage until needed.
    private var near: [String: Entity] = [:]
    private var fills: [String: Entity] = [:]
    private var activePreset: String?

    init() { root.name = "actor.bowl" }

    func build(_ c: StadiumContext) {
        clear()
        near = [:]
        fills = [:]
        activePreset = nil
        let B = c.look.bowl
        let scale = Float(1 / B.yardMeters)

        if c.tabletop {
            guard let table = c.assets.model("bowl.table") else { return buildProcedural(c) }
            table.scale = SIMD3(repeating: scale)
            dress(table, look: B)
            root.addChild(table)
        } else {
            guard let stands = c.assets.model("bowl.stands"), let far = c.assets.model("bowl.seatsFar"),
                  let patches = c.assets.model("bowl.near") else { return buildProcedural(c) }
            for e in [stands, far, patches] {
                e.scale = SIMD3(repeating: scale)
                dress(e, look: B)
            }
            // Pull the per-preset pieces out of their templates; keep the
            // always-drawn remainder (stands, bands) attached.
            for (prefix, into) in [("near_", \BowlActor.near), ("fill_", \BowlActor.fills)] {
                let source = prefix == "near_" ? patches : far
                for piece in Self.descendants(of: source) where piece.name.hasPrefix(prefix) {
                    // USD nests a mesh under an Xform of the same name; take the outermost.
                    if let parent = piece.parent, parent.name.hasPrefix(prefix) { continue }
                    let id = String(piece.name.dropFirst(prefix.count))
                    // The file's Y-up conversion lives on the prims above the
                    // piece. Carry the piece's whole transform relative to the
                    // model root into the holder, or it lands rotated a quarter
                    // turn - the dark ramp across `crowd-closeup`.
                    let local = piece.transformMatrix(relativeTo: source)
                    let holder = Entity()
                    holder.name = piece.name
                    holder.scale = SIMD3(repeating: scale)
                    piece.removeFromParent()
                    holder.addChild(piece)
                    piece.setTransformMatrix(local, relativeTo: holder)
                    self[keyPath: into][id] = holder
                }
            }
            // Debug: `-bowlSkip stands,far,near,fills` leaves pieces out, to find
            // which one draws something in a look-dev shot.
            let skip = Self.skipped
            if !skip.contains("stands") { root.addChild(stands) }
            if !skip.contains("far") { root.addChild(far) }
            if skip.contains("near") { near = [:] }
            if skip.contains("fills") { fills = [:] }
            choosePreset(c)
        }
        publish(c)
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard !c.tabletop, !near.isEmpty || !fills.isEmpty else { return }
        choosePreset(c)
    }

    // MARK: - presets

    /// The preset whose seat is nearest the wearer's eye; the scene's default
    /// seat before Experience has placed anyone.
    private func preset(_ c: StadiumContext) -> String? {
        let st = c.spec.presentation.stadium
        let options = st.seats ?? []
        guard let eye = c.shared.seat else { return st.defaultSeat }
        var best: (String, Float)?
        for o in options {
            let p = SceneMath.local(x: o.x, y: o.y, z: o.z)
            let d = simd_distance(SIMD2(p.x, p.z), SIMD2(eye.x, eye.z))
            if best == nil || d < best!.1 { best = (o.id, d) }
        }
        return best?.0
    }

    private func choosePreset(_ c: StadiumContext) {
        let want = preset(c) ?? ""
        guard want != activePreset else { return }
        activePreset = want
        for (id, e) in near {
            if id == want { if e.parent == nil { attach(e) } } else { e.removeFromParent() }
        }
        for (id, e) in fills {
            if id == want { e.removeFromParent() } else if e.parent == nil { attach(e) }
        }
    }

    /// Image-based light does not inherit, and the composer points models at
    /// the probe once, after build - so a piece held off-stage then would come
    /// in unlit, as the black ledge along the bottom of `bowl-wide` did. It
    /// takes the receiver the stands already carry.
    private func attach(_ e: Entity) {
        root.addChild(e)
        guard let receiver = Self.descendants(of: root)
            .lazy.compactMap({ $0.components[ImageBasedLightReceiverComponent.self] }).first else { return }
        for node in Self.descendants(of: e) where node.components.has(ModelComponent.self) {
            node.components.set(receiver)
        }
    }

    // MARK: - materials

    /// Seat colour on every chair and band; interiors lit to their authored
    /// brightness. USD carries neither a base-colour factor over a texture nor
    /// an emissive strength, so they are applied here from `visual.bowl`.
    private func dress(_ e: Entity, look B: SceneSpec.Look.BowlLook) {
        let seat = StadiumLook.color(B.seatColor)
        // The seats in front of the wearer face away from every floodlight on
        // the far rim, and a night probe alone left them a black ledge along
        // the bottom of the view. Spill from the concourse behind is carried
        // as a low self-light on the foreground only (`nearLift`).
        let lift = StadiumLook.color(B.seatColor, scale: 1)
        for node in Self.descendants(of: e) {
            guard var model = node.components[ModelComponent.self] else { continue }
            var inNear = false
            var up: Entity? = node
            while let u = up { if u.name.hasPrefix("near_") { inNear = true; break }; up = u.parent }
            model.materials = model.materials.map { material in
                guard var pbr = material as? PhysicallyBasedMaterial else { return material }
                let n = material.name ?? ""
                if n.contains("seat_plastic") || n.contains("seat_band") {
                    pbr.baseColor.tint = seat
                    if inNear {
                        pbr.emissiveColor = .init(color: lift)
                        pbr.emissiveIntensity = Float(B.nearLift)
                    }
                } else if inNear && (n.contains("plaque") || n.contains("stair") || n.contains("seat_hardware")) {
                    pbr.emissiveColor = .init(color: .init(white: 0.55, alpha: 1))
                    pbr.emissiveIntensity = Float(B.nearLift)
                } else if n.contains("interiors") {
                    pbr.emissiveIntensity = 3.5
                }
                return pbr
            }
            node.components.set(model)
        }
    }

    static var skipped: Set<String> {
        let args = ProcessInfo.processInfo.arguments
        let value: String
        if let i = args.firstIndex(of: "-bowlSkip"), i + 1 < args.count {
            value = args[i + 1]
        } else if let env = ProcessInfo.processInfo.environment["BOWL_SKIP"] {
            value = env                               // SIMCTL_CHILD_BOWL_SKIP from a harness
        } else {
            return []
        }
        return Set(value.split(separator: ",").map(String.init))
    }

    static func descendants(of e: Entity) -> [Entity] {
        var out: [Entity] = []
        func walk(_ x: Entity) {
            out.append(x)
            x.children.forEach(walk)
        }
        walk(e)
        return out
    }

    // MARK: - blackboard

    private func publish(_ c: StadiumContext) {
        let s = c.spec, shape = s.bowl.shape
        if let pb = s.bowl.pressBox {
            let sign: Float = pb.side == "far" ? -1 : 1
            let z = sign * Float(shape.halfWidth + pb.offset)
            c.shared.pressBox = SIMD3(Float((pb.fromX + pb.toX) / 2 - 50), Float((pb.rise[0] + pb.rise[1]) / 2), z)
        }
        let tiers = c.tiers
        let behind = (tiers.first?.inner ?? 6) + 8
        let home = SceneMath.bowlPoint(shape, offset: behind, angle: .pi)
        let away = SceneMath.bowlPoint(shape, offset: behind, angle: 0)
        let h = Float(tiers.first.map { SceneMath.tierHeight($0, offset: behind) } ?? 6)
        c.shared.standsBehind = (SIMD3(Float(home.x), h, Float(home.z)), SIMD3(Float(away.x), h, Float(away.z)))
    }
}
