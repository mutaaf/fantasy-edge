import SwiftUI

/// The immersive board.
///
/// This is the argument for a headset rather than a television: the cells are
/// not laid on a plane, they are placed around you, and importance is depth.
/// A cell that can still change your week stands forward; a decided one falls
/// back and dims. On a flat screen that has to be faked with blur - here it is
/// simply where the thing is.
///
/// Laid on a shallow arc rather than a flat wall, so cells at the edges turn to
/// face you instead of presenting an oblique sliver.
struct ImmersiveBoard: View {
    @Environment(Board.self) private var board

    private let columns = 6

    var body: some View {
        ZStack {
            header
            placed
        }
    }

    private var placed: some View {
        let cells = board.mosaic.cells
        return ForEach(Array(cells.enumerated()), id: \.element.id) { pair in
            positioned(pair.offset, pair.element)
        }
    }

    /// Kept as its own function: inlining it made the body too complex for the
    /// type checker, which is a real limit rather than a style preference.
    @ViewBuilder
    private func positioned(_ index: Int, _ cell: Cell) -> some View {
        let col = Float(index % columns) - Float(columns - 1) / 2
        let row = CGFloat(index / columns)
        CellView(cell: cell)
            .rotation3DEffect(.degrees(Double(-col) * 9), axis: (x: 0, y: 1, z: 0))
            .offset(x: CGFloat(col) * 250, y: row * 190 - 140)
            .offset(z: CGFloat(cell.band.depth) * 260)
            .opacity(cell.remaining <= 0 ? 0.5 : 1.0)
            .animation(.smooth(duration: 0.6), value: cell.band)
    }

    private var header: some View {
        let m = board.mosaic
        return HStack(spacing: 26) {
            Text(m.yourScore, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 60, weight: .black))
                .foregroundStyle(Theme.green)
            VStack(spacing: 2) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 32, weight: .black))
                Text(board.league?.league ?? "")
                    .font(.system(size: 12, weight: .semibold))
                    .textCase(.uppercase)
                    .foregroundStyle(.secondary)
            }
            Text(m.oppScore, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 60, weight: .black))
                .foregroundStyle(Theme.red)
        }
        .monospacedDigit()
        .padding(.horizontal, 34)
        .padding(.vertical, 18)
        .glassBackgroundEffect()
        .offset(y: -360)
        .offset(z: 140)
    }
}
