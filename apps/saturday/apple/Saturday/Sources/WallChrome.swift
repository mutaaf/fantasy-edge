import SwiftUI

// MARK: - the whip-around

/// Around the country: the API's feed of recent scores, corrections, lead
/// changes, finals and upsets across the slate, newest first. Each card keeps
/// the score as it stood when the thing happened.
struct WhipAround: View {
    @Environment(SaturdayStore.self) private var store
    let items: [FeedItem]
    var onOpen: (String) -> Void

    var body: some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "Around the country", overline: "last 20 min", size: 22)
                ScrollView(.horizontal) {
                    LazyHStack(spacing: 12) {
                        ForEach(items) { item in
                            Button { onOpen(item.game) } label: { FeedCard(item: item) }
                                .buttonStyle(.plain)
                        }
                    }
                    .scrollTargetLayout()
                }
                .scrollIndicators(.hidden)
                .scrollTargetBehavior(.viewAligned)
                // A horizontal scroller in a vertical stack takes all the
                // height it is offered on visionOS; the cards set the row.
                .fixedSize(horizontal: false, vertical: true)
                .animation(.easeInOut(duration: 0.3), value: items.map(\.id))
            }
        }
    }
}

private struct FeedCard: View {
    let item: FeedItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                StateBadge(text: badge, fill: fill, glyph: item.kind.glyph, size: 11)
                    .layoutPriority(0)
                Spacer(minLength: 6)
                Text(time).font(Typeface.sans(12, .semibold)).foregroundStyle(.secondary).monospacedDigit()
                    .lineLimit(1).fixedSize(horizontal: true, vertical: false)
                    .layoutPriority(1)
            }
            HStack(spacing: 10) {
                side(item.away)
                Text("at").font(Typeface.serif(15)).foregroundStyle(.secondary)
                side(item.home)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .frame(width: 288, alignment: .leading)
        .frame(minHeight: Tokens.target + 20)
        .background(Tokens.plate, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(.white.opacity(0.1)) }
        .contentShape(.hoverEffect, RoundedRectangle(cornerRadius: 18, style: .continuous))
        .hoverEffect()
        .accessibilityElement(children: .combine)
    }

    private var owner: FeedItem.FeedSide? {
        [item.away, item.home].first { $0.id == item.team }
    }

    private var badge: String {
        switch item.kind {
        case .correction: return ["Off the board", owner?.abbr].compactMap { $0 }.joined(separator: " · ")
        case .score, .lead, .final: return [item.label, owner?.abbr].compactMap { $0 }.joined(separator: " · ")
        default: return item.label
        }
    }

    private var fill: Color {
        switch item.kind {
        case .upset: return Tokens.goldFill
        case .score, .lead: return owner.map { Color(hex: $0.fill) } ?? Tokens.otFill
        default: return Tokens.otFill
        }
    }

    private var time: String { item.time }

    private func side(_ s: FeedItem.FeedSide) -> some View {
        HStack(spacing: 6) {
            TeamChip(abbr: s.abbr, fill: s.fill, hatch: s.hatch, width: 50, height: 22, fontSize: 14)
            Text(s.score.map(String.init) ?? "–")
                .font(Typeface.display(24, .heavy)).monospacedDigit()
                .fontWeight(s.id == item.team ? .black : .heavy)
        }
    }
}

// MARK: - a rebuilt day

/// A day rebuilt from play timestamps says so, quietly and always: a chip
/// beside the replay clock, in the same slanted vocabulary as every other
/// state. Tapping it gives the reasons, in the API's own words.
struct RebuiltMark: View {
    let rebuilt: Rebuilt
    @State private var showing = false

    var body: some View {
        // Screenshot and UI-test hook, like -openGame: `-rebuiltNote YES`.
        Button { showing = true } label: {
            StateBadge(text: "Rebuilt", fill: Tokens.otFill, glyph: Glyph.rebuilt, size: 11)
                .overlay(alignment: .bottom) {
                    Rectangle().fill(.white.opacity(0.35)).frame(height: 1).offset(y: 3)
                }
        }
        .buttonStyle(.plain)
        .frame(minHeight: Tokens.target)
        .accessibilityLabel("Rebuilt from timestamps: \(rebuilt.games) games. What this means")
        .sheet(isPresented: $showing) { RebuiltNote(rebuilt: rebuilt) }
        .onAppear { showing = showing || UserDefaults.standard.bool(forKey: "rebuiltNote") }
    }
}

