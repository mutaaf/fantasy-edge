package com.mutaaf.fantasyedge.stadium.scene

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

// The scene contract, as the API serves it from fantasyedge/scene.py.
//
// This mirrors apple/FantasyEdge/Sources/Stadium/SceneSpec.swift field for
// field. Nothing here decides football: where a pass peaks, which lane a play
// takes and when a section lights up all arrive decided. Android draws them.
//
// Coordinates are yards. x runs from the home goal line (0) to the away goal
// line (100), end zones -10..0 and 100..110; z is across the field, positive
// toward the home sideline; y is up.

@Serializable
data class SceneSpec(
    val version: String,
    val kind: String,
    val league: String = "nfl",
    val event: String = "",
    val source: String = "live",
    val speed: Double = 1.0,
    val field: Field,
    val teams: Teams,
    val status: Status,
    val ball: Ball? = null,
    val lasers: List<Laser> = emptyList(),
    val drives: List<Drive> = emptyList(),
    val currentDrive: Int? = null,
    val winProbability: WinProbability,
    val moments: List<Moment> = emptyList(),
    val activeMoment: Moment? = null,
    val bowl: Bowl,
    val presentation: Presentation,
    val palette: Map<String, String> = emptyMap(),
    val motion: Motion,
    val replayControl: ReplayState? = null,
) {
    val isReplay: Boolean get() = source == "replay"

    /** The drive a renderer draws: the one in progress, or the last once play stops. */
    val shownDrive: Drive?
        get() = currentDrive?.let { drives.getOrNull(it) } ?: drives.lastOrNull()

    fun color(token: String, fallback: String): String = palette[token] ?: fallback

    @Serializable
    data class Field(
        val length: Double,
        val endZone: Double,
        val width: Double,
        val hashFromSideline: Double,
        val goalPostWidth: Double = 6.167,
        val stripeEvery: Double = 5.0,
        val numbersEvery: Double = 10.0,
    )

    @Serializable
    data class Team(
        val abbr: String,
        val name: String = "",
        val id: String = "",
        val color: String = "",
        val chip: String,
        val chipText: String = "#FFFFFF",
        val hatch: Boolean = false,
        val score: Double = 0.0,
    )

    @Serializable
    data class Teams(val home: Team, val away: Team) {
        fun side(s: String?): Team? = when (s) {
            "home" -> home
            "away" -> away
            else -> null
        }
    }

    @Serializable
    data class Status(
        val state: String,
        val label: String = "",
        val clock: String = "",
        val period: Int = 0,
        val homeScore: Double = 0.0,
        val awayScore: Double = 0.0,
        val possession: String? = null,
        val down: Int? = null,
        val distance: Int? = null,
        val downDistance: String = "",
        val redZone: Boolean = false,
    )

    @Serializable
    data class Beacon(val height: Double, val color: String)

    @Serializable
    data class Ball(val x: Double, val y: Double = 0.0, val z: Double = 0.0, val beacon: Beacon)

    @Serializable
    data class Laser(val kind: String, val x: Double, val color: String)

    @Serializable
    data class Arc(
        val id: String,
        val style: String,
        val shape: String,
        val type: String = "",
        val fromX: Double,
        val toX: Double,
        val lane: Double = 0.0,
        val apex: Double = 0.0,
        val color: String,
        val dash: List<Double>? = null,
        val seconds: Double = 1.0,
        val duration: Double = 1.0,
        val side: String? = null,
        val text: String = "",
        val period: Int? = null,
        val clock: String = "",
        val down: Int? = null,
        val distance: Int? = null,
    )

    @Serializable
    data class Drive(
        val id: String,
        val team: String = "",
        val side: String? = null,
        val result: String = "",
        val arcs: List<Arc> = emptyList(),
    )

    @Serializable
    data class Horizon(val z: Double, val y0: Double, val y1: Double, val x0: Double, val x1: Double)

    @Serializable
    data class WinProbability(val side: String = "home", val series: List<Double> = emptyList(), val horizon: Horizon)

    @Serializable
    data class Moment(
        val kind: String,
        val side: String,
        val team: String = "",
        val points: Double = 0.0,
        val playId: String = "",
        val text: String = "",
        val period: Int? = null,
        val clock: String = "",
    ) {
        /** Worth stopping the stadium for. A turnover changes the drive; it lights nothing. */
        val celebrates: Boolean get() = kind == "touchdown" || kind == "fieldGoal" || kind == "safety"
    }

    @Serializable
    data class Tier(val name: String, val inner: Double, val outer: Double, val rise: List<Double>, val color: String)

    @Serializable
    data class Shape(val type: String, val exponent: Double, val halfLength: Double, val halfWidth: Double)

    @Serializable
    data class RimLights(val count: Int, val offset: Double, val height: Double, val side: String, val color: String)

    @Serializable
    data class SectionTint(val side: String? = null, val color: String? = null, val dim: Double = 0.28)

    @Serializable
    data class Crowd(val home: String, val away: String, val neutral: String, val dark: String)

    @Serializable
    data class Concourse(val inner: Double, val outer: Double, val color: String)

    @Serializable
    data class Bowl(
        val shape: Shape,
        val tiers: List<Tier>,
        val concourse: Concourse? = null,
        val rimLights: RimLights,
        val crowd: Crowd,
        val sectionTint: SectionTint = SectionTint(),
    )

    @Serializable
    data class Seat(val x: Double, val y: Double, val z: Double)

    @Serializable
    data class Tabletop(val metersPerYard: Double, val volume: List<Double> = emptyList(), val floor: Double = 0.0, val bowlTiers: List<String>)

    @Serializable
    data class Stadium(val metersPerYard: Double, val seat: Seat, val bowlTiers: List<String>)

    @Serializable
    data class Presentation(val tabletop: Tabletop, val stadium: Stadium, val beaconHeight: Double = 34.0)

    @Serializable
    data class Motion(
        val minSeconds: Double = 0.6,
        val maxSeconds: Double = 2.5,
        val referenceSpeed: Double = 20.0,
        val floorSeconds: Double = 0.2,
        val sectionDim: Double = 0.28,
    )
}

