import SwiftUI

/// The player card, as a hologram rather than a card.
///
/// ESPN's headshots are cut-out PNGs with a transparent surround, so on a
/// headset there is no reason to put one inside a rectangle: the head can float
/// in the room and the numbers can sit around it. A card border here would only
/// be drawing a box around something that already has an edge.
///
/// The detail is the default. A card that opens shallow and asks you to tap
/// again for the season log is a card that wastes the one gesture you gave it.
struct PlayerHologram: View {
    let cell: Cell
    /// Supplied when the card is placed in the immersive space, where there is
    /// no sheet to dismiss.
    var onClose: (() -> Void)?
    @Environment(Board.self) private var board
    @Environment(\.dismiss) private var dismiss
    @State private var profile: Profile?

    var body: some View {
        ScrollView {
            VStack(spacing: 26) {
                head
                headline
                if let p = profile {
                    if !p.formats.isEmpty { formats(p.formats) }
                    if !seasons(p).isEmpty { seasonLog(seasons(p), pos: p.pos) }
                    if !p.draft.isEmpty { draftHistory(p.draft) }
                } else {
                    ProgressView().padding(.vertical, 30)
                }
                whySized
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 40)
        }
        .frame(minWidth: 660, minHeight: 620)
        .task { profile = await board.profile(cell.id) }
        .overlay(alignment: .topTrailing) {
            Button { onClose?() ?? dismiss() } label: { Image(systemName: "xmark") }
                .buttonStyle(.borderless).padding(18)
        }
    }

    /// Most recent season first.
    ///
    /// `suffix(5)` took the five newest but left them in the order the API
    /// sends them, which is oldest first - so the top line of the card was a
    /// season from five years ago and this year was at the bottom. What a
    /// player did last week is the reason you opened the card.
    private func seasons(_ p: Profile) -> [SeasonRow] {
        Array(p.seasons.filter(\.started).sorted { $0.season > $1.season }.prefix(5))
    }

