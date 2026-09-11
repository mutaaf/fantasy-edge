import SwiftUI

// The drawing half of the live tab: turf, tokens, and the win-probability
// series. Kept apart from the views that arrange them so both modes - one
// game, or your men across several - draw the same field the same way.

/// A hundred yards between two ten-yard end zones, which is why every
/// conversion here divides by a hundred and twenty.
enum FieldGeometry {
    static let endzone = 10.0 / 120.0

    /// Field coordinate (0 at the attacking side's own goal line, 1 at the
    /// end zone it is driving on) to a point across a view of this width.
    static func px(_ x: Double, _ width: CGFloat) -> CGFloat {
        CGFloat(endzone + max(0, min(1, x)) * (1 - 2 * endzone)) * width
    }
}

extension Color {
    /// A "#003594" out of the feed. Falls back rather than failing, because a
    /// club colour is decoration and a missing one is no reason to lose a panel.
    init(feed hex: String?, fallback: Color = Color(white: 0.18)) {
        var s = (hex ?? "").trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6, let v = UInt32(s, radix: 16) else { self = fallback; return }
        self = Color(red: Double((v >> 16) & 0xFF) / 255,
                     green: Double((v >> 8) & 0xFF) / 255,
                     blue: Double(v & 0xFF) / 255)
    }
}

/// The turf itself - stripes, yard lines, hashes, numbers, two end zones.
///
/// One `Canvas` rather than a stack of shapes: a field is about two hundred
/// and forty lines and ticks, and two hundred and forty views of them would be
/// two hundred and forty things for SwiftUI to diff on every poll, for a
/// drawing that never changes.
struct FieldTurf: View {
    var left = ""
    var right = ""
    var leftTint = Color(white: 0.16)
    var rightTint = Color(white: 0.16)

    var body: some View {
        Canvas { ctx, size in
            let ez = size.width * CGFloat(FieldGeometry.endzone)
            let play = size.width - ez * 2
            let h = size.height

            // Mowing stripes. Ten yards each, the way a groundsman cuts them.
            for band in stride(from: 0, to: 10, by: 2) {
                let r = CGRect(x: ez + play * CGFloat(band) / 10, y: 0,
                               width: play / 10, height: h)
                ctx.fill(Path(r), with: .color(.white.opacity(0.04)))
            }

            ctx.fill(Path(CGRect(x: 0, y: 0, width: ez, height: h)),
                     with: .color(leftTint.opacity(0.65)))
            ctx.fill(Path(CGRect(x: size.width - ez, y: 0, width: ez, height: h)),
                     with: .color(rightTint.opacity(0.65)))

            for yard in stride(from: 0, through: 100, by: 5) {
                let x = ez + play * CGFloat(yard) / 100
                var p = Path()
                p.move(to: CGPoint(x: x, y: 0))
                p.addLine(to: CGPoint(x: x, y: h))
                let goal = yard == 0 || yard == 100
                ctx.stroke(p, with: .color(.white.opacity(
                    goal ? 0.80 : (yard % 10 == 0 ? 0.38 : 0.16))),
                    lineWidth: goal ? 2 : 1)
            }

            for yard in 1..<100 where yard % 5 != 0 {
                let x = ez + play * CGFloat(yard) / 100
                for row in [h * 0.36, h * 0.64] {
                    var p = Path()
                    p.move(to: CGPoint(x: x, y: row - h * 0.018))
                    p.addLine(to: CGPoint(x: x, y: row + h * 0.018))
                    ctx.stroke(p, with: .color(.white.opacity(0.18)), lineWidth: 1)
                }
            }

            let fs = max(8, min(19, h * 0.105))
            for yard in stride(from: 10, through: 90, by: 10) {
                let n = yard <= 50 ? yard : 100 - yard
                let x = ez + play * CGFloat(yard) / 100
                for row in [h * 0.165, h * 0.835] {
                    ctx.draw(Text("\(n)")
                        .font(.system(size: fs, weight: .heavy))
                        .foregroundStyle(.white.opacity(0.26)),
                             at: CGPoint(x: x, y: row))
                }
            }

            // Club names read up the end zone, as they are painted on one.
            for (label, cx, side) in [(left, ez / 2, -1.0),
                                      (right, size.width - ez / 2, 1.0)] {
                guard !label.isEmpty else { continue }
                ctx.drawLayer { l in
                    l.translateBy(x: cx, y: h / 2)
                    l.rotate(by: .degrees(90 * side))
                    l.draw(Text(label)
                        .font(.system(size: max(10, min(21, h * 0.125)), weight: .black))
                        .foregroundStyle(.white.opacity(0.82)), at: .zero)
                }
            }
        }
        .background(
            LinearGradient(colors: [Color(red: 0.055, green: 0.224, blue: 0.122),
                                    Color(red: 0.020, green: 0.129, blue: 0.075)],
                           startPoint: .top, endPoint: .bottom)
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16)
            .stroke(.white.opacity(0.14), lineWidth: 1))
    }
}

/// One man, as he appears standing on the field or sitting beside it.
struct FieldToken: View {
    let man: FieldMan
    var selected = false
    var size: CGFloat = 44
    var dimmed = false
    /// The name capsule under the face. Off where the name is already beside
    /// the token, which is a row rather than a field.
    var named = true
    /// Nil where the token is part of something larger that is already the
    /// hit target. A face inside a tappable row must not be a second control:
    /// the two targets overlap, and which one a pinch lands on depends on
    /// where the gaze happened to settle - so the same gesture sometimes does
    /// the right thing and sometimes nothing at all. On the grass the token
    /// *is* the row, and there it takes the tap itself.
    var tap: (() -> Void)? = nil

