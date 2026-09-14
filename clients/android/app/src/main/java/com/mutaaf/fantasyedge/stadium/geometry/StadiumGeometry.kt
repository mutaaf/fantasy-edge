package com.mutaaf.fantasyedge.stadium.geometry

import com.mutaaf.fantasyedge.stadium.scene.SceneMath
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import com.mutaaf.fantasyedge.stadium.scene.Vec3
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sin

enum class Mode { TABLETOP, STADIUM }

data class RimLight(val position: Vec3, val target: Vec3, val color: FloatArray)

/**
 * Meshes for a scene, built from its numbers alone.
 *
 * Everything that decides football - apexes, lanes, which drive, which side is
 * lit - is read from the spec. What is here is only how a primitive becomes
 * triangles. Where the spec is silent (how thick an arc is, how many people
 * fill a tier) the value matches the visionOS renderer so the two platforms
 * draw the same stadium; each of those is listed in [Look] as a gap the spec
 * should close.
 */
object StadiumGeometry {

    /** Presentation values the scene spec does not carry yet, matched to StadiumRenderer.swift. */
    object Look {
        fun crowdCount(mode: Mode) = if (mode == Mode.TABLETOP) 1800 else 6000
        fun arcRadius(mode: Mode) = if (mode == Mode.TABLETOP) 0.45f else 0.22f
        const val HALO_FACTOR = 3.2f
        const val SCORE_EMPHASIS = 1.5f
        fun haloAlpha(score: Boolean) = if (score) 0.3f else 0.14f
        fun rimAboveTier(mode: Mode) = if (mode == Mode.TABLETOP) 4.0 else 9.0
        fun lampSize(mode: Mode) = if (mode == Mode.TABLETOP) floatArrayOf(6f, 2f) else floatArrayOf(10f, 4f)
        fun ballRadius(mode: Mode) = if (mode == Mode.TABLETOP) 1.2f else 0.6f
        fun beaconRadius(mode: Mode) = if (mode == Mode.TABLETOP) 1.4f else 0.7f
        fun horizonThickness(mode: Mode) = if (mode == Mode.TABLETOP) 0.35f else 0.18f
        const val BALL_LIFT = 0.8
        const val SKY_RADIUS = 700f
        const val NUMBERS_IN_FROM_SIDELINE = 9.0
        const val TREAD_YARDS = 2.0
        const val BOWL_SEGMENTS = 128
    }

    fun tiersFor(spec: SceneSpec, mode: Mode): List<SceneSpec.Tier> {
        val names = if (mode == Mode.TABLETOP) spec.presentation.tabletop.bowlTiers else spec.presentation.stadium.bowlTiers
        return spec.bowl.tiers.filter { it.name in names }
    }

    fun staticParts(spec: SceneSpec, mode: Mode): List<Part> {
        val parts = mutableListOf<Part>()
        parts += field(spec)
        val tiers = tiersFor(spec, mode)
        tiers.forEach { parts += tier(it, spec.bowl.shape, spec.color(it.color, "#302722")) }
        val concourse = spec.bowl.concourse
        if (concourse != null && tiers.size > 1) {
            parts += concourse(concourse, spec.bowl.shape, tiers, spec.color(concourse.color, "#15110F"))
        }
        parts += crowd(spec, tiers, Look.crowdCount(mode))
        if (mode == Mode.STADIUM) parts += sky(spec)
        if (mode == Mode.TABLETOP) parts += plinth(spec, tiers)
        parts += rimLamps(spec, mode)
        return parts
    }

    // ───────────────────────── the field ─────────────────────────

