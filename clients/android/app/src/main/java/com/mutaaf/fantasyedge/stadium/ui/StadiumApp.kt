package com.mutaaf.fantasyedge.stadium.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.windowsizeclass.WindowSizeClass
import androidx.compose.material3.windowsizeclass.WindowWidthSizeClass
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.mutaaf.fantasyedge.stadium.geometry.Mode
import com.mutaaf.fantasyedge.stadium.render.StadiumSurfaceView
import com.mutaaf.fantasyedge.stadium.scene.DesignTokens
import com.mutaaf.fantasyedge.stadium.scene.ReplayState
import com.mutaaf.fantasyedge.stadium.scene.SceneSpec
import com.mutaaf.fantasyedge.stadium.scene.argbOf

private class Palette(t: DesignTokens) {
    val ink = Color(t.argb("ink", "#F7F6F2"))
    val inkSecondary = Color(t.argb("ink.secondary", "#F7F6F2BD"))
    val plate = Color(t.argb("plate", "#121417E0"))
    val live = Color(t.argb("fill.live", "#237A04"))
    val redZone = Color(t.argb("fill.redZone", "#DF0B0B"))
    val score = Color(t.argb("fill.score", "#8B7300"))
    val gold = Color(t.argb("laser.lineToGain", "#FFD400"))
}

@Composable
fun StadiumApp(model: StadiumViewModel, window: WindowSizeClass) {
    val state by model.state.collectAsStateWithLifecycle()
    val p = remember { Palette(model.tokens) }
    // A drive-log side panel needs a tablet: wide AND tall. A phone on its side is wide but short.
    val wide = window.widthSizeClass == WindowWidthSizeClass.Expanded &&
        window.heightSizeClass != androidx.compose.material3.windowsizeclass.WindowHeightSizeClass.Compact
    val short = window.heightSizeClass == androidx.compose.material3.windowsizeclass.WindowHeightSizeClass.Compact
    var showDrive by remember { mutableStateOf(false) }
    var showGames by remember { mutableStateOf(false) }
    var showSettings by remember { mutableStateOf(false) }

    MaterialTheme(colorScheme = darkColorScheme(primary = p.ink, background = Color.Black, surface = Color(0xFF121417))) {
        Row(Modifier.fillMaxSize().background(Color.Black)) {
            Box(Modifier.weight(1f).fillMaxHeight()) {
                AndroidView(
                    factory = { StadiumSurfaceView(it) },
                    update = { it.show(state.spec, state.mode, model.reduceMotion) },
                    modifier = Modifier.fillMaxSize().semantics { contentDescription = "Stadium" },
                )
                Overlay(state, p, wide, short, model,
                    onDrive = { showDrive = true }, onGames = { showGames = true; model.refreshGames() },
                    onSettings = { showSettings = true })
            }
            if (wide) {
                Column(
                    Modifier.width(380.dp).fillMaxHeight().background(Color(0xFF0C0D0F))
                        .windowInsetsPadding(WindowInsets.safeDrawing).padding(16.dp),
                ) {
                    DriveLog(state.spec, p, Modifier.weight(1f))
                    Spacer(Modifier.height(12.dp))
                    PlateButton("Games", p) { showGames = true; model.refreshGames() }
                }
            }
        }
        if (showDrive && !wide) {
            DriveSheet(state.spec, p) { showDrive = false }
        }
        if (showGames) {
            GamesSheet(state.games, state.replay?.event, p, onPick = { model.load(it); showGames = false }) { showGames = false }
        }
        if (showSettings) {
            SettingsDialog(state.baseUrl, onSave = { model.setBaseUrl(it); showSettings = false }) { showSettings = false }
        }
    }
}

