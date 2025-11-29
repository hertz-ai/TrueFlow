package com.crawl4ai.learningviz

import java.awt.*
import javax.swing.JPanel
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.max

/**
 * Live visualization renderer for learning flow.
 * Renders function calls in real-time as they arrive from trace events.
 */
class LiveFlowRenderer : JPanel() {

    // Track calls by correlation ID
    private val correlationTrees = ConcurrentHashMap<String, MutableList<CallNode>>()
    private var currentCorrelationId: String? = null

    // Display state
    private var offsetY = 0
    private val columnWidth = 250
    private val rowHeight = 60
    private val padding = 10

    data class CallNode(
        val callId: String,
        val functionName: String,
        val module: String,
        val depth: Int,
        val parentId: String?,
        val phase: String?,
        val correlationId: String,
        val threadId: String,
        var x: Int = 0,
        var y: Int = 0,
        var endTime: Double? = null,
        val parameters: Map<String, Any>? = null
    )

    init {
        background = Color.WHITE
        preferredSize = Dimension(800, 600)
    }

    /**
     * Add a call event from trace stream.
     */
    fun addCall(
        callId: String,
        functionName: String,
        module: String,
        depth: Int,
        parentId: String?,
        phase: String?,
        correlationId: String,
        threadId: String,
        parameters: Map<String, Any>? = null
    ) {
        val call = CallNode(
            callId, functionName, module, depth, parentId,
            phase, correlationId, threadId, parameters = parameters
        )

        // Get or create tree for this correlation ID
        val tree = correlationTrees.getOrPut(correlationId) { mutableListOf() }
        tree.add(call)

        // Set as current if this is the active cycle
        if (currentCorrelationId == null || currentCorrelationId == correlationId) {
            currentCorrelationId = correlationId
        }

        // Repaint to show new call
        repaint()
    }

    /**
     * Mark a call as complete.
     */
    fun completeCall(callId: String, endTime: Double) {
        currentCorrelationId?.let { corrId ->
            correlationTrees[corrId]?.find { it.callId == callId }?.endTime = endTime
        }
        repaint()
    }

    /**
     * Start a new correlation ID (learning cycle).
     */
    fun startCycle(correlationId: String) {
        currentCorrelationId = correlationId
        correlationTrees[correlationId] = mutableListOf()
        repaint()
    }

    /**
     * Complete a correlation ID (learning cycle).
     */
    fun completeCycle(correlationId: String) {
        // Keep the cycle but mark it as complete
        // User can still view it in history
        repaint()
    }

    override fun paintComponent(g: Graphics) {
        super.paintComponent(g)
        val g2d = g as Graphics2D

        // Enable antialiasing
        g2d.setRenderingHint(
            RenderingHints.KEY_ANTIALIASING,
            RenderingHints.VALUE_ANTIALIAS_ON
        )

        // No current cycle
        if (currentCorrelationId == null) {
            drawWaitingMessage(g2d)
            return
        }

        // Get calls for current correlation ID
        val calls = correlationTrees[currentCorrelationId] ?: emptyList()
        if (calls.isEmpty()) {
            drawWaitingMessage(g2d)
            return
        }

        // Draw correlation ID header
        drawHeader(g2d, currentCorrelationId!!)

        // Detect parallel threads
        val threadGroups = detectThreads(calls)

        // Layout: side-by-side columns for parallel threads
        val threadSpacing = max(columnWidth, width / maxOf(threadGroups.size, 1))

        threadGroups.forEachIndexed { index, threadCalls ->
            val xOffset = padding + index * threadSpacing
            drawThread(g2d, threadCalls, xOffset, threadSpacing)
        }

        // Draw timeline at bottom
        drawTimeline(g2d, calls)
    }

    private fun drawWaitingMessage(g2d: Graphics2D) {
        g2d.color = Color.GRAY
        g2d.font = Font("Sans-Serif", Font.ITALIC, 14)
        val msg = "Waiting for learning cycles... (Trace server on port 5678)"
        val bounds = g2d.fontMetrics.getStringBounds(msg, g2d)
        g2d.drawString(
            msg,
            (width - bounds.width.toInt()) / 2,
            height / 2
        )
    }

