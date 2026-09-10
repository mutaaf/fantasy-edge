import SwiftUI

/// One cell. Deliberately the same component in the window and in the volume,
/// so the two can never drift into different-looking boards.
struct CellView: View {
    let cell: Cell
    var compact = false

    private var accent: Color { Theme.side(cell.side) }
    private var isRedZone: Bool { cell.state == "RZ" }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(cell.name)
                    .font(.system(size: compact ? 15 : 19, weight: .bold))
                    .lineLimit(1).minimumScaleFactor(0.7)
                Spacer(minLength: 6)
                Text(cell.pos)
                    .font(.system(size: 10, weight: .heavy)).kerning(0.8)
                    .padding(.horizontal, 7).padding(.vertical, 2)
                    .background(Theme.position(cell.pos), in: Capsule())
                    .foregroundStyle(.black)
            }
            Spacer(minLength: 4)
            HStack(alignment: .lastTextBaseline, spacing: 6) {
                Text(cell.scored, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: compact ? 26 : 38, weight: .heavy))
                    .monospacedDigit()
                Text("/ \(cell.projected, format: .number.precision(.fractionLength(1)))")
                    .font(.system(size: compact ? 11 : 13, weight: .medium))
                    .foregroundStyle(.secondary).monospacedDigit()
                Spacer(minLength: 4)
                Text(isRedZone ? "RED ZONE" : cell.state)
                    .font(.system(size: 10, weight: .heavy)).kerning(0.9)
                    .foregroundStyle(isRedZone ? Theme.gold : .secondary)
            }
        }
        .padding(compact ? 11 : 15)
        .frame(width: cell.band.span.w, height: cell.band.span.h, alignment: .topLeading)
        .background(alignment: .leading) {
            // the leverage spine, drawn to the share it actually holds
            Rectangle().fill(accent)
                .frame(width: 4, height: cell.band.span.h * min(1, cell.share * 4))
                .frame(maxHeight: .infinity, alignment: .bottom)
        }
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .strokeBorder(isRedZone ? Theme.gold : accent.opacity(0.55),
                              lineWidth: isRedZone ? 2 : 1)
        )
        .opacity(cell.remaining <= 0 ? 0.45 : 1)
        .animation(.smooth(duration: 0.45), value: cell.band)
        .animation(.smooth(duration: 0.35), value: cell.scored)
    }
}
