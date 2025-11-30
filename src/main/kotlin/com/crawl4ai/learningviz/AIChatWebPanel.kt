package com.crawl4ai.learningviz

import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.ui.jcef.JBCefBrowser
import com.intellij.ui.jcef.JBCefJSQuery
import org.cef.browser.CefBrowser
import org.cef.browser.CefFrame
import org.cef.handler.CefLoadHandlerAdapter
import java.awt.BorderLayout
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean
import javax.swing.JPanel
import javax.swing.SwingUtilities

/**
 * Rich web-based AI chat panel using JCEF for modern HTML/CSS rendering.
 * Matches the VS Code extension's stylish chat interface.
 *
 * Handles browser lifecycle during IDE indexing operations.
 */
class AIChatWebPanel(private val project: Project) : JPanel(BorderLayout()), Disposable {

    private var browser: JBCefBrowser? = null
    private var sendMessageQuery: JBCefJSQuery? = null
    private var pageLoaded = false
    private val pendingMessages = ConcurrentLinkedQueue<String>()
    private val isDisposed = AtomicBoolean(false)

    // Callback for when user sends a message
    var onSendMessage: ((String, String?) -> Unit)? = null  // (message, imageBase64) -> Unit

    // Callback for action buttons
    var onStartServer: (() -> Unit)? = null
    var onStopServer: (() -> Unit)? = null
    var onDownloadModel: (() -> Unit)? = null
    var onAttachImage: (() -> Unit)? = null
    var onPasteImage: (() -> Unit)? = null
    var onClearHistory: (() -> Unit)? = null
    var onMaximize: (() -> Unit)? = null
    var onContextChanged: ((Int) -> Unit)? = null  // Context selection callback
    var onStopOperation: (() -> Unit)? = null  // Stop/cancel callback
    var onBackendChanged: ((String) -> Unit)? = null  // Backend selection (llama.cpp or ollama)
    var onGpuChanged: ((Boolean) -> Unit)? = null  // GPU acceleration toggle
    var onOllamaModelChanged: ((String) -> Unit)? = null  // Ollama model selection
    var onCheckOllama: (() -> Unit)? = null  // Check Ollama connection
    var onDeployNewModel: (() -> Unit)? = null  // Deploy new model (stop current and start with new)

    init {
        try {
            browser = JBCefBrowser()
            add(browser!!.component, BorderLayout.CENTER)

            // Set up JS -> Kotlin communication
            sendMessageQuery = JBCefJSQuery.create(browser!!)
            sendMessageQuery?.addHandler { request ->
                handleJSMessage(request)
                JBCefJSQuery.Response("")
            }

            // Wait for page to load before injecting the query handler
            browser!!.jbCefClient.addLoadHandler(object : CefLoadHandlerAdapter() {
                override fun onLoadEnd(browser: CefBrowser?, frame: CefFrame?, httpStatusCode: Int) {
                    if (frame?.isMain == true) {
                        pageLoaded = true
                        injectQueryHandler()
                        // Process any pending messages
                        while (pendingMessages.isNotEmpty()) {
                            val msg = pendingMessages.poll()
                            if (msg != null) executeJS(msg)
                        }
                    }
                }
            }, browser!!.cefBrowser)

            browser!!.loadHTML(getChatHtml())
            PluginLogger.info("AIChatWebPanel initialized with JCEF browser")
        } catch (e: Exception) {
            PluginLogger.error("Failed to initialize JCEF browser for AI chat: ${e.message}")
            add(javax.swing.JLabel(
                "<html><center><p>Rich chat view requires JCEF support.</p>" +
                "<p>Please use a JetBrains IDE with JCEF enabled.</p></center></html>"
            ), BorderLayout.CENTER)
        }
    }

    private fun injectQueryHandler() {
        val injection = sendMessageQuery?.inject("msg")
        executeJS("""
            window.sendToKotlin = function(msg) {
                $injection
            };
        """.trimIndent())
    }

