package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.project.Project
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import java.awt.*
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import java.io.File
import javax.swing.*

/**
 * Flamegraph visualization panel - hierarchical performance visualization.
 *
 * Features:
 * - Speedscope.app style flamegraph
 * - Interactive zoom/pan
 * - Click to jump to source code
 * - Hover for details
 * - Color-coded by duration
 */
class FlamegraphPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val canvas = FlamegraphCanvas()
    private val statsLabel = JBLabel()
    private val searchField = JTextField(20)
    private var flamegraphData: FlamegraphData? = null

    init {
        // Top toolbar
        val toolbar = JPanel(FlowLayout(FlowLayout.LEFT))
        toolbar.add(JBLabel("Search: "))
        toolbar.add(searchField)

        val resetZoomButton = JButton("Reset Zoom")
        resetZoomButton.addActionListener {
            canvas.resetZoom()
        }
        toolbar.add(resetZoomButton)

        add(toolbar, BorderLayout.NORTH)

        // Flamegraph canvas
        val scrollPane = JBScrollPane(canvas)
        add(scrollPane, BorderLayout.CENTER)

        // Bottom stats
        statsLabel.text = "No flamegraph data loaded"
        add(statsLabel, BorderLayout.SOUTH)

        // Search functionality
        searchField.addActionListener {
            canvas.searchFunction(searchField.text)
        }
    }

    /**
     * Update flamegraph from real-time trace events (socket streaming).
     * This is called from handleTraceEvent() in EnhancedLearningFlowToolWindow.
     */
    fun updateFromSocketTrace(
        sessionId: String,
        frames: List<FlamegraphFrame>,
        totalDurationMs: Double,
        maxDepth: Int,
        totalCalls: Int
    ) {
        SwingUtilities.invokeLater {
            try {
                flamegraphData = FlamegraphData(
                    sessionId = sessionId,
                    frames = frames,
                    statistics = FlamegraphStats(
                        totalDurationMs = totalDurationMs,
                        maxDepth = maxDepth,
                        totalCalls = totalCalls
                    )
                )

                canvas.setData(flamegraphData!!)
                updateStats()

            } catch (e: Exception) {
                statsLabel.text = "Error updating flamegraph: ${e.message}"
                e.printStackTrace()
            }
        }
    }

    fun loadFlamegraph(file: File) {
        try {
            val json = file.readText()
            val gson = Gson()
            val jsonObj = gson.fromJson(json, JsonObject::class.java)

            flamegraphData = FlamegraphData(
                sessionId = jsonObj.get("session_id").asString,
                frames = jsonObj.getAsJsonArray("frames").map { frameObj ->
                    val frame = frameObj.asJsonObject
                    FlamegraphFrame(
                        name = frame.get("name").asString,
                        value = frame.get("value").asDouble,
                        file = frame.get("file").asString,
                        line = frame.get("line").asInt,
                        parentId = if (frame.has("parent_id") && !frame.get("parent_id").isJsonNull)
                            frame.get("parent_id").asString else null,
                        callId = frame.get("call_id").asString,
                        depth = frame.get("depth").asInt,
                        framework = if (frame.has("framework") && !frame.get("framework").isJsonNull)
                            frame.get("framework").asString else null,
                        isAiAgent = frame.get("is_ai_agent").asBoolean
                    )
                },
                statistics = jsonObj.getAsJsonObject("statistics").let { stats ->
                    FlamegraphStats(
                        totalDurationMs = stats.get("total_duration_ms").asDouble,
                        maxDepth = stats.get("max_depth").asInt,
                        totalCalls = stats.get("total_calls").asInt
                    )
                }
            )

            canvas.setData(flamegraphData!!)
            updateStats()

        } catch (e: Exception) {
            statsLabel.text = "Error loading flamegraph: ${e.message}"
            e.printStackTrace()
        }
    }

    private fun updateStats() {
        flamegraphData?.let { data ->
            statsLabel.text = "Session: ${data.sessionId} | " +
                    "Total: ${String.format("%.1f", data.statistics.totalDurationMs)}ms | " +
                    "Max Depth: ${data.statistics.maxDepth} | " +
                    "Calls: ${data.statistics.totalCalls}"
        }
    }
}

/**
 * Canvas for rendering flamegraph using hierarchical rectangles.
 */
private class FlamegraphCanvas : JPanel() {

    private var data: FlamegraphData? = null
    private var zoomLevel = 1.0
    private var offsetX = 0
    private var offsetY = 0
    private var highlightedFrame: FlamegraphFrame? = null

