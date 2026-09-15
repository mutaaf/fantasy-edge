import Foundation
import ImageIO
import RealityKit

/// The stadium's textures, light probe and sound, loaded once per process
/// from the bundled copy of `assets/` - one folder per actor, the same files
/// the web and Android renderers load.
///
/// Every asset is addressed as `<actor>.<id>`, from that actor's section of
/// `look`, so two actors can each have a `glow` without colliding. Loading is
/// asynchronous and happens before the first build, so opening the stadium
/// never stalls a frame on a PNG decode. Anything that fails to load is simply
/// absent: the actor draws without it rather than not at all.
@MainActor
public final class StadiumAssets {
    public static let shared = StadiumAssets()

    public private(set) var ready = false
    private var loading: Task<Void, Never>?
    private(set) var textures: [String: TextureResource] = [:]
    private(set) var images: [String: CGImage] = [:]
    private(set) var environment: EnvironmentResource?
    private(set) var audio: [String: AudioFileResource] = [:]
    private(set) var models: [String: Entity] = [:]
    private(set) var bytes = 0

    /// The bundled `assets/` folder. Xcode keeps a folder reference's on-disk
    /// name; a Swift package would call it `StadiumAssets`. It must hold `actors`.
    static var folder: URL? {
        for name in ["assets", "StadiumAssets"] {
            if let url = Bundle.main.url(forResource: name, withExtension: nil),
               FileManager.default.fileExists(atPath: url.appendingPathComponent("generated").path)
                || FileManager.default.fileExists(atPath: url.appendingPathComponent("actors").path) {
                return url
            }
        }
        return nil
    }

    /// Texture semantics by the file's role; anything unnamed is colour.
    private static func semantic(_ id: String) -> TextureResource.Semantic {
        if id.hasSuffix("Normal") { return .normal }
        if id.hasSuffix("Roughness") { return .scalar }
        return .color
    }

    /// Mask images an actor composes itself rather than sampling directly.
    private static let imagesOnly: Set<String> = ["crowd.crowd"]

    public func prepare(_ look: SceneSpec.Look) async {
        if ready { return }
        if let loading { await loading.value; return }
        let task = Task { await self.load(look) }
        loading = task
        await task.value
    }

    private func load(_ look: SceneSpec.Look) async {
        guard let root = Self.folder else {
            StadiumLog.log.error("[stadium] no assets folder in the bundle; drawing without textures")
            ready = true
            return
        }
        var byPath: [String: TextureResource] = [:]
        for (actor, section) in look.assetSections {
            for (id, rel) in section.sorted(by: { $0.key < $1.key }) {
                let key = "\(actor).\(id)"
                let url = root.appendingPathComponent(rel)
                switch url.pathExtension.lowercased() {
                case "png":
                    if Self.imagesOnly.contains(key) {
                        if let img = Self.image(url) { images[key] = img; bytes += img.width * img.height * 4 }
                        continue
                    }
                    // Two actors may name one file; it is loaded once.
                    if let shared = byPath[rel] {
                        textures[key] = shared
                        continue
                    }
                    var options = TextureResource.CreateOptions(semantic: Self.semantic(id))
                    options.mipmapsMode = .allocateAndGenerateAll
                    if let t = try? await TextureResource(contentsOf: url, options: options) {
                        textures[key] = t
                        byPath[rel] = t
                        if let img = Self.image(url) { bytes += img.width * img.height * 16 / 3 }
                    }
                case "hdr", "exr":
                    if let img = Self.image(url, float: true),
                       let env = try? await EnvironmentResource(equirectangular: img, withName: key) {
                        environment = env
                        bytes += img.width * img.height * 8
                    }
                case "wav", "caf", "m4a":
                    let loop = id.hasSuffix("Bed")
                    if let a = try? await AudioFileResource(contentsOf: url, configuration: .init(shouldLoop: loop)) {
                        audio[key] = a
                    }
                default:
                    continue
                }
            }
        }
        // Models: a specialist's `.usdz` (exported from Blender beside its
        // `.glb`), loaded once as a template that actors clone.
        for (actor, section) in look.modelSections {
            for (id, rel) in section.sorted(by: { $0.key < $1.key }) {
                let url = root.appendingPathComponent(rel)
                guard ["usdz", "usda", "usdc", "reality"].contains(url.pathExtension.lowercased()) else { continue }
                do {
                    models["\(actor).\(id)"] = try await Entity(contentsOf: url)
                } catch {
                    StadiumLog.log.error("[stadium] model \(actor).\(id) failed to load from \(rel): \(error.localizedDescription)")
                }
            }
        }
        ready = true
        StadiumLog.log.notice("[stadium] models: \(self.models.count)")
        StadiumLog.log.notice("[stadium] assets: \(self.textures.count) textures, \(self.audio.count) sounds, probe \(self.environment == nil ? "missing" : "loaded"), ~\(self.bytes / 1_048_576) MB")
    }

    static func image(_ url: URL, float: Bool = false) -> CGImage? {
        let options = [kCGImageSourceShouldAllowFloat: float] as CFDictionary
        guard let src = CGImageSourceCreateWithURL(url as CFURL, options) else { return nil }
        return CGImageSourceCreateImageAtIndex(src, 0, options)
    }

    /// A texture by `<actor>.<id>`.
    func texture(_ key: String) -> TextureResource? { textures[key] }

    /// A fresh copy of a model by `<actor>.<id>`, or nil if none was declared or it failed.
    func model(_ key: String) -> Entity? { models[key]?.clone(recursive: true) }
}