    private var tint: Color { Theme.position(man.pos) }
    private var surname: String {
        // A D/ST is "Rams D/ST" and the useful half is the club; a man's is
        // his surname. Both come out of the same trim.
        man.name.split(separator: " ").dropLast(man.defence ? 1 : 0).last
            .map(String.init) ?? man.name
    }

    var body: some View {
        if let tap {
            Button(action: tap) { face }
                .buttonStyle(.plain)
                .hoverEffect(.highlight)
        } else {
            face
        }
    }

    private var face: some View {
            VStack(spacing: 3) {
                ZStack(alignment: .topTrailing) {
                    Headshot(url: man.img, name: man.name, tint: tint, size: size)
                        .overlay(Circle().stroke(selected ? Theme.gold : .clear, lineWidth: 2))
                    if man.points > 0 {
                        Text(man.points, format: .number.precision(.fractionLength(0)))
                            .font(.system(size: 9, weight: .heavy)).monospacedDigit()
                            .padding(.horizontal, 4).padding(.vertical, 1)
                            .background(Theme.green, in: .capsule)
                            .foregroundStyle(.black)
                            .offset(x: 5, y: -3)
                            // Points land in lumps - a touchdown is six at
                            // once - so the badge rolls to the new number
                            // rather than swapping it between polls.
                            .contentTransition(.numericText())
                            .animation(.easeInOut(duration: 0.45), value: man.points)
                    }
                }
                if named {
                    Text(surname)
                        .font(.system(size: 9, weight: .semibold))
                        .lineLimit(1).minimumScaleFactor(0.7)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Color.black.opacity(0.55), in: .capsule)
                }
            }
            .frame(width: named ? size + 26 : size)
            .opacity(dimmed ? 0.45 : 1)
            // A bare token is a headshot and nothing else, so a square hover
            // highlight sat outside the circle on all four corners. Named, it
            // is the circle plus the caption under it, and the smallest shape
            // that honestly covers both is a rounded rectangle.
            .contentShape(named ? AnyShape(.rect(cornerRadius: 12)) : AnyShape(.circle))
    }
}

/// The win probability the feed published, drawn rather than modelled.
///
/// Nothing here computes a probability. The series is one point per play from
/// ESPN, and the only arithmetic is turning it into a path - which is the
/// point: a curve this app invented would look exactly like one it was given.
struct WinProbChart: View {
    let series: [Double]            // home win probability per play, 0...1
    let home: String, away: String
    var homeTint = Theme.green
    var awayTint = Theme.red
    /// Indices of plays that scored, and where the reader is looking.
    var scores: [Int] = []
    var cursor: Int?

    var body: some View {
        Canvas { ctx, size in
            guard series.count > 1 else { return }
            let w = size.width, h = size.height
            func point(_ i: Int) -> CGPoint {
                CGPoint(x: w * CGFloat(i) / CGFloat(series.count - 1),
                        y: h * CGFloat(1 - max(0, min(1, series[i]))))
            }
            ctx.fill(Path(CGRect(x: 0, y: 0, width: w, height: h)),
                     with: .color(awayTint.opacity(0.10)))

            var line = Path()
            line.move(to: point(0))
            for i in 1..<series.count { line.addLine(to: point(i)) }

            var area = line
            area.addLine(to: CGPoint(x: w, y: h))
            area.addLine(to: CGPoint(x: 0, y: h))
            area.closeSubpath()
            ctx.fill(area, with: .linearGradient(
                Gradient(colors: [homeTint.opacity(0.55), homeTint.opacity(0.12)]),
                startPoint: .zero, endPoint: CGPoint(x: 0, y: h)))

            var mid = Path()
            mid.move(to: CGPoint(x: 0, y: h / 2))
            mid.addLine(to: CGPoint(x: w, y: h / 2))
            ctx.stroke(mid, with: .color(.white.opacity(0.30)),
                       style: StrokeStyle(lineWidth: 1, dash: [3, 3]))

            for i in scores where i < series.count {
                var t = Path()
                t.move(to: CGPoint(x: point(i).x, y: 0))
                t.addLine(to: CGPoint(x: point(i).x, y: h))
                ctx.stroke(t, with: .color(Theme.gold.opacity(0.40)), lineWidth: 1)
            }

            ctx.stroke(line, with: .color(.white.opacity(0.92)),
                       style: StrokeStyle(lineWidth: 1.6, lineJoin: .round))

            if let c = cursor, c >= 0, c < series.count {
                var t = Path()
                t.move(to: CGPoint(x: point(c).x, y: 0))
                t.addLine(to: CGPoint(x: point(c).x, y: h))
                ctx.stroke(t, with: .color(Theme.gold), lineWidth: 1.2)
                ctx.fill(Path(ellipseIn: CGRect(x: point(c).x - 3, y: point(c).y - 3,
                                                width: 6, height: 6)),
                         with: .color(Theme.gold))
            }
        }
        .overlay(alignment: .topLeading) { tag(away, awayTint) }
        .overlay(alignment: .bottomLeading) { tag(home, homeTint) }
        .background(RoundedRectangle(cornerRadius: 12).fill(.white.opacity(0.04)))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func tag(_ s: String, _ c: Color) -> some View {
        Text(s).font(.system(size: 9, weight: .heavy))
            .foregroundStyle(c).padding(5)
    }
}

/// A vertical marker on the field: the line of scrimmage, a first-down line,
/// or wherever the ball finished. A view rather than another stroke in the
/// turf's canvas because it is the part that moves, and moving it should be
/// an animation rather than a redraw of the whole field.
struct FieldMarker: View {
    let tint: Color
    var width: CGFloat = 2
    var strength: Double = 0.9

    var body: some View {
        Rectangle().fill(tint).frame(width: width).opacity(strength)
    }
}
