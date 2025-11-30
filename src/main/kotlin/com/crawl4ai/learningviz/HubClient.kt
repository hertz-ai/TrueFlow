package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import java.net.URI
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.swing.SwingUtilities

// Message types - moved outside class for Kotlin compatibility
data class HubMessage(
    val type: String,
    val timestamp: String? = null,
    val data: JsonObject? = null,
    val from_project: String? = null,
    val command: String? = null,
    val args: JsonObject? = null,
    val request_id: String? = null  // For RPC requests
)

// Callback type for message handlers - must be at file level in Kotlin
typealias HubMessageHandler = (HubMessage) -> Unit

/**
 * TrueFlow Hub Client - WebSocket connection to MCP Hub
 *
 * Provides:
 * - Auto-connect to hub (starts hub if not running)
 * - Auto-reconnect on disconnect
 * - Event-driven message handling
 * - Project registration
 * - RPC request/response support
 */
class HubClient private constructor() : Disposable {

    companion object {
        @Volatile
        private var instance: HubClient? = null

        fun getInstance(): HubClient {
            return instance ?: synchronized(this) {
                instance ?: HubClient().also { instance = it }
            }
        }

        private const val HUB_URL = "ws://127.0.0.1:5680"
    }

    // State
    private var wsClient: WebSocketClient? = null
    private var projectId: String = "pycharm_${System.currentTimeMillis()}"
    private var projectName: String = "unknown"
    private var projectPath: String? = null
    private var reconnectAttempts = 0
    private val maxReconnectAttempts = 5
    private val reconnectDelay = 2000L
    private val messageHandlers = ConcurrentHashMap<String, CopyOnWriteArrayList<HubMessageHandler>>()
    private val isConnecting = AtomicBoolean(false)
    private val isConnected = AtomicBoolean(false)
    private val executor = Executors.newSingleThreadExecutor()
    private val gson = Gson()

    fun setProject(project: Project) {
        projectId = "pycharm_${project.name}_${System.currentTimeMillis()}"
        projectName = project.name
        projectPath = project.basePath
    }

    fun getProjectId(): String = projectId

    /**
     * Connect to the MCP Hub
     */
    fun connect(): Boolean {
        if (isConnected.get()) {
            return true
        }

        if (!isConnecting.compareAndSet(false, true)) {
            return false
        }

        try {
            // Try to connect to existing hub
            if (tryConnect()) {
                isConnecting.set(false)
                return true
            }

            // Start hub if not running
            PluginLogger.info("[TrueFlow Hub] Hub not running, starting...")
            startHub()

            // Wait a bit for hub to start
            Thread.sleep(2000)

            // Try connecting again
            val connected = tryConnect()
            isConnecting.set(false)
            return connected

        } catch (e: Exception) {
            PluginLogger.warn("[TrueFlow Hub] Connection error: ${e.message}")
            isConnecting.set(false)
            return false
        }
    }

    private fun tryConnect(): Boolean {
        try {
            val latch = java.util.concurrent.CountDownLatch(1)
            var connectSuccess = false

            wsClient = object : WebSocketClient(URI(HUB_URL)) {
                override fun onOpen(handshakedata: ServerHandshake?) {
                    PluginLogger.info("[TrueFlow Hub] Connected to hub")
                    isConnected.set(true)
                    reconnectAttempts = 0
                    connectSuccess = true
                    latch.countDown()

                    // Register this project
                    register()
                }

                override fun onMessage(message: String?) {
                    if (message == null) return
                    try {
                        val hubMessage = gson.fromJson(message, HubMessage::class.java)
                        handleMessage(hubMessage)
                    } catch (e: Exception) {
                        PluginLogger.warn("[TrueFlow Hub] Invalid message: ${e.message}")
                    }
                }

                override fun onClose(code: Int, reason: String?, remote: Boolean) {
                    PluginLogger.info("[TrueFlow Hub] Disconnected from hub: $reason")
                    isConnected.set(false)
                    latch.countDown()
                    scheduleReconnect()
                }

                override fun onError(ex: Exception?) {
                    PluginLogger.debug("[TrueFlow Hub] WebSocket error: ${ex?.message}")
                    latch.countDown()
                }
            }

            wsClient?.connectBlocking(3, java.util.concurrent.TimeUnit.SECONDS)

            // Wait for connection result
            latch.await(5, java.util.concurrent.TimeUnit.SECONDS)

            return connectSuccess && isConnected.get()

        } catch (e: Exception) {
            PluginLogger.debug("[TrueFlow Hub] Connection attempt failed: ${e.message}")
            return false
        }
    }

    private fun register() {
        val data = JsonObject().apply {
            addProperty("project_id", projectId)
            addProperty("ide", "pycharm")
            addProperty("project_name", projectName)
            addProperty("project_path", projectPath)
            add("capabilities", gson.toJsonTree(listOf(
                "ai_server",
                "trace_collection",
                "manim_generation",
                "dead_code_analysis",
                "performance_analysis"
            )))
        }
        send(HubMessage(type = "register", data = data))
    }

