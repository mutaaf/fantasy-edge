import RealityKit
import UIKit
import simd

/// The moment graphic: TOUCHDOWN, FIELD GOAL, SAFETY as a broadcast would
/// put it up - a slab in the scoring side's colour hung high over the end
/// zone it happened in, big enough to own the moment from any seat
/// (`visual.broadcast.banner`). It wipes open, holds for the scene's
/// `motion.momentSeconds`, and wipes shut; with reduce motion it is simply
/// there and then gone.
@MainActor
final class BroadcastBanner {
    let root = Entity()
    private let plate = ModelEntity()
    private let glow = ModelEntity()
    private var shownAt: Double?
    private var dwell: Double = 4.5
    private var size = SIMD2<Float>(1, 1)

    init() {
        root.name = "broadcast.banner"
        plate.name = "banner.plate"
        glow.name = "banner.glow"
        root.addChild(glow)
        root.addChild(plate)
        root.components.set(BillboardComponent())
        root.isEnabled = false
    }

    func clear() {
        root.isEnabled = false
        shownAt = nil
    }

    func show(_ m: SceneSpec.Moment, _ c: StadiumContext) {
        guard m.celebrates else { return }
        let s = c.spec, look = c.look.broadcast.banner
        let word = c.look.broadcast.ribbon.flash.words[m.kind] ?? m.kind.uppercased()
        let team = m.side == "away" ? s.teams.away : s.teams.home
        guard let img = Self.image(word: word, team: team, s: s, look: look),
              let pm = BroadcastGraphics.overlay(img, opacity: 1) else { return }
        let w = Float(look.widthYards.value(tabletop: c.tabletop))
        let h = w * Float(img.height) / Float(max(1, img.width))
        size = SIMD2(w, h)
        plate.model = ModelComponent(mesh: .generatePlane(width: w, height: h), materials: [pm])
        let gm = StadiumLook.glow(team.chip, opacity: look.glowOpacity, texture: c.assets.texture("broadcast.marker"))
        glow.model = ModelComponent(mesh: .generatePlane(width: w * Float(look.glowScale), height: h * Float(look.glowScale) * 2.2),
                                    materials: [gm])
        glow.position = SIMD3(0, 0, -0.05)

        let anchor = m.anchor ?? SceneSpec.Point(x: m.side == "home" ? 105 : -5, y: 0, z: 0)
        root.position = SceneMath.local(x: anchor.x, y: look.liftYards.value(tabletop: c.tabletop), z: anchor.z)
        dwell = max(1, s.motion.momentSeconds ?? 4.5)
        shownAt = c.shared.time
        root.isEnabled = true
        apply(open: c.reduceMotion ? 1 : 0, c)
    }

    func update(_ c: StadiumContext) {
        guard let start = shownAt else { return }
        let look = c.look.broadcast.banner
        let age = c.shared.time - start
        if age >= dwell {
            clear()
            return
        }
        if c.reduceMotion {
            apply(open: 1, c)
            return
        }
        let opening = min(1, age / max(0.05, look.inSeconds))
        let closing = min(1, max(0, (dwell - age) / max(0.05, look.outSeconds)))
        let eased = 1 - pow(1 - min(opening, closing), 3)
        apply(open: eased, c)
    }

    /// 0 shut, 1 open: the slab wipes out from its centre line and its light
    /// comes up with it.
    private func apply(open: Double, _ c: StadiumContext) {
        let f = Float(max(0.001, open))
        plate.scale = SIMD3(f, min(1, 0.35 + 0.65 * f), 1)
        glow.scale = SIMD3(f, f, 1)
    }

    static func image(word: String, team: SceneSpec.Team, s: SceneSpec, look: SceneSpec.Look.BannerLook) -> CGImage? {
        let W = look.pixels.count == 2 ? look.pixels[0] : 2048
        let H = look.pixels.count == 2 ? look.pixels[1] : 560
        return BroadcastGraphics.image(width: W, height: H, opaque: false) { ctx, size in
            ctx.clear(CGRect(origin: .zero, size: size))
            let chip = StadiumLook.color(team.chip)
            let rect = CGRect(origin: .zero, size: size).insetBy(dx: size.height * 0.03, dy: size.height * 0.06)
            let radius = size.height * 0.1
            // The slab: the side's chip, lighter at the top like a lit panel.
            ctx.saveGState()
            UIBezierPath(roundedRect: rect, cornerRadius: radius).addClip()
            var hue: CGFloat = 0, sat: CGFloat = 0, bri: CGFloat = 0, a: CGFloat = 0
            chip.getHue(&hue, saturation: &sat, brightness: &bri, alpha: &a)
            let top = UIColor(hue: hue, saturation: sat * 0.9, brightness: min(1, bri * 1.45 + 0.08), alpha: 1)
            let bottom = UIColor(hue: hue, saturation: min(1, sat * 1.05), brightness: bri * 0.72, alpha: 1)
            if let grad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: [top.cgColor, bottom.cgColor] as CFArray,
                                     locations: [0, 1]) {
                ctx.drawLinearGradient(grad, start: CGPoint(x: 0, y: rect.minY), end: CGPoint(x: 0, y: rect.maxY), options: [])
            }
            // A bright rule along the top and a dark band along the bottom.
            UIColor.white.withAlphaComponent(0.85).setFill()
            ctx.fill(CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: size.height * 0.03))
            UIColor.black.withAlphaComponent(0.28).setFill()
            ctx.fill(CGRect(x: rect.minX, y: rect.maxY - size.height * 0.24, width: rect.width, height: size.height * 0.24))
            ctx.restoreGState()

            // The word, as large as the slab allows.
            var font = size.height * 0.5
            var t = NSAttributedString()
            repeat {
                t = NSAttributedString(string: word, attributes: [.font: UIFont.systemFont(ofSize: font, weight: .black),
                                                                  .foregroundColor: UIColor.white, .kern: font * 0.06])
                font *= 0.94
            } while t.size().width > rect.width * 0.9 && font > 20
            t.draw(at: CGPoint(x: rect.midX - t.size().width / 2, y: rect.minY + size.height * 0.07))

            // Under it: the scoreline after the score.
            let small = UIFont.systemFont(ofSize: size.height * 0.13, weight: .heavy)
            let line = "\(s.teams.away.abbr) \(Int(s.status.awayScore))     \(s.teams.home.abbr) \(Int(s.status.homeScore))"
            let sub = NSAttributedString(string: line, attributes: [.font: small, .foregroundColor: UIColor.white.withAlphaComponent(0.92),
                                                                    .kern: size.height * 0.012])
            sub.draw(at: CGPoint(x: rect.midX - sub.size().width / 2, y: rect.maxY - size.height * 0.12 - sub.size().height / 2))
        }
    }
}
