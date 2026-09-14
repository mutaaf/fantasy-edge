package com.mutaaf.fantasyedge.stadium.ui

import android.app.Application
import android.provider.Settings
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mutaaf.fantasyedge.stadium.BuildConfig
import com.mutaaf.fantasyedge.stadium.geometry.Mode
import com.mutaaf.fantasyedge.stadium.net.ApiClient
import com.mutaaf.fantasyedge.stadium.scene.DesignTokens
import com.mutaaf.fantasyedge.stadium.scene.ReplayState
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

data class UiState(
    val spec: SceneSpec? = null,
    val replay: ReplayState? = null,
    val games: List<ReplayState.Game> = emptyList(),
    val error: String? = null,
    val mode: Mode = Mode.TABLETOP,
    val baseUrl: String = BuildConfig.DEFAULT_API,
    val liveEvent: String? = null,
    val busy: Boolean = false,
)

/**
 * Polls the scene and drives the replay remote. Holds no football: the scene
 * arrives decided, and the only thing this chooses is how often to ask.
 */
class StadiumViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("stadium", 0)
    private val _state = MutableStateFlow(
        UiState(
            baseUrl = prefs.getString("baseUrl", null) ?: BuildConfig.DEFAULT_API,
            mode = runCatching { Mode.valueOf(prefs.getString("mode", "TABLETOP")!!) }.getOrDefault(Mode.TABLETOP),
        )
    )
    val state: StateFlow<UiState> = _state.asStateFlow()
    private val api = ApiClient { _state.value.baseUrl }
    private var poll: Job? = null

    val tokens: DesignTokens = DesignTokens.parse(app.assets.open("tokens.json").bufferedReader().use { it.readText() })

    val reduceMotion: Boolean
        get() = Settings.Global.getFloat(getApplication<Application>().contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f

    init {
        start()
        refreshGames()
    }

    private val target: ApiClient.Target
        get() = _state.value.liveEvent?.let { ApiClient.Target.Live(it) } ?: ApiClient.Target.Replay

    fun start() {
        poll?.cancel()
        poll = viewModelScope.launch {
            while (isActive) {
                refresh()
                // A replay moves at up to 300x; a live scene changes a few times a minute.
                delay(if (target == ApiClient.Target.Replay) 700 else 3000)
            }
        }
    }

    private suspend fun refresh() {
        try {
            val spec = api.scene(target)
            _state.update { it.copy(spec = spec, replay = spec.replayControl ?: it.replay, error = null) }
        } catch (e: Exception) {
            _state.update { it.copy(error = e.message ?: "The scene could not be loaded.") }
        }
    }

    fun refreshGames() = viewModelScope.launch {
        try {
            val r = api.replay()
            _state.update { it.copy(games = r.games.orEmpty(), replay = r) }
        } catch (_: Exception) {
            // The poll reports reachability; the catalogue just stays as it was.
        }
    }

    fun setMode(mode: Mode) {
        prefs.edit().putString("mode", mode.name).apply()
        _state.update { it.copy(mode = mode) }
    }

    fun setBaseUrl(url: String) {
        prefs.edit().putString("baseUrl", url.trim()).apply()
        _state.update { it.copy(baseUrl = url.trim(), spec = null, error = null) }
        start()
        refreshGames()
    }

    fun load(event: String) = control { put("action", "load"); put("event", event) }
    fun play() = control { put("action", "play") }
    fun pause() = control { put("action", "pause") }
    fun seek(seconds: Int) = control { put("action", "seek"); put("at", seconds) }
    fun speed(speed: Double) = control { put("action", "speed"); put("speed", speed) }

    private fun control(body: kotlinx.serialization.json.JsonObjectBuilder.() -> Unit) = viewModelScope.launch {
        _state.update { it.copy(busy = true) }
        try {
            val r = api.control(buildJsonObject(body))
            _state.update { it.copy(replay = r, games = r.games ?: it.games, error = null, liveEvent = null) }
            refresh()
        } catch (e: Exception) {
            _state.update { it.copy(error = e.message) }
        } finally {
            _state.update { it.copy(busy = false) }
        }
    }
}
