import CoreGraphics
import Foundation
import RealityKit
import UIKit

/// The rotunda, generated rather than stored.
///
/// Nothing in this app is a checked-in binary - the app icon is drawn by
/// `tools/make_icon.py` and this is the same rule applied to a room. There is
/// no `.usdz`, no `.reality`, no `.hdr` and no texture file anywhere in the
/// repository: every surface below is a `MeshDescriptor` built from arithmetic
/// and a `PhysicallyBasedMaterial` built in code, and the only imagery is the
/// player headshots the ESPN API already serves.
///
/// ## Why a mesh is built here and not in the view
///
/// Every mesh in here is generated once and shared by every entity that wants
/// it. Ten plinths are ten `ModelEntity`s pointing at *one* cylinder; ten
/// busts are ten pointing at one solid of revolution. A headset re-renders
/// this ninety times a second per eye, and the difference between one mesh
/// referenced ten times and ten identical meshes is ten times the vertex
/// upload for a room that looks the same. `Hall.Room` holds them in a struct
/// built at scene set-up so nothing in this file is ever called from a
/// `RealityView`'s `update:`.
///
/// ## Winding
///
/// The wearer stands *inside* almost everything here, so the wall, the band
/// and the dome are wound so their normals point at the middle of the room.
/// Getting that backwards does not error - it renders an invisible room with
/// correct lighting on the outside, which is exactly what the first attempt
/// did.
enum HallMesh {

    // MARK: - flat rings and shells

    /// A flat ring lying in the XZ plane. The floor inlay, the cornice over
    /// the arcade and the collar round the oculus are all this.
    static func annulus(inner: Float, outer: Float, segments: Int = 96,
                        facingUp: Bool = true) -> MeshResource {
        var pos: [SIMD3<Float>] = []
        var nrm: [SIMD3<Float>] = []
        var uv: [SIMD2<Float>] = []
        var idx: [UInt32] = []
        let n: SIMD3<Float> = facingUp ? [0, 1, 0] : [0, -1, 0]
        for i in 0...segments {
            let t = Float(i) / Float(segments) * 2 * .pi
            let c = cos(t), s = sin(t)
            pos.append([c * inner, 0, s * inner])
            pos.append([c * outer, 0, s * outer])
            nrm.append(n); nrm.append(n)
            uv.append([Float(i) / Float(segments), 0])
            uv.append([Float(i) / Float(segments), 1])
        }
        for i in 0..<segments {
            let a = UInt32(i * 2), b = a + 1, c = a + 2, d = a + 3
            if facingUp { idx += [a, c, b, b, c, d] } else { idx += [a, b, c, b, d, c] }
        }
        return build(pos, nrm, uv, idx, "annulus")
    }

    /// An open cylinder - a wall with no top and no bottom.
    static func shell(radius: Float, height: Float, segments: Int = 96,
                      inward: Bool = true) -> MeshResource {
        var pos: [SIMD3<Float>] = []
        var nrm: [SIMD3<Float>] = []
        var uv: [SIMD2<Float>] = []
        var idx: [UInt32] = []
        for i in 0...segments {
            let f = Float(i) / Float(segments)
            let t = f * 2 * .pi
            let c = cos(t), s = sin(t)
            let n: SIMD3<Float> = inward ? [-c, 0, -s] : [c, 0, s]
            pos.append([c * radius, 0, s * radius])
            pos.append([c * radius, height, s * radius])
            nrm.append(n); nrm.append(n)
            uv.append([f, 1]); uv.append([f, 0])
        }
        for i in 0..<segments {
            let a = UInt32(i * 2), b = a + 1, c = a + 2, d = a + 3
            if inward { idx += [a, b, c, b, d, c] } else { idx += [a, c, b, b, c, d] }
        }
        return build(pos, nrm, uv, idx, "shell")
    }

