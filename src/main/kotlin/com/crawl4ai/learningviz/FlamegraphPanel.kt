package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import java.awt.*
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import java.awt.event.MouseWheelEvent
import java.io.File
import javax.swing.*

/**
 * Flamegraph visualization panel - hierarchical performance visualization.
 *
 * Features:
 * - Speedscope.app style icicle graph (root at top, children below)
 * - Interactive zoom/pan with mouse wheel
 * - Click to jump to source code
 * - Hover for details
 * - Color-coded by duration (green=fast, red=slow)
 * - Search with highlighting
 */
class FlamegraphPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val canvas = FlamegraphCanvas(project)
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

        val zoomInButton = JButton("+")
        zoomInButton.addActionListener { canvas.zoomIn() }
        toolbar.add(zoomInButton)

        val zoomOutButton = JButton("-")
        zoomOutButton.addActionListener { canvas.zoomOut() }
        toolbar.add(zoomOutButton)

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
 * Uses icicle graph style (root at top, children below).
 */
private class FlamegraphCanvas(private val project: Project) : JPanel() {

    private var data: FlamegraphData? = null
    private var zoomLevel = 1.0
    private var panX = 0.0
    private var highlightedFrame: FlamegraphFrame? = null
    private var searchQuery: String = ""

    // Cache rendered frame rectangles for hit testing
    private val frameRects = mutableMapOf<Rectangle, FlamegraphFrame>()

    private val barHeight = 24
    private val barGap = 1

    init {
        preferredSize = Dimension(800, 600)
        background = JBColor(Color(30, 30, 30), Color(30, 30, 30))

        // Mouse click - jump to source
        addMouseListener(object : MouseAdapter() {
            override fun mouseClicked(e: MouseEvent) {
                val frame = getFrameAtPoint(e.x, e.y)
                if (frame != null) {
                    highlightedFrame = frame
                    repaint()

                    // Double-click to jump to source
                    if (e.clickCount == 2) {
                        jumpToSource(frame)
                    }
                }
            }
        })

        // Mouse hover - show tooltip
        addMouseMotionListener(object : MouseAdapter() {
            override fun mouseMoved(e: MouseEvent) {
                val frame = getFrameAtPoint(e.x, e.y)
                toolTipText = frame?.let { buildTooltip(it) }
                cursor = if (frame != null) Cursor.getPredefinedCursor(Cursor.HAND_CURSOR)
                         else Cursor.getDefaultCursor()
            }
        })

        // Mouse wheel - zoom
        addMouseWheelListener { e: MouseWheelEvent ->
            val oldZoom = zoomLevel
            if (e.wheelRotation < 0) {
                zoomLevel = (zoomLevel * 1.1).coerceAtMost(10.0)
            } else {
                zoomLevel = (zoomLevel / 1.1).coerceAtLeast(0.1)
            }

            // Adjust pan to keep mouse position stable
            val mouseX = e.x
            panX = mouseX - (mouseX - panX) * (zoomLevel / oldZoom)

            updatePreferredSize()
            repaint()
        }
    }

    fun setData(data: FlamegraphData) {
        this.data = data
        zoomLevel = 1.0
        panX = 0.0
        updatePreferredSize()
        repaint()
    }

    private fun updatePreferredSize() {
        data?.let { flamegraph ->
            val height = (flamegraph.statistics.maxDepth + 2) * (barHeight + barGap) + 40
            val width = ((parent?.width ?: 800) * zoomLevel).toInt()
            preferredSize = Dimension(width, height)
            revalidate()
        }
    }

    fun resetZoom() {
        zoomLevel = 1.0
        panX = 0.0
        updatePreferredSize()
        repaint()
    }

    fun zoomIn() {
        zoomLevel = (zoomLevel * 1.2).coerceAtMost(10.0)
        updatePreferredSize()
        repaint()
    }

    fun zoomOut() {
        zoomLevel = (zoomLevel / 1.2).coerceAtLeast(0.1)
        updatePreferredSize()
        repaint()
    }

    fun searchFunction(query: String) {
        searchQuery = query
        data?.let { flamegraph ->
            val matches = flamegraph.frames.filter { it.name.contains(query, ignoreCase = true) }
            if (matches.isNotEmpty()) {
                highlightedFrame = matches.first()
            }
        }
        repaint()
    }

    override fun paintComponent(g: Graphics) {
        super.paintComponent(g)
        val g2d = g as Graphics2D
        g2d.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
        g2d.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON)

        // Clear frame cache
        frameRects.clear()