    fun field(spec: SceneSpec): Part {
        val f = spec.field
        val half = f.width / 2
        val mesh = MeshData()
        fun plate(x0: Double, x1: Double, z0: Double, z1: Double, y: Double, hex: String, gain: Float = 1f) {
            val c = SceneMath.linearRgba(hex).let { floatArrayOf(it[0] * gain, it[1] * gain, it[2] * gain, 1f) }
            mesh.quad(
                SceneMath.local(x0, y, z1), SceneMath.local(x1, y, z1),
                SceneMath.local(x1, y, z0), SceneMath.local(x0, y, z0), c, Vec3.UP,
            )
        }
        plate(-f.endZone - 6, f.length + f.endZone + 6, -half - 6, half + 6, -0.02, spec.color("turf.surround", "#17401F"))
        var x = 0.0
        var i = 0
        while (x < f.length) {
            val hex = if (i % 2 == 0) spec.color("turf.b", "#237A3C") else spec.color("turf.a", "#1E6A34")
            plate(x, x + f.stripeEvery, -half, half, 0.0, hex)
            x += f.stripeEvery
            i++
        }
        plate(-f.endZone, 0.0, -half, half, 0.0, spec.teams.home.chip)
        plate(f.length, f.length + f.endZone, -half, half, 0.0, spec.teams.away.chip)
        if (spec.teams.away.hatch) hatch(mesh, f.length, f.length + f.endZone, half)
        if (spec.teams.home.hatch) hatch(mesh, -f.endZone, 0.0, half)
        val line = spec.color("line.yard", "#FFFFFF")
        var yard = 0.0
        while (yard <= f.length + 1e-6) {
            val heavy = abs(yard % 10.0) < 1e-6
            val w = if (heavy) 0.22 else 0.14
            plate(yard - w, yard + w, -half, half, 0.01, line, if (heavy) 0.85f else 0.55f)
            yard += f.stripeEvery
        }
        // Sidelines and end lines.
        plate(-f.endZone - 2, f.length + f.endZone + 2, half, half + 2, 0.01, line, 0.9f)
        plate(-f.endZone - 2, f.length + f.endZone + 2, -half - 2, -half, 0.01, line, 0.9f)
        val hash = half - f.hashFromSideline
        for (y in 1 until f.length.toInt()) {
            for (z in doubleArrayOf(hash, -hash)) {
                plate(y - 0.06, y + 0.06, z - 0.35, z + 0.35, 0.01, line, 0.45f)
            }
        }
        var n = f.numbersEvery
        while (n < f.length - 1e-6) {
            val label = (if (n <= f.length / 2) n else f.length - n).roundToInt().toString()
            // Read from each sideline, as painted: the home side's digits face +z, the far side's -z.
            numerals(mesh, label, n, half - Look.NUMBERS_IN_FROM_SIDELINE, homeSide = true, hex = line)
            numerals(mesh, label, n, -(half - Look.NUMBERS_IN_FROM_SIDELINE), homeSide = false, hex = line)
            n += f.numbersEvery
        }
        return Part("field", mesh, Surface.LIT, roughness = 0.95f)
    }

    private fun hatch(mesh: MeshData, x0: Double, x1: Double, half: Double) {
        val c = floatArrayOf(0f, 0f, 0f, 1f).also { it[0] = 0.02f; it[1] = 0.02f; it[2] = 0.02f }
        var z = -half
        while (z < half) {
            mesh.quad(
                SceneMath.local(x0, 0.005, z + 1.2), SceneMath.local(x1, 0.005, z + 1.2 + (x1 - x0) * 0.6),
                SceneMath.local(x1, 0.005, z + (x1 - x0) * 0.6), SceneMath.local(x0, 0.005, z), c, Vec3.UP,
            )
            z += 3.6
        }
    }

    private val SEGMENTS = mapOf(
        '0' to "abcdef", '1' to "bc", '2' to "abdeg", '3' to "abcdg", '4' to "bcfg",
        '5' to "acdfg", '6' to "acdefg", '7' to "abc", '8' to "abcdefg", '9' to "abcdfg",
    )

