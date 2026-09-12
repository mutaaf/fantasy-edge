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
/// This is the deepest surface the app has, and it is reached by a gesture
/// nothing advertises - a long press on a man, anywhere - so everything the
/// app genuinely knows about him is here rather than rationed across taps.
///
/// Nothing on it is derived twice. The season log, the ranks, the draft rows
/// and the nflverse opportunity block are the payload `/api/player/<id>`
/// already serves; the floor and the ceiling come off `Profile.playedWeeks`,
/// which is the same arithmetic the right-rail card quotes. A section with no
/// source says so and shows nothing.
struct PlayerHologram: View {
    let id: String
    /// The live cell, when he happens to be a starter in the matchup on
    /// screen. Absent when he was opened from the player universe or from a
    /// league's bench, and the leverage figures - his share of what is still
    /// in doubt - are the only part of the card that needs it.
    var cell: Cell?
    /// Supplied when the card is placed in the immersive space, where there is
    /// no sheet to dismiss.
    var onClose: (() -> Void)?

    init(cell: Cell, onClose: (() -> Void)? = nil) {
        self.id = cell.id
        self.cell = cell
        self.onClose = onClose
    }
    init(id: String, cell: Cell? = nil, onClose: (() -> Void)? = nil) {
        self.id = id
        self.cell = cell
        self.onClose = onClose
    }

    @Environment(Board.self) private var board
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var profile: Profile?
    /// Drives the one-off arrival: the rings spin up and the sections rise in
    /// sequence. Set once, in `onAppear`, so nothing here re-animates when the
    /// live poll lands a new number behind the sheet.
    @State private var arrived = false

    private var owner: RosteredPlayer? { board.roster.first { $0.id == id } }
    private var liveLine: LiveState? { board.live?.players[id] }

    private var name: String { cell?.name ?? profile?.name ?? "—" }
    private var pos: String { cell?.pos ?? profile?.pos ?? owner?.pos ?? "" }
    private var team: String { cell?.team ?? profile?.team ?? owner?.team ?? "" }
    private var img: String? {
        if let c = cell, !c.img.isEmpty { return c.img }
        return profile?.img ?? owner?.img
    }
    /// What he has scored, or nothing. A hologram opened on a Wednesday has no
    /// live line at all, and a bold 0.0 in the middle of the card would read
    /// as a bad afternoon rather than as a week that has not started.
    private var scored: Double? { cell?.scored ?? liveLine?.s }
    /// The chosen source's number for him, falling back to the cell the
    /// hologram was opened from - which is itself already sized by that
    /// source, so the two cannot disagree.
    private var pick: ProjectionPick? {
        board.projectionPick(id, fallback: owner?.projected)
    }
    private var projected: Double? {
        if let p = pick { return p.value }
        if let c = cell, c.projected > 0 { return c.projected }
        return owner?.projected
    }
    private var state: String? { cell?.state ?? liveLine?.g }

    var body: some View {
        ScrollView {
            VStack(spacing: 26) {
                head
                headline
                if let p = profile {
                    stage(0) { thisWeek(p) }
                    if !p.formats.isEmpty { stage(1) { formats(p.formats) } }
                    if let s = latestWithWeeks(p) { stage(2) { distribution(s, p) } }
                    if !seasons(p).isEmpty { stage(3) { seasonLog(seasons(p), pos: p.pos) } }
                    stage(4) { ranks(p) }
                    stage(5) { opportunity(p) }
                    if let c = p.career { stage(6) { career(c) } }
                    if !p.draft.isEmpty { stage(7) { draftHistory(p.draft) } }
                } else {
                    ProgressView().padding(.vertical, 30)
                }
                if cell != nil { stage(8) { whySized } }
            }
            .padding(.horizontal, 40)
            .padding(.bottom, 40)
        }
        .frame(minWidth: 700, minHeight: 640)
        .task { profile = await board.profile(id) }
        .onAppear { arrived = true }
        .overlay(alignment: .topTrailing) {
            Button { onClose?() ?? dismiss() } label: { Image(systemName: "xmark") }
                .buttonStyle(.borderless).padding(18)
        }
    }