@Composable
private fun BoxScope.Overlay(
    state: UiState, p: Palette, wide: Boolean, short: Boolean, model: StadiumViewModel,
    onDrive: () -> Unit, onGames: () -> Unit, onSettings: () -> Unit,
) {
    val spec = state.spec
    Column(
        Modifier.align(Alignment.TopCenter).fillMaxWidth().windowInsetsPadding(WindowInsets.safeDrawing).padding(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            ModeToggle(state.mode, p, model::setMode)
            Spacer(Modifier.weight(1f))
            if (short && spec != null) Scorebug(spec, p)
            Spacer(Modifier.weight(1f))
            PlateButton("⚙", p, description = "Settings", onClick = onSettings)
        }
        if (!short) {
            Spacer(Modifier.height(10.dp))
            if (spec != null) Scorebug(spec, p)
        }
        Spacer(Modifier.height(if (short) 6.dp else 10.dp))
        val moment = spec?.activeMoment?.takeIf { it.celebrates }
        AnimatedVisibility(
            visible = moment != null,
            enter = if (model.reduceMotion) EnterTransition.None else fadeIn() + scaleIn(initialScale = 1.08f),
            exit = if (model.reduceMotion) ExitTransition.None else fadeOut(),
        ) {
            if (moment != null) MomentBanner(moment, spec, p, compact = !wide, titleOnly = short)
        }
    }

    state.error?.let { err ->
        Column(
            Modifier.align(Alignment.Center).padding(24.dp).widthIn(max = 420.dp)
                .clip(RoundedCornerShape(24.dp)).background(p.plate).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(if (spec == null) "No scene yet" else "Scene is stale", color = p.ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text(err, color = p.inkSecondary, fontSize = 15.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PlateButton("Games", p, onClick = onGames)
                PlateButton("API address", p, onClick = onSettings)
            }
        }
    }

    Column(
        Modifier.align(Alignment.BottomCenter).fillMaxWidth()
            .windowInsetsPadding(WindowInsets.navigationBars).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (!wide) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PlateButton("This drive", p, onClick = onDrive)
                PlateButton("Games", p, onClick = onGames)
            }
        }
        state.replay?.takeIf { it.loaded }?.let { ReplayBar(it, p, model, short) }
    }
}

// ───────────────────────── pieces ─────────────────────────

