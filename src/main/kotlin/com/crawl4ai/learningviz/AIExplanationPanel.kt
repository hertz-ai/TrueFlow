package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonArray
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.fileChooser.FileChooser
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.JBUI
import java.awt.*
import java.awt.datatransfer.DataFlavor
import java.awt.event.ActionEvent
import java.awt.event.KeyEvent
import java.awt.image.BufferedImage
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import javax.imageio.ImageIO
import javax.swing.*

/**
 * AI Explanation Panel - Interactive chat interface with local VLM (Qwen3-VL).
 *
 * Features:
 * - Chat interface with conversation history (last 3 exchanges)
 * - Image/screenshot support (paste or attach) for visual queries
 * - Cross-tab context injection (dead code, performance, call traces)
 * - Public API for other panels to invoke explanations programmatically
 * - Direct HuggingFace model download with progress
 */
class AIExplanationPanel(private val project: Project) : JPanel(BorderLayout()) {

    // Model presets from https://docs.unsloth.ai/models/qwen3-vl-how-to-run-and-fine-tune
    data class ModelPreset(
        val displayName: String,
        val repoId: String,
        val fileName: String,
        val sizeMB: Int,
        val description: String,
        val hasVision: Boolean,
        val mmprojFile: String? = null  // Vision projector file for VL models
    )

    private val modelPresets = listOf(
        // Qwen3-VL models - excellent for code analysis
        // Note: mmproj file is required for vision - named mmproj-F16.gguf in each repo
        ModelPreset(
            "Qwen3-VL-2B Instruct Q4_K_XL (Recommended)",
            "unsloth/Qwen3-VL-2B-Instruct-GGUF",
            "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
            1500,
            "Vision+text, best for code analysis with diagrams",
            hasVision = true,
            mmprojFile = "mmproj-F16.gguf"
        ),
        ModelPreset(
            "Qwen3-VL-2B Thinking Q4_K_XL",
            "unsloth/Qwen3-VL-2B-Thinking-GGUF",
            "Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf",
            1500,
            "Vision+text with chain-of-thought reasoning",
            hasVision = true,
            mmprojFile = "mmproj-F16.gguf"
        ),
        ModelPreset(
            "Qwen3-VL-4B Instruct Q4_K_XL",
            "unsloth/Qwen3-VL-4B-Instruct-GGUF",
            "Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf",
            2800,
            "Larger model, better quality, needs ~6GB RAM",
            hasVision = true,
            mmprojFile = "mmproj-F16.gguf"
        ),
        // Gemma 3 models - Google's multimodal
        ModelPreset(
            "Gemma-3-4B IT Q4_K_XL",
            "unsloth/gemma-3-4b-it-GGUF",
            "gemma-3-4b-it-Q4_K_XL.gguf",
            2700,
            "Vision+text, Google Gemma 3, well-tested multimodal",
            hasVision = true,
            mmprojFile = "mmproj-F16.gguf"
        ),
        ModelPreset(
            "Gemma-3-1B IT Q4_K_M",
            "unsloth/gemma-3-1b-it-GGUF",
            "gemma-3-1b-it-Q4_K_M.gguf",
            600,
            "Text-only, compact & fast, good for quick analysis",
            hasVision = false
        ),
        // SmolVLM - ultra-compact vision model
        ModelPreset(
            "SmolVLM-256M-Instruct",
            "ggml-org/SmolVLM-256M-Instruct-GGUF",
            "SmolVLM-256M-Instruct-Q8_0.gguf",
            280,
            "Tiny vision model, ultra-fast, basic image analysis",
            hasVision = true,
            mmprojFile = "mmproj-SmolVLM-256M-Instruct-f16.gguf"
        ),
        // Text-only option
        ModelPreset(
            "Qwen3-2B Text-Only Q4_K_M",
            "unsloth/Qwen3-2B-Instruct-GGUF",
            "Qwen3-2B-Instruct-Q4_K_M.gguf",
            1100,
            "Text-only, fastest, no vision support",
            hasVision = false
        ),
        ModelPreset(
            "Custom HuggingFace Model...",
            "",
            "",
            0,
            "Enter a custom HuggingFace GGUF model URL",
            hasVision = false
        )
    )

    // Chat history (role, content, optional image base64)
    data class ChatMessage(
        val role: String,  // "user" or "assistant"
        val content: String,
        val imageBase64: String? = null
    )

    private val conversationHistory = mutableListOf<ChatMessage>()
    private val maxHistorySize = 3  // Keep last 3 exchanges (6 messages)

    // UI Components - Rich web-based chat panel
    private var webChatPanel: AIChatWebPanel? = null
    private val statusLabel = JBLabel("AI Ready")
    private val benchmarkLabel = JBLabel("")  // Shows CPU/GPU benchmark results
    private val progressBar = JProgressBar(0, 100)

    // Model selection
    private val modelComboBox = ComboBox(modelPresets.map { it.displayName }.toTypedArray())
    private val customUrlField = JBTextField()
    private val customUrlPanel = JPanel(BorderLayout())
    private val downloadButton = JButton("Download Model")
    private val startServerButton = JButton("Start AI Server")

    // HuggingFace search
    private val hfSearchField = JBTextField()
    private val hfSearchButton = JButton("Search HF")
    private val hfResultsList = JList<String>()
    private val hfSearchPanel = JPanel(BorderLayout())
    private var hfSearchResults = mutableListOf<Pair<String, Int>>()  // (model_id, downloads)
    private var selectedHFModel: String? = null

    // Context injection
    private val contextComboBox = ComboBox(arrayOf(
        "No additional context",
        "Include Dead Code data",
        "Include Performance data",
        "Include Call Trace data",
        "Include Current Diagram",
        "Include All Tab Data"
    ))

    // State
    private var currentModelFile: String? = null
    private var pendingImage: String? = null  // Base64 encoded image waiting to be sent
    private var serverProcess: Process? = null
    private val apiBase = "http://127.0.0.1:8080/v1"
    private val modelsDir = File(System.getProperty("user.home"), ".trueflow/models")
    private val serverStatusFile = File(System.getProperty("user.home"), ".trueflow/server_status.json")
    private var statusCheckTimer: javax.swing.Timer? = null

    // Chunked context and interrupt control
    @Volatile private var isOperationCancelled = false
    private val TOKEN_CHUNK_SIZE = 200  // Tokens per chunk

    // Cross-tab data references (set by EnhancedLearningFlowToolWindow)
    private var deadCodeData: JsonObject? = null
    private var performanceData: JsonObject? = null
    private var callTraceData: JsonObject? = null
    private var currentDiagramData: String? = null

    // Hub client for real-time cross-IDE coordination
    private val hubClient = HubClient.getInstance()

    // GPU acceleration with benchmark results
    private var gpuAvailable: String = "none"  // "cuda", "metal", or "none"
    private var useGpuAcceleration = false
    private var cpuTokensPerSecond: Double = 0.0
    private var gpuTokensPerSecond: Double = 0.0
    private var benchmarkCompleted = false
    private var recommendedBackend: String = "cpu"  // "cpu" or "gpu"

    // Server status data class for cross-IDE coordination
    data class ServerStatus(
        val running: Boolean,
        val pid: Int?,
        val port: Int,
        val model: String?,
        val startedBy: String,
        val startedAt: String
    )

    init {
        modelsDir.mkdirs()
        detectGpuAcceleration()
        setupUI()
        setupHubHandlers()
        checkModelStatus()
        connectToHub()
        // Check if server is already running (e.g., from previous session or another IDE)
        checkExistingServer()
        // Register listener to reinitialize browser after indexing completes
        setupIndexingListener()
    }

