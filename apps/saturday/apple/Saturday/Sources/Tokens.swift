import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// INTEGRATE: design/tokens.json from fantasy-edge scene/replay branch.
// Every colour here is a value from design/build.py (itself Theme.swift's
// measured fills); at integration this enum reads the shared JSON instead and
// the literals go. Text is never coloured: it is system ink (.primary /
// .secondary). Colour lives on chips beside it.
enum Tokens {
    static let greenFill = Color(hex: "#237A04")
    static let redFill = Color(hex: "#DF0B0B")
    static let goldFill = Color(hex: "#8B7300")
    static let otFill = Color(hex: "#3B3F46")
    static let plate = Color(hex: "#121417").opacity(0.88)
    static let turfA = Color(hex: "#0E3A1F")
    static let turfB = Color(hex: "#124726")
    static let lineToGain = Color(hex: "#FFD400")
    static let scrimmage = Color(hex: "#58A7FF")
    static let liveGlyph = Color(hex: "#6BE04A")
    static let ball = Color(hex: "#7A3E17")
    static let lightBank = Color(hex: "#FFF4D6")

    /// Minimum hit target: 60 pt where you look and pinch, 44 pt where you tap.
    static var target: CGFloat {
        #if os(visionOS)
        60
        #else
        44
        #endif
    }
}

/// State glyphs. Colour is never the only signal: each state has one of these.
enum Glyph {
    static let live = "dot.radiowaves.left.and.right"
    static let possession = "football.fill"
    static let redZone = "arrow.right.to.line"
    static let upset = "bolt.fill"
    static let overtime = "clock.arrow.circlepath"
    static let delayed = "hourglass"
    static let final = "stop.circle"
    static let score = "flag.fill"
    static let turnover = "xmark"
    static let tabletop = "cube"
    static let stadium = "sportscourt"
    static let correction = "arrow.uturn.backward"
    static let lead = "arrow.up.forward"
    static let kickoff = "figure.american.football"
    static let resume = "play.fill"
    static let replay = "backward.end.alt"
    /// A moment nobody recorded, worked out afterwards from each play's stamp.
    static let rebuilt = "clock.arrow.2.circlepath"
    static let feed = "antenna.radiowaves.left.and.right"
    static let favorite = "star.fill"
    static let notFavorite = "star"
}

/// The three faces from the design system, with system fallbacks when a
/// bundled font fails to register - the layout must survive either.
enum Typeface {
    private static func available(_ postScript: String) -> Bool {
        #if canImport(UIKit)
        return UIFont(name: postScript, size: 12) != nil
        #else
        return false
        #endif
    }

    private static let hasDisplay = available("BigShouldersDisplay-Thin")
    private static let hasSans = available("InstrumentSans-Regular")
    private static let hasSerif = available("InstrumentSerif-Italic")

    static func display(_ size: CGFloat, _ weight: Font.Weight = .heavy) -> Font {
        hasDisplay ? .custom("Big Shoulders Display", size: size).weight(weight)
                   : .system(size: size, weight: weight).width(.condensed)
    }

    static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        hasSans ? .custom("Instrument Sans", size: size).weight(weight) : .system(size: size, weight: weight)
    }

    static func serif(_ size: CGFloat) -> Font {
        hasSerif ? .custom("InstrumentSerif-Italic", size: size) : .system(size: size, design: .serif).italic()
    }
}

extension Color {
    init(hex: String) {
        var value: UInt64 = 0
        Scanner(string: hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))).scanHexInt64(&value)
        self.init(red: Double((value >> 16) & 0xFF) / 255,
                  green: Double((value >> 8) & 0xFF) / 255,
                  blue: Double(value & 0xFF) / 255)
    }
}
