import RealityKit
import UIKit
import simd

/// Pictures the broadcast package draws into textures: the ribbon board's
/// crawl and its flashes, and the down-and-distance tag painted on the field.
@MainActor
enum BroadcastGraphics {
    static func image(width: Int, height: Int, opaque: Bool, _ draw: (CGContext, CGSize) -> Void) -> CGImage? {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = opaque
        let size = CGSize(width: max(1, width), height: max(1, height))
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            draw(ctx.cgContext, size)
        }.cgImage
    }

    /// A picture's alpha as a grey image. A transparent material takes its
    /// opacity from a texture's colour, not its alpha, so a coloured graphic
    /// drawn with its own alpha as opacity loses every pixel that is not
    /// red: the chip under the word disappears and only white survives.
    static func alphaMask(_ img: CGImage) -> CGImage? {
        let w = img.width, h = img.height
        guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                                  space: CGColorSpaceCreateDeviceGray(),
                                  bitmapInfo: CGImageAlphaInfo.alphaOnly.rawValue) else { return nil }
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        guard let bytes = ctx.data, let provider = CGDataProvider(data: Data(bytes: bytes, count: w * h) as CFData) else { return nil }
        return CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 8, bytesPerRow: w,
                       space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }

    /// A graphic with real transparency: colour from the picture, opacity
    /// from its alpha. Never writes depth.
    static func overlay(_ img: CGImage, opacity: Double) -> UnlitMaterial? {
        guard let colour = StadiumText.texture(img), let maskImg = alphaMask(img),
              let mask = try? TextureResource(image: maskImg, options: .init(semantic: .raw)) else { return nil }
        var m = UnlitMaterial(applyPostProcessToneMap: false)
        m.color = .init(tint: .white, texture: StadiumLook.clamped(colour))
        m.blending = .transparent(opacity: .init(scale: Float(opacity), texture: StadiumLook.clamped(mask)))
        m.writesDepth = false
        m.faceCulling = .none
        return m
    }

    /// Light in the air from a coloured picture: the stadium's glow material
    /// with the picture's alpha as its opacity.
    static func light(_ img: CGImage, opacity: Double) -> UnlitMaterial? {
        guard let colour = StadiumText.texture(img), let maskImg = alphaMask(img),
              let mask = try? TextureResource(image: maskImg, options: .init(semantic: .raw)) else { return nil }
        var m = StadiumLook.glow("#FFFFFF", opacity: opacity, texture: colour)
        m.blending = .transparent(opacity: .init(scale: 1, texture: StadiumLook.clamped(mask)))
        return m
    }

    /// The ribbon's crawl: both chips and scores, the clock and the down, with
    /// capital letters `textShare` of the board's height (the legibility rule
    /// in `visual.broadcast.ribbon`).
    static func ribbon(_ s: SceneSpec, look: SceneSpec.Look, segmentYards: Double? = nil) -> CGImage? {
        let r = look.broadcast.ribbon
        let h = r.heightPixels
        let rise = (s.bowl.ribbon?.rise[1] ?? 23.6) - (s.bowl.ribbon?.rise[0] ?? 21)
        let w = h * Int(((segmentYards ?? r.segmentYards) / max(0.1, rise)).rounded())
        return image(width: max(256, w), height: h, opaque: true) { ctx, size in
            StadiumLook.color(s.palette[s.bowl.ribbon?.color ?? ""] ?? "#05060A").setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            let ink = StadiumLook.color(s.palette[s.bowl.ribbon?.text ?? ""] ?? "#F7F6F2")
            let text = size.height * CGFloat(r.textShare)
            let big = UIFont.systemFont(ofSize: text, weight: .black)
            var parts = [s.status.label, s.status.downDistance].filter { !$0.isEmpty }
            if s.status.redZone { parts.append("RED ZONE") }
            // The segment repeats round the bowl, so whatever runs past its end
            // is cut mid-word ("2ND & 6 A"). Measure first: the clock and the
            // down narrow toward `fitFloor` of their size, and only then does
            // the red-zone word go (the down turns red on the video board too).
            let chips = size.height * (0.5 + 2 * (1.7 + 0.3 + 0.8)) + 2 * NSAttributedString(string: "00",
                attributes: [.font: big]).size().width
            func tailWidth(_ list: [String], _ scale: CGFloat) -> CGFloat {
                let f = UIFont.systemFont(ofSize: text * 0.82 * scale, weight: .heavy)
                return list.reduce(0) { $0 + NSAttributedString(string: $1.uppercased(),
                    attributes: [.font: f, .kern: text * 0.04 * scale]).size().width + size.height * 0.9 }
            }
            let room = size.width - chips
            var scale: CGFloat = 1
            while tailWidth(parts, scale) > room, parts.count > 2 || scale > CGFloat(r.fitFloor) {
                if scale > CGFloat(r.fitFloor) { scale = max(CGFloat(r.fitFloor), scale - 0.04) } else { parts.removeLast() }
            }
            let mid = UIFont.systemFont(ofSize: text * 0.82 * scale, weight: .heavy)
            var x: CGFloat = size.height * 0.5
            func chip(_ t: SceneSpec.Team, _ score: Double) {
                // "#16" before the chip, small: a Saturday's ribbon says who is
                // ranked, and the crawl has room for two characters more.
                if let rank = t.rank {
                    let r = NSAttributedString(string: "#\(rank)", attributes: [
                        .font: UIFont.systemFont(ofSize: text * 0.5, weight: .heavy),
                        .foregroundColor: ink.withAlphaComponent(0.85)])
                    r.draw(at: CGPoint(x: x, y: (size.height - r.size().height) / 2))
                    x += r.size().width + size.height * 0.16
                }
                let rect = CGRect(x: x, y: size.height * 0.1, width: size.height * 1.7, height: size.height * 0.8)
                StadiumLook.color(t.chip).setFill()
                UIBezierPath(roundedRect: rect, cornerRadius: size.height * 0.1).fill()
                let abbr = NSAttributedString(string: t.abbr, attributes: [.font: UIFont.systemFont(ofSize: text * 0.8, weight: .black),
                                                                           .foregroundColor: UIColor.white])
                let ab = abbr.size()
                abbr.draw(at: CGPoint(x: rect.midX - ab.width / 2, y: rect.midY - ab.height / 2))
                x = rect.maxX + size.height * 0.3
                let n = NSAttributedString(string: "\(Int(score))", attributes: [.font: big, .foregroundColor: ink])
                n.draw(at: CGPoint(x: x, y: (size.height - n.size().height) / 2))
                x += n.size().width + size.height * 0.8
            }
            chip(s.teams.away, s.status.awayScore)
            chip(s.teams.home, s.status.homeScore)
            for (i, p) in parts.enumerated() {
                if i > 0 {
                    let dot = CGRect(x: x - size.height * 0.45, y: size.height * 0.44, width: size.height * 0.12, height: size.height * 0.12)
                    ink.withAlphaComponent(0.6).setFill()
                    UIBezierPath(ovalIn: dot).fill()
                }
                let t = NSAttributedString(string: p.uppercased(), attributes: [.font: mid, .foregroundColor: ink, .kern: text * 0.04 * scale])
                t.draw(at: CGPoint(x: x, y: (size.height - t.size().height) / 2))
                x += t.size().width + size.height * 0.9
            }
        }
    }

    /// A moment across the whole board: the word, repeated, on the side's chip.
    ///
    /// The image is one tile of a board that repeats round the bowl, so the
    /// words must tile with it: as many whole words as fit, spaced evenly
    /// across the tile with a divider after each. Drawn until the edge
    /// instead, the last word was cut and met the next tile's first -
    /// "TOUCHD TOUCHDOWN" (integration-11).
    static func flash(_ word: String, chip: String, s: SceneSpec, look: SceneSpec.Look, segmentYards: Double? = nil) -> CGImage? {
        let r = look.broadcast.ribbon
        let h = r.heightPixels
        let rise = (s.bowl.ribbon?.rise[1] ?? 23.6) - (s.bowl.ribbon?.rise[0] ?? 21)
        let w = max(256, h * Int(((segmentYards ?? r.segmentYards) / max(0.1, rise)).rounded()))
        return image(width: w, height: h, opaque: true) { ctx, size in
            StadiumLook.color(chip).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            var text = size.height * CGFloat(r.textShare)
            func make(_ pt: CGFloat) -> NSAttributedString {
                NSAttributedString(string: word, attributes: [.font: UIFont.systemFont(ofSize: pt, weight: .black),
                                                             .foregroundColor: UIColor.white, .kern: pt * 0.12])
            }
            var t = make(text)
            let gap = size.height * 1.2
            // A word longer than the tile narrows until one fits whole.
            while t.size().width + gap > size.width, text > 4 {
                text *= 0.95
                t = make(text)
            }
            let count = max(1, Int(size.width / (t.size().width + gap)))
            let pitch = size.width / CGFloat(count)
            for i in 0..<count {
                let x = CGFloat(i) * pitch + (pitch - t.size().width - gap) / 2 + gap / 2
                t.draw(at: CGPoint(x: x, y: (size.height - t.size().height) / 2))
                UIColor.white.withAlphaComponent(0.55).setFill()
                ctx.fill(CGRect(x: CGFloat(i + 1) * pitch - size.height * 0.03, y: size.height * 0.2,
                                width: size.height * 0.06, height: size.height * 0.6))
            }
        }
    }

    /// "3RD & 6" as a broadcast paints it on the grass: bold white on a dark
    /// translucent plate, so it reads over stripes and paint alike.
    static func tag(_ text: String, look: SceneSpec.Look.LineTag) -> CGImage? {
        let h = CGFloat(max(48, look.pixels))
        let font = UIFont.systemFont(ofSize: h * 0.62, weight: .black)
        let t = NSAttributedString(string: text.uppercased(), attributes: [.font: font, .foregroundColor: UIColor.white, .kern: h * 0.03])
        let w = t.size().width + h * 0.7
        return image(width: Int(w), height: Int(h), opaque: false) { ctx, size in
            ctx.clear(CGRect(origin: .zero, size: size))
            UIColor(white: 0.02, alpha: 0.55).setFill()
            UIBezierPath(roundedRect: CGRect(origin: .zero, size: size).insetBy(dx: h * 0.04, dy: h * 0.1),
                         cornerRadius: h * 0.18).fill()
            t.draw(at: CGPoint(x: (size.width - t.size().width) / 2, y: (size.height - t.size().height) / 2))
        }
    }
}

