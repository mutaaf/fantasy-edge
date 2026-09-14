import RealityKit
import SwiftUI

// The two ways into a game: on the table in front of you, and from a seat at
// the fifty. Both draw the same `SceneSpec` through the same renderer at a
// different scale, and both are generic - the app hands them a feed and,
// optionally, a panel of its own for the stadium's right hand.

/// The scorebug, drawn the same in the volume and in the stadium. Sized in
/// points: an attachment is rasterised once, so scaling its entity would only
/// enlarge a texture.
public struct SceneScorebug: View {
    let spec: SceneSpec
    public init(spec: SceneSpec) { self.spec = spec }

    public var body: some View {
        HStack(spacing: 18) {
            side(spec.teams.away, score: spec.status.awayScore, has: spec.status.possession == "away")
            VStack(spacing: 3) {
                Text(spec.status.label.isEmpty ? spec.status.state.capitalized : spec.status.label)
                    .font(.system(size: 17, weight: .bold)).monospacedDigit()
                if !spec.status.downDistance.isEmpty {
                    Text(spec.status.downDistance).font(.system(size: 14)).foregroundStyle(.secondary)
                }
                if spec.isReplay {
                    Label("Replay", systemImage: "arrow.counterclockwise")
                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
                }
            }
            side(spec.teams.home, score: spec.status.homeScore, has: spec.status.possession == "home")
            if spec.status.redZone {
                SceneChip(text: "RED ZONE", fill: spec.palette["fill.redZone"] ?? "#DF0B0B",
                     symbol: "arrow.right.to.line")
            }
        }
        .padding(.horizontal, 24).padding(.vertical, 14)
        .glassBackgroundEffect()
    }

    private func side(_ t: SceneSpec.Team, score: Double, has ball: Bool) -> some View {
        HStack(spacing: 10) {
            SceneChip(text: t.abbr, fill: t.chip, symbol: nil, hatch: t.hatch)
            Text("\(Int(score))").font(.system(size: 38, weight: .heavy)).monospacedDigit()
            Image(systemName: "football.fill").font(.system(size: 14)).opacity(ball ? 1 : 0)
                .accessibilityLabel(ball ? "has the ball" : "")
        }
    }
}

/// Colour on an opaque chip beside ink, never as ink. The fill is already in
/// the luminance band, so white text on it clears 4.5:1 for any club.
struct SceneChip: View {
    let text: String
    let fill: String
    let symbol: String?
    var hatch = false