    private fun handleJSMessage(request: String) {
        try {
            // Parse JSON message from JS
            val parts = request.split("|", limit = 2)
            val action = parts[0]
            val data = if (parts.size > 1) parts[1] else ""

            SwingUtilities.invokeLater {
                when (action) {
                    "send" -> {
                        val msgParts = data.split("|||", limit = 2)
                        val message = msgParts[0]
                        val image = if (msgParts.size > 1 && msgParts[1].isNotBlank()) msgParts[1] else null
                        onSendMessage?.invoke(message, image)
                    }
                    "startServer" -> onStartServer?.invoke()
                    "stopServer" -> onStopServer?.invoke()
                    "downloadModel" -> onDownloadModel?.invoke()
                    "attachImage" -> onAttachImage?.invoke()
                    "pasteImage" -> onPasteImage?.invoke()
                    "clearHistory" -> onClearHistory?.invoke()
                    "maximize" -> onMaximize?.invoke()
                    "contextChanged" -> {
                        val contextIndex = data.toIntOrNull() ?: 0
                        onContextChanged?.invoke(contextIndex)
                    }
                    "stopOperation" -> onStopOperation?.invoke()
                    "setBackend" -> onBackendChanged?.invoke(data)
                    "setGpu" -> onGpuChanged?.invoke(data == "true")
                    "setOllamaModel" -> onOllamaModelChanged?.invoke(data)
                    "checkOllama" -> onCheckOllama?.invoke()
                    "deployNewModel" -> onDeployNewModel?.invoke()
                }
            }
        } catch (e: Exception) {
            PluginLogger.error("Error handling JS message: ${e.message}")
        }
    }

    private fun executeJS(script: String) {
        if (isDisposed.get()) {
            PluginLogger.debug("AIChatWebPanel: Skipping JS execution - panel disposed")
            return
        }
        val b = browser
        if (pageLoaded && b != null) {
            try {
                b.cefBrowser.executeJavaScript(script, "", 0)
            } catch (e: Exception) {
                PluginLogger.debug("AIChatWebPanel: JS execution failed - ${e.message}")
                // Browser might be in bad state, queue for later
                pendingMessages.add(script)
            }
        } else {
            pendingMessages.add(script)
        }
    }

    /**
     * Check if the browser is still valid and usable
     */
    fun isBrowserValid(): Boolean {
        return !isDisposed.get() && browser != null
    }

    /**
     * Reinitialize the browser if it was disposed (e.g., after indexing)
     */
    fun reinitializeIfNeeded() {
        if (isDisposed.get()) return

        if (browser == null) {
            PluginLogger.info("AIChatWebPanel: Reinitializing browser after disposal")
            SwingUtilities.invokeLater {
                initBrowser()
            }
        }
    }

    private fun initBrowser() {
        try {
            // Remove old components
            removeAll()

            browser = JBCefBrowser()
            add(browser!!.component, BorderLayout.CENTER)

            sendMessageQuery = JBCefJSQuery.create(browser!!)
            sendMessageQuery?.addHandler { request ->
                handleJSMessage(request)
                JBCefJSQuery.Response("")
            }

            browser!!.jbCefClient.addLoadHandler(object : CefLoadHandlerAdapter() {
                override fun onLoadEnd(browser: CefBrowser?, frame: CefFrame?, httpStatusCode: Int) {
                    if (frame?.isMain == true) {
                        pageLoaded = true
                        injectQueryHandler()
                        while (pendingMessages.isNotEmpty()) {
                            val msg = pendingMessages.poll()
                            if (msg != null) executeJS(msg)
                        }
                    }
                }
            }, browser!!.cefBrowser)

            pageLoaded = false
            browser!!.loadHTML(getChatHtml())

            revalidate()
            repaint()
            PluginLogger.info("AIChatWebPanel browser reinitialized successfully")
        } catch (e: Exception) {
            PluginLogger.error("Failed to reinitialize JCEF browser: ${e.message}")
        }
    }

    override fun dispose() {
        isDisposed.set(true)
        sendMessageQuery?.let { Disposer.dispose(it) }
        browser?.let { Disposer.dispose(it) }
        browser = null
        sendMessageQuery = null
    }

    // ==================== Public API ====================

    fun addUserMessage(content: String, imageBase64: String? = null) {
        val escapedContent = escapeJS(content)
        val imageHtml = if (imageBase64 != null) {
            "<img src='data:image/png;base64,$imageBase64' class='message-image' onclick='showImageModal(this.src)'/>"
        } else ""
        executeJS("addMessage('user', `$escapedContent`, `$imageHtml`);")
    }

    fun addAssistantMessage(content: String) {
        val escapedContent = escapeJS(content)
        executeJS("addMessage('assistant', `$escapedContent`, '');")
    }

    fun addSystemMessage(content: String) {
        val escapedContent = escapeJS(content)
        executeJS("addMessage('system', `$escapedContent`, '');")
    }

    fun setThinking(thinking: Boolean, message: String? = null) {
        val escapedMessage = if (message != null) escapeJS(message) else "AI is thinking..."
        executeJS("setThinking($thinking, `$escapedMessage`);")
    }

    fun updateStatus(status: String) {
        val escapedStatus = escapeJS(status)
        executeJS("updateStatus(`$escapedStatus`);")
    }

    fun setServerRunning(running: Boolean, model: String = "") {
        val escapedModel = escapeJS(model)
        executeJS("setServerRunning($running, `$escapedModel`);")
    }