    /**
     * Detect available GPU acceleration (CUDA on Windows/Linux, Metal on macOS).
     */
    private fun detectGpuAcceleration() {
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val osName = System.getProperty("os.name").lowercase()
                when {
                    osName.contains("mac") -> {
                        // macOS - Metal is always available on modern Macs
                        gpuAvailable = "metal"
                        PluginLogger.info("[TrueFlow] GPU: Metal available on macOS")
                    }
                    osName.contains("win") || osName.contains("linux") -> {
                        // Check for CUDA via nvidia-smi
                        try {
                            val process = ProcessBuilder("nvidia-smi", "--query-gpu=name", "--format=csv,noheader")
                                .redirectErrorStream(true)
                                .start()
                            val completed = process.waitFor(3, TimeUnit.SECONDS)
                            if (completed && process.exitValue() == 0) {
                                gpuAvailable = "cuda"
                                PluginLogger.info("[TrueFlow] GPU: CUDA available")
                            }
                        } catch (e: Exception) {
                            PluginLogger.info("[TrueFlow] GPU: No CUDA detected")
                        }
                    }
                }
            } catch (e: Exception) {
                PluginLogger.warn("[TrueFlow] GPU detection failed: ${e.message}")
            }
        }
    }

    /**
     * Run a quick benchmark to compare CPU vs GPU performance.
     * Uses llama-bench if available, otherwise estimates based on a short inference test.
     * Called after server starts - runs a quick inference and measures tokens/second.
     */
    private fun runBenchmark(onComplete: (cpuTps: Double, gpuTps: Double, recommended: String) -> Unit) {
        if (gpuAvailable == "none") {
            // No GPU, just set CPU as recommended
            cpuTokensPerSecond = 50.0  // Default estimate
            gpuTokensPerSecond = 0.0
            recommendedBackend = "cpu"
            benchmarkCompleted = true
            onComplete(cpuTokensPerSecond, gpuTokensPerSecond, recommendedBackend)
            return
        }

        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                // Use the /health endpoint to get server info, or do a quick completion
                val startTime = System.currentTimeMillis()
                val testPrompt = "Count from 1 to 10:"
                val response = callLLMForBenchmark(testPrompt, 50)  // Generate ~50 tokens
                val endTime = System.currentTimeMillis()

                val durationSeconds = (endTime - startTime) / 1000.0
                val estimatedTokens = response.split(" ").size + 10  // Rough token estimate
                val tokensPerSecond = if (durationSeconds > 0) estimatedTokens / durationSeconds else 0.0

                // Store based on current GPU setting
                if (useGpuAcceleration) {
                    gpuTokensPerSecond = tokensPerSecond
                } else {
                    cpuTokensPerSecond = tokensPerSecond
                }

                // Determine recommendation: GPU is only better if significantly faster (>20% improvement)
                recommendedBackend = when {
                    gpuTokensPerSecond <= 0 -> "cpu"
                    cpuTokensPerSecond <= 0 -> "gpu"
                    gpuTokensPerSecond > cpuTokensPerSecond * 1.2 -> "gpu"
                    else -> "cpu"  // Prefer CPU if similar or CPU is faster
                }

                benchmarkCompleted = true
                PluginLogger.info("[TrueFlow] Benchmark: CPU=${cpuTokensPerSecond.toInt()} t/s, GPU=${gpuTokensPerSecond.toInt()} t/s, Recommended=$recommendedBackend")

                SwingUtilities.invokeLater {
                    onComplete(cpuTokensPerSecond, gpuTokensPerSecond, recommendedBackend)
                }
            } catch (e: Exception) {
                PluginLogger.warn("[TrueFlow] Benchmark failed: ${e.message}")
                benchmarkCompleted = true
                SwingUtilities.invokeLater {
                    onComplete(cpuTokensPerSecond, gpuTokensPerSecond, "cpu")
                }
            }
        }
    }

    /**
     * Simple LLM call for benchmarking - doesn't use streaming
     */
    private fun callLLMForBenchmark(prompt: String, maxTokens: Int): String {
        val url = URL("$apiBase/chat/completions")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 30000
        conn.readTimeout = 60000

        val requestBody = """
            {
                "model": "local",
                "messages": [{"role": "user", "content": "$prompt"}],
                "max_tokens": $maxTokens,
                "temperature": 0.1,
                "stream": false
            }
        """.trimIndent()

        conn.outputStream.use { os ->
            os.write(requestBody.toByteArray())
        }

        if (conn.responseCode != 200) {
            return ""
        }

        val response = conn.inputStream.bufferedReader().readText()
        val json = Gson().fromJson(response, JsonObject::class.java)
        return json.getAsJsonArray("choices")
            ?.get(0)?.asJsonObject
            ?.getAsJsonObject("message")
            ?.get("content")?.asString ?: ""
    }

    /**
     * Get benchmark status string for UI display
     */
    fun getBenchmarkStatus(): String {
        return when {
            !benchmarkCompleted -> "Benchmark pending..."
            gpuAvailable == "none" -> "CPU: ${cpuTokensPerSecond.toInt()} t/s"
            else -> "CPU: ${cpuTokensPerSecond.toInt()} t/s | GPU: ${gpuTokensPerSecond.toInt()} t/s | Best: ${recommendedBackend.uppercase()}"
        }
    }

    /**
     * Listen for indexing completion to reinitialize the browser if needed.
     * The JCEF browser can become disposed during indexing operations.
     */
    private fun setupIndexingListener() {
        project.messageBus.connect().subscribe(DumbService.DUMB_MODE, object : DumbService.DumbModeListener {
            override fun exitDumbMode() {
                PluginLogger.info("[TrueFlow] Indexing completed - checking browser state")
                SwingUtilities.invokeLater {
                    webChatPanel?.reinitializeIfNeeded()
                }
            }
        })
    }

    /**
     * Check if AI server is already running on startup.
     * This handles the case where PyCharm restarts but the server is still running.
     */
    private fun checkExistingServer() {
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val isRunning = checkServerHealth()
                if (isRunning) {
                    // Server is running - check status file for details
                    val status = readServerStatus()
                    val model = status?.model ?: "Unknown model"
                    val startedBy = status?.startedBy ?: "external process"

                    SwingUtilities.invokeLater {
                        startServerButton.text = if (status?.startedBy != null) {
                            "Using External Server ($startedBy)"
                        } else {
                            "Stop AI Server"
                        }
                        startServerButton.isEnabled = true
                        statusLabel.text = "AI Server already running - Ready!"
                        webChatPanel?.setServerRunning(true, model)
                        webChatPanel?.updateStatus("Server running: $model")
                        PluginLogger.info("[TrueFlow] Detected existing AI server on startup (model: $model)")
                    }
                }
            } catch (e: Exception) {
                PluginLogger.debug("[TrueFlow] No existing server detected: ${e.message}")
            }
        }
    }

    private fun setupHubHandlers() {
        // Handle AI server status updates from other IDEs
        hubClient.on("ai_server_status") { message ->
            val data = message.data ?: return@on
            val running = data.get("running")?.asBoolean ?: false
            val startedBy = data.get("started_by")?.asString ?: "external"
            val model = data.get("model")?.asString ?: ""

            SwingUtilities.invokeLater {
                if (running && serverProcess == null) {
                    // Server started by another IDE
                    startServerButton.text = "Using External Server ($startedBy)"
                    startServerButton.isEnabled = false
                    statusLabel.text = "AI Server running (started by $startedBy) - Ready!"
                    webChatPanel?.setServerRunning(true, model)
                    webChatPanel?.updateStatus("Connected via $startedBy: $model")
                } else if (!running) {
                    // Server stopped
                    startServerButton.text = "Start AI Server"
                    startServerButton.isEnabled = true
                    statusLabel.text = "AI Server stopped"
                    webChatPanel?.setServerRunning(false)
                    webChatPanel?.updateStatus("Server stopped")
                }
            }
        }

        // Handle legacy commands from MCP Hub
        hubClient.on("command") { message ->
            val command = message.command ?: return@on

            when (command) {
                "start_ai_server" -> SwingUtilities.invokeLater { startServer() }
                "stop_ai_server" -> SwingUtilities.invokeLater { stopServer() }
            }
        }

        // Handle RPC requests from MCP Hub (with response)
        // NOTE: This handler runs on a background thread (not EDT) for performance
        hubClient.on("rpc_request") { message ->
            val requestId = message.request_id ?: return@on
            val command = message.command ?: return@on
            val args = message.args ?: JsonObject()

            val responseData = JsonObject()

            when (command) {
                "get_trace_data" -> {
                    // Safe read-only access to cached data
                    callTraceData?.let { responseData.add("calls", it.getAsJsonArray("calls")) }
                    responseData.addProperty("total_calls", callTraceData?.get("total_calls")?.asInt ?: 0)
                    hubClient.sendRpcResponse(requestId, responseData)
                }

                "get_dead_code" -> {
                    deadCodeData?.let {
                        responseData.add("dead_functions", it.getAsJsonArray("dead_functions"))
                        responseData.add("called_functions", it.getAsJsonArray("called_functions"))
                    }
                    hubClient.sendRpcResponse(requestId, responseData)
                }

                "get_performance_data" -> {
                    performanceData?.let {
                        responseData.add("hotspots", it.getAsJsonArray("hotspots"))
                        responseData.addProperty("total_time_ms", it.get("total_time_ms")?.asDouble ?: 0.0)
                    }
                    hubClient.sendRpcResponse(requestId, responseData)
                }

                "export_diagram" -> {
                    val format = args.get("format")?.asString ?: "plantuml"
                    responseData.addProperty("format", format)
                    responseData.addProperty("diagram", currentDiagramData ?: "")
                    hubClient.sendRpcResponse(requestId, responseData)
                }

                "start_ai_server" -> {
                    // Start server on EDT, respond when done
                    ApplicationManager.getApplication().invokeLater {
                        startServer()
                        // Server start is async, respond with acknowledgment
                        val startResponse = JsonObject().apply {
                            addProperty("status", "started")
                            addProperty("port", 8080)
                        }
                        hubClient.sendRpcResponse(requestId, startResponse)
                    }
                    // Don't send response here - will be sent after server starts
                    return@on
                }

                "stop_ai_server" -> {
                    ApplicationManager.getApplication().invokeLater {
                        stopServer()
                    }
                    responseData.addProperty("status", "stopped")
                    hubClient.sendRpcResponse(requestId, responseData)
                }

                else -> {
                    responseData.addProperty("error", "Unknown command: $command")
                    hubClient.sendRpcResponse(requestId, responseData)
                }
            }
        }
    }

    private fun connectToHub() {
        // Connect to MCP Hub for real-time cross-IDE coordination
        CompletableFuture.runAsync {
            hubClient.setProject(project)
            val connected = hubClient.connect()
            if (connected) {
                PluginLogger.info("[TrueFlow] Connected to MCP Hub for cross-IDE coordination")
            } else {
                PluginLogger.info("[TrueFlow] Hub not available, using file-based status polling")
                // Fall back to polling if hub not available
                SwingUtilities.invokeLater { startStatusPolling() }
            }
        }
    }

    private fun readServerStatus(): ServerStatus? {
        return try {
            if (serverStatusFile.exists()) {
                val content = serverStatusFile.readText()
                val json = Gson().fromJson(content, JsonObject::class.java)
                ServerStatus(
                    running = json.get("running")?.asBoolean ?: false,
                    pid = json.get("pid")?.asInt,
                    port = json.get("port")?.asInt ?: 8080,
                    model = json.get("model")?.asString,
                    startedBy = json.get("startedBy")?.asString ?: "unknown",
                    startedAt = json.get("startedAt")?.asString ?: ""
                )
            } else null
        } catch (e: Exception) {
            PluginLogger.warn("Failed to read server status: ${e.message}")
            null
        }
    }

    private fun writeServerStatus(status: ServerStatus?) {
        try {
            if (status == null) {
                if (serverStatusFile.exists()) {
                    serverStatusFile.delete()
                }
            } else {
                val json = JsonObject().apply {
                    addProperty("running", status.running)
                    status.pid?.let { addProperty("pid", it) }
                    addProperty("port", status.port)
                    status.model?.let { addProperty("model", it) }
                    addProperty("startedBy", status.startedBy)
                    addProperty("startedAt", status.startedAt)
                }
                serverStatusFile.writeText(Gson().toJson(json))
            }
        } catch (e: Exception) {
            PluginLogger.warn("Failed to write server status: ${e.message}")
        }
    }

    private fun checkServerHealth(): Boolean {
        return try {
            val conn = URL("http://127.0.0.1:8080/health").openConnection() as HttpURLConnection
            conn.connectTimeout = 2000
            conn.readTimeout = 2000
            conn.responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    private fun startStatusPolling() {
        statusCheckTimer = javax.swing.Timer(2000) {
            val status = readServerStatus()
            val isRunning = checkServerHealth()

            SwingUtilities.invokeLater {
                if (isRunning && serverProcess == null && status?.running == true) {
                    // Server running from another IDE
                    startServerButton.text = "Using External Server (${status.startedBy})"
                    startServerButton.isEnabled = false
                    statusLabel.text = "AI Server running (started by ${status.startedBy})"
                    webChatPanel?.setServerRunning(true, status.model ?: "")
                    webChatPanel?.updateStatus("Connected via ${status.startedBy}")
                } else if (!isRunning && serverProcess != null) {
                    // Our server died
                    serverProcess = null
                    startServerButton.text = "Start AI Server"
                    startServerButton.isEnabled = true
                    statusLabel.text = "AI Server stopped unexpectedly"
                    webChatPanel?.setServerRunning(false)
                    webChatPanel?.updateStatus("Server stopped unexpectedly")
                }
            }
        }
        statusCheckTimer?.start()
    }

    private fun stopStatusPolling() {
        statusCheckTimer?.stop()
        statusCheckTimer = null
    }

    private fun setupUI() {
        border = JBUI.Borders.empty(5)

        // Initialize the rich web-based chat panel
        webChatPanel = AIChatWebPanel(project)

        // Wire up callbacks from the web panel
        webChatPanel?.onSendMessage = { message, imageBase64 ->
            sendMessageFromWeb(message, imageBase64)
        }

        webChatPanel?.onStartServer = {
            toggleServer()
        }

        webChatPanel?.onStopServer = {
            stopServer()
        }

        webChatPanel?.onDownloadModel = {
            showModelDownloadDialog()
        }

        webChatPanel?.onAttachImage = {
            attachImage()
        }

        webChatPanel?.onPasteImage = {
            pasteImageFromClipboard()
        }

        webChatPanel?.onClearHistory = {
            clearHistory()
        }

        webChatPanel?.onMaximize = {
            showMaximizedChat()
        }

        webChatPanel?.onContextChanged = { index ->
            // Sync the context selection with the combo box (for consistency)
            if (index in 0 until contextComboBox.itemCount) {
                contextComboBox.selectedIndex = index
            }
        }

        webChatPanel?.onStopOperation = {
            // Set cancel flag to interrupt chunked operations or MCP calls
            isOperationCancelled = true
            webChatPanel?.showStopButton(false)
            webChatPanel?.setThinking(false)
            webChatPanel?.addSystemMessage("Operation cancelled by user")
        }

        webChatPanel?.onDeployNewModel = {
            // Stop current server and start with new model
            stopServer()
            // Wait a moment for server to stop then start with new model
            javax.swing.Timer(1000) { _ ->
                startServer()
            }.apply {
                isRepeats = false
                start()
            }
        }

        // Show MCP status if hub is connected
        if (hubClient.isConnected()) {
            webChatPanel?.setMCPStatus(true, "MCP Hub: ws://127.0.0.1:5680 | Project: ${hubClient.getProjectId()}")
        }

        // Add the web panel as the main content
        add(webChatPanel, BorderLayout.CENTER)

        // Bottom status bar (minimal, since most status is shown in web panel)
        val statusBar = JPanel(BorderLayout())
        statusBar.border = JBUI.Borders.empty(2, 5)
        statusBar.add(statusLabel, BorderLayout.WEST)
        progressBar.isVisible = false
        statusBar.add(progressBar, BorderLayout.CENTER)
        // Benchmark results on the right
        benchmarkLabel.foreground = java.awt.Color.GRAY
        benchmarkLabel.font = benchmarkLabel.font.deriveFont(11f)
        statusBar.add(benchmarkLabel, BorderLayout.EAST)
        add(statusBar, BorderLayout.SOUTH)
    }

    private fun showModelDownloadDialog() {
        val dialog = JDialog(SwingUtilities.getWindowAncestor(this) as? Frame, "Download AI Model", true)
        dialog.layout = BorderLayout()
        dialog.preferredSize = Dimension(500, 400)

        val contentPanel = JPanel()
        contentPanel.layout = BoxLayout(contentPanel, BoxLayout.Y_AXIS)
        contentPanel.border = JBUI.Borders.empty(10)

        // Model selection
        val modelPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        modelPanel.add(JBLabel("Select Model: "))
        modelComboBox.preferredSize = Dimension(350, 30)
        modelComboBox.addActionListener { onModelSelectionChanged() }
        modelPanel.add(modelComboBox)
        contentPanel.add(modelPanel)

        // Custom URL panel (hidden by default)
        customUrlPanel.isVisible = false
        customUrlField.preferredSize = Dimension(400, 30)
        customUrlField.toolTipText = "Enter HuggingFace URL"
        customUrlPanel.add(JBLabel("URL: "), BorderLayout.WEST)
        customUrlPanel.add(customUrlField, BorderLayout.CENTER)
        contentPanel.add(customUrlPanel)

        // HuggingFace search panel
        hfSearchPanel.border = BorderFactory.createTitledBorder("Search HuggingFace GGUF Models")
        hfSearchPanel.isVisible = false
        val hfSearchInputPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        hfSearchField.preferredSize = Dimension(300, 30)
        hfSearchField.toolTipText = "Search for GGUF models (e.g., qwen, llama, gemma)"
        hfSearchButton.addActionListener { searchHuggingFace() }
        hfSearchInputPanel.add(hfSearchField)
        hfSearchInputPanel.add(hfSearchButton)

        hfResultsList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        hfResultsList.addListSelectionListener { e ->
            if (!e.valueIsAdjusting && hfResultsList.selectedIndex >= 0) {
                val selected = hfSearchResults.getOrNull(hfResultsList.selectedIndex)
                if (selected != null) {
                    selectedHFModel = selected.first
                    startServerButton.text = "Start with HF Model"
                    startServerButton.isEnabled = true
                    statusLabel.text = "Selected: ${selected.first}"
                }
            }
        }
        val hfScrollPane = JBScrollPane(hfResultsList)
        hfScrollPane.preferredSize = Dimension(450, 150)

        hfSearchPanel.add(hfSearchInputPanel, BorderLayout.NORTH)
        hfSearchPanel.add(hfScrollPane, BorderLayout.CENTER)
        contentPanel.add(hfSearchPanel)

        // Context selection
        val contextPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        contextPanel.add(JBLabel("Context: "))
        contextComboBox.preferredSize = Dimension(200, 30)
        contextPanel.add(contextComboBox)
        contentPanel.add(contextPanel)

        // Button panel
        val buttonPanel = JPanel(FlowLayout(FlowLayout.RIGHT))
        downloadButton.addActionListener {
            downloadSelectedModel()
        }
        startServerButton.addActionListener {
            toggleServer()
            dialog.dispose()
        }
        startServerButton.isEnabled = false
        buttonPanel.add(downloadButton)
        buttonPanel.add(startServerButton)
        buttonPanel.add(JButton("Close").apply {
            addActionListener { dialog.dispose() }
        })

        dialog.add(contentPanel, BorderLayout.CENTER)
        dialog.add(buttonPanel, BorderLayout.SOUTH)
        dialog.pack()
        dialog.setLocationRelativeTo(this)

        // Check model status before showing
        checkModelStatus()
        dialog.isVisible = true
    }

    private fun showMaximizedChat() {
        val frame = JFrame("TrueFlow AI Chat - Full Screen")
        frame.defaultCloseOperation = JFrame.DISPOSE_ON_CLOSE
        frame.preferredSize = Dimension(1200, 800)

        // Create a new web panel for the maximized view
        val maximizedPanel = AIChatWebPanel(project)

        // Copy conversation history to maximized panel
        for (msg in conversationHistory) {
            if (msg.role == "user") {
                maximizedPanel.addUserMessage(msg.content, msg.imageBase64)
            } else {
                maximizedPanel.addAssistantMessage(msg.content)
            }
        }

        // Wire up the same callbacks
        maximizedPanel.onSendMessage = { message, imageBase64 ->
            sendMessageFromWeb(message, imageBase64)
            // Also add to the maximized panel
            maximizedPanel.addUserMessage(message, imageBase64)
            maximizedPanel.setThinking(true)
        }

        maximizedPanel.onStartServer = { toggleServer() }
        maximizedPanel.onStopServer = { stopServer() }
        maximizedPanel.onDownloadModel = { showModelDownloadDialog() }
        maximizedPanel.onAttachImage = { attachImageForPanel(maximizedPanel) }
        maximizedPanel.onPasteImage = { pasteImageForPanel(maximizedPanel) }
        maximizedPanel.onClearHistory = {
            clearHistory()
            maximizedPanel.clearChat()
        }
        maximizedPanel.onMaximize = { frame.dispose() }  // Close = restore

        // Update server status
        val serverRunning = isServerRunning()
        maximizedPanel.setServerRunning(serverRunning, currentModelFile?.substringAfterLast("/") ?: "")

        frame.contentPane.add(maximizedPanel)
        frame.pack()
        frame.setLocationRelativeTo(null)
        frame.isVisible = true
    }

    private fun sendMessageFromWeb(message: String, imageBase64: String?) {
        if (message.isEmpty() && imageBase64 == null) return

        // Check if server is running
        val serverRunning = isServerRunning()
        if (!serverRunning) {
            webChatPanel?.addSystemMessage("Please start the AI server first. Click 'Download Model' then 'Start Server'.")
            return
        }

        // Reset cancel flag
        isOperationCancelled = false

        // Build context from selected tab
        val contextText = buildContextFromSelection()

        // Add user message to history
        val userMessage = ChatMessage("user", message, imageBase64)
        conversationHistory.add(userMessage)
        trimHistory()

        // Show user message in chat
        webChatPanel?.addUserMessage(message, imageBase64)
        webChatPanel?.setThinking(true)
        webChatPanel?.updateStatus("Thinking...")

        // Send to LLM asynchronously
        CompletableFuture.runAsync {
            try {
                // Estimate tokens (rough: 1 token ≈ 4 chars)
                val estimatedTokens = contextText.length / 4

                val response = if (estimatedTokens > TOKEN_CHUNK_SIZE) {
                    // Large context - send in chunks without history
                    sendWithChunkedContext(message, contextText, imageBase64, estimatedTokens)
                } else {
                    // Small context - normal call
                    callLLM(message, contextText, imageBase64)
                }

                if (isOperationCancelled) return@runAsync

                // Add assistant response to history
                conversationHistory.add(ChatMessage("assistant", response))
                trimHistory()

                SwingUtilities.invokeLater {
                    webChatPanel?.setThinking(false)
                    webChatPanel?.showStopButton(false)
                    webChatPanel?.addAssistantMessage(response)
                    webChatPanel?.updateStatus("Ready")
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    webChatPanel?.setThinking(false)
                    webChatPanel?.showStopButton(false)
                    webChatPanel?.addSystemMessage("Error: ${e.message}")
                    webChatPanel?.updateStatus("Error occurred")
                }
            }
        }
    }

    /**
     * Send context in chunks for large contexts (>200 tokens).
     * Skips conversation history during chunked calls.
     */
    private fun sendWithChunkedContext(
        userPrompt: String,
        fullContext: String,
        imageBase64: String?,
        totalTokens: Int
    ): String {
        val chunkSize = TOKEN_CHUNK_SIZE * 4  // Convert tokens to chars
        val chunks = fullContext.chunked(chunkSize)
        val responses = mutableListOf<String>()

        SwingUtilities.invokeLater {
            webChatPanel?.showStopButton(true)
            webChatPanel?.updateStatus("Sending context in chunks...")
        }

        for ((index, chunk) in chunks.withIndex()) {
            if (isOperationCancelled) {
                return "Operation cancelled by user"
            }

            val currentOffset = index * TOKEN_CHUNK_SIZE
            val nextOffset = minOf((index + 1) * TOKEN_CHUNK_SIZE, totalTokens)

            SwingUtilities.invokeLater {
                webChatPanel?.setChunkProgress(currentOffset, totalTokens,
                    "Fetching $currentOffset-$nextOffset of $totalTokens tokens...")
            }

            // For all chunks, include the original question so LLM has context
            val prompt = if (index == 0) {
                "$userPrompt\n\n[Context chunk ${index + 1}/${chunks.size}]:\n$chunk"
            } else {
                "Original question: $userPrompt\n\n[Context chunk ${index + 1}/${chunks.size}]:\n$chunk\n\nAnalyze this additional context chunk and provide relevant insights."
            }

            // Update thinking status with chunk info
            SwingUtilities.invokeLater {
                webChatPanel?.setThinking(true, "Analyzing chunk ${index + 1}/${chunks.size}...")
            }

            // Call LLM WITHOUT history for chunked calls
            val response = callLLMWithoutHistory(prompt, imageBase64, userPrompt)
            responses.add(response)

            // Show actual AI response for each chunk (not just "processed" message)
            if (chunks.size > 1) {
                SwingUtilities.invokeLater {
                    webChatPanel?.addAssistantMessage("📦 **Chunk ${index + 1}/${chunks.size}:**\n\n$response")

                    // If not last chunk, show continuation message in thinking area
                    if (index < chunks.size - 1) {
                        webChatPanel?.setThinking(true, "Processing next chunk (${index + 2}/${chunks.size})...")
                    }
                }
            }
        }

        SwingUtilities.invokeLater {
            webChatPanel?.setChunkProgress(0, 0, "")
        }

        // If multiple responses, combine them or take the last meaningful one
        return if (responses.size == 1) {
            responses[0]
        } else {
            // Filter out unhelpful responses
            val unhelpfulPatterns = listOf(
                "need more context",
                "can't continue",
                "cannot continue",
                "please provide",
                "clarify your question",
                "additional context"
            )
            val combined = responses.filter { response ->
                response.isNotBlank() && unhelpfulPatterns.none { pattern ->
                    response.contains(pattern, ignoreCase = true)
                }
            }

            when {
                combined.isEmpty() -> "Unable to analyze the context. Please try with a more specific question or smaller context."
                combined.size > 1 -> "Based on analyzing all context chunks:\n\n${combined.last()}"
                else -> combined.first()
            }
        }
    }

    /**
     * Call LLM without conversation history (for chunked context).
     */
    private fun callLLMWithoutHistory(prompt: String, imageBase64: String?, originalQuestion: String? = null): String {
        val messages = mutableListOf<Map<String, Any>>()

        // Sanitize all text inputs
        val sanitizedPrompt = sanitizeForLLM(prompt)
        val sanitizedQuestion = originalQuestion?.let { sanitizeForLLM(it) }

        // System prompt with original question context for better chunk analysis
        val systemContent = if (sanitizedQuestion != null) {
            sanitizeForLLM("TrueFlow AI: You are analyzing code execution context in chunks. The user's question is: \"$sanitizedQuestion\". Analyze the provided context chunk and extract relevant information to answer this question. Focus on facts from the context, not speculation.")
        } else {
            "TrueFlow AI: Analyze the provided context and answer concisely."
        }
        messages.add(mapOf(
            "role" to "system",
            "content" to systemContent
        ))

        // User message only (no history)
        if (imageBase64 != null && modelHasVision()) {
            messages.add(mapOf(
                "role" to "user",
                "content" to listOf(
                    mapOf("type" to "text", "text" to sanitizedPrompt),
                    mapOf("type" to "image_url", "image_url" to mapOf("url" to "data:image/png;base64,$imageBase64"))
                )
            ))
        } else {
            messages.add(mapOf("role" to "user", "content" to sanitizedPrompt))
        }

        val requestBody = Gson().toJson(mapOf(
            "model" to "qwen3-vl",
            "messages" to messages,
            "max_tokens" to 1024,
            "temperature" to 0.7
        ))

        val url = URL("$apiBase/chat/completions")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 30000
        conn.readTimeout = 120000

        OutputStreamWriter(conn.outputStream).use { it.write(requestBody) }

        val responseCode = conn.responseCode
        if (responseCode != 200) {
            val errorBody = conn.errorStream?.let { BufferedReader(InputStreamReader(it)).use { r -> r.readText() } } ?: ""
            val errorMsg = when (responseCode) {
                500 -> "Server error (500): $errorBody. This may be due to: (1) Model not fully loaded - wait a few seconds, (2) Out of memory - try a smaller model, (3) Invalid request format."
                503 -> "Server unavailable (503): The AI server is still initializing. Please wait a moment."
                else -> "HTTP $responseCode: $errorBody"
            }
            throw RuntimeException(errorMsg)
        }

        val response = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
        val json = Gson().fromJson(response, JsonObject::class.java)

        return json.getAsJsonArray("choices")
            ?.get(0)?.asJsonObject
            ?.getAsJsonObject("message")
            ?.get("content")?.asString
            ?: "No response"
    }

    private fun attachImageForPanel(panel: AIChatWebPanel) {
        // Use JFileChooser with image preview
        val fileChooser = JFileChooser()
        fileChooser.dialogTitle = "Select Image"
        fileChooser.fileSelectionMode = JFileChooser.FILES_ONLY
        fileChooser.isAcceptAllFileFilterUsed = false

        fileChooser.addChoosableFileFilter(javax.swing.filechooser.FileNameExtensionFilter(
            "Image Files (*.png, *.jpg, *.jpeg, *.gif, *.bmp)",
            "png", "jpg", "jpeg", "gif", "bmp"
        ))

        val previewPanel = ImagePreviewPanel()
        fileChooser.accessory = previewPanel
        fileChooser.addPropertyChangeListener { evt ->
            if (evt.propertyName == JFileChooser.SELECTED_FILE_CHANGED_PROPERTY) {
                val file = evt.newValue as? File
                previewPanel.setImage(file)
            }
        }

        val result = fileChooser.showOpenDialog(this)
        if (result == JFileChooser.APPROVE_OPTION) {
            val file = fileChooser.selectedFile
            try {
                val image = ImageIO.read(file)
                val base64 = encodeImageToBase64(image)
                pendingImage = base64
                panel.setImageAttached(true, file.name, base64)
            } catch (e: Exception) {
                panel.addSystemMessage("Failed to load image: ${e.message}")
            }
        }
    }

    private fun pasteImageForPanel(panel: AIChatWebPanel) {
        try {
            val clipboard = Toolkit.getDefaultToolkit().systemClipboard
            if (clipboard.isDataFlavorAvailable(DataFlavor.imageFlavor)) {
                val image = clipboard.getData(DataFlavor.imageFlavor) as Image
                val bufferedImage = toBufferedImage(image)
                val base64 = encodeImageToBase64(bufferedImage)
                pendingImage = base64
                panel.setImageAttached(true, "Screenshot from clipboard", base64)
            } else {
                panel.addSystemMessage("No image in clipboard")
            }
        } catch (e: Exception) {
            panel.addSystemMessage("Failed to paste image: ${e.message}")
        }
    }

    private fun buildWelcomeMessage(): String {
        return """
            |TrueFlow AI Assistant
            |=====================
            |
            |I'm a local AI powered by Qwen3-VL running on your machine.
            |I can help you understand your code execution traces.
            |
            |What I can do:
            |• Explain why code is marked as dead/unreachable
            |• Analyze performance bottlenecks from call traces
            |• Explain exceptions and errors in your traces
            |• Answer questions about the sequence diagrams
            |• Analyze screenshots (paste with Ctrl+V or attach)
            |
            |Setup:
            |1. Select a model and click "Download Model"
            |2. Click "Start AI Server" to launch the LLM
            |3. Select context from other tabs if needed
            |4. Type your question and press Ctrl+Enter or click Send
            |
            |Tip: Paste screenshots directly with Ctrl+V for visual analysis!
        """.trimMargin()
    }

    // ==================== Chat Functions ====================

    private fun clearHistory() {
        conversationHistory.clear()
        webChatPanel?.clearChat()
        pendingImage = null
    }

    private fun trimHistory() {
        // Keep only last N exchanges (N*2 messages)
        while (conversationHistory.size > maxHistorySize * 2) {
            conversationHistory.removeAt(0)
        }
    }

    // ==================== Image Functions ====================

    private fun attachImage() {
        // Use JFileChooser with image preview instead of IntelliJ's FileChooser
        val fileChooser = JFileChooser()
        fileChooser.dialogTitle = "Select Image"
        fileChooser.fileSelectionMode = JFileChooser.FILES_ONLY
        fileChooser.isAcceptAllFileFilterUsed = false

        // Add image file filter
        fileChooser.addChoosableFileFilter(javax.swing.filechooser.FileNameExtensionFilter(
            "Image Files (*.png, *.jpg, *.jpeg, *.gif, *.bmp)",
            "png", "jpg", "jpeg", "gif", "bmp"
        ))

        // Add image preview accessory panel
        val previewPanel = ImagePreviewPanel()
        fileChooser.accessory = previewPanel
        fileChooser.addPropertyChangeListener { evt ->
            if (evt.propertyName == JFileChooser.SELECTED_FILE_CHANGED_PROPERTY) {
                val file = evt.newValue as? File
                previewPanel.setImage(file)
            }
        }

        val result = fileChooser.showOpenDialog(this)
        if (result == JFileChooser.APPROVE_OPTION) {
            val file = fileChooser.selectedFile
            try {
                val image = ImageIO.read(file)
                val base64 = encodeImageToBase64(image)
                pendingImage = base64
                webChatPanel?.setImageAttached(true, file.name, base64)
                statusLabel.text = "Image attached: ${file.name}"
            } catch (e: Exception) {
                webChatPanel?.addSystemMessage("Failed to load image: ${e.message}")
                statusLabel.text = "Failed to load image: ${e.message}"
            }
        }
    }

    /**
     * Image preview panel for JFileChooser accessory
     */
    private inner class ImagePreviewPanel : JPanel() {
        private val imageLabel = JLabel()
        private val PREVIEW_SIZE = 200

        init {
            preferredSize = Dimension(PREVIEW_SIZE + 20, PREVIEW_SIZE + 40)
            layout = BorderLayout()
            border = BorderFactory.createTitledBorder("Preview")
            imageLabel.horizontalAlignment = JLabel.CENTER
            imageLabel.verticalAlignment = JLabel.CENTER
            add(imageLabel, BorderLayout.CENTER)
        }

        fun setImage(file: File?) {
            if (file == null || !file.isFile) {
                imageLabel.icon = null
                imageLabel.text = "No preview"
                return
            }

            try {
                val image = ImageIO.read(file)
                if (image != null) {
                    // Scale image to fit preview
                    val scale = minOf(
                        PREVIEW_SIZE.toDouble() / image.width,
                        PREVIEW_SIZE.toDouble() / image.height
                    )
                    val newWidth = (image.width * scale).toInt()
                    val newHeight = (image.height * scale).toInt()
                    val scaled = image.getScaledInstance(newWidth, newHeight, Image.SCALE_SMOOTH)
                    imageLabel.icon = ImageIcon(scaled)
                    imageLabel.text = null
                } else {
                    imageLabel.icon = null
                    imageLabel.text = "Cannot preview"
                }
            } catch (e: Exception) {
                imageLabel.icon = null
                imageLabel.text = "Error loading"
            }
        }
    }

    private fun pasteImageFromClipboard() {
        try {
            val clipboard = Toolkit.getDefaultToolkit().systemClipboard
            if (clipboard.isDataFlavorAvailable(DataFlavor.imageFlavor)) {
                val image = clipboard.getData(DataFlavor.imageFlavor) as Image
                val bufferedImage = toBufferedImage(image)
                val base64 = encodeImageToBase64(bufferedImage)
                pendingImage = base64
                webChatPanel?.setImageAttached(true, "Screenshot from clipboard", base64)
                statusLabel.text = "Screenshot pasted from clipboard"
            } else {
                webChatPanel?.addSystemMessage("No image in clipboard")
                statusLabel.text = "No image in clipboard"
            }
        } catch (e: Exception) {
            webChatPanel?.addSystemMessage("Failed to paste image: ${e.message}")
            statusLabel.text = "Failed to paste image: ${e.message}"
        }
    }

    private fun toBufferedImage(img: Image): BufferedImage {
        if (img is BufferedImage) return img
        val buffered = BufferedImage(img.getWidth(null), img.getHeight(null), BufferedImage.TYPE_INT_ARGB)
        val g2d = buffered.createGraphics()
        g2d.drawImage(img, 0, 0, null)
        g2d.dispose()
        return buffered
    }

    private fun encodeImageToBase64(image: BufferedImage): String {
        val baos = ByteArrayOutputStream()
        ImageIO.write(image, "png", baos)
        return Base64.getEncoder().encodeToString(baos.toByteArray())
    }

    // ==================== Context Building ====================

    private fun buildContextFromSelection(): String {
        val selection = contextComboBox.selectedIndex
        return when (selection) {
            1 -> buildDeadCodeContext()
            2 -> buildPerformanceContext()
            3 -> buildCallTraceContext()
            4 -> buildDiagramContext()
            5 -> buildAllContext()
            else -> ""
        }
    }

    private fun buildDeadCodeContext(): String {
        val data = deadCodeData ?: return ""
        val sb = StringBuilder()
        sb.appendLine("\n--- Dead Code Context ---")

        val deadFunctions = data.getAsJsonArray("dead_functions")
        if (deadFunctions != null && deadFunctions.size() > 0) {
            sb.appendLine("Dead/Unreachable functions (${deadFunctions.size()}):")
            deadFunctions.take(20).forEach { func ->
                sb.appendLine("  - $func")
            }
        }

        val calledFunctions = data.getAsJsonArray("called_functions")
        if (calledFunctions != null) {
            sb.appendLine("Called functions: ${calledFunctions.size()}")
        }

        return sb.toString()
    }

    private fun buildPerformanceContext(): String {
        val data = performanceData ?: return ""
        val sb = StringBuilder()
        sb.appendLine("\n--- Performance Context ---")

        val hotspots = data.getAsJsonArray("hotspots")
        if (hotspots != null && hotspots.size() > 0) {
            sb.appendLine("Performance hotspots:")
            hotspots.take(10).forEach { item ->
                val obj = item.asJsonObject
                val func = obj.get("function")?.asString ?: "?"
                val totalMs = obj.get("total_ms")?.asDouble ?: 0.0
                val calls = obj.get("calls")?.asInt ?: 0
                sb.appendLine("  - $func: ${String.format("%.2f", totalMs)}ms ($calls calls)")
            }
        }

        return sb.toString()
    }

    private fun buildCallTraceContext(): String {
        val data = callTraceData ?: return ""
        val sb = StringBuilder()
        sb.appendLine("\n--- Call Trace Context ---")

        val calls = data.getAsJsonArray("calls")
        if (calls != null && calls.size() > 0) {
            sb.appendLine("Recent call sequence:")
            calls.take(30).forEach { item ->
                val obj = item.asJsonObject
                val depth = obj.get("depth")?.asInt ?: 0
                val func = obj.get("function")?.asString ?: "?"
                val module = obj.get("module")?.asString ?: "?"
                val indent = "  ".repeat(depth)
                sb.appendLine("$indent→ $module.$func()")
            }
        }

        return sb.toString()
    }

    private fun buildDiagramContext(): String {
        val diagram = currentDiagramData ?: return ""
        return "\n--- Current Diagram ---\n$diagram"
    }

    private fun buildAllContext(): String {
        val sb = StringBuilder()
        sb.append(buildDeadCodeContext())
        sb.append(buildPerformanceContext())
        sb.append(buildCallTraceContext())
        sb.append(buildDiagramContext())
        return sb.toString()
    }

    // ==================== MCP Tools (Compact) ====================

    private fun buildMCPToolsDocumentation(): String {
        // Ultra-compact format for minimal token usage (ASCII only for compatibility)
        return """
            |MCP Tools (use mcp{"tool":"name","args":{}} to call):
            |- get_trace_data: call history
            |- get_dead_code: unused functions
            |- get_performance_data: hotspots
            |- get_sql_queries: SQL with N+1
            |- export_diagram(format): plantuml/mermaid/d2
            |- search_function(function_name): find function
            |- get_call_chain(function_name): callers/callees
        """.trimMargin()
    }

    // ==================== LLM Communication ====================

    /**
     * Sanitize text for JSON/LLM API compatibility.
     * Removes or replaces problematic characters that can cause UTF-8 parsing errors.
     */
    private fun sanitizeForLLM(text: String): String {
        return text
            // Replace common problematic Unicode characters with ASCII equivalents
            .replace("•", "-")
            .replace("–", "-")
            .replace("—", "-")
            .replace(""", "\"")
            .replace(""", "\"")
            .replace("'", "'")
            .replace("'", "'")
            .replace("…", "...")
            .replace("→", "->")
            .replace("←", "<-")
            .replace("↔", "<->")
            .replace("≤", "<=")
            .replace("≥", ">=")
            .replace("≠", "!=")
            .replace("×", "x")
            .replace("÷", "/")
            .replace("±", "+/-")
            .replace("°", " degrees")
            .replace("©", "(c)")
            .replace("®", "(R)")
            .replace("™", "(TM)")
            .replace("€", "EUR")
            .replace("£", "GBP")
            .replace("¥", "JPY")
            // Remove or replace control characters and invalid UTF-8 sequences
            .replace(Regex("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F\\x7F]"), "")
            // Replace any remaining non-ASCII with space (safe fallback)
            .replace(Regex("[^\\x20-\\x7E\\n\\r\\t]"), " ")
            // Collapse multiple spaces
            .replace(Regex(" +"), " ")
            .trim()
    }

    private fun callLLM(userPrompt: String, contextText: String, imageBase64: String?): String {
        val messages = mutableListOf<Map<String, Any>>()

        // Sanitize all text inputs
        val sanitizedPrompt = sanitizeForLLM(userPrompt)
        val sanitizedContext = sanitizeForLLM(contextText)

        // Build MCP tools documentation
        val mcpToolsDocs = buildMCPToolsDocumentation()

        // Compact system prompt with MCP awareness
        val systemPrompt = sanitizeForLLM("""TrueFlow AI: Code analysis assistant. Be concise and technical.
                |$mcpToolsDocs
                |If context insufficient, use MCP tool. I will execute and return results.
            """.trimMargin())

        messages.add(mapOf(
            "role" to "system",
            "content" to systemPrompt
        ))

        // Add conversation history (text only - images are too large to resend each time)
        for (msg in conversationHistory.dropLast(1)) {  // Exclude the message we just added
            val sanitizedContent = sanitizeForLLM(msg.content)
            // For messages that had images, add a note but don't resend the image data
            val content = if (msg.imageBase64 != null) {
                "$sanitizedContent\n[User shared an image with this message]"
            } else {
                sanitizedContent
            }
            messages.add(mapOf("role" to msg.role, "content" to content))
        }

        // Current user message with context
        val fullPrompt = if (sanitizedContext.isNotEmpty()) {
            "$sanitizedPrompt\n$sanitizedContext"
        } else {
            sanitizedPrompt
        }

        if (imageBase64 != null && modelHasVision()) {
            messages.add(mapOf(
                "role" to "user",
                "content" to listOf(
                    mapOf("type" to "text", "text" to fullPrompt),
                    mapOf(
                        "type" to "image_url",
                        "image_url" to mapOf("url" to "data:image/png;base64,$imageBase64")
                    )
                )
            ))
        } else {
            messages.add(mapOf("role" to "user", "content" to fullPrompt))
        }

        val requestBody = Gson().toJson(mapOf(
            "model" to "qwen3-vl",
            "messages" to messages,
            "max_tokens" to 1024,
            "temperature" to 0.7
        ))

        val url = URL("$apiBase/chat/completions")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 30000
        conn.readTimeout = 120000  // 2 minutes for generation

        OutputStreamWriter(conn.outputStream).use { it.write(requestBody) }

        val responseCode = conn.responseCode
        if (responseCode != 200) {
            val errorBody = conn.errorStream?.let { BufferedReader(InputStreamReader(it)).use { r -> r.readText() } } ?: ""
            PluginLogger.error("LLM API error $responseCode: $errorBody")
            PluginLogger.debug("Request body was: ${requestBody.take(500)}...")
            val errorMsg = when (responseCode) {
                500 -> "Server error (500): $errorBody. This may be due to: (1) Model not fully loaded - wait a few seconds, (2) Out of memory - try a smaller model, (3) Invalid request format for the model."
                503 -> "Server unavailable (503): The AI server is still initializing. Please wait a moment."
                else -> "HTTP $responseCode: $errorBody"
            }
            throw RuntimeException(errorMsg)
        }

        val response = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
        val json = Gson().fromJson(response, JsonObject::class.java)

        val content = json.getAsJsonArray("choices")
            ?.get(0)?.asJsonObject
            ?.getAsJsonObject("message")
            ?.get("content")?.asString
            ?: "No response"

        // Check if model requested MCP tool call
        val mcpResult = detectAndExecuteMCPCall(content)
        if (mcpResult != null) {
            // Model requested a tool - execute it and continue conversation
            val (toolResponse, remainingText) = mcpResult

            // Add tool result to messages and call LLM again
            val followUpMessages = messages.toMutableList()
            followUpMessages.add(mapOf("role" to "assistant", "content" to content))
            followUpMessages.add(mapOf("role" to "user", "content" to "Tool result:\n$toolResponse\n\nNow answer the original question using this data."))

            // Make follow-up call with tool results
            val followUpBody = Gson().toJson(mapOf(
                "model" to "qwen3-vl",
                "messages" to followUpMessages,
                "max_tokens" to 1024,
                "temperature" to 0.7
            ))

            val followUpConn = URL("$apiBase/chat/completions").openConnection() as HttpURLConnection
            followUpConn.requestMethod = "POST"
            followUpConn.setRequestProperty("Content-Type", "application/json")
            followUpConn.doOutput = true
            followUpConn.connectTimeout = 30000
            followUpConn.readTimeout = 120000

            OutputStreamWriter(followUpConn.outputStream).use { it.write(followUpBody) }

            val followUpCode = followUpConn.responseCode
            if (followUpCode != 200) {
                val followUpError = followUpConn.errorStream?.let { BufferedReader(InputStreamReader(it)).use { r -> r.readText() } } ?: ""
                PluginLogger.error("Follow-up LLM API error $followUpCode: $followUpError")
                return content  // Fallback to original response
            }

            val followUpResponse = BufferedReader(InputStreamReader(followUpConn.inputStream)).use { it.readText() }
            val followUpJson = Gson().fromJson(followUpResponse, JsonObject::class.java)

            return followUpJson.getAsJsonArray("choices")
                ?.get(0)?.asJsonObject
                ?.getAsJsonObject("message")
                ?.get("content")?.asString
                ?: content  // Fallback to original if follow-up fails
        }

        return content
    }

    /**
     * Detect MCP tool call in response and execute it.
     * Returns (toolResponse, remainingText) or null if no tool call.
     */
    private fun detectAndExecuteMCPCall(content: String): Pair<String, String>? {
        // Look for ```mcp{...}``` pattern
        val mcpPattern = Regex("```mcp\\s*\\{([^}]+)\\}\\s*```", RegexOption.DOT_MATCHES_ALL)
        val match = mcpPattern.find(content) ?: return null

        try {
            val jsonStr = "{${match.groupValues[1]}}"
            val toolCall = Gson().fromJson(jsonStr, JsonObject::class.java)
            val toolName = toolCall.get("tool")?.asString ?: return null
            val args = toolCall.getAsJsonObject("args") ?: JsonObject()

            // Execute the tool
            val result = executeMCPTool(toolName, args)
            val remainingText = content.replace(match.value, "").trim()

            return Pair(result, remainingText)
        } catch (e: Exception) {
            PluginLogger.warn("Failed to parse MCP call: ${e.message}")
            return null
        }
    }

    /**
     * Execute an MCP tool and return the result as JSON string.
     * First tries local data, then falls back to Hub RPC for cross-IDE data.
     */
    private fun executeMCPTool(toolName: String, args: JsonObject): String {
        // Try local data first (faster)
        val localResult = executeLocalMCPTool(toolName, args)
        if (localResult != null && localResult != "{}") {
            return localResult
        }

        // If local data empty and Hub connected, try remote
        if (hubClient.isConnected()) {
            return executeRemoteMCPTool(toolName, args)
        }

        return localResult ?: """{"error":"No data available for $toolName"}"""
    }

    private fun executeLocalMCPTool(toolName: String, args: JsonObject): String? {
        return when (toolName) {
            "get_trace_data" -> {
                val data = callTraceData
                if (data != null && data.size() > 0) Gson().toJson(data) else null
            }
            "get_dead_code" -> {
                val data = deadCodeData
                if (data != null && data.size() > 0) Gson().toJson(data) else null
            }
            "get_performance_data" -> {
                val data = performanceData
                if (data != null && data.size() > 0) Gson().toJson(data) else null
            }
            "get_sql_queries" -> {
                // TODO: Implement SQL query data collection
                """{"queries":[],"total_queries":0}"""
            }
            "export_diagram" -> {
                val format = args.get("format")?.asString ?: "plantuml"
                if (currentDiagramData != null) {
                    """{"format":"$format","diagram":"${currentDiagramData?.replace("\"", "\\\"") ?: ""}"}"""
                } else null
            }
            "search_function" -> {
                val funcName = args.get("function_name")?.asString ?: ""
                if (callTraceData != null) searchFunctionInTrace(funcName) else null
            }
            "get_call_chain" -> {
                val funcName = args.get("function_name")?.asString ?: ""
                if (callTraceData != null) getCallChainForFunction(funcName) else null
            }
            "get_flamegraph_data" -> {
                val data = performanceData
                if (data != null && data.size() > 0) Gson().toJson(data) else null
            }
            else -> null
        }
    }

    /**
     * Execute MCP tool via Hub RPC (for cross-IDE data access)
     */
    private fun executeRemoteMCPTool(toolName: String, args: JsonObject): String {
        // Map tool names to Hub RPC commands
        val command = when (toolName) {
            "get_trace_data" -> "get_trace_data"
            "get_dead_code" -> "get_dead_code"
            "get_performance_data" -> "get_performance_data"
            "export_diagram" -> "export_diagram"
            else -> return """{"error":"Remote tool not supported: $toolName"}"""
        }

        // Request from any connected IDE via Hub broadcast
        hubClient.requestFromProject("*", command, args)

        // Note: This is async - for now return empty and let Hub handlers update data
        // In future, implement synchronous RPC with timeout
        return """{"status":"requested","command":"$command","note":"Data will arrive via Hub"}"""
    }

    private fun searchFunctionInTrace(functionName: String): String {
        val calls = callTraceData?.getAsJsonArray("calls") ?: return """{"found":false,"calls":[]}"""
        val matches = calls.filter {
            it.asJsonObject.get("function")?.asString?.contains(functionName, ignoreCase = true) == true
        }
        return """{"found":${matches.isNotEmpty()},"calls":${Gson().toJson(matches.take(10))},"total_matches":${matches.size}}"""
    }

    private fun getCallChainForFunction(functionName: String): String {
        val calls = callTraceData?.getAsJsonArray("calls") ?: return """{"function":"$functionName","callers":[],"callees":[]}"""

        // Simple implementation - find callers and callees based on depth
        val callers = mutableSetOf<String>()
        val callees = mutableSetOf<String>()
        var foundDepth = -1

        calls.forEachIndexed { index, call ->
            val obj = call.asJsonObject
            val func = obj.get("function")?.asString ?: ""
            val depth = obj.get("depth")?.asInt ?: 0

            if (func.contains(functionName, ignoreCase = true)) {
                foundDepth = depth
                // Look for caller (previous call with lower depth)
                for (i in index - 1 downTo 0) {
                    val prev = calls[i].asJsonObject
                    if ((prev.get("depth")?.asInt ?: 0) < depth) {
                        callers.add(prev.get("function")?.asString ?: "")
                        break
                    }
                }
                // Look for callees (next calls with higher depth)
                for (i in index + 1 until calls.size()) {
                    val next = calls[i].asJsonObject
                    val nextDepth = next.get("depth")?.asInt ?: 0
                    if (nextDepth <= depth) break
                    if (nextDepth == depth + 1) {
                        callees.add(next.get("function")?.asString ?: "")
                    }
                }
            }
        }

        return """{"function":"$functionName","callers":${Gson().toJson(callers.toList())},"callees":${Gson().toJson(callees.toList())}}"""
    }

    private fun modelHasVision(): Boolean {
        val selectedIndex = modelComboBox.selectedIndex
        return if (selectedIndex < modelPresets.size) {
            modelPresets[selectedIndex].hasVision
        } else {
            false
        }
    }

    // ==================== Public API for Other Panels ====================

    /**
     * Set dead code data for context injection.
     * Called by EnhancedLearningFlowToolWindow when dead code tab updates.
     */
    fun setDeadCodeData(data: JsonObject) {
        deadCodeData = data
    }

    /**
     * Set performance data for context injection.
     */
    fun setPerformanceData(data: JsonObject) {
        performanceData = data
    }

    /**
     * Set call trace data for context injection.
     */
    fun setCallTraceData(data: JsonObject) {
        callTraceData = data
    }

    /**
     * Set current diagram for context injection.
     */
    fun setDiagramData(diagram: String) {
        currentDiagramData = diagram
    }

    /**
     * Programmatically ask a question with specific context.
     * Used by other panels to invoke AI explanation.
     *
     * @param question The question to ask
     * @param context Additional context (e.g., specific function code, error message)
     * @param image Optional screenshot as Base64
     * @param callback Called with the AI response
     */
    fun askQuestion(
        question: String,
        context: String = "",
        image: String? = null,
        callback: (String) -> Unit
    ) {
        // Check if server is running (either our local process or external server)
        val serverRunning = (serverProcess != null && serverProcess!!.isAlive) || checkServerHealth()
        if (!serverRunning) {
            callback("AI server not running. Please start it from the AI Explanation tab.")
            return
        }

        CompletableFuture.runAsync {
            try {
                val response = callLLM(question, context, image)
                SwingUtilities.invokeLater {
                    // Also add to visible chat
                    webChatPanel?.addUserMessage(question, image)
                    webChatPanel?.addAssistantMessage(response)
                    callback(response)
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    callback("Error: ${e.message}")
                }
            }
        }
    }

    /**
     * Explain why a specific function is dead/unreachable.
     */
    fun explainDeadCode(functionName: String, callTree: String, callback: (String) -> Unit) {
        val question = """Why is the function '$functionName' marked as dead/unreachable?
            |
            |Call tree context:
            |$callTree
            |
            |Explain:
            |1. What paths could reach this function?
            |2. Why aren't those paths being executed?
            |3. Is this likely intentional or a bug?
        """.trimMargin()

        askQuestion(question, buildDeadCodeContext(), null, callback)
    }

    /**
     * Explain a performance bottleneck.
     */
    fun explainPerformance(functionName: String, stats: String, callSequence: String, callback: (String) -> Unit) {
        val question = """Why is '$functionName' a performance bottleneck?
            |
            |Stats: $stats
            |Call sequence leading to it:
            |$callSequence
            |
            |Explain:
            |1. Why is this function slow?
            |2. What's causing repeated calls?
            |3. Potential optimizations?
        """.trimMargin()

        askQuestion(question, buildPerformanceContext(), null, callback)
    }

    /**
     * Explain an exception from trace data.
     */
    fun explainException(exceptionType: String, message: String, stackTrace: String, callback: (String) -> Unit) {
        val question = """Explain this exception:
            |
            |Type: $exceptionType
            |Message: $message
            |Stack trace:
            |$stackTrace
            |
            |Explain:
            |1. What caused this exception?
            |2. What was the code trying to do?
            |3. How to fix it?
        """.trimMargin()

        askQuestion(question, "", null, callback)
    }

    /**
     * Get a brief explanation of a method for Manim billboard display.
     * Returns a short 1-2 sentence description.
     */
    fun getMethodSummary(methodName: String, methodCode: String, callback: (String) -> Unit) {
        val question = """In ONE brief sentence (max 15 words), what does this method do?
            |
            |Method: $methodName
            |Code:
            |```
            |$methodCode
            |```
        """.trimMargin()

        // Check if server is running (either our local process or external server)
        val serverRunning = (serverProcess != null && serverProcess!!.isAlive) || checkServerHealth()
        if (!serverRunning) {
            callback(methodName)  // Fallback to just method name
            return
        }

        CompletableFuture.runAsync {
            try {
                val response = callLLM(question, "", null)
                // Clean up response - take first sentence only
                val summary = response.split(".")[0].trim()
                SwingUtilities.invokeLater {
                    callback(if (summary.length > 80) summary.take(77) + "..." else summary)
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    callback(methodName)  // Fallback
                }
            }
        }
    }

    /**
     * Check if AI server is running (either our local process or external server).
     */
    fun isServerRunning(): Boolean {
        return (serverProcess != null && serverProcess!!.isAlive) || checkServerHealth()
    }

    // ==================== Model & Server Management ====================

    private fun onModelSelectionChanged() {
        val selectedIndex = modelComboBox.selectedIndex
        val preset = modelPresets[selectedIndex]

        // Show custom URL panel and HuggingFace search when "Custom HuggingFace Model..." is selected
        val isCustomModel = preset.repoId.isEmpty()
        customUrlPanel.isVisible = isCustomModel
        hfSearchPanel.isVisible = isCustomModel

        // Check if this specific model is already downloaded
        val modelFile = File(modelsDir, preset.fileName)
        if (modelFile.exists()) {
            downloadButton.text = "Change Model"
            downloadButton.isEnabled = true
            downloadButton.toolTipText = "Current: ${preset.displayName} - Click to download a different model"
        } else if (preset.sizeMB > 0) {
            downloadButton.text = "Download (${preset.sizeMB}MB)"
            downloadButton.toolTipText = "Download ${preset.displayName}"
        } else {
            downloadButton.text = "Download Model"
            downloadButton.toolTipText = null
        }

        checkModelStatus()
    }

    private fun getSelectedModelInfo(): Triple<String, String, String>? {
        val selectedIndex = modelComboBox.selectedIndex
        val preset = modelPresets[selectedIndex]

        return if (preset.repoId.isNotEmpty()) {
            val url = "https://huggingface.co/${preset.repoId}/resolve/main/${preset.fileName}"
            Triple(url, preset.fileName, preset.displayName)
        } else {
            val customUrl = customUrlField.text.trim()
            if (customUrl.isEmpty()) {
                statusLabel.text = "Please enter a HuggingFace URL"
                return null
            }
            val fileName = customUrl.substringAfterLast("/")
            if (!fileName.endsWith(".gguf")) {
                statusLabel.text = "URL must point to a .gguf file"
                return null
            }
            Triple(customUrl, fileName, "Custom: $fileName")
        }
    }

    private fun checkModelStatus() {
        val modelInfo = getSelectedModelInfo() ?: return
        val (_, fileName, displayName) = modelInfo
        val modelFile = File(modelsDir, fileName)

        val selectedIndex = modelComboBox.selectedIndex
        val preset = if (selectedIndex in modelPresets.indices) modelPresets[selectedIndex] else null

        CompletableFuture.runAsync {
            SwingUtilities.invokeLater {
                val modelExists = modelFile.exists()

                // Check if fully downloaded (model + mmproj for vision models)
                val fullyDownloaded = preset != null && isModelFullyDownloaded(preset)

                when {
                    fullyDownloaded -> {
                        // All prerequisites downloaded
                        currentModelFile = modelFile.absolutePath
                        downloadButton.isEnabled = true
                        downloadButton.text = "Change Model"
                        downloadButton.toolTipText = "Current: $displayName"
                        startServerButton.isEnabled = true
                        statusLabel.text = "Model ready: $fileName"
                        webChatPanel?.setDownloadedModel(displayName)
                    }
                    modelExists && preset?.hasVision == true && preset.mmprojFile != null -> {
                        // Model exists but mmproj missing - allow server start, but offer vision download
                        currentModelFile = modelFile.absolutePath
                        downloadButton.isEnabled = true
                        downloadButton.text = "Add Vision Support"
                        downloadButton.toolTipText = "Download vision projector for $displayName (optional)"
                        startServerButton.isEnabled = true  // Allow starting without mmproj - text chat will still work
                        statusLabel.text = "Model ready (vision support optional): $fileName"
                        webChatPanel?.setDownloadedModel(displayName)
                    }
                    else -> {
                        // Model not downloaded
                        currentModelFile = null
                        downloadButton.isEnabled = true
                        startServerButton.isEnabled = false
                        if (preset != null && preset.sizeMB > 0) {
                            downloadButton.text = "Download (${preset.sizeMB}MB)"
                        } else {
                            downloadButton.text = "Download Model"
                        }
                        statusLabel.text = "Model not found. Download to start."
                        webChatPanel?.setDownloadedModel(null)
                    }
                }
            }
        }
    }

    /**
     * Check if all prerequisites for a model are downloaded.
     * For vision models, this includes both model file AND mmproj file.
     */
    private fun isModelFullyDownloaded(preset: ModelPreset): Boolean {
        val modelFile = File(modelsDir, preset.fileName)
        if (!modelFile.exists()) {
            return false
        }

        // For vision models, also check mmproj
        if (preset.hasVision && preset.mmprojFile != null) {
            val mmprojFile = File(modelsDir, preset.mmprojFile)
            if (!mmprojFile.exists()) {
                return false
            }
        }

        return true
    }

    private fun downloadSelectedModel() {
        val modelInfo = getSelectedModelInfo() ?: return
        val (url, fileName, displayName) = modelInfo

        // Get the preset to check for mmproj file
        val selectedIndex = modelComboBox.selectedIndex
        val preset = if (selectedIndex in modelPresets.indices) modelPresets[selectedIndex] else null

        val destFile = File(modelsDir, fileName)
        val modelExists = destFile.exists()

        // Check if ALL prerequisites are downloaded (model + mmproj for vision models)
        if (preset != null && isModelFullyDownloaded(preset)) {
            // Fully downloaded - just update state
            currentModelFile = destFile.absolutePath
            downloadButton.text = "Change Model"
            downloadButton.toolTipText = "Current: $displayName - Select a different model from dropdown"
            startServerButton.isEnabled = true
            statusLabel.text = "Model ready: $fileName"
            webChatPanel?.setDownloadedModel(displayName)
            return
        }

        // Model exists but mmproj is missing for vision model
        if (modelExists && preset?.mmprojFile != null && preset.hasVision) {
            currentModelFile = destFile.absolutePath
            downloadButton.text = "Change Model"
            startServerButton.isEnabled = true
            webChatPanel?.setDownloadedModel(displayName)

            // Download only the missing mmproj
            statusLabel.text = "Downloading vision projector for $displayName..."
            downloadMmprojOnly(preset, displayName)
            return
        }

        downloadButton.isEnabled = false
        modelComboBox.isEnabled = false
        progressBar.isVisible = true
        progressBar.value = 0
        statusLabel.text = "Downloading $displayName..."

        CompletableFuture.runAsync {
            try {
                downloadFileWithProgress(url, destFile) { downloaded, total ->
                    val pct = if (total > 0) ((downloaded.toDouble() / total) * 100).toInt() else 0
                    val downloadedMB = downloaded / (1024 * 1024)
                    val totalMB = total / (1024 * 1024)
                    SwingUtilities.invokeLater {
                        progressBar.value = pct
                        statusLabel.text = "Downloading model... ${downloadedMB}MB / ${totalMB}MB ($pct%)"
                    }
                }

                // Download mmproj file if this is a vision model
                if (preset?.mmprojFile != null && preset.hasVision) {
                    val mmprojUrl = "https://huggingface.co/${preset.repoId}/resolve/main/${preset.mmprojFile}"
                    val mmprojDest = File(modelsDir, preset.mmprojFile)

                    if (!mmprojDest.exists()) {
                        SwingUtilities.invokeLater {
                            statusLabel.text = "Downloading vision projector..."
                            progressBar.value = 0
                        }

                        try {
                            downloadFileWithProgress(mmprojUrl, mmprojDest) { downloaded, total ->
                                val pct = if (total > 0) ((downloaded.toDouble() / total) * 100).toInt() else 0
                                val downloadedMB = downloaded / (1024 * 1024)
                                val totalMB = total / (1024 * 1024)
                                SwingUtilities.invokeLater {
                                    progressBar.value = pct
                                    statusLabel.text = "Downloading vision projector... ${downloadedMB}MB / ${totalMB}MB ($pct%)"
                                }
                            }
                            PluginLogger.info("Downloaded mmproj file: ${preset.mmprojFile}")
                        } catch (e: Exception) {
                            PluginLogger.warn("Failed to download mmproj file: ${e.message} - vision may not work")
                        }
                    }
                }

                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    modelComboBox.isEnabled = true
                    currentModelFile = destFile.absolutePath
                    downloadButton.text = "Change Model"
                    downloadButton.isEnabled = true
                    downloadButton.toolTipText = "Current: $displayName"
                    startServerButton.isEnabled = true
                    statusLabel.text = "Download complete: $fileName"
                    webChatPanel?.setDownloadedModel(displayName)
                }

            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    downloadButton.isEnabled = true
                    modelComboBox.isEnabled = true
                    statusLabel.text = "Download error: ${e.message}"
                    PluginLogger.warn("Model download failed: ${e.message}")
                }
            }
        }
    }

    private fun downloadFileWithProgress(
        urlString: String,
        destFile: File,
        progressCallback: (Long, Long) -> Unit
    ) {
        val url = URL(urlString)
        val connection = url.openConnection() as HttpURLConnection
        connection.setRequestProperty("User-Agent", "TrueFlow/1.0")
        connection.connectTimeout = 30000
        connection.readTimeout = 60000

        val totalSize = connection.contentLengthLong
        var downloaded = 0L
        val buffer = ByteArray(1024 * 1024)

        connection.inputStream.use { input ->
            FileOutputStream(destFile).use { output ->
                var bytesRead: Int
                while (input.read(buffer).also { bytesRead = it } != -1) {
                    output.write(buffer, 0, bytesRead)
                    downloaded += bytesRead
                    progressCallback(downloaded, totalSize)
                }
            }
        }
    }

    /**
     * Download only the mmproj file for a vision model (when model already exists but mmproj is missing).
     */
    private fun downloadMmprojOnly(preset: ModelPreset, displayName: String) {
        val mmprojFile = preset.mmprojFile ?: return
        val mmprojUrl = "https://huggingface.co/${preset.repoId}/resolve/main/$mmprojFile"
        val mmprojDest = File(modelsDir, mmprojFile)

        progressBar.isVisible = true
        progressBar.value = 0
        statusLabel.text = "Downloading vision projector..."

        PluginLogger.info("Downloading mmproj from: $mmprojUrl")

        CompletableFuture.runAsync {
            try {
                downloadFileWithProgress(mmprojUrl, mmprojDest) { downloaded, total ->
                    val pct = if (total > 0) ((downloaded.toDouble() / total) * 100).toInt() else 0
                    val downloadedMB = downloaded / (1024 * 1024)
                    val totalMB = total / (1024 * 1024)
                    SwingUtilities.invokeLater {
                        progressBar.value = pct
                        statusLabel.text = "Downloading vision projector... ${downloadedMB}MB / ${totalMB}MB ($pct%)"
                    }
                }
                // If server is running, restart it to pick up the new mmproj
                val needsRestart = serverProcess != null && serverProcess!!.isAlive

                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    downloadButton.text = "Change Model"
                    PluginLogger.info("Downloaded mmproj file: $mmprojFile")

                    if (needsRestart) {
                        statusLabel.text = "Vision enabled! Restarting server..."
                        PluginLogger.info("Restarting server to load mmproj")
                        stopServer()
                    } else {
                        statusLabel.text = "Model ready: $displayName (vision enabled)"
                    }
                }

                // Restart server after short delay (if it was running)
                if (needsRestart) {
                    Thread.sleep(1000)  // Wait for server to stop
                    SwingUtilities.invokeLater {
                        startServer()
                    }
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    // Still allow using the model without vision
                    statusLabel.text = "Model ready (text-only, vision download failed: ${e.message?.take(50)})"
                    downloadButton.text = "Add Vision Support"
                    PluginLogger.warn("Failed to download mmproj file from $mmprojUrl: ${e.message}")
                }
            }
        }
    }

    private fun toggleServer() {
        if (serverProcess != null && serverProcess!!.isAlive) {
            stopServer()
        } else if (selectedHFModel != null) {
            startServerWithHF(selectedHFModel!!)
        } else {
            startServer()
        }
    }

    private fun startServer() {
        // Check if server is already running from another IDE
        val existingStatus = readServerStatus()
        if (existingStatus?.running == true && checkServerHealth()) {
            SwingUtilities.invokeLater {
                startServerButton.text = "Using External Server (${existingStatus.startedBy})"
                startServerButton.isEnabled = false
                statusLabel.text = "AI Server already running (started by ${existingStatus.startedBy})"
                webChatPanel?.setServerRunning(true, existingStatus.model ?: "")
                webChatPanel?.updateStatus("Connected via ${existingStatus.startedBy}")
            }
            return
        }

        val modelFile = currentModelFile
        if (modelFile == null) {
            statusLabel.text = "No model selected. Please download a model first."
            return
        }

        startServerButton.isEnabled = false
        statusLabel.text = "Starting AI server..."

        CompletableFuture.runAsync {
            try {
                val llamaServer = findLlamaServer()

                if (llamaServer == null) {
                    SwingUtilities.invokeLater {
                        statusLabel.text = "llama.cpp not found. Installing..."
                        installLlamaCpp()
                    }
                    return@runAsync
                }

                // Find the matching mmproj file for this model
                val modelFileName = File(modelFile).name
                val matchingPreset = modelPresets.find { it.fileName == modelFileName }
                val mmprojFile = if (matchingPreset?.mmprojFile != null) {
                    File(modelsDir, matchingPreset.mmprojFile)
                } else {
                    // Fallback: try to find any mmproj that matches the model prefix
                    val modelPrefix = modelFileName.substringBefore("-Q").substringBefore("-UD")
                    modelsDir.listFiles()?.find {
                        it.name.startsWith("mmproj") && it.name.contains(modelPrefix, ignoreCase = true)
                    }
                }

                val isVisionModel = matchingPreset?.hasVision == true ||
                    modelFile.contains("-VL-", ignoreCase = true) ||
                    modelFile.contains("gemma-3", ignoreCase = true) ||
                    modelFile.contains("smol", ignoreCase = true)

                val cmd = mutableListOf(
                    llamaServer,
                    "--model", modelFile,
                    "--port", "8080",
                    "--ctx-size", "4096",
                    "--threads", "${Runtime.getRuntime().availableProcessors()}",
                    "--host", "127.0.0.1",
                    "--jinja"  // Required for chat template support
                )

                // Add vision model flags
                if (isVisionModel) {
                    cmd.add("--kv-unified")
                    // Only add --no-mmproj-offload if not using GPU
                    if (!useGpuAcceleration || gpuAvailable == "none") {
                        cmd.add("--no-mmproj-offload")
                    }
                }

                // Add GPU acceleration flags if enabled and available
                if (useGpuAcceleration && gpuAvailable != "none") {
                    // Offload all layers to GPU
                    cmd.addAll(listOf("--n-gpu-layers", "-1"))
                    // Enable flash attention for CUDA (faster inference)
                    if (gpuAvailable == "cuda") {
                        cmd.add("--flash-attn")
                    }
                    PluginLogger.info("[TrueFlow] GPU acceleration enabled: $gpuAvailable")
                }

                // Add mmproj if available for vision models
                if (mmprojFile != null && mmprojFile.exists() && isVisionModel) {
                    cmd.addAll(listOf("--mmproj", mmprojFile.absolutePath))
                    PluginLogger.info("Using mmproj: ${mmprojFile.absolutePath}")
                    SwingUtilities.invokeLater {
                        statusLabel.text = "Starting AI server (with vision)..."
                    }
                } else if (isVisionModel) {
                    PluginLogger.warn("Vision model detected but no mmproj file found at ${modelsDir.absolutePath}")
                    SwingUtilities.invokeLater {
                        statusLabel.text = "Starting AI server (text-only, no mmproj)..."
                    }
                }

                serverProcess = ProcessBuilder(cmd)
                    .redirectErrorStream(true)
                    .start()

                // Wait for server ready
                var ready = false
                for (i in 1..60) {
                    Thread.sleep(1000)
                    try {
                        val conn = URL("http://127.0.0.1:8080/health").openConnection() as HttpURLConnection
                        conn.connectTimeout = 2000
                        if (conn.responseCode == 200) {
                            ready = true
                            break
                        }
                    } catch (e: Exception) { }

                    SwingUtilities.invokeLater {
                        statusLabel.text = "Starting AI server... ($i/60)"
                    }
                }

                SwingUtilities.invokeLater {
                    if (ready) {
                        val modelName = File(modelFile).name

                        // Write shared status so other IDEs know the server is running (file-based fallback)
                        writeServerStatus(ServerStatus(
                            running = true,
                            pid = null,  // Java Process doesn't easily expose PID
                            port = 8080,
                            model = modelName,
                            startedBy = "pycharm",
                            startedAt = java.time.Instant.now().toString()
                        ))

                        // Notify via WebSocket hub (real-time)
                        hubClient.notifyAIServerStarted(8080, modelName)

                        startServerButton.text = "Stop AI Server"
                        startServerButton.isEnabled = true
                        statusLabel.text = "AI Server running - Running benchmark..."

                        // Update web panel
                        webChatPanel?.setServerRunning(true, modelName)
                        webChatPanel?.updateStatus("Connected: $modelName")

                        // Run benchmark to measure CPU/GPU performance
                        benchmarkLabel.text = "⏱ Benchmarking..."
                        runBenchmark { cpuTps, gpuTps, recommended ->
                            statusLabel.text = "AI Server running - Ready to chat!"
                            benchmarkLabel.text = getBenchmarkStatus()

                            // Auto-select the recommended backend
                            if (gpuAvailable != "none") {
                                val shouldUseGpu = recommended == "gpu"
                                if (shouldUseGpu != useGpuAcceleration) {
                                    PluginLogger.info("[TrueFlow] Benchmark recommends ${recommended.uppercase()}, will use for next server start")
                                    // Note: We don't restart server automatically to avoid disruption
                                    // User can restart to use the recommended setting
                                    useGpuAcceleration = shouldUseGpu
                                }
                            }
                        }
                    } else {
                        serverProcess?.destroyForcibly()
                        serverProcess = null
                        startServerButton.isEnabled = true
                        statusLabel.text = "Server failed to start"
                        webChatPanel?.setServerRunning(false)
                        webChatPanel?.updateStatus("Server failed to start")
                    }
                }

            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    startServerButton.isEnabled = true
                    statusLabel.text = "Server error: ${e.message}"
                    webChatPanel?.setServerRunning(false)
                    webChatPanel?.updateStatus("Server error: ${e.message}")
                    PluginLogger.warn("Server start failed: ${e.message}")
                }
            }
        }
    }

    private fun stopServer() {
        serverProcess?.destroyForcibly()
        serverProcess = null

        // Clear shared status so other IDEs know server stopped (file-based fallback)
        writeServerStatus(null)

        // Notify via WebSocket hub (real-time)
        hubClient.notifyAIServerStopped()

        startServerButton.text = "Start AI Server"
        statusLabel.text = "AI Server stopped"
        selectedHFModel = null

        // Update web panel
        webChatPanel?.setServerRunning(false)
        webChatPanel?.updateStatus("Server stopped")
    }

    private fun startServerWithHF(hfModel: String) {
        startServerButton.isEnabled = false
        statusLabel.text = "Starting AI server with HuggingFace model..."

        CompletableFuture.runAsync {
            try {
                val llamaServer = findLlamaServer()

                if (llamaServer == null) {
                    SwingUtilities.invokeLater {
                        statusLabel.text = "llama.cpp not found. Installing..."
                        installLlamaCpp()
                    }
                    return@runAsync
                }

                val isVisionModel = hfModel.contains("vl", ignoreCase = true) ||
                        hfModel.contains("vision", ignoreCase = true) ||
                        hfModel.contains("gemma-3-4b", ignoreCase = true) ||  // Gemma-3-4B has vision
                        hfModel.contains("smol", ignoreCase = true)

                val cmd = mutableListOf(
                    llamaServer,
                    "-hf", hfModel,  // Direct HuggingFace loading
                    "--port", "8080",
                    "--ctx-size", "4096",
                    "--threads", "${Runtime.getRuntime().availableProcessors()}",
                    "--host", "127.0.0.1",
                    "--jinja"  // Required for chat template support
                )

                if (isVisionModel) {
                    // Try to find mmproj file in the HuggingFace repo
                    // llama-server supports -hfmp flag for HuggingFace mmproj
                    val mmprojName = findMmprojInHFRepo(hfModel)
                    if (mmprojName != null) {
                        // Use -hfmp to load mmproj from same repo
                        cmd.addAll(listOf("-hfmm", mmprojName))
                        PluginLogger.info("Using mmproj from HF repo: $mmprojName")
                    }
                    cmd.add("--kv-unified")  // Fix KV cache issues for vision models
                    // Only add --no-mmproj-offload if not using GPU
                    if (!useGpuAcceleration || gpuAvailable == "none") {
                        cmd.add("--no-mmproj-offload")
                    }
                }

                // Add GPU acceleration flags if enabled and available
                if (useGpuAcceleration && gpuAvailable != "none") {
                    cmd.addAll(listOf("--n-gpu-layers", "-1"))
                    if (gpuAvailable == "cuda") {
                        cmd.add("--flash-attn")
                    }
                    PluginLogger.info("[TrueFlow] GPU acceleration enabled for HF model: $gpuAvailable")
                }

                PluginLogger.info("Starting server with HF model: $hfModel")
                serverProcess = ProcessBuilder(cmd)
                    .redirectErrorStream(true)
                    .start()

                // Wait for server ready (longer timeout for HF download)
                var ready = false
                for (i in 1..120) {
                    Thread.sleep(1000)
                    try {
                        val conn = URL("http://127.0.0.1:8080/health").openConnection() as HttpURLConnection
                        conn.connectTimeout = 2000
                        if (conn.responseCode == 200) {
                            ready = true
                            break
                        }
                    } catch (e: Exception) { }

                    SwingUtilities.invokeLater {
                        statusLabel.text = "Downloading and loading model... ($i/120)"
                    }
                }

                SwingUtilities.invokeLater {
                    if (ready) {
                        // Write shared status for file-based fallback
                        writeServerStatus(ServerStatus(
                            running = true,
                            pid = null,
                            port = 8080,
                            model = hfModel,
                            startedBy = "pycharm",
                            startedAt = java.time.Instant.now().toString()
                        ))

                        // Notify via WebSocket hub (real-time)
                        hubClient.notifyAIServerStarted(8080, hfModel)

                        startServerButton.text = "Stop AI Server"
                        startServerButton.isEnabled = true
                        statusLabel.text = "AI Server running - Running benchmark..."

                        // Update web panel
                        webChatPanel?.setServerRunning(true, hfModel)
                        webChatPanel?.updateStatus("Connected: $hfModel")

                        // Run benchmark to measure CPU/GPU performance
                        benchmarkLabel.text = "⏱ Benchmarking..."
                        runBenchmark { cpuTps, gpuTps, recommended ->
                            statusLabel.text = "AI Server running with $hfModel"
                            benchmarkLabel.text = getBenchmarkStatus()

                            // Auto-select the recommended backend
                            if (gpuAvailable != "none") {
                                val shouldUseGpu = recommended == "gpu"
                                if (shouldUseGpu != useGpuAcceleration) {
                                    PluginLogger.info("[TrueFlow] Benchmark recommends ${recommended.uppercase()}, will use for next server start")
                                    useGpuAcceleration = shouldUseGpu
                                }
                            }
                        }
                    } else {
                        serverProcess?.destroyForcibly()
                        serverProcess = null
                        startServerButton.isEnabled = true
                        statusLabel.text = "Server failed to start"
                        webChatPanel?.setServerRunning(false)
                        webChatPanel?.updateStatus("Server failed to start")
                    }
                }

            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    startServerButton.isEnabled = true
                    statusLabel.text = "Server error: ${e.message}"
                    webChatPanel?.setServerRunning(false)
                    webChatPanel?.updateStatus("Server error: ${e.message}")
                    PluginLogger.warn("Server start failed: ${e.message}")
                }
            }
        }
    }

    private fun searchHuggingFace() {
        val query = hfSearchField.text.trim()
        if (query.length < 2) {
            statusLabel.text = "Search query too short"
            return
        }

        hfSearchButton.isEnabled = false
        statusLabel.text = "Searching HuggingFace..."

        CompletableFuture.runAsync {
            try {
                val searchUrl = "https://huggingface.co/api/models?search=${java.net.URLEncoder.encode(query + " gguf", "UTF-8")}&sort=downloads&limit=20"
                val url = URL(searchUrl)
                val conn = url.openConnection() as HttpURLConnection
                conn.setRequestProperty("User-Agent", "TrueFlow/1.0")
                conn.connectTimeout = 10000

                val response = BufferedReader(InputStreamReader(conn.inputStream)).readText()
                val models = Gson().fromJson(response, JsonArray::class.java)

                hfSearchResults.clear()
                val displayList = mutableListOf<String>()

                models.forEach { modelElement ->
                    val model = modelElement.asJsonObject
                    val id = model.get("id")?.asString ?: model.get("modelId")?.asString ?: return@forEach
                    val downloads = model.get("downloads")?.asInt ?: 0
                    hfSearchResults.add(Pair(id, downloads))
                    displayList.add("$id (${formatNumber(downloads)} downloads)")
                }

                SwingUtilities.invokeLater {
                    hfResultsList.setListData(displayList.toTypedArray())
                    hfSearchButton.isEnabled = true
                    statusLabel.text = "Found ${hfSearchResults.size} GGUF models"
                }

            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    hfSearchButton.isEnabled = true
                    statusLabel.text = "Search error: ${e.message}"
                }
            }
        }
    }

    private fun formatNumber(num: Int): String {
        return when {
            num >= 1000000 -> String.format("%.1fM", num / 1000000.0)
            num >= 1000 -> String.format("%.1fK", num / 1000.0)
            else -> num.toString()
        }
    }

    /**
     * Queries HuggingFace API to find mmproj files in a repo.
     * Returns the filename of the first mmproj file found (preferring F16).
     */
    private fun findMmprojInHFRepo(repoId: String): String? {
        try {
            val apiUrl = "https://huggingface.co/api/models/$repoId/tree/main"
            val url = URL(apiUrl)
            val conn = url.openConnection() as HttpURLConnection
            conn.setRequestProperty("User-Agent", "TrueFlow/1.0")
            conn.connectTimeout = 10000

            if (conn.responseCode != 200) {
                return null
            }

            val response = BufferedReader(InputStreamReader(conn.inputStream)).readText()
            val files = Gson().fromJson(response, JsonArray::class.java)

            val mmprojFiles = mutableListOf<String>()
            files.forEach { fileElement ->
                val file = fileElement.asJsonObject
                val path = file.get("path")?.asString ?: return@forEach
                if (path.startsWith("mmproj") && path.endsWith(".gguf")) {
                    mmprojFiles.add(path)
                }
            }

            // Prefer F16 > BF16 > F32 > any
            return mmprojFiles.find { it.contains("F16", ignoreCase = true) }
                ?: mmprojFiles.find { it.contains("BF16", ignoreCase = true) }
                ?: mmprojFiles.find { it.contains("f16", ignoreCase = true) }
                ?: mmprojFiles.firstOrNull()

        } catch (e: Exception) {
            PluginLogger.warn("Failed to query HF repo for mmproj: ${e.message}")
            return null
        }
    }

    private fun installLlamaCpp() {
        CompletableFuture.runAsync {
            try {
                val installDir = File(System.getProperty("user.home"), ".trueflow/llama.cpp")

                SwingUtilities.invokeLater {
                    statusLabel.text = "Installing llama.cpp..."
                    progressBar.isVisible = true
                    progressBar.isIndeterminate = true
                }

                // First try to download prebuilt binaries (faster and more reliable)
                if (tryDownloadPrebuiltLlama(installDir)) {
                    SwingUtilities.invokeLater {
                        progressBar.isVisible = false
                        progressBar.isIndeterminate = false
                        startServerButton.isEnabled = true
                        statusLabel.text = "llama.cpp installed successfully!"
                    }
                    return@runAsync
                }

                // Fall back to building from source
                SwingUtilities.invokeLater { statusLabel.text = "Prebuilt not available, building from source..." }

                // Step 1: Clone llama.cpp repository
                SwingUtilities.invokeLater { statusLabel.text = "Cloning llama.cpp repository..." }

                if (installDir.exists()) {
                    installDir.deleteRecursively()
                }
                installDir.parentFile.mkdirs()

                val cloneProcess = ProcessBuilder(
                    "git", "clone", "--depth", "1",
                    "https://github.com/ggml-org/llama.cpp",
                    installDir.absolutePath
                ).redirectErrorStream(true).start()

                val cloneOutput = BufferedReader(InputStreamReader(cloneProcess.inputStream)).readText()
                val cloneExitCode = cloneProcess.waitFor()

                if (cloneExitCode != 0) {
                    PluginLogger.warn("Git clone failed: $cloneOutput")
                    SwingUtilities.invokeLater {
                        statusLabel.text = "Failed to clone llama.cpp. Is git installed?"
                        progressBar.isVisible = false
                    }
                    return@runAsync
                }

                // Step 2: Create build directory and run CMake
                SwingUtilities.invokeLater { statusLabel.text = "Configuring build (CMake)..." }

                val buildDir = File(installDir, "build")
                buildDir.mkdirs()

                // Enable CUDA if GPU is available and user wants acceleration
                val useCuda = gpuAvailable == "cuda" && useGpuAcceleration
                val cmakeArgs = mutableListOf(
                    "cmake", "..",
                    "-DBUILD_SHARED_LIBS=OFF",
                    if (useCuda) "-DGGML_CUDA=ON" else "-DGGML_CUDA=OFF",
                    "-DLLAMA_CURL=OFF",
                    "-DLLAMA_BUILD_SERVER=ON"  // Required to build llama-server executable
                )

                val cmakeProcess = ProcessBuilder(cmakeArgs)
                    .directory(buildDir).redirectErrorStream(true).start()

                val cmakeOutput = BufferedReader(InputStreamReader(cmakeProcess.inputStream)).readText()
                val cmakeExitCode = cmakeProcess.waitFor()

                if (cmakeExitCode != 0) {
                    PluginLogger.warn("CMake failed: $cmakeOutput")
                    SwingUtilities.invokeLater {
                        statusLabel.text = "CMake failed. Is CMake installed?"
                        progressBar.isVisible = false
                    }
                    return@runAsync
                }

                // Step 3: Build
                SwingUtilities.invokeLater { statusLabel.text = "Building llama.cpp (this takes a few minutes)..." }

                val buildProcess = ProcessBuilder(
                    "cmake", "--build", ".", "--config", "Release", "-j"
                ).directory(buildDir).redirectErrorStream(true).start()

                val buildOutput = BufferedReader(InputStreamReader(buildProcess.inputStream)).readText()
                val buildExitCode = buildProcess.waitFor()

                if (buildExitCode != 0) {
                    PluginLogger.warn("Build failed: $buildOutput")
                    SwingUtilities.invokeLater {
                        statusLabel.text = "Build failed. Check CMake and compiler."
                        progressBar.isVisible = false
                    }
                    return@runAsync
                }

                // Success!
                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    progressBar.isIndeterminate = false
                    startServerButton.isEnabled = true
                    statusLabel.text = "llama.cpp installed successfully! Click 'Start AI Server'."
                    PluginLogger.info("llama.cpp installed to: ${installDir.absolutePath}")
                }

            } catch (e: Exception) {
                PluginLogger.warn("Installation error: ${e.message}")
                SwingUtilities.invokeLater {
                    statusLabel.text = "Installation error: ${e.message}"
                    progressBar.isVisible = false
                }
            }
        }
    }

    private fun tryDownloadPrebuiltLlama(installDir: File): Boolean {
        try {
            SwingUtilities.invokeLater { statusLabel.text = "Checking for prebuilt binaries..." }

            // Fetch latest release info from GitHub API
            val releaseUrl = URL("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest")
            val conn = releaseUrl.openConnection() as HttpURLConnection
            conn.setRequestProperty("User-Agent", "TrueFlow/1.0")
            conn.connectTimeout = 10000

            val releaseJson = BufferedReader(InputStreamReader(conn.inputStream)).readText()
            val release = Gson().fromJson(releaseJson, JsonObject::class.java)
            val tagName = release.get("tag_name")?.asString ?: return false

            // Determine the right binary for this platform
            // Use CUDA-enabled binary if GPU is available and user wants GPU acceleration
            val osName = System.getProperty("os.name").lowercase()
            val useCuda = gpuAvailable == "cuda" && useGpuAcceleration
            var assetName = when {
                osName.contains("win") -> if (useCuda) "llama-$tagName-bin-win-cuda-cu12.2.0-x64.zip" else "llama-$tagName-bin-win-cpu-x64.zip"
                osName.contains("mac") -> "llama-$tagName-bin-macos-arm64.zip"  // macOS uses Metal
                else -> if (useCuda) "llama-$tagName-bin-ubuntu-cuda-cu12.2.0-x64.zip" else "llama-$tagName-bin-ubuntu-x64.zip"
            }

            // Find the asset URL
            val assets = release.getAsJsonArray("assets")
            var asset = assets?.firstOrNull { it.asJsonObject.get("name")?.asString == assetName }?.asJsonObject

            // If CUDA binary not found, try CUDA 11.8 then fall back to CPU
            if (asset == null && useCuda) {
                PluginLogger.info("[TrueFlow] CUDA 12 binary not found, trying CUDA 11.8...")
                val cuda11Asset = when {
                    osName.contains("win") -> "llama-$tagName-bin-win-cuda-cu11.8.0-x64.zip"
                    else -> "llama-$tagName-bin-ubuntu-cuda-cu11.8.0-x64.zip"
                }
                asset = assets?.firstOrNull { it.asJsonObject.get("name")?.asString == cuda11Asset }?.asJsonObject
                if (asset != null) {
                    assetName = cuda11Asset
                } else {
                    // Fall back to CPU
                    PluginLogger.info("[TrueFlow] No CUDA binary available, falling back to CPU")
                    assetName = when {
                        osName.contains("win") -> "llama-$tagName-bin-win-cpu-x64.zip"
                        else -> "llama-$tagName-bin-ubuntu-x64.zip"
                    }
                    asset = assets?.firstOrNull { it.asJsonObject.get("name")?.asString == assetName }?.asJsonObject
                }
            }

            val downloadUrl = asset?.get("browser_download_url")?.asString ?: return false

            SwingUtilities.invokeLater { statusLabel.text = "Downloading prebuilt llama.cpp ($tagName)..." }

            // Create install directory
            installDir.mkdirs()

            // Download the zip file
            val zipFile = File(installDir, assetName)
            downloadFileWithProgress(downloadUrl, zipFile) { downloaded, total ->
                val pct = if (total > 0) ((downloaded.toDouble() / total) * 100).toInt() else 0
                SwingUtilities.invokeLater { statusLabel.text = "Downloading... $pct%" }
            }

            SwingUtilities.invokeLater { statusLabel.text = "Extracting binaries..." }

            // Extract the zip using PowerShell on Windows or unzip on Unix
            if (osName.contains("win")) {
                val extractProcess = ProcessBuilder(
                    "powershell", "-Command",
                    "Expand-Archive -Path '${zipFile.absolutePath}' -DestinationPath '${installDir.absolutePath}' -Force"
                ).redirectErrorStream(true).start()
                extractProcess.waitFor()
            } else {
                val extractProcess = ProcessBuilder("unzip", "-o", zipFile.absolutePath, "-d", installDir.absolutePath)
                    .redirectErrorStream(true).start()
                extractProcess.waitFor()
            }

            // Clean up zip file
            zipFile.delete()

            // Create build/bin/Release structure for compatibility
            val binDir = File(installDir, "build/bin/Release")
            binDir.mkdirs()

            val serverExe = if (osName.contains("win")) "llama-server.exe" else "llama-server"
            // Extract dir name matches the asset name without .zip extension
            val extractedDirName = assetName.replace(".zip", "")
            val extractedBinDir = File(installDir, extractedDirName)
            val srcServer = File(extractedBinDir, serverExe)
            val destServer = File(binDir, serverExe)

            if (srcServer.exists()) {
                srcServer.copyTo(destServer, overwrite = true)
                if (!osName.contains("win")) {
                    destServer.setExecutable(true)
                }
                PluginLogger.info("Installed llama-server to: ${destServer.absolutePath}")
                return true
            } else {
                // Try root folder
                val altSrcServer = File(installDir, serverExe)
                if (altSrcServer.exists()) {
                    altSrcServer.copyTo(destServer, overwrite = true)
                    if (!osName.contains("win")) {
                        destServer.setExecutable(true)
                    }
                    PluginLogger.info("Installed llama-server to: ${destServer.absolutePath}")
                    return true
                }
            }

            return false

        } catch (e: Exception) {
            PluginLogger.warn("Prebuilt download failed: ${e.message}")
            return false
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

    private fun findLlamaServer(): String? {
        val home = System.getProperty("user.home")
        val possiblePaths = listOf(
            // Windows MSVC build output (Release config goes to bin/Release/)
            "$home/.trueflow/llama.cpp/build/bin/Release/llama-server.exe",
            // Linux/macOS build output
            "$home/.trueflow/llama.cpp/build/bin/llama-server",
            // Fallback paths
            "$home/.trueflow/llama.cpp/build/bin/llama-server.exe",
            "/usr/local/bin/llama-server",
            "C:/llama.cpp/build/bin/Release/llama-server.exe",
            "C:/llama.cpp/build/bin/llama-server.exe"
        )
        for (path in possiblePaths) {
            if (File(path).exists()) return path
        }
        return try {
            val cmd = if (System.getProperty("os.name").lowercase().contains("win")) "where" else "which"
            val output = BufferedReader(InputStreamReader(ProcessBuilder(cmd, "llama-server").start().inputStream)).readLine()
            if (output?.isNotEmpty() == true) output else null
        } catch (e: Exception) { null }
    }

    private fun getResourcePath(): String {
        val url = this::class.java.classLoader.getResource("runtime_injector/local_llm_server.py")
        return url?.path?.substringBeforeLast("/") ?: ""
    }

    fun dispose() {
        stopStatusPolling()
        stopServer()
        hubClient.disconnect()
        webChatPanel?.dispose()
        webChatPanel = null
    }
}
