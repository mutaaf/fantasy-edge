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

    @State private var hold = MomentHold()

    public var body: some View {
        RealityView { content, attachments in
            content.add(renderer.root)
            let r = renderer
            renderer.subscription = content.subscribe(to: SceneEvents.Update.self) { event in
                MainActor.assumeIsolated { r.tick(event.deltaTime) }
            }
            if let flag = attachments.entity(for: "moment") {
                flag.position = SIMD3(0, 0.13, 0)
                content.add(flag)
            }
        } update: { _, attachments in
            // Only the renderer is told; attachments were placed once in
            // `make` and are only moved here, never re-added.
            if let spec = feed.spec { renderer.apply(spec, reduceMotion: reduceMotion) }
            if let flag = attachments.entity(for: "moment") {
                flag.isEnabled = hold.shown != nil
                if let m = hold.shown, let spec = feed.spec {
                    // Over the end zone the score went into, at table scale.
                    let x = m.anchorX
                    let s = Float(spec.presentation.tabletop.metersPerYard)
                    flag.position = SIMD3(Float(x - 50) * s, 0.13, 0)
                }
            }
        } attachments: {
            Attachment(id: "moment") {
                // The moment graphic is Broadcast's now, drawn in the world
                // over the end zone (BroadcastBanner); this glass chip stays
                // empty so the two never show at once.
                EmptyView()
            }
        }
        .onChange(of: feed.spec?.activeMoment, initial: true) { _, m in hold.arrive(m) }
        .task(id: hold.shown?.playId) {
            await hold.expire(after: feed.spec?.motion.momentSeconds ?? MomentHold.defaultSeconds)
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
        // A fade and a short rise, never a scale: the attachment is rasterised
        // at its point size, and scaling it would blur the one word that has
        // to be crisp. Reduce motion: there from the first frame.
        .opacity(shown || reduceMotion ? 1 : 0)
        .offset(y: shown || reduceMotion ? 0 : 24)
        .onAppear {
            if reduceMotion { shown = true } else { withAnimation(.easeOut(duration: 0.45)) { shown = true } }
        }
    }
}

/// How long a celebration stays up, independent of the poll.
///
/// The server holds a moment only until the game clock moves, and at 60x that
/// is less than one poll: a touchdown could arrive and be gone before a frame
/// showed it, or linger for a whole stoppage live. So the client takes the
/// moment when it first appears and keeps it for the scene's own
/// `motion.momentSeconds`, then lets it go - unless a newer one replaces it.
@MainActor
@Observable
public final class MomentHold {
    public static let defaultSeconds = 4.5
    public private(set) var shown: SceneSpec.Moment?
    @ObservationIgnored private var seen: Set<String> = []

    public init() {}

    public func arrive(_ moment: SceneSpec.Moment?) {
        guard let moment, moment.celebrates, !seen.contains(moment.playId) else { return }
        seen.insert(moment.playId)
        shown = moment
    }

    public func expire(after seconds: Double) async {
        guard let id = shown?.playId else { return }
        try? await Task.sleep(for: .seconds(max(1, seconds)))
        guard !Task.isCancelled, shown?.playId == id else { return }
        shown = nil
    }
}

/// The stadium's immersion choice, as the generic views see it.
public enum StadiumImmersion: Hashable, Sendable {
    /// Progressive: the Digital Crown sets how much of the room remains.
    case dial
    /// 100% full immersion.
    case full
}

// MARK: - the stadium

/// Placement in metres from the wearer, who sits at the origin facing -z.
///
/// The limits are the ones the old room learned the hard way, tightened for a
/// seat: side panels at 30 degrees (at 38 the simulator's own view cut them
/// off, and a head turned further than that for a drive log is a sore neck by
/// the fourth quarter), nothing lower than 33 degrees below the eye, and
/// nothing further out than 44 degrees.
public enum StadiumLayout {
    public static let eye: Float = 1.2
    public static let sideYaw: Float = 30
    public static let maxYaw: Float = 44
    public static let maxBelow: Float = 33

    public static func at(degrees: Float, distance: Float, height: Float) -> SIMD3<Float> {
        let r = degrees * .pi / 180
        return SIMD3(sin(r) * distance, height, -cos(r) * distance)
    }

    /// Degrees below the eye of a point, for checking a placement.
    public static func below(_ p: SIMD3<Float>) -> Float {
        let flat = (p.x * p.x + p.z * p.z).squareRoot()
        return atan2(eye - p.y, flat) * 180 / .pi
    }

    /// The end zone a side scores into. Home defends x = 0 and attacks 100.
    public static func endZoneX(scoredBy side: String) -> Double {
        side == "home" ? 105 : -5
    }

