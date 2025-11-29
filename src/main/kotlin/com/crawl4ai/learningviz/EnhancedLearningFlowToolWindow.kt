package com.crawl4ai.learningviz

import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.SimpleToolWindowPanel
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.table.JBTable
import com.intellij.util.ui.JBUI
import java.awt.BorderLayout
import java.awt.Dimension
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import javax.swing.*
import javax.swing.table.DefaultTableModel

/**
 * Circular buffer for trace events with bounded memory usage.
 */
private class CircularBuffer(private val maxSize: Int) {
    private val buffer = ArrayDeque<String>(maxSize)

    @Synchronized
    fun add(line: String) {
        if (buffer.size >= maxSize) {
            buffer.removeFirst()
        }
        buffer.addLast(line)
    }

    @Synchronized
    fun getRecent(n: Int = 100): List<String> {
        return buffer.takeLast(n.coerceAtMost(buffer.size))
    }

    @Synchronized
    fun clear() {
        buffer.clear()
    }

    @Synchronized
    fun lines(): List<String> = buffer.toList()
}

/**
 * Enhanced tool window with PlantUML support, dead code detection, and performance metrics.
 */
class EnhancedLearningFlowToolWindow(private val project: Project) {

    private val mainPanel = SimpleToolWindowPanel(true, true)
    private val tabbedPane = JTabbedPane()

    // Tab 1: Diagram View
    private val diagramPanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val diagramTextArea = JTextArea()
    private val diagramTypeCombo = JComboBox(arrayOf("Mermaid", "PlantUML"))
    private var mermaidPreviewPanel: MermaidPreviewPanel? = null
    private var showMermaidPreview = true // Toggle between code and preview

    // Tab 2: Performance Metrics
    private val performancePanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val performanceTable: JBTable
    private val performanceTableModel: DefaultTableModel

    // Tab 3: Dead Code Detection
    private val deadCodePanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val deadCodeTable: JBTable
    private val deadCodeTableModel: DefaultTableModel
    private val deadCodeStatsLabel = JBLabel()

    // Tab 4: Call Trace
    private val callTracePanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val callTraceTree = JTree()

    // Tab 5: Flamegraph
    private val flamegraphPanel = FlamegraphPanel(project)

    // Tab 6: SQL Query Analyzer
    private val sqlAnalyzerPanel = SqlAnalyzerPanel(project)

    // Tab 7: Live Metrics Dashboard
    private val liveMetricsPanel = LiveMetricsDashboard(project)

    // Tab 8: Distributed Architecture (WebSocket, WebRTC, MCP, A2A, Cross-Process)
    private val distributedPanel = DistributedArchitecturePanel(project)

    // Tab 9: Manim Animations (Real-time execution flow videos)
    private val manimVideoPanel = ManimVideoPanel(project)

    // Tab 10: AI Explanation (Qwen3-VL powered local LLM)
    private val aiExplanationPanel = AIExplanationPanel(project)

    // Manim Auto-Renderer (triggers rendering on new correlation IDs)
    private val manimAutoRenderer = ManimAutoRenderer(project) { videoFile ->
        // Callback when video is generated - refresh video panel
        manimVideoPanel.refresh()
        PluginLogger.info("Auto-generated Manim video: ${videoFile.name}")
    }

    // Global trace filter (applies to all tabs)
    private val traceFilter = TraceFilter.getInstance(project)

    // Statistics Panel (shown on all tabs)
    private val statsPanel = JBPanel<JBPanel<*>>(GridBagLayout())
    private var versionLabel = JBLabel("Plugin Version: ${PluginLogger.PLUGIN_VERSION}")
    private var currentSessionLabel = JBLabel("No session loaded")
    private var processInfoLabel = JBLabel("Process: Not running")
    private var totalCallsLabel = JBLabel("Total Calls: 0")
    private var totalTimeLabel = JBLabel("Total Time: 0ms")
    private var avgTimeLabel = JBLabel("Avg Time: 0ms")
    private var deadCodePercentLabel = JBLabel("Dead Code: 0%")
    private var filterStatsLabel = JBLabel("Filters: None")

    private var currentTraceDirectory: File? = null
    private val plantUMLParser = PlantUMLParser()
    private var rawPlantUMLContent: String = "" // Store raw PlantUML for conversion

    // Socket trace client for real-time tracing
    private var traceSocketClient: TraceSocketClient? = null
    private val socketTraceBuffer = CircularBuffer(10000) // Max 10,000 events
    private var traceEventCount = 0
    private val socketTraceParticipants = mutableSetOf<String>() // Track unique modules
    private val socketTraceCalls = mutableMapOf<String, Int>() // Track function call counts
    private val socketTraceAllFunctions = mutableSetOf<String>() // All instrumented functions
    private val socketDistributedEvents = mutableListOf<TraceEvent>() // Distributed-related events
    private val socketTraceFileLineMap = mutableMapOf<String, Pair<String, Int>>() // funcKey -> (file, line)

    // Real-time statistics tracking
    private val socketCallTimestamps = mutableMapOf<String, Double>() // callId -> call timestamp
    private val socketFunctionDurations = mutableMapOf<String, MutableList<Double>>() // funcKey -> list of durations
    private var socketTotalDurationMs = 0.0
    private var socketCompletedCalls = 0

    // Call trace tree tracking (for Call Trace tab)
    private data class CallTraceNode(
        val callId: String,
        val module: String,
        val function: String,
        val file: String,
        val line: Int,
        val timestamp: Double,
        var duration: Double? = null,
        val children: MutableList<CallTraceNode> = mutableListOf()
    )
    private val socketCallStacks = mutableMapOf<String, MutableList<CallTraceNode>>() // correlationId -> call stack
    private val socketCallNodes = mutableMapOf<String, CallTraceNode>() // callId -> node
    private val socketRootCalls = mutableListOf<CallTraceNode>() // Root-level calls (depth 0)

    // Function registry for dead code detection
    private val socketAllDefinedFunctions = mutableSetOf<String>() // All functions found by static analysis
    private val socketFunctionDefinitions = mutableMapOf<String, Pair<String, Int>>() // funcKey -> (file, line)

    // UI update throttling (prevent freeze from too many events) - Thread-safe with atomic operations
    private val lastUIUpdateTime = AtomicLong(0)
    private val uiUpdateIntervalMs = 2000L // Update UI every 2 seconds max (was 500ms)
    private var pendingUIUpdate = false

    // Event sampling (only process 1 out of N events for UI updates) - Thread-safe
    private val eventCounter = AtomicLong(0)
    private val eventSamplingRate = 10 // Process 1 out of every 10 events (reduced from 100 for better responsiveness)

    // Trace mode tracking (mutually exclusive)
    private enum class TraceMode { NONE, FILE_BASED, SOCKET_REALTIME }
    private var currentTraceMode = TraceMode.NONE
    private var traceModeLabel = JBLabel("Mode: Not connected")

    // UI components that need to be updated dynamically
    private lateinit var attachButton: JButton
    private lateinit var selectDirButton: JButton
    private lateinit var refreshButton: JButton
    private lateinit var autoRefreshCheckbox: JCheckBox

    // Auto-refresh timer
    private var autoRefreshTimer: javax.swing.Timer? = null
    private var autoRefreshInterval = 10000 // Default 10 seconds
    private var autoRefreshEnabled = true

