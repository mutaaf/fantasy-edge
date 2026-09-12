import SwiftUI

/// The Intel tab.
///
/// It absorbed Moves. Waivers and trades were never a peer of intel - they are
/// two of the calls it makes, alongside start/sit, matchup edges, the injury
/// wire and league trends - so two adjacent placeholders were being shown
/// where one subject exists.
///
/// The computed findings *are* the product, not a fallback for people without
/// a key. Most readers will never add one, and the brief above is complete
/// without: every card carries the tables and functions it was computed from
/// and its own caveat, copied verbatim from the analysis that produced it. The
/// model-written summary is a sibling of that, drawn in different ink, and the
/// facts stay visible underneath it.
///
/// Three routes back it, and none of them is required for this view to be
/// worth opening. `/api/intel` is the brief; `/api/intel/models` says which
/// providers the server holds a key for; `/api/intel/narrate` checks prose
/// against the numbers that were computed. A 404 on any of them is a sentence
/// on the screen rather than a broken tab.
struct IntelView: View {
    @Environment(Board.self) private var board
    /// Which sub-tab. Nil is "All", which is also where an unrecognised
    /// selection lands - see `active`.
    @State private var section: IntelSection?
    /// Which groups the reader has unfolded. Per group rather than one flag,
    /// so opening League Insights does not also unroll ten roster conflicts.
    @State private var opened: Set<String> = []

    var body: some View {
        VStack(spacing: 12) {
            header
            ScrollView {
                // Deliberately a plain VStack. A lazy one here would be handed
                // unbounded height by this scroll view, which defeats the
                // laziness and builds every row at once anyway - the bug that
                // once pegged this app at 18% of a core with no first frame.
                // The server caps the brief at twelve findings, so there is
                // nothing here that wants laziness.
                VStack(spacing: 14) {
                    summary
                    if board.intel != nil { findings } else { withoutBrief }
                    notes
                    notSourced
                }
                .padding(.bottom, 10)
            }
            .scrollIndicators(.hidden)
        }
        // The only place either fetch is triggered. The brief has a life of
        // its own on the board and returns immediately when it is current, so
        // flipping between tabs costs nothing; the poll never touches it.
        .task {
            board.noteNarrationSeen()
            await board.loadIntel()
            await board.loadModels()
        }
    }

    // MARK: - what is showing

    /// Only the sub-tabs the data supports. The design this is modelled on had
    /// Waivers and Trades too; nothing in the engine produces either, and an
    /// empty tab is a worse answer than a missing one.
    private var sections: [IntelSection] {
        let present = Set(insights.map(\.section))
        return IntelSection.allCases.filter { present.contains($0) }
    }

    /// A selection that survived a refetch. A sub-tab whose last finding went
    /// away must not leave the reader looking at nothing with no way back.
    private var active: IntelSection? {
        guard let s = section, sections.contains(s) else { return nil }
        return s
    }

    /// Computed findings only.
    ///
    /// `origin` is a read-only property on the Python side precisely so model
    /// prose cannot be dressed as arithmetic; checking it here is the same
    /// guarantee held on this end, and it is cheap.
    private var insights: [IntelInsight] {
        (board.intel?.insights ?? []).filter(\.computed)
    }

    private var shown: [IntelInsight] {
        guard let s = active else { return insights }
        return insights.filter { $0.section == s }
    }

    // MARK: - header

    private var header: some View {
        Panel(title: board.intel.map { "Week \($0.week) Intel" } ?? "Intel",
              trailing: AnyView(refresh)) {
            VStack(alignment: .leading, spacing: 11) {
                Text(headline)
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if !sections.isEmpty { switcher }
            }
        }
    }

    private var headline: String {
        guard board.intel != nil else {
            return "The computed brief comes from your own database, on the Mac."
        }
        let n = insights.count
        return (n == 1 ? "One finding, " : "\(n) findings, ")
            + "computed from rows already in your database. Each carries the "
            + "tables it came from and the caveat the analysis shipped with."
    }

