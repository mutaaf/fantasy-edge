"""Nothing the stadium opens may fail to close, and no control may go dead.

Every case here is a wedge that was really reachable: a flag that desynced
from the room it described and left a button disabled for the life of the
process, a completion handler nobody could guarantee would ever be called, a
`Task` that died with its view halfway through putting the state back, or a
retain cycle that kept a whole stadium standing behind a closed window.

They are source assertions rather than unit tests because the code under test
is visionOS SwiftUI, which this suite cannot run: `StadiumKit` is a
`.visionOS(.v2)` package and the wedges live in view lifecycles. So each test
pins the *shape* of the fix - the guard that heals instead of returning, the
timeout beside the callback, the weak capture, the `.task` that belongs to the
view - and says which bug comes back if it is removed.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "packages/swift/StadiumKit/Sources/StadiumKit"
PASSAGE = KIT / "StadiumPassage.swift"
VIEWS = KIT / "Actors/Experience/StadiumViews.swift"
UX = KIT / "Actors/Experience/ExperienceUX.swift"

# Every immersive space the passage opens, and the view that hosts it.
SPACE_HOSTS = [
    ROOT / "apple/FantasyEdge/Sources/StadiumHost.swift",
    ROOT / "apps/saturday/apple/Saturday/Sources/StadiumSpace.swift",
]

# Every place either app walks into the stadium.
WALK_INS = [
    ROOT / "apple/FantasyEdge/Sources/StadiumHost.swift",
    ROOT / "apps/saturday/apple/Saturday/Sources/StadiumVolume.swift",
    ROOT / "apps/saturday/apple/Saturday/Sources/SaturdayWall.swift",
    ROOT / "apps/saturday/apple/Saturday/Sources/GameDetailView.swift",
]


def body_of(src: str, signature: str) -> str:
    """The text of one Swift declaration, by brace depth from its signature.

    The opening brace is the first one outside the parameter list, not the
    first one after the signature: `before: () -> Void = {}` is a default
    argument, and taking it as the body returns an empty string that every
    assertion then fails against for the wrong reason.
    """
    start = src.index(signature)
    parens, open_brace = 0, None
    for i in range(start, len(src)):
        c = src[i]
        if c == "(":
            parens += 1
        elif c == ")":
            parens -= 1
        elif c == "{" and parens == 0:
            open_brace = i
            break
    assert open_brace is not None, f"{signature} has no body"
    depth = 0
    for i in range(open_brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace: i + 1]
    raise AssertionError(f"{signature} is never closed")


class Passage(unittest.TestCase):
    """The window and space bookkeeper: `StadiumPassage`."""

    @classmethod
    def setUpClass(cls):
        cls.src = PASSAGE.read_text()

    def test_being_in_the_stadium_is_evidence_and_not_only_a_belief(self):
        """`enter` used to be `guard !inStadium else { return }`. The moment
        `inStadium` desynced from the room - a space closed without
        `spaceDisappeared` running - the Enter button was dead for the rest of
        the process, silently. The flag is now checked against what the space
        itself reported, and a belief the evidence contradicts is dropped."""
        enter = body_of(self.src, "public func enter(")
        self.assertNotIn("guard !inStadium else { return }", enter,
                         "a bare guard on inStadium wedges Enter for the life of the process")
        self.assertIn("onScreen", enter, "enter trusts its own bookkeeping with nothing to check it against")
        self.assertIn("heal()", enter, "enter has no way to drop a belief the space contradicts")
        self.assertIn("log.error", enter, "the desync is healed silently")
        self.assertIn("public private(set) var onScreen", self.src,
                      "nothing records whether the space ever said it was on screen")

    def test_the_space_saying_it_is_on_screen_is_not_erased_by_the_answer(self):
        """The space comes up, and says so, while `openImmersiveSpace` is still
        suspended. `enter` cleared `onScreen` on `.opened`, after that report,
        so every stadium read as never on screen (tools/stadium_soak.py, every
        cycle) and the next Enter from inside healed the passage out of a
        stadium it was standing in: Leave ignored, the windows forgotten."""
        enter = body_of(self.src, "public func enter(")
        after = enter.split("case .opened:", 1)[1]
        self.assertNotIn("onScreen = false", after, "the answer erases what the space already said")
        before = enter.split("await openSpace(", 1)[0]
        self.assertIn("onScreen = false", before, "a stale report from the last visit is trusted")

    def test_a_second_enter_on_the_way_in_is_ignored_not_refused(self):
        """Two Enters before the first is answered opened the space twice; the
        second got `.error` and showed "Leave the immersive board" while the
        stadium came up behind it."""
        enter = body_of(self.src, "public func enter(")
        head = enter.split("await openSpace(", 1)[0]
        self.assertIn("guard !entering else", head, "a second Enter asks for a space already opening")
        self.assertIn("defer { entering = false }", head, "a thrown or early return leaves Enter dead")

    def test_a_late_goodbye_from_an_old_window_does_not_erase_the_new_one(self):
        """On a quick way out the board is reopened before the old board's
        `onDisappear` arrives. Tracked as a set by id, that late disappearance
        removed the new board, and the passage believed nothing was open: the
        next walk in left the board in the stands and the way out never
        brought it back. Windows are counted, and nothing skips a count."""
        self.assertIn("presence: [Window: Int]", self.src, "windows are a set, so an old goodbye erases a new window")
        gone = body_of(self.src, "public func disappeared(")
        self.assertIn("presence[w]", gone)
        self.assertNotIn("guard !moving", gone, "a skipped disappearance leaves the count wrong for good")

    def test_a_space_that_goes_without_saying_so_still_brings_the_windows_back(self):
        """`enter` closes every window. If the space then never comes up, or
        goes away without its `onDisappear` running, the app is left with
        nothing on screen at all and no way back. The passage watches for the
        space's own beat and restores what it closed when the beat stops."""
        self.assertIn("private func watch(", self.src, "there is no watchdog on an opened space")
        watch = body_of(self.src, "private func watch(")
        self.assertIn("restore(openWindow)", watch, "the watchdog cannot put the windows back")
        self.assertIn("log.error", watch, "the watchdog heals in silence")
        self.assertIn("refusal", watch, "the wearer is never told the stadium went on its own")
        enter = body_of(self.src, "public func enter(")
        self.assertIn("watch(openWindow)", enter, "enter closes the windows without arming the way back")
        # The watchdog has to be able to reopen windows, so `enter` is given
        # the action. It is required, not defaulted: a caller that forgot it
        # would be a caller with no way home, and every walk-in is updated
        # together rather than one of them quietly keeping the old behaviour.
        signature = self.src[self.src.index("public func enter("):].split(") async", 1)[0]
        self.assertIn("openWindow: OpenWindowAction", signature)
        self.assertNotIn("openWindow: OpenWindowAction? = nil", signature)
        for path in WALK_INS:
            with self.subTest(walk_in=path.name):
                src = path.read_text()
                for call in re.finditer(r"passage\.enter\(", src):
                    window = src[call.start(): call.start() + 300]
                    self.assertIn("openWindow:", window.split(")")[0] + window,
                                  f"{path.name} walks in with no way back")

    def test_the_watchdog_is_slow_to_conclude_the_stadium_has_gone(self):
        """Bringing the windows back into a stadium that is still standing is
        the one mistake this must not make: they would hang in the stands. A
        main actor blocked building a bowl can delay a beat, so the silence
        has to be long and confirmed more than once."""
        beat = float(re.search(r"beatSeconds: Double = ([\d.]+)", self.src).group(1))
        silence = float(re.search(r"silenceSeconds: Double = ([\d.]+)", self.src).group(1))
        strikes = int(re.search(r"strikes = (\d+)", self.src).group(1))
        self.assertGreaterEqual(silence, 4 * beat, "one slow frame could be read as a closed stadium")
        self.assertGreaterEqual(strikes, 2, "a single silent check is enough to tear the windows back")
        self.assertGreaterEqual(silence + strikes * beat, 10,
                                "the watchdog concludes too fast to survive a stadium build")

    def test_the_beat_stops_rather_than_spinning_when_it_is_cancelled(self):
        """`while !Task.isCancelled { try? await Task.sleep(...) }` runs flat
        out from the instant it is cancelled until it is torn down, because a
        cancelled sleep returns at once. Both loops here end on cancellation
        instead."""
        for name, loop in (("TracksSpace", body_of(self.src, "public struct TracksSpace")),
                           ("watch", body_of(self.src, "private func watch("))):
            with self.subTest(loop=name):
                self.assertNotIn("try? await Task.sleep", loop,
                                 "a cancelled sleep returns at once; this loop would spin")
                self.assertIn("catch { return }", loop)

    def test_leave_always_puts_the_leaving_flag_back_down(self):
        """`leaving` gates `spaceDisappeared`. Left standing by a dismiss that
        never returned it would swallow the next Crown press, and the windows
        would not come back."""
        leave = body_of(self.src, "public func leave(")
        self.assertIn("defer { leaving = false }", leave,
                      "a dismiss that never returns leaves `leaving` true for good")

    def test_every_way_out_of_the_stadium_says_what_it_did(self):
        """The besetting sin here is the silent return. Each of these three
        paths ends a visit, and each one logs."""
        for signature in ("public func leave(", "public func spaceDisappeared(",
                          "private func restore("):
            with self.subTest(path=signature):
                self.assertIn("log.", body_of(self.src, signature), f"{signature} can return without a word")

    def test_the_space_reports_itself_through_one_modifier(self):
        """`.tracksSpace()` is the space's side of `.tracksWindow(_:)`: it
        appeared, it is still here, it went. Every host wears it, so no app
        can be the one that forgot to tell the passage."""
        self.assertIn("public func tracksSpace()", self.src)
        tracks = body_of(self.src, "public struct TracksSpace")
        for call in ("passage.spaceAppeared()", "passage.spaceAlive()", "passage.spaceDisappeared("):
            self.assertIn(call, tracks)
        for host in SPACE_HOSTS:
            with self.subTest(host=host.name):
                src = host.read_text()
                self.assertIn(".tracksSpace()", src, f"{host.name} never tells the passage its space is up")
                self.assertNotIn("passage.spaceDisappeared(", src,
                                 f"{host.name} reports the way out by hand instead of through .tracksSpace()")


