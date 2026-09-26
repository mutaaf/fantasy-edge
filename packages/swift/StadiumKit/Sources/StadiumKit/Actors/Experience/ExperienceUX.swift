import ARKit
import Foundation
import OSLog
import QuartzCore
import RealityKit
import simd

private let log = Logger(subsystem: "StadiumKit", category: "experience")

// The experience's moving parts that are not panels: where its numbers come
// from, what it remembers, what it tells the other actors, and the gate of
// light that opens over the table on the way in.

/// `visual.experience`, with the bundled tokens standing in for a server that
/// predates a section. Both are the same tokens.json, so there is still one
/// source and no number lives only in Swift.
enum ExperienceTokens {
    static let bundled: SceneSpec.Look.ExperienceLook? = SceneSpec.Look.bundled()?.experience

    static func look(_ spec: SceneSpec?) -> SceneSpec.Look.ExperienceLook? { spec?.look?.experience ?? bundled }
    static func layout(_ spec: SceneSpec?) -> SceneSpec.Look.Layout? { look(spec)?.layout ?? bundled?.layout }
    static func panels(_ spec: SceneSpec?) -> SceneSpec.Look.Panels? { look(spec)?.panels ?? bundled?.panels }
    static func controls(_ spec: SceneSpec?) -> SceneSpec.Look.Controls? { look(spec)?.controls ?? bundled?.controls }
    static func arrival(_ spec: SceneSpec?) -> SceneSpec.Look.Arrival? { look(spec)?.arrival ?? bundled?.arrival }
    static func picker(_ spec: SceneSpec?) -> SceneSpec.Look.SeatPicker? { look(spec)?.seatPicker ?? bundled?.seatPicker }
    static func tabletop(_ spec: SceneSpec?) -> SceneSpec.Look.TabletopLook? { look(spec)?.tabletop ?? bundled?.tabletop }
    static func surface(_ spec: SceneSpec?) -> SceneSpec.Look.SurfaceLook? { look(spec)?.surface ?? bundled?.surface }
}

/// What the stadium remembers between visits: the seat, and whether the Crown
/// hint has been shown. The replay's position is the API's, which already
/// outlives the app.
enum ExperiencePrefs {
    private static let seatKey = "fe.stadium.seat"
    private static let hintKey = "fe.stadium.crownHintShown"

    static var seat: String? {
        get { UserDefaults.standard.string(forKey: seatKey) }
        set { UserDefaults.standard.set(newValue, forKey: seatKey) }
    }

    static var crownHintShown: Bool {
        get { UserDefaults.standard.bool(forKey: hintKey) }
        set { UserDefaults.standard.set(newValue, forKey: hintKey) }
    }

    private static let recentreKey = "fe.stadium.recentreHintShown"

    static var recentreHintShown: Bool {
        get { UserDefaults.standard.bool(forKey: recentreKey) }
        set { UserDefaults.standard.set(newValue, forKey: recentreKey) }
    }
}

/// The experience's beats, for the actors that score them (Moments & Audio
/// swell the crowd as the gate opens and duck it through a seat change).
/// Posted on `ExperienceEvents.name` with the event under "event". The
/// contract is in docs/actors/experience.md.
public enum ExperienceEvent: Equatable, Sendable {
    /// The gate starts opening over the table; the space opens `seconds` later.
    case gateOpening(seconds: Double, swellLead: Double)
    /// The wearer is in a seat. `full` is 100% immersion, else the Crown dial.
    case arrived(seat: String, full: Bool)
    /// A seat change starts; the world is dark at `fadeSeconds`.
    case seatChanging(to: String, fadeSeconds: Double)
    /// A celebrated moment took the panels away, or gave them back.
    case panelsYielded(Bool)
    case leaving
}

public enum ExperienceEvents {
    public static let name = Notification.Name("fe.stadium.experience")

    @MainActor
    public static func post(_ event: ExperienceEvent) {
        NotificationCenter.default.post(name: name, object: nil, userInfo: ["event": event])
    }
}