    /// One section, rising into place a beat after the one above it.
    ///
    /// The stagger is the whole reason this feels like something opening
    /// rather than a sheet appearing, but it is a single opacity and offset
    /// per section driven by one state change - not an animation per row.
    /// Reduce Motion gets the finished composition with no transition at all.
    @ViewBuilder
    private func stage<C: View>(_ i: Int, @ViewBuilder _ body: () -> C) -> some View {
        if reduceMotion {
            body()
        } else {
            body()
                .opacity(arrived ? 1 : 0)
                .offset(y: arrived ? 0 : 26)
                .animation(.easeOut(duration: 0.42).delay(0.06 * Double(i) + 0.10),
                           value: arrived)
        }
    }

    /// Most recent season first.
    ///
    /// `suffix(5)` took the five newest but left them in the order the API
    /// sends them, which is oldest first - so the top line of the card was a
    /// season from five years ago and this year was at the bottom. What a
    /// player did last week is the reason you opened the card.
    private func seasons(_ p: Profile) -> [SeasonRow] {
        Array(p.seasons.filter(\.started).sorted { $0.season > $1.season }.prefix(6))
    }

    /// The newest season that actually carries a distribution.
    ///
    /// Not simply the newest with a `weekly` array on it. The current season
    /// arrives as a full slate of zeroes before a ball is kicked - fourteen
    /// weeks of nothing - and charting that drew a flat axis under a caption
    /// claiming he had failed to beat his 0.0 average. A series with no
    /// positive week is not a distribution, so it falls back to the last
    /// season that is one.
    private func latestWithWeeks(_ p: Profile) -> SeasonRow? {
        p.seasons.filter { ($0.weekly ?? []).contains { $0 > 0 } }
                 .max { $0.season < $1.season }
    }