/** The remote control's view of a replay: GET /api/replay. */
@Serializable
data class ReplayState(
    val replay: Boolean = true,
    val loaded: Boolean = false,
    val playing: Boolean = false,
    val speed: Double = 1.0,
    val speeds: List<Double> = emptyList(),
    val event: String? = null,
    val gameSeconds: Int? = null,
    val length: Int? = null,
    val progress: Double? = null,
    val label: String? = null,
    val homeScore: Double? = null,
    val awayScore: Double? = null,
    val matchup: Matchup? = null,
    val games: List<Game>? = null,
    val driveStart: Int? = null,
) {
    @Serializable
    data class Side(val abbr: String, val score: Double = 0.0)

    @Serializable
    data class Matchup(val away: Side, val home: Side, val date: String = "", val final: String = "", val complete: Boolean = false)

    @Serializable
    data class Game(
        val event: String,
        val away: Side,
        val home: Side,
        val date: String = "",
        val final: String = "",
        val complete: Boolean = false,
        val plays: Int = 0,
        val length: Int = 0,
    )
}

class UnsupportedSceneException(message: String) : RuntimeException(message)

/**
 * Decodes a scene, refusing one this build cannot draw.
 *
 * A minor version only ever adds fields, so 1.3 decodes here and its new
 * fields are ignored. A major version is a different contract: drawing a 2.x
 * scene with 1.x rules would put things in the wrong place without an error,
 * so it is refused with a sentence the screen can show.
 */
object SceneDecoder {
    const val SUPPORTED_MAJOR = 1

    val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    fun decode(text: String): SceneSpec {
        val obj = try {
            json.parseToJsonElement(text).jsonObject
        } catch (e: IllegalArgumentException) {
            throw UnsupportedSceneException("The API sent something that is not a scene.")
        }
        checkVersion(obj)
        val kind = obj["kind"]?.jsonPrimitive?.contentOrNull
        if (kind != "football-scene") {
            throw UnsupportedSceneException("Expected a football-scene, got ${kind ?: "nothing"}.")
        }
        return json.decodeFromJsonElement(SceneSpec.serializer(), obj)
    }

    fun checkVersion(obj: JsonObject) {
        val version = obj["version"]?.jsonPrimitive?.contentOrNull
            ?: throw UnsupportedSceneException("This scene has no version, so it cannot be drawn safely.")
        val major = version.substringBefore('.').toIntOrNull()
            ?: throw UnsupportedSceneException("Scene version \"$version\" is not a version.")
        if (major != SUPPORTED_MAJOR) {
            throw UnsupportedSceneException(
                "This scene is version $version. This app draws version $SUPPORTED_MAJOR.x; update the app."
            )
        }
    }

    fun decodeReplay(text: String): ReplayState = json.decodeFromString(ReplayState.serializer(), text)
}
