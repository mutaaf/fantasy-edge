import SwiftUI

/// The slanted broadcast slab. The fill arrives normalised from the API, so
/// white text on it clears 4.5:1 for every team; a hatch marks the away side
/// when both teams wear the same colour.
struct TeamChip: View {
    let abbr: String
    let fill: String
    var hatch = false
    var width: CGFloat = 60
    var height: CGFloat = 28
    var fontSize: CGFloat = 17

    var body: some View {
        Text(abbr)
            .font(Typeface.display(fontSize, .heavy))
            .tracking(0.6)
            .foregroundStyle(.white)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .padding(.trailing, height / 4)
            .frame(width: width, height: height)
            .background {
                ZStack {
                    Color(hex: fill)
                    if hatch { Hatch().opacity(0.28) }
                }
            }
            .clipShape(Slant(cut: height / 3))
            .accessibilityLabel(abbr)
    }
}

struct Slant: Shape {
    var cut: CGFloat
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: .zero)
        p.addLine(to: CGPoint(x: rect.maxX, y: 0))
        p.addLine(to: CGPoint(x: rect.maxX - cut, y: rect.maxY))
        p.addLine(to: CGPoint(x: 0, y: rect.maxY))
        p.closeSubpath()
        return p
    }
}

struct Hatch: View {
    var body: some View {
        Canvas { ctx, size in
            var x: CGFloat = -size.height
            while x < size.width {
                var line = Path()
                line.move(to: CGPoint(x: x, y: size.height))
                line.addLine(to: CGPoint(x: x + size.height, y: 0))
                ctx.stroke(line, with: .color(.black), lineWidth: 3)
                x += 10
            }
        }
    }
}

/// A state badge: always a glyph and a word, never colour alone.
struct StateBadge: View {
    let text: String
    let fill: Color
    let glyph: String
    var size: CGFloat = 12

    var body: some View {
        Label {
            Text(text.uppercased()).font(Typeface.sans(size, .bold)).tracking(0.8)
        } icon: {
            Image(systemName: glyph).font(.system(size: size, weight: .bold))
        }
        .labelStyle(.titleAndIcon)
        .foregroundStyle(.white)
        .padding(.leading, 7).padding(.trailing, 13).padding(.vertical, 3)
        .lineLimit(1)
        .background(fill, in: Slant(cut: 6))
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// A 100-yard strip drawn so the offense always attacks to the right.
struct FieldBar: View {
    let game: Game
    var height: CGFloat = 10

    var body: some View {
        Canvas { ctx, size in
            let w = size.width, h = size.height
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .linearGradient(
                Gradient(colors: [Tokens.turfA, Tokens.turfB, Tokens.turfA]),
                startPoint: .zero, endPoint: CGPoint(x: w, y: 0)))
            guard let sit = game.situation, let ytg = sit.yardsToGoal,
                  let offense = game.side(id: sit.possession) else { return }
            let defense = offense.id == game.away.id ? game.home : game.away
            let ez = max(4, w * 10 / 120), play = w - 2 * ez
            ctx.fill(Path(CGRect(x: 0, y: 0, width: ez, height: h)), with: .color(Color(hex: offense.fill)))
            ctx.fill(Path(CGRect(x: w - ez, y: 0, width: ez, height: h)), with: .color(Color(hex: defense.fill)))
            for yard in stride(from: 10, to: 100, by: 10) {
                let x = ez + play * CGFloat(yard) / 100
                ctx.fill(Path(CGRect(x: x, y: 0, width: 1, height: h)), with: .color(.white.opacity(yard == 50 ? 0.35 : 0.16)))
            }
            if sit.redZone {
                ctx.fill(Path(CGRect(x: ez + play * 0.8, y: 0, width: play * 0.2, height: h)), with: .color(Tokens.redFill.opacity(0.3)))
            }
            let ballX = ez + play * CGFloat(100 - ytg) / 100
            if let togo = sit.distance {
                let firstX = ez + play * CGFloat(min(100, 100 - ytg + togo)) / 100
                ctx.fill(Path(CGRect(x: firstX - 1, y: -2, width: 2, height: h + 4)), with: .color(Tokens.lineToGain))
            }
            ctx.fill(Path(CGRect(x: ballX - 1, y: -2, width: 2, height: h + 4)), with: .color(Tokens.scrimmage))
            let ball = CGRect(x: ballX - h * 0.55, y: h * 0.12, width: h * 1.1, height: h * 0.76)
            ctx.fill(Path(ellipseIn: ball), with: .color(Tokens.ball))
            ctx.stroke(Path(ellipseIn: ball), with: .color(.white), lineWidth: 1.2)
        }
        .frame(height: height)
        .accessibilityHidden(true)
    }
}

/// Primary: an ink capsule with dark text. Secondary: a faint capsule with
/// ink text. No system accent colour anywhere; colour belongs to chips.
struct PillButtonStyle: ButtonStyle {
    var primary = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    /// A phone gets less padding, so two pills share a row instead of stacking.
    private var horizontalPadding: CGFloat {
        #if os(visionOS)
        22
        #else
        sizeClass == .compact ? 15 : 22
        #endif
    }

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Typeface.sans(17, .semibold))
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .padding(.horizontal, horizontalPadding)
            .frame(minHeight: Tokens.target)
            .foregroundStyle(primary ? Color.black : Color.primary)
            .background(primary ? Color.white.opacity(configuration.isPressed ? 0.75 : 0.92) : Color.white.opacity(configuration.isPressed ? 0.2 : 0.12), in: Capsule())
            .contentShape(.hoverEffect, Capsule())
            .hoverEffect()
    }
}

/// A team's name at whatever length fits: the full location, else the short
/// name the API chose for it. Choosing between two shipped strings by width is
/// layout; neither string is made up here. Truncation is the last resort, and
/// on the short name only.
struct TeamName: View {
    let location: String
    let shortName: String
    var font: Font
    /// In a tile row the name takes the room between chip and score; beside a
    /// rank in a header it hugs its text so the rank stays next to it.
    var fills = true

    var body: some View {
        ViewThatFits(in: .horizontal) {
            Text(location).fixedSize(horizontal: true, vertical: false)
            Text(shortName).fixedSize(horizontal: true, vertical: false)
            Text(shortName).minimumScaleFactor(0.8)
        }
        .font(font)
        .lineLimit(1)
        .frame(maxWidth: fills ? .infinity : nil, alignment: .leading)
        .accessibilityLabel(location)
    }
}