    fun setDownloadedModel(modelName: String?) {
        val escapedModel = if (modelName != null) escapeJS(modelName) else ""
        if (modelName != null) {
            executeJS("setDownloadedModel(`$escapedModel`);")
        } else {
            executeJS("setDownloadedModel(null);")
        }
    }

    fun setProgress(percent: Int, message: String = "") {
        val escapedMessage = escapeJS(message)
        executeJS("setProgress($percent, `$escapedMessage`);")
    }

    fun setChunkProgress(current: Int, total: Int, message: String = "") {
        val escapedMessage = escapeJS(message)
        executeJS("setChunkProgress($current, $total, `$escapedMessage`);")
    }

    fun showStopButton(show: Boolean) {
        executeJS("showStopButton($show);")
    }

    fun setMCPStatus(connected: Boolean, serverInfo: String = "") {
        val escapedInfo = escapeJS(serverInfo)
        executeJS("setMCPStatus($connected, `$escapedInfo`);")
    }

    fun clearChat() {
        executeJS("clearChat();")
    }

    fun setImageAttached(attached: Boolean, info: String = "", imageBase64: String? = null) {
        val escapedInfo = escapeJS(info)
        if (imageBase64 != null) {
            executeJS("setImageAttached($attached, `$escapedInfo`, `$imageBase64`);")
        } else {
            executeJS("setImageAttached($attached, `$escapedInfo`, null);")
        }
    }

    fun setGpuStatus(available: Boolean, gpuType: String, enabled: Boolean) {
        executeJS("setGpuStatus($available, '$gpuType', $enabled);")
    }

    fun setOllamaStatus(connected: Boolean, models: List<String>) {
        val modelsJson = models.joinToString(",") { "'$it'" }
        executeJS("setOllamaStatus($connected, [$modelsJson]);")
    }

    fun updateTokens(total: Int) {
        executeJS("updateTokens($total);")
    }

    private fun escapeJS(text: String): String {
        return text
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("\n", "\\n")
            .replace("\r", "")
    }

    // ==================== HTML/CSS Content ====================

    private fun getChatHtml(): String {
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow AI Assistant</title>
    <style>
        :root {
            --bg-primary: #1e1e1e;
            --bg-secondary: #252526;
            --bg-tertiary: #2d2d30;
            --bg-hover: #3c3c3c;
            --text-primary: #ffffff;
            --text-secondary: #cccccc;
            --text-muted: #858585;
            --accent-blue: #0078d4;
            --accent-green: #4ec9b0;
            --accent-purple: #c586c0;
            --accent-orange: #ce9178;
            --border-color: #3c3c3c;
            --user-bubble: #264f78;
            --assistant-bubble: #2d2d30;
            --system-bubble: #3d3d40;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            line-height: 1.5;
            overflow: hidden;
        }

        /* Header */
        .header {
            padding: 10px 14px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            flex-shrink: 0;
        }

        .header-title {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }

        .header-title h2 {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .status-indicator {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #f44336;
            display: inline-block;
        }

        .status-indicator.connected { background: #4caf50; }

        .maximize-btn {
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }

        .maximize-btn:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
        }

        .controls {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            align-items: center;
        }

        button {
            padding: 5px 10px;
            font-size: 11px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            font-weight: 500;
        }

        button.primary {
            background: var(--accent-blue);
            color: white;
        }

        button.primary:hover:not(:disabled) {
            background: #1a8cd8;
        }

        button.secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        button.secondary:hover:not(:disabled) {
            background: var(--bg-hover);
        }

        button.success {
            background: #388e3c;
            color: white;
        }

        button.success:hover:not(:disabled) {
            background: #43a047;
        }

        button.danger {
            background: #d32f2f;
            color: white;
        }

        button.danger:hover:not(:disabled) {
            background: #f44336;
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .status-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 8px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .progress-bar {
            flex: 1;
            height: 4px;
            background: var(--bg-tertiary);
            border-radius: 2px;
            overflow: hidden;
            display: none;
        }

        .progress-bar.active { display: block; }

        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
            border-radius: 2px;
            transition: width 0.3s ease;
            width: 0%;
        }

        /* Chat Container */
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 14px;
            scroll-behavior: smooth;
        }

        .chat-container::-webkit-scrollbar {
            width: 8px;
        }

        .chat-container::-webkit-scrollbar-track {
            background: transparent;
        }

        .chat-container::-webkit-scrollbar-thumb {
            background: var(--bg-hover);
            border-radius: 4px;
        }

        .chat-container::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }

        /* Welcome Card */
        .welcome-card {
            background: linear-gradient(135deg, var(--bg-tertiary), var(--bg-secondary));
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }

