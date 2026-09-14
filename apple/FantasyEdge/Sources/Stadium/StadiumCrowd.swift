import RealityKit
import UIKit
import simd

/// The crowd: cut-out fans on every row, dressed in the two clubs' colours.
///
/// One atlas per pair of clubs, composed once from the mask in `assets/src`:
/// four blocks - home shirts, away shirts, neutral, dark - each the mask's
/// figures with their own skin, hair and a shade of shirt, so a section is a
/// mottled mass rather than a flat colour. Every fan is two cards back to
/// back: the front faces the field, and the back - the same figure with its
/// head turned away - is what the wearer sees of the rows in front of them.
///
/// Fans are grouped into angular slices per section so a wave can travel and
/// a section can rise, and shared materials are all a moment has to swap.
@MainActor
final class StadiumCrowd {
    struct Group {
        let entity: Entity
        let front: ModelEntity
        let back: ModelEntity
        let slice: Int
        let away: Bool
    }

    private struct Materials {
        let normal: UnlitMaterial
        let dim: UnlitMaterial
        let bright: UnlitMaterial
    }

    let root = Entity()
    private(set) var groups: [Group] = []
    private(set) var fans = 0
    private var front: Materials?
    private var back: Materials?
    private var tint: String? = "unset"
    private var surge: (away: Bool, until: Double)?
    private var time: Double = 0

