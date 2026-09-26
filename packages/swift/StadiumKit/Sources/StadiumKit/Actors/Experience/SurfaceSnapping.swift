import ARKit
import Foundation
import QuartzCore
import SwiftUI
import simd

// Putting the tabletop on a real table.
//
// Two tiers, and they are deliberately unequal. The first is the system's own:
// a volume declared `.volumeWorldAlignment(.gravityAligned)` snaps to a
// horizontal surface by itself, with no consent dialog and no ARKit, and tells
// the app it has through `\.surfaceSnappingInfo`. That is the tier that has to
// work for everybody, so it is the tier the model's rest height hangs off.
//
// The second tier says *which* surface and *how big*, and it costs the
// world-sensing prompt. It is started only once the first tier says the volume
// is actually on something, so nobody is asked for permission to measure a
// table they are not sitting at, and it is stopped the moment the volume goes
// away.
//
// Every way either tier can fail is a log line. The one that came before this
// file swallowed its ARKit error whole, which is indistinguishable from the
// feature not being wired up at all.

/// Whether the volume is resting on something real, and what.
///
/// `snapped` is the system's word and needs no permission. `surface` is the
/// classification, which the system withholds until the wearer has allowed
/// world sensing; nil means "not allowed, or not yet decided", never "not a
/// table". `trouble` is the last thing that went wrong, in the wearer's
/// language, for a caption - it is never nil merely because nothing is wrong.
@MainActor
@Observable
public final class TabletopSurface {
    /// The volume is resting on a real horizontal surface.
    public private(set) var snapped = false
    /// What that surface is ("table", "floor", ...), when we are allowed to know.
    public private(set) var surface: String?
    /// Why the app cannot say more than it is saying.
    public private(set) var trouble: String?

    public init() {}

    /// The system's answer, already reduced to values any visionOS can hold.
    func read(snapped: Bool, surface: String?, authorization: String) {
        if snapped != self.snapped {
            StadiumLog.log.notice(
                "[surface] volume \(snapped ? "snapped to" : "lifted off", privacy: .public) a surface")
        }
        if surface != self.surface, let surface {
            StadiumLog.log.notice("[surface] the system calls it a \(surface, privacy: .public)")
        }
        self.snapped = snapped
        self.surface = surface
        // A snap with no classification is the ordinary unauthorised case, and
        // it is worth saying so once rather than looking like a dead feature.
        if snapped, surface == nil, trouble == nil {
            trouble = "Allow Surroundings to let the stadium know which table it is on."
            StadiumLog.log.notice(
                "[surface] snapped but unclassified; world sensing is \(authorization, privacy: .public)")
        }
    }

    /// visionOS before 26 never tells an app its volume has snapped.
    func unavailable() {
        guard trouble == nil else { return }
        trouble = "This visionOS does not tell an app when its volume is on a table."
        StadiumLog.log.notice("[surface] no surfaceSnappingInfo on this visionOS; the model keeps its own rest height")
    }
}

/// Reads `\.surfaceSnappingInfo` into a `TabletopSurface`.
///
/// It is a modifier rather than a property on the view because the environment
/// key is visionOS 26 and the apps deploy to 2.0; a stored `@Environment` there
/// would raise the whole view's floor.
@available(visionOS 26.0, *)
struct SurfaceSnapReader: ViewModifier {
    let state: TabletopSurface
    @Environment(\.surfaceSnappingInfo) private var info

    func body(content: Content) -> some View {
        content.onChange(of: info, initial: true) { _, now in
            state.read(snapped: now.isSnapped,
                       surface: now.classification.map { String(describing: $0) },
                       authorization: String(describing: SurfaceSnappingInfo.authorizationStatus))
        }
    }
}

extension View {
    /// Follow the volume's own snapping, where the system offers it.
    @ViewBuilder
    func readsSurfaceSnapping(into state: TabletopSurface) -> some View {
        if #available(visionOS 26.0, *) {
            modifier(SurfaceSnapReader(state: state))
        } else {
            onAppear { state.unavailable() }
        }
    }
}

