import SwiftUI

/// The spotlight game, lit by a bank of stadium lights: the design's one
/// ornament, and it has a job - it is how this game reads as lit, not merely
/// larger. Which game is the spotlight is the API's decision.
struct SpotlightCard: View {
    let game: Game
    var compact = false
    var onDetail: () -> Void = {}
    var onTabletop: () -> Void = {}
    @State private var flourish: Change?

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 10 : 13) {
            // The bank always burns over the big game; on a score it strobes.
            ZStack {
                LightBank(count: 14, dot: 9, lit: true).opacity(flourish?.kind == .score ? 0 : 1)
                if flourish?.kind == .score { LightBank(count: 14, dot: 9, lit: true) }
            }
            .frame(maxWidth: .infinity)

            VStack(alignment: .leading, spacing: 8) {
                SectionHeading(title: "The Big Game", overline: game.leverage.reasons.joined(separator: " · "), size: compact ? 24 : 30)
                ZStack(alignment: .leading) {
                    StatusLine(game: game, fontSize: 15).opacity(flourish == nil ? 1 : 0)
                    if let flourish {
                        ChangeBadge(change: flourish, game: game, size: 15)
                            .transition(.asymmetric(insertion: .push(from: .leading), removal: .opacity))
                    }
                }
            }
            VStack(spacing: 10) {
                BigTeam(game: game, side: game.away, compact: compact, lit: flourish?.kind == .score && flourish?.team == game.away.id)
                BigTeam(game: game, side: game.home, compact: compact, lit: flourish?.kind == .score && flourish?.team == game.home.id)
            }
            if let last = game.lastPlay {
                Text(last.text)
                    .font(Typeface.sans(compact ? 14 : 15)).foregroundStyle(.secondary)
                    .lineLimit(2)
                    .contentTransition(.opacity)
                    .animation(.easeInOut(duration: 0.3), value: last.text)
            }
            if let text = game.situation?.text {
                HStack {
                    Text(text).font(Typeface.display(compact ? 28 : 36, .heavy))
                    Spacer()
                    if game.flags.redZone { StateBadge(text: "Red zone", fill: Tokens.redFill, glyph: Glyph.redZone, size: 14) }
                }
                FieldBar(game: game, height: compact ? 24 : 34)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { buttons }
                VStack(alignment: .leading, spacing: 10) { buttons }
            }
            .font(Typeface.sans(17, .semibold))
        }
        .padding(compact ? 20 : 30)
        .background {
            ZStack {
                Tokens.plate
                RadialGradient(colors: [Tokens.lightBank.opacity(0.16), .clear], center: .top, startRadius: 0, endRadius: 320)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 30, style: .continuous)
                .strokeBorder(game.flags.redZone ? Tokens.redFill : .white.opacity(0.12), lineWidth: 2)
        }
        .modifier(Flourish(game: game, active: $flourish))
    }

    @ViewBuilder private var buttons: some View {
        Button(action: onTabletop) { Label("View in 3D", systemImage: Glyph.tabletop) }
            .buttonStyle(PillButtonStyle(primary: true))
        Button(action: onDetail) { Label("Game detail", systemImage: Glyph.score) }
            .buttonStyle(PillButtonStyle())
    }
}

private struct BigTeam: View {
    let game: Game
    let side: Side
    let compact: Bool
    var lit = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 14) {
            TeamChip(abbr: side.abbr, fill: side.fill, hatch: side.hatch,
                     width: compact ? 78 : 96, height: compact ? 36 : 44, fontSize: compact ? 21 : 26)
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let rank = side.rank {
                        Text("#\(rank)").font(Typeface.display(22, .bold)).foregroundStyle(.secondary)
                    }
                    Text(side.location).font(Typeface.sans(compact ? 18 : 22, .semibold)).lineLimit(1)
                        .minimumScaleFactor(0.75)
                }
                Text(side.record).font(Typeface.sans(14)).foregroundStyle(.secondary)
            }
            Spacer()
            if game.situation?.possession == side.id {
                Image(systemName: Glyph.possession).font(.system(size: 22)).accessibilityLabel("has the ball")
            }
            Text(side.score.map(String.init) ?? "–")
                .font(Typeface.display(compact ? 56 : 72, .black))
                .monospacedDigit()
                .contentTransition(reduceMotion ? .opacity : .numericText())
                .shadow(color: Tokens.lightBank.opacity(lit ? 0.8 : 0), radius: 18)
                .animation(reduceMotion ? .easeInOut(duration: 0.2) : .spring(response: 0.5, dampingFraction: 0.7), value: side.score)
        }
    }
}

struct SectionHeading: View {
    let title: String
    let overline: String
    var size: CGFloat = 26

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(title).font(Typeface.serif(size))
            Text(overline.uppercased())
                .font(Typeface.sans(12, .semibold)).tracking(1.6)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .accessibilityAddTraits(.isHeader)
    }
}