        data?.let { flamegraph ->
            drawFlamegraph(g2d, flamegraph)
        } ?: run {
            // Draw placeholder
            g2d.color = JBColor.GRAY
            g2d.drawString("No flamegraph data. Run your application with TrueFlow tracing enabled.", 20, 30)
        }
    }

    private fun drawFlamegraph(g2d: Graphics2D, flamegraph: FlamegraphData) {
        val totalWidth = (width * zoomLevel).toInt()
        val totalDuration = flamegraph.statistics.totalDurationMs

        if (totalDuration <= 0) return

        // Build parent-child map for efficient lookup
        val childrenMap = flamegraph.frames.groupBy { it.parentId }

        // Draw root frames (those with no parent)
        val rootFrames = childrenMap[null] ?: emptyList()

        var currentX = 10
        for (rootFrame in rootFrames) {
            val frameWidth = ((rootFrame.value / totalDuration) * (totalWidth - 20)).toInt()
            drawFrameRecursive(g2d, rootFrame, currentX, 10, frameWidth, childrenMap, totalDuration)
            currentX += frameWidth + 2
        }
    }

    private fun drawFrameRecursive(
        g2d: Graphics2D,
        frame: FlamegraphFrame,
        x: Int,
        y: Int,
        availableWidth: Int,
        childrenMap: Map<String?, List<FlamegraphFrame>>,
        totalDuration: Double
    ) {
        // Minimum width to draw
        if (availableWidth < 2) return

        val rect = Rectangle(x, y, availableWidth, barHeight)

        // Store for hit testing
        frameRects[rect] = frame

        // Determine color
        val baseColor = getColorForDuration(frame.value)
        val color = when {
            frame == highlightedFrame -> JBColor.CYAN
            searchQuery.isNotEmpty() && frame.name.contains(searchQuery, ignoreCase = true) -> JBColor.YELLOW
            else -> baseColor
        }

        // Draw frame rectangle
        g2d.color = color
        g2d.fillRect(x, y, availableWidth, barHeight)

        // Border
        g2d.color = JBColor(Color(20, 20, 20), Color(20, 20, 20))
        g2d.drawRect(x, y, availableWidth, barHeight)

        // Text label (dark text for readability)
        g2d.color = JBColor.BLACK
        val label = truncateText(frame.name, availableWidth - 6, g2d)
        if (label.isNotEmpty()) {
            g2d.drawString(label, x + 3, y + barHeight - 7)
        }

        // Draw children below
        val children = childrenMap[frame.callId] ?: emptyList()
        if (children.isNotEmpty()) {
            var childX = x
            val childY = y + barHeight + barGap

            // Sort children by value (duration) for consistent layout
            val sortedChildren = children.sortedByDescending { it.value }

            for (child in sortedChildren) {
                val childWidth = if (frame.value > 0) {
                    ((child.value / frame.value) * availableWidth).toInt()
                } else {
                    availableWidth / children.size
                }

                if (childWidth >= 2) {
                    drawFrameRecursive(g2d, child, childX, childY, childWidth, childrenMap, totalDuration)
                    childX += childWidth
                }
            }
        }
    }

    private fun getColorForDuration(durationMs: Double): Color {
        // Warm color palette (flame-like): fast=cool, slow=hot
        return when {
            durationMs < 1 -> Color(70, 130, 180)     // Steel blue (very fast)
            durationMs < 10 -> Color(144, 238, 144)   // Light green (fast)
            durationMs < 50 -> Color(255, 255, 153)   // Light yellow (moderate)
            durationMs < 100 -> Color(255, 200, 100)  // Orange (slow)
            durationMs < 500 -> Color(255, 140, 100)  // Dark orange (very slow)
            else -> Color(255, 100, 100)              // Red (critical)
        }
    }

    private fun truncateText(text: String, maxWidth: Int, g2d: Graphics2D): String {
        if (maxWidth < 20) return ""

        val metrics = g2d.fontMetrics
        var truncated = text

        while (metrics.stringWidth(truncated) > maxWidth && truncated.length > 3) {
            truncated = truncated.substring(0, truncated.length - 4) + "..."
        }

        return if (metrics.stringWidth(truncated) <= maxWidth) truncated else ""
    }

    private fun getFrameAtPoint(x: Int, y: Int): FlamegraphFrame? {
        // Search through cached rectangles
        for ((rect, frame) in frameRects) {
            if (rect.contains(x, y)) {
                return frame
            }
        }
        return null
    }

    private fun jumpToSource(frame: FlamegraphFrame) {
        try {
            val virtualFile = LocalFileSystem.getInstance().findFileByPath(frame.file)
            if (virtualFile != null) {
                val descriptor = OpenFileDescriptor(project, virtualFile, frame.line - 1, 0)
                FileEditorManager.getInstance(project).openTextEditor(descriptor, true)
            }
        } catch (e: Exception) {
            PluginLogger.warn("Could not open file: ${frame.file}:${frame.line} - ${e.message}")
        }
    }

    private fun buildTooltip(frame: FlamegraphFrame): String {
        return """
            <html>
            <div style="padding: 5px;">
            <b style="font-size: 12px;">${escapeHtml(frame.name)}</b><br><br>
            <b>Duration:</b> ${String.format("%.2f", frame.value)}ms<br>
            <b>File:</b> ${escapeHtml(frame.file)}:${frame.line}<br>
            <b>Depth:</b> ${frame.depth}<br>
            ${if (frame.framework != null) "<b>Framework:</b> ${frame.framework}<br>" else ""}
            ${if (frame.isAiAgent) "<b style='color: #4ec9b0;'>AI Agent</b><br>" else ""}
            <br><i>Double-click to jump to source</i>
            </div>
            </html>
        """.trimIndent()
    }

    private fun escapeHtml(text: String): String {
        return text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
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