    /** Yard numbers as seven-segment strokes flat on the grass: no font engine needed. */
    private fun numerals(mesh: MeshData, label: String, atX: Double, atZ: Double, homeSide: Boolean, hex: String) {
        val c = SceneMath.linearRgba(hex).let { floatArrayOf(it[0] * 0.7f, it[1] * 0.7f, it[2] * 0.7f, 1f) }
        val h = 2.0
        val w = 1.1
        val t = 0.24
        val gap = 0.5
        // From the home sideline, a reader faces -z: right is +x, up the page is -z.
        val right = if (homeSide) 1.0 else -1.0
        val up = if (homeSide) -1.0 else 1.0
        val total = label.length * w + (label.length - 1) * gap
        label.forEachIndexed { k, ch ->
            val u0 = -total / 2 + k * (w + gap)
            val segs = SEGMENTS[ch] ?: return@forEachIndexed
            fun stroke(ua: Double, va: Double, ub: Double, vb: Double) {
                val x0 = atX + right * ua
                val x1 = atX + right * ub
                val z0 = atZ + up * va
                val z1 = atZ + up * vb
                mesh.quad(
                    SceneMath.local(minOf(x0, x1), 0.012, maxOf(z0, z1)), SceneMath.local(maxOf(x0, x1), 0.012, maxOf(z0, z1)),
                    SceneMath.local(maxOf(x0, x1), 0.012, minOf(z0, z1)), SceneMath.local(minOf(x0, x1), 0.012, minOf(z0, z1)),
                    c, Vec3.UP,
                )
            }
            val v0 = -h / 2
            for (s in segs) when (s) {
                'a' -> stroke(u0, v0 + h - t, u0 + w, v0 + h)
                'b' -> stroke(u0 + w - t, v0 + h / 2, u0 + w, v0 + h)
                'c' -> stroke(u0 + w - t, v0, u0 + w, v0 + h / 2)
                'd' -> stroke(u0, v0, u0 + w, v0 + t)
                'e' -> stroke(u0, v0, u0 + t, v0 + h / 2)
                'f' -> stroke(u0, v0 + h / 2, u0 + t, v0 + h)
                'g' -> stroke(u0, v0 + h / 2 - t / 2, u0 + w, v0 + h / 2 + t / 2)
            }
        }
    }

    // ───────────────────────── the bowl ─────────────────────────

    private fun outward(shape: SceneSpec.Shape, m: Double, t: Double): Vec3 {
        val (x0, z0) = SceneMath.bowlPoint(shape, m, t)
        val (x1, z1) = SceneMath.bowlPoint(shape, m + 1, t)
        return Vec3((x1 - x0).toFloat(), 0f, (z1 - z0).toFloat()).normalized()
    }

    fun stepsFor(tier: SceneSpec.Tier): Int = max(2, ((tier.outer - tier.inner) / Look.TREAD_YARDS).roundToInt())

    /** Height of step `k`'s tread: the first at the tier's front rise, the last at its back. */
    fun stepHeight(tier: SceneSpec.Tier, k: Int): Double {
        val steps = stepsFor(tier)
        return tier.rise[0] + (tier.rise[1] - tier.rise[0]) * k / (steps - 1)
    }