    /// A hemisphere seen from inside, with a hole cut in the top.
    ///
    /// The hole is the point: an unbroken dome is a lid and reads as a
    /// basement ceiling. An oculus gives the room a source for its light and
    /// somewhere for the eye to go, and it costs two rings of triangles.
    static func dome(radius: Float, oculus: Float = 0.16,
                     rings: Int = 18, segments: Int = 64) -> MeshResource {
        var pos: [SIMD3<Float>] = []
        var nrm: [SIMD3<Float>] = []
        var uv: [SIMD2<Float>] = []
        var idx: [UInt32] = []
        // Latitude runs from the springing line up to just short of the pole.
        let top = (.pi / 2) * (1 - oculus)
        for r in 0...rings {
            let lat = Float(r) / Float(rings) * top
            let y = sin(lat) * radius, rad = cos(lat) * radius
            for s in 0...segments {
                let f = Float(s) / Float(segments)
                let t = f * 2 * .pi
                let p = SIMD3<Float>(cos(t) * rad, y, sin(t) * rad)
                pos.append(p)
                nrm.append(-normalize(p))
                uv.append([f, Float(r) / Float(rings)])
            }
        }
        let stride = UInt32(segments + 1)
        for r in 0..<rings {
            for s in 0..<segments {
                let a = UInt32(r) * stride + UInt32(s)
                let b = a + 1, c = a + stride, d = c + 1
                idx += [a, c, b, b, c, d]
            }
        }
        return build(pos, nrm, uv, idx, "dome")
    }

    // MARK: - the bust

    /// A solid of revolution from a half-profile in the XY plane.
    ///
    /// This is how the bust exists at all without a stored model. The profile
    /// is a silhouette read left to right as (radius, height); spinning it
    /// gives head, neck and shoulders as one closed bronze form, and the
    /// player's own portrait is then cast onto the front of it by `cameo`.
    /// Sculpting a likeness procedurally is not possible and pretending
    /// otherwise would put ten identical strangers in the room; a bronze
    /// armature carrying the man's real photograph is the honest version of
    /// the same idea.
    static func lathe(_ profile: [SIMD2<Float>], segments: Int = 40) -> MeshResource {
        var pos: [SIMD3<Float>] = []
        var nrm: [SIMD3<Float>] = []
        var uv: [SIMD2<Float>] = []
        var idx: [UInt32] = []
        // Profile-space normal: perpendicular to the tangent, pointing out.
        var pn: [SIMD2<Float>] = []
        for i in profile.indices {
            let a = profile[max(i - 1, 0)]
            let b = profile[min(i + 1, profile.count - 1)]
            let t = b - a
            let n = SIMD2<Float>(t.y, -t.x)
            pn.append(length(n) > 1e-6 ? normalize(n) : SIMD2<Float>(1, 0))
        }
        for (i, p) in profile.enumerated() {
            for s in 0...segments {
                let f = Float(s) / Float(segments)
                let t = f * 2 * .pi
                let c = cos(t), sn = sin(t)
                pos.append([p.x * c, p.y, p.x * sn])
                nrm.append(normalize(SIMD3(pn[i].x * c, pn[i].y, pn[i].x * sn)))
                uv.append([f, Float(i) / Float(profile.count - 1)])
            }
        }
        let stride = UInt32(segments + 1)
        for r in 0..<(profile.count - 1) {
            for s in 0..<segments {
                let a = UInt32(r) * stride + UInt32(s)
                let b = a + 1, c = a + stride, d = c + 1
                idx += [a, c, b, b, c, d]
            }
        }
        return build(pos, nrm, uv, idx, "lathe")
    }

    /// The half-profile of a bust: shoulders, neck, head, crown.
    ///
    /// Read as (radius from the spine, height off the plinth). Deliberately
    /// coarse - it is an armature seen edge-on, and every extra ring is ten
    /// more of them in the room.
    static let bustProfile: [SIMD2<Float>] = [
        [0.000, 0.000], [0.180, 0.000], [0.190, 0.030], [0.176, 0.100],
        [0.132, 0.165], [0.086, 0.212], [0.072, 0.252], [0.088, 0.296],
        [0.112, 0.346], [0.118, 0.404], [0.104, 0.456], [0.068, 0.494],
        [0.026, 0.514], [0.000, 0.518],
    ]