        .welcome-card h3 {
            color: var(--accent-blue);
            font-size: 16px;
            margin-bottom: 12px;
        }

        .welcome-card ul {
            list-style: none;
            padding: 0;
        }

        .welcome-card li {
            padding: 6px 0;
            color: var(--text-secondary);
            font-size: 13px;
        }

        .welcome-card li::before {
            content: "✓ ";
            color: var(--accent-green);
        }

        /* Messages */
        .message {
            margin-bottom: 14px;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-wrapper {
            display: flex;
            gap: 10px;
            max-width: 92%;
        }

        .message.user .message-wrapper {
            margin-left: auto;
            flex-direction: row-reverse;
        }

        .message-avatar {
            width: 28px;
            height: 28px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            flex-shrink: 0;
        }

        .message.user .message-avatar {
            background: var(--accent-blue);
        }

        .message.assistant .message-avatar {
            background: var(--accent-purple);
        }

        .message.system .message-avatar {
            background: var(--accent-orange);
        }

        .message-bubble {
            padding: 10px 14px;
            border-radius: 12px;
            position: relative;
            max-width: 100%;
        }

        .message.user .message-bubble {
            background: var(--user-bubble);
            border-bottom-right-radius: 4px;
        }

        .message.assistant .message-bubble {
            background: var(--assistant-bubble);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 4px;
        }

        .message.system .message-bubble {
            background: var(--system-bubble);
            border: 1px solid var(--border-color);
        }

        .message-content {
            color: var(--text-primary);
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
            line-height: 1.6;
        }

        .message-content code {
            background: var(--bg-primary);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace;
            font-size: 12px;
        }

        .message-content pre {
            background: var(--bg-primary);
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 8px 0;
        }

        .message-content pre code {
            padding: 0;
            background: transparent;
        }

        .message-image {
            max-width: 250px;
            max-height: 180px;
            border-radius: 8px;
            margin-top: 8px;
            cursor: pointer;
            transition: transform 0.2s;
            border: 1px solid var(--border-color);
        }

        .message-image:hover {
            transform: scale(1.02);
        }

        /* Thinking indicator */
        .thinking {
            display: none;
            padding: 12px 14px;
        }

        .thinking.active { display: block; }

        .thinking-content {
            display: flex;
            align-items: center;
            gap: 12px;
            color: var(--text-muted);
            font-size: 13px;
        }

        .thinking-dots {
            display: flex;
            gap: 4px;
        }

        .thinking-dot {
            width: 8px;
            height: 8px;
            background: var(--accent-purple);
            border-radius: 50%;
            animation: bounce 1.4s ease-in-out infinite;
        }

        .thinking-dot:nth-child(1) { animation-delay: 0s; }
        .thinking-dot:nth-child(2) { animation-delay: 0.2s; }
        .thinking-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes bounce {
            0%, 80%, 100% { transform: translateY(0); }
            40% { transform: translateY(-8px); }
        }

        /* Input Area */
        .input-area {
            padding: 12px 14px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
            flex-shrink: 0;
        }

        .image-preview-container {
            display: none;
            margin-bottom: 10px;
            padding: 8px;
            background: var(--bg-tertiary);
            border-radius: 8px;
            position: relative;
        }

        .image-preview-container.active { display: flex; align-items: center; gap: 10px; }

        .image-preview {
            max-height: 60px;
            border-radius: 6px;
        }

        .image-preview-info {
            font-size: 12px;
            color: var(--text-muted);
        }

        .image-preview-remove {
            position: absolute;
            right: 8px;
            top: 8px;
            background: var(--bg-hover);
            border: none;
            color: var(--text-primary);
            width: 20px;
            height: 20px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 12px;
        }

        .input-wrapper {
            display: flex;
            gap: 10px;
            align-items: flex-end;
        }

        .input-left {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        textarea {
            width: 100%;
            min-height: 50px;
            max-height: 120px;
            padding: 10px 12px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
            resize: none;
            line-height: 1.4;
        }

        textarea:focus {
            outline: none;
            border-color: var(--accent-blue);
        }

        textarea::placeholder {
            color: var(--text-muted);
        }

        .input-actions {
            display: flex;
            gap: 6px;
            align-items: center;
        }

        .context-selector {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            padding: 6px 10px;
            background: var(--bg-tertiary);
            border-radius: 6px;
            border: 1px solid var(--border-color);
        }

        .context-selector label {
            font-size: 11px;
            color: var(--text-muted);
            white-space: nowrap;
        }

        .context-selector select {
            flex: 1;
            padding: 4px 8px;
            font-size: 11px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            cursor: pointer;
        }

        .context-selector select:focus {
            outline: none;
            border-color: var(--accent-blue);
        }

        .context-badge {
            font-size: 10px;
            padding: 2px 6px;
            background: var(--accent-blue);
            color: white;
            border-radius: 10px;
            display: none;
        }

        .context-badge.active {
            display: inline-block;
        }

        .icon-btn {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 6px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }

        .icon-btn:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
        }

        .send-btn {
            background: var(--accent-blue);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.2s;
        }

        .send-btn:hover:not(:disabled) {
            background: #1a8cd8;
            transform: translateY(-1px);
        }

        .send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Image Modal */
        .image-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }

