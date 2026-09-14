package com.mutaaf.fantasyedge.stadium.scene

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

data class Vec3(val x: Float, val y: Float, val z: Float) {
    operator fun plus(o: Vec3) = Vec3(x + o.x, y + o.y, z + o.z)
    operator fun minus(o: Vec3) = Vec3(x - o.x, y - o.y, z - o.z)
    operator fun times(s: Float) = Vec3(x * s, y * s, z * s)
    fun dot(o: Vec3) = x * o.x + y * o.y + z * o.z
    fun cross(o: Vec3) = Vec3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x)
    fun length() = sqrt(dot(this))
    fun normalized(): Vec3 {
        val l = length()
        return if (l < 1e-6f) this else this * (1f / l)
    }

    companion object {
        val ZERO = Vec3(0f, 0f, 0f)
        val UP = Vec3(0f, 1f, 0f)
    }
}

/**
 * Pure geometry for a scene: yards in, local points out.
 *
 * A line-for-line port of apple/FantasyEdge/Sources/Stadium/SceneMath.swift,
 * and meant to stay one: a renderer on any platform reproduces exactly this
 * and nothing more. The unit tests hold it to the scene's own numbers.
 */
object SceneMath {

    /** Midfield is the origin, so the field sits centred and a seat is placed relative to it. */
    fun local(x: Double, y: Double = 0.0, z: Double = 0.0): Vec3 =
        Vec3((x - 50).toFloat(), y.toFloat(), z.toFloat())

    /** A point on a play's arc, t from 0 at the snap spot to 1 where it ended. Peaks at exactly `apex`. */
    fun point(arc: SceneSpec.Arc, t: Double): Vec3 {
        val u = max(0.0, min(1.0, t))
        val x = arc.fromX + (arc.toX - arc.fromX) * u
        val y = arc.apex * 4 * u * (1 - u)
        return local(x, y, arc.lane)
    }

    fun samples(arc: SceneSpec.Arc, count: Int = 24): List<Vec3> {
        val n = max(2, count)
        return (0 until n).map { point(arc, it.toDouble() / (n - 1)) }
    }

    /** The arc split into the pieces a dashed style draws; a solid arc is one piece. */
    fun dashes(arc: SceneSpec.Arc, count: Int = 48): List<List<Vec3>> {
        val pts = samples(arc, count)
        val pattern = arc.dash
        if (pattern == null || pattern.size != 2 || pattern[0] <= 0) return listOf(pts)
        val pieces = mutableListOf<List<Vec3>>()
        var current = mutableListOf(pts[0])
        var travelled = 0f
        val on = pattern[0].toFloat()
        val period = (pattern[0] + pattern[1]).toFloat()
        for (i in 1 until pts.size) {
            travelled += (pts[i] - pts[i - 1]).length()
            val drawing = travelled % period < on
            if (drawing) {
                current.add(pts[i])
            } else if (current.size > 1) {
                pieces.add(current)
                current = mutableListOf(pts[i])
            } else {
                current = mutableListOf(pts[i])
            }
        }
        if (current.size > 1) pieces.add(current)
        return pieces
    }

    /** A point on the bowl's superellipse, `m` yards out from the field's edge, at angle `t`. */
    fun bowlPoint(shape: SceneSpec.Shape, m: Double, t: Double): Pair<Double, Double> {
        val a = shape.halfLength + m
        val b = shape.halfWidth + m
        val e = 2 / shape.exponent
        val c = cos(t)
        val s = sin(t)
        val x = a * (if (c < 0) -1.0 else 1.0) * abs(c).pow(e)
        val z = b * (if (s < 0) -1.0 else 1.0) * abs(s).pow(e)
        return x to z
    }

    fun tierHeight(tier: SceneSpec.Tier, m: Double): Double {
        val span = max(1e-6, tier.outer - tier.inner)
        val f = max(0.0, min(1.0, (m - tier.inner) / span))
        return tier.rise[0] + (tier.rise[1] - tier.rise[0]) * f
    }

    fun horizon(wp: SceneSpec.WinProbability): List<Vec3> {
        val s = wp.series
        if (s.size <= 1) return emptyList()
        val h = wp.horizon
        return s.mapIndexed { i, p ->
            val x = h.x0 + (h.x1 - h.x0) * i / (s.size - 1)
            local(x, h.y0 + (h.y1 - h.y0) * p, h.z)
        }
    }

    /** "#RRGGBB" or "#RRGGBBAA" as sRGB components and alpha, 0..1. */
    fun rgba(hex: String): FloatArray {
        var h = hex.trim()
        if (h.startsWith("#")) h = h.substring(1)
        val v = if (h.length == 6 || h.length == 8) h.toLongOrNull(16) else null
        if (v == null) return floatArrayOf(0.5f, 0.5f, 0.5f, 1f)
        val n = if (h.length == 8) v else (v shl 8) or 0xFF
        return floatArrayOf(
            ((n shr 24) and 0xFF) / 255f, ((n shr 16) and 0xFF) / 255f,
            ((n shr 8) and 0xFF) / 255f, (n and 0xFF) / 255f,
        )
    }

    /** sRGB to linear, which is what a physically based renderer wants as a base colour. */
    fun linear(c: Float): Float =
        if (c <= 0.04045f) c / 12.92f else ((c + 0.055f) / 1.055f).toDouble().pow(2.4).toFloat()

    fun linearRgba(hex: String): FloatArray {
        val c = rgba(hex)
        return floatArrayOf(linear(c[0]), linear(c[1]), linear(c[2]), c[3])
    }

    fun smoothstep(t: Double): Double {
        val u = max(0.0, min(1.0, t))
        return u * u * (3 - 2 * u)
    }
}

/**
 * How the ball travels each new play, in order. Ported from PlayMotion in
 * SceneMath.swift: plays queue, each flies for the duration the scene gave it,
 * a backlog over three halves what is left, and reduce motion lands the ball.
 */
class PlayMotion {
    val queue = ArrayDeque<SceneSpec.Arc>()
    val seen = mutableSetOf<String>()

    /** The first scene is history, not news: it is marked seen and nothing animates. */
    fun arrive(drive: SceneSpec.Drive?, initial: Boolean): List<SceneSpec.Arc> {
        if (drive == null) return emptyList()
        val fresh = drive.arcs.filter { it.id !in seen }
        drive.arcs.forEach { seen.add(it.id) }
        if (initial) return emptyList()
        queue.addAll(fresh)
        return fresh
    }

    fun reset() {
        queue.clear()
        seen.clear()
    }

    fun next(reduceMotion: Boolean, floor: Double): Pair<SceneSpec.Arc, Double>? {
        val arc = queue.removeFirstOrNull() ?: return null
        if (reduceMotion) return arc to 0.0
        val squeeze = if (queue.size > 3) 0.5 else 1.0
        return arc to max(floor, arc.duration * squeeze)
    }
}
