import SwiftUI

// MARK: - shared furniture

extension View {
    /// A control's rounded background and its hit shape, from one radius.
    ///
    /// These used to be two calls - a `RoundedRectangle` background and a
    /// separate `.contentShape(.rect)` - and on visionOS the content shape is
    /// also the *hover* shape. So every rounded row on this surface lit up
    /// under a square highlight, and because the system inflates the highlight
    /// slightly it overhung the corners of the card it was meant to be
    /// lighting. Two calls will drift again; one cannot.
    ///
    /// The radius is still per element rather than a token. The rows on this
    /// board are drawn at ten different radii, several a point apart, and
    /// collapsing them would change shapes that have already been looked at
    /// and approved - a different bug from the one this fixes.
    func plate(_ radius: CGFloat, _ fill: Color) -> some View {
        background(RoundedRectangle(cornerRadius: radius).fill(fill))
            .contentShape(.rect(cornerRadius: radius))
    }
}

/// A word on an opaque ground.
///
/// The only shape on this surface allowed to put colour underneath text.
/// Opaque is the whole point: `glassBackgroundEffect` is translucent over a
/// room this code cannot see, so a chip filled at 18% alpha meant its label
/// was really sitting on the wearer's wall - and gold-on-a-bright-wall
/// measures 1.02:1, which is invisible. White on a `Theme.*Fill` measures
/// 4.6:1 or better whatever the room, because the ground is painted rather
/// than borrowed. See `apple/contrast_check.py`.
struct Chip: View {
    var text: String = ""
    var systemImage: String? = nil
    var fill: Color = Theme.greenFill
    var size: CGFloat = 9

