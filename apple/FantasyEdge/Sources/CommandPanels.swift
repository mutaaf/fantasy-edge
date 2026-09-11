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

/// Why a number is the number it is.
///
/// Several figures on this surface are derived in a way a reader would get
/// wrong by guessing: floor and ceiling are that man's own percentile weeks
/// rather than a forecast, "avg rank" changes meaning with the league count,
/// and a win probability is a share of the uncertainty that is *left* rather
/// than of the points already on the board. This is where that is said.
///
/// Nothing here is a new explanation. Every string is the derivation the code
/// beside it already performs, written out - inventing a rationale for a
/// number would be the same failure as inventing the number.
struct StatDetail {
    let title: String
    /// What the figure is, in a sentence.
    let what: String
    /// How it was arrived at.
    let how: String
    /// The thing that would make quoting it as settled fact wrong. Nil where
    /// there genuinely isn't one - an empty caveat would be furniture.
    var caveat: String? = nil
}

/// The card behind a number. Deliberately not a push: a projection is a
/// footnote, and a footnote that takes over the window loses the thing it was
/// a footnote to.
struct StatPopover: View {
    let detail: StatDetail
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(detail.title).font(.system(size: 15, weight: .bold))
            Text(detail.what).font(.system(size: 12))
                .fixedSize(horizontal: false, vertical: true)
            line("function", detail.how, .secondary)
            if let c = detail.caveat { line("exclamationmark.triangle", c, Theme.gold) }
        }
        .padding(18).frame(width: 320)
    }
    private func line(_ icon: String, _ text: String, _ tint: Color) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon).font(.system(size: 10)).foregroundStyle(tint)
                .padding(.top, 2)
            Text(text).font(.system(size: 11)).foregroundStyle(tint)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

extension View {
    /// Make one figure explain itself.
    ///
    /// The whole block becomes the hit target, not the digits: a number and
    /// its label are one thing to a reader, and a tap that only lands on the
    /// glyphs is a tap that mostly misses. A nil detail leaves the view
    /// exactly as it was, with no control on it at all.
    func explains(_ detail: StatDetail?) -> some View {
        ExplainedFigure(detail: detail) { self }
    }
}

private struct ExplainedFigure<C: View>: View {
    let detail: StatDetail?
    @ViewBuilder let content: C
    @State private var open = false

    var body: some View {
        if let d = detail {
            Button { open = true } label: { content.contentShape(.rect) }
                .buttonStyle(.plain).hoverEffect(.highlight)
                .popover(isPresented: $open) { StatPopover(detail: d) }
        } else {
            content
        }
    }
}

/// A label over a number. Used wherever a panel is a row of figures.
///
/// Tappable exactly when there is something more to say about the figure. A
/// tile with no `detail` stays a plain label rather than becoming a control
/// that opens an empty card: blanket tappability trains a reader to distrust
/// every affordance on the surface.
struct StatTile: View {
    let value: String
    let label: String
    var tint: Color = .primary
    var detail: StatDetail? = nil

    var body: some View { face.explains(detail) }

