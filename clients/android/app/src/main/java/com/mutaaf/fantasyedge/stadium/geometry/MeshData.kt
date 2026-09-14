package com.mutaaf.fantasyedge.stadium.geometry

import com.mutaaf.fantasyedge.stadium.scene.Vec3

/** How a part is shaded. The renderer maps each to one Filament material. */
enum class Surface {
    /** Physically lit by the rim lights and the night sky: turf, stands, crowd, ball. */
    LIT,
    /** Emits its own colour, bright enough to bloom: arcs, lasers, lamps. */
    GLOW,
    /** Unlit and fogless, drawn behind everything: the sky. */
    SKY,
    /** Additive light: halos, beams, glows. Never writes depth. */
    ADD,
}

/**
 * Plain vertex data with no rendering API in it, so geometry can be built and
 * counted on the JVM. Colours are linear RGBA; normals are unit vectors.
 */
class MeshData {
    private var capacity = 128
    private var pos = FloatArray(capacity * 3)
    private var nrm = FloatArray(capacity * 3)
    private var col = FloatArray(capacity * 4)
    private var idx = IntArray(384)
    var vertexCount = 0
        private set
    var indexCount = 0
        private set

    val positions: FloatArray get() = pos.copyOf(vertexCount * 3)
    val normals: FloatArray get() = nrm.copyOf(vertexCount * 3)
    val colors: FloatArray get() = col.copyOf(vertexCount * 4)
    val indices: IntArray get() = idx.copyOf(indexCount)
    val isEmpty: Boolean get() = vertexCount == 0 || indexCount == 0

    fun vertex(p: Vec3, n: Vec3, c: FloatArray): Int {
        if (vertexCount == capacity) {
            capacity *= 2
            pos = pos.copyOf(capacity * 3)
            nrm = nrm.copyOf(capacity * 3)
            col = col.copyOf(capacity * 4)
        }
        val i3 = vertexCount * 3
        pos[i3] = p.x; pos[i3 + 1] = p.y; pos[i3 + 2] = p.z
        nrm[i3] = n.x; nrm[i3 + 1] = n.y; nrm[i3 + 2] = n.z
        val i4 = vertexCount * 4
        col[i4] = c[0]; col[i4 + 1] = c[1]; col[i4 + 2] = c[2]; col[i4 + 3] = c[3]
        return vertexCount++
    }

    fun triangle(a: Int, b: Int, c: Int) {
        if (indexCount + 3 > idx.size) idx = idx.copyOf(idx.size * 2)
        idx[indexCount++] = a; idx[indexCount++] = b; idx[indexCount++] = c
    }

    /** A quad from four corners in winding order, one flat normal. */
    fun quad(a: Vec3, b: Vec3, c: Vec3, d: Vec3, color: FloatArray, normal: Vec3? = null) {
        val n = normal ?: (b - a).cross(d - a).normalized()
        val i0 = vertex(a, n, color)
        val i1 = vertex(b, n, color)
        val i2 = vertex(c, n, color)
        val i3 = vertex(d, n, color)
        triangle(i0, i1, i2)
        triangle(i0, i2, i3)
    }

    /** Axis-aligned bounds as [minX, minY, minZ, maxX, maxY, maxZ]. */
    fun bounds(): FloatArray {
        if (vertexCount == 0) return floatArrayOf(0f, 0f, 0f, 0f, 0f, 0f)
        val b = floatArrayOf(Float.MAX_VALUE, Float.MAX_VALUE, Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE)
        for (i in 0 until vertexCount) {
            for (k in 0..2) {
                val v = pos[i * 3 + k]
                if (v < b[k]) b[k] = v
                if (v > b[k + 3]) b[k + 3] = v
            }
        }
        return b
    }
}

/**
 * One drawable piece of the scene. `group` names what the renderer may change
 * later without rebuilding the mesh: a crowd section's tint, a laser's
 * position. `tint` is the colour a white-vertex part is multiplied by.
 */
data class Part(
    val name: String,
    val mesh: MeshData,
    val surface: Surface,
    val tint: FloatArray = floatArrayOf(1f, 1f, 1f, 1f),
    val group: String = "",
    val roughness: Float = 0.9f,
    val emissive: Float = 1f,
)
