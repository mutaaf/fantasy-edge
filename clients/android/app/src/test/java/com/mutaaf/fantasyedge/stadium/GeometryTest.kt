package com.mutaaf.fantasyedge.stadium

import com.mutaaf.fantasyedge.stadium.geometry.MeshData
import com.mutaaf.fantasyedge.stadium.geometry.Mode
import com.mutaaf.fantasyedge.stadium.geometry.Part
import com.mutaaf.fantasyedge.stadium.geometry.StadiumGeometry
import com.mutaaf.fantasyedge.stadium.geometry.Surface
import com.mutaaf.fantasyedge.stadium.scene.DesignTokens
import com.mutaaf.fantasyedge.stadium.scene.SceneMath
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class GeometryTest {

    private fun assertWellFormed(part: Part) {
        val m = part.mesh
        assertFalse("${part.name} is empty", m.isEmpty)
        assertEquals("${part.name} has a partial triangle", 0, m.indexCount % 3)
        val idx = m.indices
        assertTrue("${part.name} indexes past its vertices", idx.all { it in 0 until m.vertexCount })
        assertTrue("${part.name} has a non-finite position", m.positions.all { it.isFinite() })
    }

    @Test
    fun theStadiumBuildsEveryTierItsPresentationNames() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val stadium = StadiumGeometry.staticParts(spec, Mode.STADIUM)
        stadium.forEach(::assertWellFormed)
        val tiers = stadium.filter { it.name.startsWith("tier.") }.map { it.name.removePrefix("tier.") }
        assertEquals(spec.presentation.stadium.bowlTiers.sorted(), tiers.sorted())
        assertTrue(stadium.any { it.surface == Surface.SKY })
        assertTrue(stadium.any { it.name == "concourse" })
    }

    @Test
    fun theTabletopHasOnlyTheLowerBowlAndNoSky() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val table = StadiumGeometry.staticParts(spec, Mode.TABLETOP)
        table.forEach(::assertWellFormed)
        val tiers = table.filter { it.name.startsWith("tier.") }.map { it.name.removePrefix("tier.") }
        assertEquals(spec.presentation.tabletop.bowlTiers, tiers)
        assertFalse(table.any { it.surface == Surface.SKY })
        assertFalse(table.any { it.name == "concourse" })
    }

    @Test
    fun theCrowdIsExactlyTheCountItWasAskedFor() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        for (mode in Mode.values()) {
            val tiers = StadiumGeometry.tiersFor(spec, mode)
            val crowd = StadiumGeometry.crowd(spec, tiers, StadiumGeometry.Look.crowdCount(mode))
            val people = crowd.sumOf { it.mesh.vertexCount } / 4
            assertEquals(StadiumGeometry.Look.crowdCount(mode), people)
            // Sections are the two sidelines: what a touchdown lights.
            assertEquals(setOf("home", "away"), crowd.map { it.group.split(":")[1] }.toSet())
            assertTrue(crowd.any { it.group.endsWith(spec.bowl.crowd.home) })
        }
    }

    @Test
    fun theCrowdIsDeterministic() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val tiers = StadiumGeometry.tiersFor(spec, Mode.STADIUM)
        val a = StadiumGeometry.crowd(spec, tiers, 500).map { it.mesh.positions.toList() }
        val b = StadiumGeometry.crowd(spec, tiers, 500).map { it.mesh.positions.toList() }
        assertEquals(a, b)
    }

    @Test
    fun peopleSitOnTheTreadsTheSpecRises() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val tiers = StadiumGeometry.tiersFor(spec, Mode.STADIUM)
        val lo = tiers.minOf { it.rise[0] } - 1e-3
        val hi = tiers.maxOf { it.rise[1] } + 1.2
        for (part in StadiumGeometry.crowd(spec, tiers, 800)) {
            val p = part.mesh.positions
            for (i in 1 until p.size step 3) assertTrue("person at y=${p[i]}", p[i] >= lo && p[i] <= hi)
        }
    }

    @Test
    fun rimLightsStandOnlyOnTheFarSideAndCountFromTheSpec() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val lights = StadiumGeometry.rimLights(spec, Mode.STADIUM)
        assertTrue(lights.isNotEmpty())
        assertTrue(lights.size <= spec.bowl.rimLights.count)
        assertTrue(lights.all { it.position.z <= 12f })
        val outer = StadiumGeometry.tiersFor(spec, Mode.STADIUM).last()
        lights.forEach { assertEquals((outer.rise[1] + 9).toFloat(), it.position.y, 1e-3f) }
    }

    @Test
    fun theFieldHasAStripePerFiveYardsAndBothEndZonesInChipColours() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val field = StadiumGeometry.field(spec)
        assertWellFormed(field)
        val colors = field.mesh.colors
        fun hasColour(hex: String): Boolean {
            val c = SceneMath.linearRgba(hex)
            for (i in colors.indices step 4) {
                if (kotlin.math.abs(colors[i] - c[0]) < 1e-4 && kotlin.math.abs(colors[i + 1] - c[1]) < 1e-4 &&
                    kotlin.math.abs(colors[i + 2] - c[2]) < 1e-4) return true
            }
            return false
        }
        assertTrue(hasColour(spec.teams.home.chip))
        assertTrue(hasColour(spec.teams.away.chip))
        val b = field.mesh.bounds()
        assertEquals((-spec.field.endZone - 6 - 50).toFloat(), b[0], 1e-3f)
        assertEquals((spec.field.length + spec.field.endZone + 6 - 50).toFloat(), b[3], 1e-3f)
    }

    @Test
    fun anArcIsACoreAndAHaloAndAScoreIsThicker() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val arcs = spec.drives.flatMap { it.arcs }
        val score = arcs.first { it.style == "score" }
        val run = arcs.first { it.style == "run" }
        val scoreParts = StadiumGeometry.arc(score, spec, Mode.STADIUM)
        val runParts = StadiumGeometry.arc(run, spec, Mode.STADIUM)
        scoreParts.forEach(::assertWellFormed)
        assertEquals(listOf(Surface.GLOW, Surface.ADD), scoreParts.map { it.surface })
        fun thickness(p: Part): Float {
            val pos = p.mesh.positions
            // The first ring of a tube: its spread in z around the lane is twice the radius.
            val zs = (0 until 8).map { pos[it * 3 + 2] }
            return zs.max() - zs.min()
        }
        assertTrue(thickness(scoreParts[0]) > thickness(runParts[0]))
        // Tube vertices are rings of 8 along 24 samples, per dash piece.
        val pieces = SceneMath.dashes(run).size
        assertEquals(pieces * 48 * 8, runParts[0].mesh.vertexCount)
    }

    @Test
    fun lasersBeaconBallAndHorizonAreBuiltForEverySceneThatHasThem() {
        for (name in Fixtures.names) {
            val spec = Fixtures.scene(name)
            spec.lasers.forEach { l -> StadiumGeometry.laser(l, spec).forEach(::assertWellFormed) }
            spec.ball?.let { b -> StadiumGeometry.beacon(b, spec, Mode.STADIUM).forEach(::assertWellFormed) }
            val horizon = StadiumGeometry.horizon(spec, Mode.STADIUM)
            if (spec.winProbability.series.size > 1) {
                assertEquals(2, horizon.size)
                horizon.forEach(::assertWellFormed)
            } else {
                assertTrue(horizon.isEmpty())
            }
        }
        assertWellFormed(StadiumGeometry.ball(Mode.TABLETOP))
    }

    @Test
    fun meshDataGrowsPastItsInitialCapacity() {
        val m = MeshData()
        val tube = List(400) { com.mutaaf.fantasyedge.stadium.scene.Vec3(it.toFloat(), 0f, 0f) }
        StadiumGeometry.tube(m, tube, 1f, floatArrayOf(1f, 1f, 1f, 1f))
        assertEquals(400 * 8, m.vertexCount)
        assertEquals(399 * 8 * 6, m.indexCount)
    }

    @Test
    fun everyColourTokenTheScenesUseIsInDesignTokens() {
        val path = System.getProperty("designTokens") ?: "../../../design/tokens.json"
        val tokens = DesignTokens.parse(File(path).readText())
        for (name in Fixtures.names) {
            val spec = Fixtures.scene(name)
            val used = spec.drives.flatMap { d -> d.arcs.map { it.color } } + spec.lasers.map { it.color } +
                listOfNotNull(spec.ball?.beacon?.color) + spec.bowl.tiers.map { it.color } +
                listOf(spec.bowl.rimLights.color, spec.bowl.crowd.neutral, spec.bowl.crowd.dark)
            used.forEach { assertTrue("token $it missing from design/tokens.json", tokens.colors.containsKey(it)) }
            assertEquals(tokens.colors, spec.palette)
        }
        assertEquals(0.28, tokens.motion["sectionDim"]!!, 1e-9)
    }
}
