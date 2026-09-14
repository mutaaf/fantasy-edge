package com.mutaaf.fantasyedge.stadium.render

import android.view.Surface
import android.view.SurfaceView
import com.google.android.filament.Box
import com.google.android.filament.Camera
import com.google.android.filament.ColorGrading
import com.google.android.filament.Engine
import com.google.android.filament.EntityManager
import com.google.android.filament.IndexBuffer
import com.google.android.filament.IndirectLight
import com.google.android.filament.LightManager
import com.google.android.filament.MaterialInstance
import com.google.android.filament.RenderableManager
import com.google.android.filament.Renderer
import com.google.android.filament.Scene
import com.google.android.filament.SurfaceOrientation
import com.google.android.filament.SwapChain
import com.google.android.filament.ToneMapper
import com.google.android.filament.VertexBuffer
import com.google.android.filament.View
import com.google.android.filament.Viewport
import com.google.android.filament.android.UiHelper
import com.mutaaf.fantasyedge.stadium.geometry.Part
import com.mutaaf.fantasyedge.stadium.geometry.Surface as PartSurface
import com.mutaaf.fantasyedge.stadium.scene.Vec3
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.IntBuffer

/** One part on the GPU: its entity, buffers and material instance. */
class Drawable(
    val part: Part,
    val entity: Int,
    private val vertices: VertexBuffer,
    private val indices: IndexBuffer,
    val instance: MaterialInstance,
) {
    fun tint(r: Float, g: Float, b: Float, a: Float) = instance.setParameter("tint", r, g, b, a)

    internal fun destroy(engine: Engine) {
        engine.destroyEntity(entity)
        engine.destroyVertexBuffer(vertices)
        engine.destroyIndexBuffer(indices)
        engine.destroyMaterialInstance(instance)
        EntityManager.get().destroy(entity)
    }
}

/**
 * The Filament plumbing: engine, view, camera, swap chain, lights, and turning
 * a [Part] into something drawn. It knows nothing about football.
 *
 * Night lighting is image-based rather than flat: a spherical-harmonics sky
 * gives the stands a cool ambient, the rim banks are real spot lights on the
 * turf, and bloom turns anything emissive - lamps, arcs, lasers, the beacon -
 * into light rather than paint.
 */
class Stage(private val surfaceView: SurfaceView) {
    val engine: Engine = Engine.create()
    val scene: Scene = engine.createScene()
    val view: View = engine.createView()
    private val renderer: Renderer = engine.createRenderer()
    private val cameraEntity = EntityManager.get().create()
    val camera: Camera = engine.createCamera(cameraEntity)
    private val materials = Materials(engine, surfaceView.context.cacheDir)
    private val uiHelper = UiHelper(UiHelper.ContextErrorPolicy.DONT_CHECK)
    private var swapChain: SwapChain? = null
    private val lights = mutableListOf<Int>()
    private var indirect: IndirectLight? = null
    private val colorGrading: ColorGrading
    var width = 1
        private set
    var height = 1
        private set
    var onResize: ((Int, Int) -> Unit)? = null

    init {
        view.scene = scene
        view.camera = camera
        camera.setExposure(1.0f)
        colorGrading = ColorGrading.Builder().toneMapper(ToneMapper.Filmic()).build(engine)
        view.colorGrading = colorGrading
        view.antiAliasing = View.AntiAliasing.FXAA
        view.multiSampleAntiAliasingOptions = View.MultiSampleAntiAliasingOptions().apply {
            enabled = true
            sampleCount = 4
        }
        view.bloomOptions = View.BloomOptions().apply {
            enabled = true
            strength = 0.22f
            resolution = 384
            threshold = true
            highlight = 1000f
        }
        view.fogOptions = View.FogOptions().apply {
            enabled = true
            distance = 70f
            density = 0.0035f
            maximumOpacity = 0.55f
            height = 0f
            heightFalloff = 0.012f
            color = floatArrayOf(0.035f, 0.05f, 0.09f)
            inScatteringStart = 0f
            inScatteringSize = -1f
        }
        renderer.clearOptions = Renderer.ClearOptions().apply { clear = true }

        indirect = IndirectLight.Builder()
            // A night sky: a cool, dim ambient that is brighter overhead than at the horizon.
            .irradiance(3, floatArrayOf(
                0.55f, 0.60f, 0.78f,
                0.16f, 0.18f, 0.26f,
                0.00f, 0.00f, 0.00f,
                0.00f, 0.00f, 0.00f,
                0.00f, 0.00f, 0.00f,
                0.00f, 0.00f, 0.00f,
                0.00f, 0.00f, 0.00f,
                0.00f, 0.00f, 0.00f,
                0.00f, 0.00f, 0.00f,
            ))
            .intensity(1.0f)
            .build(engine)
        scene.indirectLight = indirect

        uiHelper.renderCallback = object : UiHelper.RendererCallback {
            override fun onNativeWindowChanged(surface: Surface) {
                swapChain?.let { engine.destroySwapChain(it) }
                swapChain = engine.createSwapChain(surface, uiHelper.swapChainFlags)
            }

            override fun onDetachedFromSurface() {
                swapChain?.let {
                    engine.destroySwapChain(it)
                    engine.flushAndWait()
                    swapChain = null
                }
            }

            override fun onResized(width: Int, height: Int) {
                this@Stage.width = maxOf(1, width)
                this@Stage.height = maxOf(1, height)
                view.viewport = Viewport(0, 0, this@Stage.width, this@Stage.height)
                onResize?.invoke(this@Stage.width, this@Stage.height)
            }
        }
        uiHelper.attachTo(surfaceView)
    }

