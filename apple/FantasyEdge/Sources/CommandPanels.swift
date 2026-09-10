import SwiftUI

// MARK: - shared furniture

/// One glass panel with a title. Every card on this surface is one of these,
/// so they share edges, padding and type without each re-deciding.
struct Panel<C: View>: View {
    let title: String
    var badge: Int? = nil
    var trailing: AnyView? = nil
    @ViewBuilder var content: C

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Text(title).font(.system(size: 15, weight: .semibold))
                if let b = badge, b > 0 {
                    Text("\(b)").font(.system(size: 10, weight: .bold))
                        .padding(.horizontal, 7).padding(.vertical, 2)
                        .background(Theme.red, in: .capsule)
                }
                Spacer(minLength: 0)
                if let t = trailing { t }
            }
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassBackgroundEffect(in: .rect(cornerRadius: 22))
    }
}

/// A win probability, drawn as a ring. The number alone is a fact; the ring is
/// the same fact readable without reading.
struct ProbRing: View {
    let value: Double
    var size: CGFloat = 46

    private var tint: Color {
        value >= 0.6 ? Theme.green : (value <= 0.4 ? Theme.red : Theme.gold)
    }
    var body: some View {
        ZStack {
            Circle().stroke(.white.opacity(0.14), lineWidth: 4)
            Circle().trim(from: 0, to: max(0.001, min(1, value)))
                .stroke(tint, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(value, format: .percent.precision(.fractionLength(0)))
                .font(.system(size: size * 0.28, weight: .bold)).monospacedDigit()
        }
        .frame(width: size, height: size)
        .animation(.easeInOut(duration: 0.45), value: value)
    }
}

/// A headshot with the club's colour behind it, falling back to initials.
/// The API serves the URL; nothing is bundled.
struct Headshot: View {
    let url: String?
    let name: String
    let tint: Color
    var size: CGFloat = 42

    var body: some View {
        ZStack {
            Circle().fill(tint.opacity(0.28))
            if let s = url, let u = URL(string: s) {
                AsyncImage(url: u) { img in
                    img.resizable().scaledToFill()
                } placeholder: { initials }
            } else { initials }
        }
        .frame(width: size, height: size)
        .clipShape(.circle)
        .overlay(Circle().stroke(tint.opacity(0.55), lineWidth: 1.5))
    }
    private var initials: some View {
        Text(name.split(separator: " ").prefix(2).compactMap { $0.first }
                 .map(String.init).joined())
            .font(.system(size: size * 0.36, weight: .bold))
            .foregroundStyle(.white.opacity(0.85))
    }
}

/// An NFL club mark, built from the abbreviation. ESPN publishes these at a
/// stable path, which is why a slate with only abbreviations can still show
/// the badges.
struct ClubMark: View {
    let abbr: String
    var size: CGFloat = 26
    var body: some View {
        AsyncImage(url: URL(string:
            "https://a.espncdn.com/i/teamlogos/nfl/500/\(abbr.lowercased()).png")) { img in
            img.resizable().scaledToFit()
        } placeholder: {
            Text(abbr).font(.system(size: size * 0.34, weight: .heavy))
                .foregroundStyle(.secondary)
        }
        .frame(width: size, height: size)
    }
}

/// A label over a number. Used wherever a panel is a row of figures.
struct StatTile: View {
    let value: String
    let label: String
    var tint: Color = .primary
    var body: some View {
        VStack(spacing: 2) {
            Text(value).font(.system(size: 19, weight: .bold)).monospacedDigit()
                .foregroundStyle(tint).lineLimit(1).minimumScaleFactor(0.6)
            Text(label).font(.system(size: 8, weight: .heavy)).kerning(0.7)
                .foregroundStyle(.tertiary).lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }
}

/// Said out loud when a panel has no source rather than no data. The two are
/// different and a reader deserves to know which they are looking at.
struct NoSource: View {
    let what: String
    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: "info.circle").font(.system(size: 11))
            Text(what).font(.system(size: 11))
        }
        .foregroundStyle(.tertiary)
        .padding(.vertical, 6)
    }
}
