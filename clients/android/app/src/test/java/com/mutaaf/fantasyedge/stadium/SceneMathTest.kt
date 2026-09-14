package com.mutaaf.fantasyedge.stadium

import com.mutaaf.fantasyedge.stadium.scene.PlayMotion
import com.mutaaf.fantasyedge.stadium.scene.SceneMath
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI

class SceneMathTest {
    private val eps = 1e-3f

    @Test
    fun everyArcPeaksAtTheApexTheSceneStates() {
        for (name in Fixtures.names) {
            for (arc in Fixtures.scene(name).drives.flatMap { it.arcs }) {
                val mid = SceneMath.point(arc, 0.5)
                assertEquals("apex of ${arc.id}", arc.apex.toFloat(), mid.y, eps)
                assertEquals(arc.lane.toFloat(), mid.z, eps)
                val start = SceneMath.point(arc, 0.0)
                val end = SceneMath.point(arc, 1.0)
                assertEquals((arc.fromX - 50).toFloat(), start.x, eps)
                assertEquals((arc.toX - 50).toFloat(), end.x, eps)
                assertEquals(0f, start.y, eps)
                assertEquals(0f, end.y, eps)
            }
        }
    }

    @Test
    fun pointsOutsideTheArcClampToItsEnds() {
        val arc = Fixtures.scene(Fixtures.PICK_SIX).drives.flatMap { it.arcs }.first()
        assertEquals(SceneMath.point(arc, 0.0), SceneMath.point(arc, -3.0))
        assertEquals(SceneMath.point(arc, 1.0), SceneMath.point(arc, 9.0))
    }

    @Test
    fun anIncompletePassIsDrawnInDashesAndACatchIsNot() {
        val arcs = Fixtures.names.flatMap { Fixtures.scene(it).drives.flatMap { d -> d.arcs } }
        val incomplete = arcs.first { it.style == "incomplete" }
        assertTrue(SceneMath.dashes(incomplete).size > 1)
        val solid = arcs.first { it.style == "pass" }
        assertEquals(1, SceneMath.dashes(solid).size)
    }

    @Test
    fun theBowlIsTheSpecsSuperellipse() {
        val shape = Fixtures.scene(Fixtures.PICK_SIX).bowl.shape
        val (x0, z0) = SceneMath.bowlPoint(shape, 6.0, 0.0)
        assertEquals(shape.halfLength + 6, x0, 1e-9)
        assertEquals(0.0, z0, 1e-9)
        val (x1, z1) = SceneMath.bowlPoint(shape, 6.0, PI / 2)
        assertEquals(0.0, x1, 1e-6)
        assertEquals(shape.halfWidth + 6, z1, 1e-9)
    }

    @Test
    fun tierHeightRunsFromFrontRiseToBackRise() {
        val tier = Fixtures.scene(Fixtures.PICK_SIX).bowl.tiers.first()
        assertEquals(tier.rise[0], SceneMath.tierHeight(tier, tier.inner), 1e-9)
        assertEquals(tier.rise[1], SceneMath.tierHeight(tier, tier.outer), 1e-9)
        assertEquals(tier.rise[1], SceneMath.tierHeight(tier, tier.outer + 50), 1e-9)
    }

    @Test
    fun theHorizonHasAPointPerProbabilityOnItsBand() {
        val spec = Fixtures.scene(Fixtures.OVERTIME)
        val pts = SceneMath.horizon(spec.winProbability)
        val h = spec.winProbability.horizon
        assertEquals(spec.winProbability.series.size, pts.size)
        assertEquals((h.x0 - 50).toFloat(), pts.first().x, eps)
        assertEquals((h.x1 - 50).toFloat(), pts.last().x, eps)
        pts.forEach { assertTrue(it.y >= h.y0 - eps && it.y <= h.y1 + eps) }
    }

    @Test
    fun hexColoursDecode() {
        val c = SceneMath.rgba("#F7F6F2BD")
        assertEquals(0xF7 / 255f, c[0], eps)
        assertEquals(0xBD / 255f, c[3], eps)
        assertEquals(1f, SceneMath.rgba("#FFD400")[3], eps)
        assertEquals(0.5f, SceneMath.rgba("nope")[0], eps)
    }

    private fun drive(vararg ids: String) = SceneSpec.Drive(id = "d", arcs = ids.map {
        SceneSpec.Arc(id = it, style = "run", shape = "run", fromX = 20.0, toX = 25.0, color = "arc.run", duration = 1.0)
    })

    @Test
    fun theFirstSceneIsHistoryAndLaterPlaysQueue() {
        val motion = PlayMotion()
        assertTrue(motion.arrive(drive("a", "b"), initial = true).isEmpty())
        assertTrue(motion.queue.isEmpty())
        val fresh = motion.arrive(drive("a", "b", "c"), initial = false)
        assertEquals(listOf("c"), fresh.map { it.id })
        val (arc, seconds) = motion.next(reduceMotion = false, floor = 0.2)!!
        assertEquals("c", arc.id)
        assertEquals(1.0, seconds, 1e-9)
        assertNull(motion.next(false, 0.2))
    }

    @Test
    fun aBacklogIsSqueezedAndReduceMotionLandsTheBall() {
        val motion = PlayMotion()
        motion.arrive(drive(), initial = true)
        motion.arrive(drive("1", "2", "3", "4", "5"), initial = false)
        assertEquals(0.5, motion.next(false, 0.2)!!.second, 1e-9)
        val landed = motion.next(reduceMotion = true, floor = 0.2)!!
        assertEquals(0.0, landed.second, 1e-9)
    }
}
