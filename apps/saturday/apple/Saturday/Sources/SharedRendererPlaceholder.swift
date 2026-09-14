import SwiftUI

// INTEGRATE: shared RealityKit Stadium and Tabletop renderers from
// fantasy-edge scene/replay branch. They draw GET /api/scene/{event}; this
// app deliberately builds neither, so the 3D exists once for both products.
// At integration these routes open that package's volume and immersive space.
struct SharedRendererPlaceholder: View {
    enum Kind { case tabletop, stadium }
    let kind: Kind
    let game: Game?

    var body: some View {
        ContentUnavailableView {
            Label(kind == .tabletop ? "Tabletop" : "Stadium", systemImage: kind == .tabletop ? Glyph.tabletop : Glyph.stadium)
                .font(Typeface.display(40, .heavy))
        } description: {
            VStack(spacing: 10) {
                if let game { Text("\(game.away.location) at \(game.home.location)").font(Typeface.serif(24)) }
                Text("The shared 3D renderer arrives at integration. It is being built once, for Saturday and Fantasy Edge together, from the same scene description, so it is not duplicated here.")
                    .font(Typeface.sans(16))
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 520)
            }
        }
    }
}

struct SettingsSheet: View {
    @Environment(SaturdayStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var host = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("127.0.0.1:8780", text: $host)
                        .autocorrectionDisabled()
                        #if !os(macOS)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        #endif
                } header: {
                    Text("API host")
                } footer: {
                    Text("Run `make serve` (fixtures) or `make replay` (the recorded Saturday) on your Mac, then enter its address and port.")
                }
                if let slate = store.slate {
                    Section("Source") {
                        LabeledContent("Source", value: slate.source)
                        LabeledContent("As of", value: slate.asOf)
                        Text(slate.leverageCaveat).font(Typeface.sans(13)).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { store.setHost(host); dismiss() }
                }
            }
        }
        .onAppear { host = store.host }
    }
}