    /// The portrait, cast onto the front of the bust.
    ///
    /// A grid rather than a quad because it is bowed forward: a flat photo
    /// standing on a plinth is a cardboard cut-out and looks like one the
    /// moment the wearer steps sideways. The bow gives the bronze a curved
    /// surface for the environment to run across, which is most of what makes
    /// a metal read as metal at all.
    static func cameo(width: Float, height: Float, bulge: Float,
                      cols: Int = 18, rows: Int = 14) -> MeshResource {
        var pos: [SIMD3<Float>] = []
        var nrm: [SIMD3<Float>] = []
        var uv: [SIMD2<Float>] = []
        var idx: [UInt32] = []
        for r in 0...rows {
            let v = Float(r) / Float(rows)
            for c in 0...cols {
                let u = Float(c) / Float(cols)
                let x = (u - 0.5) * width
                let y = (0.5 - v) * height
                // An elliptical dome over the panel, so the edges stay in the
                // plane and only the middle comes forward.
                let e = max(0, 1 - pow((u - 0.5) * 2, 2) - pow((v - 0.5) * 2, 2))
                let z = bulge * sqrt(e)
                pos.append([x, y, z])
                nrm.append(normalize(SIMD3(x * 0.35, y * 0.35, max(bulge, 0.02) * 3)))
                // `1 - v`, and it is not a preference. A `CGImage` has its
                // origin at the top left and RealityKit samples from the
                // bottom, so a portrait mapped with the obvious `v` arrives
                // upside down - which is exactly how the first render of this
                // room came out, ten men standing on their heads.
                uv.append([u, 1 - v])
            }
        }
        let stride = UInt32(cols + 1)
        for r in 0..<rows {
            for c in 0..<cols {
                let a = UInt32(r) * stride + UInt32(c)
                let b = a + 1, cc = a + stride, d = cc + 1
                idx += [a, cc, b, b, cc, d]
            }
        }
        return build(pos, nrm, uv, idx, "cameo")
    }

    /// The face of an arcade arch: a half-ring standing upright, with the
    /// soffit that carries it back into the bay.
    static func arch(span: Float, thickness: Float, depth: Float,
                     segments: Int = 24) -> MeshResource {
        var pos: [SIMD3<Float>] = []
        var nrm: [SIMD3<Float>] = []
        var uv: [SIMD2<Float>] = []
        var idx: [UInt32] = []
        let r0 = span / 2, r1 = r0 + thickness
        // The flat face, in the XY plane at z = 0.
        for i in 0...segments {
            let f = Float(i) / Float(segments)
            let t = f * .pi
            let c = cos(t), s = sin(t)
            pos.append([-c * r0, s * r0, 0]); pos.append([-c * r1, s * r1, 0])
            nrm.append([0, 0, 1]); nrm.append([0, 0, 1])
            uv.append([f, 0]); uv.append([f, 1])
        }
        for i in 0..<segments {
            let a = UInt32(i * 2), b = a + 1, c = a + 2, d = a + 3
            idx += [a, c, b, b, c, d]
        }
        // The soffit: the underside of the arch, seen when you look up into
        // the bay. Without it the arch is a sticker and the bay has no depth.
        let base = UInt32(pos.count)
        for i in 0...segments {
            let f = Float(i) / Float(segments)
            let t = f * .pi
            let c = cos(t), s = sin(t)
            let n = SIMD3<Float>(c, -s, 0)
            pos.append([-c * r0, s * r0, 0]); pos.append([-c * r0, s * r0, -depth])
            nrm.append(n); nrm.append(n)
            uv.append([f, 0]); uv.append([f, 1])
        }
        for i in 0..<segments {
            let a = base + UInt32(i * 2), b = a + 1, c = a + 2, d = a + 3
            idx += [a, b, c, b, d, c]
        }
        return build(pos, nrm, uv, idx, "arch")
    }

    private static func build(_ pos: [SIMD3<Float>], _ nrm: [SIMD3<Float>],
                              _ uv: [SIMD2<Float>], _ idx: [UInt32],
                              _ name: String) -> MeshResource {
        var d = MeshDescriptor(name: name)
        d.positions = MeshBuffers.Positions(pos)
        d.normals = MeshBuffers.Normals(nrm)
        d.textureCoordinates = MeshBuffers.TextureCoordinates(uv)
        d.primitives = .triangles(idx)
        // A generate that throws here is a bug in the arithmetic above, not a
        // runtime condition - an empty box makes it obvious which mesh, rather
        // than taking the whole space down on launch.
        return (try? MeshResource.generate(from: [d]))
            ?? MeshResource.generateBox(size: 0.05)
    }
}