    init {
        preferredSize = Dimension(800, 600)
        background = JBColor.WHITE

        // Mouse interactions
        addMouseListener(object : MouseAdapter() {
            override fun mouseClicked(e: MouseEvent) {
                val frame = getFrameAtPoint(e.x, e.y)
                if (frame != null) {
                    highlightedFrame = frame
                    repaint()
                    // TODO: Jump to source code
                }
            }
        })

        addMouseMotionListener(object : MouseAdapter() {
            override fun mouseMoved(e: MouseEvent) {
                val frame = getFrameAtPoint(e.x, e.y)
                if (frame != null) {
                    toolTipText = buildTooltip(frame)
                } else {
                    toolTipText = null
                }
            }
        })
    }

    fun setData(data: FlamegraphData) {
        this.data = data
        repaint()
    }

    fun resetZoom() {
        zoomLevel = 1.0
        offsetX = 0
        offsetY = 0
        repaint()
    }

    fun searchFunction(query: String) {
        data?.let { flamegraph ->
            val matches = flamegraph.frames.filter { it.name.contains(query, ignoreCase = true) }
            if (matches.isNotEmpty()) {
                highlightedFrame = matches.first()
                repaint()
            }
        }
    }

    override fun paintComponent(g: Graphics) {
        super.paintComponent(g)
        val g2d = g as Graphics2D
        g2d.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

        data?.let { flamegraph ->
            drawFlamegraph(g2d, flamegraph)
        }
    }

    private fun drawFlamegraph(g2d: Graphics2D, flamegraph: FlamegraphData) {
        val width = width
        val barHeight = 20

        // Build tree structure
        val rootFrames = flamegraph.frames.filter { it.parentId == null }

        var y = 10
        for (rootFrame in rootFrames) {
            y = drawFrame(g2d, rootFrame, 0, y, width, barHeight, flamegraph)
        }
    }

    private fun drawFrame(
        g2d: Graphics2D,
        frame: FlamegraphFrame,
        x: Int,
        y: Int,
        maxWidth: Int,
        barHeight: Int,
        flamegraph: FlamegraphData
    ): Int {
        // Calculate width based on duration percentage
        val totalDuration = flamegraph.statistics.totalDurationMs
        val widthRatio = if (totalDuration > 0) frame.value / totalDuration else 0.0
        val frameWidth = (maxWidth * widthRatio).toInt()

        // Color by duration (green = fast, red = slow)
        val color = getColorForDuration(frame.value)
        g2d.color = if (frame == highlightedFrame) JBColor.CYAN else color
        g2d.fillRect(x, y, frameWidth, barHeight)

        // Border
        g2d.color = JBColor.BLACK
        g2d.drawRect(x, y, frameWidth, barHeight)

        // Text label
        g2d.color = JBColor.BLACK
        val label = truncateText(frame.name, frameWidth - 4)
        g2d.drawString(label, x + 2, y + barHeight - 5)

        // Draw children
        val children = flamegraph.frames.filter { it.parentId == frame.callId }
        var childY = y + barHeight + 2

        for (child in children) {
            childY = drawFrame(g2d, child, x, childY, frameWidth, barHeight, flamegraph)
        }

        return childY
    }

    private fun getColorForDuration(durationMs: Double): Color {
        // Green (fast) to Red (slow) gradient
        return when {
            durationMs < 10 -> Color(144, 238, 144) // Light green
            durationMs < 50 -> Color(255, 255, 153) // Light yellow
            durationMs < 100 -> Color(255, 204, 153) // Light orange
            else -> Color(255, 153, 153) // Light red
        }
    }

    private fun truncateText(text: String, maxWidth: Int): String {
        val charWidth = 7 // Approximate character width
        val maxChars = maxWidth / charWidth
        return if (text.length > maxChars) {
            text.substring(0, maxChars.coerceAtLeast(0)) + "..."
        } else {
            text
        }
    }

    private fun getFrameAtPoint(x: Int, y: Int): FlamegraphFrame? {
        // TODO: Implement hit testing
        return null
    }

    private fun buildTooltip(frame: FlamegraphFrame): String {
        return """
            <html>
            <b>${frame.name}</b><br>
            Duration: ${String.format("%.2f", frame.value)}ms<br>
            File: ${frame.file}:${frame.line}<br>
            Depth: ${frame.depth}<br>
            ${if (frame.framework != null) "Framework: ${frame.framework}<br>" else ""}
            ${if (frame.isAiAgent) "<b>AI Agent</b><br>" else ""}
            </html>
        """.trimIndent()
    }
}

// Data classes
data class FlamegraphData(
    val sessionId: String,
    val frames: List<FlamegraphFrame>,
    val statistics: FlamegraphStats
)

data class FlamegraphFrame(
    val name: String,
    val value: Double,
    val file: String,
    val line: Int,
    val parentId: String?,
    val callId: String,
    val depth: Int,
    val framework: String?,
    val isAiAgent: Boolean
)

data class FlamegraphStats(
    val totalDurationMs: Double,
    val maxDepth: Int,
    val totalCalls: Int
)
