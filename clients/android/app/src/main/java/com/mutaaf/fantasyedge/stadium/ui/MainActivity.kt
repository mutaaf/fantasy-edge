package com.mutaaf.fantasyedge.stadium.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.material3.windowsizeclass.ExperimentalMaterial3WindowSizeClassApi
import androidx.compose.material3.windowsizeclass.calculateWindowSizeClass

class MainActivity : ComponentActivity() {
    private val model: StadiumViewModel by viewModels()

    @OptIn(ExperimentalMaterial3WindowSizeClassApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Launch arguments let a script open a mode directly for screenshots:
        // adb shell am start -n .../.ui.MainActivity --es mode STADIUM
        // Only on a fresh start: a recreated activity keeps whatever the viewer chose since.
        if (savedInstanceState == null) applyLaunchArguments(intent)
        setContent {
            StadiumApp(model, calculateWindowSizeClass(this))
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        applyLaunchArguments(intent)
    }

    private fun applyLaunchArguments(intent: android.content.Intent?) {
        intent?.getStringExtra("mode")?.let { m ->
            runCatching { com.mutaaf.fantasyedge.stadium.geometry.Mode.valueOf(m) }.getOrNull()?.let(model::setMode)
        }
        intent?.getStringExtra("api")?.let(model::setBaseUrl)
    }
}
