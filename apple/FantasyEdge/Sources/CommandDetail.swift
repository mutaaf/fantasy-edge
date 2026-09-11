import SwiftUI

extension CommandView {

    // MARK: - right: one player, in depth

    var rightRail: some View {
        ScrollView {
            // `board.defaultFocus` is scoped to the selected league, so
            // picking a league in the left rail moves this panel too. It used
            // to be the best man across every league at once, which is the
            // same man whichever league you chose - the right rail simply did
            // not react to the tap.
            if let id = focus ?? board.defaultFocus {
                PlayerPanel(id: id)
                    .id(id)                       // rebuild when the man changes
            } else {
                Panel(title: "Player") {
                    NoSource(what: "Tap a player to open him here.")
                }
            }
        }
        .scrollIndicators(.hidden)
    }
}

/// The card the whole board is really asking about.
///
/// The figures are split by how well founded they are. Points and projection
/// are reported. Floor and ceiling are *derived*, and labelled as such - they
/// are percentiles of what he has actually done week to week, not a model's
/// opinion. Opportunity comes from nflverse. Anything with no source is
/// missing rather than filled.
struct PlayerPanel: View {
    let id: String
    @Environment(Board.self) private var board
    @State private var p: Profile?
    @State private var tab = 0
    /// The way into the hologram that does not need a gesture to be
    /// discovered. Long pressing a row is the easter egg; a card already open
    /// on the man should not require you to guess it, so the same destination
    /// gets one visible control here.
    @Environment(\.revealHologram) private var reveal

    private var owner: RosteredPlayer? { board.roster.first { $0.id == id } }
    private var liveLine: LiveState? { board.live?.players[id] }

    var body: some View {
        VStack(spacing: 14) {
            header
            if let p { figures(p); ownership(p); insights(p) }
            else { Panel(title: "Loading") { NoSource(what: "Fetching his card…") } }
        }
        .task { p = await board.profile(id) }
    }

    private var header: some View {
        let pos = p?.pos ?? owner?.pos ?? ""
        let tint = Theme.position(pos)
        return VStack(spacing: 0) {
            HStack(spacing: 11) {
                if let l = p?.logo ?? owner?.logo, let u = URL(string: l) {
                    AsyncImage(url: u) { $0.resizable().scaledToFit() }
                        placeholder: { Color.clear }
                        .frame(width: 34, height: 34)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(p?.name ?? owner?.name ?? "—")
                        .font(.system(size: 19, weight: .bold))
                        .lineLimit(1).minimumScaleFactor(0.6)
                    Text("\(pos) · \(p?.team ?? owner?.team ?? "")")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if let reveal {
                    Button { reveal.open(id) } label: {
                        Image(systemName: "cube.transparent")
                            .font(.system(size: 15))
                            .foregroundStyle(Theme.green)
                            .padding(7)
                            .background(Circle().fill(Theme.green.opacity(0.14)))
                            .contentShape(.circle)
                    }
                    .buttonStyle(.plain).hoverEffect(.lift)
                    .help("Open him as a hologram")
                }
            }
            .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 10)

            // The man, as large as the panel allows, lit from behind rather
            // than pasted onto a colour. A flat fill the width of the panel
            // reads as a green block with a head on it; a radial fall-off
            // reads as a spotlight, which is what it is meant to be.
            ZStack {
                RadialGradient(colors: [tint.opacity(0.42), tint.opacity(0.10), .clear],
                               center: .center, startRadius: 8, endRadius: 130)
                // The club, faint and behind him - identity without a label.
                if let l = p?.logo ?? owner?.logo, let u = URL(string: l) {
                    AsyncImage(url: u) { $0.resizable().scaledToFit() }
                        placeholder: { Color.clear }
                        .frame(width: 190, height: 190)
                        .opacity(0.10)
                }
                if let img = p?.img ?? owner?.img, let u = URL(string: img) {
                    AsyncImage(url: u) { i in
                        i.resizable().scaledToFit()
                    } placeholder: {
                        ProgressView().controlSize(.small)
                    }
                    .frame(height: 168)
                    .shadow(color: .black.opacity(0.45), radius: 12, y: 6)
                }
            }
            .frame(height: 168)
            .clipped()
        }
        .frame(maxWidth: .infinity)
        .glassBackgroundEffect(in: .rect(cornerRadius: 22))
    }