    /// Where the celebration goes in the stadium: in the direction of the end
    /// zone the score went into, lifted above the stands' sightline.
    ///
    /// Not *at* the end zone. From the fifty that is 50 yards away and 52
    /// degrees round, where a banner sized to read is a postage stamp and a
    /// head turned that far misses the field. So it sits on the same bearing,
    /// held to `maxYaw`, a few metres out.
    public static func moment(_ m: SceneSpec.Moment, seat: SceneSpec.SeatOption) -> SIMD3<Float> {
        // The bearing of the scene's anchor as the seated wearer sees it: the
        // world is turned so the seat faces -z, so turn the anchor the same way.
        let facing = SIMD3(Float(seat.lookAt.x - seat.x), 0, Float(seat.lookAt.z - seat.z))
        let turn = simd_quatf(angle: atan2(facing.x, -facing.z), axis: SIMD3(0, 1, 0))
        let toward = turn.act(SIMD3(Float(m.anchorX - seat.x), 0, Float((m.anchor?.z ?? 0) - seat.z)))
        let yaw = atan2(toward.x, -toward.z) * 180 / .pi
        let held = max(-maxYaw, min(maxYaw, yaw))
        return at(degrees: held, distance: 2.4, height: eye + 0.65)
    }
}

/// Seated at the fifty, in a bowl at night, reached from the tabletop.
///
/// Entered on the Digital Crown's dial, with 100% full a tap away on the
/// ornament. Everything in the space comes from the scene: no board window, no
/// tabletop, and when the scene cannot be read, one small status panel instead
/// of an empty stand.
public struct StadiumSpaceView<Trailing: View>: View {
    let feed: SceneFeed
    @Binding var immersion: StadiumImmersion
    let look: SIMD2<Float>
    let leave: () -> Void
    let trailing: Trailing
    @State private var renderer = StadiumRenderer(mode: .stadium)
    @State private var hold = MomentHold()
    /// Everything in the space hangs off `world`, which hangs off `pivot` at
    /// the wearer's eye, so a debug build can turn the whole bowl about the
    /// eye and capture a side panel or the ornament below head-on.
    @State private var world = Entity()
    @State private var pivot = Entity()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// `look` is (yaw, pitch) in degrees, zero outside debug captures.
    public init(feed: SceneFeed, immersion: Binding<StadiumImmersion>, look: SIMD2<Float> = .zero,
                leave: @escaping () -> Void, @ViewBuilder trailing: () -> Trailing) {
        self.feed = feed
        self._immersion = immersion
        self.look = look
        self.leave = leave
        self.trailing = trailing()
    }

    public var body: some View {
        RealityView { content, attachments in
            world.addChild(renderer.root)
            let r = renderer
            renderer.subscription = content.subscribe(to: SceneEvents.Update.self) { event in
                MainActor.assumeIsolated { r.tick(event.deltaTime) }
            }
            let args = ProcessInfo.processInfo.arguments
            if let seat = StadiumShots.argument("-stadiumSeat") { renderer.sit(seat) }
            if args.contains("-stadiumMute") { renderer.setMuted(true) }
            let place: [(String, SIMD3<Float>)] = [
                // Closer than it was (2.4 m): at that distance the scorebug
                // was a thumbnail under the rim lights.
                ("scorebug", StadiumLayout.at(degrees: 0, distance: 1.8, height: StadiumLayout.eye + 0.5)),
                ("status", StadiumLayout.at(degrees: 0, distance: 2.0, height: StadiumLayout.eye + 0.05)),
                ("drive", StadiumLayout.at(degrees: -StadiumLayout.sideYaw, distance: 1.3, height: StadiumLayout.eye - 0.28)),
                ("trailing", StadiumLayout.at(degrees: StadiumLayout.sideYaw, distance: 1.3, height: StadiumLayout.eye - 0.28)),
                ("controls", StadiumLayout.at(degrees: 0, distance: 1.05, height: StadiumLayout.eye - 0.52)),
                ("moment", StadiumLayout.at(degrees: 0, distance: 3.2, height: StadiumLayout.eye + 0.85)),
            ]
            for (id, position) in place {
                guard let e = attachments.entity(for: id) else { continue }
                assert(StadiumLayout.below(position) <= StadiumLayout.maxBelow, "\(id) sits too low")
                face(e, at: position)
                world.addChild(e)
            }
            world.position = SIMD3(0, -StadiumLayout.eye, 0)
            pivot.addChild(world)
            if look == .zero {
                pivot.position = SIMD3(0, StadiumLayout.eye, 0)
                content.add(pivot)
            } else {
                // A debug capture turns the viewer's head, not the world. The
                // simulator camera is not at the seated eye the layout assumes,
                // and turning the world about the assumed eye swung the stands
                // across the real camera. Anchored to the head, the pivot is
                // the camera: the seat's eye lands exactly on it, and the
                // inverse of the head turn is applied to the world, which stays
                // level. yaw > 0 turns right, pitch > 0 looks up.
                let head = AnchorEntity(.head, trackingMode: .once)
                pivot.orientation = simd_quatf(angle: -look.y * .pi / 180, axis: SIMD3(1, 0, 0))
                    * simd_quatf(angle: look.x * .pi / 180, axis: SIMD3(0, 1, 0))
                head.addChild(pivot)
                content.add(head)
            }
        } update: { _, attachments in
            if let spec = feed.spec { renderer.apply(spec, reduceMotion: reduceMotion) }
            let reading = feed.spec != nil
            for id in ["scorebug", "drive", "trailing"] {
                attachments.entity(for: id)?.isEnabled = reading
            }
            attachments.entity(for: "status")?.isEnabled = !reading
            if let flag = attachments.entity(for: "moment") {
                flag.isEnabled = hold.shown != nil
                if let m = hold.shown, let spec = feed.spec {
                    face(flag, at: StadiumLayout.moment(m, seat: renderer.seat(spec)))
                }
            }
        } attachments: {
            Attachment(id: "scorebug") {
                if let spec = feed.spec { SceneScorebug(spec: spec) }
            }
            Attachment(id: "status") {
                StadiumStatus(message: feed.error)
            }
            Attachment(id: "drive") {
                if let spec = feed.spec { DriveLog(spec: spec) }
            }
            Attachment(id: "trailing") { trailing }
            Attachment(id: "controls") { controls }
            Attachment(id: "moment") {
                // The moment graphic is Broadcast's now, drawn in the world
                // over the end zone (BroadcastBanner); this glass chip stays
                // empty so the two never show at once.
                EmptyView()
            }
        }
        .onChange(of: feed.spec?.activeMoment, initial: true) { _, m in hold.arrive(m) }
        .task(id: hold.shown?.playId) {
            await hold.expire(after: feed.spec?.motion.momentSeconds ?? MomentHold.defaultSeconds)
        }
        .task { feed.start() }
        .onDisappear { feed.stop() }
    }

