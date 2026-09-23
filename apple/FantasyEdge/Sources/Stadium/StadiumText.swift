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

    /// The LED boards along the front wall. One repeat carries what a real
    /// ribbon carries - both clubs with their scores, the clock, and the down
    /// and distance - and the wall tiles it every `visual.sideline.boards
    /// .panelYards`.
    ///
    /// The score is `s.status`, which is the status the stadium is *showing*:
    /// `StadiumRenderer` writes `shownStatus` into the spec it hands every
    /// actor, so these boards cannot announce a touchdown before the ball has
    /// landed any more than the ribbon or the video board can.
    static func boardsImage(_ s: SceneSpec, look: SceneSpec.Look) -> CGImage? {
        let B = look.sideline.boards
        let h = B.heightPixels
        // Square-ish texels: the panel is `panelYards` long and the wall
        // `wall.height` tall, so the width follows that ratio.
        let rise = max(0.1, s.bowl.wall?.height ?? 1.4)
        let w = Int((Double(h) * B.panelYards / rise).rounded())
        return image(width: max(256, w), height: h) { ctx, size in
            UIColor(white: 0.02, alpha: 1).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            let ink = UIColor(white: 0.94, alpha: 1)
            let font = UIFont.systemFont(ofSize: size.height * 0.5, weight: .heavy)
            var x = size.height * 0.5
            func chip(_ t: SceneSpec.Team, _ score: Double) {
                let rect = CGRect(x: x, y: size.height * 0.2, width: size.height * 1.5, height: size.height * 0.6)
                StadiumLook.color(t.chip).setFill()
                UIBezierPath(roundedRect: rect, cornerRadius: size.height * 0.08).fill()
                let abbr = NSAttributedString(string: t.abbr, attributes: [
                    .font: UIFont.systemFont(ofSize: size.height * 0.4, weight: .black), .foregroundColor: UIColor.white])
                let ab = abbr.size()
                abbr.draw(at: CGPoint(x: rect.midX - ab.width / 2, y: rect.midY - ab.height / 2))
                x = rect.maxX + size.height * 0.25
                let n = NSAttributedString(string: "\(Int(score))", attributes: [.font: font, .foregroundColor: ink])
                n.draw(at: CGPoint(x: x, y: (size.height - n.size().height) / 2))
                x += n.size().width + size.height * 0.8
            }
            chip(s.teams.away, s.status.awayScore)
            chip(s.teams.home, s.status.homeScore)
            var tail = [s.status.label, s.status.downDistance].filter { !$0.isEmpty }.joined(separator: "   ·   ")
            if s.status.redZone { tail += "   ·   RED ZONE" }
            let t = NSAttributedString(string: tail.uppercased(), attributes: [
                .font: UIFont.systemFont(ofSize: size.height * 0.42, weight: .bold), .foregroundColor: ink])
            t.draw(at: CGPoint(x: x, y: (size.height - t.size().height) / 2))
        }
    }

    static func boards(_ s: SceneSpec, look: SceneSpec.Look) -> TextureResource? {
        boardsImage(s, look: look).flatMap { texture($0) }
    }

    static func updateBoards(_ tex: TextureResource, _ s: SceneSpec, look: SceneSpec.Look) {
        guard let img = boardsImage(s, look: look) else { return }
        try? tex.replace(withImage: img, options: .init(semantic: .color))
    }
}
