package com.mutaaf.fantasyedge.stadium.render

import com.google.android.filament.Camera
import com.mutaaf.fantasyedge.stadium.geometry.Mode
import com.mutaaf.fantasyedge.stadium.geometry.StadiumGeometry
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import kotlin.math.PI
import kotlin.math.atan
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.tan

/**
 * Where the eye is. Tabletop is an orbit around the bowl; Stadium is a seat.
 *
 * The seat comes from the scene (`presentation.stadium.seat`, in yards) plus a
 * seated eye height. Look-around there is drag plus the phone's own rotation,
 * so turning the device turns your head in the stands.
 */
class CameraRig {
    var mode: Mode = Mode.TABLETOP

    // Tabletop orbit.
    var azimuth = 0.0
    var elevation = 0.62
    var zoom = 1.0

    // Stadium look.
    var yaw = 0.0
    var pitch = 0.0
    var gyroYaw = 0.0
    var gyroPitch = 0.0
    private var seatedPitch = 0.0

    /** A seated eye above the seat's step, about 1.2 m. */
    private val eyeAboveSeat = 1.3

    fun reset(spec: SceneSpec?) {
        azimuth = 0.0
        elevation = 0.62
        zoom = 1.0
        yaw = 0.0
        gyroYaw = 0.0
        gyroPitch = 0.0
        spec?.let {
            val seat = it.presentation.stadium.seat
            // Aim past midfield toward the far hash, so the stands and sky are in view too.
            seatedPitch = atan2(-(seat.y + eyeAboveSeat), seat.z + 18)
        }
        pitch = 0.0
    }

    fun drag(dx: Float, dy: Float, viewHeight: Int) {
        val per = PI / maxOf(1, viewHeight)
        when (mode) {
            Mode.TABLETOP -> {
                azimuth -= dx * per * 1.2
                elevation = (elevation + dy * per * 0.8).coerceIn(0.12, 1.45)
            }
            Mode.STADIUM -> {
                yaw -= dx * per * 0.9
                pitch = (pitch + dy * per * 0.6).coerceIn(-0.9, 0.9)
            }
        }
    }

    fun pinch(scale: Float) {
        if (mode == Mode.TABLETOP) zoom = (zoom / scale).coerceIn(0.45, 2.2)
    }

    fun apply(camera: Camera, spec: SceneSpec?, width: Int, height: Int) {
        val aspect = width.toDouble() / maxOf(1, height)
        when (mode) {
            Mode.TABLETOP -> {
                val tiers = spec?.let { StadiumGeometry.tiersFor(it, Mode.TABLETOP) }.orEmpty()
                val reach = (spec?.bowl?.shape?.halfLength ?: 60.0) + (tiers.lastOrNull()?.outer ?: 36.0) + 8
                val vfov = 38.0
                val hHalf = atan(tan(vfov / 2 * PI / 180) * aspect)
                // Fit the whole bowl across the narrower of the two spans.
                val fit = maxOf(reach / tan(hHalf), reach * 0.62 / tan(vfov / 2 * PI / 180))
                val d = fit * zoom
                val tx = 0.0
                val ty = 4.0
                val tz = 0.0
                val ex = tx + d * cos(elevation) * sin(azimuth)
                val ey = ty + d * sin(elevation)
                val ez = tz + d * cos(elevation) * cos(azimuth)
                camera.setProjection(vfov, aspect, 1.0, 4000.0, Camera.Fov.VERTICAL)
                camera.lookAt(ex, ey, ez, tx, ty, tz, 0.0, 1.0, 0.0)
            }
            Mode.STADIUM -> {
                val seat = spec?.presentation?.stadium?.seat
                val ex = (seat?.x ?: 50.0) - 50
                val ey = (seat?.y ?: 8.0) + eyeAboveSeat
                val ez = seat?.z ?: 42.7
                val y = yaw + gyroYaw
                val p = (seatedPitch + pitch + gyroPitch).coerceIn(-1.3, 1.3)
                val fx = sin(y) * cos(p)
                val fy = sin(p)
                val fz = -cos(y) * cos(p)
                // A wide seat's-eye view: 92 degrees across in landscape, 84 up-and-down in portrait.
                val vfov = if (aspect >= 1) 2 * atan(tan(92.0 / 2 * PI / 180) / aspect) * 180 / PI else 84.0
                camera.setProjection(vfov, aspect, 0.3, 2500.0, Camera.Fov.VERTICAL)
                camera.lookAt(ex, ey, ez, ex + fx, ey + fy, ez + fz, 0.0, 1.0, 0.0)
            }
        }
    }
}
