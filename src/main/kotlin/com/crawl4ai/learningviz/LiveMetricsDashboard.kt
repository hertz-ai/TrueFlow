package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.project.Project
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.table.JBTable
import java.awt.*
import java.io.File
import javax.swing.*
import javax.swing.table.DefaultTableModel
import kotlin.math.roundToInt

/**
 * Live Metrics Dashboard - Real-time performance monitoring.
 *
 * Features:
 * - Live metrics (requests/sec, latency, errors)
 * - Top slowest endpoints
 * - Recent errors
 * - Visual gauges and charts
 * - Auto-refresh capability
 */
class LiveMetricsDashboard(private val project: Project) : JPanel(BorderLayout()) {

    private val metricsPanel = JPanel(GridLayout(2, 3, 10, 10))
    private val requestsLabel = MetricGaugeLabel("Requests/sec", "0", JBColor.BLUE)
    private val latencyLabel = MetricGaugeLabel("Avg Latency", "0ms", JBColor.GREEN)
    private val errorRateLabel = MetricGaugeLabel("Error Rate", "0%", JBColor.RED)
    private val totalCallsLabel = MetricGaugeLabel("Total Calls", "0", JBColor.CYAN)
    private val activeCallsLabel = MetricGaugeLabel("Active Calls", "0", JBColor.MAGENTA)
    private val sessionLabel = MetricGaugeLabel("Session", "N/A", JBColor.GRAY)

    private val slowestTable: JBTable
    private val slowestModel: DefaultTableModel
    private val errorsTable: JBTable
    private val errorsModel: DefaultTableModel

    private var metricsData: LiveMetricsData? = null
    private var autoRefresh = false
    private var refreshTimer: Timer? = null

    init {
        // Top metrics gauges
        metricsPanel.border = BorderFactory.createTitledBorder("Live Metrics")
        metricsPanel.add(requestsLabel)
        metricsPanel.add(latencyLabel)
        metricsPanel.add(errorRateLabel)
        metricsPanel.add(totalCallsLabel)
        metricsPanel.add(activeCallsLabel)
        metricsPanel.add(sessionLabel)

        val topPanel = JPanel(BorderLayout())
        topPanel.add(metricsPanel, BorderLayout.CENTER)

        // Auto-refresh controls
        val controlsPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        val autoRefreshCheckbox = JCheckBox("Auto-refresh (1s)", false)
        autoRefreshCheckbox.addActionListener {
            autoRefresh = autoRefreshCheckbox.isSelected
            if (autoRefresh) {
                startAutoRefresh()
            } else {
                stopAutoRefresh()
            }
        }
        controlsPanel.add(autoRefreshCheckbox)

        val refreshButton = JButton("Refresh Now")
        refreshButton.addActionListener {
            // Trigger manual refresh
            // TODO: Reload from file
        }
        controlsPanel.add(refreshButton)

        topPanel.add(controlsPanel, BorderLayout.SOUTH)
        add(topPanel, BorderLayout.NORTH)

        // Split pane: Top Slowest (left) and Recent Errors (right)
        val splitPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT)

        // Top slowest functions table
        slowestModel = DefaultTableModel(
            arrayOf("Function", "Duration (ms)", "File:Line"),
            0
        )
        slowestTable = JBTable(slowestModel)
        slowestTable.autoCreateRowSorter = true

        val slowestPanel = JPanel(BorderLayout())
        slowestPanel.add(JBLabel("Top 10 Slowest Functions"), BorderLayout.NORTH)
        slowestPanel.add(JBScrollPane(slowestTable), BorderLayout.CENTER)

        // Recent errors table
        errorsModel = DefaultTableModel(
            arrayOf("Function", "Exception", "Timestamp"),
            0
        )
        errorsTable = JBTable(errorsModel)
        errorsTable.autoCreateRowSorter = true

