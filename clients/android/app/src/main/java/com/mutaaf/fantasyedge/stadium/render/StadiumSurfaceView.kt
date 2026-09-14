package com.mutaaf.fantasyedge.stadium.render

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.view.Choreographer
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.Surface
import android.view.SurfaceView
import android.view.WindowManager
import com.google.android.filament.Filament
import com.mutaaf.fantasyedge.stadium.geometry.Mode
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import kotlin.math.PI

/**
 * The 3D surface: a SurfaceView that owns a Filament [Stage], one renderer for
 * the current mode, the camera rig, touch and the gyroscope.
 *
 * Compose hands it scenes; everything here runs on the main thread, where
 * Filament's single-threaded API is safe to call.
 */
@SuppressLint("ViewConstructor")
class StadiumSurfaceView(context: Context) : SurfaceView(context), Choreographer.FrameCallback, SensorEventListener {

    private var stage: Stage? = null
    private var renderer: StadiumRenderer? = null
    private val rig = CameraRig()
    private var pending: SceneSpec? = null
    private var reduceMotion = false
    private var mode = Mode.TABLETOP
    private var lastFrame = 0L
    private var running = false
    private val sensors = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private var gyroBase: FloatArray? = null
    private var gyroRotation = -1

    private val scaler = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            rig.pinch(detector.scaleFactor)
            return true
        }
    })
    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent) = true
        override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean {
            if (!scaler.isInProgress) rig.drag(dx, dy, height)
            return true
        }
        override fun onDoubleTap(e: MotionEvent): Boolean {
            rig.reset(renderer?.spec)
            gyroBase = null
            return true
        }
    })

    init {
        Filament.init()
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaler.onTouchEvent(event)
        gestures.onTouchEvent(event)
        return true
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        stage = Stage(this).also { s ->
            renderer = StadiumRenderer(s, mode)
            pending?.let { renderer?.apply(it, reduceMotion) }
        }
        rig.mode = mode
        rig.reset(pending)
        start()
    }

    override fun onDetachedFromWindow() {
        stop()
        renderer?.destroy()
        renderer = null
        stage?.destroy()
        stage = null
        super.onDetachedFromWindow()
    }

    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        if (visibility == VISIBLE) start() else stop()
    }

    private fun start() {
        if (running || stage == null) return
        running = true
        lastFrame = 0L
        Choreographer.getInstance().postFrameCallback(this)
        if (mode == Mode.STADIUM) listenToGyro(true)
    }

    private fun stop() {
        if (!running) return
        running = false
        Choreographer.getInstance().removeFrameCallback(this)
        listenToGyro(false)
    }

    fun show(spec: SceneSpec?, mode: Mode, reduceMotion: Boolean) {
        this.reduceMotion = reduceMotion
        if (mode != this.mode) {
            this.mode = mode
            rig.mode = mode
            rig.reset(spec ?: renderer?.spec)
            gyroBase = null
            stage?.let { s ->
                renderer?.destroy()
                renderer = StadiumRenderer(s, mode)
            }
            listenToGyro(running && mode == Mode.STADIUM)
        }
        if (spec != null) {
            if (pending == null) rig.reset(spec)
            pending = spec
            renderer?.apply(spec, reduceMotion)
        }
    }

    override fun doFrame(frameTimeNanos: Long) {
        if (!running) return
        Choreographer.getInstance().postFrameCallback(this)
        val s = stage ?: return
        val dt = if (lastFrame == 0L) 0.0 else ((frameTimeNanos - lastFrame) / 1e9).coerceIn(0.0, 0.1)
        lastFrame = frameTimeNanos
        renderer?.tick(dt)
        rig.apply(s.camera, renderer?.spec, s.width, s.height)
        s.render(frameTimeNanos)
    }

    // ───────────────────────── gyroscope ─────────────────────────

    private fun listenToGyro(on: Boolean) {
        val sensor = sensors.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR) ?: return
        if (on) {
            gyroBase = null
            sensors.registerListener(this, sensor, SensorManager.SENSOR_DELAY_GAME)
        } else {
            sensors.unregisterListener(this)
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (mode != Mode.STADIUM) return
        val rotation = FloatArray(9)
        SensorManager.getRotationMatrixFromVector(rotation, event.values)
        val remapped = FloatArray(9)
        @Suppress("DEPRECATION")
        val displayRotation = (context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.rotation
        val (ax, ay) = when (displayRotation) {
            Surface.ROTATION_90 -> SensorManager.AXIS_Y to SensorManager.AXIS_MINUS_X
            Surface.ROTATION_180 -> SensorManager.AXIS_MINUS_X to SensorManager.AXIS_MINUS_Y
            Surface.ROTATION_270 -> SensorManager.AXIS_MINUS_Y to SensorManager.AXIS_X
            else -> SensorManager.AXIS_X to SensorManager.AXIS_Y
        }
        if (displayRotation != gyroRotation) {
            gyroRotation = displayRotation
            gyroBase = null
        }
        SensorManager.remapCoordinateSystem(rotation, ax, ay, remapped)
        val angles = FloatArray(3)
        SensorManager.getOrientation(remapped, angles)
        val base = gyroBase ?: angles.copyOf().also { gyroBase = it }
        rig.gyroYaw = wrap(-(angles[0] - base[0]).toDouble())
        rig.gyroPitch = (-(angles[1] - base[1]).toDouble()).coerceIn(-1.0, 1.0)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    private fun wrap(a: Double): Double {
        var v = a
        while (v > PI) v -= 2 * PI
        while (v < -PI) v += 2 * PI
        return v
    }
}
