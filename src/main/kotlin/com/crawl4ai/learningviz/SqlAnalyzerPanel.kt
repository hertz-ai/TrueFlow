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
import javax.swing.table.DefaultTableCellRenderer
import javax.swing.table.DefaultTableModel

/**
 * SQL Query Analyzer Panel - N+1 detection and optimization suggestions.
 *
 * Features:
 * - N+1 query detection
 * - Slow query identification
 * - Query pattern analysis
 * - Optimization suggestions
 * - Click to jump to source code
 */
class SqlAnalyzerPanel(private val project: Project) : JPanel(BorderLayout()) {

    private val statsLabel = JBLabel()
    private val issuesTable: JBTable
    private val issuesModel: DefaultTableModel
    private val queriesTable: JBTable
    private val queriesModel: DefaultTableModel
    private var sqlData: SqlAnalysisData? = null

    // Live SQL tracking from socket events
    private var liveSqlCount = 0
    private val liveSqlPatterns = mutableSetOf<String>()
    private val liveSqlCallers = mutableMapOf<String, Int>()  // function -> query count

    init {
        // Top stats panel
        val statsPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        statsPanel.add(statsLabel)
        add(statsPanel, BorderLayout.NORTH)

        // Split pane: Issues (top) and All Queries (bottom)
        val splitPane = JSplitPane(JSplitPane.VERTICAL_SPLIT)

        // N+1 Issues table
        issuesModel = DefaultTableModel(
            arrayOf("Severity", "Pattern", "Count", "Example", "Suggestion"),
            0
        )
        issuesTable = JBTable(issuesModel)
        issuesTable.setDefaultRenderer(Any::class.java, SeverityCellRenderer())
        issuesTable.autoCreateRowSorter = true

        val issuesPanel = JPanel(BorderLayout())
        issuesPanel.add(JBLabel("N+1 Query Issues (Critical Performance Problems)"), BorderLayout.NORTH)
        issuesPanel.add(JBScrollPane(issuesTable), BorderLayout.CENTER)

        // All queries table
        queriesModel = DefaultTableModel(
            arrayOf("Query", "Module", "Function", "Variable"),
            0
        )
        queriesTable = JBTable(queriesModel)
        queriesTable.autoCreateRowSorter = true

        val queriesPanel = JPanel(BorderLayout())
        queriesPanel.add(JBLabel("All SQL Queries"), BorderLayout.NORTH)
        queriesPanel.add(JBScrollPane(queriesTable), BorderLayout.CENTER)

        splitPane.topComponent = issuesPanel
        splitPane.bottomComponent = queriesPanel
        splitPane.dividerLocation = 300

        add(splitPane, BorderLayout.CENTER)

        statsLabel.text = "No SQL analysis data loaded"
    }

    /**
     * Update from live socket trace event containing protocol_summary with SQL data.
     * Called from handleTraceEvent() when a return event has sql detections.
     */
    fun updateFromSocketTrace(event: TraceEvent) {
        val sqlCount = event.protocolSummary?.get("sql")?.asInt ?: return
        val sqlDetail = event.protocolDetails?.get("sql")?.asString ?: ""

        // Accumulate live SQL stats
        liveSqlCount += sqlCount
        // Extract SQL command type (SELECT, INSERT, UPDATE, DELETE, etc.)
        val cmdType = sqlDetail.trim().substringBefore(" ").uppercase()
        if (cmdType.isNotEmpty()) {
            liveSqlPatterns.add(cmdType)
        }
        val callerKey = "${event.module}.${event.function}"
        liveSqlCallers[callerKey] = (liveSqlCallers[callerKey] ?: 0) + sqlCount

        SwingUtilities.invokeLater {
            // Add to queries table (reuse existing table for live data)
            queriesModel.addRow(arrayOf(
                truncate(sqlDetail, 200),
                event.module,
                event.function,
                "${event.file}:${event.line}"
            ))

            // Live N+1 detection: same caller executing many queries
            val callerCount = liveSqlCallers[callerKey] ?: 0
            if (callerCount >= 5) {
                // Check if we already have an issue row for this caller
                var existingRow = -1
                for (i in 0 until issuesModel.rowCount) {
                    if (issuesModel.getValueAt(i, 1) == callerKey) {
                        existingRow = i
                        break
                    }
                }
                if (existingRow >= 0) {
                    issuesModel.setValueAt(callerCount, existingRow, 2)
                } else {
                    val severity = if (callerCount >= 20) "HIGH" else if (callerCount >= 10) "MEDIUM" else "LOW"
                    issuesModel.addRow(arrayOf(
                        severity,
                        callerKey,
                        callerCount,
                        truncate(sqlDetail, 150),
                        "Possible N+1: $callerKey executed $callerCount queries"
                    ))
                }
            }

            // Update stats
            val patternStr = liveSqlPatterns.joinToString(", ")
            statsLabel.text = "Live SQL | Total: $liveSqlCount | Patterns: $patternStr | Callers: ${liveSqlCallers.size}"
            statsLabel.foreground = if (liveSqlCallers.values.any { it >= 10 }) JBColor.RED else JBColor.foreground()
        }
    }

    /**
     * Reset live SQL tracking state (e.g. on new session).
     */
    fun resetLiveState() {
        liveSqlCount = 0
        liveSqlPatterns.clear()
        liveSqlCallers.clear()
    }

