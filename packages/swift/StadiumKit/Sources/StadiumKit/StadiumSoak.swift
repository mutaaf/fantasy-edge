import SwiftUI

/// Open and close every stadium, over and over, through the same passage a
/// tap goes through, and say whether anything stuck.
///
/// `tests/test_teardown.py` pins the *shape* of every teardown fix, because
/// the suite cannot run a visionOS view. This is the other half: the fixes,
/// exercised. A simulator cannot pinch, so the walk is driven from here.
///
///     -stadiumSoak <cycles>
///
/// Each cycle puts a game on the table and takes it off, puts it back, walks
/// into the stadium, waits for the space itself to say it is on screen, walks
/// out, and checks the windows came back and the passage believes what is
/// true. Every third cycle is rude on purpose: it leaves before the stadium has
/// come up, and presses Enter twice. The physical footprint is read with the
/// table up, in the stadium, and after everything has closed; a stadium that
/// is not given back shows as a closed footprint that climbs.
///
/// Every line is `[stadium-soak]`; `tools/stadium_soak.py` reads them.
@MainActor
public enum StadiumSoak {
    /// The cycle count from `-stadiumSoak`, or nil when not soaking.
    public static var cycles: Int? {
        #if DEBUG
        return StadiumShots.argument("-stadiumSoak").flatMap(Int.init)
        #else
        return nil
        #endif
    }

    /// Once per process: leaving reopens the front door, a fresh window whose
    /// launch hook would otherwise start a second soak inside the first.
    private static var started = false

    /// Run the soak. `table` is the tabletop window for one game; `before` is
    /// the app's own business ahead of each walk in, as for `enter`.
    public static func run(cycles: Int, passage: StadiumPassage, table: StadiumWindow,
                           openWindow: OpenWindowAction, dismissWindow: DismissWindowAction,
                           openSpace: OpenImmersiveSpaceAction,
                           dismissSpace: DismissImmersiveSpaceAction,
                           before: @escaping () -> Void = {}) async {
        guard !started else { return }
        started = true
        var failures = 0
        var closed: [Double] = []
        func say(_ line: String) {
            StadiumLog.log.notice("[stadium-soak] \(line, privacy: .public)")
        }
        func fail(_ cycle: Int, _ what: String) {
            failures += 1
            say("FAIL cycle \(cycle): \(what)")
        }
        func megabytes() -> Double {
            Double(StadiumDeviceStats.footprintBytes() ?? 0) / 1_048_576
        }
        /// Poll until `done` holds or `seconds` pass. The passage's own
        /// watchdog is slow on purpose (two strikes of eight seconds), so the
        /// limits here are generous: a slow stadium is not a stuck one.
        func until(_ seconds: Double, _ done: () -> Bool) async -> Bool {
            let end = ContinuousClock.now + .seconds(seconds)
            while ContinuousClock.now < end {
                if done() { return true }
                try? await Task.sleep(for: .milliseconds(250))
            }
            return done()
        }
        func openTable() { openWindow(id: table.id, value: table.value ?? "") }
        func closeTable() {
            dismissWindow(id: table.id, value: table.value ?? "")
            dismissWindow(id: table.id)
        }
        func enter() async {
            await passage.enter(openSpace: openSpace, dismissWindow: dismissWindow,
                                openWindow: openWindow, before: before)
        }

        // What is open at rest - the front door. Every cycle must end with the
        // passage believing exactly this again: a window it has lost track of
        // is a window the next walk in leaves standing in the stands.
        let resting = passage.open
        say("start: \(cycles) cycles, footprint \(String(format: "%.0f", megabytes())) MB")
        for cycle in 1...cycles {
            let rude = cycle % 3 == 0

            // The table, on and off.
            openTable()
            if !(await until(20) { passage.open.contains(table) }) { fail(cycle, "the table never appeared") }
            try? await Task.sleep(for: .seconds(StadiumPassage.doorSeconds))
            let tableMB = megabytes()
            closeTable()
            if !(await until(10) { !passage.open.contains(table) }) { fail(cycle, "the table did not close") }

            // The table again, and the walk in.
            openTable()
            _ = await until(20) { passage.open.contains(table) }
            try? await Task.sleep(for: .seconds(StadiumPassage.doorSeconds))
            if rude {
                // Enter twice at once: the second must be ignored, not wedge.
                let first = Task { @MainActor in await enter() }
                let second = Task { @MainActor in await enter() }
                await first.value
                await second.value
            } else {
                await enter()
            }
            if let refusal = passage.refusal { fail(cycle, "enter refused: \(refusal)") }
            if !passage.inStadium { fail(cycle, "enter returned but the passage is not in the stadium") }

            if rude {
                // Leave before the stadium has said it is on screen.
                await passage.leave(openWindow: openWindow, dismissSpace: dismissSpace)
            } else {
                if !(await until(45) { passage.onScreen }) { fail(cycle, "the stadium never came on screen") }
                try? await Task.sleep(for: .seconds(5))
            }
            let stadiumMB = megabytes()
            if !rude { await passage.leave(openWindow: openWindow, dismissSpace: dismissSpace) }

            // Out again: the passage must not believe it is still inside, and
            // what was open must be back.
            if !(await until(20) { !passage.inStadium && !passage.onScreen }) {
                fail(cycle, "the passage still thinks it is in the stadium (inStadium \(passage.inStadium), onScreen \(passage.onScreen))")
            }
            if !(await until(20) { passage.open.contains(table) }) { fail(cycle, "the table did not come back after leaving") }
            closeTable()
            _ = await until(10) { !passage.open.contains(table) }
            // Give RealityKit a moment to let go before reading what is held.
            try? await Task.sleep(for: .seconds(4))
            let closedMB = megabytes()
            if passage.open != resting {
                let names = { (w: Set<StadiumWindow>) in w.map { $0.value.map { "\($0)" } ?? $0.id }.sorted().joined(separator: ", ") }
                fail(cycle, "the passage lost track of a window: believes [\(names(passage.open))], at rest it was [\(names(resting))]")
            }
            closed.append(closedMB)
            say(String(format: "cycle %d%@: table %.0f MB, stadium %.0f MB, closed %.0f MB, open windows %d",
                       cycle, rude ? " (rude)" : "", tableMB, stadiumMB, closedMB, passage.open.count))
        }

        // Growth is judged from the second cycle: the first pays for caches
        // (fonts, shaders, the dress cache) that are meant to stay.
        let base = closed.count > 1 ? closed[1] : (closed.first ?? 0)
        let growth = closed.count > 2 ? (closed.last! - base) / Double(closed.count - 2) : 0
        say(String(format: "done: %d cycles, %d failures, closed footprint %.0f -> %.0f MB, %.1f MB per cycle",
                   cycles, failures, closed.first ?? 0, closed.last ?? 0, growth))
    }
}
