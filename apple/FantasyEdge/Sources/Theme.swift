import SwiftUI

/// ESPN Fantasy's identity, the same values the web board uses.
enum Theme {
    static let navy   = Color(red: 0.039, green: 0.102, blue: 0.373)
    static let navyUp = Color(red: 0.086, green: 0.188, blue: 0.498)
    static let green  = Color(red: 0.357, green: 0.761, blue: 0.212)
    static let red    = Color(red: 1.000, green: 0.294, blue: 0.294)
    static let gold   = Color(red: 1.000, green: 0.831, blue: 0.000)

    /// ESPN's own position colours.
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
    static func side(_ s: String) -> Color { s == "you" ? green : red }
}

extension Band {
    /// How much room a cell gets. The model decides the band; this is only how
    /// a band becomes a size, and it is shared by the window and the volume.
    var span: (w: CGFloat, h: CGFloat) {
        switch self {
        case .xl: return (300, 210)
        case .lg: return (240, 165)
        case .md: return (200, 130)
        case .sm: return (150, 96)
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
