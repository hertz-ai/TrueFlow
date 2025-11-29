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

/**
 * Distributed Architecture Panel - WebSocket, WebRTC, MCP, A2A, Cross-Process Analysis.
 *
 * Features:
 * - WebSocket connection tracking
 * - WebRTC peer connection monitoring
 * - MCP (Model Context Protocol) call tracing
 * - Agent-to-Agent (A2A) communication flow
 * - Cross-process architecture stitching
 * - Distributed trace ID correlation
 */
class DistributedArchitecturePanel(private val project: Project) : JPanel(BorderLayout()) {

    private val statsLabel = JBLabel()
    private val architectureCanvas = ArchitectureCanvas()
    private val tabbedPane = JTabbedPane()

    // WebSocket events table
    private val websocketTable: JBTable
    private val websocketModel: DefaultTableModel

    // WebRTC events table
    private val webrtcTable: JBTable
    private val webrtcModel: DefaultTableModel

    // MCP calls table
    private val mcpTable: JBTable
    private val mcpModel: DefaultTableModel

    // Agent communications table
    private val agentTable: JBTable
    private val agentModel: DefaultTableModel

    // Process spawns table
    private val processTable: JBTable
    private val processModel: DefaultTableModel

    private var distributedData: DistributedAnalysisData? = null

    init {
        // Top stats panel
        val statsPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        statsPanel.add(statsLabel)
        add(statsPanel, BorderLayout.NORTH)

        // WebSocket table
        websocketModel = DefaultTableModel(
            arrayOf("Module", "Function", "Type", "Data", "Timestamp"),
            0
        )
        websocketTable = JBTable(websocketModel)
        websocketTable.autoCreateRowSorter = true

        val websocketPanel = JPanel(BorderLayout())
        websocketPanel.add(JBLabel("WebSocket Events (ws:// wss:// socket.io)"), BorderLayout.NORTH)
        websocketPanel.add(JBScrollPane(websocketTable), BorderLayout.CENTER)

        // WebRTC table
        webrtcModel = DefaultTableModel(
            arrayOf("Module", "Function", "Type", "Data", "Timestamp"),
            0
        )
        webrtcTable = JBTable(webrtcModel)
        webrtcTable.autoCreateRowSorter = true

        val webrtcPanel = JPanel(BorderLayout())
        webrtcPanel.add(JBLabel("WebRTC Events (RTCPeerConnection, RTCDataChannel)"), BorderLayout.NORTH)
        webrtcPanel.add(JBScrollPane(webrtcTable), BorderLayout.CENTER)

        // MCP table
        mcpModel = DefaultTableModel(
            arrayOf("Module", "Function", "Protocol", "Data", "Timestamp"),
            0
        )
        mcpTable = JBTable(mcpModel)
        mcpTable.autoCreateRowSorter = true

        val mcpPanel = JPanel(BorderLayout())
        mcpPanel.add(JBLabel("MCP (Model Context Protocol) Calls"), BorderLayout.NORTH)
        mcpPanel.add(JBScrollPane(mcpTable), BorderLayout.CENTER)

        // Agent communications table
        agentModel = DefaultTableModel(
            arrayOf("Module", "Function", "Framework", "Type", "Data", "Timestamp"),
            0
        )
        agentTable = JBTable(agentModel)
        agentTable.autoCreateRowSorter = true

        val agentPanel = JPanel(BorderLayout())
        agentPanel.add(JBLabel("Agent-to-Agent Communications (AutoGen, CrewAI, LangGraph)"), BorderLayout.NORTH)
        agentPanel.add(JBScrollPane(agentTable), BorderLayout.CENTER)

        // Process spawns table
        processModel = DefaultTableModel(
            arrayOf("Module", "Function", "Type", "PID", "Distributed Trace ID", "Timestamp"),
            0
        )
        processTable = JBTable(processModel)
        processTable.autoCreateRowSorter = true

        val processPanel = JPanel(BorderLayout())
        processPanel.add(JBLabel("Cross-Process Spawns (multiprocessing, subprocess)"), BorderLayout.NORTH)
        processPanel.add(JBScrollPane(processTable), BorderLayout.CENTER)

        // Architecture canvas tab
        val archPanel = JPanel(BorderLayout())
        archPanel.add(JBLabel("Distributed Architecture Map"), BorderLayout.NORTH)
        archPanel.add(JBScrollPane(architectureCanvas), BorderLayout.CENTER)

        // Add all tabs
        tabbedPane.addTab("Architecture Map", archPanel)
        tabbedPane.addTab("WebSocket", websocketPanel)
        tabbedPane.addTab("WebRTC", webrtcPanel)
        tabbedPane.addTab("MCP", mcpPanel)
        tabbedPane.addTab("Agent-to-Agent", agentPanel)
        tabbedPane.addTab("Cross-Process", processPanel)

        add(tabbedPane, BorderLayout.CENTER)

        statsLabel.text = "No distributed analysis data loaded"
    }