/// The plane pass: which table the volume is on, and how much of it there is.
///
/// Held to four numbers per plane, never to ARKit's anchors, and stopped the
/// moment nobody is asking - a volume that is not on a surface does not run
/// one of these, and a volume that has closed certainly does not.
///
/// It needs two things the first tier does not: `NSWorldSensingUsageDescription`
/// in the app's Info.plist, without which `ARKitSession.run` throws, and the
/// wearer's yes to the prompt that key describes. On visionOS ARKit also only
/// delivers to an app that holds an immersive space, so from a bare volume the
/// run is expected to be refused; the refusal is logged with its reason and the
/// tabletop carries on with the snap alone.
@MainActor
@Observable
public final class SurfaceScout {
    /// A table, in metres, as the wearer's room has it.
    public struct Table: Equatable, Sendable {
        public let widthMeters: Float
        public let depthMeters: Float
        /// Nil when no floor has been seen to measure from.
        public let aboveFloorMeters: Float?
        public let centre: SIMD3<Float>
    }

    public enum Status: Equatable, Sendable {
        case idle
        case unsupported
        case denied
        case searching
        case found
        case refused(String)
    }

    public private(set) var status: Status = .idle
    /// The one table worth drawing on. Nil until one is found, and again the
    /// moment it stops being reported.
    public private(set) var table: Table?

    /// What each horizontal plane is worth, and nothing else about it. Sized by
    /// the room, a few dozen entries at most, and dropped whole on `stop`.
    private struct Plane {
        enum Kind { case table, floor, other, unknown }
        let kind: Kind
        let y: Float
        let width: Float
        let depth: Float
        let centre: SIMD3<Float>
        var area: Float { width * depth }
    }

    private var seen: [UUID: Plane] = [:]
    private var session: ARKitSession?
    private var task: Task<Void, Never>?
    private var look: SceneSpec.Look.SurfaceLook?
    private let planes = PlaneDetectionProvider(alignments: [.horizontal])
    private let world = WorldTrackingProvider()

    public init() {}

    public var running: Bool { task != nil }

    /// Start looking. Cheap to call twice; the second is a no-op.
    public func start(_ look: SceneSpec.Look.SurfaceLook?) {
        guard task == nil else { return }
        guard let look else {
            StadiumLog.log.notice("[surface] no visual.experience.surface in the scene; no plane pass")
            return
        }
        guard PlaneDetectionProvider.isSupported else {
            status = .unsupported
            StadiumLog.log.notice("[surface] PlaneDetectionProvider is unsupported here (the simulator has no planes)")
            return
        }
        self.look = look
        let session = ARKitSession()
        self.session = session
        task = Task { @MainActor [weak self] in await self?.run(session) }
    }

    /// Stop looking and forget the room. Called when the volume closes, and
    /// when it lifts off the surface: a plane pass nobody is reading is a
    /// camera budget nobody is paying for.
    public func stop() {
        guard task != nil || session != nil else { return }
        task?.cancel()
        task = nil
        session?.stop()
        session = nil
        seen.removeAll()
        table = nil
        status = .idle
        StadiumLog.log.notice("[surface] plane pass stopped")
    }

    private func run(_ session: ARKitSession) async {
        let wanted = PlaneDetectionProvider.requiredAuthorizations
        let granted = await session.requestAuthorization(for: wanted)
        for kind in wanted where granted[kind] != .allowed {
            status = .denied
            let said = String(describing: granted[kind])
            StadiumLog.log.error("[surface] \(String(describing: kind), privacy: .public) is \(said, privacy: .public): the table cannot be measured. Settings › Privacy & Security › Surroundings.")
            return
        }
        do {
            try await session.run([planes, world])
        } catch {
            let why = String(describing: error)
            status = .refused(why)
            StadiumLog.log.error("[surface] ARKit refused the plane pass: \(why, privacy: .public). Two things do this: no NSWorldSensingUsageDescription in the Info.plist, and no immersive space open - visionOS hands plane data only to an app that has one. The volume keeps the system's own snap, which needs neither.")
            return
        }
        status = .searching
        StadiumLog.log.notice("[surface] plane pass running")
        for await update in planes.anchorUpdates {
            if Task.isCancelled { break }
            absorb(update)
            choose()
        }
    }