    var body: some View {
        HStack(spacing: 3) {
            if let s = systemImage {
                Image(systemName: s).font(.system(size: size - 1, weight: .black))
            }
            if !text.isEmpty {
                Text(text).font(.system(size: size, weight: .heavy)).kerning(0.4)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, text.isEmpty ? 4 : 6).padding(.vertical, 2)
        .background(fill, in: .capsule)
        .foregroundStyle(.white)
    }
}

/// A status as a chip: the glyph carries the meaning and the colour agrees
/// with it.
///
/// Ahead and behind used to be a green number and a red number, which failed
/// twice over - neither was legible over a bright room, and green against red
/// is the one pair a red-green colourblind reader cannot separate. An arrow up
/// beside an arrow down is separable by anybody, in any room.
struct MarkChip: View {
    let mark: Theme.Mark
    var text: String = ""
    var size: CGFloat = 9
    var body: some View {
        Chip(text: text, systemImage: mark.symbol, fill: mark.fill, size: size)
            .accessibilityLabel(Text(label))
    }
    private var label: String {
        switch mark {
        case .ahead: return "ahead"
        case .behind: return "behind"
        case .level: return "level"
        case .caution: return "worth a look"
        case .live: return "live"
        case .hurt: return "on the injury wire"
        }
    }
}

/// The smallest mark there is, for where a chip would out-weigh the number it
/// is qualifying. Only used where the words beside it already say which state
/// this is, so nothing rests on the colour alone.
struct MarkDot: View {
    let mark: Theme.Mark
    var size: CGFloat = 7
    var body: some View {
        Circle().fill(mark.fill).frame(width: size, height: size)
    }
}

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
            // Opaque, not a wash. The initials are white, and at 28% alpha
            // they were really white on whatever room was behind the glass.
            Circle().fill(tint)
            if let s = url, let u = URL(string: s) {
                AsyncImage(url: u) { img in
                    img.resizable().scaledToFill()
                } placeholder: { initials }
            } else { initials }
        }
        .frame(width: size, height: size)
        .clipShape(.circle)
        .overlay(Circle().stroke(tint, lineWidth: 1.5))
    }
    private var initials: some View {
        Text(name.split(separator: " ").prefix(2).compactMap { $0.first }
                 .map(String.init).joined())
            .font(.system(size: size * 0.36, weight: .bold))
            .foregroundStyle(.white)
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
            line("function", detail.how, mark: nil)
            // The caveat used to be gold text, which measured 1.02:1 against
            // a bright room - the most important sentence on the card and the
            // least readable thing on the surface. The warning is now a chip
            // and the sentence is ordinary ink.
            if let c = detail.caveat { line(nil, c, mark: .caution) }
        }
        .padding(18).frame(width: 320)
    }
    private func line(_ icon: String?, _ text: String,
                      mark: Theme.Mark?) -> some View {
        HStack(alignment: .top, spacing: 8) {
            if let m = mark {
                MarkChip(mark: m, size: 8).padding(.top, 1)
            } else if let icon {
                Image(systemName: icon).font(.system(size: 10))
                    .foregroundStyle(.tertiary).padding(.top, 2)
            }
            Text(text).font(.system(size: 11)).foregroundStyle(.secondary)
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
    /// `shape` is the figure's own outline. It has to be passed because the
    /// things that explain themselves are not all the same shape: a stat tile
    /// is a rounded block, a win probability is a ring, and a square hover
    /// highlight around a ring is a highlight sitting outside the thing it is
    /// lighting on all four corners.
    func explains(_ detail: StatDetail?,
                  in shape: AnyShape = AnyShape(.rect(cornerRadius: 12))) -> some View {
        ExplainedFigure(detail: detail, shape: shape) { self }
    }
}

private struct ExplainedFigure<C: View>: View {
    let detail: StatDetail?
    let shape: AnyShape
    @ViewBuilder let content: C
    @State private var open = false

    var body: some View {
        if let d = detail {
            Button { open = true } label: {
                content.contentShape(shape)
            }
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
    /// What the figure says, as a mark beside the label rather than as colour
    /// on the digits.
    ///
    /// The digits used to be tinted green or red. That is the one thing this
    /// surface must not do: the tint was the message, and the message was
    /// unreadable over a bright room - and green against red is exactly the
    /// pair a deuteranope cannot separate. Naming the state rather than the
    /// colour also stops a call site deciding twice what "green" meant here.
    var mark: Theme.Mark? = nil
    var detail: StatDetail? = nil

    var body: some View { face.explains(detail) }

    private var face: some View {
        VStack(spacing: 3) {
            Text(value).font(.system(size: 19, weight: .bold)).monospacedDigit()
                .foregroundStyle(.primary).lineLimit(1).minimumScaleFactor(0.6)
            HStack(spacing: 4) {
                if let m = mark { MarkChip(mark: m, size: 7) }
                Text(label).font(.system(size: 8, weight: .heavy)).kerning(0.7)
                    .foregroundStyle(.tertiary).lineLimit(1).minimumScaleFactor(0.7)
            }
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
            Circle().fill(tint)
            if let l = logo, let u = URL(string: l) {
                AsyncImage(url: u) { $0.resizable().scaledToFill() }
                    placeholder: { monogram }
            } else {
                monogram
            }
        }
        .frame(width: size, height: size)
        .clipShape(.circle)
        .overlay(Circle().stroke(.white.opacity(0.25), lineWidth: 1))
    }

    private var monogram: some View {
        Text(initials)
            .font(.system(size: size * 0.40, weight: .heavy))
            .foregroundStyle(.white)
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
    ///
    /// The brightness is solved for rather than set, because the monogram is
    /// white and the hue is whatever the name happened to hash to. At the old
    /// `brightness: 0.85` a team that landed on yellow gave 1.8:1 and its
    /// initials could not be read at all; `chipFill` puts every hue at the one
    /// luminance where white on it clears 4.5:1.
    private var tint: Color {
        var h: UInt64 = 5381
        for b in name.utf8 { h = (h &* 33) &+ UInt64(b) }
        return Theme.chipFill(hue: Double(h % 360) / 360.0)
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

    /// One sentence naming whose numbers a figure is made of.
    ///
    /// Built from the catalogue rather than written out per tile, so a source
    /// connected on the server names itself here with no change on this side,
    /// and two panels quoting the same arithmetic cannot come to credit
    /// different sources for it. Every projection-derived popover ends with
    /// this line - which is how a figure that has no room for a label on the
    /// tile still says whose it is.
    static func whose(_ board: Board) -> String {
        guard !board.loadedSources.isEmpty else {
            return "No projection source is loaded on the server, so this is "
                 + "the figure the league's own board shipped inline."
        }
        if board.projectionChoice == "consensus" {
            return "The projections are the consensus: the mean of the "
                 + "\(board.consensusN) sources loaded "
                 + "(\(board.loadedSources.map(\.label).formatted())). A "
                 + "source that is not loaded contributes nothing to it - it "
                 + "cannot produce a zero or a share of a mean."
        }
        let s = board.loadedSources.first { $0.source == board.projectionChoice }
        let credit = (s.map { $0.attribution.isEmpty ? "" : " - \($0.attribution)" }) ?? ""
        return "The projections are \(board.projectionLabel)'s\(credit). Pick "
             + "another source from the ornament and every figure on this "
             + "surface is rebuilt from it, not merely relabelled."
    }

    static func projected(_ board: Board) -> StatDetail {
        StatDetail(
            title: "Projected total",
            what: "Where this line-up is expected to finish the week.",
            how: "Points already banked, plus what is left of each starter's "
               + "projection scaled by how much of his game is still to play. "
               + whose(board),
            caveat: "Before kickoff it is entirely projection: the source's "
                  + "numbers, added up, with nothing yet decided.")
    }

    static func opponentProjected(_ board: Board) -> StatDetail {
        StatDetail(
            title: "Opponent's projected total",
            what: "The same arithmetic, run on the other side of your matchup.",
            how: "Their banked points plus the unplayed remainder of each of "
               + "their starters' projections. " + whose(board),
            caveat: "It assumes they leave the line-up they have set. A late "
                  + "swap for somebody on a bye moves this and nothing here "
                  + "will know until the feed does.")
    }

    static func margin(_ board: Board) -> StatDetail {
        StatDetail(
            title: "Margin",
            what: "Your projected total minus your opponent's.",
            how: "The two projections above, subtracted. " + whose(board),
            caveat: "Before kickoff this is a difference between two "
                  + "forecasts, not a lead - and a difference between two "
                  + "sources' forecasts changes when you change source.")
    }

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

    static func projectedRecord(_ board: Board) -> StatDetail {
        StatDetail(
            title: "This week's projected record",
            what: "How many of your matchups you are currently ahead in.",
            how: "One win for each league where your starters out-project "
               + "your opponent's, counted right now. " + whose(board),
            caveat: "This Sunday only. It is not a season forecast and it "
                  + "does not know your schedule. A matchup inside a point "
                  + "can flip on the source alone.")
    }

    static func totalProjected(_ board: Board) -> StatDetail {
        StatDetail(
            title: "Projected points, everywhere",
            what: "Every league's projected total for your team, added together.",
            how: "The sum of the projection for your starters in each "
               + "league. " + whose(board),
            caveat: "Leagues can score differently, so this is a total rather "
                  + "than a comparable figure.")
    }

    static func edge(_ board: Board) -> StatDetail {
        StatDetail(
            title: "Points over your opponents",
            what: "How far ahead of the field you are projected across everything.",
            how: "Your projection minus your opponent's in each league, added "
               + "up. " + whose(board),
            caveat: "A big edge in one league hides a deficit in another; the "
                  + "sum cannot tell you which.")
    }

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

    /// The one projection popover that can also report a disagreement, since
    /// it is the only one about a single man - a spread is a fact about a
    /// player, and a total's spread would be a sum of them pretending to be
    /// one.
    static func playerProjection(_ pick: ProjectionPick?,
                                 board: Board) -> StatDetail {
        let apart = pick?.spread.map {
            "The loaded sources are "
            + $0.formatted(.number.precision(.fractionLength(1)))
            + " points apart on him"
            + ($0 >= ProjectionPick.disputedAt
               ? ", which is enough to move him in or out of a line-up. "
               : ". ")
            + "The card below breaks the number down by source."
        }
        if pick?.fallback == true {
            return StatDetail(
                title: "Projection",
                what: "\(board.projectionLabel) has no number for him this "
                    + "week, so this is the figure the league's own board "
                    + "shipped inline.",
                how: "Substituted rather than left blank so the board can "
                   + "still be sized, and named so nobody reads it as "
                   + "\(board.projectionLabel)'s opinion of him.",
                caveat: apart)
        }
        return StatDetail(
            title: "Projection",
            what: "What he is projected for this week, "
                + "from \(pick?.label ?? board.projectionLabel).",
            how: whose(board),
            caveat: apart)
    }

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
