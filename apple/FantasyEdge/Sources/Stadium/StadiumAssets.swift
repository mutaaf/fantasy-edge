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

    /// Textures that are only ever magnified, so a mip chain would be a third
    /// more memory no sampler reads. The cloud veil wraps 2048 texels round
    /// 360 degrees, about 6 a degree, and is empty above 69 degrees of
    /// elevation, where the equirect's rows pinch it to at most 16 a degree:
    /// still under what the display resolves. The star map is not on this
    /// list: above about 83 degrees its rows pinch past the display, and a
    /// star without mips there would shimmer as the head moves.
    private static let magnifiedOnly: Set<String> = ["sky.clouds"]

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
        let start = ContinuousClock.now
        // Every file is started at once and awaited together. The loaders are
        // main-actor entry points that decode off the main thread, so run one
        // after another they left the stadium waiting on 47 models in series
        // (6.2 of 7.5 s in the simulator at integration-11); started together
        // they share the decoders. Results land in the dictionaries on the
        // main actor as each finishes, and `ready` waits for all of them.
        var jobs: [Task<Void, Never>] = []
        var byPath: [String: [String]] = [:]
        for (actor, section) in look.assetSections {
            for (id, rel) in section.sorted(by: { $0.key < $1.key }) {
                let key = "\(actor).\(id)"
                let url = root.appendingPathComponent(rel)
                switch url.pathExtension.lowercased() {
                case "png":
                    if Self.imagesOnly.contains(key) {
                        jobs.append(Task { @MainActor in
                            let img = await Task.detached(priority: .userInitiated) { Self.image(url) }.value
                            if let img { self.images[key] = img; self.bytes += img.width * img.height * 4 }
                        })
                        continue
                    }
                    // Two actors may name one file; it is loaded once.
                    if byPath[rel] != nil {
                        byPath[rel]?.append(key)
                        continue
                    }
                    byPath[rel] = [key]
                    let semantic = Self.semantic(id)
                    let mips = !Self.magnifiedOnly.contains(key)
                    jobs.append(Task { @MainActor in
                        let one = ContinuousClock.now
                        var options = TextureResource.CreateOptions(semantic: semantic)
                        options.mipmapsMode = mips ? .allocateAndGenerateAll : .none
                        if let t = try? await TextureResource(contentsOf: url, options: options) {
                            self.textures[key] = t
                            // The header, not a second decode of the image, gives the size.
                            if let size = Self.pixelSize(url) { self.bytes += size.width * size.height * (mips ? 16 : 12) / 3 }
                        }
                        StadiumTiming.log("asset \(key)", since: one)
                    })
                case "hdr", "exr":
                    jobs.append(Task { @MainActor in
                        let one = ContinuousClock.now
                        let img = await Task.detached(priority: .userInitiated) { Self.image(url, float: true) }.value
                        if let img, let env = try? await EnvironmentResource(equirectangular: img, withName: key) {
                            self.environment = env
                            self.bytes += img.width * img.height * 8
                        }
                        StadiumTiming.log("asset \(key)", since: one)
                    })
                case "wav", "caf", "m4a":
                    let loop = id.hasSuffix("Bed")
                    jobs.append(Task { @MainActor in
                        if let a = try? await AudioFileResource(contentsOf: url, configuration: .init(shouldLoop: loop)) {
                            self.audio[key] = a
                        }
                    })
                default:
                    continue
                }
            }
        }
        // Models: a specialist's `.usdz` (exported from Blender beside its
        // `.glb`), loaded once as a template that actors clone.
        var modelJobs: [Task<Void, Never>] = []
        for (actor, section) in look.modelSections {
            for (id, rel) in section.sorted(by: { $0.key < $1.key }) {
                let url = root.appendingPathComponent(rel)
                guard ["usdz", "usda", "usdc", "reality"].contains(url.pathExtension.lowercased()) else { continue }
                modelJobs.append(Task { @MainActor in
                    let one = ContinuousClock.now
                    do {
                        self.models["\(actor).\(id)"] = try await Entity(contentsOf: url)
                    } catch {
                        StadiumLog.log.error("[stadium] model \(actor).\(id) failed to load from \(rel): \(error.localizedDescription)")
                    }
                    StadiumTiming.log("model \(actor).\(id)", since: one)
                })
            }
        }
        for job in jobs { await job.value }
        for keys in byPath.values where keys.count > 1 {
            if let t = textures[keys[0]] { for k in keys.dropFirst() { textures[k] = t } }
        }
        StadiumTiming.log("assets textures, probe and sound", since: start)
        let modelsStart = start
        for job in modelJobs { await job.value }
        StadiumTiming.log("assets models", since: modelsStart)
        StadiumTiming.log("assets total", since: start)
        ready = true
        StadiumLog.log.notice("[stadium] models: \(self.models.count)")
        StadiumLog.log.notice("[stadium] assets: \(self.textures.count) textures, \(self.audio.count) sounds, probe \(self.environment == nil ? "missing" : "loaded"), ~\(self.bytes / 1_048_576) MB")
    }

    nonisolated static func image(_ url: URL, float: Bool = false) -> CGImage? {
        let options = [kCGImageSourceShouldAllowFloat: float] as CFDictionary
        guard let src = CGImageSourceCreateWithURL(url as CFURL, options) else { return nil }
        return CGImageSourceCreateImageAtIndex(src, 0, options)
    }

    /// Width and height from the file's header, without decoding its pixels.
    nonisolated static func pixelSize(_ url: URL) -> (width: Int, height: Int)? {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
              let w = props[kCGImagePropertyPixelWidth] as? Int, let h = props[kCGImagePropertyPixelHeight] as? Int else { return nil }
        return (w, h)
    }

    /// A texture by `<actor>.<id>`.
    func texture(_ key: String) -> TextureResource? { textures[key] }

    /// A fresh copy of a model by `<actor>.<id>`, or nil if none was declared or it failed.
    func model(_ key: String) -> Entity? { models[key]?.clone(recursive: true) }
}