    /**
     * A tier as terraces - a tread and a riser per row of seats - so under the
     * lights it reads as seating rather than a ramp. The treads follow the
     * spec's rise exactly; the stepping is only how the slope is drawn.
     */
    fun tier(tier: SceneSpec.Tier, shape: SceneSpec.Shape, hex: String, segments: Int = Look.BOWL_SEGMENTS): Part {
        val mesh = MeshData()
        val base = SceneMath.linearRgba(hex)
        val steps = stepsFor(tier)
        val depth = (tier.outer - tier.inner) / steps
        fun shade(g: Float) = floatArrayOf(base[0] * g, base[1] * g, base[2] * g, 1f)
        val front = tier.rise[0]
        for (s in 0 until segments) {
            val t0 = 2 * PI * s / segments
            val t1 = 2 * PI * (s + 1) / segments
            fun p(m: Double, y: Double, t: Double): Vec3 {
                val (x, z) = SceneMath.bowlPoint(shape, m, t)
                return Vec3(x.toFloat(), y.toFloat(), z.toFloat())
            }
            // The front wall, from the ground (or the deck below) up to the first tread.
            val wallBase = if (front > 8) front - 3.0 else 0.0
            val inward = outward(shape, tier.inner, (t0 + t1) / 2) * -1f
            mesh.quad(p(tier.inner, wallBase, t0), p(tier.inner, wallBase, t1), p(tier.inner, front, t1), p(tier.inner, front, t0), shade(0.55f), inward)
            for (k in 0 until steps) {
                val m0 = tier.inner + k * depth
                val m1 = m0 + depth
                val y = stepHeight(tier, k)
                val row = if (k % 2 == 0) 1.0f else 0.86f
                mesh.quad(p(m0, y, t1), p(m1, y, t1), p(m1, y, t0), p(m0, y, t0), shade(row), Vec3.UP)
                if (k < steps - 1) {
                    val yn = stepHeight(tier, k + 1)
                    val inw = outward(shape, m1, (t0 + t1) / 2) * -1f
                    mesh.quad(p(m1, y, t0), p(m1, y, t1), p(m1, yn, t1), p(m1, yn, t0), shade(0.62f), inw)
                }
            }
            // The back wall behind the last row.
            val out = outward(shape, tier.outer, (t0 + t1) / 2)
            mesh.quad(p(tier.outer, tier.rise[1], t0), p(tier.outer, tier.rise[1], t1), p(tier.outer, tier.rise[1] + 3, t1), p(tier.outer, tier.rise[1] + 3, t0), shade(0.4f), out * -1f)
        }
        return Part("tier.${tier.name}", mesh, Surface.LIT, roughness = 0.85f)
    }

    fun concourse(c: SceneSpec.Concourse, shape: SceneSpec.Shape, tiers: List<SceneSpec.Tier>, hex: String): Part {
        val mesh = MeshData()
        val col = SceneMath.linearRgba(hex)
        val lower = tiers.first()
        val upper = tiers.last()
        val y0 = lower.rise[1]
        val y1 = upper.rise[0] - 3
        val segments = Look.BOWL_SEGMENTS
        for (s in 0 until segments) {
            val t0 = 2 * PI * s / segments
            val t1 = 2 * PI * (s + 1) / segments
            val (ax, az) = SceneMath.bowlPoint(shape, c.outer, t0)
            val (bx, bz) = SceneMath.bowlPoint(shape, c.outer, t1)
            val inward = outward(shape, c.outer, (t0 + t1) / 2) * -1f
            mesh.quad(
                Vec3(ax.toFloat(), y0.toFloat(), az.toFloat()), Vec3(bx.toFloat(), y0.toFloat(), bz.toFloat()),
                Vec3(bx.toFloat(), y1.toFloat(), bz.toFloat()), Vec3(ax.toFloat(), y1.toFloat(), az.toFloat()), col, inward,
            )
        }
        return Part("concourse", mesh, Surface.LIT)
    }

    private class Rng(var s: Long) {
        fun next(): Double {
            s = s * 6364136223846793005L + 1442695040888963407L
            return (s ushr 11).toDouble() / (1L shl 53).toDouble()
        }
    }

