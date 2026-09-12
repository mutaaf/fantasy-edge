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
        // Aligned so the whole bar sits below the scene rather than straddling
        // its edge - see the note on the same two lines in `CommandView`.
        .ornament(attachmentAnchor: .scene(.bottom), contentAlignment: .top) {
            controls
        }
        .sheet(isPresented: $showSettings) { HostSheet() }
        .sheet(item: $detail) { PlayerHologram(cell: $0) }
        .task {
            board.start()
            await board.loadPrefs()
            await board.loadProjections()
        }
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

    // MARK: - the scoreboard

    /// What a scoreboard is actually for: who is ahead, by how much, and
    /// whether it is holdable. The previous one showed two totals and a
    /// percentage and left all three questions to you - and before kickoff,
    /// when every total is 0.0, it said nothing at all.
    private var scoreline: some View {
        VStack(spacing: 14) {
            Text(headline)
                .font(.system(size: 13, weight: .heavy)).kerning(1.6)
                .foregroundStyle(.secondary)
                .contentTransition(.opacity)

            HStack(alignment: .top, spacing: 22) {
                side(board.league?.you.name ?? "You", m.yourScore, m.yourProjected,
                     toPlay("you"), Theme.green, .leading)
                VStack(spacing: 6) {
                    Text(m.winProb, format: .percent.precision(.fractionLength(0)))
                        .font(.system(size: 40, weight: .bold)).monospacedDigit()
                        .contentTransition(.numericText())
                    leanBar
                    Text("WIN PROBABILITY").font(.system(size: 9, weight: .heavy))
                        .kerning(1.3).foregroundStyle(.secondary)
                    Text(phaseLine).font(.system(size: 11)).foregroundStyle(.tertiary)
                }
                .frame(width: 210)
                side(board.league?.opp?.name ?? "Opponent", m.oppScore, m.oppProjected,
                     toPlay("opp"), Theme.red, .trailing)
            }
        }
        .padding(.horizontal, 34).padding(.vertical, 22)
        .glassBackgroundEffect(in: .rect(cornerRadius: 30))
        .padding(.horizontal, 26)
    }

    /// The lean, drawn. A percentage tells you the number; the bar tells you
    /// the shape of it without reading.
    private var leanBar: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.red.opacity(0.55))
                Capsule().fill(Theme.green)
                    .frame(width: max(3, g.size.width * m.winProb))
            }
        }
        .frame(height: 6)
        .frame(maxWidth: 180)
        .animation(.easeInOut(duration: 0.5), value: m.winProb)
    }

    /// Leader and margin, phrased for the phase. Before kickoff there is no
    /// leader, so it reports the projected edge instead of pretending to a
    /// scoreline of zeros.
    private var headline: String {
        let you = board.league?.you.name ?? "You"
        let opp = board.league?.opp?.name ?? "Opponent"
        if m.phase == "pre" {
            let d = m.yourProjected - m.oppProjected
            if abs(d) < 0.05 { return "EVENLY PROJECTED" }
            return "\(d > 0 ? you : opp) PROJECTED BY \(fmt(abs(d)))".uppercased()
        }
        let d = m.yourScore - m.oppScore
        if abs(d) < 0.05 { return m.phase == "final" ? "TIED" : "LEVEL" }
        let verb = m.phase == "final" ? "WON BY" : "LEADS BY"
        return "\(d > 0 ? you : opp) \(verb) \(fmt(abs(d)))".uppercased()
    }

    private func fmt(_ v: Double) -> String { String(format: "%.1f", v) }

    /// How many of that side's men have not finished. The single most useful
    /// number on a live scoreboard and the one the old one never showed: a
    /// twenty point lead with nobody left is not the same lead at all.
    private func toPlay(_ side: String) -> Int {
        m.cells.filter { $0.side == side && $0.remaining > 0.001 }.count
    }

    private var phaseLine: String {
        switch m.phase {
        case "pre": return "sized by projection"
        case "final": return "week complete"
        default: return "intensity \(Int(m.intensity * 100))%"
        }
    }

    private func side(_ name: String, _ score: Double, _ proj: Double,
                      _ left: Int, _ tint: Color,
                      _ align: HorizontalAlignment) -> some View {
        VStack(alignment: align, spacing: 4) {
            Text(name).font(.system(size: 13, weight: .semibold)).kerning(0.6)
                .foregroundStyle(.primary).lineLimit(1).minimumScaleFactor(0.7)
            Text(score, format: .number.precision(.fractionLength(1)))
                .font(.system(size: 54, weight: .bold)).monospacedDigit()
                .foregroundStyle(tint).contentTransition(.numericText())
            HStack(spacing: 8) {
                Text("proj \(proj, format: .number.precision(.fractionLength(1)))")
                    .monospacedDigit()
                if left > 0 {
                    Text("·").foregroundStyle(.quaternary)
                    Text("\(left) to play").monospacedDigit()
                } else if m.phase != "pre" {
                    Text("·").foregroundStyle(.quaternary)
                    Text("all done")
                }
            }
            .font(.system(size: 12)).foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, alignment: align == .leading ? .leading : .trailing)
    }

    // MARK: - choosing a league, and your team inside it

    /// A bottom ornament: the visionOS place for a scene's controls.
    ///
    /// The league picker was a bare menu of raw names, and there was no team
    /// picker at all - so the board showed whichever manager the server
    /// guessed, and on this device you had no way to correct it. Both are
    /// first-class here, and both say what they are.
    private var controls: some View {
        HStack(spacing: 14) {
            // Omitted rather than greyed with one league: a picker for a
            // choice that does not exist is chrome, not an affordance.
            if !board.scale.single {
                chooser(icon: "trophy", label: "LEAGUE",
                        value: board.league?.league ?? "—") {
                    ForEach(board.leagues, id: \.id) { L in
                        Button { board.selected = L.id } label: {
                            if L.id == board.league?.id { Label(L.league, systemImage: "checkmark") }
                            else { Text(L.league) }
                        }
                    }
                }
            }

            chooser(icon: "person.crop.circle", label: "MY TEAM",
                    value: board.league?.you.name ?? "—") {
                ForEach(teamOptions, id: \.id) { t in
                    Button {
                        if let lid = board.league?.id {
                            Task { await board.pickTeam(t.teamId, in: lid) }
                        }
                    } label: {
                        if t.teamId == board.league?.you.teamId {
                            Label(t.display, systemImage: "checkmark")
                        } else { Text(t.display) }
                    }
                }
            }
            .disabled(teamOptions.count < 2)

            // The same chooser the console carries. This window sizes its
            // cells by the projection too, so leaving it out here would mean
            // two boards in the same app showing different numbers with no
            // way to tell why.
            chooser(icon: "chart.line.uptrend.xyaxis", label: "PROJECTIONS",
                    value: board.loadedSources.isEmpty ? "none loaded"
                        : (board.projectionChoice == "consensus"
                           ? "Consensus of \(board.consensusN)"
                           : board.projectionLabel)) {
                ProjectionMenu()
            }

            Divider().frame(height: 26)

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
        .padding(.horizontal, 20).padding(.vertical, 12)
        .glassBackgroundEffect(in: .capsule)
    }

    private var teamOptions: [TeamRef] {
        (board.league?.teams ?? []).sorted { $0.display < $1.display }
    }

    /// A labelled menu button. A menu that shows only its current value makes
    /// you open it to learn what it even chooses - the label is what makes
    /// "Sure Buds" and "Karachi Bakras" legible as a league and a team rather
    /// than two names side by side.
    private func chooser<C: View>(icon: String, label: String, value: String,
                                  @ViewBuilder content: () -> C) -> some View {
        Menu {
            content()
        } label: {
            HStack(spacing: 9) {
                Image(systemName: icon).font(.system(size: 14))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 1) {
                    Text(label).font(.system(size: 8, weight: .heavy)).kerning(1.1)
                        .foregroundStyle(.tertiary)
                    Text(value).font(.system(size: 14, weight: .medium))
                        .lineLimit(1).minimumScaleFactor(0.75)
                }
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            .frame(minWidth: 150, alignment: .leading)
            // `.bordered` draws a capsule around this label, so a square hit
            // shape inside it is both the wrong shape and the wrong frame.
            .contentShape(.capsule)
        }
        .menuStyle(.button)
        .buttonStyle(.bordered)
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
