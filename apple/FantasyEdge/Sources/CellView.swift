import SwiftUI

/// One cell, as a button.
///
/// It was a plain View before, which is why nothing on the board could be
/// tapped: there was no control there at all, only something that looked like
/// one. On visionOS the affordance has to be real - a Button gets the system's
/// gaze highlight, the press animation and the accessibility behaviour for
/// free, and `hoverEffect` is what tells you the thing under your eyes is
/// live before you pinch.
struct CellView: View {
    let cell: Cell
    var compact = false
    var action: () -> Void = {}

    private var accent: Color { Theme.side(cell.side) }
    private var isRedZone: Bool { cell.state == "RZ" }
    private var isDone: Bool { cell.remaining <= 0 }

    var body: some View {
        Button(action: action) {
            content
        }
        .buttonStyle(.plain)
        .contentShape(RoundedRectangle(cornerRadius: 22))
        .hoverEffect(.highlight)
        .hoverEffect { effect, isActive, _ in
            // Under gaze a cell grows toward you. The system's own highlight
            // above supplies the specular lift; this adds the scale.
            effect.scaleEffect(isActive ? 1.05 : 1.0)
        }
        .accessibilityLabel("\(cell.name), \(cell.pos), \(cell.scored, specifier: "%.1f") points")
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(cell.name)
                    .font(.system(size: compact ? 16 : 20, weight: .semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(2).minimumScaleFactor(0.7)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Text(cell.pos)
                    .font(.system(size: 10, weight: .heavy)).kerning(0.7)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(Theme.position(cell.pos).opacity(0.9), in: Capsule())
                    .foregroundStyle(.black)
            }
            Spacer(minLength: 6)
            HStack(alignment: .lastTextBaseline, spacing: 6) {
                Text(cell.scored, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: compact ? 30 : 42, weight: .bold))
                    .monospacedDigit().foregroundStyle(.primary)
                    .lineLimit(1).minimumScaleFactor(0.55)   // "0..." was a clip
                    .contentTransition(.numericText())
                    .layoutPriority(2)
                Text("/ \(cell.projected, format: .number.precision(.fractionLength(1)))")
                    .font(.system(size: compact ? 12 : 14))
                    .foregroundStyle(.secondary).monospacedDigit()
                    .lineLimit(1).layoutPriority(1)
                Spacer(minLength: 4)
                Text(isRedZone ? "RZ" : cell.state)
                    .font(.system(size: 10, weight: .heavy)).kerning(0.6)
                    .lineLimit(1).fixedSize()
                    .foregroundStyle(isRedZone ? AnyShapeStyle(Theme.gold)
                                               : AnyShapeStyle(.secondary))
            }
            leverageBar
        }
        .padding(compact ? 14 : 18)
        .frame(width: cell.band.span.w, height: cell.band.span.h, alignment: .topLeading)
        // Glass, not paint. The board should sit in the room rather than cover it.
        .glassBackgroundEffect(in: .rect(cornerRadius: 22))
        .overlay {
            RoundedRectangle(cornerRadius: 22)
                .strokeBorder(isRedZone ? Theme.gold.opacity(0.9)
                                        : accent.opacity(0.45),
                              lineWidth: isRedZone ? 2.5 : 1)
        }
        .opacity(isDone ? 0.75 : 1)
        .animation(.smooth(duration: 0.45), value: cell.band)
        .animation(.smooth(duration: 0.35), value: cell.scored)
    }

    /// The share this cell holds, drawn. It is the only chart on the cell and
    /// it is the one number the layout is actually made of.
    private var leverageBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(.white.opacity(0.14))
                Capsule().fill(accent)
                    .frame(width: geo.size.width * min(1, cell.share * 4))
            }
        }
        .frame(height: 4)
        .padding(.top, 10)
    }
}