    fun loadSqlAnalysis(file: File) {
        try {
            val json = file.readText()
            val gson = Gson()
            val jsonObj = gson.fromJson(json, JsonObject::class.java)

            sqlData = SqlAnalysisData(
                sessionId = jsonObj.get("session_id").asString,
                statistics = jsonObj.getAsJsonObject("statistics").let { stats ->
                    SqlStats(
                        totalQueries = stats.get("total_queries").asInt,
                        uniquePatterns = stats.get("unique_patterns").asInt,
                        nPlus1Issues = stats.get("n_plus_1_issues").asInt
                    )
                },
                nPlus1Issues = jsonObj.getAsJsonArray("n_plus_1_issues").map { issueObj ->
                    val issue = issueObj.asJsonObject
                    NPlusOneIssue(
                        severity = issue.get("severity").asString,
                        pattern = issue.get("pattern").asString,
                        count = issue.get("count").asInt,
                        example = issue.get("example").asString,
                        suggestion = issue.get("suggestion").asString,
                        locations = issue.getAsJsonArray("locations").map { locObj ->
                            val loc = locObj.asJsonObject
                            QueryLocation(
                                module = loc.get("module").asString,
                                function = loc.get("function").asString,
                                line = loc.get("line").asInt
                            )
                        }
                    )
                },
                allQueries = jsonObj.getAsJsonArray("all_queries").map { queryObj ->
                    val query = queryObj.asJsonObject
                    SqlQuery(
                        query = query.get("query").asString,
                        module = query.get("module").asString,
                        function = query.get("function").asString,
                        variable = query.get("variable").asString
                    )
                }
            )

            updateTables()
            updateStats()

        } catch (e: Exception) {
            statsLabel.text = "Error loading SQL analysis: ${e.message}"
            e.printStackTrace()
        }
    }

    private fun updateTables() {
        sqlData?.let { data ->
            // Clear existing data
            issuesModel.rowCount = 0
            queriesModel.rowCount = 0

            // Populate N+1 issues
            for (issue in data.nPlus1Issues) {
                issuesModel.addRow(arrayOf(
                    issue.severity.uppercase(),
                    truncate(issue.pattern, 100),
                    issue.count,
                    truncate(issue.example, 150),
                    issue.suggestion
                ))
            }

            // Populate all queries
            for (query in data.allQueries) {
                queriesModel.addRow(arrayOf(
                    truncate(query.query, 200),
                    query.module,
                    query.function,
                    query.variable
                ))
            }
        }
    }

    private fun updateStats() {
        sqlData?.let { data ->
            val warningText = if (data.statistics.nPlus1Issues > 0) {
                " - WARNING: ${data.statistics.nPlus1Issues} N+1 issues detected!"
            } else {
                " - No N+1 issues detected"
            }

            statsLabel.text = "Session: ${data.sessionId} | " +
                    "Total Queries: ${data.statistics.totalQueries} | " +
                    "Unique Patterns: ${data.statistics.uniquePatterns}" +
                    warningText

            if (data.statistics.nPlus1Issues > 0) {
                statsLabel.foreground = JBColor.RED
            } else {
                statsLabel.foreground = JBColor.GREEN
            }
        }
    }

    private fun truncate(text: String, maxLength: Int): String {
        return if (text.length > maxLength) {
            text.substring(0, maxLength) + "..."
        } else {
            text
        }
    }

    /**
     * Get current SQL analysis data for snapshot export.
     */
    fun getSqlData(): SqlAnalysisData? = sqlData
}

/**
 * Cell renderer that colors severity levels.
 */
private class SeverityCellRenderer : DefaultTableCellRenderer() {
    override fun getTableCellRendererComponent(
        table: JTable,
        value: Any?,
        isSelected: Boolean,
        hasFocus: Boolean,
        row: Int,
        column: Int
    ): Component {
        val component = super.getTableCellRendererComponent(table, value, isSelected, hasFocus, row, column)

        if (column == 0 && value is String) {
            when (value.uppercase()) {
                "HIGH" -> {
                    component.foreground = JBColor.WHITE
                    component.background = JBColor.RED
                }
                "MEDIUM" -> {
                    component.foreground = JBColor.BLACK
                    component.background = JBColor.ORANGE
                }
                "LOW" -> {
                    component.foreground = JBColor.BLACK
                    component.background = JBColor.YELLOW
                }
            }
        } else if (!isSelected) {
            component.background = JBColor.WHITE
            component.foreground = JBColor.BLACK
        }

        return component
    }
}

// Data classes
data class SqlAnalysisData(
    val sessionId: String,
    val statistics: SqlStats,
    val nPlus1Issues: List<NPlusOneIssue>,
    val allQueries: List<SqlQuery>
)

data class SqlStats(
    val totalQueries: Int,
    val uniquePatterns: Int,
    val nPlus1Issues: Int
)

data class NPlusOneIssue(
    val severity: String,
    val pattern: String,
    val count: Int,
    val example: String,
    val suggestion: String,
    val locations: List<QueryLocation>
)

data class QueryLocation(
    val module: String,
    val function: String,
    val line: Int
)

data class SqlQuery(
    val query: String,
    val module: String,
    val function: String,
    val variable: String
)