    /// Put an attachment at a point, facing the wearer. An attachment looks
    /// down +z by default.
    private func face(_ e: Entity, at position: SIMD3<Float>) {
        e.position = position
        e.look(at: SIMD3(0, StadiumLayout.eye, 0), from: position, relativeTo: world, forward: .positiveZ)
    }

    /// Two rows, so the ornament stays inside the 30-degree panels either
    /// side of it: the replay on top, where you are and how to leave below.
    private var controls: some View {
        VStack(spacing: 8) {
            HStack(spacing: 10) {
                ReplayControls(feed: feed)
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
            HStack(spacing: 12) {
                if let seats = feed.spec?.presentation.stadium.seats, !seats.isEmpty, let spec = feed.spec {
                    Menu {
                        ForEach(seats) { seat in
                            Button(seat.label) { renderer.sit(seat.id) }
                        }
                    } label: {
                        Label(renderer.seat(spec).label, systemImage: "chair.lounge")
                            .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                    }
                    .accessibilityHint("Moves the stadium around you to another seat")
                }
                Button {
                    renderer.setMuted(!renderer.muted)
                } label: {
                    Image(systemName: renderer.muted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                        .font(.system(size: 20, weight: .semibold)).frame(width: 60, height: 60)
                }
                .accessibilityLabel(renderer.muted ? "Unmute the crowd" : "Mute the crowd")
                Picker("Immersion", selection: $immersion) {
                    Text("Crown dial").tag(StadiumImmersion.dial)
                    Text("Full 100%").tag(StadiumImmersion.full)
                }
                .pickerStyle(.segmented)
                .frame(width: 300)
                Button(action: leave) {
                    Label("Leave stadium", systemImage: "xmark")
                        .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                }
                .accessibilityHint("Returns to the tabletop and windows you had open")
            }
        }
        .padding(12)
        .glassBackgroundEffect()
    }
}

/// The one thing shown in the stands when the scene cannot be read.
struct StadiumStatus: View {
    let message: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(message == nil ? "Finding the game…" : "Can't reach the game",
                  systemImage: message == nil ? "antenna.radiowaves.left.and.right" : "wifi.exclamationmark")
                .font(.system(size: 22, weight: .semibold))
            if let message {
                Text(message).font(.system(size: 16)).foregroundStyle(.secondary).lineLimit(3)
                Text("The scene comes from the Fantasy Edge API on your Mac.")
                    .font(.system(size: 15)).foregroundStyle(.secondary)
            }
        }
        .padding(24)
        .frame(width: 460, alignment: .leading)
        .glassBackgroundEffect()
    }
}