private struct RebuiltNote: View {
    let rebuilt: Rebuilt
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Rebuilt from timestamps").font(Typeface.serif(30))
                    Text("\(rebuilt.games) of these games were not recorded as they happened. Every play carries the instant it happened, so this hour was worked out from those afterwards. It is not a recording, and it does not know everything a recording would.")
                        .font(Typeface.sans(15)).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Rectangle().fill(.white.opacity(0.15)).frame(height: 1)
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(Array(rebuilt.caveats.enumerated()), id: \.offset) { _, line in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: Glyph.rebuilt).font(.system(size: 12))
                                .foregroundStyle(.secondary).padding(.top, 3)
                            Text(line).font(Typeface.sans(14))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                Button("Done") { dismiss() }
                    .buttonStyle(PillButtonStyle(primary: true))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(28)
            .frame(maxWidth: 620, alignment: .leading)
        }
        #if !os(visionOS)
        .background(Color.black)
        #endif
    }
}

// MARK: - the replay bar

/// Play, pause, speed and a scrubber over the recorded night. The frames and
/// their marks come from /api/replay; the bar lands only on real frames.
struct ReplayBar: View {
    @Environment(SaturdayStore.self) private var store
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var dragIndex: Double?

    private var compact: Bool {
        #if os(visionOS)
        false
        #else
        sizeClass == .compact
        #endif
    }

    var body: some View {
        if let clock = store.slate?.clock {
            let shown = dragIndex.map { Int($0.rounded()) } ?? clock.index
            let frame = store.timeline?.frames[safe: shown]
            if compact {
                // A phone gets two rows: controls and time, then the night.
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 12) {
                        playButton
                        time(frame?.label ?? clock.label, size: 22)
                        Spacer(minLength: 4)
                        speedMenu
                    }
                    scrubber(clock)
                    headline(frame)
                }
                .padding(.horizontal, 14).padding(.vertical, 10)
            } else {
                HStack(spacing: 16) {
                    playButton
                    time(frame?.label ?? clock.label, size: 24).frame(width: 118, alignment: .leading)
                    VStack(alignment: .leading, spacing: 4) {
                        scrubber(clock)
                        headline(frame)
                    }
                    .frame(minWidth: 280)
                    speedMenu
                }
                .padding(.horizontal, 14).padding(.vertical, 8)
            }
        }
    }

    private var playButton: some View {
        Button {
            store.playing ? store.pause() : store.play()
        } label: {
            Image(systemName: store.playing ? "pause.fill" : "play.fill")
                .font(.system(size: 20, weight: .bold))
                .frame(width: Tokens.target, height: Tokens.target)
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(RoundButtonStyle())
        .accessibilityLabel(store.playing ? "Pause replay" : "Play replay")
    }

    private func time(_ label: String, size: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Replay").font(Typeface.serif(14)).foregroundStyle(.secondary)
            Text(label).font(Typeface.display(size, .heavy)).monospacedDigit()
                .contentTransition(.numericText())
                .fixedSize(horizontal: true, vertical: false)
        }
    }

    /// One tap steps to the next speed. A button rather than a menu: a menu's
    /// label renders as a blank capsule on visionOS glass.
    private var speedMenu: some View {
        Button {
            let all = SaturdayStore.speeds
            store.setSpeed(all[((all.firstIndex(of: store.speed) ?? 0) + 1) % all.count])
        } label: {
            Text("\(Int(store.speed))×").font(Typeface.sans(17, .bold)).monospacedDigit()
                .frame(minWidth: Tokens.target, minHeight: Tokens.target)
        }
        .buttonStyle(PillButtonStyle())
        .accessibilityLabel("Replay speed \(Int(store.speed)) times")
        .accessibilityHint("Steps to the next speed")
    }

    private func scrubber(_ clock: ReplayFrame) -> some View {
        VStack(spacing: 2) {
            if let timeline = store.timeline { Marks(timeline: timeline).frame(height: 16).padding(.horizontal, 12) }
            Slider(value: Binding(get: { dragIndex ?? Double(clock.index) }, set: { dragIndex = $0 }),
                   in: 0...Double(max(1, clock.frames - 1)), step: 1) { editing in
                if !editing, let i = dragIndex, let stamp = store.timeline?.frames[safe: Int(i.rounded())]?.stamp {
                    store.seek(to: stamp)
                    dragIndex = nil
                }
            }
            .tint(.white)
            .accessibilityLabel("Replay position")
            .accessibilityValue(store.timeline?.frames[safe: Int((dragIndex ?? Double(clock.index)).rounded())]?.label ?? clock.label)
        }
    }

    @ViewBuilder private func headline(_ frame: ReplayTimeline.Frame?) -> some View {
        if let change = frame?.headline {
            let game = store.game(change.game)
            HStack(spacing: 6) {
                Image(systemName: change.kind.glyph)
                Text([game.map { "\($0.away.abbr) at \($0.home.abbr)" }, change.badgeText(in: game)].compactMap { $0 }.joined(separator: " · "))
                    .lineLimit(1)
            }
            .font(Typeface.sans(12, .semibold)).foregroundStyle(.secondary)
        } else {
            Text(" ").font(Typeface.sans(12))
        }
    }
}