    private fun handleMessage(message: HubMessage) {
        // RPC requests should NOT run on EDT - they need to respond quickly
        val runOnEdt = message.type != "rpc_request"

        // Dispatch to registered handlers
        messageHandlers[message.type]?.forEach { handler ->
            try {
                if (runOnEdt) {
                    SwingUtilities.invokeLater { handler(message) }
                } else {
                    // Run RPC handlers on executor to avoid blocking EDT
                    executor.submit { handler(message) }
                }
            } catch (e: Exception) {
                PluginLogger.warn("[TrueFlow Hub] Handler error: ${e.message}")
            }
        }

        // Also dispatch to wildcard handlers
        messageHandlers["*"]?.forEach { handler ->
            try {
                if (runOnEdt) {
                    SwingUtilities.invokeLater { handler(message) }
                } else {
                    executor.submit { handler(message) }
                }
            } catch (e: Exception) {
                PluginLogger.warn("[TrueFlow Hub] Wildcard handler error: ${e.message}")
            }
        }
    }

    private fun scheduleReconnect() {
        if (reconnectAttempts >= maxReconnectAttempts) {
            PluginLogger.info("[TrueFlow Hub] Max reconnect attempts reached")
            return
        }

        reconnectAttempts++
        val delay = reconnectDelay * reconnectAttempts
        PluginLogger.info("[TrueFlow Hub] Reconnecting in ${delay}ms (attempt $reconnectAttempts)")

        executor.submit {
            Thread.sleep(delay)
            if (!isConnected.get()) {
                connect()
            }
        }
    }

    private fun startHub() {
        try {
            // Find the hub script in various locations
            val homeDir = System.getProperty("user.home")
            val possiblePaths = listOf(
                "$homeDir/.trueflow/trueflow_mcp_hub.py",
                "src/main/resources/runtime_injector/trueflow_mcp_hub.py"
            )

            var hubScript: java.io.File? = null
            for (path in possiblePaths) {
                val file = java.io.File(path)
                if (file.exists()) {
                    hubScript = file
                    break
                }
            }

            if (hubScript == null) {
                PluginLogger.warn("[TrueFlow Hub] Hub script not found")
                return
            }

            // Start hub in background (WebSocket only mode)
            val process = ProcessBuilder(findPython(), hubScript.absolutePath, "--ws-only")
                .redirectErrorStream(true)
                .start()

            PluginLogger.info("[TrueFlow Hub] Started hub process")

        } catch (e: Exception) {
            PluginLogger.warn("[TrueFlow Hub] Failed to start hub: ${e.message}")
        }
    }

    private fun findPython(): String {
        val paths = listOf("python", "python3", "C:/Python310/python.exe", "C:/Python311/python.exe", "C:/Python312/python.exe")
        for (path in paths) {
            try {
                if (ProcessBuilder(path, "--version").start().waitFor() == 0) return path
            } catch (e: Exception) { }
        }
        return "python"
    }

    // ==================== Public API ====================

    fun send(message: HubMessage) {
        if (!isConnected.get() || wsClient?.isOpen != true) {
            PluginLogger.warn("[TrueFlow Hub] Cannot send - not connected")
            return
        }

        try {
            val json = gson.toJson(message)
            wsClient?.send(json)
        } catch (e: Exception) {
            PluginLogger.warn("[TrueFlow Hub] Send error: ${e.message}")
        }
    }

    fun on(messageType: String, handler: HubMessageHandler) {
        messageHandlers.computeIfAbsent(messageType) { CopyOnWriteArrayList() }.add(handler)
    }

    fun off(messageType: String, handler: HubMessageHandler) {
        messageHandlers[messageType]?.remove(handler)
    }

    fun isConnected(): Boolean = isConnected.get() && wsClient?.isOpen == true

    fun disconnect() {
        isConnected.set(false)
        wsClient?.close()
        wsClient = null
    }

    // ==================== Convenience Methods ====================

    fun notifyAIServerStarted(port: Int, model: String) {
        val data = JsonObject().apply {
            addProperty("port", port)
            addProperty("model", model)
            addProperty("started_by", projectId)
        }
        send(HubMessage(type = "ai_server_started", data = data))
    }

    fun notifyAIServerStopped() {
        send(HubMessage(type = "ai_server_stopped", data = JsonObject()))
    }

    fun sendTraceUpdate(traceData: JsonObject) {
        send(HubMessage(type = "trace_update", data = traceData))
    }

    fun requestFromProject(targetProject: String, command: String, args: JsonObject = JsonObject()) {
        val data = JsonObject().apply {
            addProperty("target_project", targetProject)
            addProperty("command", command)
            add("args", args)
        }
        send(HubMessage(type = "request", data = data))
    }

    fun respondToProject(targetProject: String, responseData: JsonObject) {
        val data = JsonObject().apply {
            addProperty("target_project", targetProject)
            responseData.entrySet().forEach { (key, value) ->
                add(key, value)
            }
        }
        send(HubMessage(type = "response", data = data))
    }

    /**
     * Send RPC response back to hub for a specific request
     */
    fun sendRpcResponse(requestId: String, responseData: JsonObject) {
        if (!isConnected.get() || wsClient?.isOpen != true) {
            PluginLogger.warn("[TrueFlow Hub] Cannot send RPC response - not connected")
            return
        }

        try {
            val response = JsonObject().apply {
                addProperty("type", "rpc_response")
                addProperty("request_id", requestId)
                add("data", responseData)
            }
            wsClient?.send(gson.toJson(response))
        } catch (e: Exception) {
            PluginLogger.warn("[TrueFlow Hub] RPC response error: ${e.message}")
        }
    }

    override fun dispose() {
        disconnect()
        executor.shutdown()
    }
}
