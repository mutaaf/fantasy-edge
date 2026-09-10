import RealityKit
import SwiftUI

/// The board, placed in the room.
///
/// The first version put SwiftUI views in a ZStack and nudged them with
/// `offset(z:)`. That does nothing useful here, because an immersive space's
/// origin is *the floor under the wearer* - the content was rendering at your
/// feet and inside your head, which is why turning it on appeared to do
/// nothing at all.
///
/// Positions are metres now, on an arc in front of you at eye height, through
/// RealityKit attachments. Importance is depth: a cell that can still change
/// your week stands nearer, a decided one falls back and dims. That is the
/// thing a flat screen cannot do, and the only honest reason to put a board in
/// a headset.
struct ImmersiveBoard: View {
    @Environment(Board.self) private var board
    var onSelect: (Cell) -> Void = { _ in }

    /// Comfort, not spectacle: far enough to focus on, low enough not to crane.
    private let radius: Float = 1.9
    private let eyeHeight: Float = 1.35
    private let columns = 5
    private let columnAngle: Float = 17 * .pi / 180   // radians between columns
    private let rowDrop: Float = 0.34                 // metres between rows

    var body: some View {
        RealityView { content, attachments in
            let root = Entity()
            root.name = "root"
            content.add(root)
            place(board.mosaic.cells, into: root, attachments: attachments)
        } update: { content, attachments in
            guard let root = content.entities.first(where: { $0.name == "root" })
            else { return }
            root.children.forEach { $0.removeFromParent() }
            place(board.mosaic.cells, into: root, attachments: attachments)
        } attachments: {
            ForEach(board.mosaic.cells) { cell in
                Attachment(id: cell.id) {
                    CellView(cell: cell) { onSelect(cell) }
                        .frame(width: cell.band.span.w, height: cell.band.span.h)
                }
            }
            Attachment(id: "scoreline") { scoreline }
        }
    }

    private func place(_ cells: [Cell], into root: Entity,
                       attachments: RealityViewAttachments) {
        for (i, cell) in cells.enumerated() {
            guard let view = attachments.entity(for: cell.id) else { continue }
            let col = Float(i % columns) - Float(columns - 1) / 2
            let row = Float(i / columns)
            let angle = col * columnAngle
            // leverage brings a cell forward; a finished one falls away
            let depth = radius - cell.band.depth
            view.position = SIMD3(
                x: sin(angle) * depth,
                y: eyeHeight - row * rowDrop,
                z: -cos(angle) * depth
            )
            // turn each cell to face the wearer rather than show an oblique edge
            view.orientation = simd_quatf(angle: -angle, axis: SIMD3(0, 1, 0))
            root.addChild(view)
        }
        if let head = attachments.entity(for: "scoreline") {
            head.position = SIMD3(0, eyeHeight + 0.42, -radius + 0.1)
            root.addChild(head)
        }
    }

    private var scoreline: some View {
        let m = board.mosaic
        return HStack(spacing: 30) {
            Text(m.yourScore, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 54, weight: .bold))
                .foregroundStyle(Theme.green)
                .contentTransition(.numericText())
            VStack(spacing: 2) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 30, weight: .bold))
                Text(board.league?.league ?? "")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary).lineLimit(1)
            }
            Text(m.oppScore, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 54, weight: .bold))
                .foregroundStyle(Theme.red)
                .contentTransition(.numericText())
        }
        .monospacedDigit()
        .padding(.horizontal, 38).padding(.vertical, 22)
        .glassBackgroundEffect(in: .capsule)
    }
}