@Composable
private fun TeamChip(team: SceneSpec.Team, height: Int = 36) {
    Box(
        Modifier.height(height.dp).widthIn(min = 58.dp).clip(RoundedCornerShape(8.dp))
            .background(Color(argbOf(team.chip))).padding(horizontal = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(team.abbr, color = Color(argbOf(team.chipText)), fontWeight = FontWeight.ExtraBold, fontSize = 17.sp, letterSpacing = 0.5.sp)
    }
}

private fun score(v: Double) = if (v % 1.0 == 0.0) v.toInt().toString() else v.toString()

@Composable
private fun Scorebug(spec: SceneSpec, p: Palette) {
    Row(
        Modifier.clip(RoundedCornerShape(26.dp)).background(p.plate)
            .border(1.dp, Color.White.copy(alpha = 0.14f), RoundedCornerShape(26.dp)).padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TeamChip(spec.teams.away)
        Text(score(spec.status.awayScore), color = p.ink, fontSize = 30.sp, fontWeight = FontWeight.Black)
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.widthIn(min = 96.dp)) {
            Text(spec.status.label.replace(" - ", " · ").ifBlank { spec.status.state.uppercase() }, color = p.ink, fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 1)
            if (spec.status.downDistance.isNotBlank()) {
                Text(spec.status.downDistance, color = p.inkSecondary, fontSize = 12.sp, maxLines = 1)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                if (spec.status.redZone) Badge("RED ZONE", p.redZone)
                if (spec.isReplay) Text("REPLAY · ${score(spec.speed)}×", color = p.inkSecondary, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        Text(score(spec.status.homeScore), color = p.ink, fontSize = 30.sp, fontWeight = FontWeight.Black)
        TeamChip(spec.teams.home)
    }
}

@Composable
private fun Badge(text: String, fill: Color) {
    Box(Modifier.clip(RoundedCornerShape(4.dp)).background(fill).padding(horizontal = 6.dp, vertical = 2.dp)) {
        Text(text, color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.8.sp)
    }
}

@Composable
private fun ModeToggle(mode: Mode, p: Palette, onPick: (Mode) -> Unit) {
    Row(Modifier.clip(RoundedCornerShape(28.dp)).background(p.plate).padding(4.dp)) {
        for ((m, label) in listOf(Mode.TABLETOP to "Tabletop", Mode.STADIUM to "Stadium")) {
            val on = m == mode
            Box(
                Modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(24.dp))
                    .background(if (on) p.ink else Color.Transparent)
                    .clickable { onPick(m) }.padding(horizontal = 18.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(label, color = if (on) Color(0xFF141619) else p.ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            }
        }
    }
}

@Composable
private fun PlateButton(label: String, p: Palette, description: String? = null, onClick: () -> Unit) {
    Box(
        Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp).clip(RoundedCornerShape(24.dp)).background(p.plate)
            .clickable(onClick = onClick).padding(horizontal = 16.dp)
            .semantics { description?.let { contentDescription = it } },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = p.ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
    }
}

@Composable
private fun MomentBanner(moment: SceneSpec.Moment, spec: SceneSpec, p: Palette, compact: Boolean, titleOnly: Boolean = false) {
    val title = when (moment.kind) {
        "touchdown" -> "TOUCHDOWN"
        "fieldGoal" -> "FIELD GOAL"
        "safety" -> "SAFETY"
        else -> "SCORE"
    }
    val team = spec.teams.side(moment.side)
    Column(
        Modifier.widthIn(max = 520.dp).clip(RoundedCornerShape(28.dp)).background(p.plate)
            .border(2.dp, p.gold.copy(alpha = 0.7f), RoundedCornerShape(28.dp)).padding(horizontal = 20.dp, vertical = if (compact) 10.dp else 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            team?.let { TeamChip(it, 40) }
            Text(title, color = Color(0xFFFFF3B0), fontSize = if (compact) 28.sp else 40.sp, fontWeight = FontWeight.Black,
                letterSpacing = 1.sp, maxLines = 1, softWrap = false)
        }
        if (!titleOnly) Text(moment.text, color = p.inkSecondary, fontSize = 13.sp, textAlign = TextAlign.Center, maxLines = if (compact) 2 else 3, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun PlayPauseGlyph(playing: Boolean, color: Color) {
    Canvas(Modifier.size(22.dp)) {
        if (playing) {
            val w = size.width * 0.28f
            drawRect(color, topLeft = Offset(size.width * 0.14f, 0f), size = androidx.compose.ui.geometry.Size(w, size.height))
            drawRect(color, topLeft = Offset(size.width * 0.58f, 0f), size = androidx.compose.ui.geometry.Size(w, size.height))
        } else {
            val path = Path().apply {
                moveTo(size.width * 0.18f, 0f)
                lineTo(size.width, size.height / 2)
                lineTo(size.width * 0.18f, size.height)
                close()
            }
            drawPath(path, color)
        }
    }
}

private fun clock(seconds: Int): String = "%d:%02d".format(seconds / 60, seconds % 60)

@Composable
private fun ReplayBar(r: ReplayState, p: Palette, model: StadiumViewModel, short: Boolean = false) {
    val length = (r.length ?: 3600).coerceAtLeast(1)
    var scrubbing by remember { mutableStateOf(false) }
    var scrub by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(r.gameSeconds) { if (!scrubbing) scrub = (r.gameSeconds ?: 0).toFloat() }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(p.plate).padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(
                Modifier.size(52.dp).clip(CircleShape).background(p.ink)
                    .clickable { if (r.playing) model.pause() else model.play() }
                    .semantics { contentDescription = if (r.playing) "Pause" else "Play" },
                contentAlignment = Alignment.Center,
            ) { PlayPauseGlyph(r.playing, Color(0xFF141619)) }
            Slider(
                value = scrub.coerceIn(0f, length.toFloat()),
                onValueChange = { scrubbing = true; scrub = it },
                onValueChangeFinished = { scrubbing = false; model.seek(scrub.toInt()) },
                valueRange = 0f..length.toFloat(),
                colors = SliderDefaults.colors(thumbColor = p.ink, activeTrackColor = p.ink, inactiveTrackColor = Color.White.copy(alpha = 0.2f)),
                modifier = Modifier.weight(1f).heightIn(min = 48.dp),
            )
            Text(r.label?.replace(" - ", " · ") ?: clock(scrub.toInt()), color = p.ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
            if (short && r.speeds.isNotEmpty()) {
                val next = r.speeds.firstOrNull { it > r.speed } ?: r.speeds.first()
                Box(
                    Modifier.heightIn(min = 48.dp).widthIn(min = 64.dp).clip(RoundedCornerShape(20.dp)).background(Color.White.copy(alpha = 0.1f))
                        .clickable { model.speed(next) }.semantics { contentDescription = "Speed ${score(r.speed)}×, tap for ${score(next)}×" },
                    contentAlignment = Alignment.Center,
                ) { Text("${score(r.speed)}×", color = p.ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1) }
            }
        }
        if (!short && r.speeds.isNotEmpty()) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Speed", color = p.inkSecondary, fontSize = 13.sp)
                for (s in r.speeds) {
                    val on = s == r.speed
                    Box(
                        Modifier.heightIn(min = 48.dp).widthIn(min = 48.dp).clip(RoundedCornerShape(20.dp))
                            .background(if (on) p.ink.copy(alpha = 0.9f) else Color.White.copy(alpha = 0.08f))
                            .clickable { model.speed(s) }.padding(horizontal = 10.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("${score(s)}×", color = if (on) Color(0xFF141619) else p.ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, softWrap = false)
                    }
                }
            }
        }
    }
}

@Composable
private fun DriveLog(spec: SceneSpec?, p: Palette, modifier: Modifier = Modifier) {
    val drive = spec?.shownDrive
    Column(modifier) {
        Text("This drive", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        if (spec == null || drive == null) {
            Text("No drive yet.", color = p.inkSecondary, fontSize = 15.sp)
            return
        }
        val team = spec.teams.side(drive.side)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
            team?.let { TeamChip(it, 28) }
            Text("${drive.arcs.size} plays" + (drive.result.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""), color = p.inkSecondary, fontSize = 14.sp)
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(drive.arcs.reversed(), key = { it.id }) { arc ->
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.padding(top = 6.dp).size(10.dp).clip(CircleShape).background(Color(argbOf(spec.color(arc.color, "#FFFFFF")))))
                    Column(Modifier.weight(1f)) {
                        val lead = listOfNotNull(
                            arc.down?.takeIf { it > 0 }?.let { d -> "${ordinal(d)} & ${arc.distance ?: "-"}" },
                            "Q${arc.period ?: "-"} ${arc.clock}",
                        ).joinToString(" · ")
                        Text(lead, color = p.ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text(arc.text, color = p.inkSecondary, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

private fun ordinal(n: Int) = when (n) { 1 -> "1st"; 2 -> "2nd"; 3 -> "3rd"; else -> "${n}th" }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DriveSheet(spec: SceneSpec?, p: Palette, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Color(0xFF121417)) {
        DriveLog(spec, p, Modifier.padding(horizontal = 16.dp).heightIn(max = 520.dp))
        Spacer(Modifier.height(24.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GamesSheet(games: List<ReplayState.Game>, current: String?, p: Palette, onPick: (String) -> Unit, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Color(0xFF121417)) {
        Column(Modifier.padding(horizontal = 16.dp)) {
            Text("Replay a game", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            if (games.isEmpty()) {
                Text("No captured games on this API. Capture one with `python3 -m fantasyedge replay --season 2025 --week 1 --team CHI`.",
                    color = p.inkSecondary, fontSize = 14.sp, modifier = Modifier.padding(vertical = 12.dp))
            }
            LazyColumn(Modifier.heightIn(max = 520.dp)) {
                items(games, key = { it.event }) { g ->
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable { onPick(g.event) }.padding(vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("${g.away.abbr} ${score(g.away.score)} at ${g.home.abbr} ${score(g.home.score)}", color = p.ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                            Text("${g.final} · ${g.date.take(10)} · ${g.plays} plays", color = p.inkSecondary, fontSize = 13.sp)
                        }
                        if (g.event == current) Badge("LOADED", p.live)
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun SettingsDialog(current: String, onSave: (String) -> Unit, onDismiss: () -> Unit) {
    var text by remember { mutableStateOf(current) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("API address") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("The emulator reaches this Mac at 10.0.2.2. A phone on your network needs the Mac's address and HTTPS or a debug build.")
                OutlinedTextField(value = text, onValueChange = { text = it }, singleLine = true)
            }
        },
        confirmButton = { TextButton(onClick = { onSave(text) }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
