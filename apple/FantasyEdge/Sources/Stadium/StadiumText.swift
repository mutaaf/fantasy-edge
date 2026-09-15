import RealityKit
import UIKit

/// Text and graphics drawn into textures, shared by the actors that need
/// them: the ribbon board (Broadcast) and the LED boards (Sideline).
@MainActor
enum StadiumText {
    static func image(width: Int, height: Int, _ draw: (CGContext, CGSize) -> Void) -> CGImage? {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let size = CGSize(width: width, height: height)
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            draw(ctx.cgContext, size)
        }.cgImage
    }

    static func texture(_ img: CGImage?) -> TextureResource? {
        guard let img else { return nil }
        var o = TextureResource.CreateOptions(semantic: .color)
        o.mipmapsMode = .allocateAndGenerateAll
        return try? TextureResource(image: img, options: o)
    }

    static func ribbonKey(_ s: SceneSpec) -> String {
        "\(s.teams.away.abbr)\(Int(s.status.awayScore))|\(s.teams.home.abbr)\(Int(s.status.homeScore))|\(s.status.downDistance)|\(s.status.redZone)|\(s.status.label)"
    }

    static func ribbonImage(_ s: SceneSpec, look: SceneSpec.Look) -> CGImage? {
        let h = look.broadcast.ribbon.heightPixels
        let rise = (s.bowl.ribbon?.rise[1] ?? 23.6) - (s.bowl.ribbon?.rise[0] ?? 21)
        let w = h * Int((look.broadcast.ribbon.segmentYards / max(0.1, rise)).rounded())
        return image(width: max(256, w), height: h) { ctx, size in
            StadiumLook.color(s.palette[s.bowl.ribbon?.color ?? ""] ?? "#05060A").setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            let ink = StadiumLook.color(s.palette[s.bowl.ribbon?.text ?? ""] ?? "#F7F6F2")
            let font = UIFont.systemFont(ofSize: size.height * 0.56, weight: .heavy)
            var x: CGFloat = size.height * 0.4
            func chip(_ t: SceneSpec.Team, _ score: Double) {
                let rect = CGRect(x: x, y: size.height * 0.16, width: size.height * 1.35, height: size.height * 0.68)
                StadiumLook.color(t.chip).setFill()
                UIBezierPath(roundedRect: rect, cornerRadius: size.height * 0.08).fill()
                let abbr = NSAttributedString(string: t.abbr, attributes: [.font: UIFont.systemFont(ofSize: size.height * 0.42, weight: .black),
                                                                           .foregroundColor: UIColor.white])
                let ab = abbr.size()
                abbr.draw(at: CGPoint(x: rect.midX - ab.width / 2, y: rect.midY - ab.height / 2))
                x = rect.maxX + size.height * 0.3
                let n = NSAttributedString(string: "\(Int(score))", attributes: [.font: font, .foregroundColor: ink])
                n.draw(at: CGPoint(x: x, y: (size.height - n.size().height) / 2))
                x += n.size().width + size.height * 0.7
            }
            chip(s.teams.away, s.status.awayScore)
            chip(s.teams.home, s.status.homeScore)
            var tail = [s.status.label, s.status.downDistance].filter { !$0.isEmpty }.joined(separator: "   ·   ")
            if s.status.redZone { tail += "   ·   RED ZONE" }
            let t = NSAttributedString(string: tail.uppercased(), attributes: [.font: UIFont.systemFont(ofSize: size.height * 0.44, weight: .bold),
                                                                               .foregroundColor: ink])
            t.draw(at: CGPoint(x: x, y: (size.height - t.size().height) / 2))
        }
    }

    static func updateRibbon(_ tex: TextureResource, _ s: SceneSpec, look: SceneSpec.Look) {
        guard let img = ribbonImage(s, look: look) else { return }
        try? tex.replace(withImage: img, options: .init(semantic: .color))
    }

    /// The LED boards along the front wall: each club's colours and name, in turn.
    static func boards(_ s: SceneSpec) -> TextureResource? {
        texture(image(width: 1024, height: 64) { ctx, size in
            let half = size.width / 2
            for (i, t) in [s.teams.home, s.teams.away].enumerated() {
                let rect = CGRect(x: CGFloat(i) * half, y: 0, width: half, height: size.height)
                UIColor(white: 0.03, alpha: 1).setFill()
                ctx.fill(rect)
                StadiumLook.color(t.chip).setFill()
                ctx.fill(CGRect(x: rect.minX, y: 0, width: half * 0.12, height: size.height))
                ctx.fill(CGRect(x: rect.maxX - half * 0.04, y: 0, width: half * 0.04, height: size.height))
                let label = NSAttributedString(string: t.name.uppercased(), attributes: [
                    .font: UIFont.systemFont(ofSize: size.height * 0.52, weight: .heavy),
                    .foregroundColor: UIColor(white: 0.92, alpha: 1), .kern: 6])
                let ls = label.size()
                label.draw(at: CGPoint(x: rect.minX + half * 0.18, y: (size.height - ls.height) / 2))
            }
        })
    }
}
