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
        .sheet(item: $detail) { PlayerSheet(cell: $0) }
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
                        CellView(cell: cell, compact: true) { detail = cell }
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
                immersed.toggle()
                Task {
                    if immersed { _ = await openImmersive(id: "board-space") }
                    else { await dismissImmersive() }
                }
            } label: {
                Label(immersed ? "Leave" : "Immersive",
                      systemImage: immersed ? "rectangle.on.rectangle" : "visionpro")
            }
            .buttonStyle(.borderedProminent)
            .tint(immersed ? Theme.red : Theme.green)
            Button { showSettings = true } label: {
                Image(systemName: "gearshape").font(.system(size: 17))
            }
        }
        .padding(.horizontal, 18).padding(.vertical, 12)
        .glassBackgroundEffect(in: .capsule)
    }
}

/// Tapping a cell opens the numbers behind it. It was the missing half of the
/// board: cells that looked interactive and did nothing.
struct PlayerSheet: View {
    let cell: Cell
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 22) {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(cell.name).font(.system(size: 32, weight: .bold))
                    Text(cell.pos).font(.system(size: 12, weight: .heavy))
                        .padding(.horizontal, 9).padding(.vertical, 3)
                        .background(Theme.position(cell.pos), in: Capsule())
                        .foregroundStyle(.black)
                    Text(cell.team).font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                HStack(spacing: 0) {
                    stat("Scored", cell.scored, .number.precision(.fractionLength(1)))
                    stat("Projected", cell.projected, .number.precision(.fractionLength(1)))
                    stat("Game left", cell.remaining, .percent.precision(.fractionLength(0)))
                    stat("Leverage", cell.share, .percent.precision(.fractionLength(1)))
                }
                VStack(alignment: .leading, spacing: 7) {
                    Text("WHY THIS SIZE").font(.system(size: 10, weight: .heavy))
                        .kerning(1.2).foregroundStyle(.secondary)
                    Text(explanation)
                        .font(.system(size: 15)).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
            }
            .padding(30)
            .navigationTitle(cell.state)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 560, minHeight: 380)
    }

    /// Built as a plain String: interpolating four format styles inline blew
    /// past the type checker's budget, which is a real limit and not a style note.
    private var explanation: String {
        let share = (cell.share * 100).formatted(.number.precision(.fractionLength(1)))
        let left = (cell.remaining * 100).formatted(.number.precision(.fractionLength(0)))
        let sigma = cell.sigma.formatted(.number.precision(.fractionLength(1)))
        return "This cell holds \(share)% of everything still in doubt in this "
             + "matchup. Uncertainty \(sigma) points, with \(left)% of his game "
             + "left to play."
    }

    private func stat(_ label: String, _ value: Double,
                      _ fmt: FloatingPointFormatStyle<Double>.Percent) -> some View {
        VStack(spacing: 3) {
            Text(value, format: fmt).font(.system(size: 24, weight: .bold))
                .monospacedDigit()
            Text(label).font(.system(size: 10, weight: .heavy)).kerning(1)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
    private func stat(_ label: String, _ value: Double,
                      _ fmt: FloatingPointFormatStyle<Double>) -> some View {
        VStack(spacing: 3) {
            Text(value, format: fmt).font(.system(size: 24, weight: .bold))
                .monospacedDigit()
            Text(label).font(.system(size: 10, weight: .heavy)).kerning(1)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

struct HostSheet: View {
    @Environment(Board.self) private var board
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

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
            }
            .navigationTitle("Where is the board?")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        if !draft.isEmpty { board.host = draft }
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
        .onAppear { draft = board.host }
    }
}