        .image-modal.active { display: flex; }

        .image-modal img {
            max-width: 90%;
            max-height: 90%;
            border-radius: 8px;
        }

        .image-modal-close {
            position: absolute;
            top: 20px;
            right: 20px;
            background: var(--bg-tertiary);
            border: none;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 20px;
        }

        /* Stop button */
        .stop-btn {
            background: #d32f2f;
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            margin-left: 12px;
        }

        .stop-btn:hover {
            background: #f44336;
        }

        /* Chunk progress */
        .chunk-progress {
            margin-top: 8px;
            font-size: 11px;
            color: var(--accent-blue);
        }

        /* MCP Status */
        .mcp-status {
            padding: 8px 14px;
            background: linear-gradient(90deg, rgba(6, 182, 212, 0.1), rgba(34, 197, 94, 0.1));
            border-left: 3px solid var(--accent-green);
            margin: 0 14px 10px;
            border-radius: 0 6px 6px 0;
            font-size: 11px;
        }

        .mcp-indicator {
            margin-right: 6px;
            color: #4caf50;
        }

        .mcp-indicator.disconnected {
            color: #ff5252;
        }

        .mcp-hint {
            display: block;
            margin-top: 4px;
            color: var(--text-muted);
            font-size: 10px;
            opacity: 0.8;
        }

        .mcp-hint code {
            background: var(--bg-primary);
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 10px;
        }