    /// The head itself: no plate, no frame, lit from the position colour so it
    /// reads as a presence in the room rather than a sticker.
    private var head: some View {
        ZStack {
            Circle()
                .fill(Theme.position(cell.pos).opacity(0.30))
                .frame(width: 230, height: 230)
                .blur(radius: 55)
            AsyncImage(url: URL(string: cell.img)) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFit()
                        .shadow(color: .black.opacity(0.45), radius: 22, y: 14)
                default:
                    Image(systemName: "person.crop.circle.fill")
                        .resizable().scaledToFit()
                        .foregroundStyle(.tertiary)
                }
            }
            .frame(width: 260, height: 260)
        }
        .frame(height: 250)
        .padding(.top, 18)
    }

    private var headline: some View {
        VStack(spacing: 10) {
            Text(cell.name)
                .font(.system(size: 38, weight: .bold))
                .multilineTextAlignment(.center)
            HStack(spacing: 10) {
                Text(cell.pos)
                    .font(.system(size: 12, weight: .heavy))
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Theme.position(cell.pos), in: Capsule())
                    .foregroundStyle(.black)
                Text(cell.team).font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)
                Text(cell.state == "RZ" ? "RED ZONE" : cell.state)
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(cell.state == "RZ" ? Theme.gold : .secondary)
            }
            HStack(alignment: .lastTextBaseline, spacing: 10) {
                Text(cell.scored, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 58, weight: .bold)).monospacedDigit()
                    .contentTransition(.numericText())
                Text("of \(cell.projected, format: .number.precision(.fractionLength(1))) projected")
                    .font(.system(size: 15)).foregroundStyle(.secondary)
            }
        }
    }

    private func formats(_ rows: [FormatRow]) -> some View {
        section("THIS WEEK, BY SCORING FORMAT") {
            HStack(spacing: 12) {
                ForEach(rows) { f in
                    VStack(spacing: 3) {
                        Text(f.points, format: .number.precision(.fractionLength(1)))
                            .font(.system(size: 22, weight: .bold)).monospacedDigit()
                        Text(f.name).font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .glassBackgroundEffect(in: .rect(cornerRadius: 14))
                }
            }
        }
    }

    private func seasonLog(_ rows: [SeasonRow], pos: String) -> some View {
        section("SEASON BY SEASON") {
            VStack(spacing: 0) {
                ForEach(rows) { r in
                    HStack {
                        Text(String(r.season)).font(.system(size: 15, weight: .semibold))
                            .frame(width: 62, alignment: .leading)
                        Text(r.rank.map { "\(pos)\($0)" } ?? "—")
                            .font(.system(size: 12, weight: .heavy))
                            .padding(.horizontal, 9).padding(.vertical, 3)
                            .background(rankTint(r.rank), in: Capsule())
                            .frame(width: 84, alignment: .leading)
                        Spacer()
                        num("\(r.weeks)", 46)
                        num(r.ppg.formatted(.number.precision(.fractionLength(1))), 62)
                        num(r.total.formatted(.number.precision(.fractionLength(0))), 68)
                        num(r.best.formatted(.number.precision(.fractionLength(1))), 62)
                    }
                    .padding(.vertical, 9)
                    if r.id != rows.last?.id { Divider().opacity(0.25) }
                }
                HStack {
                    Spacer()
                    ForEach(["G", "PPG", "TOTAL", "BEST"], id: \.self) { h in
                        Text(h).font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.tertiary)
                            .frame(width: h == "TOTAL" ? 68 : (h == "G" ? 46 : 62),
                                   alignment: .trailing)
                    }
                }
                .padding(.top, 4)
            }
        }
    }

    private func draftHistory(_ all: [DraftRow]) -> some View {
        // Newest draft first, for the same reason the season log is: the most
        // recent time he went off the board is the one that informs anything.
        let rows = Array(all.sorted { $0.season > $1.season }.prefix(5))
        return section("WHERE HE WENT, IN YOUR LEAGUES") {
            VStack(spacing: 0) {
                ForEach(rows) { d in
                    HStack(spacing: 12) {
                        Text(String(d.season)).font(.system(size: 13))
                            .foregroundStyle(.secondary).frame(width: 46, alignment: .leading)
                        Text(d.league ?? "—").font(.system(size: 14)).lineLimit(1)
                        Text("\(d.teams ?? 0)TM").font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.tertiary)
                        Spacer()
                        Text("R\(d.round ?? 0) P\(d.overall ?? 0)")
                            .font(.system(size: 14, weight: .semibold)).monospacedDigit()
                        if let reach = d.reach {
                            Text("\(reach > 0 ? "+" : "")\(reach, format: .number.precision(.fractionLength(1)))")
                                .font(.system(size: 12)).monospacedDigit()
                                .foregroundStyle(reach > 0 ? Theme.gold : Theme.green)
                                .frame(width: 54, alignment: .trailing)
                        }
                    }
                    .padding(.vertical, 9)
                    if d.id != rows.last?.id { Divider().opacity(0.25) }
                }
            }
        }
    }

    private var whySized: some View {
        section("WHY THIS SIZE") {
            Text(explanation).font(.system(size: 15)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var explanation: String {
        let share = (cell.share * 100).formatted(.number.precision(.fractionLength(1)))
        let left = (cell.remaining * 100).formatted(.number.precision(.fractionLength(0)))
        let sigma = cell.sigma.formatted(.number.precision(.fractionLength(1)))
        return "He holds \(share)% of everything still in doubt in this matchup — "
             + "\(sigma) points of uncertainty, with \(left)% of his game left."
    }

    private func rankTint(_ rank: Int?) -> Color {
        guard let r = rank else { return .white.opacity(0.12) }
        if r <= 5 { return Theme.green.opacity(0.85) }
        if r <= 15 { return Theme.green.opacity(0.35) }
        return .white.opacity(0.12)
    }

    private func num(_ text: String, _ width: CGFloat) -> some View {
        Text(text).font(.system(size: 14, weight: .medium)).monospacedDigit()
            .frame(width: width, alignment: .trailing)
    }

    private func section<C: View>(_ title: String,
                                  @ViewBuilder _ body: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.system(size: 10, weight: .heavy)).kerning(1.3)
                .foregroundStyle(.tertiary)
            body()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
