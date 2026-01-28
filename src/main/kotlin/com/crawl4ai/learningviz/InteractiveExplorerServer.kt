package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.URL
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import kotlin.concurrent.thread

/**
 * HTTP Server that serves the Interactive Explorer with real-time updates.
 *
 * Features:
 * - Serves the interactive_flow_explorer.html at /
 * - Provides Server-Sent Events (SSE) at /events for real-time trace updates
 * - Provides JSON API at /api/data for current trace data
 * - Provides AI explanation API at /api/ai/explain (proxies to llama.cpp server)
 * - Auto-opens browser when started
 *
 * Usage:
 * 1. Start server: server.start()
 * 2. Push updates: server.pushTraceData(data)
 * 3. Stop server: server.stop()
 */
class InteractiveExplorerServer(
    private val port: Int = 8765,
    private val llmEndpoint: String = "http://127.0.0.1:8080/v1",  // llama.cpp server (OpenAI-compatible)
    private val onServerStarted: (url: String) -> Unit = {},
    private val onServerStopped: () -> Unit = {},
    private val onError: (Exception) -> Unit = {},
    // Unified explain handler - routes through same logic as IDE mode
    // Takes (funcName, filePath, isDead, whyNotCovered) and callback for result
    private val onExplainRequest: ((funcName: String, filePath: String, isDead: Boolean, whyNotCovered: String?, onResult: (String?, Boolean) -> Unit) -> Unit)? = null,
    // Prioritize handler - for preemptive caching based on user searches/focus
    private val onPrioritizeRequest: ((funcNames: List<String>, reason: String) -> Unit)? = null
) {
    private var server: HttpServer? = null
    private val gson = Gson()
    private val sseClients = CopyOnWriteArrayList<HttpExchange>()

    // Current trace data (cached for new SSE clients)
    @Volatile
    private var currentTraceData: Map<String, Any>? = null

    // HTML template cache
    private var htmlTemplate: String? = null

    fun start(): Boolean {
        if (server != null) {
            PluginLogger.warn("[ExplorerServer] Server already running")
            return false
        }

        return try {
            server = HttpServer.create(InetSocketAddress(port), 0)
            server?.executor = Executors.newCachedThreadPool()

            // Main page - serves the HTML
            server?.createContext("/") { exchange ->
                handleMainPage(exchange)
            }

            // SSE endpoint for real-time updates
            server?.createContext("/events") { exchange ->
                handleSSE(exchange)
            }

            // JSON API for current data
            server?.createContext("/api/data") { exchange ->
                handleDataApi(exchange)
            }

            // Static resources (if needed)
            server?.createContext("/static") { exchange ->
                handleStatic(exchange)
            }

            // AI explanation endpoint
            server?.createContext("/api/ai/explain") { exchange ->
                handleAIExplain(exchange)
            }

            // AI status endpoint
            server?.createContext("/api/ai/status") { exchange ->
                handleAIStatus(exchange)
            }

            // AI prioritize endpoint (for preemptive caching)
            server?.createContext("/api/ai/prioritize") { exchange ->
                handleAIPrioritize(exchange)
            }

            server?.start()

            val url = "http://localhost:$port"
            PluginLogger.info("[ExplorerServer] Started at $url")
            onServerStarted(url)

            true
        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Failed to start: ${e.message}", e)
            onError(e)
            false
        }
    }

    fun stop() {
        try {
            // Close all SSE connections
            sseClients.forEach { exchange ->
                try {
                    exchange.responseBody?.close()
                } catch (e: Exception) {
                    // Ignore close errors
                }
            }
            sseClients.clear()

            server?.stop(0)
            server = null

            PluginLogger.info("[ExplorerServer] Stopped")
            onServerStopped()
        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error stopping: ${e.message}", e)
        }
    }

    fun isRunning(): Boolean = server != null

    fun getUrl(): String = "http://localhost:$port"

    /**
     * Push new trace data to all connected SSE clients.
     */
    fun pushTraceData(data: Map<String, Any>) {
        currentTraceData = data

        val jsonData = gson.toJson(data)
        val sseMessage = "event: traceUpdate\ndata: $jsonData\n\n"

        // Send to all connected SSE clients
        val deadClients = mutableListOf<HttpExchange>()

        for (client in sseClients) {
            try {
                val output = client.responseBody
                output.write(sseMessage.toByteArray())
                output.flush()
            } catch (e: Exception) {
                // Client disconnected
                deadClients.add(client)
            }
        }

        // Clean up dead connections
        sseClients.removeAll(deadClients)

        PluginLogger.debug("[ExplorerServer] Pushed update to ${sseClients.size} clients")
    }

    /**
     * Serve the main HTML page with embedded SSE client.
     */
    private fun handleMainPage(exchange: HttpExchange) {
        try {
            if (exchange.requestMethod != "GET") {
                sendResponse(exchange, 405, "Method Not Allowed")
                return
            }

            val html = getHtmlWithSSE()

            exchange.responseHeaders.add("Content-Type", "text/html; charset=utf-8")
            exchange.responseHeaders.add("Cache-Control", "no-cache")
            exchange.sendResponseHeaders(200, html.toByteArray().size.toLong())

            exchange.responseBody.use { output ->
                output.write(html.toByteArray())
            }
        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error serving main page: ${e.message}", e)
            sendResponse(exchange, 500, "Internal Server Error")
        }
    }

    /**
     * Handle Server-Sent Events connection for real-time updates.
     */
    private fun handleSSE(exchange: HttpExchange) {
        try {
            if (exchange.requestMethod != "GET") {
                sendResponse(exchange, 405, "Method Not Allowed")
                return
            }

            // Set SSE headers
            exchange.responseHeaders.add("Content-Type", "text/event-stream")
            exchange.responseHeaders.add("Cache-Control", "no-cache")
            exchange.responseHeaders.add("Connection", "keep-alive")
            exchange.responseHeaders.add("Access-Control-Allow-Origin", "*")
            exchange.sendResponseHeaders(200, 0) // Chunked transfer

            // Add to clients list
            sseClients.add(exchange)
            PluginLogger.info("[ExplorerServer] SSE client connected (${sseClients.size} total)")

            // Send initial data if available
            currentTraceData?.let { data ->
                try {
                    val jsonData = gson.toJson(data)
                    val initialMessage = "event: traceUpdate\ndata: $jsonData\n\n"
                    exchange.responseBody.write(initialMessage.toByteArray())
                    exchange.responseBody.flush()
                } catch (e: Exception) {
                    // Client may have disconnected
                }
            }

            // Keep connection open - client will disconnect when browser closes
            // The connection is kept in sseClients and cleaned up on push failures

        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error handling SSE: ${e.message}", e)
            sseClients.remove(exchange)
        }
    }

    /**
     * Handle JSON API requests for current trace data.
     */
    private fun handleDataApi(exchange: HttpExchange) {
        try {
            // CORS headers
            exchange.responseHeaders.add("Access-Control-Allow-Origin", "*")
            exchange.responseHeaders.add("Access-Control-Allow-Methods", "GET, OPTIONS")
            exchange.responseHeaders.add("Access-Control-Allow-Headers", "Content-Type")

            if (exchange.requestMethod == "OPTIONS") {
                exchange.sendResponseHeaders(200, -1)
                return
            }

            if (exchange.requestMethod != "GET") {
                sendResponse(exchange, 405, "Method Not Allowed")
                return
            }

            val data = currentTraceData ?: emptyMap<String, Any>()
            val json = gson.toJson(data)

            exchange.responseHeaders.add("Content-Type", "application/json")
            exchange.sendResponseHeaders(200, json.toByteArray().size.toLong())

            exchange.responseBody.use { output ->
                output.write(json.toByteArray())
            }
        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error handling data API: ${e.message}", e)
            sendResponse(exchange, 500, "Internal Server Error")
        }
    }

    /**
     * Handle static resource requests.
     */
    private fun handleStatic(exchange: HttpExchange) {
        sendResponse(exchange, 404, "Not Found")
    }

    /**
     * Handle AI explanation requests - proxies to llama.cpp server.
     */
    private fun handleAIExplain(exchange: HttpExchange) {
        try {
            // CORS headers
            exchange.responseHeaders.add("Access-Control-Allow-Origin", "*")
            exchange.responseHeaders.add("Access-Control-Allow-Methods", "POST, OPTIONS")
            exchange.responseHeaders.add("Access-Control-Allow-Headers", "Content-Type")

            if (exchange.requestMethod == "OPTIONS") {
                exchange.sendResponseHeaders(200, -1)
                return
            }

            if (exchange.requestMethod != "POST") {
                sendJsonResponse(exchange, 405, mapOf("error" to "Method Not Allowed"))
                return
            }

            // Read request body
            val requestBody = exchange.requestBody.bufferedReader().readText()
            val request = gson.fromJson(requestBody, JsonObject::class.java)

            val functionName = request.get("function")?.asString ?: "unknown"
            val fileName = request.get("file")?.asString ?: ""
            val isDead = request.get("isDead")?.asBoolean ?: false
            val whyNotCovered = request.get("whyNotCovered")?.asString

            // Use unified explain handler if available (same logic as IDE mode)
            if (onExplainRequest != null) {
                PluginLogger.info("[ExplorerServer] Routing explain request to unified handler: $functionName")
                onExplainRequest.invoke(functionName, fileName, isDead, whyNotCovered) { explanation, cached ->
                    if (explanation != null) {
                        sendJsonResponse(exchange, 200, mapOf(
                            "success" to true,
                            "explanation" to explanation,
                            "cached" to cached
                        ))
                    } else {
                        sendJsonResponse(exchange, 500, mapOf(
                            "success" to false,
                            "error" to "Failed to get AI explanation"
                        ))
                    }
                }
                return
            }

            // Fallback: use simple direct LLM call (no unified handler available)
            val context = request.get("context")?.asString ?: ""
            val prompt = buildExplanationPrompt(functionName, fileName, context)

            thread {
                try {
                    val response = callLLM(prompt)
                    sendJsonResponse(exchange, 200, mapOf(
                        "success" to true,
                        "explanation" to response,
                        "cached" to false
                    ))
                } catch (e: Exception) {
                    PluginLogger.error("[ExplorerServer] LLM error: ${e.message}", e)
                    sendJsonResponse(exchange, 500, mapOf(
                        "success" to false,
                        "error" to (e.message ?: "Failed to get AI explanation")
                    ))
                }
            }

        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error handling AI explain: ${e.message}", e)
            sendJsonResponse(exchange, 500, mapOf("error" to "Internal Server Error"))
        }
    }

    /**
     * Handle AI status check - checks if llama.cpp server is running.
     */
    private fun handleAIStatus(exchange: HttpExchange) {
        try {
            // CORS headers
            exchange.responseHeaders.add("Access-Control-Allow-Origin", "*")
            exchange.responseHeaders.add("Access-Control-Allow-Methods", "GET, OPTIONS")
            exchange.responseHeaders.add("Access-Control-Allow-Headers", "Content-Type")

            if (exchange.requestMethod == "OPTIONS") {
                exchange.sendResponseHeaders(200, -1)
                return
            }

            // Check if llama.cpp server is running
            val (isRunning, modelName) = checkLLMStatus()

            sendJsonResponse(exchange, 200, mapOf(
                "available" to isRunning,
                "endpoint" to llmEndpoint,
                "model" to modelName
            ))

        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error checking AI status: ${e.message}", e)
            sendJsonResponse(exchange, 200, mapOf(
                "available" to false,
                "error" to (e.message ?: "Unknown error")
            ))
        }
    }

    /**
     * Handle AI prioritize request - queues functions for preemptive caching.
     */
    private fun handleAIPrioritize(exchange: HttpExchange) {
        try {
            // CORS headers
            exchange.responseHeaders.add("Access-Control-Allow-Origin", "*")
            exchange.responseHeaders.add("Access-Control-Allow-Methods", "POST, OPTIONS")
            exchange.responseHeaders.add("Access-Control-Allow-Headers", "Content-Type")

            if (exchange.requestMethod == "OPTIONS") {
                exchange.sendResponseHeaders(200, -1)
                return
            }

            if (exchange.requestMethod != "POST") {
                sendJsonResponse(exchange, 405, mapOf("error" to "Method not allowed"))
                return
            }

            // Parse request body
            val body = exchange.requestBody.bufferedReader().readText()
            val request = gson.fromJson(body, JsonObject::class.java)

            val reason = request.get("reason")?.asString ?: "user_interaction"
            val funcNames = mutableListOf<String>()

            // Support both single function and array of functions
            val singleFunc = request.get("function")?.asString
            val funcArray = request.getAsJsonArray("functions")

            if (singleFunc != null) {
                funcNames.add(singleFunc)
            }
            if (funcArray != null) {
                funcArray.forEach { funcNames.add(it.asString) }
            }

            if (funcNames.isEmpty()) {
                sendJsonResponse(exchange, 400, mapOf("error" to "No functions specified"))
                return
            }

            // Call the prioritize handler
            if (onPrioritizeRequest != null) {
                onPrioritizeRequest.invoke(funcNames, reason)
                sendJsonResponse(exchange, 200, mapOf(
                    "success" to true,
                    "prioritized" to funcNames.size,
                    "reason" to reason
                ))
            } else {
                sendJsonResponse(exchange, 200, mapOf(
                    "success" to false,
                    "message" to "Prioritization not available in browser mode"
                ))
            }

        } catch (e: Exception) {
            PluginLogger.error("[ExplorerServer] Error handling AI prioritize: ${e.message}", e)
            sendJsonResponse(exchange, 500, mapOf("error" to "Internal Server Error"))
        }
    }

    /**
     * Build a prompt for explaining a function.
     */
    private fun buildExplanationPrompt(functionName: String, fileName: String, context: String): String {
        return """You are a code analysis assistant. Explain the purpose and behavior of this function concisely.

Function: $functionName
File: $fileName
${if (context.isNotBlank()) "Additional context:\n$context" else ""}

Provide a clear, concise explanation of:
1. What this function does
2. Its role in the codebase
3. Any important side effects or dependencies

Keep the explanation focused and under 200 words."""
    }

    /**
     * Call llama.cpp server using OpenAI-compatible chat completions API.
     */
    private fun callLLM(prompt: String): String {
        val url = URL("$llmEndpoint/chat/completions")
        val connection = url.openConnection() as HttpURLConnection

        try {
            connection.requestMethod = "POST"
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true
            connection.connectTimeout = 30000
            connection.readTimeout = 120000  // 2 minutes for AI response

            val requestBody = gson.toJson(mapOf(
                "messages" to listOf(
                    mapOf("role" to "user", "content" to prompt)
                ),
                "temperature" to 0.7,
                "max_tokens" to 1024,
                "stream" to false
            ))

            connection.outputStream.use { os ->
                os.write(requestBody.toByteArray())
            }

            if (connection.responseCode != 200) {
                throw Exception("LLM server returned ${connection.responseCode}")
            }

            val response = connection.inputStream.bufferedReader().readText()
            val jsonResponse = gson.fromJson(response, JsonObject::class.java)

            // OpenAI format: choices[0].message.content
            val choices = jsonResponse.getAsJsonArray("choices")
            if (choices != null && choices.size() > 0) {
                val message = choices[0].asJsonObject.getAsJsonObject("message")
                return message?.get("content")?.asString ?: "No response from AI"
            }

            return "No response from AI"

        } finally {
            connection.disconnect()
        }
    }

    /**
     * Check if llama.cpp server is running and get model info.
     * Returns (isRunning, modelName)
     */
    private fun checkLLMStatus(): Pair<Boolean, String> {
        // First check /health endpoint
        try {
            val healthUrl = URL(llmEndpoint.replace("/v1", "/health"))
            val healthConn = healthUrl.openConnection() as HttpURLConnection
            healthConn.connectTimeout = 2000
            healthConn.readTimeout = 2000
            healthConn.requestMethod = "GET"

            if (healthConn.responseCode != 200) {
                healthConn.disconnect()
                return Pair(false, "")
            }
            healthConn.disconnect()
        } catch (e: Exception) {
            return Pair(false, "")
        }

        // Get model name from /v1/models
        try {
            val modelsUrl = URL("$llmEndpoint/models")
            val modelsConn = modelsUrl.openConnection() as HttpURLConnection
            modelsConn.connectTimeout = 2000
            modelsConn.readTimeout = 2000
            modelsConn.requestMethod = "GET"

            if (modelsConn.responseCode == 200) {
                val response = modelsConn.inputStream.bufferedReader().readText()
                val jsonResponse = gson.fromJson(response, JsonObject::class.java)
                val data = jsonResponse.getAsJsonArray("data")
                if (data != null && data.size() > 0) {
                    val modelId = data[0].asJsonObject.get("id")?.asString ?: "unknown"
                    modelsConn.disconnect()
                    return Pair(true, modelId)
                }
            }
            modelsConn.disconnect()
            return Pair(true, "llama.cpp")
        } catch (e: Exception) {
            return Pair(true, "llama.cpp")  // Server is up but couldn't get model name
        }
    }

    private fun sendJsonResponse(exchange: HttpExchange, code: Int, data: Map<String, Any?>) {
        try {
            val json = gson.toJson(data)
            exchange.responseHeaders.add("Content-Type", "application/json")
            exchange.sendResponseHeaders(code, json.toByteArray().size.toLong())
            exchange.responseBody.use { output ->
                output.write(json.toByteArray())
            }
        } catch (e: Exception) {
            // Ignore send errors
        }
    }

    private fun sendResponse(exchange: HttpExchange, code: Int, message: String) {
        try {
            exchange.sendResponseHeaders(code, message.toByteArray().size.toLong())
            exchange.responseBody.use { output ->
                output.write(message.toByteArray())
            }
        } catch (e: Exception) {
            // Ignore send errors
        }
    }

    /**
     * Get the HTML template with SSE client code injected.
     */
    private fun getHtmlWithSSE(): String {
        // Load base HTML template
        if (htmlTemplate == null) {
            htmlTemplate = try {
                val inputStream = javaClass.getResourceAsStream("/interactive_viz/interactive_flow_explorer.html")
                inputStream?.bufferedReader()?.readText() ?: getDefaultHtml()
            } catch (e: Exception) {
                PluginLogger.error("[ExplorerServer] Failed to load HTML template", e)
                getDefaultHtml()
            }
        }

        // Inject SSE client code
        val sseClientScript = """
<script>
// TrueFlow Real-time SSE Client
(function() {
    const SSE_URL = '/events';
    let eventSource = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    const RECONNECT_DELAY = 2000;

    function showConnectionStatus(status, message) {
        let statusEl = document.getElementById('trueflow-connection-status');
        if (!statusEl) {
            statusEl = document.createElement('div');
            statusEl.id = 'trueflow-connection-status';
            statusEl.style.cssText = 'position:fixed;bottom:80px;right:10px;padding:8px 16px;border-radius:4px;font-size:12px;z-index:10000;transition:opacity 0.3s;';
            document.body.appendChild(statusEl);
        }

        if (status === 'connected') {
            statusEl.style.background = '#4CAF50';
            statusEl.style.color = 'white';
            statusEl.textContent = '● Live: ' + message;
            setTimeout(() => { statusEl.style.opacity = '0.6'; }, 3000);
        } else if (status === 'connecting') {
            statusEl.style.background = '#FF9800';
            statusEl.style.color = 'white';
            statusEl.style.opacity = '1';
            statusEl.textContent = '◌ ' + message;
        } else if (status === 'error') {
            statusEl.style.background = '#f44336';
            statusEl.style.color = 'white';
            statusEl.style.opacity = '1';
            statusEl.textContent = '✕ ' + message;
        }
    }

    function connect() {
        if (eventSource) {
            eventSource.close();
        }

        showConnectionStatus('connecting', 'Connecting to TrueFlow...');

        eventSource = new EventSource(SSE_URL);

        eventSource.onopen = function() {
            console.log('[TrueFlow] SSE connected');
            reconnectAttempts = 0;
            showConnectionStatus('connected', 'Real-time updates active');
        };

        eventSource.addEventListener('traceUpdate', function(e) {
            try {
                const data = JSON.parse(e.data);
                console.log('[TrueFlow] Received trace update:', Object.keys(data));

                // Update the visualization
                if (typeof loadVisualizationData === 'function') {
                    loadVisualizationData(data);
                } else if (window.explorer && typeof window.explorer.loadData === 'function') {
                    window.explorer.loadData(data);
                }

                // Flash status to show update received
                showConnectionStatus('connected', 'Updated ' + new Date().toLocaleTimeString());
            } catch (err) {
                console.error('[TrueFlow] Error processing update:', err);
            }
        });

        eventSource.onerror = function(e) {
            console.error('[TrueFlow] SSE error:', e);
            eventSource.close();

            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                showConnectionStatus('connecting', 'Reconnecting (' + reconnectAttempts + '/' + MAX_RECONNECT_ATTEMPTS + ')...');
                setTimeout(connect, RECONNECT_DELAY);
            } else {
                showConnectionStatus('error', 'Connection lost. Refresh to retry.');
            }
        };
    }

    // Start connection when page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', connect);
    } else {
        connect();
    }

    // Expose for debugging
    window.trueflowSSE = {
        reconnect: connect,
        getStatus: () => eventSource ? eventSource.readyState : -1
    };
})();
</script>
"""

        // Inject before </body>
        return htmlTemplate!!.replace("</body>", "$sseClientScript</body>")
    }

    private fun getDefaultHtml(): String {
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TrueFlow Interactive Explorer</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .message {
            text-align: center;
            padding: 40px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            max-width: 500px;
        }
        h2 { color: #4CAF50; margin-bottom: 20px; }
        p { color: #aaa; line-height: 1.6; }
        .status {
            display: inline-block;
            padding: 4px 12px;
            background: #4CAF50;
            color: white;
            border-radius: 20px;
            font-size: 12px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="message">
        <h2>🔄 TrueFlow Interactive Explorer</h2>
        <p>Waiting for trace data...</p>
        <p>Run your Python/Java code with TrueFlow tracing enabled to see the visualization here in real-time.</p>
        <div class="status">● Server Active</div>
    </div>
    <script>
        function loadVisualizationData(data) {
            // Replace this placeholder with actual visualization
            document.querySelector('.message').innerHTML =
                '<h2>✓ Data Received</h2>' +
                '<p>Trace data loaded. Full visualization requires the complete HTML template.</p>' +
                '<pre style="text-align:left;background:#2a2a3e;padding:20px;border-radius:8px;overflow:auto;max-height:400px;">' +
                JSON.stringify(data, null, 2).substring(0, 2000) + '...</pre>';
        }
    </script>
</body>
</html>
        """.trimIndent()
    }
}