        /* Backend and GPU controls - now inline with other buttons */
        .backend-selector {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .backend-selector label {
            font-size: 11px;
            color: var(--text-muted);
        }

        .backend-selector select {
            padding: 4px 8px;
            font-size: 11px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            cursor: pointer;
        }

        .gpu-option {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .gpu-option input[type="checkbox"] {
            width: 14px;
            height: 14px;
            cursor: pointer;
        }

        .gpu-option label {
            font-size: 11px;
            color: var(--accent-green);
            cursor: pointer;
        }

        /* Model info row */
        .model-info {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 10px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            margin-top: 6px;
            font-size: 11px;
        }

        .model-label {
            color: var(--text-muted);
        }

        .model-name {
            color: var(--accent-blue);
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 200px;
        }

        /* Server controls row */
        .server-controls {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 6px 10px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            margin-top: 6px;
        }

        .server-status-row {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 11px;
        }

        .server-label {
            color: var(--text-muted);
        }

        .running-model {
            color: var(--accent-green);
            font-weight: 500;
        }

        .running-model.stopped {
            color: var(--text-muted);
        }

        .server-buttons {
            display: flex;
            gap: 6px;
        }

        /* Ollama controls */
        .ollama-controls {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 10px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            margin-top: 6px;
        }

        .ollama-controls select {
            padding: 4px 8px;
            font-size: 11px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            cursor: pointer;
        }

        .ollama-status {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 10px;
        }

        .ollama-status.connected {
            background: var(--accent-green);
            color: white;
        }

        .ollama-status.disconnected {
            background: #c62828;
            color: white;
        }

        /* Token counter */
        .token-counter {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
            padding: 4px 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            margin-bottom: 6px;
        }

        .token-counter span {
            color: var(--accent-blue);
            font-weight: 500;
        }

        /* Inline context selector */
        .context-inline {
            padding: 4px 6px;
            font-size: 11px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            cursor: pointer;
            min-width: 90px;
        }

        .context-inline:focus {
            outline: none;
            border-color: var(--accent-blue);
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h2>
                <span class="status-indicator" id="statusIndicator"></span>
                TrueFlow AI
            </h2>
            <button class="maximize-btn" onclick="maximize()">Maximize</button>
        </div>
        <div class="controls">
            <div class="backend-selector">
                <label>Backend:</label>
                <select id="backendSelect" onchange="onBackendChange()">
                    <option value="llama.cpp">llama.cpp</option>
                    <option value="ollama">Ollama</option>
                </select>
            </div>
            <div class="gpu-option" id="gpuOption" style="display:none;">
                <input type="checkbox" id="gpuCheckbox" onchange="onGpuChange()" />
                <label for="gpuCheckbox" id="gpuLabel">GPU</label>
            </div>
            <button class="secondary" onclick="clearHistory()">Clear</button>
            <button id="downloadBtn" class="secondary" onclick="downloadModel()">Download Model</button>
        </div>
        <div class="model-info" id="modelInfo" style="display:none;">
            <span class="model-label">Model:</span>
            <span class="model-name" id="downloadedModelName">None</span>
        </div>
        <div class="server-controls">
            <div class="server-status-row">
                <span class="server-label">Server:</span>
                <span class="running-model" id="runningModelName">Not running</span>
            </div>
            <div class="server-buttons">
                <button id="startBtn" class="success" onclick="startServer()">Start Server</button>
                <button id="stopBtn" class="danger" onclick="stopServer()" style="display:none;">Stop Server</button>
                <button id="deployNewBtn" class="primary" onclick="deployNewModel()" style="display:none;">Stop & Deploy New</button>
            </div>
        </div>
        <div class="ollama-controls" id="ollamaControls" style="display:none;">
            <select id="ollamaModelSelect" onchange="onOllamaModelChange()">
                <option value="">Select model...</option>
            </select>
            <span class="ollama-status" id="ollamaStatus">Not connected</span>
        </div>
        <div class="status-bar">
            <span id="status">Ready</span>
            <div class="progress-bar" id="progressBar">
                <div class="progress-bar-fill" id="progressFill"></div>
            </div>
        </div>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="welcome-card">
            <h3>Welcome to TrueFlow AI</h3>
            <ul>
                <li>Explain dead/unreachable code</li>
                <li>Analyze performance bottlenecks</li>
                <li>Debug exceptions and errors</li>
                <li>Analyze screenshots and diagrams</li>
            </ul>
        </div>
    </div>

    <div class="thinking" id="thinking">
        <div class="thinking-content">
            <div class="thinking-dots">
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
            </div>
            <span id="thinkingText">AI is thinking...</span>
            <button id="stopOperationBtn" class="stop-btn" onclick="stopOperation()" style="display:none;">⏹ Stop</button>
        </div>
        <div class="chunk-progress" id="chunkProgress" style="display:none;">
            <span id="chunkText">Fetching data...</span>
        </div>
    </div>

    <div class="mcp-status" id="mcpStatus" style="display:none;">
        <span class="mcp-indicator" id="mcpIndicator">●</span>
        <span id="mcpInfo">MCP Hub: ws://127.0.0.1:5680</span>
        <span class="mcp-hint">Tools: get_trace_data, get_dead_code, get_performance_data, search_function</span>
    </div>

    <div class="input-area">
        <div class="token-counter" id="tokenCounter">
            <span id="tokenDisplay">Tokens: 0</span>
        </div>
        <div class="image-preview-container" id="imagePreviewContainer">
            <img id="imagePreview" class="image-preview" />
            <span class="image-preview-info" id="imageInfo">Image attached</span>
            <button class="image-preview-remove" onclick="removeImage()">×</button>
        </div>
        <div class="input-wrapper">
            <div class="input-left">
                <textarea id="userInput" placeholder="Ask about your code... (Enter to send, Shift+Enter for new line)"></textarea>
                <div class="input-actions">
                    <button class="icon-btn" onclick="pasteImage()" title="Paste image">📋</button>
                    <button class="icon-btn" onclick="attachImage()" title="Attach image">📎</button>
                    <select id="contextSelect" class="context-inline" onchange="onContextChange()" title="Inject context data">
                        <option value="0">No context</option>
                        <option value="1">Dead Code</option>
                        <option value="2">Performance</option>
                        <option value="3">Call Trace</option>
                        <option value="4">Diagram</option>
                        <option value="5">All Data</option>
                    </select>
                </div>
            </div>
            <button class="send-btn" id="sendBtn" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <div class="image-modal" id="imageModal" onclick="closeImageModal()">
        <button class="image-modal-close" onclick="closeImageModal()">×</button>
        <img id="modalImage" />
    </div>

    <script>
        let pendingImageBase64 = null;
        let serverRunning = false;

        // Elements
        const chatContainer = document.getElementById('chatContainer');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const thinking = document.getElementById('thinking');
        const statusIndicator = document.getElementById('statusIndicator');
        const status = document.getElementById('status');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const imagePreviewContainer = document.getElementById('imagePreviewContainer');
        const imagePreview = document.getElementById('imagePreview');
        const imageInfo = document.getElementById('imageInfo');
        const imageModal = document.getElementById('imageModal');
        const modalImage = document.getElementById('modalImage');

        // Keyboard handler
        userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if (e.shiftKey || e.altKey) {
                    return; // Allow new line
                }
                e.preventDefault();
                sendMessage();
            }
        });