    /**
     * The crowd: `count` people seated on the treads, merged into one mesh per
     * section and colour. Vertices are grey-white shirt shades; the club colour
     * is the part's tint, so a touchdown relights a section by changing one
     * parameter instead of rebuilding six thousand quads.
     */
    fun crowd(spec: SceneSpec, tiers: List<SceneSpec.Tier>, count: Int): List<Part> {
        if (tiers.isEmpty()) return emptyList()
        val rng = Rng(12)
        val shape = spec.bowl.shape
        val crowd = spec.bowl.crowd
        val neutral = spec.color(crowd.neutral, "#F4F1EA")
        val dark = spec.color(crowd.dark, "#2A2A2A")
        val buckets = linkedMapOf<Pair<String, String>, MeshData>()
        repeat(count) {
            val tier = tiers[minOf(tiers.size - 1, (rng.next() * tiers.size).toInt())]
            val steps = stepsFor(tier)
            val depth = (tier.outer - tier.inner) / steps
            val k = minOf(steps - 1, floor(rng.next() * steps).toInt())
            val m = tier.inner + (k + 0.55) * depth
            val t = rng.next() * 2 * PI
            val (x, z) = SceneMath.bowlPoint(shape, m, t)
            val y = stepHeight(tier, k)
            val section = if (z >= 0) "home" else "away"
            val r = rng.next()
            val visitors = x > 40 && z < -10
            val colour = if (visitors) {
                if (r < 0.8) crowd.away else neutral
            } else {
                if (r < 0.62) crowd.home else if (r < 0.86) neutral else dark
            }
            val facing = outward(shape, m, t) * -1f
            val right = Vec3.UP.cross(facing).normalized()
            val half = 0.27f + 0.05f * rng.next().toFloat()
            val tall = 0.8f + 0.25f * rng.next().toFloat()
            val g = (0.5 + 0.35 * rng.next()).toFloat()
            val shade = floatArrayOf(g, g, g, 1f)
            val c = Vec3(x.toFloat(), y.toFloat(), z.toFloat())
            val mesh = buckets.getOrPut(section to colour) { MeshData() }
            mesh.quad(c - right * half, c + right * half, c + right * half + Vec3.UP * tall, c - right * half + Vec3.UP * tall, shade, facing)
        }
        return buckets.map { (key, mesh) ->
            Part("crowd.${key.first}.${key.second}", mesh, Surface.LIT, tint = SceneMath.linearRgba(key.second),
                group = "crowd:${key.first}:${key.second}", roughness = 0.9f)
        }
    }

    /** Where the rim's light banks stand, exactly as StadiumMeshes.rimLights places them. */
    fun rimLights(spec: SceneSpec, mode: Mode): List<RimLight> {
        val tiers = tiersFor(spec, mode)
        val outer = tiers.lastOrNull() ?: return emptyList()
        val lights = spec.bowl.rimLights
        val rim = outer.outer + 1
        val height = outer.rise[1] + Look.rimAboveTier(mode)
        val colour = SceneMath.linearRgba(spec.color(lights.color, "#FFF8E6"))
        val out = mutableListOf<RimLight>()
        for (k in 0 until lights.count) {
            val t = k * PI / maxOf(1, lights.count / 2) + 0.3
            val (x, z) = SceneMath.bowlPoint(spec.bowl.shape, rim, t)
            if (lights.side == "far" && z > 12) continue
            out += RimLight(Vec3(x.toFloat(), height.toFloat(), z.toFloat()), Vec3.ZERO, colour)
        }
        return out
    }

    fun rimLamps(spec: SceneSpec, mode: Mode): List<Part> {
        val lights = rimLights(spec, mode)
        if (lights.isEmpty()) return emptyList()
        val size = Look.lampSize(mode)
        val lamps = MeshData()
        val glow = MeshData()
        val poles = MeshData()
        val pole = SceneMath.linearRgba("#3A342E")
        val outer = tiersFor(spec, mode).last()
        for (l in lights) {
            val facing = (l.target - l.position).let { Vec3(it.x, 0f, it.z) }.normalized()
            val right = Vec3.UP.cross(facing).normalized()
            val tilt = (l.target - l.position).normalized()
            val up = right.cross(tilt).normalized() * -1f
            val hw = size[0] / 2
            val hh = size[1] / 2
            val c = l.position
            val white = floatArrayOf(1f, 1f, 1f, 1f)
            lamps.quad(c - right * hw - up * hh, c + right * hw - up * hh, c + right * hw + up * hh, c - right * hw + up * hh, white, tilt)
            // A soft disc of light around each bank; additive, so it genuinely glows.
            val centre = glow.vertex(c + tilt * 0.3f, tilt, floatArrayOf(0.9f, 0.85f, 0.7f, 0.55f))
            val radius = size[0] * 1.3f
            val ring = 20
            val first = glow.vertexCount
            for (i in 0 until ring) {
                val a = 2 * PI * i / ring
                val p = c + tilt * 0.3f + right * (radius * cos(a).toFloat()) + up * (radius * 0.6f * sin(a).toFloat())
                glow.vertex(p, tilt, floatArrayOf(0f, 0f, 0f, 0f))
            }
            for (i in 0 until ring) glow.triangle(centre, first + i, first + (i + 1) % ring)
            val base = Vec3(c.x, outer.rise[1].toFloat(), c.z)
            poles.quad(base - right * 0.3f, base + right * 0.3f, c + right * 0.3f - up * hh, c - right * 0.3f - up * hh, pole, facing * -1f)
        }
        return listOf(
            Part("rim.lamps", lamps, Surface.GLOW, tint = lights.first().color, emissive = 6f),
            Part("rim.glow", glow, Surface.ADD, tint = lights.first().color, emissive = 2.2f),
            Part("rim.poles", poles, Surface.LIT),
        )
    }