class TheWayIn(unittest.TestCase):
    """The tabletop's "Enter stadium" button, and the gate it plays first."""

    @classmethod
    def setUpClass(cls):
        cls.views = VIEWS.read_text()
        cls.ux = UX.read_text()

    def test_the_arrival_gate_cannot_orphan_its_completion(self):
        """`open(then:)` stores the completion and waits for `tick`, which is
        driven by a `SceneEvents.Update` subscription on the volume. If that
        subscription is not alive the completion never fires, "Enter stadium"
        stays disabled and nothing at all is logged. The gate now keeps its own
        clock and finishes on whichever arrives first."""
        gate = body_of(self.ux, "final class ArrivalGate")
        opened = body_of(gate, "func open(")
        self.assertIn("Task.sleep", opened, "the gate has no clock but the frame clock")
        self.assertIn("log.error", opened, "a gate that had to finish itself says nothing about it")
        self.assertIn("self.finish()", opened)
        # One shared exit, so the fallback and the tick cannot both call back.
        finish = body_of(gate, "private func finish()")
        self.assertIn("done = nil", finish)
        self.assertIn("fallback?.cancel()", finish)
        self.assertIn("fallback?.cancel()", body_of(gate, "func cancel()"),
                      "a cancelled gate leaves its own clock running")

    def test_the_enter_button_is_re_enabled_by_the_view_and_not_by_a_loose_task(self):
        """`entering` disables Enter and used to be cleared inside a `Task`
        started in the gate's completion, after a sleep. That `Task` died with
        the volume, so a table torn down mid-sleep could come back with the
        button disabled and no way to press it. It is a `.task(id:)` now, which
        belongs to the view: it restarts whenever the view appears, and it
        cannot outlive or be outlived by the flag it clears."""
        tabletop = body_of(self.views, "public struct TabletopView")
        arrive = body_of(tabletop, "private func arrive()")
        self.assertNotIn("Task {", arrive, "the regret timer is a loose Task again; it dies with the volume")
        self.assertIn("attempt &+= 1", arrive, "nothing restarts the view's own regret timer")
        self.assertIn(".task(id: attempt)", tabletop, "no view-owned timer gives the table back")
        regret = tabletop.split(".task(id: attempt)", 1)[1]
        for undo in ("entering = false", "gate.cancel()", "OpacityComponent.self"):
            self.assertIn(undo, regret.split("\n        }", 1)[0], f"the regret timer never does {undo}")

    def test_the_regret_timer_outlasts_the_gate_it_is_waiting_on(self):
        """It has to wait out the curtain, the gate's own fallback and the
        space's chance to take, or it would give the table back mid-walk."""
        grace = float(re.search(r"graceSeconds: Double = ([\d.]+)", self.ux).group(1))
        regret = float(re.search(r"regretSeconds: Double = ([\d.]+)", self.views).group(1))
        self.assertGreater(grace, 0)
        self.assertGreater(regret, 0)
        tabletop = body_of(self.views, "public struct TabletopView")
        self.assertIn("gateSeconds + ArrivalGate.graceSeconds + Self.regretSeconds", tabletop,
                      "the regret timer can fire before the gate it is waiting on has given up")

    def test_a_refused_walk_is_shown_and_not_only_logged(self):
        """`StadiumPassage.refusal` says why a walk did not happen. Written and
        never read it is still a button that did nothing: the tabletop shows
        it, beside the button that was refused, and clears it on the next try."""
        tabletop = body_of(self.views, "public struct TabletopView")
        self.assertIn("passage?.refusal", tabletop, "the refusal is never shown to anybody")
        self.assertIn("passage?.clearRefusal()", body_of(tabletop, "private func arrive()"),
                      "a refusal from a previous try is left standing over a fresh one")

    def test_every_path_out_of_arrive_says_which_one_it_took(self):
        """Three of the four ways through `arrive` are early returns, and all
        three used to be silent."""
        arrive = body_of(body_of(self.views, "public struct TabletopView"), "private func arrive()")
        self.assertEqual(arrive.count("return"), arrive.count("log."),
                         "a path through arrive() returns without saying so")
        self.assertGreaterEqual(arrive.count("log."), 3)

    def test_asking_for_an_immersive_space_is_never_answered_with_silence(self):
        """Every `openImmersiveSpace` in either app either logs its refusal or
        hands it to the passage, which does. A tap that opens nothing and says
        nothing is indistinguishable from a broken button."""
        rooms = list(WALK_INS) + [
            ROOT / "apple/FantasyEdge/Sources/CommandView.swift",
            ROOT / "apple/FantasyEdge/Sources/BoardView.swift",
        ]
        for path in rooms:
            src = path.read_text()
            for call in re.finditer(r"await open\w*Immersive\w*\(id:", src):
                window = src[call.start(): call.start() + 600]
                with self.subTest(file=path.name, at=src[:call.start()].count("\n") + 1):
                    self.assertTrue("log." in window or "case .error" in window,
                                    "an immersive space is opened without handling the refusal")
        # And the passage, which every other walk-in goes through.
        enter = body_of(PASSAGE.read_text(), "public func enter(")
        for outcome in ("case .userCancelled", "case .error", "@unknown default"):
            self.assertIn(outcome, enter)