        // Auto-resize textarea
        userInput.addEventListener('input', () => {
            userInput.style.height = 'auto';
            userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
        });

        function sendMessage() {
            const text = userInput.value.trim();
            if (!text && !pendingImageBase64) return;

            const imageData = pendingImageBase64 || '';
            window.sendToKotlin('send|' + text + '|||' + imageData);

            userInput.value = '';
            userInput.style.height = 'auto';
            removeImage();
        }

        function addMessage(role, content, imageHtml) {
            const avatarEmoji = role === 'user' ? '👤' : role === 'assistant' ? '🤖' : 'ℹ️';

            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + role;
            messageDiv.innerHTML =
                '<div class="message-wrapper">' +
                    '<div class="message-avatar">' + avatarEmoji + '</div>' +
                    '<div class="message-bubble">' +
                        '<div class="message-content">' + formatContent(content) + '</div>' +
                        imageHtml +
                    '</div>' +
                '</div>';

            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function formatContent(text) {
            // Basic markdown-like formatting
            return text
                .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/\*([^*]+)\*/g, '<em>$1</em>');
        }

        function setThinking(active, message) {
            thinking.classList.toggle('active', active);
            // Update thinking text with custom message, reset when done
            var thinkingText = document.getElementById('thinkingText');
            if (thinkingText) {
                if (active) {
                    thinkingText.textContent = message || 'AI is thinking...';
                } else {
                    // Reset to default when thinking ends
                    thinkingText.textContent = 'AI is thinking...';
                }
            }
            if (active) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }

        function updateStatus(text) {
            status.textContent = text;
        }

        let downloadedModel = null;
        let runningModel = null;

        function setServerRunning(running, model) {
            serverRunning = running;
            runningModel = running ? model : null;
            statusIndicator.classList.toggle('connected', running);

            const runningModelEl = document.getElementById('runningModelName');
            const deployNewBtn = document.getElementById('deployNewBtn');

            if (running && model) {
                runningModelEl.textContent = model;
                runningModelEl.classList.remove('stopped');
                status.textContent = 'Connected: ' + model;
                startBtn.style.display = 'none';
                stopBtn.style.display = 'inline-block';

                // Show deploy button if downloaded model differs from running model
                if (downloadedModel && downloadedModel !== model) {
                    deployNewBtn.style.display = 'inline-block';
                } else {
                    deployNewBtn.style.display = 'none';
                }
            } else {
                runningModelEl.textContent = 'Not running';
                runningModelEl.classList.add('stopped');
                startBtn.style.display = 'inline-block';
                stopBtn.style.display = 'none';
                deployNewBtn.style.display = 'none';
            }
        }

        function setDownloadedModel(modelName) {
            downloadedModel = modelName;
            const modelInfo = document.getElementById('modelInfo');
            const modelNameEl = document.getElementById('downloadedModelName');
            const downloadBtn = document.getElementById('downloadBtn');
            const deployNewBtn = document.getElementById('deployNewBtn');

            if (modelName) {
                modelInfo.style.display = 'flex';
                modelNameEl.textContent = modelName;
                downloadBtn.textContent = 'Change Model';

                // Show deploy button if running different model
                if (serverRunning && runningModel && runningModel !== modelName) {
                    deployNewBtn.style.display = 'inline-block';
                }
            } else {
                modelInfo.style.display = 'none';
                downloadBtn.textContent = 'Download Model';
                deployNewBtn.style.display = 'none';
            }
        }

        function deployNewModel() {
            window.sendToKotlin('deployNewModel|');
        }

        function setProgress(percent, message) {
            if (percent > 0 && percent < 100) {
                progressBar.classList.add('active');
                progressFill.style.width = percent + '%';
                if (message) status.textContent = message;
            } else {
                progressBar.classList.remove('active');
            }
        }

        function clearChat() {
            chatContainer.innerHTML = '';
        }

        function setImageAttached(attached, info, base64) {
            if (attached) {
                imagePreviewContainer.classList.add('active');
                imageInfo.textContent = info || 'Image attached';
                if (base64) {
                    pendingImageBase64 = base64;
                    imagePreview.src = 'data:image/png;base64,' + base64;
                    imagePreview.style.display = 'block';
                }
            } else {
                imagePreviewContainer.classList.remove('active');
                imagePreview.src = '';
                imagePreview.style.display = 'none';
                pendingImageBase64 = null;
            }
        }

        function removeImage() {
            pendingImageBase64 = null;
            imagePreview.src = '';
            imagePreview.style.display = 'none';
            imagePreviewContainer.classList.remove('active');
        }

        function showImageModal(src) {
            modalImage.src = src;
            imageModal.classList.add('active');
        }

