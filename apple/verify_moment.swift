// Sweeps MomentGate, the composer's rule for when a moment is allowed to
// happen: held until Broadcast has flown its play, released the frame it lands,
// and never stranded when nothing ever lands.
//
//   swiftc -parse-as-library -o /tmp/verify-moment \
//     apple/FantasyEdge/Sources/Stadium/MomentGate.swift apple/verify_moment.swift && /tmp/verify-moment
//
// Prints OK and exits 0, or the first failure and exits 1.

import Foundation

func check(_ what: String, _ ok: Bool) {
    VerifyMoment.checks += 1
    if !ok { VerifyMoment.failures.append(what) }
}

/// One touchdown, its play flying for `flight` seconds, stepped a frame at a
/// time. Returns the time the moment fired, or nil.
func firedAt(flight: Double, lands: Double?, grace: Double = 1.0,
             landedAtArrival: Bool = false, dt: Double = 1.0 / 90) -> Double? {
    var gate = MomentGate()
    var now = 0.0
    var landed = landedAtArrival
    if gate.arrive(playId: "p1", flightSeconds: flight, now: now, grace: grace, landed: landed) {
        return now
    }
    for _ in 0..<100_000 {
        now += dt
        if let lands, now >= lands { landed = true }
        if gate.due(now: now, landed: { _ in landed }) != nil { return now }
    }
    return nil
}

@main
struct VerifyMoment {
    nonisolated(unsafe) static var checks = 0
    nonisolated(unsafe) static var failures: [String] = []

