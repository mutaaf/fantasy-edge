import Observation
import OSLog
import SwiftUI

private let log = Logger(subsystem: "com.mutaaf.fantasyedge", category: "stadium")

/// The walk into the stadium and back out again.
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
@MainActor
@Observable
final class StadiumPassage {
    enum Window: Hashable {
        case board
        case tabletop(String)
    }

    private(set) var open: Set<Window> = []
    private(set) var inStadium = false

    @ObservationIgnored private var saved: Set<Window> = []
    @ObservationIgnored private var moving = false
    @ObservationIgnored private var leaving = false

    func appeared(_ w: Window) { open.insert(w) }

    func disappeared(_ w: Window) {
        guard !moving else { return }
        open.remove(w)
    }

    func renamed(from old: Window, to new: Window) {
        open.remove(old)
        open.insert(new)
    }

    /// Open the stadium and put every other window of this app away.
    ///
    /// Tabletops are closed before the board because the stadium is often
    /// entered from the board's own launch task, and closing the board ends
    /// that task; whatever comes after it would never run.
    func enter(style: RoomStyle, board: Board,
               openSpace: OpenImmersiveSpaceAction, dismissWindow: DismissWindowAction) async {
        guard !inStadium else { return }
        board.stadiumStyle = style
        let before = open
        switch await openSpace(id: "stadium") {
        case .opened:
            break
        default:
            // Another space is open (the board's room) or the system refused.
            // Nothing was closed, so nothing needs restoring.
            return
        }
        saved = before
        inStadium = true
        moving = true
        log.info("entered stadium; closing \(before.count) window(s)")
        for case .tabletop(let value) in before { dismissWindow(id: "tabletop", value: value) }
        if before.contains(.board) { dismissWindow(id: "board") }
        moving = false
    }

    /// Bring back what was open, then close the space. Windows first: an app
    /// whose last scene closes is an app with nothing on screen.
    func leave(openWindow: OpenWindowAction, dismissSpace: DismissImmersiveSpaceAction) async {
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
    func spaceDisappeared(openWindow: OpenWindowAction) {
        guard inStadium, !leaving else { return }
        restore(openWindow)
    }

    private func restore(_ openWindow: OpenWindowAction) {
        let back = saved
        saved = []
        inStadium = false
        // Launched straight into the stadium with nothing behind it: the board
        // is the app's front door, so that is what comes back.
        if back.isEmpty { openWindow(id: "board"); return }
        if back.contains(.board) { openWindow(id: "board") }
        for case .tabletop(let value) in back { openWindow(id: "tabletop", value: value) }
    }
}

/// Reports a window's presence to the passage.
struct TracksWindow: ViewModifier {
    let window: StadiumPassage.Window
    @Environment(StadiumPassage.self) private var passage

    func body(content: Content) -> some View {
        content
            .onAppear { passage.appeared(window) }
            .onDisappear { passage.disappeared(window) }
    }
}

extension View {
    func tracksWindow(_ w: StadiumPassage.Window) -> some View { modifier(TracksWindow(window: w)) }
}
