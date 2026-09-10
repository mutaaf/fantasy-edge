import SwiftUI

/// The windowed board.
///
/// The controls live in a bottom ornament rather than a header bar, which is
/// the visionOS convention and buys the board its whole width back. The window
/// itself carries no paint: glass belongs to the system, and a solid navy fill
/// fought the room instead of sitting in it.
struct BoardView: View {
    @Environment(Board.self) private var board
    @Environment(\.openImmersiveSpace) private var openImmersive
    @Environment(\.dismissImmersiveSpace) private var dismissImmersive
    @Environment(\.dismissWindow) private var dismissWindow
    @State private var immersed = false
    @State private var showSettings = false
    @State private var detail: Cell?

    private var m: Mosaic { board.mosaic }

    var body: some View {
        Group {
            if board.leagues.isEmpty { empty } else { board_ }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .ornament(attachmentAnchor: .scene(.bottom), contentAlignment: .center) {
            controls
        }
        .sheet(isPresented: $showSettings) { HostSheet() }
        .sheet(item: $detail) { PlayerHologram(cell: $0) }
        .task { board.start() }
        .onDisappear { board.stop() }
    }

    private var empty: some View {
        ContentUnavailableView {
            Label("No board yet", systemImage: "sportscourt")
        } description: {
            Text(board.lastError.map { "Cannot reach \(board.host).\n\($0)" }
                 ?? "Start the API on your Mac:\npython3 -m fantasyedge api --host 0.0.0.0")
        } actions: {
            Button("Set address") { showSettings = true }.buttonStyle(.borderedProminent)
            Button("Retry") { Task { await board.load() } }
        }
    }

    private var board_: some View {
        VStack(spacing: 18) {
            scoreline
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 18)],
                          spacing: 16) {
                    ForEach(m.cells) { cell in
                        CellView(cell: cell, compact: true,
                                 reaction: board.reactions[cell.id]) { detail = cell }
                    }
                }
                .padding(.horizontal, 26).padding(.bottom, 26)
            }
        }
        .padding(.top, 26)
    }

    private var scoreline: some View {
        HStack(alignment: .center, spacing: 20) {
            side(board.league?.you.name ?? "You", m.yourScore, m.yourProjected,
                 Theme.green, .leading)
            VStack(spacing: 3) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 34, weight: .bold)).monospacedDigit()
                    .contentTransition(.numericText())
                Text("WIN PROBABILITY").font(.system(size: 9, weight: .heavy))
                    .kerning(1.3).foregroundStyle(.secondary)
                Text(phaseLine).font(.system(size: 11)).foregroundStyle(.tertiary)
            }
            .frame(width: 190)
            side(board.league?.opp?.name ?? "Opponent", m.oppScore, m.oppProjected,
                 Theme.red, .trailing)
        }
        .padding(.horizontal, 30).padding(.vertical, 20)
        .glassBackgroundEffect(in: .rect(cornerRadius: 28))
        .padding(.horizontal, 26)
    }

    private var phaseLine: String {
        switch m.phase {
        case "pre": return "sized by projection"
        case "final": return "week complete"
        default: return "intensity \(Int(m.intensity * 100))%"
        }
    }

    private func side(_ name: String, _ score: Double, _ proj: Double,
                      _ tint: Color, _ align: HorizontalAlignment) -> some View {
        VStack(alignment: align, spacing: 3) {
            Text(name).font(.system(size: 12, weight: .medium)).kerning(0.9)
                .textCase(.uppercase).foregroundStyle(.secondary).lineLimit(1)
            Text(score, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 50, weight: .bold)).monospacedDigit()
                .foregroundStyle(tint).contentTransition(.numericText())
            Text("proj \(proj, format: .number.precision(.fractionLength(1)))")
                .font(.system(size: 12)).foregroundStyle(.tertiary).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: align == .leading ? .leading : .trailing)
    }

    /// A bottom ornament: the visionOS place for a scene's controls.
    private var controls: some View {
        HStack(spacing: 12) {
            if board.leagues.count > 1 {
                Picker("League", selection: Binding(
                    get: { board.selected ?? board.leagues.first?.id ?? "" },
                    set: { board.selected = $0 })) {
                    ForEach(board.leagues, id: \.id) { Text($0.league).tag($0.id) }
                }
                .pickerStyle(.menu).labelsHidden().frame(minWidth: 190)
            }
            Divider().frame(height: 22)
            Button {
                Task {
                    // One mode at a time. Leaving the window open behind the
                    // immersive board put you in both at once, with two boards
                    // fighting for the same room.
                    if await openImmersive(id: "board-space") == .opened {
                        dismissWindow(id: "board")
                    }
                }
            } label: {
                Label("Immersive", systemImage: "visionpro")
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.green)
            Button { showSettings = true } label: {
                Image(systemName: "gearshape").font(.system(size: 17))
            }
        }
        .padding(.horizontal, 18).padding(.vertical, 12)
        .glassBackgroundEffect(in: .capsule)
    }
}

struct HostSheet: View {
    @Environment(Board.self) private var board
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""
    @State private var watch = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("192.168.1.20:8770", text: $draft)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                } header: {
                    Text("Mac address and port")
                } footer: {
                    Text("Run `python3 -m fantasyedge api --host 0.0.0.0` on the Mac "
                         + "holding the database, and put its address here. No "
                         + "credential ever leaves that Mac.")
                }
                Section {
                    TextField("https://…/stream.m3u8", text: $watch)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                } header: {
                    Text("Game video")
                } footer: {
                    Text("Played in the middle of the immersive board, with your "
                         + "line-up opened into a ring around it. Any stream or "
                         + "file URL AVPlayer can open. Nothing is bundled - "
                         + "point it at whatever you are already watching.")
                }
            }
            .navigationTitle("Where is the board?")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        if !draft.isEmpty { board.host = draft }
                        board.watchURL = watch
                        Task { await board.load() }
                        dismiss()
                    }
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .frame(minWidth: 520, minHeight: 300)
        .onAppear { draft = board.host; watch = board.watchURL }
    }
}
