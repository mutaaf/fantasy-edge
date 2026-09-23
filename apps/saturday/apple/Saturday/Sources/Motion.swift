import SwiftUI

// The motion spec: restraint in the tiles, spent on scoring plays. What
// changed is the API's answer (`Slate.changes`); this file only decides how
// it looks, and what it looks like when Reduce Motion is on.

extension Change.Kind {
    var glyph: String {
        switch self {
        case .score: return Glyph.score
        case .correction: return Glyph.correction
        case .lead: return Glyph.lead
        case .possession: return Glyph.possession
        case .kickoff: return Glyph.kickoff
        case .final: return Glyph.final
        case .upset: return Glyph.upset
        case .redZone: return Glyph.redZone
        case .delay: return Glyph.delayed
        case .resume: return Glyph.resume
        }
    }

    /// Which changes earn a flourish on a tile. Possession flips move the ball
    /// glyph instead, and a red zone already has its own badge and border.
    var flourishes: Bool {
        switch self {
        case .score, .correction, .lead, .final, .upset, .kickoff, .delay, .resume: return true
        case .possession, .redZone: return false
        }
    }

    /// How long a flourish holds. Scores hold longest: they are the news.
    var hold: Duration {
        switch self {
        case .score, .upset: return .seconds(5)
        case .correction, .final: return .seconds(4)
        default: return .seconds(3)
        }
    }
}

extension Change {
    /// The chip a change's badge sits on: the team's normalised fill when the
    /// change belongs to a team, otherwise a state token. White text clears
    /// 4.5:1 on all of them.
    func fill(in game: Game?) -> Color {
        switch kind {
        case .upset: return Tokens.goldFill
        case .redZone: return Tokens.redFill
        case .correction, .delay, .final, .kickoff, .resume: return Tokens.otFill
        case .score, .lead, .possession:
            if let side = game?.side(id: team) { return Color(hex: side.fill) }
            return Tokens.otFill
        }
    }

    func badgeText(in game: Game?) -> String {
        let abbr = game?.side(id: team)?.abbr
        switch kind {
        case .score, .lead: return [label, abbr].compactMap { $0 }.joined(separator: " · ")
        case .correction: return ["Off the board", abbr].compactMap { $0 }.joined(separator: " · ")
        default: return label
        }
    }
}

/// A flourish's badge: a slanted chip with a glyph and a word, like every state.
struct ChangeBadge: View {
    let change: Change
    let game: Game?
    var size: CGFloat = 12

    var body: some View {
        StateBadge(text: change.badgeText(in: game), fill: change.fill(in: game), glyph: change.kind.glyph, size: size)
            .accessibilityLabel(change.badgeText(in: game))
    }
}

/// The product's one ornament - a bank of stadium lights - coming up on a score.
/// With Reduce Motion the bank is simply lit for the hold, no strobe.
struct LightBank: View {
    var count = 14
    var dot: CGFloat = 7
    var lit: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var strobe = false

    var body: some View {
        HStack(spacing: dot) {
            ForEach(0..<count, id: \.self) { i in
                Circle()
                    .fill(Tokens.lightBank)
                    .frame(width: dot, height: dot)
                    .shadow(color: Tokens.lightBank.opacity(lit ? 0.9 : 0), radius: dot)
                    .opacity(lit ? (strobe && i.isMultiple(of: 2) ? 0.45 : 1) : 0)
            }
        }
        .accessibilityHidden(true)
        .task(id: lit) {
            guard lit, !reduceMotion else { strobe = false; return }
            // Three quick alternations, then hold: punchy and brief.
            for _ in 0..<6 {
                try? await Task.sleep(for: .milliseconds(110))
                strobe.toggle()
            }
            strobe = false
        }
    }
}

/// Plays a tile's newest unclaimed change once, then lets it go.
struct Flourish: ViewModifier {
    @Environment(SaturdayStore.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let game: Game
    @Binding var active: Change?

    func body(content: Content) -> some View {
        content
            .task(id: store.changes(for: game.id).map(\.id)) {
                let fresh = store.changes(for: game.id).filter { store.claim($0) }
                guard let lead = fresh.first(where: { $0.kind.flourishes }) else { return }
                withAnimation(reduceMotion ? .easeInOut(duration: 0.25) : .spring(response: 0.42, dampingFraction: 0.72)) {
                    active = lead
                }
                if store.favorites.contains(game.away.id) || store.favorites.contains(game.home.id) {
                    AccessibilityNotification.Announcement("\(game.away.abbr) \(game.away.score ?? 0), \(game.home.abbr) \(game.home.score ?? 0). \(lead.badgeText(in: game))").post()
                }
                try? await Task.sleep(for: lead.kind.hold)
                guard !Task.isCancelled else { return }
                withAnimation(.easeOut(duration: reduceMotion ? 0.25 : 0.6)) { active = nil }
            }
    }
}

/// The upset reveal: a gold border drawn around the tile once, then held.
struct UpsetSweep: View {
    let cornerRadius: CGFloat
    let revealing: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var progress: CGFloat = 1

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .trim(from: 0, to: progress)
            .stroke(Tokens.goldFill, style: StrokeStyle(lineWidth: 3, lineCap: .round))
            .onChange(of: revealing) { _, now in
                guard now, !reduceMotion else { return }
                progress = 0
                withAnimation(.easeInOut(duration: 0.9)) { progress = 1 }
            }
            .accessibilityHidden(true)
    }
}