    fun render(frameTimeNanos: Long) {
        val chain = swapChain ?: return
        if (!uiHelper.isReadyToRender) return
        if (renderer.beginFrame(chain, frameTimeNanos)) {
            renderer.render(view)
            renderer.endFrame()
        }
    }

    fun add(part: Part): Drawable {
        val mesh = part.mesh
        val n = mesh.vertexCount
        val positions = floatBuffer(mesh.positions)
        val normals = floatBuffer(mesh.normals)
        val colors = floatBuffer(mesh.colors)
        val triangles = intBuffer(mesh.indices)
        val tangents = floatBuffer(FloatArray(n * 4))
        val orientation = SurfaceOrientation.Builder()
            .vertexCount(n)
            .normals(normals)
            .build()
        orientation.getQuatsAsFloat(tangents)
        orientation.destroy()
        tangents.rewind()

        val vb = VertexBuffer.Builder()
            .bufferCount(3)
            .vertexCount(n)
            .attribute(VertexBuffer.VertexAttribute.POSITION, 0, VertexBuffer.AttributeType.FLOAT3, 0, 12)
            .attribute(VertexBuffer.VertexAttribute.TANGENTS, 1, VertexBuffer.AttributeType.FLOAT4, 0, 16)
            .attribute(VertexBuffer.VertexAttribute.COLOR, 2, VertexBuffer.AttributeType.FLOAT4, 0, 16)
            .build(engine)
        vb.setBufferAt(engine, 0, positions)
        vb.setBufferAt(engine, 1, tangents)
        vb.setBufferAt(engine, 2, colors)
        val ib = IndexBuffer.Builder()
            .indexCount(mesh.indexCount)
            .bufferType(IndexBuffer.Builder.IndexType.UINT)
            .build(engine)
        ib.setBuffer(engine, triangles)

        val instance = materials[part.surface].createInstance()
        instance.setParameter("tint", part.tint[0], part.tint[1], part.tint[2], part.tint[3])
        instance.setParameter("emissive", part.emissive)
        if (part.surface == PartSurface.LIT) instance.setParameter("roughness", part.roughness)

        val b = mesh.bounds()
        val entity = EntityManager.get().create()
        RenderableManager.Builder(1)
            .boundingBox(Box(
                (b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2,
                maxOf(0.01f, (b[3] - b[0]) / 2), maxOf(0.01f, (b[4] - b[1]) / 2), maxOf(0.01f, (b[5] - b[2]) / 2),
            ))
            .geometry(0, RenderableManager.PrimitiveType.TRIANGLES, vb, ib)
            .material(0, instance)
            .culling(part.surface != PartSurface.SKY)
            .fog(part.surface == PartSurface.LIT)
            .castShadows(false)
            .receiveShadows(false)
            .priority(if (part.surface == PartSurface.SKY) 0 else 4)
            .build(engine, entity)
        engine.transformManager.create(entity)
        scene.addEntity(entity)
        return Drawable(part, entity, vb, ib, instance)
    }

    fun remove(d: Drawable) {
        scene.removeEntity(d.entity)
        d.destroy(engine)
    }

    fun translate(d: Drawable, at: Vec3) {
        val tm = engine.transformManager
        tm.setTransform(tm.getInstance(d.entity), floatArrayOf(
            1f, 0f, 0f, 0f,
            0f, 1f, 0f, 0f,
            0f, 0f, 1f, 0f,
            at.x, at.y, at.z, 1f,
        ))
    }

    /** A floodlight aimed at `target`, in yards; the renderer places one per rim bank. */
    fun spotLight(position: Vec3, target: Vec3, color: FloatArray, candela: Float) {
        val entity = EntityManager.get().create()
        val dir = (target - position).normalized()
        LightManager.Builder(LightManager.Type.FOCUSED_SPOT)
            .position(position.x, position.y, position.z)
            .direction(dir.x, dir.y, dir.z)
            .color(color[0], color[1], color[2])
            .intensityCandela(candela)
            .spotLightCone(0.35f, 0.95f)
            .falloff(420f)
            .castShadows(false)
            .build(engine, entity)
        scene.addEntity(entity)
        lights += entity
    }

    fun clearLights() {
        lights.forEach {
            scene.removeEntity(it)
            engine.lightManager.destroy(it)
            EntityManager.get().destroy(it)
        }
        lights.clear()
    }

    fun destroy() {
        clearLights()
        uiHelper.detach()
        swapChain?.let { engine.destroySwapChain(it) }
        indirect?.let { engine.destroyIndirectLight(it) }
        engine.destroyColorGrading(colorGrading)
        materials.destroy(engine)
        engine.destroyRenderer(renderer)
        engine.destroyView(view)
        engine.destroyScene(scene)
        engine.destroyCameraComponent(cameraEntity)
        EntityManager.get().destroy(cameraEntity)
        engine.destroy()
    }

    private fun floatBuffer(a: FloatArray): FloatBuffer =
        ByteBuffer.allocateDirect(a.size * 4).order(ByteOrder.nativeOrder()).asFloatBuffer().apply {
            put(a)
            flip()
        }

    private fun intBuffer(a: IntArray): IntBuffer =
        ByteBuffer.allocateDirect(a.size * 4).order(ByteOrder.nativeOrder()).asIntBuffer().apply {
            put(a)
            flip()
        }
}