    /// The head itself: no plate, no frame, lit from the position colour so it
    /// reads as a presence in the room rather than a sticker.
    ///
    /// The two rings are the theatre, and they are deliberately not a network
    /// of any kind - that motif belongs to the coming-soon screen, where there
    /// is no figure for it to be mistaken for. Here it would be drawing lines
    /// between numbers that have no relationship.
    private var head: some View {
        ZStack {
            Circle()
                .fill(Theme.position(pos).opacity(0.30))
                .frame(width: 230, height: 230)
                .blur(radius: 55)
            SpinRing(diameter: 268, dash: [2, 12], width: 1.2,
                     tint: Theme.position(pos).opacity(0.55),
                     seconds: 22, spinning: !reduceMotion)
            SpinRing(diameter: 226, dash: [30, 22], width: 1.6,
                     tint: Theme.position(pos).opacity(0.35),
                     seconds: 34, clockwise: false, spinning: !reduceMotion)
            AsyncImage(url: img.flatMap(URL.init(string:))) { phase in
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
        .frame(height: 276)
        .padding(.top, 18)
    }

    private var headline: some View {
        VStack(spacing: 10) {
            Text(name)
                .font(.system(size: 38, weight: .bold))
                .multilineTextAlignment(.center)
            HStack(spacing: 10) {
                Chip(text: pos, fill: Theme.positionFill(pos), size: 12)
                Text(team).font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)
                if let s = state {
                    if s == "RZ" {
                        Chip(text: "RED ZONE", fill: Theme.goldFill, size: 12)
                    } else {
                        Text(s).font(.system(size: 12, weight: .heavy))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            scoreline
        }
    }

    @ViewBuilder
    private var scoreline: some View {
        if let s = scored {
            HStack(alignment: .lastTextBaseline, spacing: 10) {
                Text(s, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 58, weight: .bold)).monospacedDigit()
                    .contentTransition(.numericText())
                if let pr = projected {
                    Text("of \(pr, format: .number.precision(.fractionLength(1))) projected")
                        .font(.system(size: 15)).foregroundStyle(.secondary)
                    // Whose projection, said beside the projection. This is
                    // the largest unattributed number the app had.
                    SourceTag(text: pick?.fallback == true
                              ? "LEAGUE" : board.projectionTag)
                }
            }
        } else if let pr = projected {
            HStack(alignment: .lastTextBaseline, spacing: 10) {
                Text(pr, format: .number.precision(.fractionLength(1)))
                    .font(.system(size: 58, weight: .bold)).monospacedDigit()
                Text("projected").font(.system(size: 15)).foregroundStyle(.secondary)
                SourceTag(text: pick?.fallback == true ? "LEAGUE" : board.projectionTag)
            }
        } else {
            NoSource(what: "No live line or projection for him this week.")
        }
    }

    // MARK: - this week, and what his own weeks say about it

    private func thisWeek(_ p: Profile) -> some View {
        let weeks = p.playedWeeks
        return section("THIS WEEK, AND HIS OWN RANGE") {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 12) {
                    figure(scored.map { fmt($0, 1) } ?? "—", "LIVE",
                           mark: (scored ?? 0) > 0 ? .live : nil)
                    figure(projected.map { fmt($0, 1) } ?? "—", "PROJECTED",
                           mark: (pick?.disputed == true) ? .caution : nil)
                    figure(p.percentileWeek(0.2).map { fmt($0, 1) } ?? "—", "FLOOR")
                    figure(p.percentileWeek(0.8).map { fmt($0, 1) } ?? "—", "CEILING")
                }
                bySource
                if weeks.isEmpty {
                    NoSource(what: "No games played, so there is no distribution "
                                 + "to take a floor and a ceiling from.")
                } else {
                    Text("Floor and ceiling are his own 20th and 80th percentile "
                         + "weeks across \(weeks.count) games actually played - "
                         + "nearest rank, not interpolated, and not a forecast. "
                         + "Weeks he did not play are excluded, because a zero "
                         + "for a man who was inactive is not a bad game.")
                        .font(.system(size: 11)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
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

    // MARK: - the distribution itself

    /// Every week of his most recent season, with his floor and his ceiling
    /// ruled across it.
    ///
    /// The two rules are computed over *every* season, not this one, which is
    /// why the caption says so: read as this season's own quintiles they would
    /// be wrong, and a chart that lets you read a line the wrong way is worse
    /// than one without the line.
    private func distribution(_ s: SeasonRow, _ p: Profile) -> some View {
        let weeks = s.weekly ?? []
        let peak = max(weeks.max() ?? 1, p.percentileWeek(0.8) ?? 1, 1)
        let plot: CGFloat = 104
        return section("WEEK BY WEEK · \(String(s.season))") {
            VStack(alignment: .leading, spacing: 7) {
                ZStack(alignment: .bottom) {
                    if let c = p.percentileWeek(0.8) {
                        rule(c / peak, plot, Theme.greenFill)
                    }
                    if let f = p.percentileWeek(0.2) {
                        rule(f / peak, plot, Theme.goldFill)
                    }
                    HStack(alignment: .bottom, spacing: 3) {
                        ForEach(Array(weeks.enumerated()), id: \.offset) { _, v in
                            RoundedRectangle(cornerRadius: 2)
                                .fill(v <= 0 ? AnyShapeStyle(Color.white.opacity(0.07))
                                      : AnyShapeStyle(v >= s.ppg
                                                      ? Theme.green
                                                      : Theme.green.opacity(0.42)))
                                .frame(height: max(2, plot * CGFloat(v / peak)))
                                .frame(maxWidth: .infinity)
                        }
                    }
                }
                .frame(height: plot)
                HStack(spacing: 3) {
                    ForEach(Array(weeks.enumerated()), id: \.offset) { i, _ in
                        Text("\(i + 1)").font(.system(size: 7))
                            .foregroundStyle(.tertiary)
                            .frame(maxWidth: .infinity)
                    }
                }
                Text("Weeks 1-\(weeks.count) of \(String(s.season)). Solid bars beat "
                     + "his \(fmt(s.ppg, 1)) average that season; a stub is a week with "
                     + "no points, which is usually a week he did not play. The two "
                     + "rules are the floor and ceiling above, taken across every "
                     + "season rather than this one.")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func rule(_ fraction: Double, _ plot: CGFloat, _ tint: Color) -> some View {
        Rectangle()
            .fill(tint)
            .frame(height: 1)
            .offset(y: -plot * CGFloat(min(1, max(0, fraction))))
            .frame(maxWidth: .infinity, alignment: .bottom)
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
                            .frame(width: 74, alignment: .leading)
                        // The field the rank was out of. A positional rank
                        // with no denominator is unreadable across seasons -
                        // WR24 of 60 and WR24 of 140 are not the same year.
                        Text(r.rank == nil ? "" : "of \(r.field)")
                            .font(.system(size: 10)).foregroundStyle(.tertiary)
                            .frame(width: 46, alignment: .leading)
                        Spacer()
                        num("\(r.weeks)", 44)
                        num(fmt(r.ppg, 1), 58)
                        num(fmt(r.total, 0), 64)
                        num(fmt(r.best, 1), 58)
                    }
                    .padding(.vertical, 9)
                    if r.id != rows.last?.id { Divider().opacity(0.25) }
                }
                HStack {
                    Spacer()
                    ForEach(["G", "PPG", "TOTAL", "BEST"], id: \.self) { h in
                        Text(h).font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.tertiary)
                            .frame(width: h == "TOTAL" ? 64 : (h == "G" ? 44 : 58),
                                   alignment: .trailing)
                    }
                }
                .padding(.top, 4)
            }
        }
    }

    /// Where he finished, in the words the API already puts on it. `label` is
    /// served rather than assembled here, so this cannot say WR12 about a row
    /// the rest of the app calls something else.
    @ViewBuilder
    private func ranks(_ p: Profile) -> some View {
        section("WHERE HE FINISHED") {
            if let rows = p.recentRanks, !rows.isEmpty {
                HStack(spacing: 10) {
                    ForEach(rows.sorted { $0.season > $1.season }, id: \.season) { r in
                        VStack(spacing: 3) {
                            Text(r.label).font(.system(size: 20, weight: .bold))
                                .foregroundStyle(rankTintText(r.rank))
                            Text("of \(r.field) · \(String(r.season))")
                                .font(.system(size: 9, weight: .heavy))
                                .foregroundStyle(.tertiary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .glassBackgroundEffect(in: .rect(cornerRadius: 14))
                    }
                }
            } else {
                NoSource(what: "No finishing ranks stored for him.")
            }
        }
    }

    // MARK: - opportunity

    /// What he is being given, rather than what it came to. All of it from
    /// nflverse, and absent in one piece when there is no row for him: half a
    /// block of opportunity metrics with the other half blank invites the
    /// reader to assume the blanks are zeroes.
    @ViewBuilder
    private func opportunity(_ p: Profile) -> some View {
        section("OPPORTUNITY · NFLVERSE") {
            if let o = p.opportunity {
                let tiles: [(String, String)] = [
                    ("GAMES", o.games.map(String.init) ?? "—"),
                    ("TARGETS", o.targets.map(String.init) ?? "—"),
                    ("CARRIES", o.carries.map(String.init) ?? "—"),
                    ("TGT SHARE", o.targetShare.map { fmt($0, 1) + "%" } ?? "—"),
                    ("AIR YDS SHARE", o.airYardsShare.map { fmt($0, 1) + "%" } ?? "—"),
                    ("WOPR", o.wopr.map { fmt($0, 2) } ?? "—"),
                    ("aDOT", o.adot.map { fmt($0, 1) } ?? "—"),
                    ("YAC", o.yac.map { fmt($0, 1) } ?? "—"),
                    ("PPG", o.ppg.map { fmt($0, 1) } ?? "—"),
                ]
                VStack(alignment: .leading, spacing: 8) {
                    // Chunked by hand rather than in a LazyVGrid: nine tiles
                    // is not a list, and a lazy container inside this scroll
                    // view is the pattern that has already cost this app a
                    // first frame once.
                    ForEach(Array(stride(from: 0, to: tiles.count, by: 5)), id: \.self) { s in
                        HStack(spacing: 8) {
                            ForEach(s..<min(s + 5, tiles.count), id: \.self) { i in
                                VStack(spacing: 3) {
                                    Text(tiles[i].1)
                                        .font(.system(size: 19, weight: .bold))
                                        .monospacedDigit()
                                        .lineLimit(1).minimumScaleFactor(0.6)
                                    Text(tiles[i].0)
                                        .font(.system(size: 8, weight: .heavy))
                                        .kerning(0.6)
                                        .foregroundStyle(.tertiary)
                                        .lineLimit(1).minimumScaleFactor(0.7)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 11)
                                .background(RoundedRectangle(cornerRadius: 13)
                                    .fill(.white.opacity(0.05)))
                            }
                            if s + 5 > tiles.count {
                                ForEach(0..<(s + 5 - tiles.count), id: \.self) { _ in
                                    Color.clear.frame(maxWidth: .infinity)
                                }
                            }
                        }
                    }
                    Text("WOPR weights his share of his team's targets and its air "
                         + "yards together. aDOT is how far downfield the average "
                         + "throw at him travels, and YAC is what he adds after it "
                         + "arrives. Season to date, from nflverse - not this week.")
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                NoSource(what: "No nflverse opportunity row for him this season. "
                             + "Nothing here is estimated in its place.")
            }
        }
    }

    private func career(_ c: Career) -> some View {
        section("CAREER, AS THIS DATABASE HAS IT") {
            HStack(spacing: 12) {
                figure(c.seasons.map(String.init) ?? "—", "SEASONS")
                figure(c.totalWeeks.map(String.init) ?? "—", "WEEKS PLAYED")
                figure(c.best.map { fmt($0, 1) } ?? "—", "BEST WEEK")
            }
            Text("Only the seasons you have pulled. It is a fact about your "
                 + "database, not about his career.")
                .font(.system(size: 10)).foregroundStyle(.tertiary)
        }
    }

    private func draftHistory(_ all: [DraftRow]) -> some View {
        // Newest draft first, for the same reason the season log is: the most
        // recent time he went off the board is the one that informs anything.
        let rows = Array(all.sorted { $0.season > $1.season }.prefix(6))
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
                            .frame(width: 74, alignment: .trailing)
                        Text(d.adp.map { "ADP \(fmt($0, 0))" } ?? "no ADP")
                            .font(.system(size: 11)).monospacedDigit()
                            .foregroundStyle(.tertiary)
                            .frame(width: 76, alignment: .trailing)
                        if let reach = d.reach {
                            Text("\(reach > 0 ? "+" : "")\(reach, format: .number.precision(.fractionLength(1)))")
                                .font(.system(size: 12)).monospacedDigit()
                                .frame(width: 54, alignment: .trailing)
                        } else {
                            Color.clear.frame(width: 54, height: 1)
                        }
                    }
                    .padding(.vertical, 9)
                    if d.id != rows.last?.id { Divider().opacity(0.25) }
                }
                // Positive reach means the pick came in before the market had
                // him. Said here because the sign is the half everybody gets
                // backwards, and the same sentence is in the Python.
                Text("Reach is ADP minus where he actually went, so a gold number "
                     + "is a pick made earlier than the board expected.")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                    .padding(.top, 6)
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
        guard let c = cell else { return "" }
        let share = (c.share * 100).formatted(.number.precision(.fractionLength(1)))
        let left = (c.remaining * 100).formatted(.number.precision(.fractionLength(0)))
        let sigma = c.sigma.formatted(.number.precision(.fractionLength(1)))
        return "He holds \(share)% of everything still in doubt in this matchup — "
             + "\(sigma) points of uncertainty, with \(left)% of his game left."
    }

    private func rankTint(_ rank: Int?) -> Color {
        guard let r = rank else { return .white.opacity(0.12) }
        if r <= 5 { return Theme.green.opacity(0.85) }
        if r <= 15 { return Theme.green.opacity(0.35) }
        return .white.opacity(0.12)
    }
    /// A rank's colour is the *cell* behind it, never the digits. The band is
    /// already drawn by `rankTint`; tinting the number too said the same thing
    /// again in the one form a bright room erases.
    private func rankTintText(_ rank: Int) -> Color { .primary }

    /// Every loaded source's number for him, in this card's own idiom
    /// rather than in a glass panel borrowed from the console.
    ///
    /// A card opened this large is the one place a reader has asked for the
    /// detail, so the disagreement is shown rather than summarised: the
    /// PROJECTED figure above is whichever source is sizing the board, and on
    /// a man the sources are apart on, that single number is a choice being
    /// made on the reader's behalf.
    @ViewBuilder
    private var bySource: some View {
        if board.loadedSources.isEmpty {
            NoSource(what: "No projection source is loaded on the server.")
        } else {
            let row = board.projectionIndex[id]
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    ForEach(board.loadedSources) { s in
                        let chosen = s.source == board.projectionChoice
                        figure(row?.by[s.source].map { fmt($0, 2) } ?? "—",
                               s.label.uppercased() + (chosen ? " · SIZING" : ""))
                    }
                    if board.consensusOffered {
                        figure(row?.consensus.map { fmt($0, 2) } ?? "—",
                               "CONSENSUS · \(row?.n ?? board.consensusN)")
                    }
                    if let sp = row?.spread {
                        figure(fmt(sp, 2), "SPREAD",
                               mark: sp >= ProjectionPick.disputedAt ? .caution : nil)
                    }
                }
                if !board.pendingSources.isEmpty {
                    Text(board.pendingSources
                            .map { "\($0.label) needs \($0.needs)" }
                            .joined(separator: " · ")
                         + ". Not loaded, so not averaged in - a source that "
                         + "cannot produce a number must not produce a zero.")
                        .font(.system(size: 11)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func fmt(_ v: Double, _ places: Int) -> String {
        v.formatted(.number.precision(.fractionLength(places)))
    }

    private func num(_ text: String, _ width: CGFloat) -> some View {
        Text(text).font(.system(size: 14, weight: .medium)).monospacedDigit()
            .frame(width: width, alignment: .trailing)
    }

    /// Same rule as `StatTile` on the console: the number is ink and the
    /// state is a mark beside its label, because a tinted 26pt figure is the
    /// largest unreadable thing a bright room can produce.
    private func figure(_ value: String, _ label: String,
                        mark: Theme.Mark? = nil) -> some View {
        VStack(spacing: 3) {
            Text(value).font(.system(size: 26, weight: .bold)).monospacedDigit()
                .foregroundStyle(.primary).lineLimit(1).minimumScaleFactor(0.6)
            HStack(spacing: 4) {
                if let m = mark { MarkChip(mark: m, size: 7) }
                Text(label).font(.system(size: 8, weight: .heavy)).kerning(0.7)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 14).fill(.white.opacity(0.05)))
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


/// One dashed ring, turning.
///
/// A rotation driven by a repeating `Animation` is handed to Core Animation
/// and costs nothing per frame on this side, which is the difference between
/// this and drawing the same ring in a `TimelineView`. It also stops on its
/// own: the sheet is torn down when it closes, and the animation with it.
private struct SpinRing: View {
    let diameter: CGFloat
    let dash: [CGFloat]
    let width: CGFloat
    let tint: Color
    let seconds: Double
    var clockwise: Bool = true
    var spinning: Bool = true
    @State private var turned = false

    var body: some View {
        Circle()
            .stroke(tint, style: StrokeStyle(lineWidth: width, dash: dash))
            .frame(width: diameter, height: diameter)
            .rotationEffect(.degrees(turned ? (clockwise ? 360 : -360) : 0))
            .animation(spinning
                       ? .linear(duration: seconds).repeatForever(autoreverses: false)
                       : nil,
                       value: turned)
            .onAppear { if spinning { turned = true } }
    }
}


// MARK: - reaching the hologram from anywhere

/// The man a hologram is up for. A one-field type only because `sheet(item:)`
/// wants something `Identifiable` and a bare player id string is not.
struct HologramTarget: Identifiable, Hashable {
    let id: String
}

/// Opening a player in depth, handed down the view tree.
///
/// Every rail on this surface draws players, and none of them owns the sheet.
/// Passing a closure down through eight views would have made each of them
/// know about a destination it has no other business with; an environment
/// action puts the knowledge in exactly two places - the view that presents
/// the sheet and the row that was pressed.
struct HologramReveal: Equatable {
    let open: (String) -> Void

    /// Always equal, and that is the point. `CommandView` builds a fresh
    /// closure on every body evaluation, and the live poll re-evaluates that
    /// body every five seconds; without this, an environment value that never
    /// compares equal would invalidate every player row on the surface on
    /// every tick, for an action whose behaviour never changes.
    static func == (a: HologramReveal, b: HologramReveal) -> Bool { true }
}

private struct HologramRevealKey: EnvironmentKey {
    static let defaultValue: HologramReveal? = nil
}

extension EnvironmentValues {
    var revealHologram: HologramReveal? {
        get { self[HologramRevealKey.self] }
        set { self[HologramRevealKey.self] = newValue }
    }
}

extension View {
    /// Make a player row or tile open his hologram on a long press.
    ///
    /// Applied over the row's existing `Button` rather than replacing it. The
    /// tap that was already there still selects him into the right rail; the
    /// press held past half a second additionally raises the hologram, so the
    /// two gestures cannot be mistaken for each other and neither swallows
    /// the other. Where the surrounding view has not offered a
    /// `revealHologram` action - the immersive space, for one - no gesture is
    /// installed at all rather than a dead one.
    func revealsHologram(_ id: String) -> some View {
        modifier(HologramGesture(id: id))
    }
}

private struct HologramGesture: ViewModifier {
    let id: String
    @Environment(\.revealHologram) private var reveal

    @ViewBuilder
    func body(content: Content) -> some View {
        if let reveal {
            content.simultaneousGesture(
                LongPressGesture(minimumDuration: 0.5)
                    .onEnded { _ in reveal.open(id) })
        } else {
            content
        }
    }
}