    fun loadDistributedAnalysis(file: File) {
        try {
            val json = file.readText()
            val gson = Gson()
            val jsonObj = gson.fromJson(json, JsonObject::class.java)

            distributedData = DistributedAnalysisData(
                sessionId = jsonObj.get("session_id").asString,
                distributedTraceId = jsonObj.get("distributed_trace_id").asString,
                processInfo = jsonObj.getAsJsonObject("process_info").let { proc ->
                    ProcessInfo(
                        pid = proc.get("pid").asInt,
                        parentPid = proc.get("parent_pid").asInt
                    )
                },
                statistics = jsonObj.getAsJsonObject("statistics").let { stats ->
                    DistributedStats(
                        websocketEvents = stats.get("websocket_events").asInt,
                        webrtcEvents = stats.get("webrtc_events").asInt,
                        mcpCalls = stats.get("mcp_calls").asInt,
                        agentCommunications = stats.get("agent_communications").asInt,
                        processSpawns = stats.get("process_spawns").asInt
                    )
                },
                websocketEvents = jsonObj.getAsJsonArray("websocket_events").map { wsObj ->
                    val ws = wsObj.asJsonObject
                    WebSocketEvent(
                        module = ws.get("module").asString,
                        function = ws.get("function").asString,
                        type = ws.get("type").asString,
                        data = ws.get("data").asString,
                        timestamp = ws.get("timestamp").asDouble
                    )
                },
                webrtcEvents = jsonObj.getAsJsonArray("webrtc_events").map { rtcObj ->
                    val rtc = rtcObj.asJsonObject
                    WebRTCEvent(
                        module = rtc.get("module").asString,
                        function = rtc.get("function").asString,
                        type = rtc.get("type").asString,
                        data = rtc.get("data").asString,
                        timestamp = rtc.get("timestamp").asDouble
                    )
                },
                mcpCalls = jsonObj.getAsJsonArray("mcp_calls").map { mcpObj ->
                    val mcp = mcpObj.asJsonObject
                    MCPCall(
                        module = mcp.get("module").asString,
                        function = mcp.get("function").asString,
                        protocol = mcp.get("protocol").asString,
                        data = mcp.get("data").asString,
                        timestamp = mcp.get("timestamp").asDouble
                    )
                },
                agentCommunications = jsonObj.getAsJsonArray("agent_communications").map { agentObj ->
                    val agent = agentObj.asJsonObject
                    AgentCommunication(
                        module = agent.get("module").asString,
                        function = agent.get("function").asString,
                        type = agent.get("type").asString,
                        framework = agent.get("framework").asString,
                        data = agent.get("data").asString,
                        timestamp = agent.get("timestamp").asDouble
                    )
                },
                processSpawns = jsonObj.getAsJsonArray("process_spawns").map { procObj ->
                    val proc = procObj.asJsonObject
                    ProcessSpawn(
                        module = proc.get("module").asString,
                        function = proc.get("function").asString,
                        type = proc.get("type").asString,
                        processId = proc.get("process_id").asInt,
                        distributedTraceId = proc.get("distributed_trace_id").asString,
                        timestamp = proc.get("timestamp").asDouble
                    )
                }
            )

            updateTables()
            updateStats()
            architectureCanvas.setData(distributedData!!)

        } catch (e: Exception) {
            statsLabel.text = "Error loading distributed analysis: ${e.message}"
            e.printStackTrace()
        }
    }