    var body: some View {
        HStack(spacing: 5) {
            if let symbol { Image(systemName: symbol).font(.system(size: 12, weight: .bold)) }
            Text(text).font(.system(size: 15, weight: .heavy))
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background {
            let c = SceneMath.rgba(fill)
            ZStack {
                Color(red: Double(c.x), green: Double(c.y), blue: Double(c.z))
                if hatch {
                    Canvas { ctx, size in
                        var x: CGFloat = -size.height
                        while x < size.width {
                            var p = Path()
                            p.move(to: CGPoint(x: x, y: size.height))
                            p.addLine(to: CGPoint(x: x + size.height, y: 0))
                            ctx.stroke(p, with: .color(.black.opacity(0.28)), lineWidth: 3)
                            x += 9
                        }
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
    }
}

/// The drive, play by play: the stadium's left-hand panel and the volume's
/// scrubber both read from it.
public struct DriveLog: View {
    let spec: SceneSpec
    public init(spec: SceneSpec) { self.spec = spec }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let d = spec.shownDrive {
                Text("\(d.team) drive\(d.result.isEmpty ? "" : " · \(d.result)")")
                    .font(.system(size: 20, weight: .semibold))
                ForEach(Array(d.arcs.suffix(9).enumerated()), id: \.element.id) { i, arc in
                    HStack(alignment: .top, spacing: 10) {
                        Circle().fill(color(arc.color)).frame(width: 10, height: 10).padding(.top, 5)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(label(arc)).font(.system(size: 14, weight: .semibold))
                            Text(arc.text).font(.system(size: 13)).foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            } else {
                Text("No drive yet").font(.system(size: 17)).foregroundStyle(.secondary)
            }
        }
        .padding(22)
        .frame(width: 460, alignment: .leading)
        .glassBackgroundEffect()
    }

    private func label(_ arc: SceneSpec.Arc) -> String {
        var parts: [String] = []
        if let down = arc.down, down > 0, let dist = arc.distance {
            parts.append("\(down)\(["st", "nd", "rd", "th"][min(down, 4) - 1]) & \(dist)")
        }
        parts.append(arc.type)
        return parts.joined(separator: " · ")
    }

    private func color(_ token: String) -> Color {
        let c = SceneMath.rgba(spec.palette[token] ?? "#FFFFFF")
        return Color(red: Double(c.x), green: Double(c.y), blue: Double(c.z))
    }
}

/// Play, pause, scrub and speed for a replay. Every control is 60 points or
/// more, the size a look-and-pinch target needs.
public struct ReplayControls: View {
    let feed: SceneFeed
    @State private var scrub: Double?

    public init(feed: SceneFeed) { self.feed = feed }

    public var body: some View {
        if let r = feed.replay, r.loaded, let length = r.length, length > 0 {
            HStack(spacing: 16) {
                Button {
                    Task { r.playing ? await feed.pause() : await feed.play() }
                } label: {
                    Image(systemName: r.playing ? "pause.fill" : "play.fill")
                        .font(.system(size: 22, weight: .bold)).frame(width: 60, height: 60)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel(r.playing ? "Pause" : "Play")

                Slider(value: Binding(
                    get: { scrub ?? Double(r.gameSeconds ?? 0) },
                    set: { scrub = $0 }),
                       in: 0...Double(length)) { editing in
                    if !editing, let s = scrub {
                        Task { await feed.seek(Int(s)); scrub = nil }
                    }
                }
                .frame(width: 360)

                Text(r.label ?? "").font(.system(size: 15, weight: .semibold)).monospacedDigit()
                    .frame(width: 96)

                Menu {
                    ForEach(r.speeds, id: \.self) { s in
                        Button("\(Int(s))×") { Task { await feed.setSpeed(s) } }
                    }
                } label: {
                    Text("\(Int(r.speed))×").font(.system(size: 17, weight: .bold))
                        .frame(minWidth: 60, minHeight: 60)
                }
            }
            .padding(.horizontal, 16)
        }
    }
}

// MARK: - the tabletop

/// A game on the table: a volumetric window about 0.9 × 0.4 × 0.6 m.
public struct TabletopView: View {
    let feed: SceneFeed
    let enterStadium: () -> Void
    @State private var renderer = StadiumRenderer(mode: .tabletop)
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(feed: SceneFeed, enterStadium: @escaping () -> Void) {
        self.feed = feed
        self.enterStadium = enterStadium
    }

    public var body: some View {
        RealityView { content, attachments in
            content.add(renderer.root)
            if let flag = attachments.entity(for: "moment") {
                flag.position = SIMD3(0, 0.08, 0.05)
                content.add(flag)
            }
        } update: { _, attachments in
            // Only the renderer is told; attachments were placed once in
            // `make` and are never re-added here.
            if let spec = feed.spec { renderer.apply(spec, reduceMotion: reduceMotion) }
            attachments.entity(for: "moment")?.isEnabled = feed.spec?.activeMoment?.celebrates == true
        } attachments: {
            Attachment(id: "moment") {
                if let m = feed.spec?.activeMoment { MomentBanner(moment: m, spec: feed.spec) }
            }
        }
        // The scorebug rides in the ornament rather than floating in the
        // volume: the win-probability horizon fills the back of the volume
        // at exactly the height a floating scorebug wanted, and the two drew
        // through each other.
        .ornament(attachmentAnchor: .scene(.bottomFront)) {
            HStack(spacing: 12) {
                if let spec = feed.spec {
                    SceneScorebug(spec: spec)
                } else {
                    Text(feed.error ?? "Loading the game…").font(.system(size: 15)).padding()
                }
                ReplayControls(feed: feed)
                Button {
                    enterStadium()
                } label: {
                    Label("Enter stadium", systemImage: "sportscourt.fill")
                        .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                }
            }
            .padding(12)
            .glassBackgroundEffect()
        }
        .task { feed.start() }
        .onDisappear { feed.stop() }
    }
}

/// TOUCHDOWN, or whatever the moment is, with the play that made it.
public struct MomentBanner: View {
    let moment: SceneSpec.Moment
    let spec: SceneSpec?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false

    public init(moment: SceneSpec.Moment, spec: SceneSpec?) {
        self.moment = moment
        self.spec = spec
    }

    private var title: String {
        switch moment.kind {
        case "touchdown": return "TOUCHDOWN"
        case "fieldGoal": return "FIELD GOAL"
        case "safety": return "SAFETY"
        default: return moment.kind.uppercased()
        }
    }

    public var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                if let t = spec?.teams.side(moment.side) {
                    SceneChip(text: t.abbr, fill: t.chip, symbol: nil, hatch: t.hatch)
                }
                Text(title).font(.system(size: 64, weight: .black))
            }
            Text(moment.text).font(.system(size: 18)).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).frame(maxWidth: 640)
        }
        .padding(28)
        .glassBackgroundEffect()
        .scaleEffect(reduceMotion || shown ? 1 : 0.94)
        .opacity(shown || reduceMotion ? 1 : 0)
        .onAppear {
            if reduceMotion { shown = true } else { withAnimation(.spring(duration: 0.5)) { shown = true } }
        }
    }
}

// MARK: - the stadium

/// Placement in metres from the wearer, who sits at the origin facing -z.
/// Panels stay inside 46 degrees either side and no lower than 33 degrees
/// below the eye, which is what the old room learned the hard way.
public enum StadiumLayout {
    public static let eye: Float = 1.2
    public static func at(degrees: Float, distance: Float, height: Float) -> SIMD3<Float> {
        let r = degrees * .pi / 180
        return SIMD3(sin(r) * distance, height, -cos(r) * distance)
    }
}

/// Seated at the fifty, in a bowl at night. Full immersion, reached from the
/// tabletop; the Digital Crown can take it back down to progressive.
public struct StadiumSpaceView<Trailing: View>: View {
    let feed: SceneFeed
    let leave: () -> Void
    let trailing: Trailing
    @State private var renderer = StadiumRenderer(mode: .stadium)
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(feed: SceneFeed, leave: @escaping () -> Void, @ViewBuilder trailing: () -> Trailing) {
        self.feed = feed
        self.leave = leave
        self.trailing = trailing()
    }


    public var body: some View {
        RealityView { content, attachments in
            content.add(renderer.root)
            let place: [(String, SIMD3<Float>)] = [
                ("scorebug", StadiumLayout.at(degrees: 0, distance: 2.4, height: StadiumLayout.eye + 0.75)),
                ("drive", StadiumLayout.at(degrees: -38, distance: 1.25, height: StadiumLayout.eye - 0.30)),
                ("trailing", StadiumLayout.at(degrees: 38, distance: 1.25, height: StadiumLayout.eye - 0.30)),
                ("controls", StadiumLayout.at(degrees: 0, distance: 1.0, height: StadiumLayout.eye - 0.55)),
                ("moment", StadiumLayout.at(degrees: 0, distance: 3.0, height: StadiumLayout.eye + 0.25)),
            ]
            for (id, position) in place {
                guard let e = attachments.entity(for: id) else { continue }
                e.position = position
                // Face the wearer: an attachment looks down +z by default.
                e.look(at: SIMD3(0, StadiumLayout.eye, 0), from: position, relativeTo: nil, forward: .positiveZ)
                content.add(e)
            }
        } update: { _, attachments in
            if let spec = feed.spec { renderer.apply(spec, reduceMotion: reduceMotion) }
            attachments.entity(for: "moment")?.isEnabled = feed.spec?.activeMoment?.celebrates == true
        } attachments: {
            Attachment(id: "scorebug") {
                if let spec = feed.spec { SceneScorebug(spec: spec) }
            }
            Attachment(id: "drive") {
                if let spec = feed.spec { DriveLog(spec: spec) }
            }
            Attachment(id: "trailing") { trailing }
            Attachment(id: "controls") {
                HStack(spacing: 10) {
                    ReplayControls(feed: feed)
                    Button(action: leave) {
                        Label("Tabletop", systemImage: "cube")
                            .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                    }
                    if feed.spec?.isReplay == true, let start = feed.replay?.driveStart {
                        Button {
                            // Just before the snap, so the first play flies.
                            Task { await feed.seek(max(0, start - 1)) }
                        } label: {
                            Label("Replay drive", systemImage: "gobackward")
                                .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                        }
                    }
                }
                .padding(12)
                .glassBackgroundEffect()
            }
            Attachment(id: "moment") {
                if let m = feed.spec?.activeMoment { MomentBanner(moment: m, spec: feed.spec) }
            }
        }
        .task { feed.start() }
        .onDisappear { feed.stop() }
    }
}
