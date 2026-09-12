import SwiftUI

// The furniture that puts a name on a projection.
//
// The rule the placements follow: one attribution per surface, not one per
// figure. The ornament names the source for the whole console, a table names
// it once in its column head, and only the things that vary *per man* - a
// disagreement, a source that has no number for him - earn a mark on the row.
// A badge on every tile would be the same sentence forty times and would read
// as decoration within a minute.

/// Whose numbers these are, shouted small. Carries the count when it is a
/// consensus, because a mean that does not say how many agreed is the figure
/// on this surface most likely to be read as more authority than it has.
struct SourceTag: View {
    let text: String
    /// Opaque, because a tag is text and text needs a ground this code chose.
    /// Slate by default so an attribution reads as a caption rather than as a
    /// status; a `Theme.*Fill` when it is saying something.
    var fill: Color = Theme.positionFill("DEF")
    var body: some View {
        Chip(text: text, fill: fill, size: 8)
    }
}

/// How far apart the sources are on one man, where there is room for one mark.
///
/// Gold rather than red: two sources disagreeing is information, not a
/// warning. Drawn only above `ProjectionPick.disputedAt`, so a row that
/// carries it is one where the choice of source would actually change a
/// start/sit rather than a decimal.
struct SpreadChip: View {
    let spread: Double
    var compact = false
    var body: some View {
        HStack(spacing: 2) {
            Text("Δ").font(.system(size: compact ? 8 : 9, weight: .black))
            Text(spread, format: .number.precision(.fractionLength(1)))
                .font(.system(size: compact ? 8 : 9, weight: .heavy)).monospacedDigit()
        }
        .padding(.horizontal, compact ? 5 : 6).padding(.vertical, 2)
        // Opaque. At 20% alpha this was gold text on the wearer's wall, which
        // measured 1.02:1 - the mark meant to draw the eye was the least
        // visible thing on the row.
        .background(Theme.goldFill, in: .capsule)
        .foregroundStyle(.white)
        .help("The loaded sources are \(spread.formatted(.number.precision(.fractionLength(1)))) points apart on him.")
    }
}

/// The bottom ornament's third chooser.
///
/// Loaded sources, then the consensus once there are two of them to average,
/// then the ones that are not connected - present but disabled, each naming
/// what it is waiting on. Showing a pending source as selectable would open a
/// board with nothing on it and blame the players; leaving it out entirely
/// would suggest the app has two sources rather than two of five.
struct ProjectionMenu: View {
    @Environment(Board.self) private var board

    var body: some View {
        Group {
            if board.loadedSources.isEmpty {
                Button {} label: { Text("No projections loaded") }.disabled(true)
            } else {
                Section("Loaded") {
                    ForEach(board.loadedSources) { s in
                        Button { Task { await board.pickProjectionSource(s.source) } } label: {
                            if s.source == board.projectionChoice {
                                Label(s.label, systemImage: "checkmark")
                            } else { Text(s.label) }
                        }
                    }
                    if board.consensusOffered {
                        Button {
                            Task { await board.pickProjectionSource("consensus") }
                        } label: {
                            let name = "Consensus of \(board.consensusN)"
                            if board.projectionChoice == "consensus" {
                                Label(name, systemImage: "checkmark")
                            } else { Text(name) }
                        }
                    }
                }
            }
            if !board.pendingSources.isEmpty {
                Section("Not connected") {
                    ForEach(board.pendingSources) { s in
                        Button {} label: {
                            Text("\(s.label) — needs \(s.needs)")
                        }
                        .disabled(true)
                    }
                }
            }
        }
    }
}

/// Every loaded source's number for one man, the consensus, and the gap.
///
/// The natural home for the detail: a card already about one player has the
/// room to show the disagreement in full rather than compress it into a chip,
/// and this is the only place on the surface where a reader can see *why* the
/// picker matters. The pending sources are listed under it for the same reason
/// they are in the menu - so the absence reads as a licence, not as silence.
struct SourceBreakdown: View {
    let id: String
    /// The figure the payload already carried inline, so a man no source has
    /// still shows the number the rest of the board is sized by.
    let fallback: Double?
    @Environment(Board.self) private var board

