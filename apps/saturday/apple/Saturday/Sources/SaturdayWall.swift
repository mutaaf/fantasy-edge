import SwiftUI
#if os(visionOS)
import StadiumKit
#endif

enum Route: Hashable {
    case game(String)
    case tabletop(String)
    case stadium(String)
}

/// View-state filters over flags the API already set. Choosing which games a
/// person is looking at is presentation; deciding what a game *is* stays on
/// the server.
enum WallFilter: String, CaseIterable, Identifiable {
    case all = "All", top25 = "Top 25", close = "Close", mine = "My teams"
    var id: String { rawValue }

    func keeps(_ g: Game, favorites: Set<String>) -> Bool {
        switch self {
        case .all: return true
        case .top25: return g.flags.ranked
        case .close: return g.flags.oneScore && g.status.state != "pre"
        case .mine: return favorites.contains(g.away.id) || favorites.contains(g.home.id)
        }
    }
}

struct SaturdayWall: View {
    @Environment(SaturdayStore.self) private var store
    #if os(visionOS)
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openImmersiveSpace) private var openImmersiveSpace
    @Environment(\.dismissWindow) private var dismissWindow
    @Environment(StadiumPassage.self) private var passage
    #endif
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var filter: WallFilter = .all
    @State private var path = NavigationPath()
    @State private var showSettings = false

    var body: some View {
        NavigationStack(path: $path) {
            content
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .game(let id): GameDetailView(gameID: id, path: $path)
                    case .tabletop(let id): SharedRendererPlaceholder(kind: .tabletop, game: store.game(id))
                    case .stadium(let id): SharedRendererPlaceholder(kind: .stadium, game: store.game(id))
                    }
                }
                #if !os(visionOS)
                .toolbar {
                    ToolbarItem(placement: .principal) { filterPicker.pickerStyle(.segmented).frame(maxWidth: 520) }
                    ToolbarItem(placement: .primaryAction) {
                        Button { showSettings = true } label: { Image(systemName: "gearshape") }
                            .accessibilityLabel("Settings")
                    }
                }
                .navigationBarTitleDisplayMode(.inline)
                #endif
        }
        #if os(visionOS)
        .ornament(attachmentAnchor: .scene(.bottom), contentAlignment: .top) {
            VStack(spacing: 6) {
                if store.isReplay { ReplayBar().frame(width: 1040) }
                HStack(spacing: 4) {
                    filterPicker.pickerStyle(.segmented).frame(width: 560)
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                        .frame(minWidth: Tokens.target, minHeight: Tokens.target)
                        .accessibilityLabel("Settings")
                }
            }
            .padding(8)
            .glassBackgroundEffect()
        }
        #else
        .safeAreaInset(edge: .bottom) {
            if store.isReplay {
                ReplayBar()
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
                    .padding(.horizontal, sizeClass == .regular ? 24 : 12)
                    .padding(.bottom, 4)
            }
        }
        #endif
        .sheet(isPresented: $showSettings) { SettingsSheet() }
        .onAppear {
            store.watch()
            // Screenshot and UI-test hook: `-openGame <event id>` opens a game.
            let defaults = UserDefaults.standard
            if let id = defaults.string(forKey: "openGame"), path.isEmpty { path.append(Route.game(id)) }
            // `-openTabletop <event id>` puts one game straight on the table.
            if let id = defaults.string(forKey: "openTabletop"), path.isEmpty { openTabletop(id) }
            #if os(visionOS)
            // `-openStadium <event id>` walks straight in: the table first,
            // because that is the door, then the space.
            if let id = defaults.string(forKey: "openStadium") {
                openWindow(id: "tabletop", value: id)
                let passage = passage, open = openImmersiveSpace, dismiss = dismissWindow
                Task { @MainActor in
                    try? await Task.sleep(for: .seconds(3))
                    await passage.enter(openSpace: open, dismissWindow: dismiss)
                }
            }
            #endif
        }
        .onDisappear { store.unwatch() }
    }

    /// The stadium lives in its own volume on visionOS; elsewhere the
    /// placeholder is still the honest answer.
    private func openTabletop(_ id: String) {
        #if os(visionOS)
        openWindow(id: "tabletop", value: id)
        #else
        path.append(Route.tabletop(id))
        #endif
    }

    private var filterPicker: some View {
        Picker("Filter", selection: $filter) {
            ForEach(WallFilter.allCases) { Text($0.rawValue).tag($0) }
        }
    }

    @ViewBuilder private var content: some View {
        if let slate = store.slate {
            layout(slate)
                .overlay(alignment: .bottom) {
                    if let error = store.error { ErrorBanner(text: error).padding() }
                }
        } else if let error = store.error {
            ContentUnavailableView {
                Label("No slate yet", systemImage: "wifi.exclamationmark")
            } description: {
                Text(error)
            } actions: {
                Button("Settings") { showSettings = true }.frame(minHeight: Tokens.target)
            }
        } else {
            ProgressView("Reading the slate…")
        }
    }

    @ViewBuilder private func layout(_ slate: Slate) -> some View {
        #if os(visionOS)
        VisionWall(slate: slate, filter: filter, path: $path, onTabletop: openTabletop)
        #else
        if sizeClass == .regular {
            PadWall(slate: slate, filter: filter, path: $path, onTabletop: openTabletop)
        } else {
            PhoneWall(slate: slate, filter: filter, path: $path, onTabletop: openTabletop)
        }
        #endif
    }
}

