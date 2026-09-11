import SwiftUI

/// Every player, filtered down.
///
/// The board is organised around men you already own; this is the opposite
/// question. Filtering happens on the server so this view and the web board
/// cannot disagree about what "available" means, and each distinct query is
/// kept, so moving back to a filter you have already used costs nothing.
struct PlayersView: View {
    @Environment(Board.self) private var board
    @Binding var focus: String?

    @State private var pos = ""
    @State private var scope = ""
    @State private var query = ""
    /// How many rows are on screen. Paged rather than capped, so a long list
    /// is reachable without building six hundred headshots to show twelve.
    @State private var shown = 40

    /// The scopes that can be answered from what this install actually reads.
    /// A watchlist, trade targets and rookie watch are absent rather than
    /// stubbed: two of them need state nothing here keeps, and the third
    /// needs a rookie flag no feed here carries.
    private let scopes: [(String, String, String)] = [
        ("", "All players", "person.3"),
        ("mine", "My players", "star"),
        ("rostered", "Rostered", "checkmark.circle"),
        ("free", "Free agents", "plus.circle"),
        ("hurt", "Injury report", "cross.case"),
    ]

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            filters.frame(width: 210)
            table
        }
        .task { await reload() }
    }

    private func reload() async {
        shown = 40
        await board.loadUniverse(pos: pos, scope: scope, q: query)
    }

    // MARK: - filters

    private var filters: some View {
        VStack(spacing: 12) {
            Panel(title: "Players") {
                VStack(spacing: 5) {
                    ForEach(scopes, id: \.0) { key, label, icon in
                        Button {
                            scope = key
                            Task { await reload() }
                        } label: {
                            HStack(spacing: 9) {
                                Image(systemName: icon).font(.system(size: 12))
                                    .frame(width: 18)
                                Text(label).font(.system(size: 12))
                                Spacer(minLength: 0)
                                if let n = count(for: key) {
                                    Text("\(n)").font(.system(size: 10, weight: .semibold))
                                        .foregroundStyle(.tertiary).monospacedDigit()
                                }
                            }
                            .padding(.vertical, 7).padding(.horizontal, 10)
                            .plate(11, scope == key ? Theme.green.opacity(0.16)
                                                    : .white.opacity(0.04))
                            .foregroundStyle(scope == key ? AnyShapeStyle(Theme.green)
                                                          : AnyShapeStyle(.primary))
                        }
                        .buttonStyle(.plain).hoverEffect(.highlight)
                    }
                }
            }

            Panel(title: "Position") {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 56), spacing: 6)],
                          spacing: 6) {
                    posChip("", "ALL", board.universe?.total)
                    ForEach(["QB", "RB", "WR", "TE", "K", "DEF"], id: \.self) { p in
                        posChip(p, p, board.universe?.byPosition[p])
                    }
                }
            }
        }
    }

    /// Only the counts the payload actually reports. A scope whose size the
    /// server has not been asked for shows no number rather than a guess.
    private func count(for key: String) -> Int? {
        guard let u = board.universe else { return nil }
        return (key == scope) ? u.count : nil
    }

    private func posChip(_ key: String, _ label: String, _ n: Int?) -> some View {
        Button {
            pos = key
            Task { await reload() }
        } label: {
            VStack(spacing: 1) {
                Text(label).font(.system(size: 11, weight: .bold))
                if let n { Text("\(n)").font(.system(size: 9)).foregroundStyle(.tertiary) }
            }
            .frame(maxWidth: .infinity).padding(.vertical, 7)
            .plate(10, pos == key ? Theme.green.opacity(0.20) : .white.opacity(0.05))
            .foregroundStyle(pos == key ? AnyShapeStyle(Theme.green)
                                        : AnyShapeStyle(.primary))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    // MARK: - table

    private var table: some View {
        Panel(title: heading, trailing: AnyView(search)) {
            if board.universeLoading && board.universe == nil {
                HStack { Spacer(); ProgressView(); Spacer() }.padding(.vertical, 28)
            } else if let men = board.universe?.players, !men.isEmpty {
                VStack(spacing: 0) {
                    header
                    // The scroll view has to live here, with a bounded height.
                    // A LazyVStack inside a parent that offers unbounded
                    // height is not lazy at all: every row is built
                    // immediately, and with a headshot each that is several
                    // hundred image requests before the first frame.
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(men.prefix(shown)) { row($0) }
                        }
                        if men.count > shown {
                            Button("Show more") { shown += 60 }
                                .buttonStyle(.bordered).controlSize(.small)
                                .padding(.top, 10)
                        }
                    }
                    .frame(maxHeight: 560)
                    .scrollIndicators(.visible)
                    Text("\(min(shown, men.count)) of \(men.count)"
                         + (men.count > shown ? " · narrow it with a position or a search" : ""))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .padding(.top, 8)
                }
            } else {
                NoSource(what: "Nobody matches that.")
            }
        }
    }

    private var heading: String {
        let u = board.universe
        let n = u?.count ?? 0
        let label = scopes.first { $0.0 == scope }?.1 ?? "All players"
        return "\(label) · \(n)"
    }

    private var search: some View {
        HStack(spacing: 7) {
            Image(systemName: "magnifyingglass").font(.system(size: 11))
                .foregroundStyle(.tertiary)
            TextField("Search players", text: $query)
                .textFieldStyle(.plain).font(.system(size: 12))
                .frame(width: 160)
                .onSubmit { Task { await reload() } }
            if !query.isEmpty {
                Button {
                    query = ""
                    Task { await reload() }
                } label: { Image(systemName: "xmark.circle.fill").font(.system(size: 11)) }
                    .buttonStyle(.plain).foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 11).padding(.vertical, 6)
        .background(Capsule().fill(.white.opacity(0.07)))
    }

    private var header: some View {
        HStack(spacing: 10) {
            Text("PLAYER").frame(maxWidth: .infinity, alignment: .leading)
            Text("POS").frame(width: 38, alignment: .leading)
            Text("OPP").frame(width: 70, alignment: .leading)
            Text("PROJ").frame(width: 50, alignment: .trailing)
            Text("LIVE").frame(width: 50, alignment: .trailing)
            Text("YOUR LEAGUES").frame(width: 96, alignment: .trailing)
            Text("STATUS").frame(width: 74, alignment: .trailing)
        }
        .font(.system(size: 8, weight: .heavy)).kerning(0.8)
        .foregroundStyle(.tertiary).padding(.vertical, 7).padding(.horizontal, 5)
    }

    private func row(_ p: UniversePlayer) -> some View {
        let fx = board.fixtures[p.team]
        let live = board.live?.players[p.id]
        return Button { focus = p.id } label: {
            HStack(spacing: 10) {
                HStack(spacing: 9) {
                    Headshot(url: p.img, name: p.name,
                             tint: Theme.position(p.pos), size: 28)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(p.name).font(.system(size: 12))
                            .lineLimit(1).minimumScaleFactor(0.7)
                        Text(p.team).font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Text(p.pos).font(.system(size: 10, weight: .heavy))
                    .foregroundStyle(Theme.position(p.pos))
                    .frame(width: 38, alignment: .leading)

                Text(fx?.line ?? "—").font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .frame(width: 70, alignment: .leading)

                Text(p.projected.map {
                    $0.formatted(.number.precision(.fractionLength(1))) } ?? "—")
                    .font(.system(size: 11)).monospacedDigit()
                    .foregroundStyle(.secondary)
                    .frame(width: 50, alignment: .trailing)

                Group {
                    if let s = live?.s, (fx?.state ?? "pre") != "pre" {
                        Text(s, format: .number.precision(.fractionLength(1)))
                            .foregroundStyle(s > 0 ? AnyShapeStyle(Theme.green)
                                                   : AnyShapeStyle(.secondary))
                    } else { Text("–").foregroundStyle(.tertiary) }
                }
                .font(.system(size: 12, weight: .semibold)).monospacedDigit()
                .frame(width: 50, alignment: .trailing)

                // Owned in N of your leagues, and how many of those are your
                // own team. Both are facts about your leagues, not the world.
                HStack(spacing: 5) {
                    if p.mine > 0 {
                        Text("\(p.mine) yours").font(.system(size: 9, weight: .heavy))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Theme.green.opacity(0.22), in: .capsule)
                            .foregroundStyle(Theme.green)
                    }
                    Text("\(p.owned)/\(board.universe?.leagues ?? 0)")
                        .font(.system(size: 10)).monospacedDigit()
                        .foregroundStyle(p.owned == 0 ? AnyShapeStyle(Theme.gold)
                                                      : AnyShapeStyle(.tertiary))
                }
                .frame(width: 96, alignment: .trailing)

                Text((p.status ?? "").isEmpty ? "—" : p.status!)
                    .font(.system(size: 9, weight: (p.status ?? "").isEmpty ? .regular : .heavy))
                    .foregroundStyle((p.status ?? "").isEmpty ? AnyShapeStyle(.tertiary)
                                                              : AnyShapeStyle(Theme.red))
                    .lineLimit(1)
                    .frame(width: 74, alignment: .trailing)
            }
            .padding(.vertical, 5).padding(.horizontal, 5)
            .plate(9, focus == p.id ? Theme.green.opacity(0.12) : .clear)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
        .revealsHologram(p.id)
    }
}
