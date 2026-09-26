import Observation
import OSLog
import SwiftUI

private let log = Logger(subsystem: "StadiumKit", category: "stadium")

/// The walk into the stadium and back out again, for any app that has one.
///
/// Full immersion hides other apps, not this one: the first simulator capture
/// of the stadium had the tabletop volume sitting in the middle of the bowl and
/// the board's "No board yet" window floating in the stands, nav ornament and
/// all. So the stadium is entered through here. It writes down which of the
/// app's windows are open, opens the space, closes those windows, and on the
/// way out reopens exactly them before the space goes.
///
/// SwiftUI cannot be asked which windows are open, so each window reports its
/// own appearance. While a passage is under way the disappearances it causes
/// are not recorded; otherwise closing the windows would erase the list of
/// windows to bring back.
/// A window this app can open, named the way SwiftUI names it: an id, and the
/// value for a `WindowGroup(for:)`.
public struct StadiumWindow: Hashable, Sendable {
    public let id: String
    public let value: String?

    public init(id: String, value: String? = nil) {
        self.id = id
        self.value = value
    }

    public static func id(_ id: String) -> StadiumWindow { .init(id: id) }
}

@MainActor
@Observable
public final class StadiumPassage {
    public typealias Window = StadiumWindow

    public private(set) var open: Set<Window> = []
    public private(set) var inStadium = false

    /// Why the last walk into the stadium did not happen, for the caller to
    /// show. `enter` used to return silently on a refusal, so a tap with the
    /// board's room already open played the gate, dimmed the table and did
    /// nothing else - indistinguishable from a bug.
    public private(set) var refusal: String?

    /// How long the table needs to be up before the space can read the game
    /// off it. The walk-in hooks each had their own sleep; this is the one.
    public static let doorSeconds: Double = 3

    /// The space to open, and what to bring back when the wearer walked
    /// straight into the stadium with nothing behind them - the app's front
    /// door, which is its board or its wall.
    private let spaceID: String
    private let frontDoor: Window

    public init(spaceID: String = "stadium", frontDoor: Window) {
        self.spaceID = spaceID
        self.frontDoor = frontDoor
    }

    @ObservationIgnored private var saved: Set<Window> = []
    @ObservationIgnored private var moving = false
    @ObservationIgnored private var leaving = false

    public func appeared(_ w: Window) { open.insert(w) }

    /// A window that opens while the stadium is up belongs behind it, not in
    /// the stands. Under load the tabletop the launch opened could finish
    /// appearing after `enter` had already written down what to close, and it
    /// sat in the middle of the bowl, win-probability labels and all. Returns
    /// true when the window should close itself; it comes back on the way out.
    public func appearedInside(_ w: Window) -> Bool {
        guard inStadium else { return false }
        saved.insert(w)
        moving = true
        defer { moving = false }
        open.remove(w)
        log.info("a window appeared inside the stadium; closing it until the way out")
        return true
    }

    public func disappeared(_ w: Window) {
        guard !moving else { return }
        open.remove(w)
    }

    public func renamed(from old: Window, to new: Window) {
        open.remove(old)
        open.insert(new)
    }

    /// Open the stadium and put every other window of this app away.
    ///
    /// Tabletops are closed before the board because the stadium is often
    /// entered from the board's own launch task, and closing the board ends
    /// that task; whatever comes after it would never run.
    public func enter(openSpace: OpenImmersiveSpaceAction, dismissWindow: DismissWindowAction,
                      before: () -> Void = {}) async {
        guard !inStadium else { log.info("enter ignored: already in the stadium"); return }
        // The app's own business before the walk - which immersion style the
        // dial opens at, say - done while nothing has moved yet.
        before()
        let opened = open
        refusal = nil
        switch await openSpace(id: spaceID) {
        case .opened:
            break
        case .userCancelled:
            // Nothing was closed, so nothing needs restoring - but the wearer
            // has watched the gate rise for nothing unless we say so.
            refusal = "The stadium was not opened."
            log.info("enter refused: the wearer cancelled")
            return
        case .error:
            refusal = "Leave the immersive board before entering the stadium."
            log.error("enter refused: another space is open, or the system refused")
            return
        @unknown default:
            refusal = "The stadium could not be opened."
            log.error("enter refused: unknown result from openImmersiveSpace")
            return
        }
        saved = opened
        inStadium = true
        moving = true
        log.info("entered stadium; closing \(opened.count) window(s)")
        for w in opened where w.value != nil {
            dismissWindow(id: w.id, value: w.value!)
            // A window visionOS restored on launch carries no value, so
            // dismissing by value misses it and it stayed in the middle of the
            // bowl. Dismiss by id as well.
            dismissWindow(id: w.id)
        }
        for w in opened where w.value == nil { dismissWindow(id: w.id) }
        moving = false
    }

    /// Bring back what was open, then close the space. Windows first: an app
    /// whose last scene closes is an app with nothing on screen.
    public func leave(openWindow: OpenWindowAction, dismissSpace: DismissImmersiveSpaceAction) async {
        guard inStadium else { log.info("leave ignored: not in stadium"); return }
        leaving = true
        restore(openWindow)
        log.info("windows reopened; dismissing stadium")
        await dismissSpace()
        log.info("stadium dismissed")
        leaving = false
    }

    /// The space went away without `leave` - the Digital Crown press, or the
    /// system closing it. The windows still have to come back.
    public func spaceDisappeared(openWindow: OpenWindowAction) {
        guard inStadium, !leaving else { return }
        restore(openWindow)
    }

    private func restore(_ openWindow: OpenWindowAction) {
        let back = saved
        saved = []
        inStadium = false
        // Launched straight into the stadium with nothing behind it: the front
        // door is what comes back.
        if back.isEmpty { openWindow(id: frontDoor.id); return }
        for w in back where w.value == nil { openWindow(id: w.id) }
        for w in back where w.value != nil { openWindow(id: w.id, value: w.value!) }
    }
}

/// Reports a window's presence to the passage.
public struct TracksWindow: ViewModifier {
    let window: StadiumPassage.Window
    @Environment(StadiumPassage.self) private var passage

    @Environment(\.dismissWindow) private var dismissWindow

    public func body(content: Content) -> some View {
        content
            .onAppear {
                passage.appeared(window)
                // A window that opened inside the stadium closes itself and
                // comes back on the way out.
                if passage.appearedInside(window), window.value == nil { dismissWindow(id: window.id) }
            }
            .onDisappear { passage.disappeared(window) }
    }
}

extension View {
    public func tracksWindow(_ w: StadiumPassage.Window) -> some View { modifier(TracksWindow(window: w)) }
}
