package com.mutaaf.fantasyedge.stadium.render

import com.google.android.filament.Engine
import com.google.android.filament.Material
import com.google.android.filament.filamat.MaterialBuilder
import com.mutaaf.fantasyedge.stadium.geometry.Surface

/**
 * The four materials every part of the stadium is drawn with, compiled once at
 * start-up from source so the build needs no offline material compiler.
 *
 * Each takes vertex colour times a `tint` parameter. That is the whole trick
 * behind the touchdown: a crowd section's people are white vertices and their
 * club colour is the tint, so lighting a section is one parameter change.
 */
class Materials(engine: Engine, private val cache: java.io.File? = null) {
    private val materials: Map<Surface, Material>
    private var builderReady = false

    init {
        try {
            materials = mapOf(
                Surface.LIT to build(engine, "lit") {
                    shading(MaterialBuilder.Shading.LIT)
                        .uniformParameter(MaterialBuilder.UniformType.FLOAT, "roughness")
                        .doubleSided(true)
                        .material(
                            """
                            void material(inout MaterialInputs material) {
                                prepareMaterial(material);
                                vec4 c = getColor() * materialParams.tint;
                                material.baseColor = vec4(c.rgb, 1.0);
                                material.roughness = materialParams.roughness;
                                material.metallic = 0.0;
                                material.reflectance = 0.35;
                            }
                            """.trimIndent()
                        )
                },
                Surface.GLOW to build(engine, "glow") {
                    shading(MaterialBuilder.Shading.UNLIT)
                        .culling(MaterialBuilder.CullingMode.NONE)
                        .material(
                            """
                            void material(inout MaterialInputs material) {
                                prepareMaterial(material);
                                vec4 c = getColor() * materialParams.tint;
                                material.baseColor = vec4(c.rgb * materialParams.emissive, 1.0);
                            }
                            """.trimIndent()
                        )
                },
                Surface.SKY to build(engine, "sky") {
                    shading(MaterialBuilder.Shading.UNLIT)
                        .culling(MaterialBuilder.CullingMode.NONE)
                        .material(
                            """
                            void material(inout MaterialInputs material) {
                                prepareMaterial(material);
                                vec4 c = getColor() * materialParams.tint;
                                material.baseColor = vec4(c.rgb * materialParams.emissive, 1.0);
                            }
                            """.trimIndent()
                        )
                },
                Surface.ADD to build(engine, "add") {
                    shading(MaterialBuilder.Shading.UNLIT)
                        .blending(MaterialBuilder.BlendingMode.ADD)
                        .depthWrite(false)
                        .culling(MaterialBuilder.CullingMode.NONE)
                        .material(
                            """
                            void material(inout MaterialInputs material) {
                                prepareMaterial(material);
                                vec4 c = getColor() * materialParams.tint;
                                material.baseColor = vec4(c.rgb * c.a * materialParams.emissive, c.a);
                            }
                            """.trimIndent()
                        )
                },
            )
        } finally {
            if (builderReady) MaterialBuilder.shutdown()
        }
    }

    private fun build(engine: Engine, name: String, configure: MaterialBuilder.() -> MaterialBuilder): Material {
        // Compiling a material takes seconds on a slow GPU driver and would hold
        // the first frame black, so the compiled package is kept on disk and
        // only rebuilt when VERSION changes.
        val cached = cache?.resolve("material-$name-$VERSION.filamat")
        if (cached != null && cached.exists() && cached.length() > 0) {
            val bytes = cached.readBytes()
            val stored = java.nio.ByteBuffer.allocateDirect(bytes.size).order(java.nio.ByteOrder.nativeOrder())
            stored.put(bytes)
            stored.flip()
            return Material.Builder().payload(stored, bytes.size).build(engine)
        }
        if (!builderReady) {
            MaterialBuilder.init()
            builderReady = true
        }
        val builder = MaterialBuilder()
            .name(name)
            .require(MaterialBuilder.VertexAttribute.COLOR)
            .uniformParameter(MaterialBuilder.UniformType.FLOAT4, "tint")
            .uniformParameter(MaterialBuilder.UniformType.FLOAT, "emissive")
            .platform(MaterialBuilder.Platform.MOBILE)
            .targetApi(MaterialBuilder.TargetApi.OPENGL)
            .optimization(MaterialBuilder.Optimization.PERFORMANCE)
            .configure()
        val pkg = builder.build()
        check(pkg.isValid) { "material $name failed to compile" }
        val buffer = pkg.buffer
        if (cached != null) {
            val bytes = ByteArray(buffer.remaining())
            buffer.duplicate().get(bytes)
            runCatching {
                cached.parentFile?.mkdirs()
                cached.writeBytes(bytes)
            }
        }
        return Material.Builder().payload(buffer, buffer.remaining()).build(engine)
    }

    operator fun get(surface: Surface): Material = materials.getValue(surface)

    companion object {
        /** Bump when a shader or material setting in this file changes, so a stale cache is ignored. */
        const val VERSION = 1
    }

    fun destroy(engine: Engine) = materials.values.forEach { engine.destroyMaterial(it) }
}