    private fun updateTables() {
        distributedData?.let { data ->
            // Clear existing data
            websocketModel.rowCount = 0
            webrtcModel.rowCount = 0
            mcpModel.rowCount = 0
            agentModel.rowCount = 0
            processModel.rowCount = 0

            // Populate WebSocket events
            for (ws in data.websocketEvents) {
                websocketModel.addRow(arrayOf(
                    ws.module,
                    ws.function,
                    ws.type,
                    truncate(ws.data, 100),
                    formatTimestamp(ws.timestamp)
                ))
            }

            // Populate WebRTC events
            for (rtc in data.webrtcEvents) {
                webrtcModel.addRow(arrayOf(
                    rtc.module,
                    rtc.function,
                    rtc.type,
                    truncate(rtc.data, 100),
                    formatTimestamp(rtc.timestamp)
                ))
            }

            // Populate MCP calls
            for (mcp in data.mcpCalls) {
                mcpModel.addRow(arrayOf(
                    mcp.module,
                    mcp.function,
                    mcp.protocol,
                    truncate(mcp.data, 100),
                    formatTimestamp(mcp.timestamp)
                ))
            }

            // Populate agent communications
            for (agent in data.agentCommunications) {
                agentModel.addRow(arrayOf(
                    agent.module,
                    agent.function,
                    agent.framework,
                    agent.type,
                    truncate(agent.data, 100),
                    formatTimestamp(agent.timestamp)
                ))
            }

            // Populate process spawns
            for (proc in data.processSpawns) {
                processModel.addRow(arrayOf(
                    proc.module,
                    proc.function,
                    proc.type,
                    proc.processId,
                    proc.distributedTraceId,
                    formatTimestamp(proc.timestamp)
                ))
            }
        }
    }

    private fun updateStats() {
        distributedData?.let { data ->
            statsLabel.text = "Session: ${data.sessionId} | " +
                    "Trace ID: ${data.distributedTraceId} | " +
                    "PID: ${data.processInfo.pid} | " +
                    "WebSocket: ${data.statistics.websocketEvents} | " +
                    "WebRTC: ${data.statistics.webrtcEvents} | " +
                    "MCP: ${data.statistics.mcpCalls} | " +
                    "A2A: ${data.statistics.agentCommunications} | " +
                    "Processes: ${data.statistics.processSpawns}"
        }
    }

    private fun truncate(text: String, maxLength: Int): String {
        return if (text.length > maxLength) {
            text.substring(0, maxLength) + "..."
        } else {
            text
        }
    }

    private fun formatTimestamp(timestamp: Double): String {
        val date = java.util.Date((timestamp * 1000).toLong())
        val formatter = java.text.SimpleDateFormat("HH:mm:ss.SSS")
        return formatter.format(date)
    }