    init(_ s: SceneSpec, look: SceneSpec.Look, assets: StadiumAssets, tiers: [SceneSpec.Tier], tabletop: Bool) {
        root.name = "crowd"
        let C = look.crowd
        guard let mask = assets.images["crowd"],
              let frontImage = Self.compose(mask, s: s, look: look, back: false),
              let backImage = Self.compose(mask, s: s, look: look, back: true),
              let frontTexture = StadiumText.texture(frontImage),
              let backTexture = StadiumText.texture(backImage) else { return }
        func materials(_ t: TextureResource) -> Materials {
            Materials(normal: StadiumLook.crowd(t, tint: C.tint.normal),
                      dim: StadiumLook.crowd(t, tint: C.tint.dim),
                      bright: StadiumLook.crowd(t, tint: C.tint.bright))
        }
        let frontM = materials(frontTexture), backM = materials(backTexture)
        front = frontM
        back = backM

        struct Rng {
            var s: UInt64
            mutating func next() -> Double {
                s = s &* 6364136223846793005 &+ 1442695040888963407
                return Double(s >> 11) / Double(1 << 53)
            }
        }
        var rng = Rng(s: C.seed)
        let shape = s.bowl.shape
        let perRow = C.seatsPerRow.value(tabletop: tabletop)
        let size = C.fanYards.value(tabletop: tabletop)
        let fw = Float(size[0] / 2), fh = Float(size[1])
        let cols = C.atlas.columns, rowsA = C.atlas.rows
        let slices = max(1, C.slices)
        let away = s.bowl.crowd.awaySection
        var builders: [String: (front: MeshBuilder, back: MeshBuilder)] = [:]
        // Every seat a wearer can take, so the crowd leaves them room.
        let seats = (s.presentation.stadium.seats ?? []).map { SceneMath.local(x: $0.x, y: $0.y, z: $0.z) }
        let clear = Float(C.clearance.radius), clearHeight = Float(C.clearance.height)

        for tier in tiers {
            let rows = look.bowl.rows[tier.name] ?? 20
            // On the table every other row is enough to read as full.
            let step = tabletop ? 2 : 1
            for r in stride(from: 0, to: rows, by: step) {
                let row = SceneMath.row(tier, r, of: rows)
                let m = row.front + (row.back - row.front) * 0.45
                let (angles, _) = SceneMath.evenAngles(shape, offset: m, count: perRow)
                for t in angles {
                    guard rng.next() < C.fill else { continue }
                    if tabletop && StadiumBowl.cut(t, t, look) { continue }
                    let p = SceneMath.bowlPoint(shape, offset: m, angle: t)
                    if !tabletop && seats.contains(where: { seat in
                        hypot(Float(p.x) - seat.x, Float(p.z) - seat.z) < clear && abs(Float(row.tread) - seat.y) < clearHeight
                    }) { continue }
                    let n = SceneMath.inward(shape, offset: m, angle: t)
                    let isAway = away.map { a in
                        (a.side == "far" ? p.z < 0 : p.z > 0) && p.x >= a.fromX - 50
                    } ?? false
                    // Which block of the atlas dresses this fan.
                    let roll = rng.next()
                    let block: Int
                    if roll < C.shirts.team { block = isAway ? 1 : 0 }
                    else if roll < C.shirts.team + C.shirts.neutral { block = 2 }
                    else { block = 3 }
                    let standing = rng.next() < C.standingShare
                    let cellRow = standing ? C.atlas.armsUpFromRow + Int(rng.next() * Double(rowsA - C.atlas.armsUpFromRow))
                                           : Int(rng.next() * Double(C.atlas.armsUpFromRow))
                    let cellCol = Int(rng.next() * Double(cols))
                    let bx = Float(block % 2), by = Float(block / 2)
                    let cu = (bx + (Float(cellCol) + 0.04) / Float(cols)) / 2
                    let cu1 = (bx + (Float(cellCol) + 0.96) / Float(cols)) / 2
                    let cv0 = (by + Float(cellRow) / Float(rowsA)) / 2
                    let cv1 = (by + Float(cellRow + 1) / Float(rowsA)) / 2
                    let jitter = Float(rng.next() - 0.5) * fw * 2 * Float(C.sideJitter)
                    let side = SIMD3<Float>(-Float(n.y), 0, Float(n.x))
                    let base = SIMD3(Float(p.x), Float(row.tread), Float(p.z)) + side * jitter
                    let scale = Float(1 - C.scaleJitter + rng.next() * 2 * C.scaleJitter)
                    let a = base - side * fw * scale, b = base + side * fw * scale
                    let up = SIMD3<Float>(0, fh * scale, 0)
                    let slice = min(slices - 1, Int(t / (2 * .pi) * Double(slices)))
                    let key = "\(slice)|\(isAway)"
                    var pair = builders[key] ?? (MeshBuilder(), MeshBuilder())
                    let facing = SIMD3(Float(n.x), 0, Float(n.y))
                    // v runs up the image, so the head (cv0) is at the top of the card.
                    // Seen from the field, `b` is on the left: the front card
                    // winds b-a so its face turns to the field.
                    pair.front.quad(b, a, a + up, b + up,
                                    uv: (SIMD2(cu, 1 - cv1), SIMD2(cu1, 1 - cv1), SIMD2(cu1, 1 - cv0), SIMD2(cu, 1 - cv0)),
                                    normal: facing)
                    // The back card winds the other way, so it shows only from behind.
                    pair.back.quad(a, b, b + up, a + up,
                                   uv: (SIMD2(cu, 1 - cv1), SIMD2(cu1, 1 - cv1), SIMD2(cu1, 1 - cv0), SIMD2(cu, 1 - cv0)),
                                   normal: -facing)
                    builders[key] = pair
                    fans += 1
                }
            }
        }
        for (key, pair) in builders.sorted(by: { $0.key < $1.key }) {
            let parts = key.split(separator: "|")
            let holder = Entity()
            holder.name = "crowd.\(key)"
            let f = pair.front.entity("crowd.front", frontM.normal)
            let b = pair.back.entity("crowd.back", backM.normal)
            holder.addChild(f)
            holder.addChild(b)
            root.addChild(holder)
            groups.append(Group(entity: holder, front: f, back: b, slice: Int(parts[0]) ?? 0, away: parts[1] == "true"))
        }
    }