/// Every material in the hall, built once.
///
/// Bronze and stone are the whole palette. They are `PhysicallyBasedMaterial`
/// rather than `SimpleMaterial` because the difference between the two here is
/// the difference between a brown room and a metal one: bronze is metallic 1.0
/// with a low roughness, which means it has no diffuse colour of its own at
/// all and every bit of what you see on it is a reflection of
/// `HallLight.environment`. Take the image-based light away and the busts go
/// black.
enum HallMaterial {

    static func stone(_ shade: CGFloat = 0.30, rough: Float = 0.72) -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        m.baseColor = .init(tint: UIColor(hue: 0.09, saturation: 0.07,
                                          brightness: shade, alpha: 1))
        m.metallic = 0.0
        m.roughness = .init(floatLiteral: rough)
        return m
    }

    static var bronze: PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        m.baseColor = .init(tint: UIColor(red: 0.58, green: 0.36, blue: 0.14, alpha: 1))
        m.metallic = 1.0
        m.roughness = 0.32
        return m
    }

    /// The darker, greener bronze of something that has been in a room a long
    /// time. Used on the busts so they separate from the polished rails.
    static var patina: PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        m.baseColor = .init(tint: UIColor(red: 0.50, green: 0.35, blue: 0.19, alpha: 1))
        m.metallic = 0.85
        m.roughness = 0.44
        m.emissiveColor = .init(color: UIColor(red: 0.34, green: 0.22, blue: 0.10, alpha: 1))
        m.emissiveIntensity = 0.14
        return m
    }

    /// The lit back of an alcove. Emissive rather than a real light: ten
    /// `SpotLight`s is ten shadow-casting lights in a scene that has to hold
    /// ninety frames a second per eye, and an emissive panel behind the bust
    /// buys the same read - a bright wall the bronze is silhouetted against -
    /// for the cost of a shader constant.
    static func glow(_ intensity: Float = 0.30) -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        m.baseColor = .init(tint: UIColor(red: 0.10, green: 0.07, blue: 0.05, alpha: 1))
        m.roughness = 0.9
        m.metallic = 0.0
        m.emissiveColor = .init(color: UIColor(red: 1.0, green: 0.66, blue: 0.32, alpha: 1))
        // Low, and measured off a capture rather than picked. At 1.5 the panel
        // clipped to flat cream and every alcove read as a lightbox with a
        // silhouette in front of it - the bust lost its own modelling to the
        // wall behind it. A lit niche wants to be a little brighter than the
        // stone, not eight times brighter.
        m.emissiveIntensity = intensity
        return m
    }

    /// The bronze itself, applied to a photograph.
    ///
    /// Hue and saturation come from the metal and luminance from the picture,
    /// which is what a duotone is and what a casting looks like. Done here in
    /// Core Graphics rather than in the material because RealityKit's PBR has
    /// no desaturation term: a `baseColor` tint multiplies, so a red jersey
    /// stays red and only gets darker.
    ///
    /// The two blend passes are both load-bearing. `.color` composites across
    /// the whole rectangle including the transparent surround, so it fills the
    /// cut-out's background with solid bronze; `.destinationIn` then re-draws
    /// the original purely for its alpha and punches the man back out of it.
    /// Drop the second pass and every bust becomes a bronze rectangle.
    static func duotone(_ src: CGImage) -> CGImage? {
        let r = CGRect(x: 0, y: 0, width: src.width, height: src.height)
        guard let ctx = CGContext(
            data: nil, width: src.width, height: src.height,
            bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return nil }
        ctx.draw(src, in: r)
        ctx.setBlendMode(.color)
        ctx.setFillColor(UIColor(red: 0.74, green: 0.47, blue: 0.17, alpha: 1).cgColor)
        ctx.fill(r)
        ctx.setBlendMode(.destinationIn)
        ctx.draw(src, in: r)
        return ctx.makeImage()
    }

    /// A man's portrait, cast in bronze.
    ///
    /// The ESPN cut-out carries an alpha channel, which is what makes this
    /// work: `opacityThreshold` turns that channel into a stencil, so the
    /// bronze takes the shape of the player rather than of a rectangle with a
    /// photo in it. Without the threshold the same texture renders as a
    /// tea-tray on a stick.
    static func cast(_ texture: TextureResource) -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        // Near-white, because the bronze is already in the texture - see
        // `duotone`. Tinting a full-colour photograph brown instead just
        // produces a brown photograph: the first render of this room had ten
        // colour headshots standing on stone plinths, which reads as a
        // cardboard cut-out rather than as a casting.
        m.baseColor = .init(tint: UIColor(red: 1.0, green: 0.94, blue: 0.86, alpha: 1),
                            texture: .init(texture))
        m.metallic = 0.74
        m.roughness = 0.34
        // A gallery spotlight, in the one place a real light would be aimed.
        // RealityKit has no global illumination, so the emissive panel behind
        // a bust lights nothing but itself, and a purely metallic face lit
        // only by a painted sky renders too dark to recognise - measured off a
        // capture, the faces came out around a fifth of the plinth's
        // brightness. Driving emission from the portrait's own texture keeps
        // the modelling instead of flattening it the way a flat ambient lift
        // would.
        // Warm and small. Driven with a white tint at 0.42 - the first thing
        // tried - the lift ran the portraits to pale blue-white ghosts, which
        // is worse than the dark they were rescuing. Bronze times bronze, at a
        // sixth of the strength, keeps the metal a metal.
        m.emissiveColor = .init(color: UIColor(red: 0.92, green: 0.63,
                                               blue: 0.30, alpha: 1),
                                texture: .init(texture))
        m.emissiveIntensity = 0.17
        m.opacityThreshold = 0.45
        m.blending = .transparent(opacity: 1.0)
        // Seen from behind when the wearer walks round the ambulatory. A
        // culled back face would make the bust vanish from half the room.
        m.faceCulling = .none
        return m
    }
}


