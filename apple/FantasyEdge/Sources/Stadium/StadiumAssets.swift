import Foundation
import ImageIO
import RealityKit

/// The stadium's textures, light probe and sound, loaded once per process
/// from the `StadiumAssets` folder the app bundles - `assets/src` unchanged,
/// the same files the web and Android renderers load.
///
/// Loading is asynchronous and happens before the first build, so opening the
/// stadium never stalls a frame on a PNG decode. Anything that fails to load
/// is simply absent: the renderer draws without it rather than not at all.
@MainActor
public final class StadiumAssets {
    public static let shared = StadiumAssets()

    public private(set) var ready = false
    private var loading: Task<Void, Never>?
    private(set) var textures: [String: TextureResource] = [:]
    private(set) var images: [String: CGImage] = [:]
    private(set) var environment: EnvironmentResource?
    private(set) var audio: [String: AudioFileResource] = [:]
    private(set) var bytes = 0

    /// The bundled copy of `assets/src`. Xcode keeps a folder reference's
    /// on-disk name, so it is `src`; a Swift package would call it
    /// `StadiumAssets`. Either is accepted, and it must hold the probe.
    static var folder: URL? {
        for name in ["StadiumAssets", "src"] {
            if let url = Bundle.main.url(forResource: name, withExtension: nil),
               FileManager.default.fileExists(atPath: url.appendingPathComponent("env").path) {
                return url
            }
        }
        return nil
    }

    /// Which texture semantic each asset is, by id in `look.assets`.
    private static let semantics: [String: TextureResource.Semantic] = [
        "turfAlbedo": .color, "turfNormal": .normal, "turfRoughness": .scalar,
        "paint": .color, "glow": .color, "beam": .color, "trail": .color, "haze": .color,
        "lampFace": .color, "seats": .color, "concrete": .color, "sky": .color, "football": .color,
    ]

    public func prepare(_ look: SceneSpec.Look) async {
        if ready { return }
        if let loading { await loading.value; return }
        let task = Task { await self.load(look) }
        loading = task
        await task.value
    }

    private func load(_ look: SceneSpec.Look) async {
        guard let root = Self.folder else {
            StadiumLog.log.error("[stadium] no StadiumAssets folder in the bundle; drawing without textures")
            ready = true
            return
        }
        for (id, rel) in look.assets.sorted(by: { $0.key < $1.key }) {
            let url = root.appendingPathComponent(rel)
            switch url.pathExtension.lowercased() {
            case "png":
                if id == "crowd" {
                    // The crowd atlas is a mask a renderer dresses in club
                    // colours, so it is kept as an image, not a texture.
                    if let img = Self.image(url) { images[id] = img; bytes += img.width * img.height * 4 }
                    continue
                }
                var options = TextureResource.CreateOptions(semantic: Self.semantics[id] ?? .color)
                options.mipmapsMode = .allocateAndGenerateAll
                if let t = try? await TextureResource(contentsOf: url, options: options) {
                    textures[id] = t
                    if let img = Self.image(url) { bytes += img.width * img.height * 4 * 4 / 3 }
                }
            case "hdr", "exr":
                if let img = Self.image(url, float: true),
                   let env = try? await EnvironmentResource(equirectangular: img, withName: id) {
                    environment = env
                    bytes += img.width * img.height * 8
                }
            case "wav", "caf", "m4a":
                let loop = id == "crowdBed"
                if let a = try? await AudioFileResource(contentsOf: url,
                                                        configuration: .init(shouldLoop: loop)) {
                    audio[id] = a
                }
            default:
                continue
            }
        }
        ready = true
        StadiumLog.log.notice("[stadium] assets: \(self.textures.count) textures, \(self.audio.count) sounds, probe \(self.environment == nil ? "missing" : "loaded"), ~\(self.bytes / 1_048_576) MB")
    }

    static func image(_ url: URL, float: Bool = false) -> CGImage? {
        let options = [kCGImageSourceShouldAllowFloat: float] as CFDictionary
        guard let src = CGImageSourceCreateWithURL(url as CFURL, options) else { return nil }
        return CGImageSourceCreateImageAtIndex(src, 0, options)
    }

    func texture(_ id: String) -> TextureResource? { textures[id] }
}
