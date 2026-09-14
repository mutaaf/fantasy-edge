import SwiftUI

/// One game, in every state the API can put it in: pre, live, red zone,
/// overtime, delayed, final, upset. The tile reads flags; it never derives them.
struct GameTile: View {
    enum Size { case regular, compact }

    let game: Game
    var size: Size = .regular

    private var compact: Bool { size == .compact }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 6 : 10) {
            StatusLine(game: game, fontSize: compact ? 12 : 13)
            VStack(spacing: compact ? 5 : 8) {
                TeamRow(game: game, side: game.away, size: size)
                TeamRow(game: game, side: game.home, size: size)
            }
            if !compact { footer }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, compact ? 10 : 14)
        .frame(maxWidth: .infinity, minHeight: compact ? 100 : 172, alignment: .topLeading)
        .background(Tokens.plate, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .strokeBorder(border.color, lineWidth: border.width)
        }
        .opacity(game.flags.delayed ? 0.82 : 1)
        .contentShape(.hoverEffect, RoundedRectangle(cornerRadius: 22, style: .continuous))
        .hoverEffect()
        .accessibilityElement(children: .combine)
    }

    private var border: (color: Color, width: CGFloat) {
        if game.flags.redZone { return (Tokens.redFill, 2) }
        if game.flags.upset { return (Tokens.goldFill, 2) }
        if game.flags.overtime && game.status.state == "in" { return (.secondary, 2) }
        return (.white.opacity(0.1), 1)
    }

    @ViewBuilder private var footer: some View {
        if game.status.state == "in", !game.flags.delayed {
            HStack {
                Text(game.situation?.text ?? (game.status.halftime ? "Halftime" : ""))
                    .font(Typeface.sans(13, .semibold))
                Spacer(minLength: 8)
                badge
            }
            FieldBar(game: game)
        } else if game.status.state == "pre" {
            Text(game.venue.name).font(Typeface.sans(13)).foregroundStyle(.secondary).lineLimit(1)
        } else {
            HStack { Spacer(); badge }
        }
    }

    @ViewBuilder private var badge: some View {
        if game.flags.redZone {
            StateBadge(text: "Red zone", fill: Tokens.redFill, glyph: Glyph.redZone)
        } else if game.flags.upset {
            StateBadge(text: "Upset", fill: Tokens.goldFill, glyph: Glyph.upset)
        } else if game.flags.upsetAlert {
            StateBadge(text: "Upset alert", fill: Tokens.goldFill, glyph: Glyph.upset)
        } else if game.flags.overtime {
            StateBadge(text: game.status.overtimes > 1 ? "\(game.status.overtimes)OT" : "OT", fill: Tokens.otFill, glyph: Glyph.overtime)
        }
    }
}

struct StatusLine: View {
    let game: Game
    var fontSize: CGFloat = 13

    var body: some View {
        HStack(spacing: 6) {
            switch game.status.state {
            case "pre":
                Text(kickoff).foregroundStyle(.secondary)
            case "post":
                Image(systemName: Glyph.final)
                Text(game.status.detail)
            default:
                if game.flags.delayed {
                    Image(systemName: Glyph.delayed)
                    Text("Delayed")
                } else {
                    Image(systemName: Glyph.live).foregroundStyle(Tokens.liveGlyph)
                    Text(game.status.detail.replacingOccurrences(of: " - ", with: " · "))
                }
            }
            Spacer(minLength: 6)
            if let tv = game.tv { Text(tv).foregroundStyle(.secondary).lineLimit(1) }
        }
        .font(Typeface.sans(fontSize, .semibold))
    }

    private var kickoff: String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        guard let date = f.date(from: game.kickoff.replacingOccurrences(of: "Z", with: ":00Z")) ?? f.date(from: game.kickoff) else {
            return game.status.detail
        }
        return date.formatted(date: .omitted, time: .shortened)
    }
}

struct TeamRow: View {
    let game: Game
    let side: Side
    var size: GameTile.Size = .regular

    private var other: Side { side.id == game.away.id ? game.home : game.away }
    private var isFinal: Bool { game.status.state == "post" }
    private var lost: Bool { isFinal && (side.score ?? 0) < (other.score ?? 0) }

    var body: some View {
        HStack(spacing: 10) {
            TeamChip(abbr: side.abbr, fill: side.fill, hatch: side.hatch,
                     width: size == .compact ? 52 : 62, height: size == .compact ? 24 : 28,
                     fontSize: size == .compact ? 15 : 17)
            if let rank = side.rank {
                Text("#\(rank)").font(Typeface.sans(12, .semibold)).foregroundStyle(.secondary)
            }
            if size == .regular {
                Text(side.location).font(Typeface.sans(15, .medium)).lineLimit(1)
                    .foregroundStyle(lost ? .secondary : .primary)
            }
            Spacer(minLength: 4)
            if game.situation?.possession == side.id {
                Image(systemName: Glyph.possession).font(.system(size: 13)).accessibilityLabel("has the ball")
            }
            if game.status.state == "pre" {
                Text(side.record).font(Typeface.sans(13)).foregroundStyle(.secondary)
            } else {
                Text(side.score.map(String.init) ?? "–")
                    .font(Typeface.display(size == .compact ? 26 : 38, .heavy))
                    .monospacedDigit()
                    .foregroundStyle(lost ? .secondary : .primary)
            }
            if isFinal {
                Image(systemName: "arrowtriangle.left.fill").font(.system(size: 9))
                    .opacity(lost ? 0 : 1).accessibilityLabel(lost ? "" : "winner")
            }
        }
    }
}
