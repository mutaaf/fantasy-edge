import Foundation
import RealityKit
import simd

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

extension StadiumLayout {
    /// A slot from `visual.experience.layout`, as a point in the wearer's space.
    static func position(_ slot: SceneSpec.Look.Slot) -> SIMD3<Float> {
        at(degrees: Float(slot.yaw), distance: Float(slot.distance), height: eye + Float(slot.height))
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
    func open(at progress: Double? = nil, then: @escaping () -> Void) {
        root.isEnabled = true
        if let progress {
            draw(progress)
            return
        }
        elapsed = 0
        done = then
        draw(0)
    }

    func cancel() {
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
            elapsed = nil
            let finish = done
            done = nil
            finish?()
        } else {
            elapsed = e
        }
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
