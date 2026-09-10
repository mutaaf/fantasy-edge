import AVKit
import RealityKit
import SwiftUI

/// The board, placed in the room.
///
/// An immersive space's origin is the floor under the wearer, so everything
/// here is positioned in metres rather than nudged with view offsets - the
/// first version used `offset(z:)` from a ZStack and rendered the whole board
/// at your feet, which is why turning it on appeared to do nothing.
///
/// Two arrangements. Normally the cells sit on an arc in front of you and
/// leverage is distance: a player who can still change your week stands
/// nearer, a decided one falls back. Put a game on and they open into a ring
/// around the screen, so you are watching with your line-up around you rather
/// than beside a list.
struct ImmersiveBoard: View {
    @Environment(Board.self) private var board
    @Environment(\.dismissImmersiveSpace) private var dismissImmersive
    @Environment(\.openWindow) private var openWindow

    @State private var detail: Cell?
    @State private var player = AVPlayer()
    @State private var watching = false

    private let radius: Float = 1.9
    private let eyeHeight: Float = 1.35
    private let columns = 5
    private let columnAngle: Float = 17 * .pi / 180
    private let rowDrop: Float = 0.34
    /// Wider when a game is on, so the screen has the middle to itself.
    private var ringAngle: Float { watching ? 26 * .pi / 180 : columnAngle }

    var body: some View {
        RealityView { content, attachments in
            let root = Entity()
            root.name = "root"
            content.add(root)
            layout(into: root, attachments: attachments)
        } update: { content, attachments in
            guard let root = content.entities.first(where: { $0.name == "root" })
            else { return }
            // Idempotent: entities are added once and moved thereafter. Tearing
            // them down each pass is what made this seize up.
            layout(into: root, attachments: attachments)
        } attachments: {
            ForEach(board.mosaic.cells) { cell in
                Attachment(id: cell.id) {
                    CellView(cell: cell, reaction: board.reactions[cell.id]) {
                        detail = (detail?.id == cell.id) ? nil : cell
                    }
                }
            }
            Attachment(id: "scoreline") { scoreline }
            Attachment(id: "controls") { controls }
            Attachment(id: "reactions") { reactionFeed }
            if let cell = detail {
                Attachment(id: "detail") {
                    PlayerHologram(cell: cell) { detail = nil }
                        .frame(width: 640, height: 640)
                        .glassBackgroundEffect(in: .rect(cornerRadius: 34))
                }
            }
            if watching {
                Attachment(id: "screen") { screen }
            }
        }
    }

    // MARK: - placement

    private func layout(into root: Entity, attachments: RealityViewAttachments) {
        let cells = board.mosaic.cells
        for (i, cell) in cells.enumerated() {
            guard let view = attachments.entity(for: cell.id) else { continue }
            if view.parent !== root { root.addChild(view) }
            let col = Float(i % columns) - Float(columns - 1) / 2
            let row = Float(i / columns)
            let angle = col * ringAngle
            let depth = radius - cell.band.depth
            view.position = SIMD3(x: sin(angle) * depth,
                                  y: eyeHeight - row * rowDrop,
                                  z: -cos(angle) * depth)
            view.orientation = simd_quatf(angle: -angle, axis: SIMD3(0, 1, 0))
            // A detail panel is open in the middle; get the near cells out of it.
            view.isEnabled = !(detail != nil && abs(col) < 1.2 && row < 1)
        }
        pin("scoreline", attachments, root, SIMD3(0, eyeHeight + 0.42, -radius + 0.1))
        pin("controls", attachments, root, SIMD3(0, eyeHeight - 0.95, -radius + 0.4))
        pin("reactions", attachments, root,
            SIMD3(-radius * 0.92, eyeHeight - 0.1, -radius * 0.42), yaw: 0.62)
        pin("detail", attachments, root, SIMD3(0, eyeHeight - 0.02, -radius + 0.55))
        pin("screen", attachments, root, SIMD3(0, eyeHeight, -radius - 0.25))
    }