    /** The night: a dome seen from inside, graded from the horizon haze to the zenith. */
    fun sky(spec: SceneSpec): Part {
        val mesh = MeshData()
        val top = SceneMath.linearRgba(spec.color("sky.top", "#03050A"))
        val horizon = SceneMath.linearRgba(spec.color("sky.horizon", "#1A2436"))
        val rings = 18
        val slices = 48
        val r = Look.SKY_RADIUS
        for (i in 0..rings) {
            val phi = -PI / 2 + PI * i / rings
            val y = sin(phi)
            val f = SceneMath.smoothstep(y / 0.45).toFloat()
            val below = y < 0
            val c = if (below) floatArrayOf(horizon[0] * 0.35f, horizon[1] * 0.35f, horizon[2] * 0.35f, 1f)
            else floatArrayOf(horizon[0] + (top[0] - horizon[0]) * f, horizon[1] + (top[1] - horizon[1]) * f, horizon[2] + (top[2] - horizon[2]) * f, 1f)
            for (j in 0..slices) {
                val theta = 2 * PI * j / slices
                val p = Vec3((cos(phi) * cos(theta)).toFloat() * r, y.toFloat() * r, (cos(phi) * sin(theta)).toFloat() * r)
                mesh.vertex(p, p.normalized() * -1f, c)
            }
        }
        val cols = slices + 1
        for (i in 0 until rings) for (j in 0 until slices) {
            val a = i * cols + j
            val b = a + 1
            val c = a + cols
            val d = c + 1
            mesh.triangle(a, c, b)
            mesh.triangle(b, c, d)
        }
        return Part("sky", mesh, Surface.SKY)
    }

    private fun plinth(spec: SceneSpec, tiers: List<SceneSpec.Tier>): Part {
        val mesh = MeshData()
        val outer = (tiers.lastOrNull()?.outer ?: 36.0) + 6
        val col = SceneMath.linearRgba("#101214")
        val segments = 96
        val centre = mesh.vertex(Vec3(0f, -0.4f, 0f), Vec3.UP, col)
        for (s in 0..segments) {
            val (x, z) = SceneMath.bowlPoint(spec.bowl.shape, outer, 2 * PI * s / segments)
            mesh.vertex(Vec3(x.toFloat(), -0.4f, z.toFloat()), Vec3.UP, col)
        }
        for (s in 0 until segments) mesh.triangle(centre, centre + 1 + s + 1, centre + 1 + s)
        return Part("plinth", mesh, Surface.LIT, roughness = 0.4f)
    }

    // ───────────────────────── what moves ─────────────────────────