// MARK: - shared pieces

private struct WallHeader: View {
    @Environment(SaturdayStore.self) private var store
    let slate: Slate
    var compact = false

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 16) { title; Spacer(); pills }
            VStack(alignment: .leading, spacing: 10) {
                title
                // A phone gives the mark its own line: beside three count pills
                // it had neither its word nor their words in full.
                if let rebuilt = slate.reconstructed { RebuiltMark(rebuilt: rebuilt) }
                HStack(spacing: 8) { pills }
            }
        }
    }

    private var title: some View {
        HStack(alignment: .firstTextBaseline, spacing: 14) {
            Text("SATURDAY").font(Typeface.display(compact ? 40 : 52, .black)).tracking(1)
                .fixedSize(horizontal: true, vertical: false)
            Text(subtitle).font(Typeface.serif(compact ? 19 : 24)).foregroundStyle(.secondary)
                .contentTransition(.numericText())
                .fixedSize(horizontal: true, vertical: false)
            // On a phone the mark rides with the counts; beside the clock there
            // is not room for it and the word SATURDAY both.
            if !compact, let rebuilt = slate.reconstructed { RebuiltMark(rebuilt: rebuilt) }
        }
    }

    private var subtitle: String {
        if let clock = slate.clock { return "Replay · \(clock.label)" }
        return store.connection == .streaming ? "FBS · live" : "FBS"
    }

    @ViewBuilder private var pills: some View {
        CountPill(glyph: Glyph.live, text: "\(slate.counts.live) live", tint: Tokens.liveGlyph)
        if slate.counts.delayed > 0 { CountPill(glyph: Glyph.delayed, text: "\(slate.counts.delayed) delayed") }
        CountPill(glyph: "calendar", text: "\(slate.counts.pre) to come")
        CountPill(glyph: Glyph.final, text: "\(slate.counts.post) final")
    }
}

private struct CountPill: View {
    let glyph: String
    let text: String
    var tint: Color = .primary
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: glyph).foregroundStyle(tint)
            Text(text)
        }
        .font(Typeface.sans(15, .semibold))
        .lineLimit(1)
        .fixedSize(horizontal: true, vertical: false)
        .padding(.horizontal, 16).frame(minHeight: 44)
        .background(.white.opacity(0.08), in: Capsule())
    }
}

private struct ErrorBanner: View {
    let text: String
    var body: some View {
        Label(text, systemImage: "exclamationmark.triangle")
            .font(Typeface.sans(14, .medium))
            .padding(12)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14))
    }
}

private struct SectionBlock: View {
    @Environment(SaturdayStore.self) private var store
    let section: WallSection
    let filter: WallFilter
    var columns: Int
    var size: GameTile.Size = .regular
    @Binding var path: NavigationPath

