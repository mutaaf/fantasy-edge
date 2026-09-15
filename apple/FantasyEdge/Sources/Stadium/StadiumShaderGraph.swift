import Foundation
import RealityKit
import UIKit

/// Shader Graph materials authored as text (`tools/shadergraph/`, or an
/// actor's own `.rkassets`), compiled by realitytool into a `.reality` under
/// assets/, and loaded here. See docs/SHADERGRAPH.md.
///
/// Two load paths, tried in order and logged: `ShaderGraphMaterial(named:from:in:)`
/// against the bundle, and, when that finds nothing (it looks for scenes in
/// Reality Composer Pro packages Xcode compiled, not in a loose `.reality`),
/// the compiled `.reality` opened as an entity once per file.
///
/// A file may hold several materials. RealityKit keeps no material name, so a
/// material is found by the mesh bound to it: `/Root/Beam` is the material on
/// the model named `BeamPreview`. A file with exactly one graph material also
/// answers to any prim, so single-material files may keep a mesh named `Preview`.
@MainActor
enum StadiumShaderGraph {
    private static var cache: [String: ShaderGraphMaterial] = [:]
    private static var files: [String: Entity] = [:]
    private(set) static var loadedVia: [String: String] = [:]

    /// A copy of the material at `prim` in `file` (a .reality under the bundled
    /// assets folder, by its path under assets/), or nil if it did not load.
    static func material(_ prim: String, file: String) async -> ShaderGraphMaterial? {
        let key = "\(file)#\(prim)"
        if let hit = cache[key] { return hit }
        let scene = (file as NSString).lastPathComponent
        if let m = try? await ShaderGraphMaterial(named: prim, from: scene, in: .main) {
            cache[key] = m
            loadedVia[key] = "named"
            StadiumLog.log.notice("[shadergraph] \(prim, privacy: .public) loaded by ShaderGraphMaterial(named:from:in:)")
            return m
        }
        guard let entity = await open(file) else { return nil }
        let name = (prim as NSString).lastPathComponent
        var found: [(mesh: String, material: ShaderGraphMaterial)] = []
        collect(entity, into: &found)
        let m: ShaderGraphMaterial
        if let hit = found.first(where: { $0.mesh.split(separator: "/").contains("\(name)Preview") }) {
            m = hit.material
        } else if found.count == 1 {
            m = found[0].material
        } else {
            let meshes = found.map(\.mesh).joined(separator: ", ")
            StadiumLog.log.error("[shadergraph] \(file, privacy: .public) has no mesh \(name, privacy: .public)Preview for \(prim, privacy: .public); graph meshes: \(meshes, privacy: .public)")
            return nil
        }
        cache[key] = m
        loadedVia[key] = "reality"
        StadiumLog.log.notice("[shadergraph] \(prim, privacy: .public) loaded from \(file, privacy: .public) via Entity(contentsOf:)")
        return m
    }

    private static func open(_ file: String) async -> Entity? {
        if let e = files[file] { return e }
        guard let root = StadiumAssets.folder else { return nil }
        do {
            let e = try await Entity(contentsOf: root.appendingPathComponent(file))
            files[file] = e
            return e
        } catch {
            StadiumLog.log.error("[shadergraph] \(file, privacy: .public) failed: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    private static func collect(_ e: Entity, into found: inout [(mesh: String, material: ShaderGraphMaterial)]) {
        if let model = e.components[ModelComponent.self],
           let m = model.materials.compactMap({ $0 as? ShaderGraphMaterial }).first {
            // The mesh prim's name may be on the model or on the entity above it.
            found.append(([e.parent?.name ?? "", e.name].joined(separator: "/"), m))
        }
        for child in e.children { collect(child, into: &found) }
    }

    /// Set a parameter from a token value: a "#RRGGBB" string becomes a
    /// colour, a number a float. Anything else is ignored and logged.
    static func set(_ material: inout ShaderGraphMaterial, _ name: String, _ value: Any) {
        do {
            switch value {
            case let hex as String:
                let c = SceneMath.rgba(hex)
                try material.setParameter(name: name, value: .color(UIColor(red: CGFloat(c.x), green: CGFloat(c.y),
                                                                             blue: CGFloat(c.z), alpha: 1).cgColor))
            case let n as Double:
                try material.setParameter(name: name, value: .float(Float(n)))
            case let n as Int:
                try material.setParameter(name: name, value: .float(Float(n)))
            default:
                StadiumLog.log.error("[shadergraph] parameter \(name, privacy: .public) has an unusable value")
            }
        } catch {
            StadiumLog.log.error("[shadergraph] setParameter \(name, privacy: .public): \(error.localizedDescription, privacy: .public)")
        }
    }
}