    /**
     * Update distributed panel from real-time socket trace events.
     * Detects distributed patterns based on module/function names.
     */
    fun updateFromSocketTrace(
        event: TraceEvent,
        isWebSocket: Boolean,
        isWebRTC: Boolean,
        isMCP: Boolean,
        isAgent: Boolean,
        isProcess: Boolean
    ) {
        val timestamp = formatTimestamp(event.timestamp)
        val eventData = "${event.module}.${event.function}() at ${event.file}:${event.line}"

        // Add to appropriate table based on detected type
        if (isWebSocket) {
            websocketModel.addRow(arrayOf(
                event.module,
                event.function,
                "call", // Type (we only have call events from socket)
                truncate(eventData, 100),
                timestamp
            ))
        }

        if (isWebRTC) {
            webrtcModel.addRow(arrayOf(
                event.module,
                event.function,
                "call",
                truncate(eventData, 100),
                timestamp
            ))
        }

        if (isMCP) {
            mcpModel.addRow(arrayOf(
                event.module,
                event.function,
                "unknown", // Protocol (not available from basic trace)
                truncate(eventData, 100),
                timestamp
            ))
        }

        if (isAgent) {
            agentModel.addRow(arrayOf(
                event.module,
                event.function,
                "detected", // Framework
                "call",
                truncate(eventData, 100),
                timestamp
            ))
        }

        if (isProcess) {
            processModel.addRow(arrayOf(
                event.module,
                event.function,
                "spawn/fork",
                event.processId,
                event.sessionId,
                timestamp
            ))
        }

        // Update stats label
        val wsCount = websocketModel.rowCount
        val rtcCount = webrtcModel.rowCount
        val mcpCount = mcpModel.rowCount
        val agentCount = agentModel.rowCount
        val processCount = processModel.rowCount

        statsLabel.text = "Real-time mode | " +
                "Session: ${event.sessionId} | " +
                "PID: ${event.processId} | " +
                "WebSocket: $wsCount | " +
                "WebRTC: $rtcCount | " +
                "MCP: $mcpCount | " +
                "Agents: $agentCount | " +
                "Processes: $processCount"
    }
}

/**
 * Canvas for rendering distributed architecture map.
 */
private class ArchitectureCanvas : JPanel() {

    private var data: DistributedAnalysisData? = null

    init {
        preferredSize = Dimension(800, 600)
        background = JBColor.WHITE
    }

    fun setData(data: DistributedAnalysisData) {
        this.data = data
        repaint()
    }

    override fun paintComponent(g: Graphics) {
        super.paintComponent(g)
        val g2d = g as Graphics2D
        g2d.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)

