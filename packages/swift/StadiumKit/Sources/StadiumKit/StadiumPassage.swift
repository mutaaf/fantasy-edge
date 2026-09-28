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
/// own appearance and disappearance, and the passage counts them. `enter`
/// writes the list down before it closes anything, so the disappearances it
/// causes are recorded like any other.
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

    /// Whether the space has said, itself, that it is on screen. `inStadium`
    /// is a belief written down when `openImmersiveSpace` answered; this is
    /// evidence, reported by the space through `.tracksSpace()`. The two are
    /// kept apart on purpose - see `enter` and `watch`.
    public private(set) var onScreen = false

    /// Why the last walk into the stadium did not happen, for the caller to
    /// show. `enter` used to return silently on a refusal, so a tap with the
    /// board's room already open played the gate, dimmed the table and did
    /// nothing else - indistinguishable from a bug.
    public private(set) var refusal: String?

    /// How long the table needs to be up before the space can read the game
    /// off it. The walk-in hooks each had their own sleep; this is the one.
    public static let doorSeconds: Double = 3

    /// How often the open space says it is still there, how long a silence has
    /// to run before the passage stops believing it, and how many checks in a
    /// row have to agree. Not design numbers: a beat cheap enough to be free,
    /// and a silence long enough - and confirmed often enough - that a main
    /// actor blocked building a stadium cannot fake one. Bringing the windows
    /// back into a stadium that is still standing is the one mistake this must
    /// not make, so it is slow to conclude and quick to be talked out of it.
    public static let beatSeconds: Double = 1.5
    public static let silenceSeconds: Double = 8
    public static let strikes = 2

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
    /// How many live instances of each window have said they appeared and not
    /// yet that they went. A count, not a set: on a quick way out the passage
    /// reopens the board before the old board's `onDisappear` has arrived, and
    /// with a set that late disappearance erased the new board. The passage
    /// then believed nothing was open, so the next walk in left the board
    /// standing in the stands and the way out never brought it back
    /// (tools/stadium_soak.py, with the API down so the stadium comes up fast).
    @ObservationIgnored private var presence: [Window: Int] = [:]
    @ObservationIgnored private var leaving = false
    /// A walk in is under way: `openImmersiveSpace` has been asked and has not
    /// answered. A second Enter in that window asked for a space already
    /// opening, got `.error`, and told the wearer to leave an immersive board
    /// that did not exist while the stadium came up behind the message.
    @ObservationIgnored private var entering = false
    /// The last time the open space said it was there, and the task that
    /// checks. Both are the passage's way home from a space that went without
    /// saying so; see `watch`.
    ///
    /// A suspending clock, not a wall clock: an app put to sleep with the
    /// stadium open comes back with every timer overdue, and on a wall clock
    /// that reads as a stadium that stopped answering hours ago. Time the app
    /// was not running is not time the space was silent.
    @ObservationIgnored private var lastBeat = SuspendingClock.Instant.now
    @ObservationIgnored private var watchdog: Task<Void, Never>?

    private var silence: Double {
        let d = lastBeat.duration(to: .now)
        return Double(d.components.seconds) + Double(d.components.attoseconds) * 1e-18
    }

    public func appeared(_ w: Window) {
        presence[w, default: 0] += 1
        open.insert(w)
    }

    /// Forget the last refusal, once the wearer has been told about it.
    public func clearRefusal() { refusal = nil }

    /// A window that opens while the stadium is up belongs behind it, not in
    /// the stands. Under load the tabletop the launch opened could finish
    /// appearing after `enter` had already written down what to close, and it
    /// sat in the middle of the bowl, win-probability labels and all. Returns
    /// true when the window should close itself; it comes back on the way out.
    public func appearedInside(_ w: Window) -> Bool {
        guard inStadium else { return false }
        // It closes itself, and its own disappearance takes it off the count.
        saved.insert(w)
        log.info("a window appeared inside the stadium; closing it until the way out")
        return true
    }

    public func disappeared(_ w: Window) {
        guard let n = presence[w] else { return }
        if n > 1 {
            presence[w] = n - 1
        } else {
            presence[w] = nil
            open.remove(w)
        }
    }

    public func renamed(from old: Window, to new: Window) {
        let n = presence.removeValue(forKey: old) ?? 1
        open.remove(old)
        presence[new, default: 0] += n
        open.insert(new)
    }

    /// Open the stadium and put every other window of this app away.
    ///
    /// Tabletops are closed before the board because the stadium is often
    /// entered from the board's own launch task, and closing the board ends
    /// that task; whatever comes after it would never run.
    ///
    /// `openWindow` is not used on the way in. It is the way back: the space
    /// can be opened and then never come up, and every window is already
    /// closed by then, so the passage has to be able to put them back on its
    /// own. See `watch`.
    public func enter(openSpace: OpenImmersiveSpaceAction, dismissWindow: DismissWindowAction,
                      openWindow: OpenWindowAction,
                      before: () -> Void = {}) async {
        guard !entering else { log.info("enter ignored: already on the way in"); return }
        entering = true
        defer { entering = false }
        // `inStadium` is bookkeeping, and bookkeeping desyncs: a space that
        // went away without `spaceDisappeared` running used to leave this true
        // for the rest of the process, and "Enter stadium" dead with it, with
        // nothing logged and nothing shown. So the belief is only trusted when
        // the space itself has said it is on screen; otherwise it is wrong,
        // loudly, and the walk goes ahead.
        if inStadium {
            guard !onScreen else { log.info("enter ignored: already in the stadium"); return }
            log.error("enter: the passage thought it was in the stadium, but the space never said it was on screen; walking in again")
            heal()
        }
        // The app's own business before the walk - which immersion style the
        // dial opens at, say - done while nothing has moved yet.
        before()
        let opened = open
        refusal = nil
        // Reset before asking, never after the answer: the space can come up
        // and say so while `openImmersiveSpace` is still suspended, and
        // clearing it on `.opened` erased that - every stadium then read as
        // never on screen, and the next Enter from inside "healed" the
        // passage out of it, leaving Leave ignored and the windows forgotten.
        onScreen = false
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
        lastBeat = .now
        log.info("entered stadium; closing \(opened.count) window(s)")
        for w in opened where w.value != nil {
            dismissWindow(id: w.id, value: w.value!)
            // A window visionOS restored on launch carries no value, so
            // dismissing by value misses it and it stayed in the middle of the
            // bowl. Dismiss by id as well.
            dismissWindow(id: w.id)
        }
        for w in opened where w.value == nil { dismissWindow(id: w.id) }
        watch(openWindow)
    }

    // MARK: - what the space itself says

    /// The space is on screen. Reported by `.tracksSpace()`.
    public func spaceAppeared() {
        lastBeat = .now
        guard !onScreen else { return }
        onScreen = true
        log.info("the stadium is on screen")
    }

    /// The space is still on screen. A beat rather than a one-off, because the
    /// only other thing that ever says the space has gone is an `onDisappear`,
    /// and an `onDisappear` that does not run is exactly the failure that left
    /// an app with every window closed and no way back.
    public func spaceAlive() { lastBeat = .now }

    /// Put the windows back if the space stops saying it is there. Two
    /// failures land here: a space that answered `.opened` and never came up,
    /// and a space that went away without its `onDisappear` running. Both used
    /// to leave the app with nothing on screen at all, permanently, and
    /// nothing written down about it.
    private func watch(_ openWindow: OpenWindowAction) {
        watchdog?.cancel()
        watchdog = Task { @MainActor [weak self] in
            var strikes = 0
            while let self, self.inStadium {
                do { try await Task.sleep(for: .seconds(Self.beatSeconds)) } catch { return }
                guard self.inStadium else { return }
                let quiet = self.silence
                guard quiet > Self.silenceSeconds else { strikes = 0; continue }
                strikes += 1
                log.error("the stadium has said nothing for \(quiet, format: .fixed(precision: 1))s (\(strikes) of \(Self.strikes))")
                guard strikes >= Self.strikes else { continue }
                log.error("the stadium is gone without having said so; putting the windows back")
                self.refusal = "The stadium closed on its own."
                self.onScreen = false
                self.restore(openWindow)
                return
            }
        }
    }

    // MARK: - the way out

    /// Bring back what was open, then close the space. Windows first: an app
    /// whose last scene closes is an app with nothing on screen.
    public func leave(openWindow: OpenWindowAction, dismissSpace: DismissImmersiveSpaceAction) async {
        guard inStadium else { log.info("leave ignored: not in stadium"); return }
        leaving = true
        // Whatever happens to the dismiss below, `leaving` comes back down. It
        // gates `spaceDisappeared`, so a `leaving` left standing by a dismiss
        // that never returned would silently swallow the next Crown press and
        // the windows would not come back.
        defer { leaving = false }
        restore(openWindow)
        log.info("windows reopened; dismissing stadium")
        await dismissSpace()
        log.info("stadium dismissed")
    }

    /// The space went away without `leave` - the Digital Crown press, or the
    /// system closing it. The windows still have to come back.
    public func spaceDisappeared(openWindow: OpenWindowAction) {
        onScreen = false
        guard inStadium else { log.info("the stadium went, and the passage was not in it; nothing to restore"); return }
        guard !leaving else { return }
        log.info("the stadium went without a Leave; restoring what was open")
        restore(openWindow)
    }

    /// Drop a belief the evidence contradicts, without touching the windows:
    /// they were never closed, or they are already back.
    private func heal() {
        watchdog?.cancel()
        watchdog = nil
        saved = []
        inStadium = false
        onScreen = false
    }

    private func restore(_ openWindow: OpenWindowAction) {
        watchdog?.cancel()
        watchdog = nil
        let back = saved
        saved = []
        inStadium = false
        // Launched straight into the stadium with nothing behind it: the front
        // door is what comes back.
        if back.isEmpty {
            log.info("nothing was open behind the stadium; reopening the front door")
            openWindow(id: frontDoor.id)
            return
        }
        log.info("reopening \(back.count) window(s)")
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

/// Reports the immersive space's presence to the passage: that it came up,
/// that it is still here, and that it went.
///
/// The beat is the point. An `onDisappear` is the only other thing that ever
/// says the stadium has gone, and an `onDisappear` that does not run left
/// `inStadium` true for the life of the process - every window closed, the
/// Enter button dead, and nothing written down. A space that stops saying it
/// is there is a space that has gone, whatever the bookkeeping believes.
public struct TracksSpace: ViewModifier {
    @Environment(StadiumPassage.self) private var passage
    @Environment(\.openWindow) private var openWindow

    public init() {}

    public func body(content: Content) -> some View {
        content
            .onAppear { passage.spaceAppeared() }
            .task {
                // `try?` would spin here: a cancelled sleep returns at once and
                // the loop would run flat out for as long as the task took to
                // be torn down. Cancellation ends it.
                while !Task.isCancelled {
                    passage.spaceAlive()
                    do { try await Task.sleep(for: .seconds(StadiumPassage.beatSeconds)) } catch { return }
                }
            }
            .onDisappear { passage.spaceDisappeared(openWindow: openWindow) }
    }
}

extension View {
    public func tracksWindow(_ w: StadiumPassage.Window) -> some View { modifier(TracksWindow(window: w)) }

    /// The immersive space's side of `tracksWindow`. Every space the passage
    /// opens wears this; without it the passage has only its own belief.
    public func tracksSpace() -> some View { modifier(TracksSpace()) }
}
