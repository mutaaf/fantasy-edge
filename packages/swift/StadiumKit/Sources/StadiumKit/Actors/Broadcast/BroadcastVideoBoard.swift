import RealityKit
import UIKit
import simd

/// What the video board behind the east end zone shows (`bowl.videoBoard` is
/// Bowl's frame and face; `visual.broadcast.videoBoard` is how it looks): the
/// scorebug across the top, the last play under it, and the drive drawn as a
/// small field from above. One opaque emissive plane a hair in front of
/// Bowl's dark screen, redrawn only when what it says changes. Stadium only.
@MainActor
final class BroadcastVideoBoard {
    let root = Entity()
    private var entity: ModelEntity?
    private var texture: TextureResource?
    private var key = ""

    init() { root.name = "broadcast.videoBoard" }

    func build(_ c: StadiumContext) {
        root.children.removeAll()
        entity = nil
        texture = nil
        key = ""
        guard !c.tabletop, let vb = c.spec.bowl.videoBoard, vb.centre.count == 3, vb.facing.count == 3,
              vb.size.count == 2 else { return }
        let look = c.look.broadcast.videoBoard
        guard let img = Self.image(c.spec, look: look), let tex = StadiumText.texture(img) else { return }
        texture = tex
        // Built before any play of this drive has landed: the board says the
        // score and the down, and takes its first play from the first landing.
        key = Self.key(c.spec, told: nil)
        let w = Float(vb.size[0]), h = Float(vb.size[1])
        let e = ModelEntity(mesh: .generatePlane(width: w, height: h),
                            materials: [StadiumLook.emissive("#FFFFFF", scale: look.brightness, texture: tex, tile: false)])
        e.name = "videoBoard.face"
        // Face along `facing`, the texture's +x to the right of whoever looks at it.
        let n = simd_normalize(SIMD3(Float(vb.facing[0]), Float(vb.facing[1]), Float(vb.facing[2])))
        var right = simd_cross(-n, SIMD3<Float>(0, 1, 0))
        if simd_length(right) < 1e-4 { right = SIMD3(1, 0, 0) }
        right = simd_normalize(right)
        let up = simd_cross(n, right)
        e.orientation = simd_quatf(simd_float3x3(columns: (right, up, n)))
        let centre = SceneMath.local(x: vb.centre[0], y: vb.centre[1], z: vb.centre[2])
        e.position = centre + n * Float(look.offset)
        entity = e
        root.addChild(e)
    }

    /// `laid` is a play the viewer has seen land. The board narrates the
    /// newest of those, never the one in the air: it read "31 yard field goal
    /// is GOOD" with the kick still up, beside a score correctly waiting for
    /// it (integration-13, score-timing).
    func apply(_ c: StadiumContext, laid: (String) -> Bool) {
        guard let tex = texture else { return }
        let told = Self.newestLaid(c.spec, laid: laid)
        let k = Self.key(c.spec, told: told)
        guard k != key else { return }
        key = k
        if let img = Self.image(c.spec, look: c.look.broadcast.videoBoard, told: told) {
            try? tex.replace(withImage: img, options: .init(semantic: .color))
        }
    }

    /// The newest play on the drive that has landed, or nil while the first
    /// play of a drive is still in the air. The rule lives in `LaidPlay`, which
    /// the composer and the drive log ask too.
    static func newestLaid(_ s: SceneSpec, laid: (String) -> Bool) -> SceneSpec.Arc? {
        LaidPlay.newest(s.shownDrive, laid: laid)
    }

    static func key(_ s: SceneSpec, told: SceneSpec.Arc?) -> String {
        let d = s.shownDrive
        return "\(StadiumText.ribbonKey(s))|\(d?.id ?? "")|\(told?.id ?? "-")|\(s.ball?.x ?? -1)"
    }