    static func main() {
        // A play that flies: the moment waits for the landing, not for the deadline.
        if let t = firedAt(flight: 5.0, lands: 5.0) {
            check("fires when the ball lands, not on arrival", t >= 5.0 && t < 5.1)
        } else {
            check("fires when the ball lands", false)
        }

        // A fast replay lands the same play early; the moment follows the ball.
        if let t = firedAt(flight: 5.0, lands: 0.4) {
            check("a fast replay fires early with the ball", t >= 0.4 && t < 0.5)
        } else {
            check("a fast replay fires with the ball", false)
        }

        // Nothing ever lands: the deadline releases it, flight + grace.
        if let t = firedAt(flight: 5.0, lands: nil) {
            check("the deadline releases a moment nothing lands", t >= 6.0 && t < 6.1)
        } else {
            check("the deadline releases a moment nothing lands", false)
        }

        // A scene with no such play in the drive waits only the grace.
        if let t = firedAt(flight: 0, lands: nil) {
            check("no play in the drive waits only the grace", t >= 1.0 && t < 1.1)
        } else {
            check("no play in the drive waits only the grace", false)
        }

        // Already laid down - a drive set at rest, a seat change, reduce motion's jump.
        check("a play already landed fires at once", firedAt(flight: 5, lands: nil, landedAtArrival: true) == 0)

        // The same moment arriving every poll queues once and fires once.
        do {
            var gate = MomentGate()
            check("first arrival holds", !gate.arrive(playId: "p1", flightSeconds: 4, now: 0, grace: 1, landed: false))
            for i in 1...30 {
                let again = gate.arrive(playId: "p1", flightSeconds: 4, now: Double(i) * 0.1, grace: 1, landed: false)
                check("a re-announced moment never fires on arrival", !again)
            }
            var fires = 0
            var now = 0.0
            var landed = false
            for _ in 0..<1000 {
                now += 1.0 / 90
                if now >= 4.0 { landed = true }
                if gate.due(now: now, landed: { _ in landed }) != nil { fires += 1 }
            }
            check("a held moment fires exactly once", fires == 1)
        }

        // Scrubbing to another moment while one is held: the new one is held on its own
        // deadline, and the old one never fires.
        do {
            var gate = MomentGate()
            _ = gate.arrive(playId: "p1", flightSeconds: 5, now: 0, grace: 1, landed: false)
            check("p1 is held", gate.isHolding("p1"))
            _ = gate.arrive(playId: "p2", flightSeconds: 3, now: 1, grace: 1, landed: false)
            check("p2 replaces p1", gate.isHolding("p2") && !gate.isHolding("p1"))
            var fired: [String] = []
            var now = 1.0
            for _ in 0..<2000 {
                now += 1.0 / 90
                if let id = gate.due(now: now, landed: { $0 == "p2" && now >= 4.0 }) { fired.append(id) }
            }
            check("only the scrubbed-to moment fires", fired == ["p2"])
        }

        // Scrubbed off the moment entirely: nothing fires later.
        do {
            var gate = MomentGate()
            _ = gate.arrive(playId: "p1", flightSeconds: 5, now: 0, grace: 1, landed: false)
            gate.clear()
            var now = 0.0
            var fired = 0
            for _ in 0..<2000 {
                now += 1.0 / 90
                if gate.due(now: now, landed: { _ in true }) != nil { fired += 1 }
            }
            check("a cleared moment never fires", fired == 0)
            // ...and the same moment may arrive again afterwards, as a scrub back.
            check("a cleared moment can arrive again",
                  !gate.arrive(playId: "p1", flightSeconds: 5, now: 10, grace: 1, landed: false))
        }

        // A new game suppresses whatever the first scene carries.
        do {
            var gate = MomentGate()
            gate.suppress("p1")
            check("a suppressed moment does not fire on arrival",
                  !gate.arrive(playId: "p1", flightSeconds: 5, now: 0, grace: 1, landed: true))
            check("nothing is held after suppression", gate.held == nil)
            check("a later moment still works",
                  !gate.arrive(playId: "p2", flightSeconds: 5, now: 0, grace: 1, landed: false))
        }

        // Every kind uses the same rule: the gate is told a play id, never a kind.
        for flight in [0.6, 2.4, 4.3, 6.0, 7.6] {
            for speed in [1.0, 4.0, 20.0, 60.0] {
                let lands = flight / speed
                guard let t = firedAt(flight: flight, lands: lands) else {
                    check("fires at \(flight)s / \(speed)x", false); continue
                }
                check("fires with the ball at \(flight)s / \(speed)x", t >= lands && t < lands + 0.05)
                check("fires before the deadline at \(flight)s / \(speed)x", t < flight + 1.0)
            }
        }

        // Negative or missing numbers must not push a moment into the past or the
        // far future.
        do {
            var gate = MomentGate()
            _ = gate.arrive(playId: "p1", flightSeconds: -5, now: 3, grace: -2, landed: false)
            check("a negative flight cannot fire before now", (gate.held?.deadline ?? 0) >= 3)
        }

        // MARK: the drawn score, which lags the scene the same way

        // The first scene has nothing to lag behind: it is shown at once.
        do {
            var g = StatusGate<Int>()
            g.hold(7, playId: "p1", until: 99)
            check("the first status is shown at once", g.shown == 7 && !g.isHolding)
        }

        // A score arriving with a play in the air waits for it.
        do {
            var g = StatusGate<Int>()
            g.adopt(0)
            g.hold(7, playId: "p1", until: 6)
            var now = 0.0, shownWhen: Double?
            for _ in 0..<2000 {
                now += 1.0 / 90
                if g.due(now: now, landed: { _ in now >= 5.0 }) != nil { shownWhen = now; break }
            }
            check("the score waits for the ball", (shownWhen ?? 0) >= 5.0 && (shownWhen ?? 0) < 5.1)
            check("the board read the old score until then", g.shown == 7)
        }

        // Nothing lands: the deadline shows it anyway, so the board cannot freeze.
        do {
            var g = StatusGate<Int>()
            g.adopt(0)
            g.hold(7, playId: "p1", until: 6)
            var now = 0.0, shownWhen: Double?
            for _ in 0..<2000 {
                now += 1.0 / 90
                if g.due(now: now, landed: { _ in false }) != nil { shownWhen = now; break }
            }
            check("the deadline shows a score nothing lands", (shownWhen ?? 0) >= 6.0 && (shownWhen ?? 0) < 6.1)
        }

        // A scene with no new play - the clock ticking - is shown at once.
        do {
            var g = StatusGate<Int>()
            g.adopt(0)
            g.arrive(3)
            check("a scene with no new play is shown at once", g.shown == 3)
        }

        // While holding, later scenes replace what is waiting: the board catches up
        // to the newest, never to a state that has been passed.
        do {
            var g = StatusGate<Int>()
            g.adopt(0)
            g.hold(7, playId: "p1", until: 9)
            g.arrive(8)
            g.arrive(9)
            check("a held score is still the old one", g.shown == 0)
            var shown: [Int] = []
            var now = 0.0
            for _ in 0..<2000 {
                now += 1.0 / 90
                if let s = g.due(now: now, landed: { _ in now >= 4.0 }) { shown.append(s) }
            }
            check("only the newest status is shown, once", shown == [9])
        }

        // A scrub, a seat change, a new game: shown immediately, nothing left waiting.
        do {
            var g = StatusGate<Int>()
            g.adopt(0)
            g.hold(7, playId: "p1", until: 9)
            g.adopt(21)
            check("adopting shows at once", g.shown == 21 && !g.isHolding)
            var fired = 0
            var now = 0.0
            for _ in 0..<2000 {
                now += 1.0 / 90
                if g.due(now: now, landed: { _ in true }) != nil { fired += 1 }
            }
            check("nothing is shown after adopting", fired == 0)
        }

        // A play that changes nothing - an incompletion - costs no redraw.
        do {
            var g = StatusGate<Int>()
            g.adopt(7)
            g.hold(7, playId: "p1", until: 9)
            var fired = 0
            var now = 0.0
            for _ in 0..<2000 {
                now += 1.0 / 90
                if g.due(now: now, landed: { _ in true }) != nil { fired += 1 }
            }
            check("a status that did not change is not redrawn", fired == 0)
            check("and it is no longer waiting", !g.isHolding)
        }

        // The rule holds at every flight and replay speed: the score is shown with
        // the ball, never before it.
        for flight in [0.6, 2.4, 4.3, 6.0, 7.6] {
            for speed in [1.0, 4.0, 20.0, 60.0] {
                let lands = flight / speed
                var g = StatusGate<Int>()
                g.adopt(0)
                g.hold(7, playId: "p1", until: flight + 1.0)
                var now = 0.0, shownWhen: Double?
                for _ in 0..<20000 {
                    now += 1.0 / 90
                    if g.due(now: now, landed: { _ in now >= lands }) != nil { shownWhen = now; break }
                }
                check("the score is shown with the ball at \(flight)s / \(speed)x",
                      (shownWhen ?? 0) >= lands && (shownWhen ?? 0) < lands + 0.05)
            }
        }

        if failures.isEmpty {
            print("OK: \(checks) checks")
            exit(0)
        } else {
            for f in failures.prefix(10) { print("FAIL: \(f)") }
            print("\(failures.count) of \(checks) checks failed")
            exit(1)
        }

    }
}