    /** A tube through points: an arc, a rail. */
    fun tube(mesh: MeshData, pts: List<Vec3>, radius: Float, color: FloatArray, sides: Int = 8, taper: ((Int) -> Float)? = null) {
        if (pts.size < 2) return
        val start = mesh.vertexCount
        for ((i, p) in pts.withIndex()) {
            val tangent = (pts[minOf(pts.size - 1, i + 1)] - pts[maxOf(0, i - 1)]).normalized()
            val ref = if (abs(tangent.dot(Vec3.UP)) > 0.9f) Vec3(1f, 0f, 0f) else Vec3.UP
            val n1 = tangent.cross(ref).normalized()
            val n2 = tangent.cross(n1).normalized()
            val c = taper?.invoke(i)?.let { floatArrayOf(color[0], color[1], color[2], color[3] * it) } ?: color
            for (s in 0 until sides) {
                val a = 2 * PI * s / sides
                val dir = n1 * cos(a).toFloat() + n2 * sin(a).toFloat()
                mesh.vertex(p + dir * radius, dir, c)
            }
        }
        for (i in 0 until pts.size - 1) for (s in 0 until sides) {
            val a = start + i * sides + s
            val b = start + i * sides + (s + 1) % sides
            val c = a + sides
            val d = b + sides
            mesh.triangle(a, c, b)
            mesh.triangle(b, c, d)
        }
    }

    fun arc(arc: SceneSpec.Arc, spec: SceneSpec, mode: Mode): List<Part> {
        val colour = SceneMath.linearRgba(spec.color(arc.color, "#FFFFFF"))
        val score = arc.style == "score"
        val radius = Look.arcRadius(mode) * (if (score) Look.SCORE_EMPHASIS else 1f)
        val core = MeshData()
        SceneMath.dashes(arc).forEach { tube(core, it, radius, floatArrayOf(1f, 1f, 1f, 1f)) }
        val halo = MeshData()
        tube(halo, SceneMath.samples(arc), Look.arcRadius(mode) * Look.HALO_FACTOR, floatArrayOf(1f, 1f, 1f, Look.haloAlpha(score)), sides = 8)
        return listOf(
            Part("arc.core.${arc.id}", core, Surface.GLOW, tint = colour, group = "arc:${arc.id}", emissive = if (score) 3.2f else 2.2f),
            Part("arc.halo.${arc.id}", halo, Surface.ADD, tint = colour, group = "arc:${arc.id}", emissive = 1.4f),
        )
    }

    /** A laser across the field, built at x = 0; the renderer slides it to the spec's x. */
    fun laser(laser: SceneSpec.Laser, spec: SceneSpec): List<Part> {
        val colour = SceneMath.linearRgba(spec.color(laser.color, "#FFD400"))
        val half = spec.field.width / 2
        val core = MeshData()
        val w = 0.175
        core.quad(Vec3(-w.toFloat(), 0.05f, half.toFloat()), Vec3(w.toFloat(), 0.05f, half.toFloat()),
            Vec3(w.toFloat(), 0.05f, -half.toFloat()), Vec3(-w.toFloat(), 0.05f, -half.toFloat()), floatArrayOf(1f, 1f, 1f, 1f), Vec3.UP)
        val glow = MeshData()
        val gw = 0.9f
        val white = floatArrayOf(1f, 1f, 1f, 0.35f)
        val clear = floatArrayOf(1f, 1f, 1f, 0f)
        for (sign in floatArrayOf(-1f, 1f)) {
            val a = glow.vertex(Vec3(0f, 0.06f, half.toFloat()), Vec3.UP, white)
            val b = glow.vertex(Vec3(sign * gw, 0.06f, half.toFloat()), Vec3.UP, clear)
            val c = glow.vertex(Vec3(sign * gw, 0.06f, -half.toFloat()), Vec3.UP, clear)
            val d = glow.vertex(Vec3(0f, 0.06f, -half.toFloat()), Vec3.UP, white)
            glow.triangle(a, b, c)
            glow.triangle(a, c, d)
        }
        return listOf(
            Part("laser.core.${laser.kind}", core, Surface.GLOW, tint = colour, group = "laser:${laser.kind}", emissive = 2.5f),
            Part("laser.glow.${laser.kind}", glow, Surface.ADD, tint = colour, group = "laser:${laser.kind}", emissive = 1.5f),
        )
    }