/// The light in the room, drawn rather than loaded.
///
/// `ImageBasedLightComponent` wants an `EnvironmentResource`, and the usual way
/// to get one is a checked-in `.hdr`. This repository does not check in binary
/// assets, so the equirectangular map is painted into a `CGImage` here: a warm
/// oculus overhead, a band of clerestory windows at the springing line, and a
/// dark floor. The vertical bars matter more than they look - a metal lit by a
/// perfectly smooth gradient has nothing to reflect and reads as flat plastic,
/// and those bars are what a wearer actually sees travelling across a bust as
/// they walk past it.
enum HallLight {

    static func equirect(width: Int = 512, height: Int = 256) -> CGImage? {
        var px = [UInt8](repeating: 0, count: width * height * 4)
        for y in 0..<height {
            // 0 at the zenith, 1 at nadir.
            let v = Double(y) / Double(height - 1)
            // Overhead: the oculus. Falls off fast, so the room is lit from a
            // hole in the roof rather than from everywhere.
            let sky = pow(max(0, 1 - v * 2.1), 2.2) * 4.2
            // The floor returns almost nothing: polished stone at grazing
            // incidence, and a bright floor would light the busts from below
            // and make them look like a car showroom.
            // A little more than nothing. Bronze at metallic 1.0 has no
            // diffuse term at all, so what the floor throws back is the only
            // thing modelling the underside of a bust; at 0.05 every chin in
            // the room was solid black.
            let ground = max(0, (v - 0.55) / 0.45) * 0.14 + 0.05
            for x in 0..<width {
                let u = Double(x) / Double(width)
                // Ten clerestory openings on the ring, aligned with the bays.
                let bay = abs(sin(u * .pi * 10))
                let window = pow(bay, 26) * max(0, 1 - abs(v - 0.30) * 9) * 2.6
                let e = sky + ground + window
                let r = min(1.0, e * 1.00)
                let g = min(1.0, e * 0.78)
                let b = min(1.0, e * 0.52)
                let i = (y * width + x) * 4
                px[i] = UInt8(r * 255)
                px[i + 1] = UInt8(g * 255)
                px[i + 2] = UInt8(b * 255)
                px[i + 3] = 255
            }
        }
        let cs = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(data: &px, width: width, height: height,
                                  bitsPerComponent: 8, bytesPerRow: width * 4,
                                  space: cs,
                                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
        else { return nil }
        return ctx.makeImage()
    }

    /// Built once per space. `EnvironmentResource` pre-filters the map into a
    /// specular chain, which is not free, so this is awaited during set-up and
    /// never on a frame.
    @MainActor
    static func environment() async -> EnvironmentResource? {
        guard let img = equirect() else { return nil }
        return try? await EnvironmentResource(equirectangular: img)
    }
}
