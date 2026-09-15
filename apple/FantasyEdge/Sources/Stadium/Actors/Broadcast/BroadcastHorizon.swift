import RealityKit
import UIKit
import simd

/// Win probability as one luminous band above the far rim
/// (`visual.broadcast.horizon`): it swells the more one side is favoured and
/// takes that side's colour, fades out at both ends, and ends in a glowing
/// marker at now with a single label beside it. No rails, no floating words.
@MainActor
final class BroadcastHorizon {
    let root = Entity()
    private var key = ""

    init() { root.name = "broadcast.horizon" }

    func clear() {
        root.children.removeAll()
        key = ""
    }

    func update(_ c: StadiumContext) {
        let s = c.spec, wp = s.winProbability
        let k = "\(wp.series.count)|\(wp.series.last ?? -1)|\(s.teams.home.chip)|\(s.teams.away.chip)|\(c.tabletop)"
        guard k != key else { return }
        key = k
        root.children.removeAll()
        let pts = SceneMath.horizon(wp)
        guard pts.count > 1 else { return }
        let look = c.look.broadcast.horizon
        let series = wp.series
        let homeSide = wp.side == "home"
        let thick = Float(look.thickness.value(tabletop: c.tabletop))

        // The band and its halo: one strip each, thickness per sample.
        func band(_ scale: Float) -> MeshBuilder {
            var b = MeshBuilder()
            let base = UInt32(0)
            for (i, p) in pts.enumerated() {
                let strength = Float(abs(series[i] - 0.5) * 2)
                let half = thick * scale / 2 * (1 + Float(look.swell) * strength)
                let u = Float(i) / Float(pts.count - 1)
                b.positions += [p - SIMD3(0, half, 0), p + SIMD3(0, half, 0)]
                b.normals += [SIMD3(0, 0, 1), SIMD3(0, 0, 1)]
                b.uvs += [SIMD2(u, 0), SIMD2(u, 1)]
            }
            for i in 0..<UInt32(pts.count - 1) {
                let a = base + i * 2
                b.indices += [a, a + 2, a + 1, a + 1, a + 2, a + 3]
            }
            return b
        }
        let image = Self.bandImage(series: series, homeSide: homeSide, home: s.teams.home.chip,
                                   away: s.teams.away.chip, ink: s.palette["ink"] ?? "#F7F6F2", look: look)
        let tex = StadiumText.texture(image)
        root.addChild(band(Float(look.haloScale)).entity("horizon.halo",
                                                          StadiumLook.glow("#FFFFFF", opacity: look.haloOpacity, texture: tex)))
        root.addChild(band(1).entity("horizon.band", StadiumLook.glow("#FFFFFF", opacity: look.opacity, texture: tex)))

        // Now: the marker at the last sample, and the one label beside it.
        guard let now = pts.last, let last = series.last else { return }
        let marker = ModelEntity(mesh: .generatePlane(width: Float(look.marker.yards.value(tabletop: c.tabletop)),
                                                      height: Float(look.marker.yards.value(tabletop: c.tabletop))),
                                 materials: [StadiumLook.glow(s.palette["ink"] ?? "#F7F6F2", opacity: look.marker.opacity,
                                                              texture: c.assets.texture("broadcast.marker"))])
        marker.name = "horizon.now"
        marker.position = now
        marker.components.set(BillboardComponent())
        root.addChild(marker)

        let favourHome = last >= 0.5
        let favoured = favourHome == homeSide ? s.teams.home : s.teams.away
        let share = favourHome == homeSide ? last : 1 - last
        if let label = Self.labelImage(team: favoured, percent: Int((share * 100).rounded()), look: look,
                                       ink: s.palette["ink"] ?? "#F7F6F2") {
            let h = Float(look.label.heightYards.value(tabletop: c.tabletop))
            let w = h * Float(label.width) / Float(max(1, label.height))
            var m = UnlitMaterial(applyPostProcessToneMap: false)
            if let t = StadiumText.texture(label) {
                m.color = .init(tint: UIColor(white: 1, alpha: 1), texture: StadiumLook.clamped(t))
                m.blending = .transparent(opacity: .init(scale: Float(look.label.opacity), texture: StadiumLook.clamped(t)))
            }
            m.writesDepth = false
            m.faceCulling = .none
            let plate = ModelEntity(mesh: .generatePlane(width: w, height: h), materials: [m])
            plate.name = "horizon.label"
            // A billboard pivots on its centre, so the label is its own
            // billboard beside the marker rather than a child offset from it.
            plate.position = now + SIMD3(Float(look.label.gapYards) + w / 2, 0, 0)
            plate.components.set(BillboardComponent())
            root.addChild(plate)
        }
    }

