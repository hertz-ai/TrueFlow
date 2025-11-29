package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Socket client for connecting to Python trace server.
 * Receives real-time trace events and notifies listeners.
 */
class TraceSocketClient(
    private val host: String = "127.0.0.1",
    private val port: Int = 5678,
    private val onTraceReceived: (TraceEvent) -> Unit,
    private val onConnected: () -> Unit = {},
    private val onDisconnected: (String?) -> Unit = {},
    private val onError: (Exception) -> Unit = {}
) {
    private var socket: Socket? = null
    private val running = AtomicBoolean(false)
    private val gson = Gson()

    fun connect() {
        if (!running.compareAndSet(false, true)) {
            PluginLogger.info("[TraceSocketClient] Already connected")
            return
        }

        thread(name = "TraceSocketClient-Connection") {
            try {
                PluginLogger.info("[TraceSocketClient] Connecting to $host:$port...")
                socket = Socket()
                socket!!.connect(java.net.InetSocketAddress(host, port), 5000) // 5 second timeout

                // Enable TCP keep-alive to detect dropped connections
                socket!!.keepAlive = true
                socket!!.tcpNoDelay = true
                socket!!.soTimeout = 600000 // 600 seconds read timeout

                PluginLogger.info("[TraceSocketClient] Connected to trace server at $host:$port")
                onConnected()

                // Read traces in background
                val reader = BufferedReader(InputStreamReader(socket!!.getInputStream()), 65536) // 64KB buffer
                var eventCount = 0
                while (running.get()) {
                    val line = reader.readLine() ?: break
                    try {
                        val traceEvent = parseTraceEvent(line)
                        onTraceReceived(traceEvent)
                        eventCount++
                        if (eventCount <= 10) {
                            PluginLogger.debug("[TraceSocketClient] Received event #$eventCount: ${line.take(200)}")
                        }
                        if (eventCount == 11) {
                            PluginLogger.info("[TraceSocketClient] Suppressing further event logs (events are being processed)")
                        }
                    } catch (e: Exception) {
                        PluginLogger.error("[TraceSocketClient] Error parsing trace: ${e.message} - JSON: ${line.take(200)}", e)
                    }
                }

                PluginLogger.info("[TraceSocketClient] Connection closed")
                onDisconnected(null)

            } catch (e: Exception) {
                PluginLogger.error("[TraceSocketClient] Connection error: ${e.message}", e)
                onError(e)
                onDisconnected(e.message)
            } finally {
                running.set(false)
                disconnect()
            }
        }
    }

    private fun parseTraceEvent(json: String): TraceEvent {
        val data = gson.fromJson(json, JsonObject::class.java)
        return TraceEvent(
            type = data.get("type")?.asString ?: "unknown",
            timestamp = data.get("timestamp")?.asDouble ?: 0.0,
            callId = data.get("call_id")?.asString ?: "",
            module = data.get("module")?.asString ?: "",
            function = data.get("function")?.asString ?: "",
            file = data.get("file")?.asString ?: "",
            line = data.get("line")?.asInt ?: 0,
            depth = data.get("depth")?.asInt ?: 0,
            parentId = if (data.get("parent_id")?.isJsonNull == true) null else data.get("parent_id")?.asString,
            processId = data.get("process_id")?.asInt ?: 0,
            sessionId = data.get("session_id")?.asString ?: "",
            correlationId = if (data.get("correlation_id")?.isJsonNull == true) null else data.get("correlation_id")?.asString,
            learningPhase = if (data.get("learning_phase")?.isJsonNull == true) null else data.get("learning_phase")?.asString,
            traceData = data.get("trace_data")?.asJsonObject  // For cycle_complete events
        )
    }

    fun disconnect() {
        running.set(false)
        try {
            socket?.close()
            PluginLogger.info("[TraceSocketClient] Socket closed")
        } catch (e: Exception) {
            PluginLogger.error("[TraceSocketClient] Error closing socket: ${e.message}", e)
        }
        socket = null
    }

    fun isConnected(): Boolean = running.get() && socket?.isConnected == true
}

/**
 * Trace event received from Python trace server.
 */
data class TraceEvent(
    val type: String,           // "call", "return", "cycle_complete", etc.
    val timestamp: Double,      // Unix timestamp
    val callId: String,         // Unique call ID
    val module: String,         // Python module name
    val function: String,       // Function name
    val file: String,           // Source file path
    val line: Int,              // Line number
    val depth: Int,             // Call stack depth
    val parentId: String?,      // Parent call ID (for hierarchy)
    val processId: Int,         // OS process ID
    val sessionId: String,      // Session ID
    val correlationId: String?, // Learning cycle correlation ID
    val learningPhase: String?, // Learning phase (perception, reasoning, etc.)
    val traceData: com.google.gson.JsonObject? = null  // Complete trace data for cycle_complete events
) {
    /**
     * Format as PlantUML sequence diagram arrow.
     */
    fun toPlantUML(): String {
        // Use parent for proper call hierarchy
        val caller = if (parentId != null && module != "__main__") {
            module.split(".").lastOrNull() ?: module
        } else {
            module.split(".").lastOrNull() ?: module
        }
        val callee = module.split(".").lastOrNull() ?: module
        return "$caller -> $callee: $function()"
    }

    /**
     * Get short module name for participant.
     */
    fun getParticipantId(): String {
        return module.split(".").lastOrNull() ?: module
    }

    /**
     * Format as readable string.
     */
    override fun toString(): String {
        return "$module.$function() at $file:$line [depth=$depth]"
    }
}
