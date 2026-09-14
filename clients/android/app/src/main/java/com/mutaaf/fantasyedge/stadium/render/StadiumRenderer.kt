package com.mutaaf.fantasyedge.stadium.render

import com.mutaaf.fantasyedge.stadium.geometry.Mode
import com.mutaaf.fantasyedge.stadium.geometry.StadiumGeometry
import com.mutaaf.fantasyedge.stadium.scene.PlayMotion
import com.mutaaf.fantasyedge.stadium.scene.SceneMath
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import com.mutaaf.fantasyedge.stadium.scene.Vec3
import kotlin.math.exp

/**
 * Draws a [SceneSpec] into a [Stage], at tabletop or stadium framing.
 *
 * The shape follows StadiumRenderer.swift so the platforms behave alike:
 * static geometry is built once per pair of teams; what moves (ball, beacon,
 * lasers) is placed once and slid; a drive's arcs are added only after the
 * ball has flown them, so the drive visibly grows.
 */
class StadiumRenderer(private val stage: Stage, val mode: Mode) {
    var spec: SceneSpec? = null
        private set

    private var staticKey = ""
    private val statics = mutableListOf<com.mutaaf.fantasyedge.stadium.render.Drawable>()
    private val crowd = mutableListOf<Drawable>()
    private var driveId = ""
    private val arcs = LinkedHashMap<String, List<Drawable>>()
    private var ball: Drawable? = null
    private var ballAt = Vec3.ZERO
    private var ballTarget = Vec3.ZERO
    private var ballVisible = false
    private var beacon: List<Drawable> = emptyList()
    private var beaconKey = ""
    private var beaconAt = Vec3.ZERO
    private val lasers = mutableMapOf<String, LaserState>()
    private var horizon: List<Drawable> = emptyList()
    private var horizonKey = ""
    private var tintKey = "unset"
    private val motion = PlayMotion()
    private var flight: Flight? = null
    private var reduceMotion = false

    private class LaserState(val parts: List<Drawable>, var x: Float, var target: Float)
    private class Flight(val arc: SceneSpec.Arc, val seconds: Double, var elapsed: Double = 0.0)

    fun apply(next: SceneSpec, reduceMotion: Boolean) {
        this.reduceMotion = reduceMotion
        val previous = spec
        spec = next
        val key = listOf(next.league, next.teams.home.chip, next.teams.away.chip, next.teams.home.abbr,
            next.teams.away.abbr, next.teams.home.hatch, next.teams.away.hatch).joinToString("|")
        if (key != staticKey) {
            buildStatic(next)
            staticKey = key
        }
        updateDrive(next, previous)
        updateHorizon(next)
        updateTint(next)
        if (flight == null) settle(next)
    }

    // ───────────────────────── static ─────────────────────────

    private fun buildStatic(s: SceneSpec) {
        (statics + crowd).forEach(stage::remove)
        statics.clear()
        crowd.clear()
        stage.clearLights()
        for (part in StadiumGeometry.staticParts(s, mode)) {
            val d = stage.add(part)
            if (part.group.startsWith("crowd:")) crowd += d else statics += d
        }
        // Real floodlights from each rim bank onto the turf. The tabletop is
        // lit the same way at its own scale, which is what makes it read as
        // a small stadium rather than a model under a desk lamp.
        val candela = if (mode == Mode.TABLETOP) 26000f else 15000f
        StadiumGeometry.rimLights(s, mode).forEach { stage.spotLight(it.position, Vec3(it.position.x * 0.15f, 0f, 0f), it.color, candela) }
        ball?.let(stage::remove)
        ball = stage.add(StadiumGeometry.ball(mode))
        ballVisible = false
        stage.translate(ball!!, Vec3(0f, -500f, 0f))
        beacon.forEach(stage::remove)
        beacon = emptyList()
        beaconKey = ""
        lasers.values.forEach { l -> l.parts.forEach(stage::remove) }
        lasers.clear()
        tintKey = "unset"
        tearDownDrive()
    }

    // ───────────────────────── the drive ─────────────────────────

    private fun tearDownDrive() {
        flight = null
        arcs.values.flatten().forEach(stage::remove)
        arcs.clear()
        motion.reset()
        driveId = ""
    }

    private fun updateDrive(s: SceneSpec, previous: SceneSpec?) {
        val drive = s.shownDrive
        if (drive == null) {
            tearDownDrive()
            return
        }
        val oldIds = previous?.shownDrive?.arcs?.map { it.id }?.toSet() ?: emptySet()
        val lostAPlay = oldIds.isNotEmpty() && drive.id == driveId && !drive.arcs.map { it.id }.toSet().containsAll(oldIds)
        // A new drive right after the old one is the game moving on, and its
        // plays fly. Anything else - a scrub, a jump, the first scene - is
        // history, laid down at rest.
        val nextDrive = previous != null && drive.id != driveId && s.drives.size >= previous.drives.size &&
            s.drives.indexOfFirst { it.id == drive.id } == (previous.drives.indexOfFirst { it.id == driveId }.takeIf { it >= 0 } ?: -2) + 1
        if (drive.id != driveId || lostAPlay) {
            tearDownDrive()
            driveId = drive.id
            val initial = !nextDrive
            motion.arrive(drive, initial)
            if (initial) {
                drive.arcs.forEach { addArc(it, s) }
                return
            }
        } else {
            motion.arrive(drive, false)
        }
        launchNext()
    }

