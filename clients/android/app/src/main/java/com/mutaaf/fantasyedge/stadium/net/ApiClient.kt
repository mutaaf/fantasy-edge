package com.mutaaf.fantasyedge.stadium.net

import com.mutaaf.fantasyedge.stadium.scene.ReplayState
import com.mutaaf.fantasyedge.stadium.scene.SceneDecoder
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class ApiException(message: String) : IOException(message)

/**
 * The only network code in the app: GET a scene, drive a replay. No game
 * logic lives here or anywhere else on the device.
 */
class ApiClient(private val base: () -> String) {

    sealed interface Target {
        data class Live(val event: String) : Target
        data object Replay : Target
    }

    suspend fun scene(target: Target): SceneSpec = withContext(Dispatchers.IO) {
        val path = when (target) {
            is Target.Live -> "/api/scene/${target.event}"
            Target.Replay -> "/api/replay/scene"
        }
        SceneDecoder.decode(request("GET", path, null))
    }

    suspend fun replay(): ReplayState = withContext(Dispatchers.IO) {
        SceneDecoder.decodeReplay(request("GET", "/api/replay", null))
    }

    suspend fun control(body: JsonObject): ReplayState = withContext(Dispatchers.IO) {
        SceneDecoder.decodeReplay(request("POST", "/api/replay", body.toString()))
    }

    private fun request(method: String, path: String, body: String?): String {
        val root = base().trimEnd('/')
        val connection = try {
            URL(root + path).openConnection() as HttpURLConnection
        } catch (e: Exception) {
            throw ApiException("\"$root\" is not an API address.")
        }
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 4000
            connection.readTimeout = 8000
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toByteArray()) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) throw ApiException(failure(text) ?: "The API answered $code for $path.")
            text
        } catch (e: ApiException) {
            throw e
        } catch (e: IOException) {
            throw ApiException("Can't reach the API at $root. Start it with `python3 -m fantasyedge api --port 8794`.")
        } finally {
            connection.disconnect()
        }
    }

    /** The API's own error sentence and fix, when it sent one. */
    private fun failure(text: String): String? = try {
        val o = Json.parseToJsonElement(text).jsonObject
        listOfNotNull(o["error"]?.jsonPrimitive?.contentOrNull, o["fix"]?.jsonPrimitive?.contentOrNull)
            .joinToString(" ").ifBlank { null }
    } catch (e: Exception) {
        null
    }
}
