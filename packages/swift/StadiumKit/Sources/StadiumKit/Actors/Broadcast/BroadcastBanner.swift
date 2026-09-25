import RealityKit
import UIKit
import simd

/// The moment graphic: TOUCHDOWN, FIELD GOAL, SAFETY as a broadcast would
/// put it up - a slab in the scoring side's colour hung over the end zone it
/// happened in, big enough to own the moment from any seat.
///
/// What it is and when are Moments & Audio's contract, read from
/// `visual.moments`: which kinds get a banner (`banner.kinds`), when it goes
/// up (`timeline[kind].banner`, -1 for never), how wide it looks from the
/// wearer's eye (`banner.widthDegrees`, never shorter than
/// `minHeightDegrees`), how high over the end zone (`heightYards`), how long
/// (`dwellSeconds`, `enterSeconds`, `exitSeconds`) and how big its subtitle
/// reads (`subtitleDegrees`). How it looks is Broadcast's
/// (`visual.broadcast.banner`). With reduce motion there is no wipe.
@MainActor
final class BroadcastBanner {
    let root = Entity()
    private let plate = ModelEntity()
    private let glow = ModelEntity()
    private var shownAt: Double?
    private var pending: (moment: SceneSpec.Moment, at: Double)?
    private var dwell: Double = 4.2
    /// The default for `visual.moments.banner.minSeconds`.
    private static let defaultMinSeconds = 2.5

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
        pending = nil
    }

    /// A moment arrived: schedule its banner at the timeline's offset, if its
    /// kind gets one.
    func arrive(_ m: SceneSpec.Moment, _ c: StadiumContext) {
        let spec = c.look.moments
        guard spec.banner.kinds.contains(m.kind) else { return }
        let delay = spec.timeline[m.kind]?.banner ?? 0
        guard delay >= 0 else { return }
        clear()
        pending = (m, c.shared.time + delay)
    }

    /// The next play is about to snap. A moment graphic belongs to the play
    /// that caused it, so it comes down before the next one - a TOUCHDOWN slab
    /// still up over the kickoff (integration-13, t8.5) belongs to a game the
    /// board has already left. It is never cut shorter than
    /// `visual.moments.banner.minSeconds`, so a quick snap or a fast replay
    /// flashes nothing: the dwell shortens to that floor instead of vanishing.
    func snapping(_ c: StadiumContext) {
        let floor = c.look.moments.banner.minSeconds ?? Self.defaultMinSeconds
        // Scheduled but not yet up: the play it belonged to is over.
        guard let start = shownAt else {
            pending = nil
            return
        }
        // It wipes out rather than disappearing, so the end it is given is the
        // exit's length away.
        let exit = max(0.05, c.look.moments.banner.exitSeconds)
        dwell = min(dwell, max(floor, c.shared.time - start + exit))
    }

    private func show(_ m: SceneSpec.Moment, _ c: StadiumContext) {
        let s = c.spec, look = c.look.broadcast.banner, contract = c.look.moments.banner
        let word = c.look.broadcast.ribbon.flash.words[m.kind] ?? m.kind.uppercased()
        let team = m.side == "away" ? s.teams.away : s.teams.home
        let anchor = m.anchor ?? SceneSpec.Point(x: m.side == "home" ? 105 : -5, y: 0, z: 0)
        let centre = SceneMath.local(x: anchor.x, y: contract.heightYards, z: anchor.z)

        // Width from the angle it must fill at the wearer's eye; on the table
        // there is no eye in the model, so the table's own width applies.
        let W = look.pixels.count == 2 ? look.pixels[0] : 2048
        let H = look.pixels.count == 2 ? look.pixels[1] : 560
        var w = Float(look.widthYards.value(tabletop: true))
        var heightDegrees = contract.widthDegrees * Double(H) / Double(W)
        if let eye = c.shared.seat, !c.tabletop {
            let d = Double(simd_distance(eye, centre))
            let widthYards = 2 * d * tan(contract.widthDegrees * .pi / 360)
            let heightYards = max(widthYards * Double(H) / Double(W), 2 * d * tan(contract.minHeightDegrees * .pi / 360))
            w = Float(heightYards * Double(W) / Double(H))
            heightDegrees = 2 * atan(heightYards / (2 * d)) * 180 / .pi
        }
        let subtitleShare = min(0.3, max(0.08, contract.subtitleDegrees / max(1, heightDegrees)))
        guard let img = Self.image(word: word, team: team, s: s, look: look, subtitleShare: subtitleShare),
              let pm = BroadcastGraphics.overlay(img, opacity: 1) else { return }
        let h = w * Float(img.height) / Float(max(1, img.width))
        plate.model = ModelComponent(mesh: .generatePlane(width: w, height: h), materials: [pm])
        let gm = StadiumLook.glow(team.chip, opacity: look.glowOpacity, texture: c.assets.texture("broadcast.marker"))
        glow.model = ModelComponent(mesh: .generatePlane(width: w * Float(look.glowScale), height: h * Float(look.glowScale) * 2.2),
                                    materials: [gm])
        glow.position = SIMD3(0, 0, -0.05)

        root.position = centre
        dwell = max(0.5, contract.dwellSeconds)
        shownAt = c.shared.time
        root.isEnabled = true
        apply(open: c.reduceMotion ? 1 : 0)
    }

    func update(_ c: StadiumContext) {
        if let p = pending, c.shared.time >= p.at {
            pending = nil
            show(p.moment, c)
        }
        guard let start = shownAt else { return }
        let contract = c.look.moments.banner
        let age = c.shared.time - start
        if age >= dwell {
            root.isEnabled = false
            shownAt = nil
            return
        }
        if c.reduceMotion {
            apply(open: 1)
            return
        }
        let opening = min(1, age / max(0.05, contract.enterSeconds))
        let closing = min(1, max(0, (dwell - age) / max(0.05, contract.exitSeconds)))
        apply(open: 1 - pow(1 - min(opening, closing), 3))
    }

    /// 0 shut, 1 open: the slab wipes out from its centre line and its light
    /// comes up with it.
    private func apply(open: Double) {
        let f = Float(max(0.001, open))
        plate.scale = SIMD3(f, min(1, 0.35 + 0.65 * f), 1)
        glow.scale = SIMD3(f, f, 1)
    }

    /// The slab. `subtitleShare` is the scoreline's font size as a share of
    /// the slab's height, solved so it reads at `subtitleDegrees`.
    static func image(word: String, team: SceneSpec.Team, s: SceneSpec, look: SceneSpec.Look.BannerLook,
                      subtitleShare: Double) -> CGImage? {
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
            let subSize = size.height * CGFloat(subtitleShare)
            let band = subSize * 1.7
            UIColor.black.withAlphaComponent(0.28).setFill()
            ctx.fill(CGRect(x: rect.minX, y: rect.maxY - band, width: rect.width, height: band))
            ctx.restoreGState()

            // The word, as large as the slab above the scoreline allows.
            let wordArea = CGRect(x: rect.minX, y: rect.minY + size.height * 0.04, width: rect.width, height: rect.height - band - size.height * 0.04)
            var font = wordArea.height * 0.95
            var t = NSAttributedString()
            repeat {
                t = NSAttributedString(string: word, attributes: [.font: UIFont.systemFont(ofSize: font, weight: .black),
                                                                  .foregroundColor: UIColor.white, .kern: font * 0.06])
                font *= 0.94
            } while (t.size().width > rect.width * 0.9 || t.size().height > wordArea.height) && font > 20
            t.draw(at: CGPoint(x: rect.midX - t.size().width / 2, y: wordArea.midY - t.size().height / 2))

            // Under it: the scoreline after the score, at the contract's size.
            let small = UIFont.systemFont(ofSize: subSize, weight: .heavy)
            let line = "\(s.teams.away.abbr) \(Int(s.status.awayScore))     \(s.teams.home.abbr) \(Int(s.status.homeScore))"
            let sub = NSAttributedString(string: line, attributes: [.font: small, .foregroundColor: UIColor.white.withAlphaComponent(0.92),
                                                                    .kern: subSize * 0.09])
            sub.draw(at: CGPoint(x: rect.midX - sub.size().width / 2, y: rect.maxY - band / 2 - sub.size().height / 2))
        }
    }
}