    private func pin(_ id: String, _ attachments: RealityViewAttachments,
                     _ root: Entity, _ position: SIMD3<Float>, yaw: Float = 0) {
        guard let e = attachments.entity(for: id) else { return }
        if e.parent !== root { root.addChild(e) }
        e.position = position
        if yaw != 0 { e.orientation = simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0)) }
    }

    // MARK: - furniture

    private var scoreline: some View {
        let m = board.mosaic
        return HStack(spacing: 30) {
            Text(m.yourScore, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 54, weight: .bold))
                .foregroundStyle(Theme.green).contentTransition(.numericText())
            VStack(spacing: 2) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 30, weight: .bold))
                Text(board.league?.league ?? "").font(.system(size: 12))
                    .foregroundStyle(.secondary).lineLimit(1)
            }
            Text(m.oppScore, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 54, weight: .bold))
                .foregroundStyle(Theme.red).contentTransition(.numericText())
        }
        .monospacedDigit()
        .padding(.horizontal, 38).padding(.vertical, 22)
        .glassBackgroundEffect(in: .capsule)
    }

    private var controls: some View {
        HStack(spacing: 14) {
            Button {
                watching.toggle()
                if watching { startWatching() } else { player.pause() }
            } label: {
                Label(watching ? "Close game" : "Watch the game",
                      systemImage: watching ? "xmark.circle" : "play.tv")
                    .font(.system(size: 16, weight: .medium))
            }
            .buttonStyle(.borderedProminent).tint(watching ? Theme.red : Theme.green)

            Button {
                Task { await dismissImmersive(); openWindow(id: "board") }
            } label: {
                Label("Back to the window", systemImage: "rectangle.on.rectangle")
                    .font(.system(size: 16, weight: .medium))
            }
            .buttonStyle(.bordered)
        }
        .padding(.horizontal, 20).padding(.vertical, 14)
        .glassBackgroundEffect(in: .capsule)
        .hoverEffect(.highlight)
    }

    /// A live feed of what just landed, at the edge of vision, so a big play
    /// registers even while you are looking at the game rather than the board.
    private var reactionFeed: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("AS IT HAPPENS").font(.system(size: 10, weight: .heavy)).kerning(1.3)
                .foregroundStyle(.tertiary)
            if board.recent.isEmpty {
                Text("Nothing yet").font(.system(size: 14)).foregroundStyle(.secondary)
            } else {
                ForEach(board.recent.prefix(5)) { r in
                    HStack(spacing: 10) {
                        Text("+\(r.delta, format: .number.precision(.fractionLength(1)))")
                            .font(.system(size: 15, weight: .heavy)).monospacedDigit()
                            .foregroundStyle(r.side == "you" ? Theme.green : Theme.red)
                            .frame(width: 54, alignment: .leading)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(r.name).font(.system(size: 14, weight: .semibold))
                                .lineLimit(1)
                            Text("\(r.headline) · now \(r.total, format: .number.precision(.fractionLength(1)))")
                                .font(.system(size: 11)).foregroundStyle(.secondary)
                        }
                    }
                    .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
        }
        .frame(width: 270, alignment: .leading)
        .padding(18)
        .glassBackgroundEffect(in: .rect(cornerRadius: 24))
        .animation(.smooth, value: board.recent)
    }

    /// The game itself, in the middle, with the line-up opened into a ring
    /// around it. The source is whatever you point it at - there is no stream
    /// bundled here and inventing one would be worse than asking.
    private var screen: some View {
        VStack(spacing: 0) {
            if board.watchURL.isEmpty {
                VStack(spacing: 14) {
                    Image(systemName: "play.tv").font(.system(size: 40))
                        .foregroundStyle(.secondary)
                    Text("No video source set")
                        .font(.system(size: 19, weight: .semibold))
                    Text("Add a stream or file URL in the window's settings and it "
                         + "will play here, with your line-up around it.")
                        .font(.system(size: 14)).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center).frame(maxWidth: 420)
                }
                .frame(width: 900, height: 506)
            } else {
                VideoPlayer(player: player)
                    .frame(width: 900, height: 506)
            }
        }
        .glassBackgroundEffect(in: .rect(cornerRadius: 26))
    }

    private func startWatching() {
        guard let url = URL(string: board.watchURL), !board.watchURL.isEmpty
        else { return }
        player.replaceCurrentItem(with: AVPlayerItem(url: url))
        player.play()
    }
}