    /// Live, projected, and a floor and ceiling derived from his own weeks.
    private func figures(_ p: Profile) -> some View {
        let weeks = p.playedWeeks
        return Panel(title: "This Week") {
            HStack(spacing: 6) {
                StatTile(value: (liveLine?.s ?? 0)
                            .formatted(.number.precision(.fractionLength(1))),
                         label: "LIVE",
                         // Green means "he has done something". Before kickoff
                         // that is a lie told in colour.
                         tint: (liveLine?.s ?? 0) > 0 ? Theme.green : .primary,
                         detail: Explain.livePoints)
                StatTile(value: (owner?.projected ?? 0)
                            .formatted(.number.precision(.fractionLength(1))),
                         label: "PROJECTED",
                         detail: Explain.playerProjection)
                // Only explained when there is a distribution behind them. A
                // man with no games played shows a dash, and a dash has
                // nothing to open.
                StatTile(value: pct(p, 0.2), label: "FLOOR",
                         detail: weeks.isEmpty ? nil
                            : Explain.floorCeiling("Floor", quantile: "20th",
                                                   games: weeks.count))
                StatTile(value: pct(p, 0.8), label: "CEILING",
                         detail: weeks.isEmpty ? nil
                            : Explain.floorCeiling("Ceiling", quantile: "80th",
                                                   games: weeks.count))
            }
            if !weeks.isEmpty {
                Text("Floor and ceiling are his own 20th and 80th percentile weeks "
                     + "across \(weeks.count) games played - not a projection.")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
    }

    /// The distribution behind the floor and the ceiling lives on `Profile`
    /// now, so this card and the hologram cannot come to disagree about what
    /// a 20th percentile week is.
    private func pct(_ p: Profile, _ q: Double) -> String {
        p.percentileWeek(q)?.formatted(.number.precision(.fractionLength(1))) ?? "—"
    }

    /// Where he sits in your leagues, and whether he is in the line-up. Real,
    /// and the reason a cross-league board is worth having.
    private func ownership(_ p: Profile) -> some View {
        // "Owned in 1 of 1 leagues" is a ratio doing the work of a yes. With
        // one league the only question is whether he is yours.
        let mine = owner?.exposure ?? 0
        return Panel(title: board.scale.single
                     ? (mine > 0 ? "On your roster" : "Not on your roster")
                     : "Owned in \(mine) of \(board.leagues.count) leagues") {
            VStack(spacing: 7) {
                if (owner?.leagues ?? []).isEmpty {
                    NoSource(what: "Not rostered in any league you follow.")
                }
                ForEach(Array((owner?.leagues ?? []).enumerated()), id: \.offset) { _, o in
                    // A row naming a league leads to that league. Tappable
                    // only when the board is actually carrying it: a league
                    // you have hidden still appears in his ownership, and a
                    // tap that selected one the rails cannot show would take
                    // you nowhere.
                    let reachable = o.id.map { id in
                        board.leagues.contains { $0.id == id }
                    } ?? false
                    LeagueLine(o: o, selected: o.id == board.league?.id,
                               tap: reachable ? { board.selected = o.id } : nil)
                }
            }
        }
    }

    /// Opportunity, not outcome. Fantasy points say what happened; targets,
    /// carries and share say what he was given, which is the half that
    /// carries into next week.
    private func insights(_ p: Profile) -> some View {
        Panel(title: "Key Insights") {
            VStack(alignment: .leading, spacing: 8) {
                if let r = p.recentRanks, !r.isEmpty {
                    ForEach(r.reversed(), id: \.season) { row in
                        bullet("Finished \(row.label) of \(row.field) in \(String(row.season))")
                    }
                }
                if let o = p.opportunity {
                    if let t = o.targets, t > 0, let g = o.games, g > 0 {
                        bullet("\(t) targets over \(g) games "
                               + "(\((Double(t) / Double(g)).formatted(.number.precision(.fractionLength(1)))) a game)")
                    }
                    if let c = o.carries, c > 0, let g = o.games, g > 0 {
                        bullet("\(c) carries over \(g) games "
                               + "(\((Double(c) / Double(g)).formatted(.number.precision(.fractionLength(1)))) a game)")
                    }
                    if let ts = o.targetShare, ts > 0 {
                        bullet("\(ts.formatted(.number.precision(.fractionLength(1))))% of his team's targets")
                    }
                    if let w = o.wopr, w > 0 {
                        bullet("WOPR \(w.formatted(.number.precision(.fractionLength(2)))) - his share of targets and air yards combined")
                    }
                    if let a = o.adot, a != 0 {
                        bullet("Average target \(a.formatted(.number.precision(.fractionLength(1)))) yards downfield")
                    }
                } else {
                    NoSource(what: "No nflverse opportunity data for him this season.")
                }
                if let d = p.draft.sorted(by: { $0.season > $1.season }).first,
                   let overall = d.overall {
                    bullet("Last drafted \(overall) overall in \(d.league ?? "your league")"
                           + (d.adp.map { ", ADP \($0.formatted(.number.precision(.fractionLength(0))))" } ?? ""))
                }
            }
        }
    }

    private func bullet(_ s: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Circle().fill(Theme.green).frame(width: 5, height: 5).padding(.top, 5)
            Text(s).font(.system(size: 11)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// One league a man is rostered in, on the player card.
///
/// Its own type only so the whole row can be one hit target with or without a
/// tap: writing it inline meant either a Button around everything or nothing,
/// and a hidden league has to render as a plain row rather than as a control
/// that leads to a board the app is not carrying.
private struct LeagueLine: View {
    let o: Ownership
    let selected: Bool
    let tap: (() -> Void)?

    var body: some View {
        if let tap {
            Button(action: tap) { face }
                .buttonStyle(.plain).hoverEffect(.highlight)
        } else {
            face
        }
    }

    private var face: some View {
        HStack(spacing: 8) {
            Text(o.league ?? "—").font(.system(size: 11))
                .lineLimit(1).minimumScaleFactor(0.7)
            Spacer(minLength: 4)
            Text((o.started == true) ? "START" : (o.slot ?? "BENCH"))
                .font(.system(size: 9, weight: .heavy))
                .padding(.horizontal, 7).padding(.vertical, 2)
                .background(((o.started == true) ? Theme.green : Color.secondary)
                    .opacity(0.22), in: .capsule)
                .foregroundStyle((o.started == true) ? Theme.green : .secondary)
        }
        .padding(.vertical, 5).padding(.horizontal, 9)
        // The plate lives on `face` rather than on the button, so the
        // tappable row and the plain one are the same shape - and so the
        // hover highlight cannot be a different shape from the row it lights.
        .plate(11, selected ? Theme.green.opacity(0.14) : .white.opacity(0.05))
    }
}
