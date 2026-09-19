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
/// Only what is drawn is attached: the wearer's near patch, and the bands
/// merged with every other preset's fill. A seat change swaps them, so `-stadiumStats` counts exactly
/// what is on screen. Without the kit it falls back to `buildProcedural`.
///
/// Publishes to the blackboard: where the press box is, and a point in the
/// stands behind each end zone.
@MainActor
final class BowlActor: StadiumActor {
    let name = "bowl"
    let root = Entity()

    /// Near patches by preset id, held off-stage until needed.
    private var near: [String: Entity] = [:]
    /// Every preset's fill, flattened into `seatsFar`'s space. They and the
    /// bands share one material, so they draw as one merged mesh - the bands
    /// plus every fill but the wearer's - rebuilt on a seat change. Drawn as
    /// separate pieces they were five draw parts; merged they are one.
    private var fills: [String: MeshBuilder] = [:]
    private var bands = MeshBuilder()
    private var bandsEntity: ModelEntity?
    private var activePreset: String?
    private var mergedMaterial: (any Material)?

    init() { root.name = "actor.bowl" }

    func build(_ c: StadiumContext) {
        clear()
        near = [:]
        fills = [:]
        bands = MeshBuilder()
        bandsEntity = nil
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
            // Pull the per-preset pieces out of their templates; the stands
            // stay attached as they are.
            for piece in Self.descendants(of: far) where piece.name.hasPrefix("fill_") {
                if let parent = piece.parent, parent.name.hasPrefix("fill_") { continue }
                var mesh = MeshBuilder()
                Self.flatten(piece, into: &mesh, relativeTo: far)
                fills[String(piece.name.dropFirst("fill_".count))] = mesh
                piece.removeFromParent()
            }
            // What is left of seatsFar is the bands: flatten them beside the
            // fills and draw the lot as one entity with the bands' material.
            let bandModels = Self.descendants(of: far).filter { $0.components.has(ModelComponent.self) }
            let bandMaterial = bandModels.first?.components[ModelComponent.self]?.materials.first
            for piece in bandModels {
                Self.flatten(piece, into: &bands, relativeTo: far)
                piece.removeFromParent()
            }
            if let bandMaterial {
                let merged = ModelEntity()
                merged.name = "bands.merged"
                far.addChild(merged)
                bandsEntity = merged
                mergedMaterial = bandMaterial
            }
            for piece in Self.descendants(of: patches) where piece.name.hasPrefix("near_") {
                // USD nests a mesh under an Xform of the same name; take the outermost.
                if let parent = piece.parent, parent.name.hasPrefix("near_") { continue }
                let id = String(piece.name.dropFirst("near_".count))
                // The file's Y-up conversion lives on the prims above the
                // piece. Carry the piece's whole transform relative to the
                // model root into the holder, or it lands rotated a quarter
                // turn - the dark ramp across `crowd-closeup`.
                let local = piece.transformMatrix(relativeTo: patches)
                let holder = Entity()
                holder.name = piece.name
                holder.scale = SIMD3(repeating: scale)
                piece.removeFromParent()
                holder.addChild(piece)
                piece.setTransformMatrix(local, relativeTo: holder)
                near[id] = holder
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
        relayBands(except: want)
    }

    /// The bands and every fill but `except`'s, as one mesh.
    private func relayBands(except: String) {
        guard let bandsEntity, let mergedMaterial else { return }
        var mesh = bands
        for (id, fill) in fills.sorted(by: { $0.key < $1.key }) where id != except { mesh.append(fill) }
        guard let resource = mesh.resource("bands.merged") else { return }
        if var model = bandsEntity.model {
            model.mesh = resource
            bandsEntity.model = model
        } else {
            bandsEntity.model = ModelComponent(mesh: resource, materials: [mergedMaterial])
        }
    }

    /// Every mesh part under `e`, in `space`'s coordinates, appended to `mesh`.
    private static func flatten(_ e: Entity, into mesh: inout MeshBuilder, relativeTo space: Entity) {
        for node in descendants(of: e) {
            guard let model = node.components[ModelComponent.self] else { continue }
            let toSpace = node.transformMatrix(relativeTo: space)
            let contents = model.mesh.contents
            for instance in contents.instances {
                guard let m = contents.models[instance.model] else { continue }
                let xf = toSpace * instance.transform
                let n3 = simd_float3x3(SIMD3(xf.columns.0.x, xf.columns.0.y, xf.columns.0.z),
                                       SIMD3(xf.columns.1.x, xf.columns.1.y, xf.columns.1.z),
                                       SIMD3(xf.columns.2.x, xf.columns.2.y, xf.columns.2.z)).inverse.transpose
                for part in m.parts {
                    guard let idx = part.triangleIndices?.elements else { continue }
                    let pos = part.positions.elements
                    let base = UInt32(mesh.positions.count)
                    mesh.positions += pos.map { p in let v = xf * SIMD4(p, 1); return SIMD3(v.x, v.y, v.z) }
                    mesh.normals += (part.normals?.elements ?? Array(repeating: SIMD3(0, 1, 0), count: pos.count))
                        .map { simd_normalize(n3 * $0) }
                    mesh.uvs += part.textureCoordinates?.elements ?? Array(repeating: SIMD2(0, 0), count: pos.count)
                    mesh.indices += idx.map { $0 + base }
                }
            }
        }
    }

    /// Image-based light does not inherit, and the composer points models at
    /// the probe once, after build - so a piece held off-stage then would come
    /// in unlit, as the black ledge along the bottom of `bowl-wide` did. It
    /// takes the receiver the stands already carry.
    private func attach(_ e: Entity) {
        root.addChild(e)
        // Shadow casting is opt-in and the composer only marks what exists at
        // build; a near patch or fill swapped in later marks itself.
        for node in Self.descendants(of: e) where node.components.has(ModelComponent.self) {
            node.components.set(DynamicLightShadowComponent(castsShadow: false))
        }
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
                // Debug: `-bowlSkip mat:concrete,mat:trim` hides whole materials.
                // The model-level skip answers "which model", which is rarely the
                // question - a beige mass in a frame is one material somewhere in
                // `stands`, and this is what names it in a single run.
                if Self.skipped.contains(where: { $0.hasPrefix("mat:") && n.contains($0.dropFirst(4)) }) {
                    pbr.blending = .transparent(opacity: .init(floatLiteral: 0))
                    return pbr
                }
                if n.contains("seat_plastic") || n.contains("seat_band") {
                    pbr.baseColor.tint = seat
                    if inNear {
                        pbr.emissiveColor = .init(color: lift)
                        pbr.emissiveIntensity = Float(B.nearLift)
                    }
                } else if inNear && n.contains("near_deck") {
                    // Treads and risers under the foreground seats sit in the
                    // crowd's shadow; a low self-light keeps them concrete, not void.
                    pbr.emissiveColor = .init(color: StadiumLook.color(B.nearDeckColor))
                    pbr.emissiveIntensity = Float(B.nearDeckLift)
                } else if inNear && (n.contains("plaque") || n.contains("stair") || n.contains("seat_hardware")) {
                    pbr.emissiveColor = .init(color: .init(white: 0.55, alpha: 1))
                    pbr.emissiveIntensity = Float(B.nearLift)
                } else if n.contains("press_room") {
                    pbr.emissiveIntensity = Float(B.pressRoomLift)
                } else if n.contains("bowl_glass") {
                    // USD brings the glass in near-opaque and dark from the far
                    // seats; state its blend here so rooms behind it read lit.
                    pbr.blending = .transparent(opacity: .init(floatLiteral: Float(B.glassOpacity)))
                    pbr.metallic = .init(floatLiteral: 0.15)
                    pbr.roughness = .init(floatLiteral: 0.04)
                } else if n.contains("press_desk") || n.contains("press_chair") || n.contains("press_floor") {
                    // The room's own surfaces, lit by its ceiling strips. They
                    // were one material until the box seat showed what that
                    // costs: desk, chairs and carpet in one beige field, with
                    // nothing standing on anything. Each takes its own share.
                    let share = n.contains("press_desk") ? B.pressDeskLift
                        : n.contains("press_chair") ? B.pressChairLift : B.pressFloorLift
                    pbr.emissiveColor = .init(color: StadiumLook.color("#F0D3AE"))
                    pbr.emissiveIntensity = Float(B.pressRoomLift * share)
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