        val errorsPanel = JPanel(BorderLayout())
        errorsPanel.add(JBLabel("Recent Errors"), BorderLayout.NORTH)
        errorsPanel.add(JBScrollPane(errorsTable), BorderLayout.CENTER)

        splitPane.leftComponent = slowestPanel
        splitPane.rightComponent = errorsPanel
        splitPane.dividerLocation = 400

        add(splitPane, BorderLayout.CENTER)
    }

    /**
     * Update metrics from real-time trace events (socket streaming).
     * This is called from handleTraceEvent() in EnhancedLearningFlowToolWindow.
     */
    fun updateFromSocketTrace(
        totalCalls: Int,
        avgLatencyMs: Double,
        sessionId: String,
        topSlowestFunctions: List<Pair<String, Pair<Double, Pair<String, Int>>>>,
        recentErrors: List<Triple<String, String, Double>>
    ) {
        SwingUtilities.invokeLater {
            try {
                // Update metrics data structure
                metricsData = LiveMetricsData(
                    sessionId = sessionId,
                    timestamp = System.currentTimeMillis() / 1000.0,
                    metrics = Metrics(
                        requestsPerSec = 0.0, // TODO: Calculate from time window
                        avgLatencyMs = avgLatencyMs,
                        errorRatePercent = if (totalCalls > 0) (recentErrors.size.toDouble() / totalCalls) * 100 else 0.0,
                        totalCalls = totalCalls,
                        activeCalls = 0 // TODO: Track active calls
                    ),
                    topSlowest = topSlowestFunctions.map { (funcKey, data) ->
                        val (durationMs, fileLine) = data
                        val (file, line) = fileLine
                        SlowestFunction(funcKey, durationMs, file, line)
                    },
                    recentErrors = recentErrors.map { (funcKey, exception, timestamp) ->
                        RecentError(funcKey, exception, timestamp)
                    }
                )

                updateDisplay()

            } catch (e: Exception) {
                sessionLabel.setValue("Error: ${e.message}")
                e.printStackTrace()
            }
        }
    }

    fun loadMetrics(file: File) {
        try {
            val json = file.readText()
            val gson = Gson()
            val jsonObj = gson.fromJson(json, JsonObject::class.java)

            metricsData = LiveMetricsData(
                sessionId = jsonObj.get("session_id").asString,
                timestamp = jsonObj.get("timestamp").asDouble,
                metrics = jsonObj.getAsJsonObject("metrics").let { m ->
                    Metrics(
                        requestsPerSec = m.get("requests_per_sec").asDouble,
                        avgLatencyMs = m.get("avg_latency_ms").asDouble,
                        errorRatePercent = m.get("error_rate_percent").asDouble,
                        totalCalls = m.get("total_calls").asInt,
                        activeCalls = m.get("active_calls").asInt
                    )
                },
                topSlowest = jsonObj.getAsJsonArray("top_slowest").map { slowObj ->
                    val slow = slowObj.asJsonObject
                    SlowestFunction(
                        function = slow.get("function").asString,
                        durationMs = slow.get("duration_ms").asDouble,
                        file = slow.get("file").asString,
                        line = slow.get("line").asInt
                    )
                },
                recentErrors = jsonObj.getAsJsonArray("recent_errors").map { errObj ->
                    val err = errObj.asJsonObject
                    RecentError(
                        function = err.get("function").asString,
                        exception = err.get("exception").asString,
                        timestamp = err.get("timestamp").asDouble
                    )
                }
            )

            updateDisplay()

        } catch (e: Exception) {
            sessionLabel.setValue("Error: ${e.message}")
            e.printStackTrace()
        }
    }

    private fun updateDisplay() {
        metricsData?.let { data ->
            // Update metrics gauges
            requestsLabel.setValue(String.format("%.1f", data.metrics.requestsPerSec))
            latencyLabel.setValue(String.format("%.1fms", data.metrics.avgLatencyMs))
            errorRateLabel.setValue(String.format("%.2f%%", data.metrics.errorRatePercent))
            totalCallsLabel.setValue(data.metrics.totalCalls.toString())
            activeCallsLabel.setValue(data.metrics.activeCalls.toString())
            sessionLabel.setValue(data.sessionId.replace("session_", ""))

            // Color-code error rate
            when {
                data.metrics.errorRatePercent > 5 -> errorRateLabel.setColor(JBColor.RED)
                data.metrics.errorRatePercent > 1 -> errorRateLabel.setColor(JBColor.ORANGE)
                else -> errorRateLabel.setColor(JBColor.GREEN)
            }

            // Color-code latency
            when {
                data.metrics.avgLatencyMs > 500 -> latencyLabel.setColor(JBColor.RED)
                data.metrics.avgLatencyMs > 200 -> latencyLabel.setColor(JBColor.ORANGE)
                else -> latencyLabel.setColor(JBColor.GREEN)
            }

            // Update tables
            updateTables()
        }
    }

    private fun updateTables() {
        metricsData?.let { data ->
            // Clear existing data
            slowestModel.rowCount = 0
            errorsModel.rowCount = 0

            // Populate slowest functions
            for (slow in data.topSlowest) {
                slowestModel.addRow(arrayOf(
                    slow.function,
                    String.format("%.2f", slow.durationMs),
                    "${slow.file}:${slow.line}"
                ))
            }

            // Populate recent errors
            for (error in data.recentErrors) {
                errorsModel.addRow(arrayOf(
                    error.function,
                    error.exception,
                    formatTimestamp(error.timestamp)
                ))
            }
        }
    }

    private fun startAutoRefresh() {
        refreshTimer = Timer(1000) {
            // TODO: Reload metrics file
            // loadMetrics(currentFile)
        }
        refreshTimer?.start()
    }

    private fun stopAutoRefresh() {
        refreshTimer?.stop()
        refreshTimer = null
    }

    private fun formatTimestamp(timestamp: Double): String {
        val date = java.util.Date((timestamp * 1000).toLong())
        val formatter = java.text.SimpleDateFormat("HH:mm:ss")
        return formatter.format(date)
    }
}