    private var row: ProjectionRow? { board.projectionIndex[id] }

    var body: some View {
        Panel(title: "Projections", trailing: AnyView(scope)) {
            if board.loadedSources.isEmpty {
                NoSource(what: "No projection source is loaded on the server.")
            } else if row == nil {
                NoSource(what: "No source has a number for him this week"
                         + (fallback != nil
                            ? "; the board is sizing him by the league's own figure." : "."))
            } else {
                VStack(spacing: 9) {
                    ForEach(board.loadedSources) { s in line(s) }
                    if board.consensusOffered { Divider().opacity(0.2); consensus }
                    if let sp = row?.spread { spreadLine(sp) }
                    if !board.pendingSources.isEmpty { pending }
                }
            }
        }
    }

    private var scope: some View {
        Text(board.projectionWeek > 0
             ? "WEEK \(board.projectionWeek) · \(String(board.projectionSeason))" : "")
            .font(.system(size: 8, weight: .heavy)).kerning(0.8)
            .foregroundStyle(.tertiary)
    }

    /// The widest number on the card, so the bars are comparable rather than
    /// each filling its own row.
    private var ceiling: Double {
        max(1, (row?.by.values.max() ?? 0), row?.consensus ?? 0)
    }

    private func line(_ s: ProjectionSource) -> some View {
        let v = row?.by[s.source]
        let chosen = s.source == board.projectionChoice
        return HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(s.label).font(.system(size: 12, weight: chosen ? .bold : .regular))
                    if chosen { SourceTag(text: "SIZING THE BOARD", fill: Theme.greenFill) }
                }
                // Whose number it actually is. Sleeper publishes Rotowire's,
                // and a card that says "Sleeper" without saying that credits
                // the pipe rather than the analyst.
                if !s.attribution.isEmpty {
                    Text(s.attribution).font(.system(size: 9)).foregroundStyle(.tertiary)
                        .lineLimit(1).minimumScaleFactor(0.7)
                }
            }
            Spacer(minLength: 6)
            if let v {
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(.white.opacity(0.10))
                        Capsule().fill(chosen ? Theme.greenFill : Color.secondary.opacity(0.6))
                            .frame(width: max(3, g.size.width * min(1, v / ceiling)))
                    }
                }
                .frame(width: 76, height: 5)
                // Ink, not green. Which source is chosen is already said by
                // the chip on its name and by the bar's fill; tinting the
                // digits too would be saying it a third time in the one place
                // a bright room makes it unreadable.
                Text(v, format: .number.precision(.fractionLength(2)))
                    .font(.system(size: 13, weight: chosen ? .bold : .semibold))
                    .monospacedDigit()
                    .foregroundStyle(.primary)
                    .frame(width: 52, alignment: .trailing)
            } else {
                Text("no number for him").font(.system(size: 10))
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private var consensus: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text("Consensus").font(.system(size: 12,
                        weight: board.projectionChoice == "consensus" ? .bold : .regular))
                    if board.projectionChoice == "consensus" {
                        SourceTag(text: "SIZING THE BOARD", fill: Theme.greenFill)
                    }
                }
                Text("mean of the \(row?.n ?? board.consensusN) source"
                     + ((row?.n ?? board.consensusN) == 1 ? "" : "s")
                     + " that have him")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            Spacer(minLength: 6)
            Text(row?.consensus.map {
                $0.formatted(.number.precision(.fractionLength(2))) } ?? "—")
                .font(.system(size: 13, weight: .bold)).monospacedDigit()
                .frame(width: 52, alignment: .trailing)
        }
    }

    private func spreadLine(_ sp: Double) -> some View {
        HStack(spacing: 7) {
            SpreadChip(spread: sp)
            Text(sp >= ProjectionPick.disputedAt
                 ? "They are \(sp.formatted(.number.precision(.fractionLength(1)))) points apart on him - enough to move him in or out of a line-up."
                 : "They are \(sp.formatted(.number.precision(.fractionLength(1)))) points apart on him.")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var pending: some View {
        VStack(alignment: .leading, spacing: 3) {
            Divider().opacity(0.2).padding(.vertical, 2)
            ForEach(board.pendingSources) { s in
                Text("\(s.label) — needs \(s.needs)")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                    .lineLimit(1).minimumScaleFactor(0.7)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Where the sources actually disagree, on the men you are starting.
///
/// The reason the whole feature exists. Averaging two sources into one figure
/// hides exactly the cases worth looking at - ESPN and Sleeper do not agree on
/// who the second-best quarterback is this week - and a board that quietly
/// means one of them is a board that cannot tell you that. Scoped to your
/// starters because a disagreement about your flex is a decision and the same
/// disagreement about somebody's bench tight end is trivia.
struct DisagreementPanel: View {
    @Environment(Board.self) private var board
    @Binding var focus: String?
    @State private var all = false

    private var rows: [(ProjectionRow, Double)] { board.disagreements(in: board.league) }

    var body: some View {
        Group {
            if board.consensusOffered && !rows.isEmpty {
                Panel(title: "Where The Sources Disagree",
                      trailing: AnyView(SourceTag(text: board.loadedSources
                        .map { $0.label.uppercased() }.joined(separator: " · ")))) {
                    VStack(spacing: 0) {
                        header
                        ForEach(Array((all ? rows : Array(rows.prefix(5))).enumerated()),
                                id: \.offset) { _, pair in
                            row(pair.0, pair.1)
                        }
                        if rows.count > 5 {
                            Button(all ? "Fewer" : "All \(rows.count)") { all.toggle() }
                                .buttonStyle(.bordered).controlSize(.small)
                                .padding(.top, 8)
                        }
                        Text(note).font(.system(size: 9)).foregroundStyle(.tertiary)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 8)
                    }
                }
            }
        }
    }

    private var note: String {
        "Each source's own number and the positional rank it gives him, from "
        + "\(board.loadedSources.count) sources over \(board.projectionIndex.count) "
        + "players. With two sources the spread is a difference, not a "
        + "distribution: it says they disagree, not which one is right."
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("PLAYER").frame(maxWidth: .infinity, alignment: .leading)
            ForEach(board.loadedSources) { s in
                Text(s.label.uppercased()).frame(width: 84, alignment: .trailing)
            }
            Text("SPREAD").frame(width: 54, alignment: .trailing)
        }
        .font(.system(size: 8, weight: .heavy)).kerning(0.8)
        .foregroundStyle(.tertiary).padding(.vertical, 6).padding(.horizontal, 5)
    }

    private func row(_ r: ProjectionRow, _ spread: Double) -> some View {
        Button { focus = r.id } label: {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(r.name).font(.system(size: 12, weight: .medium))
                        .lineLimit(1).minimumScaleFactor(0.7)
                    HStack(spacing: 5) {
                        Chip(text: r.pos, fill: Theme.positionFill(r.pos), size: 8)
                        Text(r.team).font(.system(size: 9)).foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                ForEach(board.loadedSources) { s in
                    VStack(alignment: .trailing, spacing: 1) {
                        // The chosen source's column is marked by weight,
                        // not by hue: a green figure is unreadable over a
                        // bright room and this is a table of figures.
                        Text(r.by[s.source].map {
                            $0.formatted(.number.precision(.fractionLength(2))) } ?? "—")
                            .font(.system(size: 12,
                                weight: s.source == board.projectionChoice
                                        ? .heavy : .regular))
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                        // The rank each source gives him at his own position.
                        // This is the sharp end of the disagreement: two
                        // sources four tenths apart on a quarterback can still
                        // be naming a different QB2.
                        Text(board.posRanks(s.source)[r.id] ?? "—")
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                    }
                    .frame(width: 84, alignment: .trailing)
                }

                HStack(spacing: 0) {
                    Spacer(minLength: 0)
                    SpreadChip(spread: spread)
                }
                .frame(width: 54, alignment: .trailing)
            }
            .padding(.vertical, 6).padding(.horizontal, 5)
            .plate(9, focus == r.id ? Theme.green.opacity(0.12) : .clear)
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
        .revealsHologram(r.id)
    }
}