    init {
        // Initialize paths and deploy resources
        PluginPaths.initializeAll(project)
        ResourceDeployer.deployAll(project)

        // Initialize performance table
        performanceTableModel = DefaultTableModel(
            arrayOf("Module", "Function", "Calls", "Total (ms)", "Avg (ms)", "Min (ms)", "Max (ms)", "Mem (MB)", "CPU (%)", "File", "Line"),
            0
        )
        performanceTable = JBTable(performanceTableModel)
        performanceTable.setDefaultEditor(Any::class.java, null) // Read-only
        performanceTable.autoCreateRowSorter = true

        // Hide File and Line columns (used for navigation)
        performanceTable.columnModel.getColumn(9).minWidth = 0
        performanceTable.columnModel.getColumn(9).maxWidth = 0
        performanceTable.columnModel.getColumn(9).width = 0
        performanceTable.columnModel.getColumn(10).minWidth = 0
        performanceTable.columnModel.getColumn(10).maxWidth = 0
        performanceTable.columnModel.getColumn(10).width = 0

        // Setup double-click to navigate
        performanceTable.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) {
                    navigateToPerformance()
                }
            }
        })

        // Initialize dead code table
        deadCodeTableModel = DefaultTableModel(
            arrayOf("Status", "Module", "Function", "File:Line", "Navigate"),
            0
        )
        deadCodeTable = JBTable(deadCodeTableModel)
        deadCodeTable.setDefaultEditor(Any::class.java, null) // Read-only
        deadCodeTable.autoCreateRowSorter = true

        // Setup double-click to navigate
        deadCodeTable.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) {
                    navigateToDeadCode()
                } else if (e.clickCount == 1) {
                    // Single-click on Navigate column (column 4) triggers navigation
                    val col = deadCodeTable.columnAtPoint(e.point)
                    if (col == 4) {
                        navigateToDeadCode()
                    }
                }
            }
        })

        createToolbar()
        createStatsPanel()
        createDiagramTab()
        createPerformanceTab()
        createDeadCodeTab()
        createCallTraceTab()
        layoutComponents()

        // Initialize control states based on current mode
        updateFileBasedControls()

        // Start auto-refresh
        startAutoRefresh()
    }

    private fun createToolbar() {
        val toolbar = JToolBar()
        toolbar.isFloatable = false

        // Auto-integrate button (highlighted - primary action)
        val autoIntegrateButton = JButton("Auto-Integrate into Repo")
        autoIntegrateButton.toolTipText = "Automatically set up tracing by selecting your Python entry point"
        autoIntegrateButton.addActionListener {
            openAutoIntegrateDialog()
        }
        autoIntegrateButton.background = java.awt.Color(76, 175, 80) // Green highlight
        autoIntegrateButton.foreground = java.awt.Color.WHITE
        toolbar.add(autoIntegrateButton)

        toolbar.addSeparator()

        // Refresh button
        refreshButton = JButton("Refresh")
        refreshButton.addActionListener {
            refreshAll()
        }
        toolbar.add(refreshButton)

        // Auto-refresh checkbox
        autoRefreshCheckbox = JCheckBox("Auto-refresh", autoRefreshEnabled)
        autoRefreshCheckbox.toolTipText = "Automatically refresh data from trace directory"
        autoRefreshCheckbox.addActionListener {
            setAutoRefreshEnabled(autoRefreshCheckbox.isSelected)
        }
        toolbar.add(autoRefreshCheckbox)

        toolbar.addSeparator()

        // Select directory button
        selectDirButton = JButton("Select Trace Directory")
        selectDirButton.addActionListener {
            selectTraceDirectory()
        }
        toolbar.add(selectDirButton)

        toolbar.addSeparator()

        // Attach/Detach button (toggles based on connection state)
        attachButton = JButton("Attach to Server")
        attachButton.toolTipText = "Connect to running Python process via socket (real-time tracing)"
        attachButton.addActionListener {
            if (currentTraceMode == TraceMode.SOCKET_REALTIME && traceSocketClient?.isConnected() == true) {
                // Currently connected, so detach
                disconnectSocketTrace()
                updateAttachButtonState(false)
            } else {
                // Not connected, so attach
                showAttachDialog()
            }
        }
        attachButton.background = java.awt.Color(33, 150, 243) // Blue highlight
        attachButton.foreground = java.awt.Color.WHITE
        toolbar.add(attachButton)

        toolbar.addSeparator()

        // Auto-trace toggle
        val autoTraceCheckbox = JCheckBox("Enable Auto-Tracing")
        autoTraceCheckbox.toolTipText = "Automatically instrument Python code (zero code changes)"
        autoTraceCheckbox.addActionListener {
            toggleAutoTracing(autoTraceCheckbox.isSelected)
        }
        toolbar.add(autoTraceCheckbox)

        toolbar.addSeparator()

        // Export button
        val exportButton = JButton("Export")
        exportButton.addActionListener {
            exportCurrentView()
        }
        toolbar.add(exportButton)

        mainPanel.toolbar = toolbar
    }

    private fun openAutoIntegrateDialog() {
        val dialog = AutoIntegrationDialog(project)
        dialog.show()
    }

    private fun createStatsPanel() {
        statsPanel.border = BorderFactory.createTitledBorder("Session Statistics & Global Filters")

        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = GridBagConstraints.RELATIVE
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = JBUI.insets(2, 5)

        // Add version label at the top (with color coding)
        versionLabel.foreground = JBColor.BLUE
        statsPanel.add(versionLabel, gbc)

        // Add mode label at the top (with color coding)
        traceModeLabel.foreground = JBColor.GRAY
        statsPanel.add(traceModeLabel, gbc)

        statsPanel.add(currentSessionLabel, gbc)
        statsPanel.add(processInfoLabel, gbc)
        statsPanel.add(totalCallsLabel, gbc)
        statsPanel.add(totalTimeLabel, gbc)
        statsPanel.add(avgTimeLabel, gbc)
        statsPanel.add(deadCodePercentLabel, gbc)

        // Add separator
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.insets = JBUI.insets(8, 5, 5, 5)
        statsPanel.add(JSeparator(), gbc)

        // Add filter stats label
        gbc.fill = GridBagConstraints.NONE
        gbc.insets = JBUI.insets(2, 5)
        filterStatsLabel.foreground = JBColor(0x008800, 0x88FF88)
        statsPanel.add(filterStatsLabel, gbc)

        // Add "Manage Filters" button
        val manageFiltersButton = JButton("Manage Filters")
        manageFiltersButton.toolTipText = "Configure global trace filtering (applies to all tabs)"
        manageFiltersButton.addActionListener {
            showFilterManagementDialog()
        }
        statsPanel.add(manageFiltersButton, gbc)

        // Register filter change listener
        traceFilter.addChangeListener {
            updateFilterStatsLabel()
            refreshAllTabs()
        }

        // Initial update
        updateFilterStatsLabel()
    }

    private fun updateFilterStatsLabel() {
        filterStatsLabel.text = "Filters: ${traceFilter.getStats()}"
    }

    private fun createDiagramTab() {
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
        topPanel.border = JBUI.Borders.empty(5)

        // Diagram type selector and action buttons
        val typePanel = JBPanel<JBPanel<*>>()
        typePanel.add(JBLabel("Diagram Type:"))
        typePanel.add(diagramTypeCombo)

        // Add action listener for diagram type changes
        diagramTypeCombo.addActionListener {
            updateDiagramDisplay()
        }

        // Toggle preview/code button
        val togglePreviewButton = JButton("Show Code")
        togglePreviewButton.toolTipText = "Toggle between live preview and code view"
        togglePreviewButton.addActionListener {
            showMermaidPreview = !showMermaidPreview
            togglePreviewButton.text = if (showMermaidPreview) "Show Code" else "Show Preview"
            updateDiagramViewMode()
        }
        typePanel.add(togglePreviewButton)

        // Preview button - opens diagram in IntelliJ's renderer
        val previewButton = JButton("Open in Editor")
        previewButton.toolTipText = "Open diagram in IntelliJ's preview window"
        previewButton.addActionListener {
            previewDiagram()
        }
        typePanel.add(previewButton)

        // Copy to clipboard button
        val copyButton = JButton("Copy to Clipboard")
        copyButton.toolTipText = "Copy diagram code to clipboard"
        copyButton.addActionListener {
            val clipboard = java.awt.Toolkit.getDefaultToolkit().systemClipboard
            clipboard.setContents(java.awt.datatransfer.StringSelection(diagramTextArea.text), null)
            com.intellij.openapi.ui.Messages.showInfoMessage(
                project,
                "Diagram code copied to clipboard!",
                "Copied"
            )
        }
        typePanel.add(copyButton)

        topPanel.add(typePanel, BorderLayout.NORTH)

        // Create split pane with code on left and preview on right
        val splitPane = javax.swing.JSplitPane(javax.swing.JSplitPane.HORIZONTAL_SPLIT)
        splitPane.resizeWeight = 0.4 // 40% for code, 60% for preview

        // Left side: Code view
        diagramTextArea.isEditable = false
        diagramTextArea.lineWrap = true
        diagramTextArea.wrapStyleWord = true
        diagramTextArea.font = java.awt.Font("Monospaced", java.awt.Font.PLAIN, 12)
        val codeScrollPane = JBScrollPane(diagramTextArea)
        codeScrollPane.minimumSize = java.awt.Dimension(200, 100)

        // Right side: Mermaid preview (JCEF browser)
        try {
            mermaidPreviewPanel = MermaidPreviewPanel(project)
            mermaidPreviewPanel!!.minimumSize = java.awt.Dimension(300, 100)
            splitPane.leftComponent = codeScrollPane
            splitPane.rightComponent = mermaidPreviewPanel
            topPanel.add(splitPane, BorderLayout.CENTER)
        } catch (e: Exception) {
            // Fallback if JCEF not available
            PluginLogger.warn("JCEF not available, using code-only view: ${e.message}")
            topPanel.add(codeScrollPane, BorderLayout.CENTER)
        }

        diagramPanel.add(topPanel, BorderLayout.CENTER)
        tabbedPane.addTab("Diagram", diagramPanel)
    }

    private fun updateDiagramViewMode() {
        // Update visibility based on toggle state
        val splitPane = diagramPanel.components
            .filterIsInstance<JBPanel<*>>()
            .firstOrNull()
            ?.components
            ?.filterIsInstance<javax.swing.JSplitPane>()
            ?.firstOrNull()

        if (splitPane != null) {
            if (showMermaidPreview) {
                // Show both code and preview
                splitPane.leftComponent?.isVisible = true
                splitPane.rightComponent?.isVisible = true
                splitPane.dividerLocation = (splitPane.width * 0.4).toInt()
            } else {
                // Show only code (expand to full width)
                splitPane.dividerLocation = splitPane.width
            }
        }
    }

    private fun createPerformanceTab() {
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
        topPanel.border = JBUI.Borders.empty(5)

        // Info label
        val infoLabel = JBLabel("Performance hotspots - sorted by total time (click column to sort)")
        infoLabel.border = JBUI.Borders.empty(5)
        topPanel.add(infoLabel, BorderLayout.NORTH)

        // Performance table
        val tableScrollPane = JBScrollPane(performanceTable)
        topPanel.add(tableScrollPane, BorderLayout.CENTER)

        // Color-code rows by performance
        performanceTable.setDefaultRenderer(Any::class.java) { table, value, isSelected, hasFocus, row, column ->
            val label = JLabel(value?.toString() ?: "")
            label.isOpaque = true

            if (isSelected) {
                label.background = table.selectionBackground
                label.foreground = table.selectionForeground
            } else {
                // Color-code by avg time (column 4)
                val avgTime = table.getValueAt(row, 4) as? Double ?: 0.0
                label.background = when {
                    avgTime > 1000.0 -> JBColor(0xFFCDD2, 0x5C1F1F) // Red - slow
                    avgTime > 100.0 -> JBColor(0xFFE082, 0x5C4A1F) // Orange - medium
                    else -> table.background
                }
                label.foreground = table.foreground
            }

            label.border = JBUI.Borders.empty(2, 5)
            label
        }

        performancePanel.add(topPanel, BorderLayout.CENTER)
        tabbedPane.addTab("Performance", performancePanel)
    }

    private fun createDeadCodeTab() {
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
        topPanel.border = JBUI.Borders.empty(5)

        // Top control panel with stats and filter button
        val controlPanel = JBPanel<JBPanel<*>>(BorderLayout())

        // Stats label
        deadCodeStatsLabel.text = "Dead Code: 0 functions (0%)"
        deadCodeStatsLabel.border = JBUI.Borders.empty(5)
        controlPanel.add(deadCodeStatsLabel, BorderLayout.WEST)

        // Filter info panel (right side)
        val filterInfoPanel = JBPanel<JBPanel<*>>()
        val filterInfoLabel = JBLabel("Dead code detection uses global filters")
        filterInfoLabel.foreground = JBColor.GRAY
        filterInfoPanel.add(filterInfoLabel)

        val manageGlobalFiltersButton = JButton("Manage Global Filters")
        manageGlobalFiltersButton.toolTipText = "Open global filter management (applies to all tabs)"
        manageGlobalFiltersButton.addActionListener {
            showFilterManagementDialog()
        }
        filterInfoPanel.add(manageGlobalFiltersButton)

        controlPanel.add(filterInfoPanel, BorderLayout.EAST)
        topPanel.add(controlPanel, BorderLayout.NORTH)

        // Dead code table
        val tableScrollPane = JBScrollPane(deadCodeTable)
        topPanel.add(tableScrollPane, BorderLayout.CENTER)

        // Info panel with instructions and quick-add button
        val infoPanel = JBPanel<JBPanel<*>>(BorderLayout())
        val instructionLabel = JBLabel("Double-click a row to navigate to source code | Right-click to add folder to global exclusions")
        infoPanel.add(instructionLabel, BorderLayout.WEST)

        val quickAddButton = JButton("Add Selected Folder to Exclusions")
        quickAddButton.addActionListener {
            val selectedRow = deadCodeTable.selectedRow
            if (selectedRow >= 0) {
                val filePath = deadCodeTable.getValueAt(selectedRow, 3) as? String ?: ""
                if (filePath.isNotEmpty()) {
                    // Extract folder from file path
                    val folder = extractFolderForExclusion(filePath)
                    if (folder != null && !traceFilter.config.excludedFolders.contains(folder)) {
                        traceFilter.addExcludedFolder(folder)
                        PluginLogger.info("[DeadCode] Quick-added folder to global exclusions: $folder from file: $filePath")
                        JOptionPane.showMessageDialog(
                            mainPanel,
                            "Added '$folder' to global exclusion list",
                            "Folder Excluded",
                            JOptionPane.INFORMATION_MESSAGE
                        )
                    } else if (folder != null) {
                        JOptionPane.showMessageDialog(
                            mainPanel,
                            "'$folder' is already in the global exclusion list",
                            "Already Excluded",
                            JOptionPane.INFORMATION_MESSAGE
                        )
                    }
                }
            }
        }
        infoPanel.add(quickAddButton, BorderLayout.EAST)

        topPanel.add(infoPanel, BorderLayout.SOUTH)

        // Add right-click context menu for dead code table
        val popupMenu = JPopupMenu()
        val addToExclusionMenuItem = JMenuItem("Add Folder to Global Exclusions")
        addToExclusionMenuItem.addActionListener {
            val selectedRow = deadCodeTable.selectedRow
            if (selectedRow >= 0) {
                val filePath = deadCodeTable.getValueAt(selectedRow, 3) as? String ?: ""
                if (filePath.isNotEmpty()) {
                    val folder = extractFolderForExclusion(filePath)
                    if (folder != null && !traceFilter.config.excludedFolders.contains(folder)) {
                        traceFilter.addExcludedFolder(folder)
                        PluginLogger.info("[DeadCode] Right-click added folder to global exclusions: $folder from file: $filePath")
                    }
                }
            }
        }
        popupMenu.add(addToExclusionMenuItem)

        deadCodeTable.componentPopupMenu = popupMenu

        // Color-code dead functions and add clickable navigate link
        deadCodeTable.setDefaultRenderer(Any::class.java) { table, value, isSelected, hasFocus, row, column ->
            val label = JLabel(value?.toString() ?: "")
            label.isOpaque = true

            // Column 4 is the "Navigate" column - show as clickable link
            if (column == 4) {
                label.text = "<html><a href='#'>Go to source</a></html>"
                label.cursor = java.awt.Cursor.getPredefinedCursor(java.awt.Cursor.HAND_CURSOR)
                label.foreground = JBColor(0x0066CC, 0x5599FF) // Blue link color
                label.background = if (isSelected) table.selectionBackground else table.background
            } else if (isSelected) {
                label.background = table.selectionBackground
                label.foreground = table.selectionForeground
            } else {
                val status = table.getValueAt(row, 0) as? String ?: ""
                if (status == "DEAD") {
                    label.background = JBColor(0xFFCDD2, 0x5C1F1F) // Red
                    label.foreground = JBColor(0x5C1F1F, 0xFFCDD2)
                } else {
                    label.background = table.background
                    label.foreground = table.foreground
                }
            }

            label.border = JBUI.Borders.empty(2, 5)
            label
        }

        deadCodePanel.add(topPanel, BorderLayout.CENTER)
        tabbedPane.addTab("Dead Code", deadCodePanel)
    }

    private fun createCallTraceTab() {
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
        topPanel.border = JBUI.Borders.empty(5)

        // Info panel at top
        val infoPanel = JBPanel<JBPanel<*>>(BorderLayout())
        val infoLabel = JBLabel("Call trace shows the full execution stack from entry point. Double-click to navigate to source.")
        infoLabel.border = JBUI.Borders.empty(5)
        infoPanel.add(infoLabel, BorderLayout.WEST)

        // Add "Expand All" and "Collapse All" buttons
        val buttonPanel = JBPanel<JBPanel<*>>()
        val expandAllBtn = JButton("Expand All")
        expandAllBtn.addActionListener {
            expandAllTreeNodes(callTraceTree)
        }
        buttonPanel.add(expandAllBtn)

        val collapseAllBtn = JButton("Collapse All")
        collapseAllBtn.addActionListener {
            collapseAllTreeNodes(callTraceTree)
        }
        buttonPanel.add(collapseAllBtn)

        val showFullStackBtn = JButton("Show Full Stack")
        showFullStackBtn.toolTipText = "Reconstruct full call stack from entry point"
        showFullStackBtn.addActionListener {
            rebuildCallTraceWithFullStack()
        }
        buttonPanel.add(showFullStackBtn)

        infoPanel.add(buttonPanel, BorderLayout.EAST)
        topPanel.add(infoPanel, BorderLayout.NORTH)

        val scrollPane = JBScrollPane(callTraceTree)
        topPanel.add(scrollPane, BorderLayout.CENTER)

        // Add double-click to navigate
        callTraceTree.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) {
                    navigateFromCallTrace()
                }
            }
        })

        callTracePanel.add(topPanel, BorderLayout.CENTER)
        tabbedPane.addTab("Call Trace", callTracePanel)

        // Add new pro-level tabs
        tabbedPane.addTab("Flamegraph", flamegraphPanel)
        tabbedPane.addTab("SQL Analyzer", sqlAnalyzerPanel)
        tabbedPane.addTab("Live Metrics", liveMetricsPanel)
        tabbedPane.addTab("Distributed", distributedPanel)
        tabbedPane.addTab("Manim Videos", manimVideoPanel)
        tabbedPane.addTab("AI Explain", aiExplanationPanel)
    }

    private fun expandAllTreeNodes(tree: JTree) {
        var row = 0
        while (row < tree.rowCount) {
            tree.expandRow(row)
            row++
        }
    }

    private fun collapseAllTreeNodes(tree: JTree) {
        var row = tree.rowCount - 1
        while (row >= 0) {
            tree.collapseRow(row)
            row--
        }
    }

    private fun navigateFromCallTrace() {
        val path = callTraceTree.selectionPath ?: return
        val node = path.lastPathComponent as? javax.swing.tree.DefaultMutableTreeNode ?: return
        val userObject = node.userObject

        // Check if this is a CallTraceNode with file info
        if (userObject is String) {
            val label = userObject as String

            // First try to extract file:line directly from the label (format: "... (file:line)")
            val fileLineMatch = """\(([^)]+):(\d+)\)\s*$""".toRegex().find(label)
            if (fileLineMatch != null) {
                val file = fileLineMatch.groupValues[1]
                val line = fileLineMatch.groupValues[2].toIntOrNull() ?: 1
                if (file != "-" && file.isNotEmpty()) {
                    navigateToFile(file, line)
                    return
                }
            }

            // Fallback: parse "module.function() - duration" format and look up file info
            val funcMatch = """^(?:#\d+\s+)?(.+)\(\)\s*-\s*.+$""".toRegex().find(label)
            if (funcMatch != null) {
                val funcKey = funcMatch.groupValues[1]
                val (file, line) = socketTraceFileLineMap[funcKey]
                    ?: socketFunctionDefinitions[funcKey]
                    ?: return

                if (file != "-") {
                    navigateToFile(file, line)
                }
            }
        }
    }

    private fun rebuildCallTraceWithFullStack() {
        // Rebuild the call trace tree with full stack information
        // This reconstructs the parent chain for each call
        SwingUtilities.invokeLater {
            val root = javax.swing.tree.DefaultMutableTreeNode("Full Call Stack (${socketRootCalls.size} entry points)")

            // Group root calls by their entry point (first function in stack)
            val entryPointGroups = mutableMapOf<String, MutableList<CallTraceNode>>()

            for (rootNode in socketRootCalls) {
                val entryKey = "${rootNode.module}.${rootNode.function}"
                entryPointGroups.getOrPut(entryKey) { mutableListOf() }.add(rootNode)
            }

            // Build tree with entry points as top-level
            for ((entryKey, calls) in entryPointGroups.entries.sortedBy { it.key }) {
                val (file, line) = socketTraceFileLineMap[entryKey]
                    ?: socketFunctionDefinitions[entryKey]
                    ?: Pair("-", 0)

                val entryNode = javax.swing.tree.DefaultMutableTreeNode(
                    "$entryKey() [Entry Point] - ${calls.size} invocations ($file:$line)"
                )

                // Add each invocation with its children
                for ((idx, call) in calls.withIndex()) {
                    val invocationNode = buildTreeNodeWithFullInfo(call, idx + 1)
                    entryNode.add(invocationNode)
                }

                root.add(entryNode)
            }

            callTraceTree.model = javax.swing.tree.DefaultTreeModel(root)

            // Expand first two levels
            if (callTraceTree.rowCount > 0) {
                callTraceTree.expandRow(0)
                if (callTraceTree.rowCount > 1) {
                    callTraceTree.expandRow(1)
                }
            }

            PluginLogger.info("[CallTrace] Rebuilt call trace with ${entryPointGroups.size} entry points")
        }
    }

    private fun buildTreeNodeWithFullInfo(callNode: CallTraceNode, invocationNum: Int? = null): javax.swing.tree.DefaultMutableTreeNode {
        val durationStr = if (callNode.duration != null) {
            String.format("%.2fms", callNode.duration)
        } else {
            "running..."
        }

        val (file, line) = socketTraceFileLineMap["${callNode.module}.${callNode.function}"]
            ?: socketFunctionDefinitions["${callNode.module}.${callNode.function}"]
            ?: Pair(callNode.file, callNode.line)

        val invocationPrefix = if (invocationNum != null) "#$invocationNum " else ""
        val label = "$invocationPrefix${callNode.module}.${callNode.function}() - $durationStr ($file:$line)"
        val treeNode = javax.swing.tree.DefaultMutableTreeNode(label)

        // Recursively add children
        for (child in callNode.children) {
            treeNode.add(buildTreeNodeWithFullInfo(child))
        }

        return treeNode
    }

    private fun layoutComponents() {
        val mainContent = JBPanel<JBPanel<*>>(BorderLayout())

        // Stats on top
        mainContent.add(statsPanel, BorderLayout.NORTH)

        // Tabbed pane in center
        mainContent.add(tabbedPane, BorderLayout.CENTER)

        mainPanel.setContent(mainContent)
    }

    /**
     * Extract meaningful folder name from file path for exclusion.
     * Priority: First-level subdirectory of project, or parent folder name.
     */
    private fun extractFolderForExclusion(filePath: String): String? {
        try {
            val projectBasePath = project.basePath ?: return null
            val normalizedFilePath = filePath.replace("\\", "/")
            val normalizedBasePath = projectBasePath.replace("\\", "/")

            // If file is in project directory, extract first-level subdirectory
            if (normalizedFilePath.startsWith(normalizedBasePath)) {
                val relativePath = normalizedFilePath.substring(normalizedBasePath.length).trimStart('/')
                val firstFolder = relativePath.split("/").firstOrNull()
                if (firstFolder != null && firstFolder.isNotEmpty() && !firstFolder.contains(".")) {
                    return firstFolder
                }
            }

            // Fallback: Extract parent directory name
            val pathParts = normalizedFilePath.split("/")
            if (pathParts.size >= 2) {
                return pathParts[pathParts.size - 2]
            }

            return null
        } catch (e: Exception) {
            PluginLogger.warn("Failed to extract folder from path: $filePath - ${e.message}")
            return null
        }
    }

    private fun selectTraceDirectory() {
        val fileChooser = JFileChooser()
        fileChooser.fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
        fileChooser.dialogTitle = "Select Trace Directory"

        // Start from current trace directory if set
        if (currentTraceDirectory != null && currentTraceDirectory!!.exists()) {
            fileChooser.currentDirectory = currentTraceDirectory
        }

        val result = fileChooser.showOpenDialog(mainPanel)
        if (result == JFileChooser.APPROVE_OPTION) {
            // Disconnect from socket mode if active
            if (currentTraceMode == TraceMode.SOCKET_REALTIME) {
                disconnectSocketTrace()
            }

            currentTraceDirectory = fileChooser.selectedFile
            currentTraceMode = TraceMode.FILE_BASED
            updateTraceModeLabel()
            updateFileBasedControls()

            refreshAll()

            // Start watching directory for changes
            val watcherService = project.getService(TraceWatcherService::class.java)
            watcherService.watchDirectory(currentTraceDirectory!!)

            // Restart auto-refresh with new directory
            startAutoRefresh()
        }
    }

    private fun showAttachDialog() {
        // Create dialog panel
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = java.awt.Insets(5, 5, 5, 5)

        // Host field
        panel.add(JLabel("Host:"), gbc)
        gbc.gridx = 1
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0
        val hostField = JTextField("127.0.0.1", 20)
        panel.add(hostField, gbc)

        // Port field
        gbc.gridx = 0
        gbc.gridy = 1
        gbc.weightx = 0.0
        panel.add(JLabel("Port:"), gbc)
        gbc.gridx = 1
        gbc.weightx = 1.0
        val portField = JTextField("5678", 20)
        panel.add(portField, gbc)

        // Info label
        gbc.gridx = 0
        gbc.gridy = 2
        gbc.gridwidth = 2
        val infoLabel = JLabel("<html><i>Connect to Python process with PYCHARM_PLUGIN_SOCKET_TRACE=1</i></html>")
        panel.add(infoLabel, gbc)

        // Show dialog
        val result = javax.swing.JOptionPane.showConfirmDialog(
            null,
            panel,
            "Attach to Trace Server",
            javax.swing.JOptionPane.OK_CANCEL_OPTION,
            javax.swing.JOptionPane.PLAIN_MESSAGE
        )

        if (result == javax.swing.JOptionPane.OK_OPTION) {
            val host = hostField.text.trim()
            val port = portField.text.trim().toIntOrNull() ?: 5678
            connectToTraceServer(host, port)
        }
    }

    private fun connectToTraceServer(host: String, port: Int) {
        // Disconnect from file-based mode if active
        if (currentTraceMode == TraceMode.FILE_BASED) {
            stopAutoRefresh()
            currentTraceDirectory = null
        }

        // Disconnect existing socket connection
        traceSocketClient?.disconnect()

        // Reset trace buffer and data
        socketTraceBuffer.clear()
        traceEventCount = 0
        socketTraceParticipants.clear()
        socketTraceCalls.clear()
        socketTraceAllFunctions.clear()
        socketDistributedEvents.clear()
        socketTraceFileLineMap.clear()
        socketCallTimestamps.clear()
        socketFunctionDurations.clear()
        socketTotalDurationMs = 0.0
        socketCompletedCalls = 0

        // Switch to socket mode
        currentTraceMode = TraceMode.SOCKET_REALTIME
        updateTraceModeLabel()
        updateFileBasedControls()

        // Create new client
        traceSocketClient = TraceSocketClient(
            host = host,
            port = port,
            onTraceReceived = { traceEvent ->
                // Handle trace event on Swing thread
                javax.swing.SwingUtilities.invokeLater {
                    handleTraceEvent(traceEvent)
                }
            },
            onConnected = {
                javax.swing.SwingUtilities.invokeLater {
                    currentSessionLabel.text = "Connected to $host:$port"
                    updateTraceModeLabel()
                    updateAttachButtonState(true) // Change to "Detach"
                    processInfoLabel.text = "Receiving real-time traces..."
                    PluginLogger.info("[ToolWindow] Successfully connected to trace server at $host:$port")
                }
            },
            onDisconnected = { error ->
                javax.swing.SwingUtilities.invokeLater {
                    val message = if (error != null) {
                        PluginLogger.warn("[ToolWindow] Disconnected from trace server: $error")
                        "Disconnected from trace server: $error"
                    } else {
                        PluginLogger.info("[ToolWindow] Disconnected from trace server (graceful)")
                        "Disconnected from trace server"
                    }
                    currentSessionLabel.text = message
                    processInfoLabel.text = "Not connected"
                    updateAttachButtonState(false) // Change back to "Attach"
                }
            },
            onError = { exception ->
                javax.swing.SwingUtilities.invokeLater {
                    PluginLogger.error("[ToolWindow] Connection error: ${exception.message}", exception)
                    com.intellij.openapi.ui.Messages.showErrorDialog(
                        project,
                        "Failed to connect to $host:$port\n${exception.message}",
                        "Connection Error"
                    )
                }
            }
        )

        // Connect
        traceSocketClient?.connect()
    }

    private fun handleTraceEvent(event: TraceEvent) {
        traceEventCount++

        // ALWAYS log for debugging (until we confirm it works)
        if (traceEventCount <= 10) {
            PluginLogger.info("[ToolWindow] Processing event #$traceEventCount: ${event.type} ${event.module}.${event.function}() [${event.callId}]")
        }
        if (traceEventCount == 11) {
            PluginLogger.info("[ToolWindow] Processed 10 events successfully, event sampling will now reduce UI updates")
        }
        if (traceEventCount % 100 == 0) {
            PluginLogger.info("[ToolWindow] Processed $traceEventCount total events")
        }

        // Handle special event types BEFORE filtering (metadata events should never be filtered)
        when (event.type) {
            "function_registry" -> {
                // Receive function registry for dead code detection
                handleFunctionRegistry(event)
                return // Don't process further, this is a special event
            }
            "cycle_complete" -> {
                // Pass to Manim for video generation (filtering happens inside ManimAutoRenderer)
                manimAutoRenderer.onTraceEvent(event)
                return // Don't process further, this is a meta-event
            }
        }

        // Apply global filter for regular call/return events
        if (traceFilter.shouldExclude(event.file) || traceFilter.shouldExcludeModule(event.module)) {
            return // Skip filtered events
        }

        // Auto-render Manim animation when new correlation ID detected
        manimAutoRenderer.onTraceEvent(event)

        // Track participants and calls
        val participantId = event.getParticipantId()
        socketTraceParticipants.add(participantId)

        val functionKey = "${event.module}.${event.function}"
        socketTraceAllFunctions.add(functionKey)
        socketTraceCalls[functionKey] = (socketTraceCalls[functionKey] ?: 0) + 1
        socketTraceFileLineMap[functionKey] = Pair(event.file, event.line)

        // Track call/return pairs for timing statistics
        when (event.type) {
            "call" -> {
                // Record call timestamp
                socketCallTimestamps[event.callId] = event.timestamp
            }
            "return" -> {
                // Calculate duration if we have the matching call
                val callTimestamp = socketCallTimestamps.remove(event.callId)
                if (callTimestamp != null) {
                    val durationMs = (event.timestamp - callTimestamp) * 1000.0
                    socketTotalDurationMs += durationMs
                    socketCompletedCalls++

                    // Track per-function durations
                    socketFunctionDurations.getOrPut(functionKey) { mutableListOf() }.add(durationMs)

                    // Log timing for first few completed calls
                    if (socketCompletedCalls <= 5) {
                        PluginLogger.debug("[ToolWindow] Completed call #$socketCompletedCalls: $functionKey took ${String.format("%.2f", durationMs)}ms")
                    }
                }
            }
        }

        // Update real-time statistics
        totalCallsLabel.text = "Total Calls: $traceEventCount"
        currentSessionLabel.text = "Session: ${event.sessionId}"
        processInfoLabel.text = "Process: ${event.processId}"

        // Calculate and update timing statistics
        if (socketCompletedCalls > 0) {
            totalTimeLabel.text = "Total Time: ${String.format("%.1f", socketTotalDurationMs)}ms"
            val avgDurationMs = socketTotalDurationMs / socketCompletedCalls
            avgTimeLabel.text = "Avg Time: ${String.format("%.2f", avgDurationMs)}ms"
        } else {
            totalTimeLabel.text = "Total Time: 0.0ms"
            avgTimeLabel.text = "Avg Time: 0.00ms"
        }

        // Calculate dead code percentage (functions called vs all instrumented functions)
        if (socketTraceAllFunctions.isNotEmpty()) {
            val calledCount = socketTraceCalls.size
            val totalCount = socketTraceAllFunctions.size
            val deadCodePercent = ((totalCount - calledCount).toDouble() / totalCount) * 100.0
            deadCodePercentLabel.text = "Dead Code: ${String.format("%.1f", deadCodePercent)}%"
        } else {
            deadCodePercentLabel.text = "Dead Code: 0.0%"
        }

        // Add to PlantUML buffer (always track data) - circular buffer prevents memory leak
        socketTraceBuffer.add(event.toPlantUML())

        // Event sampling: Only process 1 out of every N events for UI updates (thread-safe)
        val count = eventCounter.incrementAndGet()
        if (count % eventSamplingRate != 0L) {
            return  // Skip UI update for this event
        }

        // Throttle UI updates to prevent freeze (update at most every 2 seconds) - Thread-safe
        val currentTime = System.currentTimeMillis()
        val lastUpdate = lastUIUpdateTime.get()

        if (currentTime - lastUpdate >= uiUpdateIntervalMs) {
            // Try to atomically update the timestamp
            if (lastUIUpdateTime.compareAndSet(lastUpdate, currentTime)) {
                pendingUIUpdate = false
                updateUIFromTraceData(event)
            }
        } else if (!pendingUIUpdate) {
            // Schedule a delayed update
            pendingUIUpdate = true
            javax.swing.Timer(uiUpdateIntervalMs.toInt()) {
                if (pendingUIUpdate) {
                    pendingUIUpdate = false
                    lastUIUpdateTime.set(System.currentTimeMillis())
                    updateUIFromTraceData(event)
                }
            }.apply {
                isRepeats = false
                start()
            }
        }
    }

    /**
     * Escape special characters for PlantUML to prevent injection.
     */
    private fun escapePlantUML(text: String): String {
        return text
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace("<", "\\<")
            .replace(">", "\\>")
    }

    private fun updateUIFromTraceData(event: TraceEvent) {
        // Update diagram view with recent traces (last 100 lines from circular buffer)
        val recentLines = socketTraceBuffer.getRecent(100)

        // Collect dead functions (defined but never called)
        val deadFunctions = socketAllDefinedFunctions.filter { it !in socketTraceCalls }
        val deadParticipants = mutableSetOf<String>()
        deadFunctions.forEach { funcKey ->
            val parts = funcKey.split(".")
            val module = parts.dropLast(1).lastOrNull() ?: "__main__"
            deadParticipants.add(module)
        }

        // Build PlantUML diagram with proper participant declarations and dead code coloring
        val plantUMLDiagram = buildString {
            appendLine("@startuml")
            appendLine("' Real-time trace from ${escapePlantUML(event.sessionId)}")
            appendLine("' Process ID: ${event.processId}")
            appendLine()

            // Styling for live vs dead code
            appendLine("skinparam sequence {")
            appendLine("    ArrowColor #00AA00")
            appendLine("    LifeLineBorderColor #00AA00")
            appendLine("}")
            appendLine()

            // Add participant declarations - LIVE participants (green background)
            socketTraceParticipants.forEach { participant ->
                val safe = escapePlantUML(participant)
                appendLine("participant \"$safe\" as $safe #90EE90")
            }

            // Add DEAD-only participants (red background) - modules with only dead code
            deadParticipants.filter { it !in socketTraceParticipants }.forEach { participant ->
                val safe = escapePlantUML(participant)
                appendLine("participant \"$safe\" as $safe #FFCCCC")
            }
            appendLine()

            // Add trace calls (LIVE calls in green)
            appendLine("' === LIVE CALLS (Green) ===")
            recentLines.forEach { line ->
                if (line.isNotBlank()) {
                    // Modify arrow color to green
                    val greenLine = line.replace("->", "-[#00AA00]>")
                    appendLine(greenLine)
                }
            }

            // Add dead code section (red arrows, different styling)
            if (deadFunctions.isNotEmpty()) {
                appendLine()
                appendLine("' === DEAD CODE (Red - Never Called) ===")
                appendLine("note over ${socketTraceParticipants.firstOrNull() ?: deadParticipants.firstOrNull() ?: "Unknown"}: Dead Code Section")

                // Show up to 30 dead functions
                deadFunctions.take(30).forEach { funcKey ->
                    val parts = funcKey.split(".")
                    val module = parts.dropLast(1).lastOrNull() ?: "__main__"
                    val function = parts.lastOrNull() ?: funcKey
                    val safeModule = escapePlantUML(module)
                    val safeFunc = escapePlantUML(function)
                    appendLine("$safeModule -[#CC0000]> $safeModule: <color:#CC0000>$safeFunc()</color> [DEAD]")
                }

                if (deadFunctions.size > 30) {
                    appendLine("note over ${socketTraceParticipants.firstOrNull() ?: deadParticipants.firstOrNull() ?: "Unknown"}: ... and ${deadFunctions.size - 30} more dead functions")
                }
            }

            appendLine("@enduml")
        }

        // Store and display
        rawPlantUMLContent = plantUMLDiagram
        updateDiagramDisplay()

        // Update performance table with latest event
        updatePerformanceFromSocketTrace(event)

        // Update dead code tracking
        updateDeadCodeFromSocketTrace()

        // Update distributed architecture tracking
        updateDistributedFromSocketTrace(event)

        // Update Call Trace tree (TODO: full implementation)
        updateCallTraceFromSocketTrace(event)

        // Update Live Metrics dashboard
        updateLiveMetricsFromSocketTrace()

        // Update Flamegraph visualization
        updateFlamegraphFromSocketTrace()

        // Update AI Explanation panel with trace data
        updateAIExplanationPanel()
    }

    private fun updateAIExplanationPanel() {
        // Build trace data JSON for AI explanation
        val traceJson = com.google.gson.JsonObject()

        // Add function calls
        val callsArray = com.google.gson.JsonArray()
        socketTraceCalls.entries.take(50).forEach { (funcKey, count) ->
            val parts = funcKey.split(".")
            val module = parts.dropLast(1).joinToString(".")
            val function = parts.lastOrNull() ?: funcKey
            val (file, line) = socketTraceFileLineMap[funcKey] ?: Pair("-", 0)

            val callObj = com.google.gson.JsonObject()
            callObj.addProperty("function", function)
            callObj.addProperty("module", module)
            callObj.addProperty("file", file)
            callObj.addProperty("line", line)
            callObj.addProperty("count", count)
            callsArray.add(callObj)
        }
        traceJson.add("calls", callsArray)

        // Add modules
        val modulesArray = com.google.gson.JsonArray()
        socketTraceParticipants.forEach { modulesArray.add(it) }
        traceJson.add("modules", modulesArray)

        // Add dead functions
        val deadFunctions = socketAllDefinedFunctions.filter { it !in socketTraceCalls }
        val deadArray = com.google.gson.JsonArray()
        deadFunctions.take(20).forEach { deadArray.add(it) }
        traceJson.add("dead_functions", deadArray)

        // Add called functions
        val calledArray = com.google.gson.JsonArray()
        socketTraceCalls.keys.forEach { calledArray.add(it) }
        traceJson.add("called_functions", calledArray)

        // Pass to AI panel - use the new separate setters
        aiExplanationPanel.setDeadCodeData(traceJson)
        aiExplanationPanel.setCallTraceData(traceJson)
    }

    private fun updatePerformanceFromSocketTrace(event: TraceEvent) {
        // Update performance table with call counts and timing statistics
        performanceTableModel.rowCount = 0 // Clear table

        // Sort by call count descending
        val sortedCalls = socketTraceCalls.entries.sortedByDescending { it.value }

        for ((funcKey, count) in sortedCalls) {
            val parts = funcKey.split(".")
            val module = parts.dropLast(1).joinToString(".")
            val function = parts.lastOrNull() ?: funcKey
            val (file, line) = socketTraceFileLineMap[funcKey] ?: Pair("-", 0)

            // Apply global filter at display time (in case filters changed after collection)
            if (traceFilter.shouldExclude(file) || traceFilter.shouldExcludeModule(module)) {
                continue // Skip this function
            }

            // Get timing statistics for this function
            val durations = socketFunctionDurations[funcKey]
            val totalTime = if (durations != null && durations.isNotEmpty()) {
                String.format("%.1f", durations.sum())
            } else {
                "-"
            }
            val avgTime = if (durations != null && durations.isNotEmpty()) {
                String.format("%.2f", durations.average())
            } else {
                "-"
            }
            val minTime = if (durations != null && durations.isNotEmpty()) {
                String.format("%.2f", durations.minOrNull() ?: 0.0)
            } else {
                "-"
            }
            val maxTime = if (durations != null && durations.isNotEmpty()) {
                String.format("%.2f", durations.maxOrNull() ?: 0.0)
            } else {
                "-"
            }

            performanceTableModel.addRow(arrayOf(
                module.ifEmpty { "__main__" },
                function,
                count,
                totalTime, // Total time (real-time calculation)
                avgTime,   // Avg time
                minTime,   // Min time
                maxTime,   // Max time
                "-",       // Memory (not available yet)
                "-",       // CPU (not available yet)
                file,      // File path (hidden column for navigation)
                line       // Line number (hidden column for navigation)
            ))
        }
    }

    private fun handleFunctionRegistry(event: TraceEvent) {
        // Parse function registry from trace data
        try {
            val traceData = event.traceData ?: return
            val functions = traceData.getAsJsonArray("functions") ?: return

            socketAllDefinedFunctions.clear()
            socketFunctionDefinitions.clear()

            for (funcElement in functions) {
                val funcObj = funcElement.asJsonObject
                val module = funcObj.get("module").asString
                val function = funcObj.get("function").asString
                val file = funcObj.get("file").asString
                val line = funcObj.get("line").asInt

                val funcKey = "$module.$function"
                socketAllDefinedFunctions.add(funcKey)
                socketFunctionDefinitions[funcKey] = Pair(file, line)
            }

            PluginLogger.info("[ToolWindow] Received function registry: ${socketAllDefinedFunctions.size} functions")

            // Update Dead Code tab immediately
            SwingUtilities.invokeLater {
                updateDeadCodeFromSocketTrace()
            }

        } catch (e: Exception) {
            PluginLogger.error("[ToolWindow] Failed to parse function registry: ${e.message}", e)
        }
    }

    private fun updateDeadCodeFromSocketTrace() {
        // Proper dead code detection using function registry
        // Both static analysis and runtime traces now use relative module paths (e.g., src.crawl4ai.foo.bar)
        // so direct comparison works

        val totalDefined = socketAllDefinedFunctions.size
        val calledCount = socketTraceCalls.size
        val deadCount = if (totalDefined > 0) totalDefined - calledCount else 0

        if (totalDefined > 0) {
            val deadCodePercent = (deadCount.toDouble() / totalDefined) * 100.0
            deadCodeStatsLabel.text = "Functions: $totalDefined total, $calledCount called, $deadCount dead (${String.format("%.1f", deadCodePercent)}%)"
        } else {
            deadCodeStatsLabel.text = "Real-time mode: ${socketTraceCalls.size} functions called (waiting for function registry...)"
        }

        // Clear table
        deadCodeTableModel.rowCount = 0

        // Helper function to check if file should be excluded (uses global filter)
        fun isFileExcluded(filePath: String): Boolean {
            return traceFilter.shouldExclude(filePath)
        }

        // Show DEAD functions first (sorted by module/function, filtered by exclusions)
        val deadFunctions = socketAllDefinedFunctions.filter { it !in socketTraceCalls }.sorted()
        for (funcKey in deadFunctions) {
            val parts = funcKey.split(".")
            val module = parts.dropLast(1).joinToString(".")
            val function = parts.lastOrNull() ?: funcKey
            val (file, line) = socketFunctionDefinitions[funcKey] ?: Pair("-", 0)

            // FILTER: Skip if file matches excluded folders
            if (isFileExcluded(file)) {
                continue
            }

            // Store file and line separately in UserData for navigation, show combined in column
            val fileLineDisplay = if (file != "-") "$file:$line" else "-"
            deadCodeTableModel.addRow(arrayOf(
                "DEAD",
                module.ifEmpty { "__main__" },
                function,
                fileLineDisplay,
                "navigate" // Placeholder - renderer shows "Go to source" link
            ))
        }

        // Then show ALIVE functions (sorted by call count descending, filtered by exclusions)
        for ((funcKey, count) in socketTraceCalls.entries.sortedByDescending { it.value }) {
            val parts = funcKey.split(".")
            val module = parts.dropLast(1).joinToString(".")
            val function = parts.lastOrNull() ?: funcKey
            val (file, line) = socketFunctionDefinitions[funcKey]
                ?: socketTraceFileLineMap[funcKey]
                ?: Pair("-", 0)

            // FILTER: Skip if file matches excluded folders
            if (isFileExcluded(file)) {
                continue
            }

            val fileLineDisplay = if (file != "-") "$file:$line" else "-"
            deadCodeTableModel.addRow(arrayOf(
                "ALIVE ($count calls)",
                module.ifEmpty { "__main__" },
                function,
                fileLineDisplay,
                "navigate" // Placeholder - renderer shows "Go to source" link
            ))
        }
    }

    private fun updateDistributedFromSocketTrace(event: TraceEvent) {
        // Detect distributed patterns from module/function names and file paths
        val module = event.module.lowercase()
        val function = event.function.lowercase()
        val file = event.file.lowercase()

        // Check if this is a distributed event
        val isWebSocket = module.contains("websocket") || module.contains("socket") ||
                          function.contains("ws_") || function.contains("websocket") ||
                          module.contains("autobahn") || module.contains("wamp")

        val isWebRTC = module.contains("webrtc") || module.contains("rtc") ||
                       function.contains("peer") || function.contains("datachannel")

        val isMCP = module.contains("mcp") || function.contains("mcp") ||
                    file.contains("mcp") || module.contains("anthropic")

        val isAgent = module.contains("agent") || module.contains("autogen") ||
                      module.contains("crewai") || module.contains("langchain") ||
                      function.contains("agent_")

        val isProcess = function.contains("spawn") || function.contains("fork") ||
                        function.contains("subprocess") || function.contains("multiprocessing")

        // If it's a distributed event, track it
        if (isWebSocket || isWebRTC || isMCP || isAgent || isProcess) {
            socketDistributedEvents.add(event)

            // Update the distributed panel
            distributedPanel.updateFromSocketTrace(
                event = event,
                isWebSocket = isWebSocket,
                isWebRTC = isWebRTC,
                isMCP = isMCP,
                isAgent = isAgent,
                isProcess = isProcess
            )
        }
    }

    private fun updateCallTraceFromSocketTrace(event: TraceEvent) {
        // Build call trace tree from socket events
        val stackKey = event.correlationId ?: event.sessionId

        when (event.type) {
            "call" -> {
                // Create new node for this call
                val node = CallTraceNode(
                    callId = event.callId,
                    module = event.module,
                    function = event.function,
                    file = event.file,
                    line = event.line,
                    timestamp = event.timestamp
                )

                // Store node for later retrieval on return
                socketCallNodes[event.callId] = node

                // Get or create call stack for this correlation ID
                val stack = socketCallStacks.getOrPut(stackKey) { mutableListOf() }

                if (stack.isEmpty()) {
                    // Root-level call (depth 0)
                    socketRootCalls.add(node)
                } else {
                    // Child call - add to parent's children
                    val parent = stack.last()
                    parent.children.add(node)
                }

                // Push to stack
                stack.add(node)
            }

            "return" -> {
                // Pop from stack and update duration
                val stack = socketCallStacks[stackKey]
                if (stack != null && stack.isNotEmpty()) {
                    val node = stack.removeAt(stack.size - 1)
                    val callTimestamp = socketCallTimestamps[event.callId]
                    if (callTimestamp != null) {
                        node.duration = (event.timestamp - callTimestamp) * 1000.0 // Convert to ms
                    }
                }

                // Clean up completed stacks (avoid memory leak)
                if (stack?.isEmpty() == true) {
                    socketCallStacks.remove(stackKey)
                }
            }
        }

        // Rebuild tree model (limit to last 100 root calls to avoid overwhelming)
        SwingUtilities.invokeLater {
            val root = javax.swing.tree.DefaultMutableTreeNode("Call Trace (${socketRootCalls.size} root calls)")

            // Show last 100 root calls
            val recentRoots = if (socketRootCalls.size > 100) {
                socketRootCalls.takeLast(100)
            } else {
                socketRootCalls
            }

            for (rootNode in recentRoots) {
                val treeNode = buildTreeNode(rootNode)
                root.add(treeNode)
            }

            callTraceTree.model = javax.swing.tree.DefaultTreeModel(root)

            // Auto-expand first level
            if (callTraceTree.rowCount > 0) {
                callTraceTree.expandRow(0)
            }
        }
    }

    private fun buildTreeNode(callNode: CallTraceNode): javax.swing.tree.DefaultMutableTreeNode {
        val durationStr = if (callNode.duration != null) {
            String.format("%.2fms", callNode.duration)
        } else {
            "running..."
        }

        // Include file:line info for navigation
        val funcKey = "${callNode.module}.${callNode.function}"
        val (file, line) = socketTraceFileLineMap[funcKey]
            ?: socketFunctionDefinitions[funcKey]
            ?: Pair(callNode.file, callNode.line)

        val fileInfo = if (file != "-" && file.isNotEmpty()) " ($file:$line)" else ""
        val label = "$funcKey() - $durationStr$fileInfo"
        val treeNode = javax.swing.tree.DefaultMutableTreeNode(label)

        // Recursively add children
        for (child in callNode.children) {
            treeNode.add(buildTreeNode(child))
        }

        return treeNode
    }

    private fun updateLiveMetricsFromSocketTrace() {
        // Calculate top slowest functions (top 10)
        val topSlowest = socketFunctionDurations.entries
            .filter { it.value.isNotEmpty() }
            .sortedByDescending { it.value.average() }
            .take(10)
            .map { (funcKey, durations) ->
                val (file, line) = socketTraceFileLineMap[funcKey] ?: Pair("-", 0)
                funcKey to Pair(durations.average(), Pair(file, line))
            }

        // Track recent errors (TODO: needs error detection in trace events)
        val recentErrors = listOf<Triple<String, String, Double>>()

        // Calculate average latency
        val avgLatencyMs = if (socketCompletedCalls > 0) {
            socketTotalDurationMs / socketCompletedCalls
        } else {
            0.0
        }

        // Update Live Metrics panel
        liveMetricsPanel.updateFromSocketTrace(
            totalCalls = traceEventCount,
            avgLatencyMs = avgLatencyMs,
            sessionId = if (socketDistributedEvents.isNotEmpty()) {
                socketDistributedEvents.last().sessionId
            } else {
                "unknown"
            },
            topSlowestFunctions = topSlowest,
            recentErrors = recentErrors
        )
    }

    private fun updateFlamegraphFromSocketTrace() {
        // Build flamegraph frames from socket trace data
        val frames = mutableListOf<FlamegraphFrame>()

        // Convert socket trace calls to flamegraph frames
        for ((funcKey, durations) in socketFunctionDurations.entries) {
            if (durations.isEmpty()) continue

            val (file, line) = socketTraceFileLineMap[funcKey] ?: Pair("-", 0)
            val totalDuration = durations.sum()

            frames.add(FlamegraphFrame(
                name = funcKey,
                value = totalDuration,
                file = file,
                line = line,
                parentId = null, // TODO: Track parent-child relationships from call stack
                callId = funcKey, // Use funcKey as callId for now
                depth = 0, // TODO: Track actual depth from call stack
                framework = detectFramework(funcKey),
                isAiAgent = funcKey.contains("agent") || funcKey.contains("embodied")
            ))
        }

        // Calculate statistics
        val totalDurationMs = frames.sumOf { it.value }
        val maxDepth = frames.maxOfOrNull { it.depth } ?: 0
        val totalCalls = socketTraceCalls.values.sum()

        // Update Flamegraph panel
        flamegraphPanel.updateFromSocketTrace(
            sessionId = if (socketDistributedEvents.isNotEmpty()) {
                socketDistributedEvents.last().sessionId
            } else {
                "unknown"
            },
            frames = frames,
            totalDurationMs = totalDurationMs,
            maxDepth = maxDepth,
            totalCalls = totalCalls
        )
    }

    private fun detectFramework(funcKey: String): String? {
        return when {
            funcKey.contains("torch") || funcKey.contains("pytorch") -> "PyTorch"
            funcKey.contains("tensorflow") || funcKey.contains("tf.") -> "TensorFlow"
            funcKey.contains("qwen") -> "Qwen"
            funcKey.contains("transformers") -> "Transformers"
            funcKey.contains("autobahn") || funcKey.contains("wamp") -> "WAMP"
            funcKey.contains("fastapi") || funcKey.contains("starlette") -> "FastAPI"
            else -> null
        }
    }

    private fun refreshAll() {
        val dir = currentTraceDirectory ?: return

        // Find latest session files
        val pumlFiles = dir.listFiles { _, name -> name.endsWith(".puml") }?.sortedByDescending { it.lastModified() }
        val deadCodeFiles = dir.listFiles { _, name -> name.contains("dead_code") && name.endsWith(".json") }?.sortedByDescending { it.lastModified() }
        val perfFiles = dir.listFiles { _, name -> name.contains("performance") && name.endsWith(".json") }?.sortedByDescending { it.lastModified() }
        val flamegraphFiles = dir.listFiles { _, name -> name.contains("flamegraph") && name.endsWith(".json") }?.sortedByDescending { it.lastModified() }
        val sqlFiles = dir.listFiles { _, name -> name.contains("sql_analysis") && name.endsWith(".json") }?.sortedByDescending { it.lastModified() }
        val metricsFiles = dir.listFiles { _, name -> name.contains("live_metrics") && name.endsWith(".json") }?.sortedByDescending { it.lastModified() }
        val distributedFiles = dir.listFiles { _, name -> name.contains("distributed_analysis") && name.endsWith(".json") }?.sortedByDescending { it.lastModified() }

        // Load PlantUML diagram
        pumlFiles?.firstOrNull()?.let { loadPlantUMLDiagram(it) }

        // Load dead code report
        deadCodeFiles?.firstOrNull()?.let { loadDeadCodeReport(it) }

        // Load performance report
        perfFiles?.firstOrNull()?.let { loadPerformanceReport(it) }

        // Load new pro-level features
        flamegraphFiles?.firstOrNull()?.let { flamegraphPanel.loadFlamegraph(it) }
        sqlFiles?.firstOrNull()?.let { sqlAnalyzerPanel.loadSqlAnalysis(it) }
        metricsFiles?.firstOrNull()?.let { liveMetricsPanel.loadMetrics(it) }
        distributedFiles?.firstOrNull()?.let { distributedPanel.loadDistributedAnalysis(it) }
    }

    private fun startAutoRefresh() {
        stopAutoRefresh() // Stop existing timer if any

        if (autoRefreshEnabled && currentTraceDirectory != null) {
            autoRefreshTimer = javax.swing.Timer(autoRefreshInterval) {
                SwingUtilities.invokeLater {
                    refreshAll()
                }
            }
            autoRefreshTimer?.start()
        }
    }

    private fun stopAutoRefresh() {
        autoRefreshTimer?.stop()
        autoRefreshTimer = null
    }

    fun setAutoRefreshInterval(intervalMs: Int) {
        autoRefreshInterval = intervalMs
        if (autoRefreshEnabled) {
            startAutoRefresh() // Restart with new interval
        }
    }

    fun setAutoRefreshEnabled(enabled: Boolean) {
        autoRefreshEnabled = enabled
        if (enabled) {
            startAutoRefresh()
        } else {
            stopAutoRefresh()
        }
    }

    private fun loadPlantUMLDiagram(file: File) {
        val diagram = plantUMLParser.parsePlantUML(file) ?: return

        currentSessionLabel.text = "Session: ${diagram.sessionId}"
        totalCallsLabel.text = "Total Calls: ${diagram.statistics.totalCalls}"
        totalTimeLabel.text = "Total Time: ${String.format("%.1f", diagram.statistics.totalDurationMs)}ms"
        avgTimeLabel.text = "Avg Time: ${String.format("%.2f", diagram.statistics.avgDurationMs)}ms"
        deadCodePercentLabel.text = "Dead Code: ${String.format("%.1f", diagram.statistics.deadCodePercentage)}%"

        // Store raw PlantUML content for conversion
        rawPlantUMLContent = diagram.content

        // Update display based on current selection
        updateDiagramDisplay()
    }

    private fun updateDiagramDisplay() {
        if (rawPlantUMLContent.isEmpty()) {
            return
        }

        when (diagramTypeCombo.selectedItem) {
            "PlantUML" -> {
                diagramTextArea.text = rawPlantUMLContent
                // PlantUML preview not supported in JCEF, show message
                mermaidPreviewPanel?.updateDiagram("sequenceDiagram\n    Note over User: PlantUML preview not available.\n    Note over User: Switch to Mermaid for live preview.")
            }
            "Mermaid" -> {
                val mermaidCode = convertPlantUMLToMermaid(rawPlantUMLContent)
                diagramTextArea.text = mermaidCode
                // Update live Mermaid preview
                mermaidPreviewPanel?.updateDiagram(mermaidCode)
            }
        }
    }

    private fun convertPlantUMLToMermaid(plantUML: String): String {
        val lines = plantUML.lines()
        val mermaidBuilder = StringBuilder()

        // Mermaid with theme configuration for colors
        mermaidBuilder.appendLine("%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#90EE90', 'lineColor': '#00AA00' }}}%%")
        mermaidBuilder.appendLine("sequenceDiagram")

        // Extract participants (live = green background, dead = red background)
        val liveParticipants = mutableSetOf<String>()
        val deadParticipants = mutableSetOf<String>()

        lines.forEach { line ->
            // Match: participant "name" as id #COLOR
            val participantMatch = """participant\s+"([^"]+)"\s+as\s+(\w+)(?:\s+#([A-Fa-f0-9]{6}))?""".toRegex().find(line)
            if (participantMatch != null) {
                val displayName = participantMatch.groupValues[1]
                val id = participantMatch.groupValues[2]
                val color = participantMatch.groupValues.getOrNull(3) ?: ""

                // Check if this is a dead participant (red color #FFCCCC)
                if (color.equals("FFCCCC", ignoreCase = true)) {
                    deadParticipants.add(id)
                    mermaidBuilder.appendLine("    participant $id as $displayName")
                } else {
                    liveParticipants.add(id)
                    mermaidBuilder.appendLine("    participant $id as $displayName")
                }
            }
        }

        val allParticipants = liveParticipants + deadParticipants

        // Section: Live calls (solid arrows)
        mermaidBuilder.appendLine()
        mermaidBuilder.appendLine("    %% === LIVE CALLS (Green) ===")

        lines.forEach { line ->
            // Match live calls: module -[#00AA00]> module: functionName
            // Or regular: module -> module: functionName
            val liveCallMatch = """(\w+)\s*-(?:\[#[A-Fa-f0-9]+\])?>\s*(\w+)\s*:\s*(.+)""".toRegex().find(line.trim())
            if (liveCallMatch != null) {
                val from = liveCallMatch.groupValues[1]
                val to = liveCallMatch.groupValues[2]
                val message = liveCallMatch.groupValues[3].trim()

                // Skip dead code markers
                if (message.contains("[DEAD]")) {
                    return@forEach
                }

                // Only add if both participants exist
                if (allParticipants.contains(from) && allParticipants.contains(to)) {
                    mermaidBuilder.appendLine("    $from->>$to: $message")
                }
            }
        }

        // Section: Dead code (dotted red arrows in rect box)
        val deadCalls = mutableListOf<Triple<String, String, String>>()
        lines.forEach { line ->
            // Match dead calls: module -[#CC0000]> module: <color:#CC0000>funcName()</color> [DEAD]
            val deadCallMatch = """(\w+)\s*-\[#CC0000\]>\s*(\w+)\s*:\s*(?:<color:#CC0000>)?(.+?)(?:</color>)?\s*\[DEAD\]""".toRegex().find(line.trim())
            if (deadCallMatch != null) {
                val from = deadCallMatch.groupValues[1]
                val to = deadCallMatch.groupValues[2]
                val funcName = deadCallMatch.groupValues[3].trim()
                deadCalls.add(Triple(from, to, funcName))
            }
        }

        if (deadCalls.isNotEmpty()) {
            mermaidBuilder.appendLine()
            mermaidBuilder.appendLine("    %% === DEAD CODE (Red - Never Called) ===")
            mermaidBuilder.appendLine("    rect rgb(255, 200, 200)")

            val firstParticipant = liveParticipants.firstOrNull() ?: deadParticipants.firstOrNull() ?: "Unknown"
            mermaidBuilder.appendLine("        Note over $firstParticipant: DEAD CODE SECTION")

            deadCalls.forEach { (from, to, funcName) ->
                // Use --x for dotted line with X (indicating dead/error)
                mermaidBuilder.appendLine("        $from--x$to: [DEAD] $funcName")
            }

            mermaidBuilder.appendLine("    end")
        }

        // Match notes
        lines.forEach { line ->
            val noteMatch = """note\s+over\s+([^:]+):\s*Dead Code Section""".toRegex().find(line.trim())
            if (noteMatch != null) {
                // Already handled in dead code section above
                return@forEach
            }

            val generalNoteMatch = """note\s+(?:right|left|over)\s+[^:]*:\s*(.+)""".toRegex().find(line.trim())
            if (generalNoteMatch != null && !generalNoteMatch.groupValues[1].contains("Dead Code")) {
                val noteText = generalNoteMatch.groupValues[1].trim()
                mermaidBuilder.appendLine("    Note right of ${liveParticipants.lastOrNull() ?: deadParticipants.lastOrNull() ?: ""}:  $noteText")
            }
        }

        return mermaidBuilder.toString()
    }

    private fun loadDeadCodeReport(file: File) {
        val report = plantUMLParser.parseDeadCodeReport(file) ?: return

        // Update stats label
        deadCodeStatsLabel.text = "Dead Code: ${report.deadCount} functions (${String.format("%.1f", report.deadPercentage)}%) - " +
                "${report.totalCalled} called / ${report.totalInstrumented} instrumented"

        // Clear and populate table
        deadCodeTableModel.rowCount = 0

        for (func in report.deadFunctions) {
            val fileLineDisplay = if (func.filePath != "-") "${func.filePath}:${func.lineNumber}" else "-"
            deadCodeTableModel.addRow(arrayOf(
                "DEAD",
                func.module,
                func.functionName,
                fileLineDisplay,
                "navigate" // Placeholder - renderer shows "Go to source" link
            ))
        }
    }

    private fun loadPerformanceReport(file: File) {
        val report = plantUMLParser.parsePerformanceReport(file) ?: return

        // Update process info display
        val processStatus = if (report.processId != null) {
            val timestamp = if (report.startTime != null) {
                val date = java.util.Date((report.startTime.toLong() * 1000))
                val dateFormat = java.text.SimpleDateFormat("HH:mm:ss")
                " (started ${dateFormat.format(date)})"
            } else ""
            "Process: PID ${report.processId}$timestamp"
        } else {
            "Process: Not running"
        }
        processInfoLabel.text = processStatus

        // Clear and populate table
        performanceTableModel.rowCount = 0

        for (metric in report.functionMetrics) {
            performanceTableModel.addRow(arrayOf(
                metric.module,
                metric.functionName,
                metric.callCount,
                String.format("%.1f", metric.totalTimeMs),
                String.format("%.2f", metric.avgTimeMs),
                String.format("%.2f", metric.minTimeMs),
                String.format("%.2f", metric.maxTimeMs),
                String.format("%.2f", metric.avgMemoryMb),
                String.format("%.1f", metric.avgCpuPercent)
            ))
        }
    }

    private fun navigateToPerformance() {
        val selectedRow = performanceTable.selectedRow
        if (selectedRow < 0) return

        // Convert view row to model row (in case table is sorted)
        val modelRow = performanceTable.convertRowIndexToModel(selectedRow)

        val filePath = performanceTableModel.getValueAt(modelRow, 9) as? String ?: return
        if (filePath == "-") return // No file info available

        val lineNumber = performanceTableModel.getValueAt(modelRow, 10) as? Int ?: return

        navigateToFile(filePath, lineNumber)
    }

    private fun navigateToDeadCode() {
        val selectedRow = deadCodeTable.selectedRow
        if (selectedRow < 0) return

        // Convert view row to model row (in case table is sorted)
        val modelRow = deadCodeTable.convertRowIndexToModel(selectedRow)

        // File:Line is now in column 3 (combined format)
        val fileLineStr = deadCodeTableModel.getValueAt(modelRow, 3) as? String ?: return
        if (fileLineStr == "-") {
            javax.swing.JOptionPane.showMessageDialog(
                mainPanel,
                "No source location available for this function.",
                "Navigation",
                javax.swing.JOptionPane.INFORMATION_MESSAGE
            )
            return
        }

        // Parse "file:line" format - handle Windows paths with drive letters (e.g., C:\path\file.py:123)
        val lastColonIdx = fileLineStr.lastIndexOf(':')
        if (lastColonIdx <= 0) {
            PluginLogger.warn("[DeadCode] Invalid file:line format: $fileLineStr")
            return
        }

        val filePath = fileLineStr.substring(0, lastColonIdx)
        val lineNumber = fileLineStr.substring(lastColonIdx + 1).toIntOrNull() ?: 1

        navigateToFile(filePath, lineNumber)
    }

    private fun navigateToFile(filePath: String, lineNumber: Int) {
        if (filePath == "-" || lineNumber <= 0) return

        // Try 1: Direct absolute path from trace
        var vFile = LocalFileSystem.getInstance().findFileByPath(filePath)

        if (vFile == null) {
            // Try 2: Relative path from project root
            val projectPath = project.basePath
            if (projectPath != null) {
                val absolutePath = java.io.File(projectPath, filePath).absolutePath
                vFile = LocalFileSystem.getInstance().findFileByPath(absolutePath)
            }
        }

        if (vFile == null) {
            // Try 3: Normalize path (handle Windows backslashes, etc.)
            val normalizedPath = filePath.replace("\\", "/")
            vFile = LocalFileSystem.getInstance().findFileByPath(normalizedPath)
        }

        if (vFile == null && filePath.contains("site-packages")) {
            // Try 4: File is in site-packages - attempt to refresh and find in external libraries
            LocalFileSystem.getInstance().refreshAndFindFileByPath(filePath)?.let { foundFile ->
                vFile = foundFile
            }

            if (vFile == null) {
                // Show helpful message for external libraries
                javax.swing.SwingUtilities.invokeLater {
                    val fileName = java.io.File(filePath).name
                    com.intellij.openapi.ui.Messages.showInfoMessage(
                        project,
                        "Cannot navigate to external library file:\n$fileName\n\n" +
                        "This file is in site-packages (external library).\n" +
                        "Full path: $filePath\n\n" +
                        "The file exists but may not be indexed by PyCharm.\n\n" +
                        "To view this file:\n" +
                        "1. Project → External Libraries → Python → site-packages\n" +
                        "2. Or: File → Open → Navigate to path above",
                        "External Library Navigation"
                    )
                }
                return
            }
        }

        if (vFile == null) {
            // Try 5: Refresh file system and try again (for stdlib, conda envs, etc.)
            LocalFileSystem.getInstance().refreshAndFindFileByPath(filePath)?.let { foundFile ->
                vFile = foundFile
            }
        }

        if (vFile == null) {
            // Try 6: Last attempt - check if file physically exists and try to open it
            val file = java.io.File(filePath)
            if (file.exists() && file.isFile) {
                // Force refresh and retry
                LocalFileSystem.getInstance().refreshAndFindFileByPath(file.absolutePath)?.let { foundFile ->
                    vFile = foundFile
                }
            }
        }

        if (vFile == null) {
            // Finally failed - show helpful message
            javax.swing.SwingUtilities.invokeLater {
                val fileName = java.io.File(filePath).name
                val fileExists = java.io.File(filePath).exists()

                val message = if (fileExists) {
                    "Cannot navigate to file:\n$fileName\n\n" +
                    "Full path: $filePath\n\n" +
                    "The file exists on disk but PyCharm cannot open it.\n\n" +
                    "Possible reasons:\n" +
                    "- File is in Python standard library\n" +
                    "- File is in conda environment\n" +
                    "- File needs to be indexed by PyCharm\n\n" +
                    "To open manually:\n" +
                    "File → Open → Paste path above"
                } else {
                    "Cannot navigate to file:\n$fileName\n\n" +
                    "Full path: $filePath\n\n" +
                    "The file does not exist or is not accessible.\n\n" +
                    "Possible reasons:\n" +
                    "- File was deleted or moved\n" +
                    "- File path is incorrect\n" +
                    "- Permissions issue"
                }

                com.intellij.openapi.ui.Messages.showInfoMessage(
                    project,
                    message,
                    "Navigation Failed"
                )
            }
            return
        }

        // Successfully found file - open it and navigate to line
        val foundFile = vFile ?: return  // Smart cast helper
        val fileEditorManager = FileEditorManager.getInstance(project)
        val editor = fileEditorManager.openFile(foundFile, true).firstOrNull()

        if (editor != null && lineNumber > 0) {
            val textEditor = editor as? com.intellij.openapi.fileEditor.TextEditor
            textEditor?.editor?.caretModel?.moveToLogicalPosition(
                com.intellij.openapi.editor.LogicalPosition(lineNumber - 1, 0)
            )
        }
    }

    private fun previewDiagram() {
        val diagramContent = diagramTextArea.text
        if (diagramContent.isBlank()) {
            com.intellij.openapi.ui.Messages.showWarningDialog(
                project,
                "No diagram content to preview. Please generate traces first.",
                "No Diagram"
            )
            return
        }

        try {
            // Create temporary file based on diagram type
            val extension = when (diagramTypeCombo.selectedItem) {
                "PlantUML" -> "puml"
                "Mermaid" -> "md"  // Mermaid in markdown
                else -> "txt"
            }

            val tempDir = java.nio.file.Files.createTempDirectory("crawl4ai-diagrams")
            val tempFile = tempDir.resolve("diagram.$extension").toFile()

            // For Mermaid, wrap in markdown code block
            val content = if (diagramTypeCombo.selectedItem == "Mermaid") {
                "```mermaid\n$diagramContent\n```"
            } else {
                diagramContent
            }

            tempFile.writeText(content)

            // Open file in IntelliJ editor with preview
            val virtualFile = com.intellij.openapi.vfs.LocalFileSystem.getInstance()
                .refreshAndFindFileByIoFile(tempFile)

            if (virtualFile != null) {
                com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project)
                    .openFile(virtualFile, true)
            }

        } catch (e: Exception) {
            com.intellij.openapi.ui.Messages.showErrorDialog(
                project,
                "Failed to create preview: ${e.message}",
                "Preview Error"
            )
        }
    }

    private fun updateAttachButtonState(connected: Boolean) {
        if (connected) {
            attachButton.text = "Detach from Server"
            attachButton.background = java.awt.Color(244, 67, 54) // Red for disconnect
            attachButton.foreground = java.awt.Color.WHITE
            attachButton.toolTipText = "Disconnect from trace server"
        } else {
            attachButton.text = "Attach to Server"
            attachButton.background = java.awt.Color(33, 150, 243) // Blue for connect
            attachButton.foreground = java.awt.Color.WHITE
            attachButton.toolTipText = "Connect to running Python process via socket (real-time tracing)"
        }
    }

    private fun toggleAutoTracing(enabled: Boolean) {
        if (enabled) {
            // Set environment variable for auto-tracing
            val message = """
                Auto-tracing enabled!

                Add this to your Python run configuration:
                Environment variable: CRAWL4AI_AUTO_TRACE=1

                Or add at the top of your script:
                from crawl4ai.embodied_ai.monitoring.auto_instrumentor import enable_auto_tracing
                enable_auto_tracing()
            """.trimIndent()

            JOptionPane.showMessageDialog(
                mainPanel,
                message,
                "Auto-Tracing Setup",
                JOptionPane.INFORMATION_MESSAGE
            )
        }
    }

    private fun exportCurrentView() {
        val selectedTab = tabbedPane.selectedIndex
        val fileChooser = JFileChooser()

        // Start from current trace directory if available
        if (currentTraceDirectory != null && currentTraceDirectory!!.exists()) {
            fileChooser.currentDirectory = currentTraceDirectory
        }

        when (selectedTab) {
            0 -> { // Diagram
                fileChooser.dialogTitle = "Export Diagram"
                fileChooser.selectedFile = File("diagram.${if (diagramTypeCombo.selectedItem == "PlantUML") "puml" else "md"}")

                if (fileChooser.showSaveDialog(mainPanel) == JFileChooser.APPROVE_OPTION) {
                    fileChooser.selectedFile.writeText(diagramTextArea.text)
                    JOptionPane.showMessageDialog(mainPanel, "Diagram exported successfully!")
                }
            }
            1 -> { // Performance
                fileChooser.dialogTitle = "Export Performance Report"
                fileChooser.selectedFile = File("performance_report.csv")

                if (fileChooser.showSaveDialog(mainPanel) == JFileChooser.APPROVE_OPTION) {
                    exportTableToCSV(performanceTable, fileChooser.selectedFile)
                    JOptionPane.showMessageDialog(mainPanel, "Performance report exported successfully!")
                }
            }
            2 -> { // Dead Code
                fileChooser.dialogTitle = "Export Dead Code Report"
                fileChooser.selectedFile = File("dead_code_report.csv")

                if (fileChooser.showSaveDialog(mainPanel) == JFileChooser.APPROVE_OPTION) {
                    exportTableToCSV(deadCodeTable, fileChooser.selectedFile)
                    JOptionPane.showMessageDialog(mainPanel, "Dead code report exported successfully!")
                }
            }
        }
    }

    private fun exportTableToCSV(table: JBTable, file: File) {
        val builder = StringBuilder()

        // Header
        for (i in 0 until table.columnCount) {
            builder.append(table.columnModel.getColumn(i).headerValue)
            if (i < table.columnCount - 1) builder.append(",")
        }
        builder.append("\n")

        // Rows
        for (row in 0 until table.rowCount) {
            for (col in 0 until table.columnCount) {
                builder.append(table.getValueAt(row, col))
                if (col < table.columnCount - 1) builder.append(",")
            }
            builder.append("\n")
        }

        file.writeText(builder.toString())
    }

    private fun disconnectSocketTrace() {
        traceSocketClient?.disconnect()
        traceSocketClient = null
        currentTraceMode = TraceMode.NONE
        updateTraceModeLabel()
        updateFileBasedControls()

        javax.swing.SwingUtilities.invokeLater {
            currentSessionLabel.text = "Disconnected from socket"
            processInfoLabel.text = "Process: Not running"
        }
    }

    private fun updateTraceModeLabel() {
        when (currentTraceMode) {
            TraceMode.NONE -> {
                traceModeLabel.text = "Mode: Not connected"
                traceModeLabel.foreground = JBColor.GRAY
            }
            TraceMode.FILE_BASED -> {
                traceModeLabel.text = "Mode: File-based (./traces folder)"
                traceModeLabel.foreground = JBColor.BLUE
            }
            TraceMode.SOCKET_REALTIME -> {
                traceModeLabel.text = "Mode: Socket (Real-time)"
                traceModeLabel.foreground = JBColor.GREEN
            }
        }
    }

    private fun updateFileBasedControls() {
        val isSocketMode = (currentTraceMode == TraceMode.SOCKET_REALTIME)

        // Disable file-based controls when in socket mode
        selectDirButton.isEnabled = !isSocketMode
        refreshButton.isEnabled = !isSocketMode
        autoRefreshCheckbox.isEnabled = !isSocketMode

        // Update tooltips for better UX
        if (isSocketMode) {
            selectDirButton.toolTipText = "Not available in real-time socket mode"
            refreshButton.toolTipText = "Not available in real-time socket mode"
            autoRefreshCheckbox.toolTipText = "Not available in real-time socket mode"
        } else {
            selectDirButton.toolTipText = "Select directory containing trace files"
            refreshButton.toolTipText = "Manually refresh data from trace directory"
            autoRefreshCheckbox.toolTipText = "Automatically refresh data from trace directory"
        }
    }

    /**
     * Show filter management dialog
     */
    private fun showFilterManagementDialog() {
        val owner = SwingUtilities.getWindowAncestor(mainPanel) as? java.awt.Window
        val dialog = JDialog(owner, "Global Trace Filters", java.awt.Dialog.ModalityType.APPLICATION_MODAL)
        dialog.setLayout(BorderLayout())
        dialog.setMinimumSize(Dimension(600, 500))

        val mainPanel = JBPanel<JBPanel<*>>(BorderLayout())
        mainPanel.border = JBUI.Borders.empty(10)

        // Tabbed pane for different filter types
        val filterTabs = JTabbedPane()

        // Tab 1: Excluded Folders
        val foldersPanel = createFilterListPanel(
            "Folders to Exclude (e.g., site-packages, venv):",
            traceFilter.config.excludedFolders,
            { folder -> traceFilter.addExcludedFolder(folder) },
            { folder -> traceFilter.removeExcludedFolder(folder) }
        )
        filterTabs.addTab("Folders", foldersPanel)

        // Tab 2: Excluded Files
        val filesPanel = createFilterListPanel(
            "Files to Exclude (e.g., __init__.py, test_*.py):",
            traceFilter.config.excludedFiles,
            { file -> traceFilter.addExcludedFile(file) },
            { file -> traceFilter.removeExcludedFile(file) }
        )
        filterTabs.addTab("Files", filesPanel)

        // Tab 3: Excluded Modules
        val modulesPanel = createFilterListPanel(
            "Modules to Exclude (e.g., unittest, pytest):",
            traceFilter.config.excludedModules,
            { module -> traceFilter.addExcludedModule(module) },
            { module -> traceFilter.removeExcludedModule(module) }
        )
        filterTabs.addTab("Modules", modulesPanel)

        // Tab 4: Include-Only (optional whitelist)
        val includePanel = createFilterListPanel(
            "Include-Only Patterns (leave empty to include all, or specify patterns to include only):",
            traceFilter.config.includeOnly,
            { pattern -> traceFilter.addIncludeOnly(pattern) },
            { pattern -> traceFilter.removeIncludeOnly(pattern) }
        )
        filterTabs.addTab("Include-Only", includePanel)

        mainPanel.add(filterTabs, BorderLayout.CENTER)

        // Bottom buttons
        val buttonPanel = JBPanel<JBPanel<*>>()
        buttonPanel.layout = BoxLayout(buttonPanel, BoxLayout.X_AXIS)

        buttonPanel.add(Box.createHorizontalGlue())

        val resetButton = JButton("Reset to Defaults")
        resetButton.addActionListener {
            traceFilter.resetToDefaults()
            dialog.dispose()
            showFilterManagementDialog() // Re-open to show updated values
        }
        buttonPanel.add(resetButton)

        buttonPanel.add(Box.createRigidArea(Dimension(10, 0)))

        val clearAllButton = JButton("Clear All")
        clearAllButton.addActionListener {
            traceFilter.clearAllFilters()
            dialog.dispose()
            showFilterManagementDialog() // Re-open to show updated values
        }
        buttonPanel.add(clearAllButton)

        buttonPanel.add(Box.createRigidArea(Dimension(10, 0)))

        val closeButton = JButton("Close")
        closeButton.addActionListener {
            dialog.dispose()
        }
        buttonPanel.add(closeButton)

        mainPanel.add(buttonPanel, BorderLayout.SOUTH)

        dialog.add(mainPanel)
        dialog.pack()
        dialog.setLocationRelativeTo(SwingUtilities.getWindowAncestor(this.mainPanel))
        dialog.isVisible = true
    }

    /**
     * Create a panel for managing a list of filter patterns
     */
    private fun createFilterListPanel(
        title: String,
        items: MutableList<String>,
        addCallback: (String) -> Unit,
        removeCallback: (String) -> Unit
    ): JPanel {
        val panel = JBPanel<JBPanel<*>>(BorderLayout())
        panel.border = JBUI.Borders.empty(10)

        // Title label
        val titleLabel = JBLabel(title)
        titleLabel.border = JBUI.Borders.emptyBottom(5)
        panel.add(titleLabel, BorderLayout.NORTH)

        // List of current items
        val listModel = DefaultListModel<String>()
        items.forEach { listModel.addElement(it) }
        val list = JBList(listModel)
        val scrollPane = JBScrollPane(list)
        panel.add(scrollPane, BorderLayout.CENTER)

        // Bottom: Add/Remove buttons
        val buttonPanel = JBPanel<JBPanel<*>>()
        buttonPanel.layout = BoxLayout(buttonPanel, BoxLayout.X_AXIS)

        val addField = JTextField(20)
        buttonPanel.add(addField)

        buttonPanel.add(Box.createRigidArea(Dimension(5, 0)))

        val addButton = JButton("Add")
        addButton.addActionListener {
            val text = addField.text.trim()
            if (text.isNotEmpty() && !listModel.contains(text)) {
                addCallback(text)
                listModel.addElement(text)
                addField.text = ""
            }
        }
        buttonPanel.add(addButton)

        buttonPanel.add(Box.createRigidArea(Dimension(10, 0)))

        val removeButton = JButton("Remove Selected")
        removeButton.addActionListener {
            val selectedIndex = list.selectedIndex
            if (selectedIndex >= 0) {
                val item = listModel.getElementAt(selectedIndex)
                removeCallback(item)
                listModel.remove(selectedIndex)
            }
        }
        buttonPanel.add(removeButton)

        panel.add(buttonPanel, BorderLayout.SOUTH)

        return panel
    }

    /**
     * Refresh all tabs with filtered data
     */
    private fun refreshAllTabs() {
        // Trigger update on current trace mode
        when (currentTraceMode) {
            TraceMode.FILE_BASED -> refreshAll()
            TraceMode.SOCKET_REALTIME -> {
                // Socket mode: Rebuild all displays with current filtered data
                SwingUtilities.invokeLater {
                    // Rebuild diagram
                    updateDiagramDisplay()

                    // Rebuild performance table (full refresh)
                    updatePerformanceFromSocketTrace(TraceEvent(
                        type = "refresh",
                        timestamp = 0.0,
                        callId = "",
                        module = "",
                        function = "",
                        file = "",
                        line = 0,
                        depth = 0,
                        parentId = null,
                        processId = 0,
                        sessionId = "",
                        correlationId = null,
                        learningPhase = null,
                        traceData = null
                    ))

                    // Rebuild dead code table (full refresh)
                    updateDeadCodeFromSocketTrace()

                    // Call trace tree is incrementally built, already filtered at entry point
                    // Flamegraph and other panels are also incrementally updated

                    PluginLogger.info("[ToolWindow] Refreshed all tabs with updated filters")
                }
            }
            TraceMode.NONE -> {
                // Nothing to refresh
            }
        }
    }

    fun getContent(): JComponent = mainPanel

    fun dispose() {
        // Dispose ManimVideoPanel file watcher
        manimVideoPanel.dispose()

        // Dispose ManimAutoRenderer
        manimAutoRenderer.dispose()

        // Dispose AI Explanation panel (stops llama.cpp server if running)
        aiExplanationPanel.dispose()

        PluginLogger.info("EnhancedLearningFlowToolWindow disposed")
    }
}