    private fun drawHeader(g2d: Graphics2D, correlationId: String) {
        g2d.color = Color.BLACK
        g2d.font = Font("Sans-Serif", Font.BOLD, 16)
        g2d.drawString("Learning Cycle: $correlationId", padding, 30)
    }

    private fun detectThreads(calls: List<CallNode>): List<List<CallNode>> {
        // Group by thread ID
        return calls.groupBy { it.threadId }.values.toList()
    }

    private fun drawThread(
        g2d: Graphics2D,
        calls: List<CallNode>,
        xOffset: Int,
        columnWidth: Int
    ) {
        var y = 60

        calls.forEach { call ->
            // Calculate position based on depth
            val x = xOffset + (call.depth * 20)
            val boxWidth = columnWidth - (call.depth * 40).coerceAtLeast(0)

            // Color by phase
            g2d.color = when (call.phase) {
                "forward" -> Color(100, 150, 255) // Blue
                "loss" -> Color(255, 200, 100)    // Yellow
                "backward" -> Color(255, 150, 100) // Orange
                "update" -> Color(100, 200, 100)  // Green
                else -> Color(200, 200, 200)      // Gray
            }

            // Draw call box
            g2d.fillRoundRect(x, y, boxWidth, 40, 10, 10)

            // Draw border
            g2d.color = Color.BLACK
            g2d.drawRoundRect(x, y, boxWidth, 40, 10, 10)

            // Draw function name
            g2d.font = Font("Monospace", Font.PLAIN, 11)
            val shortName = call.functionName.take(25)
            g2d.drawString(shortName, x + 5, y + 20)

            // Draw parameters if available
            call.parameters?.let { params ->
                g2d.font = Font("Monospace", Font.ITALIC, 9)
                g2d.color = Color.DARK_GRAY
                val paramStr = formatParameters(params)
                g2d.drawString(paramStr, x + 5, y + 35)
            }

            // Store position for arrow drawing
            call.x = x + boxWidth / 2
            call.y = y + 20

            y += rowHeight
        }
    }

    private fun formatParameters(params: Map<String, Any>): String {
        // Show first few parameters with shapes
        return params.entries.take(2).joinToString(", ") { (name, value) ->
            when (value) {
                is Map<*, *> -> {
                    val shape = (value as? Map<*, *>)?.get("shape")
                    val dtype = (value as? Map<*, *>)?.get("dtype")
                    if (shape != null) {
                        "$name: $shape"
                    } else {
                        "$name: ${(value as? Map<*, *>)?.get("type") ?: "?"}"
                    }
                }
                else -> "$name: $value"
            }
        }
    }

    private fun drawTimeline(g2d: Graphics2D, calls: List<CallNode>) {
        if (calls.isEmpty()) return

        val y = height - 40
        g2d.color = Color.DARK_GRAY
        g2d.drawLine(padding, y, width - padding, y)

        // Timeline labels
        g2d.font = Font("Sans-Serif", Font.PLAIN, 10)
        g2d.drawString("0.0s", padding, y + 15)
        g2d.drawString("t", width / 2, y + 15)

        // Duration if available
        val duration = calls.mapNotNull { it.endTime }.maxOrNull()
        if (duration != null) {
            g2d.drawString(String.format("%.2fs", duration), width - padding - 40, y + 15)
        }
    }

    /**
     * Clear all visualizations.
     */
    fun clear() {
        correlationTrees.clear()
        currentCorrelationId = null
        repaint()
    }

    /**
     * Get list of all correlation IDs (for history).
     */
    fun getCorrelationIds(): List<String> {
        return correlationTrees.keys.toList()
    }

    /**
     * Switch to viewing a specific correlation ID.
     */
    fun showCycle(correlationId: String) {
        if (correlationTrees.containsKey(correlationId)) {
            currentCorrelationId = correlationId
            repaint()
        }
    }
}
