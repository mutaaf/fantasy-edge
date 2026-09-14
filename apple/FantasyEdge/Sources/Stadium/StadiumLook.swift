import Metal
import RealityKit
import UIKit

/// The stadium's materials: lit turf and paint, concrete and metal, and the
/// things that are light itself - lamps, glows, beams, trails - which blend
/// additively so they brighten what is behind them the way light does.
///
/// Every colour comes from the scene's palette or `look`; nothing here picks
/// one of its own.
@MainActor
enum StadiumLook {
    private static var additive: UnlitMaterial.Program?

    /// The additive program is built asynchronously, once, before anything
    /// that glows is made. Without it a glow falls back to alpha blending.
    static func prepare() async {
        guard additive == nil else { return }
        var d = UnlitMaterial.Program.Descriptor()
        d.blendMode = .add
        additive = await UnlitMaterial.Program(descriptor: d)
    }

    // MARK: colour

    nonisolated static func color(_ hex: String, scale: Double = 1) -> UIColor {
        let c = SceneMath.rgba(hex)
        let k = CGFloat(scale)
        return UIColor(red: CGFloat(c.x) * k, green: CGFloat(c.y) * k, blue: CGFloat(c.z) * k, alpha: 1)
    }

    static func repeating(_ texture: TextureResource) -> MaterialParameters.Texture {
        let d = MTLSamplerDescriptor()
        d.sAddressMode = .repeat
        d.tAddressMode = .repeat
        d.minFilter = .linear
        d.magFilter = .linear
        d.mipFilter = .linear
        d.maxAnisotropy = 8
        return MaterialParameters.Texture(texture, sampler: .init(d))
    }

    static func clamped(_ texture: TextureResource) -> MaterialParameters.Texture {
        let d = MTLSamplerDescriptor()
        d.sAddressMode = .clampToEdge
        d.tAddressMode = .clampToEdge
        d.minFilter = .linear
        d.magFilter = .linear
        d.mipFilter = .linear
        return MaterialParameters.Texture(texture, sampler: .init(d))
    }

    // MARK: lit surfaces

    static func turf(tint: String, roughness: Double, look: SceneSpec.Look, assets: StadiumAssets) -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        if let albedo = assets.texture("turfAlbedo") {
            m.baseColor = .init(tint: color(tint), texture: repeating(albedo))
        } else {
            m.baseColor = .init(tint: color("#2F5A2A"))
        }
        if let r = assets.texture("turfRoughness") {
            m.roughness = .init(scale: Float(roughness), texture: repeating(r))
        } else {
            m.roughness = .init(floatLiteral: Float(roughness))
        }
        if let n = assets.texture("turfNormal") {
            m.normal = .init(texture: repeating(n))
        }
        m.metallic = .init(floatLiteral: 0)
        m.specular = .init(floatLiteral: 0.25)
        return m
    }

    /// Paint on grass: a colour, worn by the paint mask so blades show through.
    static func paint(_ hex: String, opacity: Double, roughness: Double, assets: StadiumAssets) -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        m.baseColor = .init(tint: color(hex))
        m.roughness = .init(floatLiteral: Float(roughness))
        m.metallic = .init(floatLiteral: 0)
        if let mask = assets.texture("paint") {
            m.blending = .transparent(opacity: .init(scale: Float(opacity), texture: repeating(mask)))
        } else {
            m.blending = .transparent(opacity: .init(floatLiteral: Float(opacity)))
        }
        return m
    }

    static func solid(_ hex: String, roughness: Double = 0.7, metallic: Double = 0,
                      texture: TextureResource? = nil, tile: Bool = true, cull: Bool = true) -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        if let texture {
            m.baseColor = .init(tint: color(hex), texture: tile ? repeating(texture) : clamped(texture))
        } else {
            m.baseColor = .init(tint: color(hex))
        }
        m.roughness = .init(floatLiteral: Float(roughness))
        m.metallic = .init(floatLiteral: Float(metallic))
        if !cull { m.faceCulling = .none }
        return m
    }

    // MARK: light

    /// Something that emits: a lamp face, a ribbon board, a press box window.
    static func emissive(_ hex: String, scale: Double = 1, texture: TextureResource? = nil,
                         tile: Bool = true) -> UnlitMaterial {
        var m = UnlitMaterial(applyPostProcessToneMap: false)
        if let texture {
            m.color = .init(tint: color(hex, scale: scale), texture: tile ? repeating(texture) : clamped(texture))
        } else {
            m.color = .init(tint: color(hex, scale: scale))
        }
        return m
    }

    /// Light in the air: a bloom, a beam, a trail, a haze cone. Additive, so
    /// its brightness is `scale` times the texture's alpha-weighted colour and
    /// it never writes depth - a glow must not hide what is behind it.
    static func glow(_ hex: String, opacity: Double, texture: TextureResource?, tile: Bool = false) -> UnlitMaterial {
        var m: UnlitMaterial
        if let additive {
            m = UnlitMaterial(program: additive)
        } else {
            m = UnlitMaterial(applyPostProcessToneMap: false)
        }
        let tint = color(hex, scale: opacity)
        if let texture {
            let t = tile ? repeating(texture) : clamped(texture)
            m.color = .init(tint: tint, texture: t)
            m.blending = .transparent(opacity: .init(scale: 1, texture: t))
        } else {
            m.color = .init(tint: tint)
            m.blending = .transparent(opacity: .init(floatLiteral: Float(min(1, opacity))))
        }
        m.writesDepth = false
        m.faceCulling = .none
        return m
    }

    /// Fans on their cards: cut out at the atlas's alpha, so they write depth
    /// and sort like the solid things they stand among.
    static func crowd(_ texture: TextureResource, tint: Double) -> UnlitMaterial {
        var m = UnlitMaterial(applyPostProcessToneMap: true)
        m.color = .init(tint: UIColor(white: CGFloat(tint), alpha: 1), texture: clamped(texture))
        m.opacityThreshold = 0.5
        // Culled: each fan is a front card and a back card, and only the one
        // facing the eye should draw.
        m.faceCulling = .back
        return m
    }

    /// Turf, then paint, then broadcast lines: drawn in that order where they
    /// overlap, so a painted line never flickers through the grass it is on.
    static let groundSort = ModelSortGroup(depthPass: nil)
    static func ground(_ e: Entity, order: Int32) {
        e.components.set(ModelSortGroupComponent(group: groundSort, order: order))
    }
}