        function closeImageModal() {
            imageModal.classList.remove('active');
        }

        // Actions that call back to Kotlin
        function startServer() { window.sendToKotlin('startServer|'); }
        function stopServer() { window.sendToKotlin('stopServer|'); }
        function downloadModel() { window.sendToKotlin('downloadModel|'); }
        function attachImage() { window.sendToKotlin('attachImage|'); }
        function pasteImage() { window.sendToKotlin('pasteImage|'); }
        function clearHistory() { window.sendToKotlin('clearHistory|'); }
        function maximize() { window.sendToKotlin('maximize|'); }

        function onContextChange() {
            const select = document.getElementById('contextSelect');
            const value = select.value;

            // Notify Kotlin
            window.sendToKotlin('contextChanged|' + value);
        }

        function onBackendChange() {
            const select = document.getElementById('backendSelect');
            const backend = select.value;
            const ollamaControls = document.getElementById('ollamaControls');

            if (backend === 'ollama') {
                ollamaControls.style.display = 'flex';
                // Check Ollama connection
                window.sendToKotlin('checkOllama|');
            } else {
                ollamaControls.style.display = 'none';
            }

            window.sendToKotlin('setBackend|' + backend);
        }

        function onGpuChange() {
            const checkbox = document.getElementById('gpuCheckbox');
            window.sendToKotlin('setGpu|' + checkbox.checked);
        }

        function onOllamaModelChange() {
            const select = document.getElementById('ollamaModelSelect');
            window.sendToKotlin('setOllamaModel|' + select.value);
        }

        function setGpuStatus(available, type, enabled) {
            const gpuOption = document.getElementById('gpuOption');
            const gpuLabel = document.getElementById('gpuLabel');
            const gpuCheckbox = document.getElementById('gpuCheckbox');

            if (available && type !== 'none') {
                gpuOption.style.display = 'flex';
                gpuLabel.textContent = 'GPU (' + type.toUpperCase() + ')';
                gpuCheckbox.checked = enabled;
            } else {
                gpuOption.style.display = 'none';
            }
        }

        function setOllamaStatus(connected, models) {
            const ollamaStatus = document.getElementById('ollamaStatus');
            const ollamaSelect = document.getElementById('ollamaModelSelect');

            if (connected) {
                ollamaStatus.textContent = 'Connected';
                ollamaStatus.className = 'ollama-status connected';
                ollamaSelect.innerHTML = '<option value="">Select model...</option>';
                if (models && models.length > 0) {
                    models.forEach(function(model) {
                        ollamaSelect.innerHTML += '<option value="' + model + '">' + model + '</option>';
                    });
                }
            } else {
                ollamaStatus.textContent = 'Not connected';
                ollamaStatus.className = 'ollama-status disconnected';
                ollamaSelect.innerHTML = '<option value="">Ollama not running</option>';
            }
        }

        function updateTokens(total) {
            const tokenDisplay = document.getElementById('tokenDisplay');
            if (tokenDisplay) {
                tokenDisplay.textContent = 'Tokens: ' + total.toLocaleString();
            }
        }

        function stopOperation() {
            window.sendToKotlin('stopOperation|');
        }

        function setChunkProgress(current, total, message) {
            const chunkProgress = document.getElementById('chunkProgress');
            const chunkText = document.getElementById('chunkText');
            const stopBtn = document.getElementById('stopOperationBtn');

            if (current > 0 && current < total) {
                chunkProgress.style.display = 'block';
                chunkText.textContent = message || 'Fetching ' + current + '-' + Math.min(current + 200, total) + ' of ' + total + ' tokens...';
                stopBtn.style.display = 'inline-block';
            } else {
                chunkProgress.style.display = 'none';
                stopBtn.style.display = 'none';
            }
        }

        function showStopButton(show) {
            document.getElementById('stopOperationBtn').style.display = show ? 'inline-block' : 'none';
        }

        function setMCPStatus(connected, serverInfo) {
            const mcpStatus = document.getElementById('mcpStatus');
            const mcpInfo = document.getElementById('mcpInfo');
            const mcpIndicator = document.getElementById('mcpIndicator');
            // Always show the status bar now
            mcpStatus.style.display = 'block';
            if (connected) {
                mcpIndicator.className = 'mcp-indicator';
                mcpInfo.textContent = serverInfo || 'MCP Hub: ws://127.0.0.1:5680';
            } else {
                mcpIndicator.className = 'mcp-indicator disconnected';
                mcpInfo.textContent = 'MCP Hub: Not connected';
            }
        }

        // Initialize
        window.sendToKotlin = window.sendToKotlin || function() {};
    </script>
</body>
</html>
        """.trimIndent()
    }
}