/// The ribbon board round the upper deck's fascia (Bowl builds the fascia;
/// this is what it shows): a slowly drifting crawl, taken over by a flash
/// when something happens. Stadium only - the table has no upper deck.
@MainActor
final class BroadcastRibbon {
    let root = Entity()
    private var entity: ModelEntity?
    private var texture: TextureResource?
    private var material: UnlitMaterial?
    private var crawlKey = ""
    private var offset: Float = 0
    private var flashUntil: Double = 0
    private var flashing = false
    /// The crawl's tile length, stretched so a whole number of tiles fits the
    /// ring. With a remainder, the texture jumped where the ring closes and
    /// one word read cut in half there - "REDNE" (integration-11).
    private var segment: Double = 60

    init() { root.name = "broadcast.ribbon" }

    func build(_ c: StadiumContext) {
        root.children.removeAll()
        entity = nil
        texture = nil
        material = nil
        crawlKey = ""
        flashUntil = 0
        flashing = false
        let s = c.spec
        guard let band = s.bowl.ribbon, c.tiers.count > 1 else { return }
        let shape = s.bowl.shape
        let S = c.look.broadcast.ribbon.segments
        let angles = (0...S).map { Double($0) / Double(S) * 2 * .pi }
        var mesh = MeshBuilder()
        var run: Float = 0
        // In front of Bowl's screen, not on it. Bowl's fascia carries a dark
        // screen at exactly `band.offset`, tessellated to within 0.1 yd of the
        // true curve, and a crawl on the same surface z-fought it into
        // patches all round the bowl. Pushed toward the field along the
        // fascia's normal by more than that chord error, and cut finely
        // enough that its own chords stay close to the curve.
        let push = c.look.broadcast.ribbon.offset
        func point(_ t: Double) -> (x: Double, z: Double) {
            let p = SceneMath.bowlPoint(shape, offset: band.offset, angle: t)
            let n = SceneMath.inward(shape, offset: band.offset, angle: t)
            return (p.x + n.x * push, p.z + n.y * push)
        }
        var ring = 0.0
        for k in 0..<S {
            let a = point(angles[k]), b = point(angles[k + 1])
            ring += hypot(b.x - a.x, b.z - a.z)
        }
        let want = c.look.broadcast.ribbon.segmentYards
        self.segment = ring / max(1, (ring / max(1, want)).rounded())
        let segment = Float(self.segment)
        for k in 0..<S {
            let r0 = point(angles[k])
            let r1 = point(angles[k + 1])
            let seg = Float(hypot(r1.x - r0.x, r1.z - r0.z))
            let v0 = run / segment, v1 = (run + seg) / segment
            run += seg
            let rb = Float(band.rise[0]), rt = Float(band.rise[1])
            mesh.quad(SIMD3(Float(r0.x), rb, Float(r0.z)), SIMD3(Float(r1.x), rb, Float(r1.z)),
                      SIMD3(Float(r1.x), rt, Float(r1.z)), SIMD3(Float(r0.x), rt, Float(r0.z)),
                      uv: (SIMD2(v0, 0), SIMD2(v1, 0), SIMD2(v1, 1), SIMD2(v0, 1)))
        }
        let tex = StadiumText.texture(BroadcastGraphics.ribbon(s, look: c.look, segmentYards: self.segment))
        texture = tex
        crawlKey = StadiumText.ribbonKey(s)
        let m: UnlitMaterial = tex.map { StadiumLook.emissive("#FFFFFF", scale: 1.0, texture: $0) }
            ?? StadiumLook.emissive(s.palette[band.color] ?? "#05060A")
        material = m
        let e = mesh.entity("ribbon", m)
        entity = e
        root.addChild(e)
    }