        data?.let { archData ->
            drawArchitecture(g2d, archData)
        }
    }

    private fun drawArchitecture(g2d: Graphics2D, archData: DistributedAnalysisData) {
        val centerX = width / 2
        val centerY = height / 2
        val radius = 200

        // Draw current process (center)
        g2d.color = JBColor.BLUE
        g2d.fillOval(centerX - 50, centerY - 50, 100, 100)
        g2d.color = JBColor.BLACK
        g2d.drawString("Process ${archData.processInfo.pid}", centerX - 40, centerY)

        // Draw connections in a circle
        var angle = 0.0
        val angleStep = 2 * Math.PI / maxOf(
            archData.statistics.websocketEvents,
            archData.statistics.webrtcEvents,
            archData.statistics.mcpCalls,
            archData.statistics.agentCommunications,
            archData.statistics.processSpawns,
            1
        )

        // WebSocket connections (green)
        g2d.color = JBColor.GREEN
        for (i in 0 until archData.statistics.websocketEvents) {
            val x = (centerX + radius * Math.cos(angle)).toInt()
            val y = (centerY + radius * Math.sin(angle)).toInt()
            g2d.drawLine(centerX, centerY, x, y)
            g2d.fillOval(x - 10, y - 10, 20, 20)
            g2d.drawString("WS", x - 10, y - 15)
            angle += angleStep
        }

        // WebRTC connections (orange)
        g2d.color = JBColor.ORANGE
        for (i in 0 until archData.statistics.webrtcEvents) {
            val x = (centerX + radius * Math.cos(angle)).toInt()
            val y = (centerY + radius * Math.sin(angle)).toInt()
            g2d.drawLine(centerX, centerY, x, y)
            g2d.fillOval(x - 10, y - 10, 20, 20)
            g2d.drawString("RTC", x - 10, y - 15)
            angle += angleStep
        }

        // MCP calls (purple)
        g2d.color = JBColor.MAGENTA
        for (i in 0 until archData.statistics.mcpCalls) {
            val x = (centerX + radius * Math.cos(angle)).toInt()
            val y = (centerY + radius * Math.sin(angle)).toInt()
            g2d.drawLine(centerX, centerY, x, y)
            g2d.fillOval(x - 10, y - 10, 20, 20)
            g2d.drawString("MCP", x - 10, y - 15)
            angle += angleStep
        }

        // Agent communications (cyan)
        g2d.color = JBColor.CYAN
        for (i in 0 until archData.statistics.agentCommunications) {
            val x = (centerX + radius * Math.cos(angle)).toInt()
            val y = (centerY + radius * Math.sin(angle)).toInt()
            g2d.drawLine(centerX, centerY, x, y)
            g2d.fillOval(x - 10, y - 10, 20, 20)
            g2d.drawString("A2A", x - 10, y - 15)
            angle += angleStep
        }

        // Process spawns (red)
        g2d.color = JBColor.RED
        for ((index, proc) in archData.processSpawns.withIndex()) {
            val x = (centerX + radius * Math.cos(angle)).toInt()
            val y = (centerY + radius * Math.sin(angle)).toInt()
            g2d.drawLine(centerX, centerY, x, y)
            g2d.fillRect(x - 15, y - 15, 30, 30)
            g2d.color = JBColor.WHITE
            g2d.drawString("P${proc.processId}", x - 10, y)
            g2d.color = JBColor.RED
            angle += angleStep
        }

        // Legend
        g2d.color = JBColor.BLACK
        val legendX = 10
        var legendY = 20
        g2d.drawString("Legend:", legendX, legendY)
        legendY += 20

        g2d.color = JBColor.GREEN
        g2d.fillOval(legendX, legendY, 10, 10)
        g2d.color = JBColor.BLACK
        g2d.drawString(" WebSocket", legendX + 15, legendY + 10)
        legendY += 20

        g2d.color = JBColor.ORANGE
        g2d.fillOval(legendX, legendY, 10, 10)
        g2d.color = JBColor.BLACK
        g2d.drawString(" WebRTC", legendX + 15, legendY + 10)
        legendY += 20

        g2d.color = JBColor.MAGENTA
        g2d.fillOval(legendX, legendY, 10, 10)
        g2d.color = JBColor.BLACK
        g2d.drawString(" MCP", legendX + 15, legendY + 10)
        legendY += 20

        g2d.color = JBColor.CYAN
        g2d.fillOval(legendX, legendY, 10, 10)
        g2d.color = JBColor.BLACK
        g2d.drawString(" Agent-to-Agent", legendX + 15, legendY + 10)
        legendY += 20

        g2d.color = JBColor.RED
        g2d.fillRect(legendX, legendY, 10, 10)
        g2d.color = JBColor.BLACK
        g2d.drawString(" Process Spawn", legendX + 15, legendY + 10)
    }
}

// Data classes
data class DistributedAnalysisData(
    val sessionId: String,
    val distributedTraceId: String,
    val processInfo: ProcessInfo,
    val statistics: DistributedStats,
    val websocketEvents: List<WebSocketEvent>,
    val webrtcEvents: List<WebRTCEvent>,
    val mcpCalls: List<MCPCall>,
    val agentCommunications: List<AgentCommunication>,
    val processSpawns: List<ProcessSpawn>
)

data class ProcessInfo(
    val pid: Int,
    val parentPid: Int
)

data class DistributedStats(
    val websocketEvents: Int,
    val webrtcEvents: Int,
    val mcpCalls: Int,
    val agentCommunications: Int,
    val processSpawns: Int
)

data class WebSocketEvent(
    val module: String,
    val function: String,
    val type: String,
    val data: String,
    val timestamp: Double
)

data class WebRTCEvent(
    val module: String,
    val function: String,
    val type: String,
    val data: String,
    val timestamp: Double
)

data class MCPCall(
    val module: String,
    val function: String,
    val protocol: String,
    val data: String,
    val timestamp: Double
)

data class AgentCommunication(
    val module: String,
    val function: String,
    val type: String,
    val framework: String,
    val data: String,
    val timestamp: Double
)

data class ProcessSpawn(
    val module: String,
    val function: String,
    val type: String,
    val processId: Int,
    val distributedTraceId: String,
    val timestamp: Double
)