    /// The atlas the fans wear: the mask's channels mixed into shirt, skin and
    /// hair, one block per kind of fan. Each figure's shirt takes its own shade
    /// and, for club shirts, sometimes the raw club colour instead of the chip.
    /// `back` turns every head away: skin above the shoulders becomes hair.
    static func compose(_ mask: CGImage, s: SceneSpec, look: SceneSpec.Look, back: Bool) -> CGImage? {
        let C = look.crowd
        let cw = C.atlas.cellPixels[0], ch = C.atlas.cellPixels[1]
        let W = cw * C.atlas.columns, H = ch * C.atlas.rows
        let space = CGColorSpaceCreateDeviceRGB()
        guard let src = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4,
                                  space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        src.interpolationQuality = .high
        src.draw(mask, in: CGRect(x: 0, y: 0, width: W, height: H))
        guard let m = src.data?.assumingMemoryBound(to: UInt8.self) else { return nil }
        let OW = W * 2, OH = H * 2
        guard let dst = CGContext(data: nil, width: OW, height: OH, bitsPerComponent: 8, bytesPerRow: OW * 4,
                                  space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
              let d = dst.data?.assumingMemoryBound(to: UInt8.self) else { return nil }
        func rgb(_ hex: String) -> SIMD3<Double> {
            let c = SceneMath.rgba(hex)
            return SIMD3(Double(c.x), Double(c.y), Double(c.z))
        }
        let chips = [rgb(s.bowl.crowd.home), rgb(s.bowl.crowd.away),
                     rgb(s.palette[s.bowl.crowd.neutral] ?? "#A39E94"), rgb(s.palette[s.bowl.crowd.dark] ?? "#3E424A")]
        let raws = [rgb(s.teams.home.color), rgb(s.teams.away.color), chips[2], chips[3]]
        let skins = C.skin.map(rgb), hairs = C.hair.map(rgb)
        let shade = C.shirtShade
        for block in 0..<4 {
            let ox = (block % 2) * W
            // Bitmap memory runs top-down: blocks 0 and 1 are the top half.
            let oy = (block / 2) * H
            for y in 0..<H {
                for x in 0..<W {
                    let si = (y * W + x) * 4
                    let a = Double(m[si + 3]) / 255
                    let di = ((oy + y) * OW + ox + x) * 4
                    guard a > 0.01 else { d[di] = 0; d[di + 1] = 0; d[di + 2] = 0; d[di + 3] = 0; continue }
                    let cell = (x / cw) + (y / ch) * 7
                    var h = UInt64(cell * 2654435761 + block * 40503)
                    h ^= h >> 13
                    let r1 = Double(h % 1000) / 1000, r2 = Double((h / 1000) % 1000) / 1000
                    let skin = skins[cell % max(1, skins.count)]
                    let hair = hairs[(cell * 3 + 1) % max(1, hairs.count)]
                    let shirt = (r2 < C.rawShare ? raws[block] : chips[block]) * (shade[0] + (shade[1] - shade[0]) * r1)
                    let wr = Double(m[si]) / 255 / a
                    var wg = Double(m[si + 1]) / 255 / a, wb = Double(m[si + 2]) / 255 / a
                    if back && y % ch < ch * 45 / 100 {
                        wb += wg
                        wg = 0
                    }
                    let total = max(1e-6, wr + wg + wb)
                    // A little light from above on every figure, so a card reads as a body.
                    let lit = 1.12 - 0.24 * Double(y % ch) / Double(ch)
                    var c = (shirt * wr + skin * wg + hair * wb) / total * lit
                    c = SIMD3(min(1, c.x), min(1, c.y), min(1, c.z))
                    d[di] = UInt8(c.x * a * 255); d[di + 1] = UInt8(c.y * a * 255)
                    d[di + 2] = UInt8(c.z * a * 255); d[di + 3] = UInt8(a * 255)
                }
            }
        }
        return dst.makeImage()
    }

    // MARK: moments

    /// Light the scoring side's section and dim the rest, from the scene's
    /// section tint. Materials change only when the tint does.
    func applyTint(_ s: SceneSpec) {
        let side = s.bowl.sectionTint.side
        guard side != tint, let front, let back else { return }
        tint = side
        for g in groups {
            let pick: (Materials) -> UnlitMaterial = { set in
                guard let side else { return set.normal }
                return (side == "away") == g.away ? set.bright : set.dim
            }
            g.front.model?.materials = [pick(front)]
            g.back.model?.materials = [pick(back)]
        }
    }

    func celebrate(side: String, seconds: Double) {
        surge = (side == "away", time + seconds)
    }

    /// Idle breathing, a slow wave, and the surge of a scoring section.
    func tick(_ dt: Double, look: SceneSpec.Look, reduceMotion: Bool) {
        time += dt
        let C = look.crowd
        guard !reduceMotion else {
            for g in groups where g.entity.position.y != 0 { g.entity.position.y = 0 }
            return
        }
        let slices = Double(max(1, C.slices))
        let wavePhase = (time / max(1, C.waveSeconds)).truncatingRemainder(dividingBy: 3)
        let surging = surge.map { time < $0.until } ?? false
        for g in groups {
            let a = (Double(g.slice) + 0.5) / slices
            var y = C.bobYards * sin(time * 2 * .pi * C.bobHz + Double(g.slice) * 1.7)
            if wavePhase < 1 {
                let dist = min(abs(a - wavePhase), 1 - abs(a - wavePhase))
                y += C.surgeYards * 0.6 * exp(-(dist * dist) / max(1e-6, 2 * C.waveWidth * C.waveWidth))
            }
            if surging, let surge, surge.away == g.away {
                y += C.surgeYards * 0.5 * (1 + sin(time * 2 * .pi * C.surgeHz + Double(g.slice)))
            }
            g.entity.position.y = Float(y)
        }
    }
}