class NothingOutlivesItsWindow(unittest.TestCase):
    """What a closed volume or a dismissed space has to let go of."""

    @classmethod
    def setUpClass(cls):
        cls.views = VIEWS.read_text()

    def test_a_frame_clock_never_holds_the_renderer_that_owns_it(self):
        """`renderer.subscription` is the renderer's, and its closure called
        straight into the renderer: renderer holds subscription holds closure
        holds renderer. Every walk in and out leaked a whole stadium - entity
        tree, textures, audio - behind a window nobody could see. The comment
        on `subscription` says the frame clock stops with the renderer; the
        weak capture is what makes that true."""
        for match in re.finditer(r"content\.subscribe\(to: SceneEvents\.Update\.self\) \{([^\n]*)", self.views):
            line = match.group(1)
            with self.subTest(at=self.views[:match.start()].count("\n") + 1):
                self.assertIn("[weak", line, "a frame-clock closure captures its target strongly")

    def test_both_frame_clocks_are_cancelled_when_their_view_goes(self):
        """A subscription left running ticks a renderer whose scene has gone."""
        for view in ("public struct TabletopView", "public struct StadiumSpaceView"):
            with self.subTest(view=view):
                body = body_of(self.views, view)
                gone = body.split(".onDisappear")[-1]
                self.assertIn("renderer.subscription?.cancel()", gone,
                              f"{view} leaves its frame clock running after it goes")
        tabletop = body_of(self.views, "public struct TabletopView")
        self.assertIn("gateClock?.cancel()", tabletop, "the gate's frame clock outlives the volume")

    def test_the_dock_lets_go_of_its_attachments(self):
        """`SeatPlacement` holds every dock attachment so a recentre can fade
        them. They are RealityKit entities from a scene that has been torn
        down; the stadium drops them on the way out."""
        gone = body_of(self.views, "public struct StadiumSpaceView").split(".onDisappear")[-1]
        self.assertIn("placer.entities.removeAll()", gone)


class NoFailureIsSwallowed(unittest.TestCase):
    """The rule the repo keeps re-learning: never a silent catch."""

    def test_world_tracking_says_when_it_could_not_start(self):
        """`HeadFacing.start()` swallowed every ARKit error whole. A recentre
        that quietly fell back to the seat's own forward was indistinguishable
        from one that worked."""
        start = body_of(body_of(UX.read_text(), "final class HeadFacing"), "func start()")
        self.assertIn("log.error", start, "ARKit's failure is swallowed again")
        self.assertIn("catch {", start)
        caught = start.split("catch {", 1)[1]
        self.assertLess(caught.index("log."), caught.index("}"), "the catch returns before it logs")


if __name__ == "__main__":
    unittest.main()