    private var refresh: some View {
        HStack(spacing: 8) {
            if let at = board.briefWrittenAt, !board.intelLoading {
                Text(at, format: .dateTime.hour().minute())
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                    .monospacedDigit()
            }
            Button {
                Task { await board.loadIntel(force: true) }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "arrow.clockwise").font(.system(size: 10))
                    Text(board.intelLoading ? "Reading…" : "Refresh")
                        .font(.system(size: 10, weight: .semibold))
                }
                .padding(.horizontal, 9).padding(.vertical, 5)
                .plate(9, .white.opacity(0.06))
            }
            .buttonStyle(.plain).hoverEffect(.highlight)
            .disabled(board.intelLoading)
        }
    }

    private var switcher: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 7) {
                pill(nil, "All", "square.grid.2x2", insights.count)
                ForEach(sections) { s in
                    pill(s, s.rawValue, s.icon,
                         insights.filter { $0.section == s }.count)
                }
            }
        }
    }

    private func pill(_ s: IntelSection?, _ label: String,
                      _ icon: String, _ count: Int) -> some View {
        let on = active == s
        return Button { section = s } label: {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 10))
                Text(label).font(.system(size: 11, weight: .semibold))
                // Inherits the pill's own colour at reduced opacity rather
                // than taking `.tertiary`: a grey count on the selected pill's
                // green ground disappears entirely against system glass in a
                // lit room, which is where this app is used.
                Text("\(count)").font(.system(size: 9, weight: .heavy))
                    .monospacedDigit().opacity(0.7)
            }
            .padding(.horizontal, 11).padding(.vertical, 7)
            .plate(11, on ? Theme.greenFill : .white.opacity(0.05))
            .foregroundStyle(on ? AnyShapeStyle(.white)
                                : AnyShapeStyle(.secondary))
        }
        .buttonStyle(.plain).hoverEffect(.highlight)
    }

    // MARK: - the findings

    /// How many cards a group draws before it folds.
    ///
    /// The server sends the whole brief - up to sixty-four findings - because
    /// deciding what exists is its job and deciding what to show is this one's.
    /// This install produces twenty-eight, and twenty-eight cards of dense
    /// figures in one scroll is a directory rather than a briefing. Bounded is
    /// also what every other long list on this surface does: the rail folds at
    /// four, the field's lanes at twelve.
    private static let fold = 8

    private var findings: some View {
        let key = active?.rawValue ?? "all"
        let open = opened.contains(key)
        let head = open ? shown : Array(shown.prefix(Self.fold))
        return Panel(title: active?.rawValue ?? "Findings", badge: shown.count) {
            VStack(spacing: 10) {
                if shown.isEmpty {
                    NoSource(what: "Nothing fired in this group this week. That "
                             + "is an answer, not a gap: every insight has a "
                             + "threshold, and none of them was crossed.")
                }
                ForEach(head) { card($0) }
                if shown.count > Self.fold {
                    Button {
                        if open { opened.remove(key) } else { opened.insert(key) }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: open ? "chevron.up" : "chevron.down")
                                .font(.system(size: 9, weight: .bold))
                            Text(open ? "Show fewer"
                                 : shown.count - Self.fold == 1
                                   ? "1 more finding"
                                   : "\(shown.count - Self.fold) more findings")
                                .font(.system(size: 11, weight: .medium))
                        }
                        .frame(maxWidth: .infinity).padding(.vertical, 7)
                        .plate(11, .white.opacity(0.05))
                    }
                    .buttonStyle(.plain).hoverEffect(.highlight)
                }
            }
        }
    }

    private func card(_ i: IntelInsight) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                Chip(text: i.kindLabel, fill: Theme.greenFill, size: 8)
                if !i.league.isEmpty {
                    Text(i.league).font(.system(size: 10))
                        .foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 4)
                // Said on every card rather than assumed from the layout. The
                // one thing a reader must never have to work out is which of
                // two adjacent paragraphs a model wrote.
                Label("COMPUTED", systemImage: "function")
                    .font(.system(size: 8, weight: .heavy)).kerning(0.6)
                    .foregroundStyle(.tertiary)
            }

            Text(i.title).font(.system(size: 14, weight: .bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(i.detail).font(.system(size: 12)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if !i.players.isEmpty { men(i) }
            if !i.facts.isEmpty {
                VStack(spacing: 4) { ForEach(i.facts) { fact($0) } }
            }
            if !i.caveat.isEmpty { caveat(i.caveat) }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .plate(16, .white.opacity(0.05))
    }

    /// The men an insight is about, as a way into the card this app already
    /// draws. A long press opens the hologram, the same gesture it means on
    /// every other surface.
    private func men(_ i: IntelInsight) -> some View {
        HStack(spacing: 7) {
            ForEach(i.players.prefix(5)) { p in
                HStack(spacing: 6) {
                    Headshot(id: p.id,
                             name: p.name, tint: Theme.positionFill(p.pos), size: 24)
                    VStack(alignment: .leading, spacing: 0) {
                        Text(p.name).font(.system(size: 10, weight: .semibold))
                            .lineLimit(1)
                        Text("\(p.pos) · \(p.team)")
                            .font(.system(size: 8)).foregroundStyle(.tertiary)
                    }
                }
                .padding(.vertical, 4).padding(.horizontal, 7)
                .plate(10, .white.opacity(0.05))
                .revealsHologram(p.id)
            }
            Spacer(minLength: 0)
        }
    }

    /// One number and the table or function it came from, on two lines.
    ///
    /// The source is drawn in full rather than truncated or tucked behind a
    /// tap. `Fact.__post_init__` refuses to construct a fact without one, for
    /// the same reason it is on screen: a plausible sentence nobody can check
    /// is the failure this whole layer is arranged against.
    private func fact(_ f: IntelFact) -> some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 1) {
                Text(f.label).font(.system(size: 10)).foregroundStyle(.secondary)
                Text(f.source)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 6)
            Text(f.figure).font(.system(size: 12, weight: .bold))
                .monospacedDigit()
        }
        .padding(.vertical, 5).padding(.horizontal, 9)
        .background(RoundedRectangle(cornerRadius: 9).fill(.white.opacity(0.04)))
    }

    /// Verbatim. Not shortened, not re-worded, not behind a disclosure - the
    /// Python copies an analysis's caveat character for character precisely so
    /// no layer downstream is the one that loses the qualification.
    private func caveat(_ text: String) -> some View {
        // The caveat is the sentence the Python copies verbatim so nothing
        // downstream loses the qualification - and it was set in the one
        // colour on the surface that measured 1.02:1. The warning is a chip
        // now; the sentence is ink.
        HStack(alignment: .top, spacing: 7) {
            MarkChip(mark: .caution, size: 8).padding(.top, 1)
            Text(text).font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - the model-written half

    private var summary: some View {
        Panel(title: "Summary", trailing: AnyView(freshness)) {
            VStack(alignment: .leading, spacing: 11) {
                if let n = board.narration, n.hasProse {
                    prose(n)
                } else if let note = board.narrationNote {
                    NoSource(what: note)
                } else {
                    NoSource(what: "Nothing here is written by a model unless "
                             + "you ask. The findings below are the whole "
                             + "product; a summary only re-orders them into "
                             + "sentences and is never a source.")
                }
                controls
                providers
                chatNote
            }
        }
    }

    private func prose(_ n: IntelNarration) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                Chip(text: "MODEL-WRITTEN", systemImage: "sparkles",
                     fill: Theme.goldFill, size: 8)
                Spacer(minLength: 4)
                Text(n.model.isEmpty ? n.provider : "\(n.provider) · \(n.model)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.tertiary).lineLimit(1)
            }
            // Serif, italic, and behind a rule. Every computed number on this
            // surface is set in the system face; nothing else in the app is
            // drawn like this, so the reader can tell at a glance which
            // paragraph is evidence and which is a retelling of it.
            Text(n.text)
                .font(.system(size: 15, design: .serif)).italic()
                .fixedSize(horizontal: false, vertical: true)
                .padding(.leading, 12)
                .overlay(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2).fill(Theme.gold.opacity(0.7))
                        .frame(width: 3)
                }
            Text(n.label).font(.system(size: 9)).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
            if !n.trustworthy { flags(n) }
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16).fill(Theme.gold.opacity(0.09)))
        .overlay(RoundedRectangle(cornerRadius: 16)
            .stroke(Theme.gold.opacity(0.32), lineWidth: 1))
    }

    /// What the server's check caught. Said out loud rather than quietly
    /// dropped: the figure is still in the sentence above, so hiding the flag
    /// would leave the reader with an uncheckable number and no warning.
    private func flags(_ n: IntelNarration) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if !n.unverified.isEmpty {
                flag("Figures in that text that were not computed: "
                     + n.unverified.joined(separator: ", ")
                     + ". Nothing on this page backs them.")
            }
            if !n.flaggedMetrics.isEmpty {
                flag("It reached for a metric we do not have: "
                     + n.flaggedMetrics.joined(separator: ", ")
                     + ". See “Not sourced” at the foot of this tab.")
            }
        }
        .padding(9)
        .background(RoundedRectangle(cornerRadius: 11).fill(Theme.red.opacity(0.12)))
    }

    private func flag(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 7) {
            Chip(systemImage: "exclamationmark.octagon.fill",
                 fill: Theme.redFill, size: 9)
            Text(text).font(.system(size: 10)).foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Whether the prose on screen cost an inference just now.
    ///
    /// On a headset that is battery and heat, and on a hosted key it is money,
    /// so it is not a detail: a reader who presses the button and gets the
    /// same paragraph back is entitled to know nothing was spent.
    private var freshness: some View {
        Group {
            if board.narrationRunning {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.mini)
                    Text("WRITING ON DEVICE")
                        .font(.system(size: 8, weight: .heavy)).kerning(0.8)
                        .foregroundStyle(.secondary)
                }
            } else if board.narration != nil {
                HStack(spacing: 6) {
                    Chip(text: board.narrationFresh ? "FRESH" : "REUSED",
                         fill: board.narrationFresh ? Theme.greenFill
                                                    : Theme.positionFill("DEF"),
                         size: 8)
                    if let at = board.narrationAt {
                        Text(at, format: .dateTime.hour().minute())
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                            .monospacedDigit()
                    }
                }
            }
        }
    }

    private var controls: some View {
        HStack(spacing: 9) {
            Button {
                Task { await board.narrate() }
            } label: {
                Label(board.narrationCurrent ? "Show the summary" : "Write a summary",
                      systemImage: "text.quote")
                    .font(.system(size: 12, weight: .semibold))
            }
            .buttonStyle(.borderedProminent).tint(Theme.goldFill)
            .disabled(!canNarrate)

            if board.narration != nil {
                Button { Task { await board.narrate(force: true) } } label: {
                    Label("Rewrite", systemImage: "arrow.clockwise")
                        .font(.system(size: 12))
                }
                .buttonStyle(.bordered)
                .disabled(!canNarrate)
            }
            Spacer(minLength: 0)
            if board.narrationCurrent {
                Text("Cached against these findings")
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
    }

    private var canNarrate: Bool {
        !board.narrationRunning && board.intel?.promptable != nil
            && AppleIntelligence.readiness.usable
    }

    /// What could write one, said as booleans. This app never asks for a key
    /// and has nowhere to put one: the server holds credentials, in the
    /// environment or in `~/.fantasy-edge/ai.json`, which is the posture every
    /// other credential in this project already has.
    private var providers: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Circle()
                    .fill(AppleIntelligence.readiness.usable ? Theme.greenFill
                                                              : Color.secondary)
                    .frame(width: 6, height: 6)
                Text(AppleIntelligence.readiness.line)
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !board.aiProviders.isEmpty {
                Text("Keys on the server: "
                     + board.aiProviders
                        .filter { $0.provider != "apple" }
                        .map { "\($0.label) \($0.configured ? "yes" : "no")" }
                        .joined(separator: " · "))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
    }

    /// AI chat, which is out of scope and says so in the server's own words.
    /// There is no conversational endpoint and none is planned here; asserting
    /// that from a string on the headset would be this client making a claim
    /// about a route it does not own.
    private var chatNote: some View {
        Group {
            if let c = board.intel?.narration?.chat, !c.available, !c.note.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 9))
                    Text(c.note).font(.system(size: 9))
                }
                .foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - the honest gaps

    private var notes: some View {
        Group {
            if let n = board.intel?.notes, !n.isEmpty {
                Panel(title: "What was not computed") {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(n, id: \.self) { NoSource(what: $0) }
                    }
                }
            }
        }
    }

    /// The five metrics the design asks for that nothing within reach
    /// publishes, with the reason for each.
    ///
    /// Named rather than left blank. A gap on a page of dense figures is a gap
    /// the reader fills in with an assumption, and estimating any of these
    /// from what we do have - routes from targets, say - would put a number
    /// here that looks like the others and is not one.
    private var notSourced: some View {
        Group {
            if let b = board.intel, !b.unavailable.isEmpty {
                Panel(title: "Not sourced", badge: b.unavailable.count) {
                    VStack(alignment: .leading, spacing: 9) {
                        NoSource(what: "These are on the design this tab is "
                                 + "modelled on. They are not on this screen, "
                                 + "and they are not estimated.")
                        ForEach(b.unavailable) { u in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Image(systemName: "slash.circle")
                                        .font(.system(size: 9))
                                        .foregroundStyle(.secondary)
                                    Text(u.metric)
                                        .font(.system(size: 12, weight: .semibold))
                                }
                                Text(u.reason).font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .padding(.vertical, 7).padding(.horizontal, 10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 12)
                                .fill(.white.opacity(0.04)))
                        }
                        if !b.available.isEmpty {
                            // Read off the brief rather than kept here, so
                            // this list cannot drift from the one the server
                            // actually computes from.
                            Text("What nflverse does publish, and what the "
                                 + "usage findings are built from: "
                                 + b.available.map(\.label).joined(separator: ", ")
                                 + ".")
                                .font(.system(size: 10)).foregroundStyle(.tertiary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }

    // MARK: - no brief at all

    /// What is left when `/api/intel` does not answer.
    ///
    /// Not a stub of the brief: computing insights here would be a second
    /// engine drifting from the one in `intel.py`, and any caveat this side
    /// wrote would be a paraphrase of one it has never seen. So it shows the
    /// two intel-shaped payloads this app already has routes for, unjoined and
    /// labelled with the route they came from, and says plainly that they are
    /// not the brief.
    private var withoutBrief: some View {
        let exposed = board.roster.filter { $0.startedIn > 1 }
            .sorted { $0.startedIn > $1.startedIn }
        return VStack(spacing: 14) {
            Panel(title: "No computed brief") {
                VStack(alignment: .leading, spacing: 8) {
                    NoSource(what: board.intelNote
                             ?? "The brief has not arrived yet.")
                    Text("The insight engine runs on the Mac, over rows already "
                         + "in SQLite. Nothing below is computed here - this "
                         + "headset holds no league data of its own.")
                        .font(.system(size: 11)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if !board.injuries.isEmpty || !exposed.isEmpty {
                Panel(title: "What this app already holds") {
                    VStack(alignment: .leading, spacing: 9) {
                        NoSource(what: "Rows from other routes, shown as they "
                                 + "arrived. They carry no caveats, because "
                                 + "the layer that writes caveats is the one "
                                 + "that is missing.")
                        ForEach(board.injuries.prefix(5)) { inj in
                            plain("/api/injuries",
                                  "\(inj.name) — \(inj.label ?? inj.severity ?? "listed")")
                        }
                        ForEach(exposed.prefix(5)) { p in
                            plain("/api/players",
                                  "\(p.name) starts in \(p.startedIn) of your line-ups")
                        }
                    }
                }
            }
        }
    }

    private func plain(_ source: String, _ line: String) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Text(source).font(.system(size: 8, design: .monospaced))
                .foregroundStyle(.tertiary).frame(width: 96, alignment: .leading)
            Text(line).font(.system(size: 11))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 5).padding(.horizontal, 9)
        .background(RoundedRectangle(cornerRadius: 10).fill(.white.opacity(0.04)))
    }
}