    /// A new scene: redraw the crawl if what it says changed, unless a flash holds.
    func apply(_ c: StadiumContext, previous: SceneSpec?) {
        let s = c.spec
        if let p = previous, firstDown(s, previous: p) {
            flash(c.look.broadcast.ribbon.flash.words["firstDown"], chip: side(s, s.status.possession), c)
        }
        guard !flashing, let tex = texture else { return }
        let k = StadiumText.ribbonKey(s)
        guard k != crawlKey else { return }
        crawlKey = k
        if let img = BroadcastGraphics.ribbon(s, look: c.look, segmentYards: segment) {
            try? tex.replace(withImage: img, options: .init(semantic: .color))
        }
    }

    func moment(_ event: StadiumEvent, _ c: StadiumContext) {
        let words = c.look.broadcast.ribbon.flash.words
        switch event {
        case .moment(let m):
            flash(words[m.kind], chip: side(c.spec, m.side), c)
        case .redZoneEntered:
            flash(words["redZone"], chip: c.spec.palette["fill.redZone"] ?? "#B3261E", c)
        case .cue(let q):
            // A cue with no word in `ribbon.flash.words` leaves the crawl alone.
            flash(words[q.kind], chip: side(c.spec, q.side), c)
        }
    }

    func update(_ frame: StadiumFrame, _ c: StadiumContext) {
        guard let e = entity, var m = material else { return }
        if flashing, frame.time >= flashUntil {
            flashing = false
            crawlKey = ""
            apply(c, previous: nil)
        }
        guard !c.reduceMotion else { return }
        let r = c.look.broadcast.ribbon
        offset = (offset + Float(r.scroll.yardsPerSecond * frame.dt / segment)).truncatingRemainder(dividingBy: 1)
        m.textureCoordinateTransform.offset = SIMD2(-offset, 0)
        material = m
        e.model?.materials = [m]
    }

    private func flash(_ word: String?, chip: String, _ c: StadiumContext) {
        guard let word, let tex = texture,
              let img = BroadcastGraphics.flash(word, chip: chip, s: c.spec, look: c.look, segmentYards: segment) else { return }
        try? tex.replace(withImage: img, options: .init(semantic: .color))
        flashing = true
        flashUntil = c.shared.time + c.look.broadcast.ribbon.flash.seconds
    }

    private func side(_ s: SceneSpec, _ side: String?) -> String {
        side == "away" ? s.teams.away.chip : s.teams.home.chip
    }

    /// A first down gained by the same offense, not a new drive's first snap.
    private func firstDown(_ s: SceneSpec, previous p: SceneSpec) -> Bool {
        s.status.state == "in" && p.status.state == "in" && s.status.down == 1 && p.status.down != nil
            && p.status.down != 1 && s.status.possession != nil && s.status.possession == p.status.possession
            && s.activeMoment == nil
    }
}