    var body: some View {
        let games = store.games(in: section).filter { filter.keeps($0, favorites: store.favorites) }
        if !games.isEmpty {
            VStack(alignment: .leading, spacing: 14) {
                SectionHeading(title: section.title, overline: section.overline)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 20), count: columns), spacing: 14) {
                    ForEach(games) { g in
                        Button { path.append(Route.game(g.id)) } label: { GameTile(game: g, size: size) }
                            .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

private extension Slate {
    func section(_ id: String) -> WallSection? { sections.first { $0.id == id } }
}

// MARK: - visionOS: the window from the mockups

private struct VisionWall: View {
    @Environment(SaturdayStore.self) private var store
    let slate: Slate
    let filter: WallFilter
    @Binding var path: NavigationPath
    /// Opening the stadium is the wall's business, not a tile's: on visionOS
    /// it opens a volume, elsewhere it pushes the placeholder.
    let onTabletop: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            WallHeader(slate: slate)
            WhipAround(items: slate.feed) { path.append(Route.game($0)) }
            HStack(alignment: .top, spacing: 32) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        if let id = slate.spotlight, let g = store.game(id), filter.keeps(g, favorites: store.favorites) {
                            SpotlightCard(game: g, onDetail: { path.append(Route.game(id)) },
                                          onTabletop: { onTabletop(id) })
                        }
                        if let finals = slate.section("finals") {
                            SectionBlock(section: finals, filter: filter, columns: 2, path: $path)
                        }
                    }
                }
                .frame(width: 560)
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        ForEach(["closeLate", "rankedLive"], id: \.self) { id in
                            if let s = slate.section(id) { SectionBlock(section: s, filter: filter, columns: 3, path: $path) }
                        }
                        if let s = slate.section("live") { SectionBlock(section: s, filter: filter, columns: 4, size: .compact, path: $path) }
                        if let s = slate.section("upcoming") { SectionBlock(section: s, filter: filter, columns: 3, path: $path) }
                    }
                }
            }
        }
        .padding(.horizontal, 36).padding(.vertical, 30)
    }
}

// MARK: - iPad: two columns

private struct PadWall: View {
    @Environment(SaturdayStore.self) private var store
    let slate: Slate
    let filter: WallFilter
    @Binding var path: NavigationPath
    /// Opening the stadium is the wall's business, not a tile's: on visionOS
    /// it opens a volume, elsewhere it pushes the placeholder.
    let onTabletop: (String) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 24) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let id = slate.spotlight, let g = store.game(id), filter.keeps(g, favorites: store.favorites) {
                        SpotlightCard(game: g, compact: true, onDetail: { path.append(Route.game(id)) },
                                      onTabletop: { onTabletop(id) })
                    }
                    if let finals = slate.section("finals") {
                        SectionBlock(section: finals, filter: filter, columns: 1, path: $path)
                    }
                }
                .padding(.vertical)
            }
            .frame(width: 380)
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    WallHeader(slate: slate, compact: true)
                    WhipAround(items: slate.feed) { path.append(Route.game($0)) }
                    ForEach(["closeLate", "rankedLive", "live", "upcoming"], id: \.self) { id in
                        if let s = slate.section(id) { SectionBlock(section: s, filter: filter, columns: 2, path: $path) }
                    }
                }
                .padding(.vertical)
            }
        }
        .padding(.horizontal, 24)
        .background(Color.black)
    }
}

// MARK: - iPhone: one list, spotlight on top

private struct PhoneWall: View {
    @Environment(SaturdayStore.self) private var store
    let slate: Slate
    let filter: WallFilter
    @Binding var path: NavigationPath
    /// Opening the stadium is the wall's business, not a tile's: on visionOS
    /// it opens a volume, elsewhere it pushes the placeholder.
    let onTabletop: (String) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                WallHeader(slate: slate, compact: true)
                if let id = slate.spotlight, let g = store.game(id), filter.keeps(g, favorites: store.favorites) {
                    SpotlightCard(game: g, compact: true, onDetail: { path.append(Route.game(id)) },
                                  onTabletop: { onTabletop(id) })
                }
                WhipAround(items: slate.feed) { path.append(Route.game($0)) }
                ForEach(slate.sections) { s in
                    SectionBlock(section: s, filter: filter, columns: 1, path: $path)
                }
            }
            .padding(16)
        }
        .background(Color.black)
    }
}
