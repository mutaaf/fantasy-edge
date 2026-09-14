package com.mutaaf.fantasyedge.stadium.scene

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * design/tokens.json, read from the APK's assets where the build copied it.
 *
 * The scene already carries its palette, so the 3D renderer never needs this.
 * The Compose chrome around it does - the scorebug, the plates, the fills - and
 * reads the same file rather than a hand-kept copy of its hex values.
 */
class DesignTokens(val colors: Map<String, String>, val motion: Map<String, Double>) {

    fun color(token: String, fallback: String = "#FF00FF"): String = colors[token] ?: fallback

    /** ARGB for Compose, from "#RRGGBB" or "#RRGGBBAA". */
    fun argb(token: String, fallback: String = "#FF00FF"): Long {
        val c = SceneMath.rgba(color(token, fallback))
        return (Math.round(c[3] * 255).toLong() shl 24) or (Math.round(c[0] * 255).toLong() shl 16) or
            (Math.round(c[1] * 255).toLong() shl 8) or Math.round(c[2] * 255).toLong()
    }

    companion object {
        fun parse(text: String): DesignTokens {
            val root = Json.parseToJsonElement(text).jsonObject
            val colors = (root["color"] as? JsonObject)?.mapNotNull { (k, v) ->
                v.jsonPrimitive.contentOrNull?.let { k to it }
            }?.toMap() ?: emptyMap()
            val motion = (root["motion"] as? JsonObject)?.mapNotNull { (k, v) ->
                (v as? kotlinx.serialization.json.JsonPrimitive)?.doubleOrNull?.let { k to it }
            }?.toMap() ?: emptyMap()
            return DesignTokens(colors, motion)
        }
    }
}

/** ARGB for a hex string, for colours that arrive in the scene rather than the tokens. */
fun argbOf(hex: String): Long {
    val c = SceneMath.rgba(hex)
    return (Math.round(c[3] * 255).toLong() shl 24) or (Math.round(c[0] * 255).toLong() shl 16) or
        (Math.round(c[1] * 255).toLong() shl 8) or Math.round(c[2] * 255).toLong()
}
