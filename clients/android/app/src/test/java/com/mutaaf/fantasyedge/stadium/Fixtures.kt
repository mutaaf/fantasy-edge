package com.mutaaf.fantasyedge.stadium

import com.mutaaf.fantasyedge.stadium.scene.SceneDecoder
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import java.io.File

/** Scenes recorded from the real API by scripts/record_fixtures.py. Never edited by hand. */
object Fixtures {
    private fun resource(name: String): String =
        requireNotNull(javaClass.classLoader?.getResource(name)) { "missing test resource $name; run scripts/record_fixtures.py" }
            .readText()

    fun text(name: String): String = resource("scenes/$name.json")

    fun scene(name: String): SceneSpec = SceneDecoder.decode(text(name))

    val names: List<String> by lazy {
        val dir = File(requireNotNull(javaClass.classLoader?.getResource("scenes")).toURI())
        dir.listFiles { f -> f.extension == "json" }!!.map { it.nameWithoutExtension }.sorted()
    }

    fun replayState(): String = resource("replay_state.json")

    /** The Bears' pick-six, mid-celebration. */
    const val PICK_SIX = "401772810-1929"
    /** Seattle and the Rams in overtime. */
    const val OVERTIME = "401772949-3900"
    const val KICKOFF = "401772510-0"
}
