import Foundation
import RealityKit
import UIKit

/// Shader Graph materials authored as text in `tools/shadergraph/`, compiled
/// by `tools/shadergraph/build.py` into `assets/generated/shadergraph/`, and
/// loaded here once. See docs/SHADERGRAPH.md.
///
/// Two load paths, tried in order and logged: `ShaderGraphMaterial(named:from:in:)`
/// against the bundle, and, when that finds nothing (it looks for scenes in
/// Reality Composer Pro packages Xcode compiled, not in a loose `.reality`),
/// the compiled `.reality` opened as an entity and the material read off the
/// preview mesh bound to it.
@MainActor
enum StadiumShaderGraph {
    private static var cache: [String: ShaderGraphMaterial] = [:]
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
        guard let root = StadiumAssets.folder else { return nil }
        let url = root.appendingPathComponent(file)
        do {
            let entity = try await Entity(contentsOf: url)
            guard let m = findMaterial(entity) else {
                StadiumLog.log.error("[shadergraph] \(file, privacy: .public) has no ShaderGraphMaterial on any model")
                return nil
            }
            cache[key] = m
            loadedVia[key] = "reality"
            StadiumLog.log.notice("[shadergraph] \(prim, privacy: .public) loaded from \(file, privacy: .public) via Entity(contentsOf:)")
            return m
        } catch {
            StadiumLog.log.error("[shadergraph] \(file, privacy: .public) failed: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    private static func findMaterial(_ e: Entity) -> ShaderGraphMaterial? {
        if let model = e.components[ModelComponent.self],
           let m = model.materials.compactMap({ $0 as? ShaderGraphMaterial }).first {
            return m
        }
        for child in e.children {
            if let m = findMaterial(child) { return m }
        }
        return nil
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
