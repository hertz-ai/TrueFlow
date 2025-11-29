package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import com.intellij.util.ui.JBUI
import java.awt.*
import java.awt.event.ActionEvent
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CompletableFuture
import javax.swing.*

/**
 * AI Explanation Panel - Uses local Qwen3-VL-2B to explain traced code execution.
 *
 * Features:
 * - Automatic model download on first use
 * - Local llama.cpp server management
 * - Natural language explanations of execution flow
 * - Context-aware code analysis
 */
class AIExplanationPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val explanationArea = JBTextArea()
    private val statusLabel = JBLabel("AI Ready")
    private val explainButton = JButton("Explain Selected Trace")
    private val downloadButton = JButton("Download AI Model (1.5GB)")
    private val startServerButton = JButton("Start AI Server")
    private val progressBar = JProgressBar(0, 100)

    private var currentTraceData: JsonObject? = null
    private var serverProcess: Process? = null
    private val apiBase = "http://127.0.0.1:8080/v1"

    init {
        setupUI()
        checkModelStatus()
    }

    private fun setupUI() {
        border = JBUI.Borders.empty(10)

        // Top toolbar
        val toolbar = JPanel(FlowLayout(FlowLayout.LEFT))

        explainButton.addActionListener { explainCurrentTrace() }
        explainButton.isEnabled = false

        downloadButton.addActionListener { downloadModel() }
        startServerButton.addActionListener { toggleServer() }
        startServerButton.isEnabled = false

        toolbar.add(downloadButton)
        toolbar.add(startServerButton)
        toolbar.add(explainButton)

        add(toolbar, BorderLayout.NORTH)

        // Main explanation area
        explanationArea.isEditable = false
        explanationArea.lineWrap = true
        explanationArea.wrapStyleWord = true
        explanationArea.font = Font("Monospaced", Font.PLAIN, 13)
        explanationArea.background = JBColor(Color(40, 44, 52), Color(40, 44, 52))
        explanationArea.foreground = JBColor.WHITE
        explanationArea.text = """
            |TrueFlow AI Explanation Panel
            |=============================
            |
            |This panel uses Qwen3-VL-2B (running locally via llama.cpp) to explain
            |your code execution traces in natural language.
            |
            |Setup Steps:
            |1. Click "Download AI Model" to download the 1.5GB model
            |2. Click "Start AI Server" to launch the local LLM
            |3. Run your code with TrueFlow tracing enabled
            |4. Click "Explain Selected Trace" to get AI-powered insights
            |
            |The model runs entirely on your CPU - no GPU required.
            |No data is sent to external servers.
        """.trimMargin()

        val scrollPane = JBScrollPane(explanationArea)
        add(scrollPane, BorderLayout.CENTER)

        // Bottom status bar
        val statusBar = JPanel(BorderLayout())
        statusBar.add(statusLabel, BorderLayout.WEST)
        progressBar.isVisible = false
        statusBar.add(progressBar, BorderLayout.CENTER)
        add(statusBar, BorderLayout.SOUTH)
    }

    private fun checkModelStatus() {
        CompletableFuture.runAsync {
            val modelDir = System.getProperty("user.home") + "/.trueflow/models"
            val modelFile = java.io.File(modelDir, "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf")

            SwingUtilities.invokeLater {
                if (modelFile.exists()) {
                    downloadButton.isEnabled = false
                    downloadButton.text = "Model Downloaded"
                    startServerButton.isEnabled = true
                    statusLabel.text = "Model ready. Click 'Start AI Server' to begin."
                } else {
                    downloadButton.isEnabled = true
                    startServerButton.isEnabled = false
                    statusLabel.text = "Model not found. Click 'Download AI Model' to start."
                }
            }
        }
    }

    private fun downloadModel() {
        downloadButton.isEnabled = false
        progressBar.isVisible = true
        progressBar.value = 0
        statusLabel.text = "Downloading Qwen3-VL-2B model..."

        CompletableFuture.runAsync {
            try {
                val pythonScript = """
                    |import sys
                    |sys.path.insert(0, '${getResourcePath()}')
                    |from local_llm_server import ModelManager
                    |
                    |manager = ModelManager()
                    |def progress(msg, pct):
                    |    print(f"PROGRESS:{pct:.0f}:{msg}")
                    |    sys.stdout.flush()
                    |
                    |success = manager.download_model("qwen3-vl-2b", progress)
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
                            val parts = text.removePrefix("PROGRESS:").split(":", limit = 2)
                            val pct = parts[0].toIntOrNull() ?: 0
                            val msg = parts.getOrElse(1) { "" }
                            SwingUtilities.invokeLater {
                                progressBar.value = pct
                                statusLabel.text = msg
                            }
                        } else if (text.startsWith("RESULT:")) {
                            val success = text.contains("OK")
                            SwingUtilities.invokeLater {
                                progressBar.isVisible = false
                                if (success) {
                                    downloadButton.text = "Model Downloaded"
                                    startServerButton.isEnabled = true
                                    statusLabel.text = "Download complete! Click 'Start AI Server'."
                                } else {
                                    downloadButton.isEnabled = true
                                    statusLabel.text = "Download failed. Please try again."
                                }
                            }
                        }
                    }
                }

                process.waitFor()

            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    progressBar.isVisible = false
                    downloadButton.isEnabled = true
                    statusLabel.text = "Download error: ${e.message}"
                    PluginLogger.warn("Model download failed: ${e.message}")
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
        startServerButton.isEnabled = false
        statusLabel.text = "Starting AI server..."

        CompletableFuture.runAsync {
            try {
                val modelDir = System.getProperty("user.home") + "/.trueflow/models"
                val modelFile = "$modelDir/Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf"
                val mmproj = "$modelDir/mmproj-F16.gguf"

                // Find llama-server executable
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

                // Add vision projector if available
                if (java.io.File(mmproj).exists()) {
                    cmd.addAll(listOf("--mmproj", mmproj))
                }

                serverProcess = ProcessBuilder(cmd)
                    .redirectErrorStream(true)
                    .start()

                // Wait for server to be ready
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
                    } catch (e: Exception) {
                        // Not ready yet
                    }

                    SwingUtilities.invokeLater {
                        statusLabel.text = "Starting AI server... ($i/60)"
                    }
                }

                SwingUtilities.invokeLater {
                    if (ready) {
                        startServerButton.text = "Stop AI Server"
                        startServerButton.isEnabled = true
                        explainButton.isEnabled = true
                        statusLabel.text = "AI Server running on port 8080"
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
        explainButton.isEnabled = false
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
                            val parts = text.removePrefix("PROGRESS:").split(":", limit = 2)
                            val msg = parts.getOrElse(1) { "" }
                            SwingUtilities.invokeLater {
                                statusLabel.text = msg
                            }
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
                SwingUtilities.invokeLater {
                    statusLabel.text = "Installation error: ${e.message}"
                }
            }
        }
    }

    fun setTraceData(traceData: JsonObject) {
        currentTraceData = traceData
        if (serverProcess != null && serverProcess!!.isAlive) {
            explainButton.isEnabled = true
        }
    }

    private fun explainCurrentTrace() {
        val trace = currentTraceData ?: return
        explainButton.isEnabled = false
        statusLabel.text = "Generating explanation..."

        CompletableFuture.runAsync {
            try {
                val explanation = callLocalLLM(trace)
                SwingUtilities.invokeLater {
                    explanationArea.text = """
                        |AI Code Explanation
                        |===================
                        |
                        |$explanation
                        |
                        |---
                        |Model: Qwen3-VL-2B-Instruct (local, CPU)
                    """.trimMargin()
                    explainButton.isEnabled = true
                    statusLabel.text = "Explanation complete"
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    explanationArea.text = "Error: ${e.message}"
                    explainButton.isEnabled = true
                    statusLabel.text = "Explanation failed"
                }
            }
        }
    }

    private fun callLocalLLM(trace: JsonObject): String {
        val calls = trace.getAsJsonArray("calls") ?: return "No trace data"
        val functions = calls.take(20).mapNotNull {
            it.asJsonObject?.get("function")?.asString
        }.filter { it.isNotEmpty() }

        val modules = calls.mapNotNull {
            it.asJsonObject?.get("module")?.asString
        }.filter { it.isNotEmpty() }.toSet().take(10)

        val prompt = """Analyze this code execution pattern and explain what it's doing:

Functions called: ${functions.joinToString(", ")}
Modules involved: ${modules.joinToString(", ")}

In 3-4 sentences, explain:
1. What is the high-level purpose of this code?
2. What design pattern is it following?
3. Why would someone write code like this?
4. Any potential issues or optimizations?

Be specific and technical."""

        val requestBody = Gson().toJson(mapOf(
            "model" to "qwen3-vl-2b",
            "messages" to listOf(
                mapOf("role" to "system", "content" to "You are a code analysis expert. Be concise and technical."),
                mapOf("role" to "user", "content" to prompt)
            ),
            "max_tokens" to 512,
            "temperature" to 0.7
        ))

        val url = URL("$apiBase/chat/completions")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 30000
        conn.readTimeout = 60000

        OutputStreamWriter(conn.outputStream).use { it.write(requestBody) }

        val response = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
        val json = Gson().fromJson(response, JsonObject::class.java)

        return json.getAsJsonArray("choices")
            ?.get(0)?.asJsonObject
            ?.getAsJsonObject("message")
            ?.get("content")?.asString
            ?: "No response"
    }

    private fun findPython(): String {
        val pythonPaths = listOf(
            "python",
            "python3",
            "C:/Python310/python.exe",
            "C:/Python311/python.exe",
            "C:/Python312/python.exe",
            System.getenv("PYTHON_PATH") ?: ""
        )

        for (path in pythonPaths) {
            if (path.isEmpty()) continue
            try {
                val process = ProcessBuilder(path, "--version").start()
                if (process.waitFor() == 0) return path
            } catch (e: Exception) {
                // Try next
            }
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
            if (java.io.File(path).exists()) return path
        }

        // Check PATH
        return try {
            val process = if (System.getProperty("os.name").lowercase().contains("win")) {
                ProcessBuilder("where", "llama-server").start()
            } else {
                ProcessBuilder("which", "llama-server").start()
            }
            val output = BufferedReader(InputStreamReader(process.inputStream)).readLine()
            if (process.waitFor() == 0 && output?.isNotEmpty() == true) output else null
        } catch (e: Exception) {
            null
        }
    }

    private fun getResourcePath(): String {
        // Get path to runtime_injector resources
        val classLoader = this::class.java.classLoader
        val url = classLoader.getResource("runtime_injector/local_llm_server.py")
        return url?.path?.substringBeforeLast("/") ?: ""
    }

    fun dispose() {
        stopServer()
    }
}