/**
 * Custom label for displaying metric gauges with large numbers and colors.
 */
private class MetricGaugeLabel(
    private val metricName: String,
    private var value: String,
    private var metricColor: Color
) : JPanel(BorderLayout()) {

    private val nameLabel = JBLabel(metricName)
    private val valueLabel = JBLabel(value)

    init {
        border = BorderFactory.createLineBorder(JBColor.GRAY, 2, true)
        background = JBColor.WHITE

        nameLabel.horizontalAlignment = SwingConstants.CENTER
        nameLabel.font = nameLabel.font.deriveFont(12f)
        add(nameLabel, BorderLayout.NORTH)

        valueLabel.horizontalAlignment = SwingConstants.CENTER
        valueLabel.font = valueLabel.font.deriveFont(Font.BOLD, 24f)
        valueLabel.foreground = metricColor
        add(valueLabel, BorderLayout.CENTER)

        preferredSize = Dimension(150, 80)
    }

    fun setValue(newValue: String) {
        value = newValue
        valueLabel.text = value
    }

    fun setColor(color: Color) {
        metricColor = color
        valueLabel.foreground = color
    }
}

// Data classes
data class LiveMetricsData(
    val sessionId: String,
    val timestamp: Double,
    val metrics: Metrics,
    val topSlowest: List<SlowestFunction>,
    val recentErrors: List<RecentError>
)

data class Metrics(
    val requestsPerSec: Double,
    val avgLatencyMs: Double,
    val errorRatePercent: Double,
    val totalCalls: Int,
    val activeCalls: Int
)

data class SlowestFunction(
    val function: String,
    val durationMs: Double,
    val file: String,
    val line: Int
)

data class RecentError(
    val function: String,
    val exception: String,
    val timestamp: Double
)
