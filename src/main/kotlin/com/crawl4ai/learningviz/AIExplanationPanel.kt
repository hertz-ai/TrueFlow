package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonArray
import com.intellij.openapi.application.ApplicationManager
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
        val hasVision: Boolean
    )

    private val modelPresets = listOf(
        ModelPreset(
            "Qwen3-VL-2B Instruct Q4_K_XL (Recommended)",
            "unsloth/Qwen3-VL-2B-Instruct-GGUF",
            "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
            1500,
            "Vision+text, best for code analysis with diagrams",
            hasVision = true
        ),
        ModelPreset(
            "Qwen3-VL-2B Thinking Q4_K_XL",
            "unsloth/Qwen3-VL-2B-Thinking-GGUF",
            "Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf",
            1500,
            "Vision+text with chain-of-thought reasoning",
            hasVision = true
        ),
        ModelPreset(
            "Qwen3-VL-4B Instruct Q4_K_XL",
            "unsloth/Qwen3-VL-4B-Instruct-GGUF",
            "Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf",
            2800,
            "Larger model, better quality, needs ~6GB RAM",
            hasVision = true
        ),
        ModelPreset(
            "Qwen3-VL-8B Instruct Q4_K_XL",
            "unsloth/Qwen3-VL-8B-Instruct-GGUF",
            "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
            5000,
            "Best quality for complex code, needs ~10GB RAM",
            hasVision = true
        ),
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

    // UI Components
    private val chatArea = JBTextArea()
    private val inputField = JBTextArea(3, 50)
    private val sendButton = JButton("Send")
    private val attachImageButton = JButton("Attach Image")
    private val pasteImageButton = JButton("Paste Screenshot")
    private val clearHistoryButton = JButton("Clear")
    private val statusLabel = JBLabel("AI Ready")
    private val progressBar = JProgressBar(0, 100)

    // Model selection
    private val modelComboBox = ComboBox(modelPresets.map { it.displayName }.toTypedArray())
    private val customUrlField = JBTextField()
    private val customUrlPanel = JPanel(BorderLayout())
    private val downloadButton = JButton("Download Model")
    private val startServerButton = JButton("Start AI Server")

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

    // Cross-tab data references (set by EnhancedLearningFlowToolWindow)
    private var deadCodeData: JsonObject? = null
    private var performanceData: JsonObject? = null
    private var callTraceData: JsonObject? = null
    private var currentDiagramData: String? = null

    init {
        modelsDir.mkdirs()
        setupUI()
        checkModelStatus()
    }

    private fun setupUI() {
        border = JBUI.Borders.empty(10)

        // Top panel - Model selection and server controls
        val topPanel = JPanel()
        topPanel.layout = BoxLayout(topPanel, BoxLayout.Y_AXIS)

        // Model selection row
        val modelPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        modelPanel.add(JBLabel("Model: "))
        modelComboBox.preferredSize = Dimension(280, 30)
        modelComboBox.addActionListener { onModelSelectionChanged() }
        modelPanel.add(modelComboBox)

        // Custom URL panel (hidden by default)
        customUrlPanel.isVisible = false
        customUrlField.preferredSize = Dimension(400, 30)
        customUrlField.toolTipText = "Enter HuggingFace URL: https://huggingface.co/user/repo/resolve/main/model.gguf"
        customUrlPanel.add(JBLabel("URL: "), BorderLayout.WEST)
        customUrlPanel.add(customUrlField, BorderLayout.CENTER)

        // Server controls
        val serverPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        downloadButton.addActionListener { downloadSelectedModel() }
        startServerButton.addActionListener { toggleServer() }
        startServerButton.isEnabled = false
        serverPanel.add(downloadButton)
        serverPanel.add(startServerButton)

        // Context selection
        val contextPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        contextPanel.add(JBLabel("Context: "))
        contextComboBox.preferredSize = Dimension(200, 30)
        contextPanel.add(contextComboBox)

        topPanel.add(modelPanel)
        topPanel.add(customUrlPanel)
        topPanel.add(serverPanel)
        topPanel.add(contextPanel)

        add(topPanel, BorderLayout.NORTH)

        // Chat display area
        chatArea.isEditable = false
        chatArea.lineWrap = true
        chatArea.wrapStyleWord = true
        chatArea.font = Font("Monospaced", Font.PLAIN, 13)
        chatArea.background = JBColor(Color(30, 30, 30), Color(30, 30, 30))
        chatArea.foreground = JBColor.WHITE
        chatArea.text = buildWelcomeMessage()

        val chatScrollPane = JBScrollPane(chatArea)
        chatScrollPane.preferredSize = Dimension(600, 400)

        // Input area
        val inputPanel = JPanel(BorderLayout())
        inputPanel.border = JBUI.Borders.empty(10, 0, 0, 0)

        inputField.lineWrap = true
        inputField.wrapStyleWord = true
        inputField.border = BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(JBColor.GRAY),
            JBUI.Borders.empty(5)
        )
        inputField.toolTipText = "Type your question here. You can paste images with Ctrl+V."

        // Enable Ctrl+Enter to send
        inputField.getInputMap(JComponent.WHEN_FOCUSED).put(
            KeyStroke.getKeyStroke(KeyEvent.VK_ENTER, KeyEvent.CTRL_DOWN_MASK),
            "send"
        )
        inputField.actionMap.put("send", object : AbstractAction() {
            override fun actionPerformed(e: ActionEvent) {
                sendMessage()
            }
        })

        // Image attachment indicator
        val imageIndicatorLabel = JBLabel("")
        imageIndicatorLabel.foreground = JBColor.GREEN

        // Button panel
        val buttonPanel = JPanel(FlowLayout(FlowLayout.RIGHT))
        attachImageButton.addActionListener { attachImage() }
        pasteImageButton.addActionListener { pasteImageFromClipboard() }
        clearHistoryButton.addActionListener { clearHistory() }
        sendButton.addActionListener { sendMessage() }

        buttonPanel.add(attachImageButton)
        buttonPanel.add(pasteImageButton)
        buttonPanel.add(clearHistoryButton)
        buttonPanel.add(sendButton)

        inputPanel.add(JBScrollPane(inputField), BorderLayout.CENTER)
        inputPanel.add(buttonPanel, BorderLayout.SOUTH)

        // Center panel with chat and input
        val centerPanel = JPanel(BorderLayout())
        centerPanel.add(chatScrollPane, BorderLayout.CENTER)
        centerPanel.add(inputPanel, BorderLayout.SOUTH)

        add(centerPanel, BorderLayout.CENTER)

        // Bottom status bar
        val statusBar = JPanel(BorderLayout())
        statusBar.add(statusLabel, BorderLayout.WEST)
        progressBar.isVisible = false
        statusBar.add(progressBar, BorderLayout.CENTER)
        add(statusBar, BorderLayout.SOUTH)
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

    private fun sendMessage() {
        val userInput = inputField.text.trim()
        if (userInput.isEmpty() && pendingImage == null) {
            return
        }

        if (serverProcess == null || !serverProcess!!.isAlive) {
            appendToChat("System", "Please start the AI server first.")
            return
        }

        // Build context from selected tab
        val contextText = buildContextFromSelection()

        // Add user message to history
        val userMessage = ChatMessage("user", userInput, pendingImage)
        conversationHistory.add(userMessage)
        trimHistory()

        // Display in chat
        if (pendingImage != null) {
            appendToChat("You", "$userInput\n[Image attached]")
        } else {
            appendToChat("You", userInput)
        }

        // Clear input
        inputField.text = ""
        val sentImage = pendingImage
        pendingImage = null
        updateImageIndicator()

        // Disable send while processing
        sendButton.isEnabled = false
        statusLabel.text = "Thinking..."

        // Send to LLM asynchronously
        CompletableFuture.runAsync {
            try {
                val response = callLLM(userInput, contextText, sentImage)

                // Add assistant response to history
                conversationHistory.add(ChatMessage("assistant", response))
                trimHistory()

                SwingUtilities.invokeLater {
                    appendToChat("AI", response)
                    sendButton.isEnabled = true
                    statusLabel.text = "Ready"
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    appendToChat("System", "Error: ${e.message}")
                    sendButton.isEnabled = true
                    statusLabel.text = "Error occurred"
                }
            }
        }
    }

    private fun appendToChat(sender: String, message: String) {
        val timestamp = java.time.LocalTime.now().format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"))
        val prefix = when (sender) {
            "You" -> "\n[$timestamp] You:\n"
            "AI" -> "\n[$timestamp] AI:\n"
            else -> "\n[$timestamp] $sender:\n"
        }
        chatArea.append(prefix)
        chatArea.append(message)
        chatArea.append("\n")
        chatArea.caretPosition = chatArea.document.length
    }

    private fun clearHistory() {
        conversationHistory.clear()
        chatArea.text = buildWelcomeMessage()
        pendingImage = null
        updateImageIndicator()
    }

    private fun trimHistory() {
        // Keep only last N exchanges (N*2 messages)
        while (conversationHistory.size > maxHistorySize * 2) {
            conversationHistory.removeAt(0)
        }
    }

    // ==================== Image Functions ====================

    private fun attachImage() {
        val descriptor = FileChooserDescriptorFactory.createSingleFileDescriptor()
            .withFileFilter { it.extension?.lowercase() in listOf("png", "jpg", "jpeg", "gif", "bmp") }
            .withTitle("Select Image")

        FileChooser.chooseFile(descriptor, project, null) { virtualFile ->
            try {
                val file = File(virtualFile.path)
                val image = ImageIO.read(file)
                pendingImage = encodeImageToBase64(image)
                updateImageIndicator()
                statusLabel.text = "Image attached: ${file.name}"
            } catch (e: Exception) {
                statusLabel.text = "Failed to load image: ${e.message}"
            }
        }
    }

    private fun pasteImageFromClipboard() {
        try {
            val clipboard = Toolkit.getDefaultToolkit().systemClipboard
            if (clipboard.isDataFlavorAvailable(DataFlavor.imageFlavor)) {
                val image = clipboard.getData(DataFlavor.imageFlavor) as Image
                val bufferedImage = toBufferedImage(image)
                pendingImage = encodeImageToBase64(bufferedImage)
                updateImageIndicator()
                statusLabel.text = "Screenshot pasted from clipboard"
            } else {
                statusLabel.text = "No image in clipboard"
            }
        } catch (e: Exception) {
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

    private fun updateImageIndicator() {
        if (pendingImage != null) {
            attachImageButton.text = "Image Ready"
            attachImageButton.foreground = JBColor.GREEN
        } else {
            attachImageButton.text = "Attach Image"
            attachImageButton.foreground = null
        }
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

    // ==================== LLM Communication ====================

    private fun callLLM(userPrompt: String, contextText: String, imageBase64: String?): String {
        val messages = mutableListOf<Map<String, Any>>()

        // System prompt
        messages.add(mapOf(
            "role" to "system",
            "content" to """You are TrueFlow AI, a code analysis assistant. You help developers understand:
                |1. Why code is marked as dead/unreachable by analyzing call trees
                |2. Performance issues by tracing through execution paths
                |3. Exceptions and errors by examining trace data
                |4. Code flow from sequence diagrams
                |
                |Be concise and technical. When analyzing images, describe what you see and relate it to code concepts.
            """.trimMargin()
        ))

        // Add conversation history (last 3 exchanges)
        for (msg in conversationHistory.dropLast(1)) {  // Exclude the message we just added
            if (msg.imageBase64 != null && modelHasVision()) {
                messages.add(mapOf(
                    "role" to msg.role,
                    "content" to listOf(
                        mapOf("type" to "text", "text" to msg.content),
                        mapOf(
                            "type" to "image_url",
                            "image_url" to mapOf("url" to "data:image/png;base64,${msg.imageBase64}")
                        )
                    )
                ))
            } else {
                messages.add(mapOf("role" to msg.role, "content" to msg.content))
            }
        }

        // Current user message with context
        val fullPrompt = if (contextText.isNotEmpty()) {
            "$userPrompt\n$contextText"
        } else {
            userPrompt
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

        val response = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
        val json = Gson().fromJson(response, JsonObject::class.java)

        return json.getAsJsonArray("choices")
            ?.get(0)?.asJsonObject
            ?.getAsJsonObject("message")
            ?.get("content")?.asString
            ?: "No response"
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
        if (serverProcess == null || !serverProcess!!.isAlive) {
            callback("AI server not running. Please start it from the AI Explanation tab.")
            return
        }

        CompletableFuture.runAsync {
            try {
                val response = callLLM(question, context, image)
                SwingUtilities.invokeLater {
                    // Also add to visible chat
                    appendToChat("Panel Query", question)
                    appendToChat("AI", response)
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

        if (serverProcess == null || !serverProcess!!.isAlive) {
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
     * Check if AI server is running.
     */
    fun isServerRunning(): Boolean {
        return serverProcess != null && serverProcess!!.isAlive
    }

    // ==================== Model & Server Management ====================

    private fun onModelSelectionChanged() {
        val selectedIndex = modelComboBox.selectedIndex
        val preset = modelPresets[selectedIndex]

        customUrlPanel.isVisible = preset.repoId.isEmpty()

        if (preset.sizeMB > 0) {
            downloadButton.text = "Download Model (${preset.sizeMB}MB)"
        } else {
            downloadButton.text = "Download Model"
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
        val (_, fileName, _) = modelInfo
        val modelFile = File(modelsDir, fileName)

        CompletableFuture.runAsync {
            SwingUtilities.invokeLater {
                if (modelFile.exists()) {
                    currentModelFile = modelFile.absolutePath
                    downloadButton.isEnabled = false
                    downloadButton.text = "Model Downloaded"
                    startServerButton.isEnabled = true
                    statusLabel.text = "Model ready: $fileName"
                } else {
                    currentModelFile = null
                    downloadButton.isEnabled = true
                    startServerButton.isEnabled = false
                    onModelSelectionChanged()
                    statusLabel.text = "Model not found. Click 'Download Model' to start."
                }
            }
        }
    }

    private fun downloadSelectedModel() {
        val modelInfo = getSelectedModelInfo() ?: return
        val (url, fileName, displayName) = modelInfo

        downloadButton.isEnabled = false
        modelComboBox.isEnabled = false
        progressBar.isVisible = true
        progressBar.value = 0
        statusLabel.text = "Downloading $displayName..."

        CompletableFuture.runAsync {
            try {
                val destFile = File(modelsDir, fileName)
                downloadFileWithProgress(url, destFile) { downloaded, total ->
                    val pct = if (total > 0) ((downloaded.toDouble() / total) * 100).toInt() else 0
                    val downloadedMB = downloaded / (1024 * 1024)
                    val totalMB = total / (1024 * 1024)
                    SwingUtilities.invokeLater {
                        progressBar.value = pct
                        statusLabel.text = "Downloading... ${downloadedMB}MB / ${totalMB}MB ($pct%)"
                    }
                }

                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    modelComboBox.isEnabled = true
                    currentModelFile = destFile.absolutePath
                    downloadButton.text = "Model Downloaded"
                    startServerButton.isEnabled = true
                    statusLabel.text = "Download complete: $fileName"
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

    private fun toggleServer() {
        if (serverProcess != null && serverProcess!!.isAlive) {
            stopServer()
        } else {
            startServer()
        }
    }

    private fun startServer() {
        val modelFile = currentModelFile
        if (modelFile == null) {
            statusLabel.text = "No model selected. Please download a model first."
            return
        }

        startServerButton.isEnabled = false
        statusLabel.text = "Starting AI server..."

        CompletableFuture.runAsync {
            try {
                val mmproj = File(modelsDir, "mmproj-F16.gguf")
                val llamaServer = findLlamaServer()

                if (llamaServer == null) {
                    SwingUtilities.invokeLater {
                        statusLabel.text = "llama.cpp not found. Installing..."
                        installLlamaCpp()
                    }
                    return@runAsync
                }

                val cmd = mutableListOf(
                    llamaServer,
                    "--model", modelFile,
                    "--port", "8080",
                    "--ctx-size", "4096",
                    "--threads", "${Runtime.getRuntime().availableProcessors()}",
                    "--host", "127.0.0.1"
                )

                if (mmproj.exists() && modelFile.contains("-VL-", ignoreCase = true)) {
                    cmd.addAll(listOf("--mmproj", mmproj.absolutePath))
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
                        startServerButton.text = "Stop AI Server"
                        startServerButton.isEnabled = true
                        sendButton.isEnabled = true
                        statusLabel.text = "AI Server running - Ready to chat!"
                    } else {
                        serverProcess?.destroyForcibly()
                        serverProcess = null
                        startServerButton.isEnabled = true
                        statusLabel.text = "Server failed to start"
                    }
                }

            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    startServerButton.isEnabled = true
                    statusLabel.text = "Server error: ${e.message}"
                    PluginLogger.warn("Server start failed: ${e.message}")
                }
            }
        }
    }

    private fun stopServer() {
        serverProcess?.destroyForcibly()
        serverProcess = null
        startServerButton.text = "Start AI Server"
        sendButton.isEnabled = false
        statusLabel.text = "AI Server stopped"
    }

    private fun installLlamaCpp() {
        CompletableFuture.runAsync {
            try {
                val pythonScript = """
                    |import sys
                    |sys.path.insert(0, '${getResourcePath()}')
                    |from local_llm_server import LlamaCppServer
                    |
                    |server = LlamaCppServer()
                    |def progress(msg, pct):
                    |    print(f"PROGRESS:{pct:.0f}:{msg}")
                    |    sys.stdout.flush()
                    |
                    |success = server.install_llama_cpp(progress)
                    |print(f"RESULT:{'OK' if success else 'FAIL'}")
                """.trimMargin()

                val process = ProcessBuilder(
                    findPython(),
                    "-c",
                    pythonScript
                ).redirectErrorStream(true).start()

                BufferedReader(InputStreamReader(process.inputStream)).use { reader ->
                    var line: String?
                    while (reader.readLine().also { line = it } != null) {
                        val text = line ?: continue
                        if (text.startsWith("PROGRESS:")) {
                            val msg = text.removePrefix("PROGRESS:").split(":", limit = 2).getOrElse(1) { "" }
                            SwingUtilities.invokeLater { statusLabel.text = msg }
                        } else if (text.startsWith("RESULT:")) {
                            val success = text.contains("OK")
                            SwingUtilities.invokeLater {
                                if (success) {
                                    startServerButton.isEnabled = true
                                    statusLabel.text = "llama.cpp installed. Click 'Start AI Server'."
                                } else {
                                    statusLabel.text = "llama.cpp installation failed"
                                }
                            }
                        }
                    }
                }
                process.waitFor()
            } catch (e: Exception) {
                SwingUtilities.invokeLater { statusLabel.text = "Installation error: ${e.message}" }
            }
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
        val possiblePaths = listOf(
            System.getProperty("user.home") + "/.trueflow/llama.cpp/build/bin/llama-server",
            System.getProperty("user.home") + "/.trueflow/llama.cpp/build/bin/llama-server.exe",
            "/usr/local/bin/llama-server",
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
        stopServer()
    }
}