/// Which way the wearer's head is turned, in degrees about the vertical from
/// the stadium's own forward, so a recentre can put the dock in front of where
/// they are looking. Head pose, never gaze: the app still never learns where
/// the wearer is looking within their view.
///
/// visionOS hands this out only to an app with an immersive space open, and
/// only through ARKit, so this is best-effort: no session, no anchor, no yaw,
/// and the dock recentres to the seat's own forward instead, which is the
/// worst it can do and still useful.
@MainActor
final class HeadFacing {
    private var session: ARKitSession?
    private let provider = WorldTrackingProvider()
    private var running = false

    func start() async {
        guard !running else { return }
        guard WorldTrackingProvider.isSupported else {
            log.info("no world tracking here; the dock will recentre to the seat's own forward")
            return
        }
        running = true
        let session = ARKitSession()
        self.session = session
        do {
            try await session.run([provider])
            log.info("world tracking is running; a recentre can use the head's own facing")
        } catch {
            // Best-effort, but never silent: this used to swallow the error
            // whole, and a recentre that quietly fell back to the seat's
            // forward was indistinguishable from one that worked.
            log.error("world tracking did not start (\(error.localizedDescription, privacy: .public)); recentring to the seat's own forward instead")
            running = false
            self.session = nil
            // Silence here is the bug that hid this whole area: no session, no
            // yaw, and nothing anywhere saying why the recentre felt inert.
            StadiumLog.log.error("[head] ARKit refused world tracking: \(String(describing: error), privacy: .public); the dock recentres to the seat's own forward")
        }
    }

    func stop() {
        guard running || session != nil else { return }
        log.info("stopping world tracking")
        session?.stop()
        session = nil
        running = false
    }

    /// Degrees to the right of the stadium's forward, or nil when ARKit has
    /// nothing to say. `+z` is behind the wearer, matching StadiumLayout.at.
    var yawDegrees: Double? {
        guard running, provider.state == .running,
              let anchor = provider.queryDeviceAnchor(atTimestamp: CACurrentMediaTime()) else { return nil }
        let m = anchor.originFromAnchorTransform
        let forward = SIMD3<Float>(-m.columns.2.x, -m.columns.2.y, -m.columns.2.z)
        let flat = simd_length(SIMD2(forward.x, forward.z))
        guard flat > 1e-4 else { return nil }
        return Double(atan2(forward.x, -forward.z)) * 180 / .pi
    }
}

extension StadiumLayout {
    /// A slot from `visual.experience.layout`, as a point in the wearer's
    /// space. `facing` turns the whole dock to where a recentre put it; the
    /// slot's own yaw is measured from that facing.
    static func position(_ slot: SceneSpec.Look.Slot, facing: Double = 0) -> SIMD3<Float> {
        at(degrees: Float(slot.yaw + facing), distance: Float(slot.distance), height: eye + Float(slot.height))
    }
}

/// The gate of light over the table: a curtain of floodlight that rises from
/// a ring on the table and widens while the table dims, then the space opens.
/// A disc alone read as frosted glass under the room's light; a lit wall with
/// a bright lip reads as light. Drawn in the table's yards.
@MainActor
final class ArrivalGate {
    let root = Entity()
    private var disc: ModelEntity?
    private var ring: ModelEntity?
    private var wall: ModelEntity?
    private var elapsed: Double?
    private var arrival: SceneSpec.Look.Arrival?
    private var done: (() -> Void)?
    /// The gate's own clock, for when nothing ticks it. See `open`.
    private var fallback: Task<Void, Never>?

    /// How long past `gateSeconds` the gate waits for a tick before finishing
    /// itself. Not a design number - the curtain's length is
    /// `visual.experience.arrival.gateSeconds` - but the slack a first frame
    /// under load is allowed before the way in is called broken.
    static let graceSeconds: Double = 1.5

    init() {
        root.name = "experience.gate"
        root.isEnabled = false
    }

    var running: Bool { elapsed != nil }