    private var face: some View {
        VStack(spacing: 2) {
            Text(value).font(.system(size: 19, weight: .bold)).monospacedDigit()
                .foregroundStyle(tint).lineLimit(1).minimumScaleFactor(0.6)
            Text(label).font(.system(size: 8, weight: .heavy)).kerning(0.7)
                .foregroundStyle(.tertiary).lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
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


/// A fantasy team's badge.
///
/// ESPN gives most teams an SVG, which no plain image view will rasterise, so
/// the server marks which badges are actually drawable. For the rest this
/// draws a monogram on a colour derived from the team's own name - stable, so
/// the same team is the same colour everywhere, and legible at the size a
/// standings row gives it, which a shrunken cartoon would not be.
struct TeamBadge: View {
    let name: String
    let logo: String?
    var size: CGFloat = 30

    var body: some View {
        ZStack {
            Circle().fill(tint.opacity(0.30))
            if let l = logo, let u = URL(string: l) {
                AsyncImage(url: u) { $0.resizable().scaledToFill() }
                    placeholder: { monogram }
            } else {
                monogram
            }
        }
        .frame(width: size, height: size)
        .clipShape(.circle)
        .overlay(Circle().stroke(tint.opacity(0.55), lineWidth: 1))
    }

    private var monogram: some View {
        Text(initials)
            .font(.system(size: size * 0.40, weight: .heavy))
            .foregroundStyle(.white.opacity(0.9))
            .minimumScaleFactor(0.5).lineLimit(1)
    }

    /// Up to two initials from the words that carry meaning.
    private var initials: String {
        let words = name.split(whereSeparator: { $0 == " " || $0 == "-" })
            .filter { !["the", "of", "and", "a"].contains($0.lowercased()) }
        let letters = words.compactMap { $0.first(where: \.isLetter) }
        if letters.isEmpty { return String(name.prefix(2)).uppercased() }
        return String(letters.prefix(2)).uppercased()
    }

    /// Hashed from the name so a team keeps its colour across every surface
    /// and every launch. Not random: the same string always lands here.
    private var tint: Color {
        var h: UInt64 = 5381
        for b in name.utf8 { h = (h &* 33) &+ UInt64(b) }
        return Color(hue: Double(h % 360) / 360.0, saturation: 0.55, brightness: 0.85)
    }
}


// MARK: - what each figure on this surface actually is

/// One place where every explained number is explained.
///
/// Written out here rather than beside each tile so the same figure cannot
/// come to mean two things in two panels - "proj points" on the league page
/// and "YOU" on the command centre are the same arithmetic, and a reader who
/// opens both should be told the same thing twice, not two different things.
///
/// Every sentence describes what the code in `Leverage.swift`, `Attention.swift`
/// or `API.swift` already does. None of it is a new claim.
enum Explain {

    static let projected = StatDetail(
        title: "Projected total",
        what: "Where this line-up is expected to finish the week.",
        how: "Points already banked, plus what is left of each starter's "
           + "projection scaled by how much of his game is still to play.",
        caveat: "Before kickoff it is entirely projection: the provider's "
              + "numbers, added up, with nothing yet decided.")

    static let opponentProjected = StatDetail(
        title: "Opponent's projected total",
        what: "The same arithmetic, run on the other side of your matchup.",
        how: "Their banked points plus the unplayed remainder of each of "
           + "their starters' projections.",
        caveat: "It assumes they leave the line-up they have set. A late "
              + "swap for somebody on a bye moves this and nothing here "
              + "will know until the feed does.")

    static let margin = StatDetail(
        title: "Margin",
        what: "Your projected total minus your opponent's.",
        how: "The two projections above, subtracted.",
        caveat: "Before kickoff this is a difference between two forecasts, "
              + "not a lead.")

    static let winProbability = StatDetail(
        title: "Win probability",
        what: "The chance you finish this week ahead.",
        how: "The projected margin divided by the combined standard "
           + "deviation of every starter's remaining game, read off a normal "
           + "curve. Each man's deviation is his position's full-game sigma "
           + "times the square root of the fraction of his game left, so a "
           + "finished player adds nothing to the uncertainty.",
        caveat: "It treats players as independent and uses one sigma per "
              + "position rather than one per man. It is a model, and it is "
              + "the same model the web board and the Python both run.")

    static let intensity = StatDetail(
        title: "How close it is",
        what: "How much of this matchup is still a question.",
        how: "Twice the smaller of the two win probabilities, so a coin flip "
           + "is 1 and a decided week is 0.",
        caveat: "It says the week is close, not that it is worth watching - "
              + "two bad teams can be very close.")

    static let pointsFor = StatDetail(
        title: "Points for",
        what: "What your team has scored this season.",
        how: "Read off the league's own standings, not recomputed here.")

    static let rostered = StatDetail(
        title: "Distinct players",
        what: "How many different men you roster.",
        how: "Counted once each across every league you follow, so a man you "
           + "own in three leagues is one player here.")

    static let leaguesFollowed = StatDetail(
        title: "Leagues",
        what: "The leagues this board is about.",
        how: "Everything the server sends. A league you have put away is not "
           + "counted, which is why hiding one changes this number.")

    static let projectedRecord = StatDetail(
        title: "This week's projected record",
        what: "How many of your matchups you are currently ahead in.",
        how: "One win for each league where your starters out-project your "
           + "opponent's, counted right now.",
        caveat: "This Sunday only. It is not a season forecast and it does "
              + "not know your schedule.")

    static let totalProjected = StatDetail(
        title: "Projected points, everywhere",
        what: "Every league's projected total for your team, added together.",
        how: "The sum of each league's own projection for your starters.",
        caveat: "Leagues can score differently, so this is a total rather "
              + "than a comparable figure.")

    static let edge = StatDetail(
        title: "Points over your opponents",
        what: "How far ahead of the field you are projected across everything.",
        how: "Your projection minus your opponent's in each league, added up.",
        caveat: "A big edge in one league hides a deficit in another; the "
              + "sum cannot tell you which.")

    /// The rank tile changes meaning with the league count, so its
    /// explanation has to as well - which is the whole reason it is here.
    static func rank(_ summary: (value: String, label: String),
                     leagues: Int) -> StatDetail {
        if leagues <= 1 {
            return StatDetail(
                title: "League rank",
                what: "Where your team sits in the table.",
                how: "The place the league's own standings give you.")
        }
        return StatDetail(
            title: "Average rank",
            what: "Your place in the table, averaged over your leagues.",
            how: "The mean of the rank each league reports for you. The "
               + "label says how many reported one when that is fewer than "
               + "all of them.",
            caveat: "An average across leagues of different sizes: fourth of "
                  + "twelve and fourth of eight are not the same fourth.")
    }

    static func tally(_ which: String) -> StatDetail {
        StatDetail(
            title: which,
            what: "How many of your leagues are in that state this week.",
            how: "Ahead is a win probability of 60% or better, behind is 40% "
               + "or worse, and in doubt is everything between. The three "
               + "add up to your league count, which is what lets a summary "
               + "stand in for the list.",
            caveat: "It is the same modelled probability as everywhere else "
                  + "on this surface, with the same assumptions.")
    }

    static let livePoints = StatDetail(
        title: "Live points",
        what: "What he has scored so far this week.",
        how: "From the shared live feed, which is the same snapshot every "
           + "viewer of this board gets.",
        caveat: "Providers restate points after a stat correction, so a "
              + "figure can move after his game has finished.")

    static let playerProjection = StatDetail(
        title: "Projection",
        what: "What he is projected for this week.",
        how: "The provider's own number, carried through unchanged.")

    /// Floor and ceiling are the two figures on this surface most likely to
    /// be read as a forecast, which they are not.
    static func floorCeiling(_ which: String, quantile: String,
                             games: Int) -> StatDetail {
        StatDetail(
            title: which,
            what: "A bad week and a good week for him, from his own record.",
            how: "His \(quantile) percentile score across the \(games) "
               + "games he has actually played.",
            caveat: "A percentile of what he has done, not a projection. "
                  + "Weeks he did not play are excluded, because a zero for "
                  + "a man who was inactive is not a bad game.")
    }

    static func exposure(_ n: Int, of leagues: Int) -> StatDetail {
        StatDetail(
            title: "Exposure",
            what: n == 1 ? "You roster him in one of your leagues."
                         : "You roster him in \(n) of your \(leagues) leagues.",
            how: "Counted off the ownership rows the board already carries "
               + "for every man you own anywhere.",
            caveat: n > 1
                ? "One afternoon decides \(n) of your weeks through him, "
                + "which is the reason this number is on the card at all."
                : nil)
    }

    static let record = StatDetail(
        title: "Record",
        what: "Your wins and losses this season, and your place in the table.",
        how: "The league's own standings, stored as the provider reported them.")
}
