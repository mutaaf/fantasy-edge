import SwiftUI

/// ESPN Fantasy's identity, and where it is allowed to appear.
///
/// The palette below is ESPN's own, and ESPN picked it for a deep navy page.
/// This app draws on `glassBackgroundEffect`, which is translucent over
/// whatever room the wearer is in - and the app cannot see the room. Measured
/// against a bright one (`apple/contrast_check.py`, backdrop sampled off a
/// real headset screenshot) not one of these hues clears even the 3:1 floor
/// for large text: gold came out at 1.02:1, which is invisible, and the best
/// of them at 2.69:1. They were legible in the dark room they were tested in
/// and vanished in a bright one.
///
/// So the rule this file exists to enforce: **text wears text ink; colour
/// rides on a mark beside it.** Values, names and labels take
/// primary/secondary/tertiary, which the system re-derives against whatever is
/// actually behind the glass. Identity and status are carried by a filled chip
/// or dot, and where a chip has text on it the fill is *opaque*, so that text
/// sits on a ground this code chose rather than on the wearer's living room.
///
/// The `*Fill` values are the same hues taken to the one luminance band where
/// white text on them clears 4.5:1 and the chip's own edge clears 3:1 against
/// both a bright room and a dark one. That band is 0.135 to 0.183 relative
/// luminance and it is narrow; the numbers are computed by
/// `python3 apple/contrast_check.py --propose`, not chosen by eye, and the
/// same script re-reads this file to check they are still in it.
enum Theme {
    static let navy   = Color(red: 0.039, green: 0.102, blue: 0.373)
    static let navyUp = Color(red: 0.086, green: 0.188, blue: 0.498)

    // The brand hues. Still the product's colours, and still correct for a
    // bar, a ring, a wash or a border - anything whose job is a shape rather
    // than a glyph. Never `foregroundStyle` on text drawn straight onto glass.
    static let green  = Color(red: 0.357, green: 0.761, blue: 0.212)
    static let red    = Color(red: 1.000, green: 0.294, blue: 0.294)
    static let gold   = Color(red: 1.000, green: 0.831, blue: 0.000)

    // The same three, opaque, for a chip with words on it. Spread across the
    // legal band darkest-to-lightest as well as by hue, because ahead, caution
    // and behind are the one triple a reader must never confuse and hue alone
    // cannot carry that for a deuteranope. The glyph on the chip does the rest.
    static let greenFill = Color(red: 0.136, green: 0.476, blue: 0.014)
    static let redFill   = Color(red: 0.875, green: 0.044, blue: 0.044)
    static let goldFill  = Color(red: 0.544, green: 0.452, blue: 0.000)

    /// ESPN's own position colours. A shape's colour, not a glyph's.
    static func position(_ pos: String) -> Color {
        switch pos.uppercased() {
        case "QB":  return Color(red: 0.973, green: 0.161, blue: 0.427)
        case "RB":  return Color(red: 0.212, green: 0.808, blue: 0.239)
        case "WR":  return Color(red: 0.345, green: 0.655, blue: 1.000)
        case "TE":  return Color(red: 1.000, green: 0.682, blue: 0.345)
        case "K":   return Color(red: 0.741, green: 0.400, blue: 1.000)
        default:    return Color(red: 0.690, green: 0.718, blue: 0.765)
        }
    }

    /// The same six, opaque, for the chip a position is actually written on.
    ///
    /// A position chip carries its own letters, so the hue here is identity
    /// rather than the thing being read - which is what makes it safe that
    /// RB green and DEF slate converge for a deuteranope. All six sit at one
    /// luminance so a row of them reads as a set. D/ST keeps its near-neutral:
    /// pushing saturation to the maximum would have made it a vivid blue and
    /// given it a colour it has never had, next to the one WR already uses.
    static func positionFill(_ pos: String) -> Color {
        switch pos.uppercased() {
        case "QB":  return Color(red: 0.869, green: 0.000, blue: 0.285)
        case "RB":  return Color(red: 0.010, green: 0.509, blue: 0.033)
        case "WR":  return Color(red: 0.082, green: 0.432, blue: 0.821)
        case "TE":  return Color(red: 0.649, green: 0.366, blue: 0.065)
        case "K":   return Color(red: 0.628, green: 0.149, blue: 0.992)
        default:    return Color(red: 0.369, green: 0.440, blue: 0.559)
        }
    }

