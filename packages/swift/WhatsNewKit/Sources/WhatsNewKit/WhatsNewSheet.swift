#if canImport(SwiftUI)
import SwiftUI

/// The sheet: a headline, two to four cards, the full notes folded away, and
/// one way out.
///
/// It follows the host app's colour rule rather than inventing one: text wears
/// the system's text ink, which re-derives against whatever is behind the glass,
/// and colour rides on an opaque chip beside it. The aurora behind is light and
/// slow, and it stops entirely under Reduce Motion.
public struct WhatsNewSheet: View {
    public let release: Release
    /// The app's own art for the hero - on Fantasy Edge, the ball off its icon.
    public let art: Image?
    /// The destinations the app can open; a card naming any other stays plain.
    public let destinations: Set<String>
    /// Closes the sheet and opens a card's destination.
    public let go: (String) -> Void
    public let dismiss: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false
    @State private var notesOpen = Self.notesOpenAtLaunch
    @ScaledMetric(relativeTo: .largeTitle) private var headlineSize: CGFloat = 46

    /// `-whatsNewOpenNotes` opens the accordion in a debug build, because a
    /// simulator screenshot cannot tap it.
    private static var notesOpenAtLaunch: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("-whatsNewOpenNotes")
        #else
        return false
        #endif
    }

    public init(release: Release, art: Image? = nil, destinations: Set<String> = [],
                go: @escaping (String) -> Void = { _ in }, dismiss: @escaping () -> Void) {
        self.release = release
        self.art = art
        self.destinations = destinations
        self.go = go
        self.dismiss = dismiss
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                hero
                VStack(spacing: 12) {
                    ForEach(Array(release.cards.enumerated()), id: \.element.id) { i, card in
                        CardRow(card: card, destination: card.callout(known: destinations), go: go)
                            .opacity(shown ? 1 : 0)
                            .offset(y: shown || reduceMotion ? 0 : 14)
                            .animation(reduceMotion ? nil : .spring(duration: 0.55, bounce: 0.25)
                                .delay(0.12 + 0.08 * Double(i)), value: shown)
                    }
                }
                notes
                Button(action: dismiss) {
                    Text("Back to the board")
                        .font(.headline.weight(.heavy))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .tint(WhatsNewPalette.chip("green"))
                .controlSize(.large)
                .keyboardShortcut(.defaultAction)
                .accessibilityHint("Closes what's new")
            }
            .padding(32)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background { Aurora(still: reduceMotion) }
        #if os(visionOS)
        // A visionOS sheet sizes to its content's ideal and no further, which
        // left the notes and the button below the fold. Tall enough for both.
        .frame(width: 660, height: 900)
        #else
        .frame(idealWidth: 620, maxWidth: 680, idealHeight: 760)
        #endif
        .onAppear { shown = true }
        .accessibilityAction(.escape, dismiss)
    }

    private var hero: some View {
        HStack(alignment: .center, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(release.kicker.uppercased())
                    .font(.caption.weight(.heavy))
                    .tracking(1.6)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .foregroundStyle(.white)
                    .background(Capsule().fill(WhatsNewPalette.chip("blue")))
                Text(release.headline)
                    .font(.system(size: headlineSize, weight: .black).width(.condensed))
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                Text(release.subhead)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            if let art {
                art.resizable().scaledToFit()
                    .frame(width: 112, height: 112)
                    .rotationEffect(.degrees(shown && !reduceMotion ? -8 : 0))
                    .scaleEffect(shown || reduceMotion ? 1 : 0.6)
                    .animation(reduceMotion ? nil : .spring(duration: 0.7, bounce: 0.45), value: shown)
                    .shadow(color: .black.opacity(0.25), radius: 10, y: 6)
                    .accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var notes: some View {
        DisclosureGroup(isExpanded: $notesOpen) {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(release.notes, id: \.self) { line in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        Circle().fill(WhatsNewPalette.chip("green")).frame(width: 7, height: 7)
                            .accessibilityHidden(true)
                        Text(line).font(.callout).foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Text("Version \(release.version)")
                    .font(.caption.monospacedDigit()).foregroundStyle(.tertiary)
            }
            .padding(.top, 10)
        } label: {
            Text("All the notes")
                .font(.headline.weight(.bold))
                .foregroundStyle(.primary)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(.thinMaterial))
    }
}

/// A card. One with a destination is a button: the whole card is the target,
/// and a "Show me" chip on its trailing edge says so before anybody has to
/// find out by tapping - the same offered-not-discovered rule as the board's
/// chevrons.
private struct CardRow: View {
    let card: Release.Card
    let destination: String?
    let go: (String) -> Void

    var body: some View {
        if let destination {
            Button { go(destination) } label: { row }
                .buttonStyle(.plain)
                #if os(visionOS) || os(iOS)
                .hoverEffect(.highlight)
                #endif
                .accessibilityHint("Closes what's new and opens it")
        } else {
            row
        }
    }

    private var row: some View {
        HStack(spacing: 16) {
            Image(systemName: card.icon)
                .font(.title2.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 54, height: 54)
                .background {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(WhatsNewPalette.chip(card.tint))
                        .overlay(Stripes().opacity(0.18))
                        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(card.title)
                    .font(.headline.weight(.heavy))
                    .foregroundStyle(.primary)
                Text(card.line)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            if destination != nil {
                HStack(spacing: 4) {
                    Text("Show me")
                    Image(systemName: "arrow.up.right")
                }
                .font(.caption.weight(.heavy))
                .foregroundStyle(.white)
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(Capsule().fill(WhatsNewPalette.chip(card.tint)))
                .fixedSize()
                .accessibilityHidden(true)
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(.regularMaterial))
        .contentShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// Mown-turf stripes, the back layer of the app icon in miniature.
private struct Stripes: View {
    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                ForEach(0..<6, id: \.self) { i in
                    Rectangle().fill(i.isMultiple(of: 2) ? Color.white : .clear)
                        .frame(width: geo.size.width / 6)
                }
            }
        }
    }
}

/// A slow aurora field in the store brand's glow colours, lime, sky and turf.
private struct Aurora: View {
    let still: Bool

    var body: some View {
        if still {
            field(phase: 0)
        } else {
            TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                field(phase: ctx.date.timeIntervalSinceReferenceDate)
            }
        }
    }

    private func field(phase t: Double) -> some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            ZStack {
                blob(WhatsNewPalette.lime, w * 0.9, x: w * (0.18 + 0.06 * sin(t / 7)), y: h * (0.08 + 0.04 * cos(t / 9)))
                blob(WhatsNewPalette.sky, w * 0.8, x: w * (0.88 + 0.05 * cos(t / 8)), y: h * (0.22 + 0.05 * sin(t / 6)))
                blob(WhatsNewPalette.turf, w * 1.0, x: w * (0.5 + 0.08 * sin(t / 11)), y: h * (0.95 + 0.03 * cos(t / 10)))
            }
            .blur(radius: 70)
            .opacity(0.55)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func blob(_ c: Color, _ size: CGFloat, x: CGFloat, y: CGFloat) -> some View {
        Circle().fill(c).frame(width: size, height: size * 0.6).position(x: x, y: y)
    }
}

/// The opaque chip fills are the host app's own - the luminance band where
/// white text clears 4.5:1 (Fantasy Edge's `Theme.*Fill`). The aurora colours
/// are the store brand's glow, used only as wash, never under text alone.
enum WhatsNewPalette {
    static let lime = Color(red: 0.831, green: 1.0, blue: 0.227)    // #D4FF3A
    static let sky  = Color(red: 0.227, green: 0.839, blue: 1.0)    // #3AD6FF
    static let turf = Color(red: 0.122, green: 0.478, blue: 0.267)  // #1F7A44

    static func chip(_ tint: String) -> Color {
        switch tint {
        case "gold": return Color(red: 0.544, green: 0.452, blue: 0.000)
        case "red":  return Color(red: 0.875, green: 0.044, blue: 0.044)
        case "blue": return Color(red: 0.082, green: 0.432, blue: 0.821)
        default:     return Color(red: 0.136, green: 0.476, blue: 0.014)
        }
    }
}

// MARK: - Presenting it

public extension View {
    /// Shows `notes`' entry for this build once, after an upgrade.
    ///
    /// - Parameters:
    ///   - priorStateKeys: `UserDefaults` keys only an install that has been
    ///     used would have written; see `WhatsNewGate.decide(priorInstall:)`.
    ///   - suppression: the app's capture, test and demo flags.
    ///
    ///   - destinations: the card destinations the app routes, and `open`,
    ///     which takes one there. It runs after the sheet has gone, so the
    ///     destination may present a sheet of its own.
    ///
    /// `-whatsNewPreview` on the launch line shows the sheet in a debug build
    /// without recording anything, so it can be screenshotted; add
    /// `-whatsNewTap <destination>` to press that callout once it is up.
    func whatsNew(_ notes: ReleaseNotes?, art: Image? = nil, priorStateKeys: [String] = [],
                  suppression: WhatsNewSuppression = .init(), destinations: Set<String> = [],
                  open: @escaping (String) -> Void = { _ in }) -> some View {
        modifier(WhatsNewPresenter(notes: notes, art: art, priorStateKeys: priorStateKeys,
                                   suppression: suppression, destinations: destinations, open: open))
    }
}

private struct WhatsNewPresenter: ViewModifier {
    let notes: ReleaseNotes?
    let art: Image?
    let priorStateKeys: [String]
    let suppression: WhatsNewSuppression
    let destinations: Set<String>
    let open: (String) -> Void
    @State private var release: Release?
    @State private var decided = false
    /// Where a callout asked to go, held until the sheet has finished leaving:
    /// presenting the destination's own sheet while this one is still on
    /// screen is refused by SwiftUI, silently.
    @State private var pending: String?

    private static var force: WhatsNewForce {
        #if DEBUG
        WhatsNewForce(arguments: ProcessInfo.processInfo.arguments, isDebug: true)
        #else
        WhatsNewForce(arguments: [], isDebug: false)
        #endif
    }

    func body(content: Content) -> some View {
        content
            .sheet(item: $release, onDismiss: {
                if let d = pending { pending = nil; open(d) }
            }) { r in
                WhatsNewSheet(release: r, art: art, destinations: destinations,
                              go: { go($0) }, dismiss: { release = nil })
            }
            .task {
                guard !decided else { return }
                decided = true
                release = Self.evaluate(notes: notes, priorStateKeys: priorStateKeys, suppression: suppression)
                // The debug tap: the same `go` a finger runs, once the cards
                // have settled, so a screenshot shows where it landed.
                if let tap = Self.force.tap, let r = release,
                   r.cards.contains(where: { $0.callout(known: destinations) == tap }) {
                    try? await Task.sleep(for: .seconds(3))
                    go(tap)
                }
            }
    }

    private func go(_ destination: String) {
        pending = destination
        release = nil
    }

    static func evaluate(notes: ReleaseNotes?, priorStateKeys: [String],
                         suppression: WhatsNewSuppression) -> Release? {
        let info = ProcessInfo.processInfo
        let current = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        if force.preview {
            // Forced: the current version's entry, else the newest, and the
            // store is not touched (`WhatsNewGate.decide(forced:)`).
            let r = current.flatMap { notes?.release(for: $0) } ?? notes?.releases.first
            let d = WhatsNewGate.decide(current: current, seen: nil, priorInstall: false,
                                        hasNotes: r != nil, suppressed: false, forced: true)
            return d.show ? r : nil
        }
        let defaults = UserDefaults.standard
        let decision = WhatsNewGate.decide(
            current: current,
            seen: defaults.string(forKey: WhatsNewStore.seenKey),
            priorInstall: WhatsNewStore.hasPriorState(priorStateKeys, defaults: defaults),
            hasNotes: current.flatMap { notes?.release(for: $0) } != nil,
            suppressed: suppression.isSuppressed(arguments: info.arguments, environment: info.environment))
        if let v = decision.record { defaults.set(v, forKey: WhatsNewStore.seenKey) }
        return decision.show ? current.flatMap { notes?.release(for: $0) } : nil
    }
}
#endif
