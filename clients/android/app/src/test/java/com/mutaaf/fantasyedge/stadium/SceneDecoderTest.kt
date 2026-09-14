package com.mutaaf.fantasyedge.stadium

import com.mutaaf.fantasyedge.stadium.scene.SceneDecoder
import com.mutaaf.fantasyedge.stadium.scene.UnsupportedSceneException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class SceneDecoderTest {

    private fun raw(name: String): JsonObject = Json.parseToJsonElement(Fixtures.text(name)).jsonObject

    private fun withField(name: String, key: String, value: kotlinx.serialization.json.JsonElement): String =
        JsonObject(raw(name) + (key to value)).toString()

    @Test
    fun everyRecordedSceneDecodes() {
        assertTrue("expected the recorded set, got ${Fixtures.names.size}", Fixtures.names.size >= 10)
        for (name in Fixtures.names) {
            val spec = Fixtures.scene(name)
            assertEquals("football-scene", spec.kind)
            assertEquals("replay", spec.source)
            assertTrue(spec.palette.isNotEmpty())
        }
    }

    @Test
    fun arcCountsMatchWhatTheApiSent() {
        for (name in Fixtures.names) {
            val sent = raw(name)["drives"]!!.jsonArray.sumOf { it.jsonObject["arcs"]!!.jsonArray.size }
            val decoded = Fixtures.scene(name).drives.sumOf { it.arcs.size }
            assertEquals("arcs in $name", sent, decoded)
        }
    }

    @Test
    fun thePickSixIsACelebratingHomeTouchdown() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val moment = assertNotNull(spec.activeMoment).let { spec.activeMoment!! }
        assertEquals("touchdown", moment.kind)
        assertEquals("home", moment.side)
        assertEquals("CHI", moment.team)
        assertTrue(moment.celebrates)
        assertEquals("home", spec.bowl.sectionTint.side)
        assertEquals(spec.teams.home.chip, spec.bowl.sectionTint.color)
        // While a moment holds, the shown drive is the one it happened in.
        val shown = spec.shownDrive!!
        assertTrue(shown.arcs.any { it.id == moment.playId })
        assertEquals("beacon.score", spec.ball!!.beacon.color)
    }

    @Test
    fun aKickoffSceneHasNoDriveAndNoBall() {
        val spec = Fixtures.scene(Fixtures.KICKOFF)
        assertNull(spec.activeMoment)
        assertTrue(spec.drives.flatMap { it.arcs }.size <= 1)
    }

    @Test
    fun aMinorVersionWithNewFieldsStillDecodes() {
        val text = JsonObject(
            raw(Fixtures.PICK_SIX) + mapOf(
                "version" to JsonPrimitive("1.7"),
                "crowdAudio" to JsonObject(mapOf("section" to JsonPrimitive("home"))),
                "stadiumName" to JsonPrimitive("Soldier Field"),
            )
        ).toString()
        val spec = SceneDecoder.decode(text)
        assertEquals("1.7", spec.version)
        assertEquals("CHI", spec.teams.home.abbr)
    }

    @Test
    fun unknownFieldsInsideNestedPrimitivesAreIgnored() {
        val o = raw(Fixtures.PICK_SIX)
        val drives = o["drives"]!!.jsonArray.map { d ->
            val arcs = d.jsonObject["arcs"]!!.jsonArray.map { a -> JsonObject(a.jsonObject + ("spin" to JsonPrimitive(12))) }
            JsonObject(d.jsonObject + ("arcs" to JsonArray(arcs)))
        }
        val spec = SceneDecoder.decode(JsonObject(o + ("drives" to JsonArray(drives))).toString())
        assertEquals(Fixtures.scene(Fixtures.PICK_SIX).drives, spec.drives)
    }

    @Test
    fun aMajorVersionIsRefusedWithASentence() {
        try {
            SceneDecoder.decode(withField(Fixtures.PICK_SIX, "version", JsonPrimitive("2.0")))
            fail("a 2.x scene must not be drawn with 1.x rules")
        } catch (e: UnsupportedSceneException) {
            assertTrue(e.message!!, e.message!!.contains("2.0"))
            assertTrue(e.message!!, e.message!!.contains("1.x"))
        }
    }

    @Test
    fun aMissingOrGarbledVersionIsRefused() {
        val o = raw(Fixtures.PICK_SIX)
        for (bad in listOf(JsonObject(o - "version").toString(), withField(Fixtures.PICK_SIX, "version", JsonPrimitive("latest")))) {
            try {
                SceneDecoder.decode(bad)
                fail("refuse a scene whose version cannot be read")
            } catch (e: UnsupportedSceneException) {
                assertFalse(e.message.isNullOrBlank())
            }
        }
    }

    @Test
    fun somethingThatIsNotASceneIsRefused() {
        try {
            SceneDecoder.decode(withField(Fixtures.PICK_SIX, "kind", JsonPrimitive("board")))
            fail()
        } catch (e: UnsupportedSceneException) {
            assertTrue(e.message!!.contains("board"))
        }
        try {
            SceneDecoder.decode("<html>502</html>")
            fail()
        } catch (e: UnsupportedSceneException) {
            assertTrue(e.message!!.isNotBlank())
        }
    }

    @Test
    fun theReplayRemoteDecodes() {
        val state = SceneDecoder.decodeReplay(Fixtures.replayState())
        assertTrue(state.loaded)
        assertEquals("401772810", state.event)
        assertEquals(1929, state.gameSeconds)
        assertEquals(60.0, state.speed, 0.0)
        assertTrue(state.speeds.contains(60.0))
        assertEquals(3, state.games!!.size)
        assertTrue(state.games!!.any { it.final == "Final/OT" })
        assertEquals("MIN", state.matchup!!.away.abbr)
    }

    @Test
    fun replayControlRidesAlongOnAReplayScene() {
        val spec = Fixtures.scene(Fixtures.PICK_SIX)
        val control = spec.replayControl!!
        assertEquals("401772810", control.event)
        assertNotNull(control.driveStart)
        assertTrue(raw(Fixtures.PICK_SIX)["replayControl"]!!.jsonObject["speed"]!!.jsonPrimitive.content.toDouble() > 0)
    }
}