    private func absorb(_ update: AnchorUpdate<PlaneAnchor>) {
        let anchor = update.anchor
        guard update.event != .removed else {
            seen[anchor.id] = nil
            return
        }
        let extent = anchor.geometry.extent
        let placed = anchor.originFromAnchorTransform * extent.anchorFromExtentTransform
        let centre = SIMD3(placed.columns.3.x, placed.columns.3.y, placed.columns.3.z)
        seen[anchor.id] = Plane(kind: kind(of: anchor), y: centre.y,
                                width: abs(extent.width), depth: abs(extent.height), centre: centre)
    }

    /// What ARKit calls the plane. Only visionOS 26's `surfaceClassification` is
    /// read: the older `classification` is deprecated, and judging a plane by
    /// its height and size alone - which is what `.unknown` falls through to -
    /// is honest rather than warning-shaped.
    private func kind(of anchor: PlaneAnchor) -> Plane.Kind {
        guard #available(visionOS 26.0, *) else { return .unknown }
        switch anchor.surfaceClassification {
        case .table, .cabinet: return .table
        case .floor:           return .floor
        case .none:            return .unknown
        default:               return .other
        }
    }

    /// The best table in the room, or none.
    ///
    /// Largest wins, among the planes that are the right height above the
    /// lowest surface in the room, big enough to stand a stadium on, and near
    /// enough to the wearer to be the table they are at rather than the one in
    /// the next room.
    private func choose() {
        guard let look else { return }
        let floorY = seen.values.filter { $0.kind == .floor }.map(\.y).min()
            ?? seen.values.map(\.y).min()
        let head = world.queryDeviceAnchor(atTimestamp: CACurrentMediaTime())?
            .originFromAnchorTransform.columns.3
        var best: Plane?
        for plane in seen.values {
            guard plane.kind == .table || plane.kind == .unknown else { continue }
            guard min(plane.width, plane.depth) >= Float(look.minTableMeters) else { continue }
            if let floorY, plane.kind != .table {
                let rise = plane.y - floorY
                guard rise >= Float(look.tableHeightMeters.minimum),
                      rise <= Float(look.tableHeightMeters.maximum) else { continue }
            }
            if let head {
                let reach = simd_length(SIMD2(plane.centre.x - head.x, plane.centre.z - head.z))
                guard reach <= Float(look.planeSearchMeters) else { continue }
            }
            if best == nil || plane.area > best!.area { best = plane }
        }
        // Rounded to the centimetre, so a plane that jitters by a millimetre
        // does not re-fit the model or fill the log.
        let found = best.map { plane in
            Table(widthMeters: ((plane.width * 100).rounded()) / 100,
                  depthMeters: ((plane.depth * 100).rounded()) / 100,
                  aboveFloorMeters: floorY.map { (((plane.y - $0) * 100).rounded()) / 100 },
                  centre: plane.centre)
        }
        guard found != table else { return }
        table = found
        if let found {
            status = .found
            let said = String(format: "%.2f x %.2f m", found.widthMeters, found.depthMeters)
                + (found.aboveFloorMeters.map { String(format: ", %.2f m up", $0) } ?? "")
            StadiumLog.log.notice("[surface] table \(said, privacy: .public)")
        } else {
            status = .searching
            StadiumLog.log.notice("[surface] no table in reach; the model keeps the size the wearer gave it")
        }
    }
}