    /// The band's colour and softness, one column per stretch of the game:
    /// ink where the game was even, the favoured side's chip, lifted toward
    /// ink by `inkMix`, where it was not; gaussian across, faded at the ends.
    static func bandImage(series: [Double], homeSide: Bool, home: String, away: String, ink: String,
                          look: SceneSpec.Look.HorizonLook) -> CGImage? {
        let w = max(64, look.textureWidth), h = 32
        let inkC = SceneMath.rgba(ink), homeC = SceneMath.rgba(home), awayC = SceneMath.rgba(away)
        return BroadcastGraphics.image(width: w, height: h, opaque: false) { ctx, _ in
            ctx.clear(CGRect(x: 0, y: 0, width: w, height: h))
            for x in 0..<w {
                let u = Double(x) / Double(w - 1)
                let f = u * Double(series.count - 1)
                let i = min(series.count - 2, Int(f)), frac = f - Double(i)
                let p = series[i] * (1 - frac) + series[i + 1] * frac
                let strength = min(1, abs(p - 0.5) * 2 * 2.5)
                let favoursHome = (p >= 0.5) == homeSide
                let chip = favoursHome ? homeC : awayC
                let lifted = chip + (inkC - chip) * Float(look.inkMix)
                let col = inkC + (lifted - inkC) * Float(strength)
                let end = min(1, min(u, 1 - u) / max(1e-3, look.endFade))
                for y in 0..<h {
                    let cv = (Double(y) + 0.5) / Double(h) * 2 - 1
                    let a = exp(-cv * cv * 3.2) * end
                    ctx.setFillColor(red: CGFloat(col.x), green: CGFloat(col.y), blue: CGFloat(col.z), alpha: CGFloat(a))
                    ctx.fill(CGRect(x: x, y: y, width: 1, height: 1))
                }
            }
        }
    }

    /// "[CHI] 76%" with a small caption under it, on a transparent ground.
    static func labelImage(team: SceneSpec.Team, percent: Int, look: SceneSpec.Look.HorizonLook, ink: String) -> CGImage? {
        let h = CGFloat(max(48, look.label.pixels))
        let pctFont = UIFont.systemFont(ofSize: h * 0.62, weight: .heavy)
        let capFont = UIFont.systemFont(ofSize: h * 0.2, weight: .semibold)
        let chipFont = UIFont.systemFont(ofSize: h * 0.3, weight: .black)
        let inkColour = StadiumLook.color(ink)
        let pct = NSAttributedString(string: "\(percent)%", attributes: [.font: pctFont, .foregroundColor: inkColour])
        let cap = NSAttributedString(string: "WIN PROBABILITY", attributes: [.font: capFont, .foregroundColor: inkColour.withAlphaComponent(0.8), .kern: h * 0.02])
        let abbr = NSAttributedString(string: team.abbr, attributes: [.font: chipFont, .foregroundColor: UIColor.white])
        let chipW = abbr.size().width + h * 0.28
        let width = Int(chipW + h * 0.14 + max(pct.size().width, cap.size().width) + h * 0.1)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        let size = CGSize(width: width, height: Int(h))
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            let chipRect = CGRect(x: 0, y: h * 0.16, width: chipW, height: h * 0.44)
            StadiumLook.color(team.chip).setFill()
            UIBezierPath(roundedRect: chipRect, cornerRadius: h * 0.07).fill()
            let ab = abbr.size()
            abbr.draw(at: CGPoint(x: chipRect.midX - ab.width / 2, y: chipRect.midY - ab.height / 2))
            let x = chipW + h * 0.14
            pct.draw(at: CGPoint(x: x, y: -h * 0.06))
            cap.draw(at: CGPoint(x: x + h * 0.02, y: h * 0.7))
        }.cgImage
    }
}
