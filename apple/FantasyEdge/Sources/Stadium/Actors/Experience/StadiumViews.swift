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

    /// `status` is what the stadium is showing rather than what the scene
    /// says: while the ball is in the air the board still reads the score
    /// before the play, and the glass must agree with it (`StatusGate`).
    public init(spec: SceneSpec, status: SceneSpec.Status? = nil) {
        var s = spec
        if let status { s.status = status }
        self.spec = s
    }

    // Visuals are Broadcast's (docs/actors/broadcast.md); placement stays
    // Experience's. A broadcast scorebug: each side a panel washed in its
    // chip's colour, the clock in the middle, the down on its own plate,
    // which turns red in the red zone.
    public var body: some View {
        HStack(spacing: 0) {
            side(spec.teams.away, score: spec.status.awayScore, has: spec.status.possession == "away")
            VStack(spacing: 5) {
                Text(spec.status.label.isEmpty ? spec.status.state.capitalized : spec.status.label)
                    .font(.system(size: 19, weight: .heavy)).monospacedDigit()
                if !spec.status.downDistance.isEmpty {
                    HStack(spacing: 5) {
                        if spec.status.redZone {
                            Image(systemName: "arrow.right.to.line").font(.system(size: 11, weight: .black))
                        }
                        Text(spec.status.downDistance.uppercased()).font(.system(size: 13, weight: .heavy)).kerning(0.6)
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Capsule().fill(spec.status.redZone ? swatch(spec.palette["fill.redZone"] ?? "#DF0B0B")
                                                                 : Color.black.opacity(0.35)))
                    .accessibilityLabel(spec.status.redZone ? "red zone, \(spec.status.downDistance)" : spec.status.downDistance)
                }
                if spec.isReplay {
                    Label("Replay", systemImage: "arrow.counterclockwise")
                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 22)
            side(spec.teams.home, score: spec.status.homeScore, has: spec.status.possession == "home")
        }
        .padding(8)
        .glassBackgroundEffect()
    }

    private func side(_ t: SceneSpec.Team, score: Double, has ball: Bool) -> some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 3).fill(swatch(t.chip)).frame(width: 6, height: 46)
            SceneChip(text: t.abbr, fill: t.chip, symbol: nil, hatch: t.hatch)
            Text("\(Int(score))").font(.system(size: 40, weight: .black)).monospacedDigit()
                .frame(minWidth: 50, alignment: .trailing)
            Image(systemName: "football.fill").font(.system(size: 15, weight: .bold))
                .opacity(ball ? 1 : 0)
                .accessibilityLabel(ball ? "has the ball" : "")
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 16).fill(swatch(t.chip).opacity(0.24)))
    }

    private func swatch(_ hex: String) -> Color {
        let c = SceneMath.rgba(hex)
        return Color(red: Double(c.x), green: Double(c.y), blue: Double(c.z))
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
    let rows: Int
    /// `rows` defaults to `visual.broadcast.driveLog.rows`; Experience may pass its own.
    public init(spec: SceneSpec, rows: Int? = nil) {
        self.spec = spec
        self.rows = max(1, rows ?? spec.look?.broadcast.driveLog.rows ?? 5)
    }
    private var newestLines: Int { spec.look?.broadcast.driveLog.newestLines ?? 2 }
    private var olderLines: Int { spec.look?.broadcast.driveLog.olderLines ?? 1 }

    // Visuals are Broadcast's: the newest play bright, the drive behind it
    // fading the way its trails do, each play's gain on the right.
    public var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let d = spec.shownDrive {
                HStack(spacing: 10) {
                    if let t = d.side.flatMap({ spec.teams.side($0) }) {
                        SceneChip(text: t.abbr, fill: t.chip, symbol: nil, hatch: t.hatch)
                    }
                    Text(d.result.isEmpty ? "\(d.team) drive" : d.result).font(.system(size: 20, weight: .heavy))
                    Spacer()
                    Text("\(d.arcs.count) plays").font(.system(size: 14, weight: .semibold)).foregroundStyle(.secondary)
                }
                let shown = Array(d.arcs.suffix(rows))
                ForEach(Array(shown.enumerated()), id: \.element.id) { i, arc in
                    let age = shown.count - 1 - i
                    HStack(alignment: .top, spacing: 10) {
                        Capsule().fill(color(arc.color)).frame(width: 4, height: 30).padding(.top, 2)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(label(arc)).font(.system(size: 14, weight: age == 0 ? .heavy : .semibold))
                            Text(arc.text).font(.system(size: 13)).foregroundStyle(.secondary)
                                .lineLimit(age == 0 ? newestLines : olderLines)
                        }
                        Spacer(minLength: 8)
                        Text(gain(arc, side: d.side)).font(.system(size: 15, weight: .heavy)).monospacedDigit()
                            .foregroundStyle(age == 0 ? .primary : .secondary)
                    }
                    .opacity(age == 0 ? 1 : max(0.5, 1 - Double(age) * 0.08))
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

    /// Yards toward the side's goal: home attacks +x.
    private func gain(_ arc: SceneSpec.Arc, side: String?) -> String {
        let yards = Int(((arc.toX - arc.fromX) * (side == "away" ? -1 : 1)).rounded())
        return yards > 0 ? "+\(yards)" : "\(yards)"
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
                // Skipping by score rather than by time, because a replay is
                // watched for the scores and "back thirty seconds" is a guess
                // at where one was. The server holds where they are, so this
                // is one call and lands a beat before the snap.
                Button { Task { await feed.previousScore() } } label: {
                    Image(systemName: "backward.end.fill")
                        .font(.system(size: 17, weight: .bold)).frame(width: 60, height: 60)
                }
                .buttonStyle(.borderless).accessibilityLabel("Previous score")

                Button {
                    Task { r.playing ? await feed.pause() : await feed.play() }
                } label: {
                    Image(systemName: r.playing ? "pause.fill" : "play.fill")
                        .font(.system(size: 22, weight: .bold)).frame(width: 60, height: 60)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel(r.playing ? "Pause" : "Play")

                Button { Task { await feed.nextScore() } } label: {
                    Image(systemName: "forward.end.fill")
                        .font(.system(size: 17, weight: .bold)).frame(width: 60, height: 60)
                }
                .buttonStyle(.borderless).accessibilityLabel("Next score")

                // The scores drawn on the bar itself, so a scrub has something
                // to aim at instead of being a blind drag through an hour.
                Slider(value: Binding(
                    get: { scrub ?? Double(r.gameSeconds ?? 0) },
                    set: { scrub = $0 }),
                       in: 0...Double(length)) { editing in
                    if !editing, let s = scrub {
                        Task { await feed.seek(Int(s)); scrub = nil }
                    }
                }
                .frame(width: 360)
                .background(alignment: .leading) {
                    if let marks = feed.markers?.scores, length > 0 {
                        GeometryReader { geo in
                            ForEach(marks) { m in
                                Capsule().fill(.secondary)
                                    .frame(width: 2, height: 10)
                                    .offset(x: geo.size.width
                                            * CGFloat(m.playAt) / CGFloat(length),
                                            y: geo.size.height / 2 - 5)
                            }
                        }
                        .allowsHitTesting(false)
                    }
                }

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

/// A game on the table: a volumetric window sized by `presentation.tabletop.volume`.
///
/// The miniature sits on its lit plinth and can be turned and scaled with a
/// pinch, inside the limits the tokens give, and tipped toward the wearer with
/// "Look closer". "Enter stadium" opens a gate of floodlight over the table
/// before the space opens, so the way in is a place rather than a cut.
public struct TabletopView: View {
    let feed: SceneFeed
    let enterStadium: () -> Void
    @State private var renderer = StadiumRenderer(mode: .tabletop)
    @State private var holder = Entity()
    @State private var gate = ArrivalGate()
    @State private var gateClock: EventSubscription?
    @State private var scale: Float = 1
    @State private var gestureScale: Float?
    @State private var yaw: Float = 0
    @State private var gestureYaw: Float?
    @State private var closer = false
    @State private var entering = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(feed: SceneFeed, enterStadium: @escaping () -> Void) {
        self.feed = feed
        self.enterStadium = enterStadium
    }

    private var table: SceneSpec.Look.TabletopLook? { ExperienceTokens.tabletop(feed.spec) }

    public var body: some View {
        RealityView { content in
            holder.name = "experience.tabletop"
            holder.addChild(renderer.root)
            holder.addChild(gate.root)
            holder.components.set(InputTargetComponent())
            content.add(holder)
            let r = renderer, g = gate
            renderer.subscription = content.subscribe(to: SceneEvents.Update.self) { event in
                MainActor.assumeIsolated { r.tick(event.deltaTime) }
            }
            gateClock = content.subscribe(to: SceneEvents.Update.self) { event in
                MainActor.assumeIsolated { g.tick(event.deltaTime) }
            }
        } update: { _ in
            guard let spec = feed.spec else { return }
            renderer.apply(spec, reduceMotion: reduceMotion)
            // The pinch target is the volume itself, so a pinch anywhere on
            // the model turns or scales it. Sized once the scene says how big.
            let v = spec.presentation.tabletop.volume
            if !holder.components.has(CollisionComponent.self), v.count == 3 {
                holder.components.set(CollisionComponent(shapes: [.generateBox(size: SIMD3(Float(v[0]), Float(v[1]), Float(v[2])))]))
            }
        }
        .gesture(MagnifyGesture().targetedToEntity(holder)
            .onChanged { value in
                let base = gestureScale ?? scale
                if gestureScale == nil { gestureScale = scale }
                scale = clampScale(base * Float(value.magnification))
                place(animated: false)
            }
            .onEnded { _ in gestureScale = nil })
        .simultaneousGesture(RotateGesture3D(constrainedToAxis: .y).targetedToEntity(holder)
            .onChanged { value in
                let base = gestureYaw ?? yaw
                if gestureYaw == nil { gestureYaw = yaw }
                let turn = Float(value.rotation.angle.radians) * (value.rotation.axis.y < 0 ? -1 : 1)
                yaw = base + turn
                place(animated: false)
            }
            .onEnded { _ in gestureYaw = nil })
        #if DEBUG
        // `-arrivalAt <0...1>` freezes the gate part-way open, for a still,
        // once the scene it takes its outline from has arrived.
        .onChange(of: feed.spec != nil, initial: true) { _, reading in
            guard reading, !entering, let p = Double(StadiumShots.argument("-arrivalAt") ?? ""),
                  let arrival = ExperienceTokens.arrival(feed.spec), prepareGate(arrival) else { return }
            entering = true
            renderer.root.components.set(OpacityComponent(opacity: Float(arrival.tabletopDim)))
            gate.open(at: p) {}
        }
        #endif
        // The scorebug rides in the ornament rather than floating in the
        // volume: the win-probability horizon fills the back of the volume
        // at exactly the height a floating scorebug wanted, and the two drew
        // through each other. It hangs below the volume's front edge
        // (`contentAlignment: .top`) rather than centred on it, where its top
        // half covered the front of the model.
        .ornament(attachmentAnchor: .scene(.bottomFront), contentAlignment: .top) {
            HStack(spacing: 12) {
                if let spec = feed.spec {
                    SceneScorebug(spec: spec, status: renderer.shownStatus)
                } else {
                    Text(feed.error ?? "Loading the game…").font(.system(size: 15)).padding()
                }
                ReplayControls(feed: feed)
                Button {
                    closer.toggle()
                    place(animated: true)
                } label: {
                    Label(closer ? "Step back" : "Look closer",
                          systemImage: closer ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                        .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                }
                .accessibilityHint("Tips the model toward you so the field is easier to read")
                Button {
                    arrive()
                } label: {
                    Label("Enter stadium", systemImage: "sportscourt.fill")
                        .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                }
                .disabled(entering)
                .accessibilityHint("Opens the stadium around you, seated at your last seat")
            }
            .padding(12)
            .glassBackgroundEffect()
        }
        .task { feed.start() }
        .onDisappear {
            feed.stop()
            gate.cancel()
        }
    }

    private func clampScale(_ s: Float) -> Float {
        let lo = Float(table?.minScale ?? 1), hi = Float(table?.maxScale ?? 1)
        return max(lo, min(hi, s))
    }

    /// The model's pose from the wearer's scale, turn and "Look closer" tilt.
    /// The wearer never moves; the model does, and only on their gesture.
    private func place(animated: Bool) {
        let tilt = closer ? Float(table?.closerTiltDegrees ?? 0) * .pi / 180 : 0
        var t = holder.transform
        t.scale = SIMD3(repeating: scale)
        t.rotation = simd_quatf(angle: tilt, axis: SIMD3(1, 0, 0)) * simd_quatf(angle: yaw, axis: SIMD3(0, 1, 0))
        let seconds = animated && !reduceMotion ? (table?.closerSeconds ?? 0) : 0
        if seconds > 0, holder.parent != nil {
            holder.move(to: t, relativeTo: holder.parent, duration: seconds, timingFunction: .easeInOut)
        } else {
            holder.transform = t
        }
    }

    /// The gate follows the plinth's edge: the outermost tier the table draws,
    /// plus the plinth's margin and bevel, as `ExperienceActor` builds it.
    /// False when there is no scene yet to take the outline from.
    @discardableResult
    private func prepareGate(_ arrival: SceneSpec.Look.Arrival) -> Bool {
        guard let spec = feed.spec, let look = ExperienceTokens.look(spec) else { return false }
        let t = spec.presentation.tabletop
        let drawn = spec.bowl.tiers.filter { t.bowlTiers.contains($0.name) }
        let base = look.baseplate
        let edge = ((drawn.last?.outer ?? spec.bowl.tiers.first?.outer ?? 36) + 3) * base.marginScale + (base.bevelYards ?? 0)
        let outline = (0..<96).map { k -> SIMD2<Float> in
            let p = SceneMath.bowlPoint(spec.bowl.shape, offset: edge, angle: Double(k) / 96 * 2 * .pi)
            return SIMD2(Float(p.x), Float(p.z))
        }
        gate.build(arrival, color: spec.palette["baseplate.rim"] ?? "#FFE9C2", outline: outline)
        gate.root.scale = SIMD3(repeating: Float(t.metersPerYard))
        gate.root.position = SIMD3(0, Float(t.floor), 0)
        return true
    }

    /// The way in: gate, then the space. Reduce motion opens the space at once.
    private func arrive() {
        guard !entering else { return }
        guard let arrival = ExperienceTokens.arrival(feed.spec), !reduceMotion else {
            ExperienceEvents.post(.gateOpening(seconds: 0, swellLead: 0))
            enterStadium()
            return
        }
        guard prepareGate(arrival) else {
            enterStadium()
            return
        }
        entering = true
        renderer.root.components.set(OpacityComponent(opacity: Float(arrival.tabletopDim)))
        ExperienceEvents.post(.gateOpening(seconds: arrival.gateSeconds, swellLead: arrival.swellLeadSeconds))
        gate.open {
            enterStadium()
            // If the space did not open (another space was up, or the system
            // refused), the table is still here: give it back its light.
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                gate.cancel()
                renderer.root.components.remove(OpacityComponent.self)
                entering = false
            }
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
}

/// Seated in a bowl at night, reached from the tabletop.
///
/// Entered on the Digital Crown's dial, with 100% full a tap away on the
/// controls. Everything in the space comes from the scene: no board window, no
/// tabletop, and when the scene cannot be read, one small status panel instead
/// of an empty stand.
///
/// The field of play is kept clear. Every panel's place is a slot in
/// `visual.experience.layout`, low and to the side; panels rest translucent
/// until looked at, the side panels fold to tabs, the controls fold to a pill
/// when left alone, and a celebrated moment takes every panel but the
/// scorebug away until it has been seen.
public struct StadiumSpaceView<Trailing: View>: View {
    let feed: SceneFeed
    @Binding var immersion: StadiumImmersion
    let look: SIMD2<Float>
    let trailingTitle: String?
    let leave: () -> Void
    let trailing: Trailing
    @State private var renderer = StadiumRenderer(mode: .stadium)
    @State private var hold = MomentHold()
    /// Everything in the space hangs off `world`, which hangs off `pivot` at
    /// the wearer's eye, so a debug build can turn the whole bowl about the
    /// eye and capture a side panel or the ornament below head-on.
    @State private var world = Entity()
    @State private var pivot = Entity()
    @State private var catcher = Entity()
    @State private var driveFolded = false
    @State private var trailingFolded = true
    @State private var controlsFolded = false
    @State private var touched = 0
    @State private var yielding = false
    @State private var pickerOpen = false
    @State private var hintShown = false
    @State private var arrived = false
    @State private var beforeMoment: (drive: Bool, trailing: Bool, controls: Bool)?
    /// Where the dock last put each panel. A reference, so moving them from
    /// `update` never writes view state mid-update.
    @State private var placer = SeatPlacement()
    /// Which way the dock is facing, in degrees from the seat's own forward.
    /// A recentre moves it to the nearest facing the scene solved; nothing
    /// else ever moves it, and the world never turns.
    @State private var dockFacing: Double = 0
    @State private var head = HeadFacing()
    @State private var recentreHint = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// `look` is (yaw, pitch) in degrees, zero outside debug captures.
    /// `trailingTitle` names the right-hand panel's tab; nil when there is
    /// nothing to show there.
    public init(feed: SceneFeed, immersion: Binding<StadiumImmersion>, look: SIMD2<Float> = .zero,
                trailingTitle: String? = nil,
                leave: @escaping () -> Void, @ViewBuilder trailing: () -> Trailing) {
        self.feed = feed
        self._immersion = immersion
        self.look = look
        self.trailingTitle = trailingTitle
        self.leave = leave
        self.trailing = trailing()
    }

    private var layout: SceneSpec.Look.Layout? { ExperienceTokens.layout(feed.spec) }
    private var panels: SceneSpec.Look.Panels? { ExperienceTokens.panels(feed.spec) }

    public var body: some View {
        RealityView { content, attachments in
            world.addChild(renderer.root)
            let r = renderer
            renderer.subscription = content.subscribe(to: SceneEvents.Update.self) { event in
                MainActor.assumeIsolated { r.tick(event.deltaTime) }
            }
            let args = ProcessInfo.processInfo.arguments
            // A shot's seat wins; otherwise the seat the wearer last chose.
            if let seat = StadiumShots.argument("-stadiumSeat") {
                renderer.sit(seat)
            } else if let saved = ExperiencePrefs.seat {
                renderer.sit(saved)
            }
            if args.contains("-stadiumMute") { renderer.setMuted(true) }
            if let slots = layout?.slots {
                let place: [(String, SceneSpec.Look.Slot)] = [
                    ("scorebug", slots.scorebug), ("status", slots.status), ("drive", slots.drive),
                    ("trailing", slots.trailing), ("controls", slots.controls), ("picker", slots.picker),
                    ("hint", slots.hint),
                ]
                for (id, slot) in place {
                    guard let e = attachments.entity(for: id) else { continue }
                    let position = StadiumLayout.position(slot)
                    assert(StadiumLayout.below(position) <= StadiumLayout.maxBelow, "\(id) sits too low")
                    face(e, at: position)
                    world.addChild(e)
                }
            }
            // A pinch anywhere in the room brings the dock to where the wearer
            // is looking, and the controls back with it. The catcher is a
            // sphere around the wearer rather than a panel ahead of them,
            // because the gesture is needed exactly when the dock is off to
            // the side: everything else sits nearer, so a pinch on a panel,
            // the field or a hologram still reaches that first.
            if let c = ExperienceTokens.controls(nil)?.revealCatcher {
                catcher.name = "experience.recentreCatcher"   // RecentreCatcher
                catcher.components.set(CollisionComponent(shapes: [.generateSphere(radius: Float(c.distance))]))
                catcher.components.set(InputTargetComponent())
                catcher.position = SIMD3(0, StadiumLayout.eye, 0)
                world.addChild(catcher)
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
            if let spec = feed.spec {
                renderer.apply(spec, reduceMotion: reduceMotion)
                placeDock(renderer.seat(spec).id, attachments)
            }
            let reading = feed.spec != nil
            let seatID = feed.spec.map { renderer.seat($0).id }
            let boardHasScore = seatID.flatMap { layout?.perSeat?[$0]?.scorebugHidden } ?? false
            attachments.entity(for: "scorebug")?.isEnabled = reading && !boardHasScore
            attachments.entity(for: "drive")?.isEnabled = reading
            attachments.entity(for: "trailing")?.isEnabled = reading && trailingTitle != nil
            attachments.entity(for: "status")?.isEnabled = !reading
            attachments.entity(for: "picker")?.isEnabled = reading && pickerOpen
            attachments.entity(for: "hint")?.isEnabled = hintShown
        } attachments: {
            Attachment(id: "scorebug") {
                if let spec = feed.spec { SceneScorebug(spec: spec, status: renderer.shownStatus) }
            }
            Attachment(id: "status") {
                StadiumStatus(message: feed.error)
            }
            Attachment(id: "drive") {
                if let spec = feed.spec {
                    FoldablePanel(title: "Drive", symbol: "list.bullet", folded: $driveFolded, yielding: yielding) {
                        DriveLog(spec: spec)
                            .frame(maxHeight: panelHeight(\.drive), alignment: .top)
                            .clipped()
                    }
                    .stadiumPanel(layout, panels, yielding: yielding && !reduceMotion)
                }
            }
            Attachment(id: "trailing") {
                FoldablePanel(title: trailingTitle ?? "More", symbol: "sportscourt", folded: $trailingFolded,
                              yielding: yielding) {
                    trailing
                        .frame(maxHeight: panelHeight(\.trailing), alignment: .top)
                        .clipped()
                }
                    .stadiumPanel(layout, panels, yielding: yielding && !reduceMotion)
            }
            Attachment(id: "controls") {
                Group {
                    if controlsFolded || (yielding && reduceMotion) {
                        ControlsPill { Task { await recentre() } }
                    } else {
                        controls
                    }
                }
                .stadiumPanel(layout, panels, yielding: yielding && !reduceMotion)
            }
            Attachment(id: "picker") {
                if let spec = feed.spec {
                    SeatPickerView(spec: spec, current: renderer.seat(spec).id, sit: { sit($0) },
                                   close: { pickerOpen = false; touch() })
                }
            }
            Attachment(id: "hint") {
                if recentreHint { RecentreHint() } else { CrownHint() }
            }
        }
        .gesture(SpatialTapGesture().targetedToEntity(catcher).onEnded { _ in
            Task { await recentre() }
        })
        .task { await head.start() }
        .task(id: feed.spec.map { renderer.seat($0).id } ?? "") { await watchFacing() }
        .onDisappear { head.stop() }
        // The stadium's moment, not the scene's: the composer holds it until
        // Broadcast has flown the play, so the panels yield and the celebration
        // shows as the ball lands rather than five seconds before it.
        .onChange(of: renderer.liveMoment, initial: true) { _, m in hold.arrive(m) }
        .task(id: hold.shown?.playId) {
            await hold.expire(after: feed.spec?.motion.momentSeconds ?? MomentHold.defaultSeconds)
        }
        // A moment takes the panels away while it is up: they fold, and the
        // folded tabs fade out too, so nothing but the scorebug and Broadcast's
        // banner is between the wearer and the score. `momentReturnSeconds`
        // after it goes, each panel comes back as the wearer had it.
        .task(id: hold.shown?.playId) {
            if hold.shown != nil {
                guard !yielding else { return }
                beforeMoment = (driveFolded, trailingFolded, controlsFolded)
                driveFolded = true
                trailingFolded = true
                controlsFolded = true
                yielding = true
                ExperienceEvents.post(.panelsYielded(true))
            } else if yielding {
                try? await Task.sleep(for: .seconds(panels?.momentReturnSeconds ?? 1))
                guard !Task.isCancelled, hold.shown == nil else { return }
                yielding = false
                if let was = beforeMoment {
                    driveFolded = was.drive
                    trailingFolded = was.trailing
                    controlsFolded = was.controls
                }
                beforeMoment = nil
                ExperienceEvents.post(.panelsYielded(false))
            }
        }
        // The controls fold themselves away when left alone.
        .task(id: touched) {
            try? await Task.sleep(for: .seconds(ExperienceTokens.controls(feed.spec)?.autoHideSeconds ?? 8))
            guard !Task.isCancelled, !pickerOpen else { return }
            controlsFolded = true
        }
        .task { await crownHint() }
        .task { feed.start() }
        .onChange(of: feed.spec != nil, initial: true) { _, reading in
            guard reading, !arrived, let spec = feed.spec else { return }
            arrived = true
            ExperienceEvents.post(.arrived(seat: renderer.seat(spec).id, full: immersion == .full))
            if let folded = panels?.startFolded {
                driveFolded = folded.drive
                trailingFolded = folded.trailing
            }
            applySeatFolds(renderer.seat(spec).id)
            #if DEBUG
            // A shot cannot pinch, so it may name the facing a recentre would
            // have landed on: -stadiumRecentre <degrees>.
            if let forced = StadiumShots.argument("-stadiumRecentre"), let yaw = Double(forced) {
                dockFacing = nearestFacing(yaw, layout?.perSeat?[renderer.seat(spec).id])
            }
            if ProcessInfo.processInfo.arguments.contains("-stadiumPicker") { pickerOpen = true }
            if ProcessInfo.processInfo.arguments.contains("-stadiumUnfold") { driveFolded = false; trailingFolded = false }
            if ProcessInfo.processInfo.arguments.contains("-stadiumControlsFolded") { controlsFolded = true }
            #endif
        }
        .onDisappear { feed.stop() }
    }

    /// Re-seat the dock in front of where the wearer is looking now: the
    /// nearest facing the scene solved, so every rule the dock obeys from the
    /// seat still holds from there. The dock fades out, moves and fades back
    /// (reduce motion: it is simply placed); the world never moves, and the
    /// wearer's head is not followed - nothing happens until they ask.
    private func recentre() async {
        reveal()
        recentreHint = false
        let solved = feed.spec.flatMap { layout?.perSeat?[renderer.seat($0).id] }
        let wanted = nearestFacing(head.yawDegrees ?? 0, solved)
        guard wanted != dockFacing else { return }
        let fade = ExperienceTokens.layout(feed.spec)?.dock?.recentre?.fadeSeconds ?? 0.22
        if reduceMotion {
            dockFacing = wanted
            return
        }
        for id in ["drive", "trailing", "controls"] {
            dockOpacity(id, 0, seconds: fade / 2)
        }
        try? await Task.sleep(for: .seconds(fade / 2))
        dockFacing = wanted
        try? await Task.sleep(for: .seconds(0.02))
        for id in ["drive", "trailing", "controls"] {
            dockOpacity(id, 1, seconds: fade / 2)
        }
    }

    /// The solved facing nearest the head, so the dock always lands somewhere
    /// the rules were checked. Beyond the table's reach it lands on the
    /// furthest solved facing, which is still in front of the wearer.
    private func nearestFacing(_ yaw: Double, _ solved: SceneSpec.Look.SeatPanels?) -> Double {
        let facings = solved?.facings ?? [0]
        return facings.min { abs($0 - yaw) < abs($1 - yaw) } ?? 0
    }

    /// Fade one dock attachment. RealityKit animates an opacity component's
    /// value, so setting it inside a withAnimation is all a fade needs.
    private func dockOpacity(_ id: String, _ value: Float, seconds: Double) {
        guard let e = placer.entities[id] else { return }
        var opacity = e.components[OpacityComponent.self] ?? OpacityComponent(opacity: 1)
        opacity.opacity = value
        e.components.set(opacity)
    }

    /// Say once, and only when it would help: the first time the wearer is
    /// looking well away from the dock, name the gesture that brings it back.
    private func watchFacing() async {
        guard !ExperiencePrefs.recentreHintShown else { return }
        let limit = layout?.maxSideDegrees ?? 30
        let after = ExperienceTokens.layout(feed.spec)?.dock?.recentre?.hintAfterSeconds ?? 1.5
        var away = 0.0
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(0.25))
            guard let yaw = head.yawDegrees else { continue }
            away = abs(yaw - dockFacing) > limit ? away + 0.25 : 0
            if away >= after {
                ExperiencePrefs.recentreHintShown = true
                recentreHint = true
                hintShown = true
                try? await Task.sleep(for: .seconds(4))
                recentreHint = false
                hintShown = false
                return
            }
        }
    }

    /// How tall a side panel may be here: the seat's own height where the dock
    /// had to shorten it for a thin band, else the panel size contract.
    private func panelHeight(_ side: KeyPath<SceneSpec.Look.PanelSizes, SceneSpec.Look.PanelSize>) -> CGFloat? {
        let seat = feed.spec.map { renderer.seat($0).id }
        let per = seat.flatMap { layout?.perSeat?[$0] }
        let slot = side == \.drive ? per?.drive : per?.trailing
        if let points = slot?.maxHeightPoints { return CGFloat(points) }
        return layout?.panelSizes.map { CGFloat($0[keyPath: side].maxHeightPoints) }
    }

    /// Put an attachment at a point, facing the wearer. An attachment looks
    /// down +z by default.
    private func face(_ e: Entity, at position: SIMD3<Float>) {
        e.position = position
        e.look(at: SIMD3(0, StadiumLayout.eye, 0), from: position, relativeTo: world, forward: .positiveZ)
    }

    private func touch() { touched &+= 1 }

    private func reveal() {
        controlsFolded = false
        touch()
    }

    /// Change seats: the renderer fades the world down and back (reduce
    /// motion: a cut), and the choice is remembered for next time.
    private func sit(_ id: String) {
        touch()
        pickerOpen = false
        guard let spec = feed.spec, id != renderer.seat(spec).id else { return }
        ExperiencePrefs.seat = id
        let fade = spec.look?.experience.camera.seatFadeSeconds ?? ExperienceTokens.bundled?.camera.seatFadeSeconds ?? 0.35
        ExperienceEvents.post(.seatChanging(to: id, fadeSeconds: reduceMotion ? 0 : fade))
        renderer.sit(id)
        applySeatFolds(id)
    }

    /// Put the side panels and the controls where the dock says for this seat:
    /// on the rail while folded, in the gallery while open. A tab stands where
    /// its tab belongs, not at the middle of the panel it folded from - that is
    /// what left the Elsewhere tab among the light banks from the upper deck.
    /// Called from `update` on every pass; an attachment moves only when its
    /// seat or its fold changes, and is never re-added.
    private func placeDock(_ seat: String, _ attachments: RealityViewAttachments) {
        guard let solved = layout?.perSeat?[seat] else { return }
        let per = solved.at(facing: dockFacing)
        let asTab = yielding && reduceMotion
        let wanted: [(String, SceneSpec.Look.PanelSlot, Bool)] = [
            ("drive", per.drive, driveFolded || asTab),
            ("trailing", per.trailing, trailingFolded || asTab),
            ("controls", per.controls, controlsFolded || asTab),
        ]
        for (id, p, folded) in wanted {
            if let e = attachments.entity(for: id) { placer.entities[id] = e }
            let key = "\(seat).\(folded).\(Int(dockFacing))"
            guard placer.placed[id] != key, let e = attachments.entity(for: id) else { continue }
            placer.placed[id] = key
            let (slot, scale) = p.place(folded: folded)
            face(e, at: StadiumLayout.position(slot, facing: dockFacing))
            e.scale = SIMD3(repeating: Float(scale))
        }
    }

    /// A panel with nowhere off the field from this seat starts folded.
    private func applySeatFolds(_ seat: String) {
        guard let per = layout?.perSeat?[seat] else { return }
        if per.drive.folded { driveFolded = true }
        if per.trailing.folded { trailingFolded = true }
        if per.controls.folded { controlsFolded = true }
    }

    /// The Crown hint, once, the first time the stadium opens on the dial.
    private func crownHint() async {
        guard let arrival = ExperienceTokens.arrival(feed.spec) else { return }
        #if DEBUG
        let forced = ProcessInfo.processInfo.arguments.contains("-stadiumHint")
        #else
        let forced = false
        #endif
        guard forced || (immersion == .dial && !(arrival.crownHintOnce && ExperiencePrefs.crownHintShown)) else { return }
        ExperiencePrefs.crownHintShown = true
        hintShown = true
        try? await Task.sleep(for: .seconds(arrival.crownHintSeconds))
        hintShown = false
    }

    /// Two rows, so the controls stay inside the side panels either side of
    /// them: the replay on top, where you are and how to leave below.
    private var controls: some View {
        VStack(spacing: 8) {
            HStack(spacing: 10) {
                ReplayControls(feed: feed)
                if feed.spec?.isReplay == true, let start = feed.replay?.driveStart {
                    Button {
                        touch()
                        // Just before the snap, so the first play flies.
                        Task { await feed.seek(max(0, start - 1)) }
                    } label: {
                        Label("Replay drive", systemImage: "gobackward")
                            .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                    }
                }
            }
            HStack(spacing: 12) {
                if let spec = feed.spec, !(spec.presentation.stadium.seats ?? []).isEmpty {
                    Button {
                        pickerOpen.toggle()
                        touch()
                    } label: {
                        Label(renderer.seat(spec).label, systemImage: "chair.lounge")
                            .font(.system(size: 17, weight: .semibold)).lineLimit(1)
                            .frame(maxWidth: 240, minHeight: 60)
                    }
                    .accessibilityHint("Opens a map of the stadium to choose another seat")
                }
                Button {
                    renderer.setMuted(!renderer.muted)
                    touch()
                } label: {
                    Image(systemName: renderer.muted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                        .font(.system(size: 20, weight: .semibold)).frame(width: 60, height: 60)
                }
                .accessibilityLabel(renderer.muted ? "Unmute the crowd" : "Mute the crowd")
                // One toggle rather than a 300-point segmented control: the
                // controls stay narrow enough to sit between the side panels.
                Button {
                    immersion = immersion == .full ? .dial : .full
                    touch()
                } label: {
                    Label(immersion == .full ? "Full" : "Dial",
                          systemImage: immersion == .full ? "circle.inset.filled" : "dial.medium")
                        .font(.system(size: 17, weight: .semibold)).frame(minWidth: 60, minHeight: 60)
                }
                .accessibilityLabel(immersion == .full ? "Full immersion" : "Crown dial immersion")
                .accessibilityHint(immersion == .full ? "Switches to the Digital Crown dial" : "Switches to 100% full immersion")
                Button {
                    ExperienceEvents.post(.leaving)
                    leave()
                } label: {
                    Label("Leave", systemImage: "xmark")
                        .font(.system(size: 17, weight: .semibold)).frame(minHeight: 60)
                }
                .accessibilityLabel("Leave stadium")
                .accessibilityHint("Returns to the tabletop and windows you had open")
                Button {
                    controlsFolded = true
                } label: {
                    Image(systemName: "chevron.down")
                        .font(.system(size: 18, weight: .semibold)).frame(width: 60, height: 60)
                }
                .accessibilityLabel("Fold the controls")
            }
        }
        .padding(12)
        .glassBackgroundEffect()
        .simultaneousGesture(TapGesture().onEnded { touch() })
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

/// Where each dock attachment was last put, as "<seat>.<folded>", so a pass
/// through `update` moves only what changed.
@MainActor
final class SeatPlacement {
    var placed: [String: String] = [:]
    /// The dock's attachments, so a recentre can fade them without asking
    /// the view for them again mid-update.
    var entities: [String: Entity] = [:]
}
