import SwiftUI

/// The windowed board. A flat plane in the Shared Space, which is where you
/// actually live most of the time - the immersive space is for when the games
/// are running and you want to be in it.
struct BoardView: View {
    @Environment(Board.self) private var board
    @Environment(\.openImmersiveSpace) private var openImmersive
    @Environment(\.dismissImmersiveSpace) private var dismissImmersive
    @State private var immersed = false
    @State private var showSettings = false

    private var m: Mosaic { board.mosaic }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            if board.leagues.isEmpty {
                ContentUnavailableView {
                    Label("No board yet", systemImage: "sportscourt")
                } description: {
                    Text(board.lastError ?? "Start the API on your Mac:\n"
                         + "python3 -m fantasyedge api --host 0.0.0.0")
                        .font(.callout)
                } actions: {
                    Button("Retry") { Task { await board.load() } }
                    Button("Set address") { showSettings = true }
                }
                .frame(maxHeight: .infinity)
            } else {
                grid
            }
        }
        .background(Theme.navy.gradient)
        .sheet(isPresented: $showSettings) { HostSheet() }
        .task { board.start() }
        .onDisappear { board.stop() }
    }

    private var header: some View {
        VStack(spacing: 10) {
            HStack {
                Text(board.league?.league ?? "FANTASY EDGE")
                    .font(.system(size: 26, weight: .black)).textCase(.uppercase)
                Spacer()
                if board.leagues.count > 1 {
                    Picker("League", selection: Binding(
                        get: { board.selected ?? board.leagues.first?.id ?? "" },
                        set: { board.selected = $0 })) {
                        ForEach(board.leagues, id: \.id) { Text($0.league).tag($0.id) }
                    }
                    .pickerStyle(.menu).labelsHidden()
                }
                Toggle(isOn: $immersed) {
                    Label("Immersive", systemImage: "visionpro")
                }
                .toggleStyle(.button)
                .onChange(of: immersed) { _, on in
                    Task {
                        if on { _ = await openImmersive(id: "board-space") }
                        else { await dismissImmersive() }
                    }
                }
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape")
                }
            }
            scoreline
        }
        .padding(20)
    }

    private var scoreline: some View {
        HStack(alignment: .center) {
            side(board.league?.you.name ?? "You", m.yourScore, m.yourProjected,
                 Theme.green, .leading)
            VStack(spacing: 2) {
                Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                    .font(.system(size: 30, weight: .black)).monospacedDigit()
                Text("WIN PROBABILITY")
                    .font(.system(size: 9, weight: .heavy)).kerning(1.4)
                    .foregroundStyle(.secondary)
                Text(phaseLine).font(.system(size: 10)).foregroundStyle(.tertiary)
            }
            .frame(width: 170)
            side(board.league?.opp?.name ?? "Opponent", m.oppScore, m.oppProjected,
                 Theme.red, .trailing)
        }
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
        VStack(alignment: align, spacing: 2) {
            Text(name).font(.system(size: 12, weight: .semibold)).kerning(1.1)
                .textCase(.uppercase).foregroundStyle(.secondary).lineLimit(1)
            Text(score, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 46, weight: .black)).monospacedDigit()
                .foregroundStyle(tint)
            Text("proj \(proj, format: .number.precision(.fractionLength(1)))")
                .font(.system(size: 11)).foregroundStyle(.tertiary).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: align == .leading ? .leading : .trailing)
    }

    private var grid: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)],
                      spacing: 12) {
                ForEach(m.cells) { cell in
                    CellView(cell: cell, compact: true)
                }
            }
            .padding(20)
        }
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
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Mac address and port")
                } footer: {
                    Text("Run `python3 -m fantasyedge api --host 0.0.0.0` on the "
                         + "Mac holding the database. The headset needs to be on "
                         + "the same network. No credential ever leaves that Mac.")
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
        .onAppear { draft = board.host }
    }
}