    /// Build the gate's meshes once, in yards, along `outline`: the plinth's
    /// edge, so the curtain rises around the model rather than through it.
    func build(_ arrival: SceneSpec.Look.Arrival, color: String, outline: [SIMD2<Float>]) {
        guard disc == nil, outline.count > 2 else { return }
        self.arrival = arrival
        var d = MeshBuilder(), w = MeshBuilder(), pts: [SIMD3<Float>] = []
        for k in 0..<outline.count {
            let p0 = outline[k], p1 = outline[(k + 1) % outline.count]
            let a = SIMD3(p0.x, 0, p0.y), b = SIMD3(p1.x, 0, p1.y)
            d.quad(SIMD3(0, 0, 0), b, a, SIMD3(0, 0, 0), normal: SIMD3(0, 1, 0))
            // A unit-high wall, scaled to the curtain's height as it rises.
            w.quad(a, b, SIMD3(b.x, 1, b.z), SIMD3(a.x, 1, a.z))
            pts.append(a)
        }
        pts.append(pts[0])
        var r = MeshBuilder()
        r.tube(pts, radius: 0.6, sides: 6)
        let disc = d.entity("gate.disc", StadiumLook.glow(color, opacity: arrival.gateOpacity * 0.12, texture: nil))
        let wall = w.entity("gate.wall", StadiumLook.glow(color, opacity: arrival.gateWallOpacity ?? arrival.gateOpacity * 0.25,
                                                           texture: nil))
        let ring = r.entity("gate.ring", StadiumLook.glow(color, opacity: arrival.gateOpacity, texture: nil))
        for e in [disc, wall, ring] { root.addChild(e) }
        self.disc = disc
        self.wall = wall
        self.ring = ring
    }

    /// Open the gate, then call `then`. `at` freezes it part-way, for a still.
    ///
    /// The gate is driven by a `SceneEvents.Update` subscription made in the
    /// tabletop's RealityView. If that subscription is not alive - a volume
    /// torn down mid-open, a RealityView whose make closure never ran, a scene
    /// that stopped updating - `tick` never runs, `then` never fires and the
    /// way into the stadium is dead for the life of the window with nothing
    /// said. So the gate keeps a clock of its own as well and finishes on
    /// whichever arrives first. `then` is called exactly once either way.
    func open(at progress: Double? = nil, then: @escaping () -> Void) {
        root.isEnabled = true
        if let progress {
            draw(progress)
            return
        }
        elapsed = 0
        done = then
        draw(0)
        let limit = (arrival?.gateSeconds ?? 1.4) + Self.graceSeconds
        fallback?.cancel()
        fallback = Task { @MainActor [weak self] in
            do { try await Task.sleep(for: .seconds(limit)) } catch { return }
            guard let self, self.done != nil else { return }
            log.error("the arrival gate was never ticked in \(limit, format: .fixed(precision: 1))s; opening the stadium anyway")
            self.finish()
        }
    }

    func cancel() {
        if done != nil { log.info("the arrival gate was cancelled part-way") }
        fallback?.cancel()
        fallback = nil
        elapsed = nil
        done = nil
        root.isEnabled = false
    }

    func tick(_ dt: Double) {
        guard var e = elapsed, let arrival else { return }
        e += dt
        let p = min(1, e / max(0.1, arrival.gateSeconds))
        draw(p)
        if p >= 1 {
            finish()
        } else {
            elapsed = e
        }
    }

    /// Hand the way in over, once, from whichever clock got there first.
    private func finish() {
        elapsed = nil
        fallback?.cancel()
        fallback = nil
        let then = done
        done = nil
        then?()
    }

    /// Ease out, so the gate rushes open and settles rather than crawling.
    private func draw(_ p: Double) {
        guard let arrival else { return }
        let eased = Float(1 - pow(1 - p, 3))
        // The curtain stands at the plinth's edge and widens only a little
        // (by gateWiden of its size at the end); what grows is its height.
        let edge = 1 + Float(arrival.gateWiden) * eased
        let lift = max(0.01, Float(arrival.gateHeightYards) * eased)
        disc?.scale = SIMD3(edge, 1, edge)
        disc?.position = SIMD3(0, 0.2, 0)
        wall?.scale = SIMD3(edge, lift, edge)
        ring?.scale = SIMD3(edge, 1, edge)
        ring?.position = SIMD3(0, lift, 0)
        root.components.set(OpacityComponent(opacity: Float(min(1, p * 3))))
    }
}