/// What the night held, drawn over the scrubber: a short tick per score, a
/// tall one per final, a diamond per upset, and the recorder's gaps hatched.
/// Height and shape carry the meaning; colour only repeats it.
private struct Marks: View {
    let timeline: ReplayTimeline

    var body: some View {
        Canvas { ctx, size in
            let last = max(1, timeline.frames.last?.offsetSeconds ?? 1)
            func x(_ f: ReplayTimeline.Frame) -> CGFloat { size.width * CGFloat(f.offsetSeconds / last) }
            for (a, b) in zip(timeline.frames, timeline.frames.dropFirst()) where b.offsetSeconds - a.offsetSeconds > 180 {
                let rect = CGRect(x: x(a), y: 0, width: x(b) - x(a), height: size.height)
                ctx.fill(Path(rect), with: .color(.white.opacity(0.06)))
                var hatch = Path()
                var hx = rect.minX
                while hx < rect.maxX { hatch.move(to: CGPoint(x: hx, y: size.height)); hatch.addLine(to: CGPoint(x: hx + 6, y: 0)); hx += 6 }
                ctx.stroke(hatch, with: .color(.white.opacity(0.14)), lineWidth: 1)
            }
            for f in timeline.frames {
                let fx = x(f)
                if f.marks.scores > 0 {
                    let h = CGFloat(min(3, f.marks.scores)) * 3 + 2
                    ctx.fill(Path(CGRect(x: fx - 0.75, y: size.height - h, width: 1.5, height: h)), with: .color(.white.opacity(0.55)))
                }
                if f.marks.finals > 0 {
                    ctx.fill(Path(CGRect(x: fx - 1, y: 0, width: 2, height: size.height)), with: .color(.white))
                }
                if f.marks.upsets > 0 {
                    var d = Path()
                    d.move(to: CGPoint(x: fx, y: 0)); d.addLine(to: CGPoint(x: fx + 5, y: 5))
                    d.addLine(to: CGPoint(x: fx, y: 10)); d.addLine(to: CGPoint(x: fx - 5, y: 5)); d.closeSubpath()
                    ctx.fill(d, with: .color(Tokens.goldFill))
                    ctx.stroke(d, with: .color(.white), lineWidth: 1)
                }
            }
        }
        .accessibilityHidden(true)
    }
}

extension Array {
    subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil }
}

/// A round ink button for a single glyph.
struct RoundButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(Color.black)
            .background(Color.white.opacity(configuration.isPressed ? 0.75 : 0.92), in: Circle())
            .contentShape(.hoverEffect, Circle())
            .hoverEffect()
    }
}