    /// The board's picture. Every size is a share of its height, so the
    /// legibility rule in the tokens (`smallTextShare`) is the size of the
    /// smallest words on it.
    static func image(_ s: SceneSpec, look: SceneSpec.Look.VideoBoardLook, told: SceneSpec.Arc? = nil) -> CGImage? {
        let W = look.pixels.count == 2 ? look.pixels[0] : 1600
        let H = look.pixels.count == 2 ? look.pixels[1] : 600
        return BroadcastGraphics.image(width: W, height: H, opaque: true) { ctx, size in
            let h = size.height, w = size.width
            UIColor(white: 0.02, alpha: 1).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            let ink = UIColor(white: 0.97, alpha: 1)
            let small = h * CGFloat(look.smallTextShare)
            let pad = h * 0.05
            let rounded = { (size: CGFloat, weight: UIFont.Weight) -> UIFont in
                let f = UIFont.systemFont(ofSize: size, weight: weight)
                return f.fontDescriptor.withDesign(.rounded).map { UIFont(descriptor: $0, size: size) } ?? f
            }
            /// Draw centred in `rect`, shrinking to fit its width.
            func centred(_ string: String, _ font: UIFont, _ colour: UIColor, in rect: CGRect) {
                var t = NSAttributedString(string: string, attributes: [.font: font, .foregroundColor: colour])
                if t.size().width > rect.width, rect.width > 0 {
                    let fit = font.withSize(font.pointSize * rect.width / t.size().width)
                    t = NSAttributedString(string: string, attributes: [.font: fit, .foregroundColor: colour])
                }
                let ts = t.size()
                t.draw(at: CGPoint(x: rect.midX - ts.width / 2, y: rect.midY - ts.height / 2))
            }

            // The score, as a stadium board says it: each club a block of its
            // own colour with the number filling it, the clock between them.
            let bugH = h * CGFloat(look.scorebugShare)
            let sideW = w * CGFloat(look.sideShare)
            func side(_ t: SceneSpec.Team, _ score: Double, x: CGFloat, possession: Bool) {
                let rect = CGRect(x: x, y: 0, width: sideW, height: bugH)
                StadiumLook.color(t.chip).setFill()
                ctx.fill(rect)
                UIColor(white: 0, alpha: 0.28).setFill()
                ctx.fill(CGRect(x: rect.minX, y: rect.minY, width: rect.width * 0.42, height: rect.height))
                // A ranked club says so, the way a chyron does: the number
                // small and above its own abbreviation, never instead of it.
                let block = CGRect(x: rect.minX, y: rect.minY, width: rect.width * 0.42,
                                   height: rect.height).insetBy(dx: pad * 0.6, dy: 0)
                if let rank = t.rank {
                    centred("#\(rank)", rounded(bugH * 0.17, .heavy), UIColor(white: 1, alpha: 0.85),
                            in: CGRect(x: block.minX, y: block.minY + bugH * 0.08,
                                       width: block.width, height: bugH * 0.22))
                    centred(t.abbr, rounded(bugH * 0.30, .black), .white,
                            in: CGRect(x: block.minX, y: block.minY + bugH * 0.28,
                                       width: block.width, height: block.height - bugH * 0.30))
                } else {
                    centred(t.abbr, rounded(bugH * 0.34, .black), .white, in: block)
                }
                centred("\(Int(score))", rounded(bugH * 0.86, .black), .white,
                        in: CGRect(x: rect.minX + rect.width * 0.42, y: rect.minY, width: rect.width * 0.58, height: rect.height))
                if possession {
                    UIColor.white.setFill()
                    ctx.fill(CGRect(x: rect.minX, y: rect.maxY - h * 0.03, width: rect.width, height: h * 0.03))
                }
            }
            side(s.teams.away, s.status.awayScore, x: 0, possession: s.status.possession == "away")
            side(s.teams.home, s.status.homeScore, x: w - sideW, possession: s.status.possession == "home")
            // "11:00 - 1st" is the clock over the quarter; "Halftime" stays whole.
            let centre = CGRect(x: sideW, y: 0, width: w - 2 * sideW, height: bugH).insetBy(dx: pad, dy: 0)
            let label = s.status.label.uppercased().components(separatedBy: " - ")
            if label.count == 2 {
                centred(label[0], rounded(bugH * 0.56, .heavy), ink,
                        in: CGRect(x: centre.minX, y: 0, width: centre.width, height: bugH * 0.66))
                centred(label[1], rounded(bugH * 0.26, .bold), ink.withAlphaComponent(0.75),
                        in: CGRect(x: centre.minX, y: bugH * 0.6, width: centre.width, height: bugH * 0.34))
            } else {
                centred(label.joined(), rounded(bugH * 0.36, .heavy), ink, in: centre)
            }

            // The down strip, the width of the board: what the next snap is.
            let downH = h * CGFloat(look.downShare)
            let strip = CGRect(x: 0, y: bugH, width: w, height: downH)
            (s.status.redZone ? UIColor(red: 0.62, green: 0.1, blue: 0.08, alpha: 1) : UIColor(white: 0.1, alpha: 1)).setFill()
            ctx.fill(strip)
            if !s.status.downDistance.isEmpty {
                let words = s.status.redZone ? "\(s.status.downDistance)   ·   RED ZONE" : s.status.downDistance
                centred(words.uppercased(), rounded(downH * 0.66, .heavy), ink, in: strip.insetBy(dx: pad, dy: 0))
            }

            // Under it, left: the last play, in words.
            let top = bugH + downH + h * 0.035
            let split = w * CGFloat(look.textShare)
            let arcs = s.shownDrive?.arcs ?? []
            // Only as far as the viewer has seen: the plays up to and
            // including the one the board is narrating.
            let seen = told.flatMap { t in arcs.firstIndex(where: { $0.id == t.id }).map { Array(arcs[...$0]) } } ?? []
            if let last = told {
                // A bar in the play's own trail colour says "this is the last
                // play" without spending a line of the board's height on it.
                StadiumLook.color(s.palette[last.color] ?? "#FFFFFF").setFill()
                ctx.fill(CGRect(x: pad, y: top + small * 0.1, width: h * 0.018, height: small * 1.25 * CGFloat(look.lines) - small * 0.2))
                // Word-wrapped, the last visible line truncated: a tail
                // line-break mode on the paragraph would clip to one line.
                let words = NSAttributedString(string: Self.plain(last.text), attributes: [
                    .font: UIFont.systemFont(ofSize: small, weight: .bold), .foregroundColor: ink])
                let box = CGRect(x: pad + h * 0.05, y: top, width: split - pad * 2 - h * 0.05,
                                 height: small * 1.25 * CGFloat(look.lines))
                words.draw(with: box, options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine], context: nil)
            }

            // Right: the drive from above - the field, its plays, the ball.
            let field = CGRect(x: split, y: top, width: w - split - pad, height: h - top - pad)
            UIColor(red: 0.09, green: 0.33, blue: 0.16, alpha: 1).setFill()
            ctx.fill(field)
            let ez = field.width * 10 / 120
            StadiumLook.color(s.teams.home.chip).setFill()
            ctx.fill(CGRect(x: field.minX, y: field.minY, width: ez, height: field.height))
            StadiumLook.color(s.teams.away.chip).setFill()
            ctx.fill(CGRect(x: field.maxX - ez, y: field.minY, width: ez, height: field.height))
            func fx(_ yard: Double) -> CGFloat { field.minX + ez + (field.width - 2 * ez) * CGFloat(yard / 100) }
            func fz(_ lane: Double) -> CGFloat { field.midY - field.height * 0.8 * CGFloat(lane / s.field.width) }
            ctx.setStrokeColor(UIColor.white.withAlphaComponent(0.35).cgColor)
            ctx.setLineWidth(h * 0.004)
            for yd in stride(from: 10.0, through: 90.0, by: 10.0) {
                ctx.move(to: CGPoint(x: fx(yd), y: field.minY))
                ctx.addLine(to: CGPoint(x: fx(yd), y: field.maxY))
            }
            ctx.strokePath()
            // The diagram draws the plays the viewer has seen land, for the
            // same reason the words do.
            let drawn = seen.suffix(look.plays)
            for (i, arc) in drawn.enumerated() {
                let newest = i == drawn.count - 1
                let colour = StadiumLook.color(s.palette[arc.color] ?? "#FFFFFF").withAlphaComponent(newest ? 1 : 0.55)
                ctx.setStrokeColor(colour.cgColor)
                ctx.setLineWidth(h * (newest ? 0.014 : 0.008))
                ctx.setLineCap(.round)
                ctx.move(to: CGPoint(x: fx(arc.fromX), y: fz(arc.lane)))
                ctx.addLine(to: CGPoint(x: fx(arc.toX), y: fz(arc.lane)))
                ctx.strokePath()
            }
            if let ball = s.ball {
                let r = h * 0.022
                UIColor(red: 0.55, green: 0.29, blue: 0.13, alpha: 1).setFill()
                ctx.fillEllipse(in: CGRect(x: fx(ball.x) - r * 1.4, y: field.midY - r, width: r * 2.8, height: r * 2))
                UIColor.white.setStroke()
                ctx.setLineWidth(h * 0.005)
                ctx.strokeEllipse(in: CGRect(x: fx(ball.x) - r * 1.4, y: field.midY - r, width: r * 2.8, height: r * 2))
            }
        }
    }

    /// ESPN's play text without its leading parentheticals and jersey numbers.
    static func plain(_ text: String) -> String {
        var t = text
        // Leading parentheticals: the clock, "(Shotgun)", "(No Huddle, Shotgun)".
        while let r = t.range(of: #"^\([^)]*\)\s*"#, options: .regularExpression) { t.removeSubrange(r) }
        t = t.replacingOccurrences(of: #"#\d+\s"#, with: "", options: .regularExpression)
        return t
    }
}