    /** The ball's beacon, built at the origin: a soft beam fading upward. */
    fun beacon(ball: SceneSpec.Ball, spec: SceneSpec, mode: Mode): List<Part> {
        val colour = SceneMath.linearRgba(spec.color(ball.beacon.color, "#BFE3FF"))
        val height = ball.beacon.height.toFloat()
        val radius = Look.beaconRadius(mode)
        val beam = MeshData()
        val rings = 12
        val pts = (0..rings).map { Vec3(0f, height * it / rings, 0f) }
        tube(beam, pts, radius, floatArrayOf(1f, 1f, 1f, 0.5f), sides = 12) { i -> (1f - i.toFloat() / rings).let { it * it } }
        val pool = MeshData()
        val centre = pool.vertex(Vec3(0f, 0.08f, 0f), Vec3.UP, floatArrayOf(1f, 1f, 1f, 0.7f))
        val ring = 24
        for (i in 0 until ring) {
            val a = 2 * PI * i / ring
            pool.vertex(Vec3(radius * 5 * cos(a).toFloat(), 0.08f, radius * 5 * sin(a).toFloat()), Vec3.UP, floatArrayOf(1f, 1f, 1f, 0f))
        }
        for (i in 0 until ring) pool.triangle(centre, centre + 1 + (i + 1) % ring, centre + 1 + i)
        return listOf(
            Part("beacon.beam", beam, Surface.ADD, tint = colour, group = "beacon", emissive = 1.8f),
            Part("beacon.pool", pool, Surface.ADD, tint = colour, group = "beacon", emissive = 1.6f),
        )
    }

    fun ball(mode: Mode): Part {
        val mesh = MeshData()
        val r = Look.ballRadius(mode)
        val col = SceneMath.linearRgba("#7A3E17")
        val rings = 10
        val slices = 16
        for (i in 0..rings) {
            val phi = -PI / 2 + PI * i / rings
            for (j in 0..slices) {
                val theta = 2 * PI * j / slices
                val n = Vec3((cos(phi) * cos(theta)).toFloat(), sin(phi).toFloat(), (cos(phi) * sin(theta)).toFloat())
                mesh.vertex(Vec3(n.x * r * 1.6f, n.y * r, n.z * r), n, col)
            }
        }
        val cols = slices + 1
        for (i in 0 until rings) for (j in 0 until slices) {
            val a = i * cols + j
            mesh.triangle(a, a + 1, a + cols)
            mesh.triangle(a + 1, a + cols + 1, a + cols)
        }
        return Part("ball", mesh, Surface.LIT, group = "ball", roughness = 0.6f)
    }

    fun horizon(spec: SceneSpec, mode: Mode): List<Part> {
        val pts = SceneMath.horizon(spec.winProbability)
        if (pts.size < 2) return emptyList()
        val h = spec.winProbability.horizon
        val thin = Look.horizonThickness(mode)
        val rails = MeshData()
        for (y in doubleArrayOf(h.y0, h.y1)) {
            tube(rails, listOf(SceneMath.local(h.x0, y, h.z), SceneMath.local(h.x1, y, h.z)), thin, floatArrayOf(1f, 1f, 1f, 0.18f), sides = 6)
        }
        tube(rails, listOf(SceneMath.local(h.x0, (h.y0 + h.y1) / 2, h.z), SceneMath.local(h.x1, (h.y0 + h.y1) / 2, h.z)), thin * 0.7f, floatArrayOf(1f, 1f, 1f, 0.3f), sides = 6)
        val line = MeshData()
        tube(line, pts, thin * 2.2f, floatArrayOf(1f, 1f, 1f, 1f), sides = 6)
        return listOf(
            Part("horizon.rails", rails, Surface.ADD, tint = SceneMath.linearRgba("#FFFFFF"), group = "horizon"),
            Part("horizon.line", line, Surface.GLOW, tint = SceneMath.linearRgba(spec.color("ink", "#F7F6F2")), group = "horizon", emissive = 1.6f),
        )
    }
}
