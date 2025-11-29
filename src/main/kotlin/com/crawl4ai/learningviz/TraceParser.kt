package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.File

/**
 * Parser for learning trace JSON files.
 */
class TraceParser {

    private val gson = Gson()

    data class TraceSession(
        val session_id: String,
        val start_time: Double,
        val end_time: Double?,
        val events: List<TraceEvent>,
        val total_api_calls: Int,
        val total_corrections: Int,
        val total_learning_events: Int,
        val one_shot_successes: Int,
        val error_reductions: List<Double>,
        val lora_updates: Int,
        val ssm_updates: Int
    )

    data class TraceEvent(
        val event_id: String,
        val timestamp: Double,
        val event_type: String,
        val category: String,
        val function_name: String,
        val module: String,
        val thread_id: Long,
        val inputs: Map<String, Any>?,
        val outputs: Map<String, Any>?,
        val duration_ms: Double?,
        val memory_delta_mb: Double?,
        val learning_stats: Map<String, Any>?,
        val model_updates: Map<String, Any>?,
        val error: String?,
        val parent_event_id: String?,
        val children_event_ids: List<String>?
    )

    fun parseTraceFile(file: File): TraceSession? {
        return try {
            val json = file.readText()
            gson.fromJson(json, TraceSession::class.java)
        } catch (e: Exception) {
            println("Error parsing trace file: ${e.message}")
            null
        }
    }

    fun parseTraceJson(json: String): TraceSession? {
        return try {
            gson.fromJson(json, TraceSession::class.java)
        } catch (e: Exception) {
            println("Error parsing trace JSON: ${e.message}")
            null
        }
    }

    fun getSessionSummary(session: TraceSession): Map<String, Any> {
        val duration = (session.end_time ?: System.currentTimeMillis() / 1000.0) - session.start_time
        val avgErrorReduction = if (session.error_reductions.isNotEmpty()) {
            session.error_reductions.average()
        } else {
            0.0
        }
        val oneShotRate = if (session.total_learning_events > 0) {
            (session.one_shot_successes.toDouble() / session.total_learning_events) * 100
        } else {
            0.0
        }

        return mapOf(
            "session_id" to session.session_id,
            "duration_s" to String.format("%.1f", duration),
            "total_events" to session.events.size,
            "total_api_calls" to session.total_api_calls,
            "total_corrections" to session.total_corrections,
            "total_learning_events" to session.total_learning_events,
            "one_shot_successes" to session.one_shot_successes,
            "one_shot_success_rate" to String.format("%.1f", oneShotRate),
            "avg_error_reduction" to String.format("%.2f", avgErrorReduction),
            "lora_updates" to session.lora_updates,
            "ssm_updates" to session.ssm_updates
        )
    }
}