    static func side(_ s: String) -> Color { s == "you" ? green : red }
    static func sideFill(_ s: String) -> Color { s == "you" ? greenFill : redFill }

    /// Any hue at all, taken to the luminance the fixed fills sit at.
    ///
    /// A fantasy team's badge is coloured by a hash of its name, so the hue is
    /// not known when this file is written and cannot be hand-tuned the way
    /// the tokens above are. Solving for the brightness that lands the hue in
    /// the band means a white monogram clears 4.5:1 whatever name hashed to
    /// it - which the old `brightness: 0.85` did not: a yellow team came out
    /// at 1.8:1 and its initials were unreadable.
    static func chipFill(hue: Double, saturation: Double = 0.62,
                         target: Double = 0.159) -> Color {
        func lin(_ c: Double) -> Double {
            c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        func hsv(_ v: Double) -> (Double, Double, Double) {
            let h = (hue.truncatingRemainder(dividingBy: 1) + 1)
                .truncatingRemainder(dividingBy: 1) * 6
            let i = floor(h), f = h - i
            let p = v * (1 - saturation)
            let q = v * (1 - saturation * f)
            let t = v * (1 - saturation * (1 - f))
            switch Int(i) % 6 {
            case 0: return (v, t, p)
            case 1: return (q, v, p)
            case 2: return (p, v, t)
            case 3: return (p, q, v)
            case 4: return (t, p, v)
            default: return (v, p, q)
            }
        }
        func lum(_ v: Double) -> Double {
            let (r, g, b) = hsv(v)
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
        }
        var lo = 0.0, hi = 1.0
        for _ in 0..<24 {
            let m = (lo + hi) / 2
            if lum(m) < target { lo = m } else { hi = m }
        }
        let (r, g, b) = hsv((lo + hi) / 2)
        return Color(red: r, green: g, blue: b)
    }

    /// What a colour on this surface is allowed to mean, and the glyph that
    /// means it without the colour.
    ///
    /// The pairing is the point. Ahead and behind were a green number and a
    /// red number, which is two failures at once: neither was legible on a
    /// bright room, and the two are the classic pair a red-green colourblind
    /// reader cannot separate. An arrow up and an arrow down are separable by
    /// anybody, in any room, and the colour is then reinforcement rather than
    /// the message.
    enum Mark: Hashable {
        case ahead, behind, level, caution, live, hurt

        var fill: Color {
            switch self {
            case .ahead:   return greenFill
            case .behind:  return redFill
            case .hurt:    return redFill
            case .caution: return goldFill
            case .level:   return goldFill
            case .live:    return greenFill
            }
        }
        var symbol: String {
            switch self {
            case .ahead:   return "arrow.up"
            case .behind:  return "arrow.down"
            case .level:   return "equal"
            case .caution: return "exclamationmark"
            case .live:    return "dot.radiowaves.left.and.right"
            case .hurt:    return "cross.case.fill"
            }
        }
        /// Ahead or behind from a signed figure, so no call site decides it
        /// twice and gets a zero pointing the wrong way.
        static func of(_ value: Double, level band: Double = 0.05) -> Mark {
            if abs(value) < band { return .level }
            return value > 0 ? .ahead : .behind
        }
    }
}

extension Band {
    /// How much room a cell gets. The model decides the band; this is only how
    /// a band becomes a size, and it is shared by the window and the volume.
    var span: (w: CGFloat, h: CGFloat) {
        switch self {
        case .xl: return (330, 215)
        case .lg: return (270, 180)
        case .md: return (240, 152)
        case .sm: return (210, 128)
        }
    }
    /// In the immersive space, importance is depth: a cell that still matters
    /// stands forward, a decided one falls back.
    var depth: Float {
        switch self {
        case .xl: return 0.20
        case .lg: return 0.06
        case .md: return -0.10
        case .sm: return -0.26
        }
    }
}