    private fun addArc(arc: SceneSpec.Arc, s: SceneSpec) {
        if (arcs.containsKey(arc.id)) return
        arcs[arc.id] = StadiumGeometry.arc(arc, s, mode).map(stage::add)
    }

    private fun launchNext() {
        if (flight != null) return
        val s = spec ?: return
        val (arc, seconds) = motion.next(reduceMotion, s.motion.floorSeconds) ?: return
        if (seconds <= 0) {
            placeBall(SceneMath.point(arc, 1.0), jump = true)
            addArc(arc, s)
            launchNext()
            return
        }
        flight = Flight(arc, seconds)
        placeBall(SceneMath.point(arc, 0.0), jump = true)
    }

    // ───────────────────────── per frame ─────────────────────────

    fun tick(dt: Double) {
        val s = spec ?: return
        flight?.let { f ->
            f.elapsed += dt
            val t = (f.elapsed / f.seconds).coerceAtMost(1.0)
            placeBall(SceneMath.point(f.arc, t), jump = true)
            if (t >= 1.0) {
                addArc(f.arc, s)
                flight = null
                launchNext()
                if (flight == null) settle(s)
            }
        }
        if (flight == null) {
            val k = if (reduceMotion) 1f else (1 - exp(-dt * 9.0)).toFloat()
            ballAt += (ballTarget - ballAt) * k
            ball?.let { if (ballVisible) stage.translate(it, ballAt) }
            beacon.forEach { stage.translate(it, beaconAt) }
            for (l in lasers.values) {
                l.x += (l.target - l.x) * k
                l.parts.forEach { stage.translate(it, Vec3(l.x, 0f, 0f)) }
            }
        }
    }

    private fun placeBall(at: Vec3, jump: Boolean) {
        ballVisible = true
        ballTarget = at
        if (jump) ballAt = at
        ball?.let { stage.translate(it, at) }
    }

    // ───────────────────────── ball, beacon, lasers ─────────────────────────

    private fun settle(s: SceneSpec) {
        val b = s.ball
        if (b != null) {
            ballVisible = true
            ballTarget = SceneMath.local(b.x, StadiumGeometry.Look.BALL_LIFT, b.z)
            val key = "${b.beacon.height}|${b.beacon.color}"
            if (key != beaconKey) {
                beacon.forEach(stage::remove)
                beacon = StadiumGeometry.beacon(b, s, mode).map(stage::add)
                beaconKey = key
            }
            beaconAt = SceneMath.local(b.x, 0.0, b.z)
            if (reduceMotion) beacon.forEach { stage.translate(it, beaconAt) }
        } else {
            ballVisible = false
            ball?.let { stage.translate(it, Vec3(0f, -500f, 0f)) }
            beacon.forEach(stage::remove)
            beacon = emptyList()
            beaconKey = ""
        }
        val want = s.lasers.associateBy { it.kind }
        for (kind in lasers.keys - want.keys) {
            lasers.remove(kind)?.parts?.forEach(stage::remove)
        }
        for ((kind, laser) in want) {
            val x = (laser.x - 50).toFloat()
            val state = lasers.getOrPut(kind) {
                LaserState(StadiumGeometry.laser(laser, s).map(stage::add), x, x).also { st ->
                    st.parts.forEach { stage.translate(it, Vec3(x, 0f, 0f)) }
                }
            }
            state.target = x
        }
    }

    // ───────────────────────── horizon and tint ─────────────────────────

    private fun updateHorizon(s: SceneSpec) {
        val key = "${s.winProbability.series.size}|${s.winProbability.series.lastOrNull()}"
        if (key == horizonKey) return
        horizonKey = key
        horizon.forEach(stage::remove)
        horizon = StadiumGeometry.horizon(s, mode).map(stage::add)
    }

    /** The scoring side's club-coloured fans take the scoring chip; the other side dims. */
    private fun updateTint(s: SceneSpec) {
        val tint = s.bowl.sectionTint
        val key = "${tint.side}|${tint.color}"
        if (key == tintKey) return
        tintKey = key
        val teamColours = setOf(s.bowl.crowd.home, s.bowl.crowd.away)
        for (d in crowd) {
            val (_, section, colour) = d.part.group.split(":", limit = 3)
            val base = SceneMath.linearRgba(colour)
            val c = when {
                tint.side == null -> base
                tint.side == section -> if (colour in teamColours) SceneMath.linearRgba(tint.color ?: colour).map { it * 1.35f }.toFloatArray() else base
                else -> floatArrayOf(base[0] * tint.dim.toFloat(), base[1] * tint.dim.toFloat(), base[2] * tint.dim.toFloat(), 1f)
            }
            d.tint(c[0], c[1], c[2], 1f)
        }
    }

    fun destroy() {
        (statics + crowd + arcs.values.flatten() + beacon + horizon + lasers.values.flatMap { it.parts } + listOfNotNull(ball)).forEach(stage::remove)
        statics.clear()
        crowd.clear()
        arcs.clear()
        stage.clearLights()
    }
}
