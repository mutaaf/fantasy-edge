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
    /// Read only for the projection behind the cell: the denominator is one
    /// source's number, and which source that is decides the band this cell
    /// was given. Both scenes that draw a cell already put the board in the
    /// environment.
    @Environment(Board.self) private var board
    let cell: Cell
    var compact = false
    /// How much larger this cell is drawn than in the window, and it is a
    /// multiplier on the *points* rather than a `scaleEffect`.
    ///
    /// A point is not the same angular size on both surfaces. Measured off a
    /// simulator capture: the window's 1680pt of width subtends about 53
    /// degrees, and a 330pt cell standing at 1.9 metres in the immersive space
    /// subtends 6.5 - which is 31.7 points per degree against 50.8, so the same
    /// card in the room reads 1.6 times smaller. Everything in it was therefore
    /// set at laptop sizes and hung on a wall, which is what "unreadable text
    /// and such" was.
    ///
    /// Not `scaleEffect`: a RealityKit attachment rasterises its SwiftUI view
    /// once at a fixed density and magnifying that entity magnifies the
    /// texture. Multiplying the points means it is *rendered* larger, which is
    /// the difference between bigger type and a bigger picture of small type.
    var scale: CGFloat = 1
    /// Set for a few seconds after this player scores. A cell that only shows a
    /// new total makes you diff it in your head.
    var reaction: Board.Reaction?
    var action: () -> Void = {}

    private func s(_ v: CGFloat) -> CGFloat { v * scale }
    private var radius: CGFloat { 22 * scale }
    private var accent: Color { Theme.side(cell.side) }
    private var isRedZone: Bool { cell.state == "RZ" }
    private var isDone: Bool { cell.remaining <= 0 }

    var body: some View {
        Button(action: action) {
            content
        }
        .buttonStyle(.plain)
        .contentShape(RoundedRectangle(cornerRadius: radius))
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
                    .font(.system(size: s(compact ? 16 : 20), weight: .semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(2).minimumScaleFactor(0.7)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                // Opaque, and white rather than black on it. At 90% alpha
                // the room still showed through enough to move the ground
                // under two-point type, and black on a light hue and white on
                // a dark one cannot both be right for six positions.
                Chip(text: cell.pos, fill: Theme.positionFill(cell.pos), size: s(10))
            }
            Spacer(minLength: 6)
            HStack(alignment: .lastTextBaseline, spacing: 6) {
                Text(cell.scored, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: s(compact ? 30 : 42), weight: .bold))
                    .monospacedDigit().foregroundStyle(.primary)
                    .lineLimit(1).minimumScaleFactor(0.55)   // "0..." was a clip
                    .contentTransition(.numericText())
                    .layoutPriority(2)
                Text("/ \(cell.projected, format: .number.precision(.fractionLength(1)))")
                    .font(.system(size: s(compact ? 12 : 14)))
                    .foregroundStyle(.secondary).monospacedDigit()
                    .lineLimit(1).layoutPriority(1)
                // Only where the sources actually argue. The cell has room
                // for one mark beside the denominator, and spending it on a
                // source name would spend it on something the ornament
                // already says for the whole board - whereas "these two do
                // not agree about this man" is true of him and nothing else.
                if let sp = spread {
                    SpreadChip(spread: sp, compact: compact, scale: scale)
                }
                Spacer(minLength: 4)
                // The red zone is the one state on a cell worth shouting, so
                // it gets the chip. Gold as text measured 1.02:1 - the loudest
                // thing on the board was the one nobody could read.
                if isRedZone {
                    Chip(text: "RZ", fill: Theme.goldFill, size: s(10))
                } else {
                    Text(cell.state)
                        .font(.system(size: s(10), weight: .heavy)).kerning(0.6 * scale)
                        .lineLimit(1).fixedSize()
                        .foregroundStyle(.secondary)
                }
            }
            leverageBar
        }
        .padding(s(compact ? 14 : 18))
        .frame(width: cell.band.span.w * scale, height: cell.band.span.h * scale,
               alignment: .topLeading)
        // Glass, not paint. The board should sit in the room rather than cover it.
        .glassBackgroundEffect(in: .rect(cornerRadius: radius))
        .overlay {
            RoundedRectangle(cornerRadius: radius)
                .strokeBorder(isRedZone ? Theme.gold.opacity(0.9)
                                        : accent.opacity(0.45),
                              lineWidth: s(isRedZone ? 2.5 : 1))
        }
        .overlay(alignment: .topTrailing) { burst }
        .scaleEffect(reaction != nil ? 1.06 : 1)
        .shadow(color: reaction != nil ? accent.opacity(0.75) : .clear,
                radius: reaction != nil ? 26 : 0)
        .opacity(isDone ? 0.75 : 1)
        .animation(.smooth(duration: 0.45), value: cell.band)
        .animation(.smooth(duration: 0.35), value: cell.scored)
        .animation(.bouncy(duration: 0.55), value: reaction)
    }

    /// What just landed, said as a size rather than a claim: the feed carries
    /// totals, not events, so this knows a jump happened but not that it was a
    /// touchdown.
    @ViewBuilder
    private var burst: some View {
        if let r = reaction {
            HStack(spacing: 4) {
                Image(systemName: "arrow.up.right").font(.system(size: s(10), weight: .black))
                Text("+\(r.delta, format: .number.precision(.fractionLength(1)))")
                    .font(.system(size: s(13), weight: .heavy)).monospacedDigit()
            }
            .padding(.horizontal, s(10)).padding(.vertical, s(5))
            .background(Theme.sideFill(cell.side), in: Capsule())
            .foregroundStyle(.white)
            .offset(x: 10, y: -10)
            .transition(.scale(scale: 0.4).combined(with: .opacity))
        }
    }

    /// How far apart the loaded sources are on this man, when that is far
    /// enough to have changed the band he was given.
    private var spread: Double? {
        guard let s = board.projectionIndex[cell.id]?.spread,
              s >= ProjectionPick.disputedAt else { return nil }
        return s
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
        .frame(height: s(4))
        .padding(.top, s(10))
    }
}
