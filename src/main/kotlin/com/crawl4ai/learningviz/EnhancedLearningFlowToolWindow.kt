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
import java.awt.FlowLayout
import java.awt.Font
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import javax.swing.*
import javax.swing.table.DefaultTableModel

/**
 * WrapLayout - A FlowLayout subclass that supports wrapping components to the next line.
 * Unlike FlowLayout which clips components when container is too narrow,
 * WrapLayout adjusts the container height to accommodate all components.
 */
class WrapLayout(align: Int = FlowLayout.LEFT, hgap: Int = 5, vgap: Int = 5) : FlowLayout(align, hgap, vgap) {

    override fun preferredLayoutSize(target: java.awt.Container): Dimension {
        return layoutSize(target, true)
    }

    override fun minimumLayoutSize(target: java.awt.Container): Dimension {
        val minimum = layoutSize(target, false)
        minimum.width -= (hgap + 1)
        return minimum
    }

    private fun layoutSize(target: java.awt.Container, preferred: Boolean): Dimension {
        synchronized(target.treeLock) {
            val targetWidth = target.size.width
            val insets = target.insets
            val horizontalInsetsAndGap = insets.left + insets.right + (hgap * 2)
            val maxWidth = if (targetWidth > 0) targetWidth - horizontalInsetsAndGap else Integer.MAX_VALUE

            val dim = Dimension(0, 0)
            var rowWidth = 0
            var rowHeight = 0

            val nmembers = target.componentCount
            for (i in 0 until nmembers) {
                val m = target.getComponent(i)
                if (m.isVisible) {
                    val d = if (preferred) m.preferredSize else m.minimumSize
                    if (rowWidth + d.width > maxWidth) {
                        addRow(dim, rowWidth, rowHeight)
                        rowWidth = 0
                        rowHeight = 0
                    }
                    if (rowWidth != 0) {
                        rowWidth += hgap
                    }
                    rowWidth += d.width
                    rowHeight = maxOf(rowHeight, d.height)
                }
            }
            addRow(dim, rowWidth, rowHeight)

            dim.width += horizontalInsetsAndGap
            dim.height += insets.top + insets.bottom + vgap * 2

            val scrollPane = SwingUtilities.getAncestorOfClass(JScrollPane::class.java, target)
            if (scrollPane != null && target.isValid) {
                dim.width -= (hgap + 1)
            }
            return dim
        }
    }

    private fun addRow(dim: Dimension, rowWidth: Int, rowHeight: Int) {
        dim.width = maxOf(dim.width, rowWidth)
        if (dim.height > 0) {
            dim.height += vgap
        }
        dim.height += rowHeight
    }
}

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
    private var showDeadCallTrees = false // Toggle for showing dead code in diagrams

    // Tab 2: Performance Metrics
    private val performancePanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val performanceTable: JBTable
    private val performanceTableModel: DefaultTableModel

    // Tab 3: Dead Code Detection
    private val deadCodePanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val deadCodeTable: JBTable
    private val deadCodeTableModel: DefaultTableModel
    private val deadCodeStatsLabel = JBLabel()
    // Toggle states for showing different function categories
    private var showDeadFunctions = true
    private var showAliveFunctions = true
    private var showExternalFunctions = true
    private var showFilteredFunctions = false  // Functions excluded by filters (default off)

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
    private var qualNameDebugCount = 0  // Debug counter for co_qualname logging
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

    // Class instantiation order tracking - first __init__/constructor call timestamp per class
    // Used to order class containers in Interactive Explorer by instantiation order
    private val classFirstInitTimestamp = mutableMapOf<String, Double>() // className -> first init timestamp

    // Function first-called timestamp tracking - when each function was first invoked
    // Used to show execution order and temporal flow in Interactive Explorer
    private val functionFirstCalledTimestamp = mutableMapOf<String, Double>() // funcKey -> first call timestamp

    // Branch registry for "Why Not Covered" analysis with ACTUAL branch conditions
    data class CallSiteBranchInfo(
        val branchType: String,      // "if", "elif", "else", "for", "while", "try", "except"
        val condition: String,       // Actual condition text, e.g., "config.enabled and user.is_admin"
        val line: Int,               // Line number of the branch
        val endLine: Int             // End line of the branch block
    )
    data class CallSiteInfo(
        val callee: String,          // Function being called
        val caller: String,          // Function containing the call
        val callerModule: String,    // Module of the caller
        val file: String,            // File path
        val line: Int,               // Line number of the call
        val inBranch: CallSiteBranchInfo?  // Branch info if call is inside a branch (null if unconditional)
    )
    private val socketCallSites = mutableListOf<CallSiteInfo>()  // All call sites with branch context
    private val socketFunctionBranches = mutableMapOf<String, List<Map<String, Any>>>()  // funcKey -> branches
    private val socketResolvedCallGraph = mutableMapOf<String, List<String>>()  // Static call graph for cross-class connections

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
        val isIntegrated = isProjectAlreadyIntegrated()
        val autoIntegrateButton = JButton(if (isIntegrated) "Re-Integrate" else "Auto-Integrate into Repo")
        autoIntegrateButton.toolTipText = if (isIntegrated)
            "TrueFlow is already set up. Click to reconfigure or update."
        else
            "Automatically set up tracing by selecting your Python entry point"
        autoIntegrateButton.addActionListener {
            openAutoIntegrateDialog()
        }
        // Green if not integrated (call to action), gray if already done
        if (isIntegrated) {
            autoIntegrateButton.background = java.awt.Color(100, 100, 100) // Gray - already done
            autoIntegrateButton.foreground = java.awt.Color.WHITE
        } else {
            autoIntegrateButton.background = java.awt.Color(76, 175, 80) // Green highlight - action needed
            autoIntegrateButton.foreground = java.awt.Color.WHITE
        }
        toolbar.add(autoIntegrateButton)

        // Attach/Detach button (second button - most important after auto-integrate)
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

        // Auto-trace toggle
        val autoTraceCheckbox = JCheckBox("Enable Auto-Tracing")
        autoTraceCheckbox.toolTipText = "Automatically instrument Python code (zero code changes)"
        autoTraceCheckbox.addActionListener {
            toggleAutoTracing(autoTraceCheckbox.isSelected)
        }
        toolbar.add(autoTraceCheckbox)

        // Export button moved to stats panel row 3

        mainPanel.toolbar = toolbar
    }

    private fun openAutoIntegrateDialog() {
        val dialog = AutoIntegrationDialog(project)
        dialog.show()
    }

    /**
     * Check if the project already has TrueFlow integration (runtime injector deployed).
     * Returns true if .pycharm_plugin/runtime_injector exists with essential files.
     */
    private fun isProjectAlreadyIntegrated(): Boolean {
        // Check both .pycharm_plugin (legacy) and .trueflow (new) directories
        val possibleDirs = listOf(
            java.io.File("${project.basePath}/.pycharm_plugin/runtime_injector"),
            java.io.File("${project.basePath}/.trueflow/runtime_injector")
        )

        // Check for essential files in any of the possible directories
        val essentialFiles = listOf(
            "python_runtime_instrumentor.py",
            "sitecustomize.py"
        )

        return possibleDirs.any { runtimeInjectorDir ->
            runtimeInjectorDir.exists() && essentialFiles.all { java.io.File(runtimeInjectorDir, it).exists() }
        }
    }

    private var statsExpanded = false
    private lateinit var expandedStatsPanel: JPanel
    private lateinit var statsToggleButton: JButton
    private lateinit var manageFiltersButton: JButton
    private lateinit var filtersAppliedButton: JButton

    private fun createStatsPanel() {
        // Compact dashboard with 3 organized rows - centered
        statsPanel.layout = BoxLayout(statsPanel, BoxLayout.Y_AXIS)
        statsPanel.border = JBUI.Borders.empty(4, 4)

        // Increased font sizes for better readability
        val smallFont = Font("SansSerif", Font.PLAIN, 13)
        val normalFont = Font("SansSerif", Font.PLAIN, 14)
        val boldFont = Font("SansSerif", Font.BOLD, 14)

        // === ROW 1: Version | Mode | Session | Process ===
        val row1 = JBPanel<JBPanel<*>>(FlowLayout(FlowLayout.CENTER, 6, 2))
        row1.border = JBUI.Borders.emptyBottom(2)

        // Version badge
        versionLabel.font = smallFont
        versionLabel.foreground = JBColor(0x666666, 0xAAAAAA)
        row1.add(versionLabel)

        row1.add(createSeparator())

        // Mode (connection status) - prominent with status color
        traceModeLabel.font = boldFont
        traceModeLabel.foreground = JBColor(0xCC4400, 0xFF6633)  // Orange = disconnected
        row1.add(traceModeLabel)

        row1.add(createSeparator())

        // Session ID
        currentSessionLabel.font = smallFont
        currentSessionLabel.foreground = JBColor(0x666666, 0x999999)
        row1.add(currentSessionLabel)

        row1.add(createSeparator())

        // Process info
        processInfoLabel.font = smallFont
        processInfoLabel.foreground = JBColor(0x666666, 0x999999)
        row1.add(processInfoLabel)

        statsPanel.add(row1)

        // === ROW 2: Calls | Avg Time | Dead Code | Total Time | Export ===
        val row2 = JBPanel<JBPanel<*>>(FlowLayout(FlowLayout.CENTER, 6, 2))
        row2.border = JBUI.Borders.emptyBottom(3)

        // Total Calls - blue (primary metric)
        totalCallsLabel.font = boldFont
        totalCallsLabel.foreground = JBColor(0x0066CC, 0x66AAFF)
        row2.add(totalCallsLabel)

        row2.add(createSeparator())

        // Avg time - green (performance)
        avgTimeLabel.font = boldFont
        avgTimeLabel.foreground = JBColor(0x228B22, 0x66CC66)
        row2.add(avgTimeLabel)

        row2.add(createSeparator())

        // Dead code % - orange (warning indicator)
        deadCodePercentLabel.font = boldFont
        deadCodePercentLabel.foreground = JBColor(0xCC6600, 0xFFAA33)
        row2.add(deadCodePercentLabel)

        row2.add(createSeparator())

        // Total time - muted
        totalTimeLabel.font = normalFont
        totalTimeLabel.foreground = JBColor(0x555555, 0xAAAAAA)
        row2.add(totalTimeLabel)

        row2.add(createSeparator())

        // Export button - important, always visible in row 2
        val exportButton = JButton("Export")
        exportButton.toolTipText = "Export current view data"
        exportButton.font = smallFont
        exportButton.margin = java.awt.Insets(2, 8, 2, 8)
        exportButton.addActionListener { exportCurrentView() }
        row2.add(exportButton)

        statsPanel.add(row2)

        // === ROW 3: Single Filters button (shows status + manages filters) ===
        val row3 = JBPanel<JBPanel<*>>(FlowLayout(FlowLayout.CENTER, 8, 3))
        row3.background = JBColor(0xF0F0F0, 0x3A3A3A)
        row3.isOpaque = true
        row3.border = JBUI.Borders.empty(2, 4)

        // Single Filters button - shows filter status, styled by state, click to manage
        filtersAppliedButton = JButton("Filters: Default")
        filtersAppliedButton.toolTipText = "Click to manage filters"
        filtersAppliedButton.font = smallFont
        filtersAppliedButton.margin = java.awt.Insets(2, 12, 2, 12)
        filtersAppliedButton.addActionListener { showFilterManagementDialog() }
        updateFiltersAppliedButton()  // Set initial style and text
        row3.add(filtersAppliedButton)

        // Hidden label for compatibility (filter stats now in button)
        filterStatsLabel.isVisible = false

        // Hidden button for compatibility
        manageFiltersButton = JButton("")
        manageFiltersButton.isVisible = false

        statsPanel.add(row3)

        // Hidden expanded panel (kept for compatibility but not used)
        expandedStatsPanel = JBPanel<JBPanel<*>>(FlowLayout(FlowLayout.LEFT, 0, 0))
        expandedStatsPanel.isVisible = false

        // Hidden toggle button (kept for compatibility but not used)
        statsToggleButton = JButton("")
        statsToggleButton.isVisible = false

        // Register filter change listener
        traceFilter.addChangeListener {
            updateFilterStatsLabel()
            refreshAllTabs()
        }

        // Initial update
        updateFilterStatsLabel()
    }

    private fun createSeparator(): JLabel {
        val sep = JBLabel("|")
        sep.foreground = JBColor(0xCCCCCC, 0x555555)
        sep.font = Font("SansSerif", Font.PLAIN, 11)
        sep.border = JBUI.Borders.empty(0, 2)
        return sep
    }

    private fun toggleStatsExpansion() {
        statsExpanded = !statsExpanded
        expandedStatsPanel.isVisible = statsExpanded
        statsToggleButton.text = if (statsExpanded) "▼ Less" else "▶ More"
        statsPanel.revalidate()
        statsPanel.repaint()
    }

    private fun updateFilterStatsLabel() {
        filterStatsLabel.text = "Filters: ${traceFilter.getStats()}"
        // Also update the filters button
        updateFiltersAppliedButton()
    }

    /**
     * Update the Filters button appearance based on filter state.
     * - Default filters: White background, dark grey text
     * - Custom filters: Highlighted with filter count
     */
    private fun updateFiltersAppliedButton() {
        if (!::filtersAppliedButton.isInitialized) return

        val stats = traceFilter.getStats()
        val isDefault = traceFilter.isDefault()
        val activePreset = traceFilter.activePresetName

        if (activePreset != null) {
            // Preset active - show preset name
            filtersAppliedButton.text = "Filters: $activePreset"
            filtersAppliedButton.background = JBColor(0xE8F5E9, 0x2E4A3E)  // Light green / Dark green
            filtersAppliedButton.foreground = JBColor(0x2E7D32, 0x81C784)  // Green / Light green
            filtersAppliedButton.toolTipText = "Preset '$activePreset' active ($stats) - click to manage"
        } else if (isDefault) {
            // Default filters - white/light background, dark grey text
            filtersAppliedButton.text = "Filters: Default"
            filtersAppliedButton.background = JBColor(0xFFFFFF, 0x4A4A4A)  // White / Dark grey
            filtersAppliedButton.foreground = JBColor(0x555555, 0xBBBBBB)  // Dark grey / Light grey
            filtersAppliedButton.toolTipText = "Using default filters - click to customize"
        } else {
            // Custom filters - show count, slightly highlighted
            filtersAppliedButton.text = "Filters: $stats"
            filtersAppliedButton.background = JBColor(0xE8F0FE, 0x3A4A5A)  // Light blue / Darker blue-grey
            filtersAppliedButton.foreground = JBColor(0x1967D2, 0x8AB4F8)  // Blue / Light blue
            filtersAppliedButton.toolTipText = "Custom filters applied - click to manage"
        }
        filtersAppliedButton.isOpaque = true
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

        // Open in Browser button - fullscreen view
        val browserButton = JButton("View Fullscreen")
        browserButton.toolTipText = "Open diagram fullscreen in browser with zoom controls"
        browserButton.addActionListener {
            mermaidPreviewPanel?.openInBrowser(
                showDeadCallTrees = showDeadCallTrees,
                diagramType = diagramTypeCombo.selectedItem?.toString()?.lowercase() ?: "mermaid"
            )
        }
        typePanel.add(browserButton)

        // Show Dead Call Trees checkbox - toggles display of AST-based dead code
        val deadCallTreesCheckbox = javax.swing.JCheckBox("Show Dead Call Trees")
        deadCallTreesCheckbox.toolTipText = "Show functions that were never called (from static AST analysis)"
        deadCallTreesCheckbox.isSelected = showDeadCallTrees
        deadCallTreesCheckbox.addActionListener {
            showDeadCallTrees = deadCallTreesCheckbox.isSelected
            updateDiagramDisplay()
        }
        typePanel.add(deadCallTreesCheckbox)

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

        // Toggle checkboxes panel (center)
        val togglePanel = JBPanel<JBPanel<*>>()
        togglePanel.layout = BoxLayout(togglePanel, BoxLayout.X_AXIS)
        togglePanel.border = JBUI.Borders.empty(0, 10, 0, 10)

        val deadToggle = JCheckBox("DEAD", showDeadFunctions)
        deadToggle.foreground = JBColor(0xEF4444, 0xF87171)  // Red
        deadToggle.addActionListener {
            showDeadFunctions = deadToggle.isSelected
            updateDeadCodeFromSocketTrace()
        }
        togglePanel.add(deadToggle)

        val aliveToggle = JCheckBox("ALIVE", showAliveFunctions)
        aliveToggle.foreground = JBColor(0x22C55E, 0x4ADE80)  // Green
        aliveToggle.addActionListener {
            showAliveFunctions = aliveToggle.isSelected
            updateDeadCodeFromSocketTrace()
        }
        togglePanel.add(aliveToggle)

        val externalToggle = JCheckBox("EXTERNAL", showExternalFunctions)
        externalToggle.foreground = JBColor(0xF59E0B, 0xFBBF24)  // Amber/orange
        externalToggle.toolTipText = "Functions traced at runtime but not in static registry"
        externalToggle.addActionListener {
            showExternalFunctions = externalToggle.isSelected
            updateDeadCodeFromSocketTrace()
        }
        togglePanel.add(externalToggle)

        val filteredToggle = JCheckBox("FILTERED", showFilteredFunctions)
        filteredToggle.foreground = JBColor.GRAY
        filteredToggle.toolTipText = "Functions excluded by global filters (tests, site-packages, etc.)"
        filteredToggle.addActionListener {
            showFilteredFunctions = filteredToggle.isSelected
            updateDeadCodeFromSocketTrace()
        }
        togglePanel.add(filteredToggle)

        controlPanel.add(togglePanel, BorderLayout.CENTER)

        // Filter info panel (right side)
        val filterInfoPanel = JBPanel<JBPanel<*>>()
        val filterInfoLabel = JBLabel("Global filters active")
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
        tabbedPane.addTab("Architecture Video", manimVideoPanel)
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
        classFirstInitTimestamp.clear()
        functionFirstCalledTimestamp.clear()
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
            "branch_registry" -> {
                // Receive branch registry for Why Not Covered analysis
                handleBranchRegistry(event)
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

        // Debug: Log first few __init__ calls to verify co_qualname is working
        if (qualNameDebugCount < 20 && (event.function.contains("init") || event.function.contains("__"))) {
            PluginLogger.info("[co_qualname DEBUG] module=${event.module}, function=${event.function}, key=$functionKey")
            qualNameDebugCount++
        }

        // Skip Python internal pseudo-functions that are NOT actual function calls:
        // 1. <module> - Module-level code execution during import
        // 2. Class body execution - When a class is defined, Python executes its body
        //    These appear as bare class names (no . in function name) without __init__
        // These clutter coverage stats and don't match the static function registry
        val isModulePseudoFunction = event.function == "<module>"
        val isClassBodyExecution = event.function.isNotEmpty() &&
            !event.function.contains(".") &&
            !event.function.startsWith("__") &&
            event.function.first().isUpperCase()  // Class names are typically PascalCase

        if (!isModulePseudoFunction && !isClassBodyExecution) {
            socketTraceAllFunctions.add(functionKey)
            socketTraceCalls[functionKey] = (socketTraceCalls[functionKey] ?: 0) + 1
            socketTraceFileLineMap[functionKey] = Pair(event.file, event.line)
        } else {
            // Still track for display purposes but don't count as "called function"
            PluginLogger.debug("[ToolWindow] Skipping pseudo-function: ${event.function} (module=$isModulePseudoFunction, classBody=$isClassBodyExecution)")
        }

        // Track first-called timestamp for REAL functions only (skip pseudo-functions)
        // Used to show execution order and temporal flow in Interactive Explorer
        if (event.type == "call" && !isModulePseudoFunction && !isClassBodyExecution && functionKey !in functionFirstCalledTimestamp) {
            functionFirstCalledTimestamp[functionKey] = event.timestamp
        }

        // Track class instantiation order - record first __init__/constructor call timestamp per class
        // This is used to order class containers in Interactive Explorer by instantiation order
        if (event.type == "call" && (event.function == "__init__" || event.function == "constructor")) {
            // Extract class name from module (e.g., "myapp.services.MyClass")
            val className = event.module
            if (className !in classFirstInitTimestamp) {
                classFirstInitTimestamp[className] = event.timestamp
                PluginLogger.debug("[ToolWindow] Class instantiation order: $className at ${event.timestamp}")
            }
        }

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

        // Collect ACTIVE participants only - modules that have at least one call in socketTraceCalls
        val activeParticipants = socketTraceCalls.keys
            .map { funcKey ->
                val parts = funcKey.split(".")
                parts.dropLast(1).lastOrNull() ?: "__main__"
            }
            .toSet()

        // Collect dead functions (defined but never called) - only if toggle is enabled
        val deadFunctions = if (showDeadCallTrees) {
            socketAllDefinedFunctions.filter { it !in socketTraceCalls }
        } else {
            emptyList()
        }
        val deadParticipants = mutableSetOf<String>()
        if (showDeadCallTrees) {
            deadFunctions.forEach { funcKey ->
                val parts = funcKey.split(".")
                val module = parts.dropLast(1).lastOrNull() ?: "__main__"
                deadParticipants.add(module)
            }
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

            // Add participant declarations - ONLY ACTIVE participants with actual calls (green background)
            activeParticipants.forEach { participant ->
                val safe = escapePlantUML(participant)
                appendLine("participant \"$safe\" as $safe #90EE90")
            }

            // Add DEAD-only participants (red background) - only if showDeadCallTrees is enabled
            if (showDeadCallTrees) {
                deadParticipants.filter { it !in activeParticipants }.forEach { participant ->
                    val safe = escapePlantUML(participant)
                    appendLine("participant \"$safe\" as $safe #FFCCCC")
                }
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

            // Add dead code section (red arrows) - only if showDeadCallTrees is enabled
            if (showDeadCallTrees && deadFunctions.isNotEmpty()) {
                appendLine()
                appendLine("' === DEAD CODE (Red - Never Called) ===")
                appendLine("note over ${activeParticipants.firstOrNull() ?: deadParticipants.firstOrNull() ?: "Unknown"}: Dead Code Section")

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
                    appendLine("note over ${activeParticipants.firstOrNull() ?: deadParticipants.firstOrNull() ?: "Unknown"}: ... and ${deadFunctions.size - 30} more dead functions")
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

            // Debug: Log sample registry keys to verify format
            val sampleKeys = socketAllDefinedFunctions.filter { it.contains("__init__") }.take(5)
            if (sampleKeys.isNotEmpty()) {
                PluginLogger.info("[ToolWindow] Sample __init__ registry keys: $sampleKeys")
            }

            // Update Dead Code tab immediately
            SwingUtilities.invokeLater {
                updateDeadCodeFromSocketTrace()
            }

        } catch (e: Exception) {
            PluginLogger.error("[ToolWindow] Failed to parse function registry: ${e.message}", e)
        }
    }

    private fun handleBranchRegistry(event: TraceEvent) {
        // Parse branch registry for "Why Not Covered" analysis with ACTUAL branch conditions
        try {
            val traceData = event.traceData ?: return
            val callSitesArray = traceData.getAsJsonArray("call_sites") ?: return

            socketCallSites.clear()
            socketFunctionBranches.clear()
            socketResolvedCallGraph.clear()

            // Parse call sites with their branch context
            for (siteElement in callSitesArray) {
                val siteObj = siteElement.asJsonObject
                val callee = siteObj.get("callee")?.asString ?: continue
                val caller = siteObj.get("caller")?.asString ?: continue
                val callerModule = siteObj.get("caller_module")?.asString ?: ""
                val file = siteObj.get("file")?.asString ?: ""
                val line = siteObj.get("line")?.asInt ?: 0

                // Parse branch info if present
                val branchInfo = siteObj.get("in_branch")?.let { branchEl ->
                    if (branchEl.isJsonNull) null else {
                        val branchObj = branchEl.asJsonObject
                        CallSiteBranchInfo(
                            branchType = branchObj.get("type")?.asString ?: "if",
                            condition = branchObj.get("condition")?.asString ?: "unknown condition",
                            line = branchObj.get("line")?.asInt ?: 0,
                            endLine = branchObj.get("end_line")?.asInt ?: 0
                        )
                    }
                }

                socketCallSites.add(CallSiteInfo(
                    callee = callee,
                    caller = caller,
                    callerModule = callerModule,
                    file = file,
                    line = line,
                    inBranch = branchInfo
                ))
            }

            // Parse function branches
            val functionBranchesObj = traceData.getAsJsonObject("function_branches")
            if (functionBranchesObj != null) {
                for ((funcKey, branchesEl) in functionBranchesObj.entrySet()) {
                    val funcObj = branchesEl.asJsonObject
                    val branches = funcObj.getAsJsonArray("branches")?.map { br ->
                        val brObj = br.asJsonObject
                        mapOf<String, Any>(
                            "type" to (brObj.get("type")?.asString ?: ""),
                            "line" to (brObj.get("line")?.asInt ?: 0),
                            "condition" to (brObj.get("condition")?.asString ?: "")
                        )
                    } ?: emptyList()
                    socketFunctionBranches[funcKey] = branches
                }
            }

            // Parse resolved call graph for cross-class static connections
            val resolvedCallGraphObj = traceData.getAsJsonObject("resolved_call_graph")
            if (resolvedCallGraphObj != null) {
                for ((caller, calleesEl) in resolvedCallGraphObj.entrySet()) {
                    val callees = calleesEl.asJsonArray.map { it.asString }
                    socketResolvedCallGraph[caller] = callees
                }
            }

            PluginLogger.info("[ToolWindow] Received branch registry: ${socketCallSites.size} call sites, ${socketFunctionBranches.size} functions with branches, ${socketResolvedCallGraph.size} resolved call graph entries")

            // Update Interactive Explorer with branch data
            SwingUtilities.invokeLater {
                updateInteractiveVisualization()
            }

        } catch (e: Exception) {
            PluginLogger.error("[ToolWindow] Failed to parse branch registry: ${e.message}", e)
        }
    }

    private fun updateDeadCodeFromSocketTrace() {
        // Proper dead code detection using function registry
        // Both static analysis and runtime traces use Python's __name__ format (e.g., myapp.services.user)
        // Static registry uses sys.path to compute module names matching runtime's __name__

        // Helper function to check if file should be excluded (uses global filter)
        fun isFileExcluded(filePath: String): Boolean {
            return traceFilter.shouldExclude(filePath)
        }

        // Helper to check if a function should be excluded based on its file path
        fun shouldExcludeFunction(funcKey: String): Boolean {
            val filePath = socketFunctionDefinitions[funcKey]?.first ?: ""
            return traceFilter.shouldExclude(filePath)
        }

        // Build class-inference map FIRST (needed for both Dead Code and Interactive Explorer)
        // This handles the case where co_qualname returns "method" instead of "ClassName.method"
        val classInferenceMap = mutableMapOf<String, String>()
        val ambiguousKeys = mutableSetOf<String>()
        for (registryKey in socketAllDefinedFunctions) {
            val parts = registryKey.split(".")
            if (parts.size >= 2) {
                val methodName = parts.last()
                val potentialClassName = parts.getOrNull(parts.size - 2) ?: ""
                if (potentialClassName.isNotEmpty() && potentialClassName.first().isUpperCase()) {
                    val moduleParts = parts.dropLast(2)
                    if (moduleParts.isNotEmpty()) {
                        val shortKey = moduleParts.joinToString(".") + "." + methodName
                        if (shortKey in classInferenceMap) {
                            ambiguousKeys.add(shortKey)
                        } else {
                            classInferenceMap[shortKey] = registryKey
                        }
                    }
                }
            }
        }
        ambiguousKeys.forEach { classInferenceMap.remove(it) }

        // Normalize traced keys using class inference - use this EVERYWHERE
        val normalizedTraceCalls = mutableMapOf<String, Int>()
        for ((tracedKey, count) in socketTraceCalls) {
            val normalizedKey = when {
                tracedKey in socketAllDefinedFunctions -> tracedKey
                tracedKey in classInferenceMap -> classInferenceMap[tracedKey]!!
                else -> tracedKey
            }
            normalizedTraceCalls[normalizedKey] = (normalizedTraceCalls[normalizedKey] ?: 0) + count
        }

        // Compute FILTERED counts using NORMALIZED keys (consistent with Interactive Explorer)
        val filteredDefinedFunctions = socketAllDefinedFunctions.filter { !shouldExcludeFunction(it) }
        val filteredCalledFunctions = normalizedTraceCalls.filter { !shouldExcludeFunction(it.key) }

        // Diagnostic logging - KEY MATCH ANALYSIS
        val exactMatches = socketTraceCalls.keys.count { it in socketAllDefinedFunctions }
        val classInferredMatches = socketTraceCalls.keys.count { it !in socketAllDefinedFunctions && it in classInferenceMap }
        // Find traced keys that NEEDED class inference but were BLOCKED by ambiguity
        val ambiguousBlockedKeys = socketTraceCalls.keys.filter { key ->
            key !in socketAllDefinedFunctions && key in ambiguousKeys
        }
        if (ambiguousBlockedKeys.isNotEmpty()) {
            PluginLogger.warn("[DeadCode] AMBIGUOUS-BLOCKED traced keys (multiple classes have same method): ${ambiguousBlockedKeys.take(5)}")
        }
        val totalMatches = exactMatches + classInferredMatches
        PluginLogger.info("[DeadCode] RAW socketTraceCalls: ${socketTraceCalls.size}")
        PluginLogger.info("[DeadCode] Class inference map size: ${classInferenceMap.size}, ambiguous: ${ambiguousKeys.size}")
        PluginLogger.info("[DeadCode] KEY MATCH: $totalMatches of ${socketTraceCalls.size} (exact: $exactMatches, inferred: $classInferredMatches)")
        PluginLogger.info("[DeadCode] normalizedTraceCalls: ${normalizedTraceCalls.size}")
        PluginLogger.info("[DeadCode] filteredDefinedFunctions: ${filteredDefinedFunctions.size}")
        PluginLogger.info("[DeadCode] filteredCalledFunctions: ${filteredCalledFunctions.size}")
        if (socketTraceCalls.isNotEmpty()) {
            PluginLogger.info("[DeadCode] Sample traced keys: ${socketTraceCalls.keys.take(3)}")
        }
        if (socketAllDefinedFunctions.isNotEmpty()) {
            PluginLogger.info("[DeadCode] Sample registry keys: ${socketAllDefinedFunctions.take(3)}")
        }
        if (normalizedTraceCalls.isNotEmpty()) {
            PluginLogger.info("[DeadCode] Sample normalized keys: ${normalizedTraceCalls.keys.take(3)}")
        }
        if (classInferenceMap.isNotEmpty()) {
            PluginLogger.info("[DeadCode] Sample inference: ${classInferenceMap.entries.take(2).map { "${it.key} -> ${it.value}" }}")
        }

        val totalDefined = filteredDefinedFunctions.size
        // Only count traced functions that are ALSO in the registry (consistent with Interactive Explorer JS)
        // This avoids counting dynamically generated functions or functions from non-scanned modules
        val registryMatchedCalls = filteredCalledFunctions.filterKeys { it in filteredDefinedFunctions }
        val calledCount = registryMatchedCalls.size
        val unmatchedTraced = filteredCalledFunctions.size - calledCount
        val deadCount = if (totalDefined > 0) totalDefined - calledCount else 0

        PluginLogger.info("[DeadCode] Registry-matched calls: $calledCount (unmatched traced: $unmatchedTraced)")

        // Log unmatched traced functions for debugging - these are in trace but not registry
        if (unmatchedTraced > 0) {
            val unmatchedKeys = filteredCalledFunctions.keys.filter { it !in filteredDefinedFunctions }
            PluginLogger.info("[DeadCode] UNMATCHED TRACED (not in registry): ${unmatchedKeys.take(10)}")
            if (unmatchedKeys.size > 10) {
                PluginLogger.info("[DeadCode]   ... and ${unmatchedKeys.size - 10} more")
            }
        }

        // Calculate counts for each category
        val excludedCount = socketAllDefinedFunctions.size - filteredDefinedFunctions.size

        if (totalDefined > 0) {
            val deadCodePercent = (deadCount.toDouble() / totalDefined) * 100.0
            // Build detailed stats string
            val parts = mutableListOf<String>()
            parts.add("$deadCount dead")
            parts.add("$calledCount alive")
            if (unmatchedTraced > 0) parts.add("$unmatchedTraced external")
            if (excludedCount > 0) parts.add("$excludedCount filtered")
            deadCodeStatsLabel.text = "$totalDefined functions: ${parts.joinToString(", ")} (${String.format("%.1f", deadCodePercent)}% dead)"
        } else {
            deadCodeStatsLabel.text = "Real-time mode: ${filteredCalledFunctions.size} functions called (waiting for function registry...)"
        }

        // Clear table
        deadCodeTableModel.rowCount = 0

        // Calculate filtered-out functions (for FILTERED toggle)
        val excludedDefinedFunctions = socketAllDefinedFunctions.filter { shouldExcludeFunction(it) }
        val excludedCalledFunctions = normalizedTraceCalls.filter { shouldExcludeFunction(it.key) }
        val filteredOutCount = excludedDefinedFunctions.size + excludedCalledFunctions.size

        // Show DEAD functions (sorted by module/function)
        val deadFunctions = filteredDefinedFunctions.filter { it !in normalizedTraceCalls }.sorted()
        if (showDeadFunctions) {
            for (funcKey in deadFunctions) {
                val parts = funcKey.split(".")
                val module = parts.dropLast(1).joinToString(".")
                val function = parts.lastOrNull() ?: funcKey
                val (file, line) = socketFunctionDefinitions[funcKey] ?: Pair("-", 0)

                val fileLineDisplay = if (file != "-") "$file:$line" else "-"
                deadCodeTableModel.addRow(arrayOf(
                    "DEAD",
                    module.ifEmpty { "__main__" },
                    function,
                    fileLineDisplay,
                    "navigate"
                ))
            }
        }

        // Show ALIVE functions IN REGISTRY (sorted by call count descending)
        if (showAliveFunctions) {
            for ((funcKey, count) in registryMatchedCalls.entries.sortedByDescending { it.value }) {
                val parts = funcKey.split(".")
                val module = parts.dropLast(1).joinToString(".")
                val function = parts.lastOrNull() ?: funcKey
                val (file, line) = socketFunctionDefinitions[funcKey]
                    ?: socketTraceFileLineMap[funcKey]
                    ?: Pair("-", 0)

                val fileLineDisplay = if (file != "-") "$file:$line" else "-"
                deadCodeTableModel.addRow(arrayOf(
                    "ALIVE ($count calls)",
                    module.ifEmpty { "__main__" },
                    function,
                    fileLineDisplay,
                    "navigate"
                ))
            }
        }

        // Show EXTERNAL functions (traced but not in registry) - these are dynamic/unscanned
        val externalCalls = filteredCalledFunctions.filterKeys { it !in filteredDefinedFunctions }
        if (showExternalFunctions) {
            for ((funcKey, count) in externalCalls.entries.sortedByDescending { it.value }) {
                val parts = funcKey.split(".")
                val module = parts.dropLast(1).joinToString(".")
                val function = parts.lastOrNull() ?: funcKey
                val (file, line) = socketTraceFileLineMap[funcKey] ?: Pair("-", 0)

                val fileLineDisplay = if (file != "-") "$file:$line" else "-"
                deadCodeTableModel.addRow(arrayOf(
                    "EXTERNAL ($count calls)",
                    module.ifEmpty { "__main__" },
                    function,
                    fileLineDisplay,
                    "navigate"
                ))
            }
        }

        // Show FILTERED functions (excluded by global filters) when toggle is on
        if (showFilteredFunctions) {
            // Show filtered-out defined functions
            for (funcKey in excludedDefinedFunctions.sorted()) {
                val parts = funcKey.split(".")
                val module = parts.dropLast(1).joinToString(".")
                val function = parts.lastOrNull() ?: funcKey
                val (file, line) = socketFunctionDefinitions[funcKey] ?: Pair("-", 0)
                val called = normalizedTraceCalls.containsKey(funcKey)
                val status = if (called) "FILTERED (called)" else "FILTERED (dead)"

                val fileLineDisplay = if (file != "-") "$file:$line" else "-"
                deadCodeTableModel.addRow(arrayOf(
                    status,
                    module.ifEmpty { "__main__" },
                    function,
                    fileLineDisplay,
                    "navigate"
                ))
            }
        }

        // Update Interactive Explorer visualization with current data
        updateInteractiveVisualization()
    }

    /**
     * Updates the Interactive Explorer in the Manim tab with current trace data.
     * Builds call graph from socketRootCalls and provides "why not covered" analysis.
     *
     * IMPORTANT: This implements proper ROOT CAUSE TRACING - it walks UP the call chain
     * to find the TOPMOST executed function that blocked execution, not just the immediate caller.
     */
    private fun updateInteractiveVisualization() {
        // Skip update if no data available yet - don't overwrite demo/existing data with empty
        if (socketAllDefinedFunctions.isEmpty() && socketTraceCalls.isEmpty()) {
            PluginLogger.debug("[ToolWindow] Skipping Interactive Explorer update - no data yet")
            return
        }

        // Helper to check if a function should be excluded based on global filters
        // Uses the SAME logic as Dead Code tab: only check file path exclusion
        fun shouldExcludeFunction(funcName: String): Boolean {
            val filePath = socketFunctionDefinitions[funcName]?.first ?: ""
            return traceFilter.shouldExclude(filePath)
        }

        // Build FULL call graph from call tree (caller -> list of callees) - no filtering during traversal
        val callGraph = mutableMapOf<String, MutableList<String>>()
        fun traverseNode(node: CallTraceNode) {
            val callerKey = "${node.module}.${node.function}"
            if (callerKey !in callGraph) {
                callGraph[callerKey] = mutableListOf()
            }
            for (child in node.children) {
                val calleeKey = "${child.module}.${child.function}"
                if (calleeKey !in callGraph[callerKey]!!) {
                    callGraph[callerKey]!!.add(calleeKey)
                }
                traverseNode(child)
            }
        }
        socketRootCalls.forEach { traverseNode(it) }

        // Build reverse call graph (callee -> list of callers) from ALL defined functions
        // This includes static analysis, not just runtime calls
        val reverseCallGraph = mutableMapOf<String, MutableList<String>>()
        for ((caller, callees) in callGraph) {
            for (callee in callees) {
                if (callee !in reverseCallGraph) {
                    reverseCallGraph[callee] = mutableListOf()
                }
                if (caller !in reverseCallGraph[callee]!!) {
                    reverseCallGraph[callee]!!.add(caller)
                }
            }
        }

        // Build class-inference map for matching traced keys to registry keys
        // This handles the case where co_qualname returns "method" instead of "ClassName.method"
        // Map: "module.method" -> "module.ClassName.method" (only if unambiguous)
        val classInferenceMap = mutableMapOf<String, String>()
        val ambiguousKeys = mutableSetOf<String>()
        for (registryKey in socketAllDefinedFunctions) {
            val parts = registryKey.split(".")
            if (parts.size >= 2) {
                val methodName = parts.last()
                // Check if second-to-last part looks like a class name (PascalCase or has uppercase)
                val potentialClassName = parts.getOrNull(parts.size - 2) ?: ""
                if (potentialClassName.isNotEmpty() && potentialClassName.first().isUpperCase()) {
                    // This is likely module.ClassName.method format
                    // Create the short key: module.method (without ClassName)
                    val moduleParts = parts.dropLast(2)
                    if (moduleParts.isNotEmpty()) {
                        val shortKey = moduleParts.joinToString(".") + "." + methodName
                        if (shortKey in classInferenceMap) {
                            // Ambiguous - multiple classes have this method
                            ambiguousKeys.add(shortKey)
                        } else {
                            classInferenceMap[shortKey] = registryKey
                        }
                    }
                }
            }
        }
        // Remove ambiguous mappings
        ambiguousKeys.forEach { classInferenceMap.remove(it) }

        // Normalize traced keys using class inference
        val normalizedTraceCalls = mutableMapOf<String, Int>()
        for ((tracedKey, count) in socketTraceCalls) {
            val normalizedKey = when {
                tracedKey in socketAllDefinedFunctions -> tracedKey  // Exact match
                tracedKey in classInferenceMap -> classInferenceMap[tracedKey]!!  // Class-inferred match
                else -> tracedKey  // No match, keep original
            }
            normalizedTraceCalls[normalizedKey] = (normalizedTraceCalls[normalizedKey] ?: 0) + count
        }

        // Apply global filter to all data sources - exclude functions matching filter patterns
        val filteredAllFunctions = socketAllDefinedFunctions.filter { !shouldExcludeFunction(it) }
        val filteredTraceCalls = normalizedTraceCalls.filterKeys { !shouldExcludeFunction(it) }
        val filteredFunctionDefinitions = socketFunctionDefinitions.filterKeys { !shouldExcludeFunction(it) }
        val filteredResolvedCallGraph = socketResolvedCallGraph
            .filterKeys { !shouldExcludeFunction(it) }
            .mapValues { entry -> entry.value.filter { !shouldExcludeFunction(it) } }
            .filterValues { it.isNotEmpty() }

        // Also filter the call graph built from runtime traces
        val filteredCallGraph = callGraph
            .filterKeys { !shouldExcludeFunction(it) }
            .mapValues { entry -> entry.value.filter { !shouldExcludeFunction(it) } }
            .filterValues { it.isNotEmpty() }

        // Build "why not covered" analysis for dead functions with ROOT CAUSE TRACING
        val whyNotCovered = mutableMapOf<String, ManimVideoPanel.WhyNotCoveredInfo>()
        val deadFunctions = filteredAllFunctions.filter { it !in filteredTraceCalls }
        val executedFunctions = filteredTraceCalls.keys

        /**
         * Recursively trace up the call chain to find the ROOT CAUSE.
         * Returns: Pair<rootCauseFunction, callChain> where rootCauseFunction is the
         * FIRST EXECUTED function in the chain that blocked execution.
         *
         * @param func The dead function to analyze
         * @param visited Set of already visited functions (to prevent cycles)
         * @param chain The call chain built so far (from dead func upward)
         * @return Triple of (rootCauseType, rootCauseFunction, fullChain) or null if no root found
         */
        fun traceToRootCause(
            func: String,
            visited: MutableSet<String>,
            chain: MutableList<String>
        ): Triple<String, String, List<String>>? {
            if (func in visited) return null  // Cycle detected
            visited.add(func)
            chain.add(func)

            val callers = reverseCallGraph[func] ?: emptyList()

            if (callers.isEmpty()) {
                // No callers found - this is a root with no call sites
                return Triple("NO_CALL_SITES", func, chain.toList())
            }

            // Check each potential caller
            for (caller in callers) {
                if (caller in executedFunctions) {
                    // FOUND ROOT CAUSE! This caller WAS executed but didn't call our function
                    // The branch decision happened HERE
                    return Triple("BRANCH_NOT_TAKEN", caller, chain.toList())
                }
            }

            // All callers are also dead - recurse up to find the root
            for (caller in callers) {
                val result = traceToRootCause(caller, visited, chain)
                if (result != null) {
                    return result
                }
            }

            // No executed function found in entire chain - unreachable from entry points
            return Triple("UNREACHABLE_FROM_ENTRY", chain.last(), chain.toList())
        }

        for (deadFunc in deadFunctions) {
            val (rootCauseType, rootCauseFunc, callChain) = traceToRootCause(
                deadFunc,
                mutableSetOf(),
                mutableListOf()
            ) ?: Triple("UNKNOWN", deadFunc, listOf(deadFunc))

            val reasons = mutableListOf<ManimVideoPanel.WhyNotCoveredReason>()
            val (rootFile, rootLine) = socketFunctionDefinitions[rootCauseFunc] ?: ("" to 0)

            when (rootCauseType) {
                "NO_CALL_SITES" -> {
                    reasons.add(ManimVideoPanel.WhyNotCoveredReason(
                        type = "NO_CALL_SITES",
                        explanation = "No code in the project calls '$deadFunc'. It may be dead code or only called externally."
                    ))
                }
                "BRANCH_NOT_TAKEN" -> {
                    // Build explanation showing the full chain
                    val chainStr = if (callChain.size > 1) {
                        callChain.reversed().joinToString(" → ")
                    } else {
                        deadFunc
                    }

                    // Find ACTUAL branch condition from socketCallSites
                    // Look for call site where: caller matches rootCauseFunc and callee is in the chain
                    val firstDeadInChain = callChain.firstOrNull() ?: deadFunc
                    val relevantCallSite = socketCallSites.find { site ->
                        val fullCaller = "${site.callerModule}.${site.caller}"
                        (fullCaller == rootCauseFunc || site.caller == rootCauseFunc) &&
                        (site.callee == firstDeadInChain ||
                         callChain.any { chainFunc -> site.callee == chainFunc || chainFunc.endsWith(".${site.callee}") })
                    }

                    val actualBranchType = relevantCallSite?.inBranch?.branchType ?: "if"
                    val actualCondition = relevantCallSite?.inBranch?.condition ?: "condition was False"
                    val actualBranchLine = relevantCallSite?.inBranch?.line ?: rootLine

                    reasons.add(ManimVideoPanel.WhyNotCoveredReason(
                        type = "BRANCH_NOT_TAKEN",
                        caller = rootCauseFunc,
                        line = actualBranchLine,
                        branchType = actualBranchType,
                        branchCondition = actualCondition,
                        explanation = "Branch in '$rootCauseFunc' (line $actualBranchLine): $actualBranchType $actualCondition. Chain: $chainStr"
                    ))
                }
                "UNREACHABLE_FROM_ENTRY" -> {
                    val chainStr = callChain.reversed().joinToString(" → ")
                    reasons.add(ManimVideoPanel.WhyNotCoveredReason(
                        type = "UNREACHABLE_FROM_ENTRY",
                        explanation = "Function '$deadFunc' is unreachable from any entry point. Orphaned call chain: $chainStr"
                    ))
                }
                else -> {
                    reasons.add(ManimVideoPanel.WhyNotCoveredReason(
                        type = "UNKNOWN",
                        explanation = "Could not determine why '$deadFunc' wasn't called"
                    ))
                }
            }

            val rootDetail = if (rootCauseType == "BRANCH_NOT_TAKEN") {
                // Look up actual branch info from the first reason (which has the actual values)
                val branchReason = reasons.firstOrNull { it.type == "BRANCH_NOT_TAKEN" }
                ManimVideoPanel.WhyNotCoveredDetail(
                    type = rootCauseType,
                    caller = rootCauseFunc,
                    line = branchReason?.line ?: rootLine,
                    branchType = branchReason?.branchType ?: "if",
                    branchCondition = branchReason?.branchCondition ?: "condition was False",
                    branchLine = branchReason?.line ?: rootLine
                )
            } else null

            whyNotCovered[deadFunc] = ManimVideoPanel.WhyNotCoveredInfo(
                function = deadFunc,
                rootCause = rootCauseType,
                rootCauseDetail = rootDetail,
                reasons = reasons
            )
        }

        // Log data before sending to Interactive Explorer
        PluginLogger.info("[InteractiveExplorer] Sending data:")
        PluginLogger.info("[InteractiveExplorer]   ORIGINAL socketAllDefinedFunctions: ${socketAllDefinedFunctions.size}")
        PluginLogger.info("[InteractiveExplorer]   ORIGINAL socketTraceCalls: ${socketTraceCalls.size}")
        PluginLogger.info("[InteractiveExplorer]   ORIGINAL socketFunctionDefinitions: ${socketFunctionDefinitions.size}")
        PluginLogger.info("[InteractiveExplorer]   ORIGINAL callGraph: ${callGraph.size}")
        PluginLogger.info("[InteractiveExplorer]   ORIGINAL socketResolvedCallGraph: ${socketResolvedCallGraph.size}")
        PluginLogger.info("[InteractiveExplorer]   FILTERED allFunctions: ${filteredAllFunctions.size}")
        PluginLogger.info("[InteractiveExplorer]   FILTERED traceCalls: ${filteredTraceCalls.size}")
        PluginLogger.info("[InteractiveExplorer]   FILTERED callGraph: ${filteredCallGraph.size}")
        PluginLogger.info("[InteractiveExplorer]   FILTERED resolvedCallGraph: ${filteredResolvedCallGraph.size}")
        PluginLogger.info("[InteractiveExplorer]   whyNotCovered: ${whyNotCovered.size}")

        // KEY MATCH ANALYSIS - detect if traced keys match registry keys
        val exactMatches = socketTraceCalls.keys.count { it in socketAllDefinedFunctions }
        val classInferredMatches = socketTraceCalls.keys.count { it !in socketAllDefinedFunctions && it in classInferenceMap }
        val totalMatches = exactMatches + classInferredMatches
        val mismatchedKeys = socketTraceCalls.keys.filter { it !in socketAllDefinedFunctions && it !in classInferenceMap }.take(5)
        PluginLogger.info("[InteractiveExplorer]   KEY MATCH: $totalMatches of ${socketTraceCalls.size} traced functions found in registry")
        PluginLogger.info("[InteractiveExplorer]   Breakdown: $exactMatches exact, $classInferredMatches class-inferred, ${ambiguousKeys.size} ambiguous (skipped)")
        if (mismatchedKeys.isNotEmpty()) {
            PluginLogger.warn("[InteractiveExplorer]   MISMATCHED traced keys (not in registry): $mismatchedKeys")
            val registrySamples = socketAllDefinedFunctions.take(5)
            PluginLogger.warn("[InteractiveExplorer]   Sample registry keys: $registrySamples")
        }

        if (filteredAllFunctions.isNotEmpty()) {
            PluginLogger.info("[InteractiveExplorer]   Sample functions: ${filteredAllFunctions.take(5)}")
        }
        if (filteredTraceCalls.isNotEmpty()) {
            PluginLogger.info("[InteractiveExplorer]   Sample called: ${filteredTraceCalls.keys.take(5)}")
        }

        // Update the Manim panel's interactive visualization with FILTERED data
        manimVideoPanel.updateVisualizationData(
            allFunctions = filteredAllFunctions.toSet(),
            calledFunctions = filteredTraceCalls,
            callTree = filteredCallGraph.mapValues { it.value.toList() },
            functionDefinitions = filteredFunctionDefinitions,
            whyNotCovered = whyNotCovered,
            resolvedCallGraph = filteredResolvedCallGraph,
            classInstantiationOrder = classFirstInitTimestamp,
            functionFirstCalledTimestamp = functionFirstCalledTimestamp
        )
    }

    /**
     * Refresh Interactive Explorer with filtered data.
     * Called when global filters change to update the visualization.
     */
    private fun refreshInteractiveVisualizationWithFilters() {
        // Skip update if no data available yet - don't overwrite demo/existing data with empty
        if (socketAllDefinedFunctions.isEmpty() && socketTraceCalls.isEmpty()) {
            PluginLogger.debug("[ToolWindow] Skipping Interactive Explorer filter refresh - no data yet")
            return
        }

        // Helper to check if a function should be excluded based on global filters
        // Uses the SAME logic as Dead Code tab: only check file path exclusion
        fun shouldExcludeFunction(funcName: String): Boolean {
            val filePath = socketFunctionDefinitions[funcName]?.first ?: ""
            return traceFilter.shouldExclude(filePath)
        }

        // Build FULL call graph from socketRootCalls
        val callGraph = mutableMapOf<String, MutableList<String>>()
        fun traverseNode(node: CallTraceNode) {
            val callerKey = "${node.module}.${node.function}"
            if (callerKey !in callGraph) {
                callGraph[callerKey] = mutableListOf()
            }
            for (child in node.children) {
                val calleeKey = "${child.module}.${child.function}"
                if (calleeKey !in callGraph[callerKey]!!) {
                    callGraph[callerKey]!!.add(calleeKey)
                }
                traverseNode(child)
            }
        }
        socketRootCalls.forEach { traverseNode(it) }

        // Build class-inference map for matching traced keys to registry keys
        val classInferenceMap = mutableMapOf<String, String>()
        val ambiguousKeys = mutableSetOf<String>()
        for (registryKey in socketAllDefinedFunctions) {
            val parts = registryKey.split(".")
            if (parts.size >= 2) {
                val methodName = parts.last()
                val potentialClassName = parts.getOrNull(parts.size - 2) ?: ""
                if (potentialClassName.isNotEmpty() && potentialClassName.first().isUpperCase()) {
                    val moduleParts = parts.dropLast(2)
                    if (moduleParts.isNotEmpty()) {
                        val shortKey = moduleParts.joinToString(".") + "." + methodName
                        if (shortKey in classInferenceMap) {
                            ambiguousKeys.add(shortKey)
                        } else {
                            classInferenceMap[shortKey] = registryKey
                        }
                    }
                }
            }
        }
        ambiguousKeys.forEach { classInferenceMap.remove(it) }

        // Normalize traced keys using class inference
        val normalizedTraceCalls = mutableMapOf<String, Int>()
        for ((tracedKey, count) in socketTraceCalls) {
            val normalizedKey = when {
                tracedKey in socketAllDefinedFunctions -> tracedKey
                tracedKey in classInferenceMap -> classInferenceMap[tracedKey]!!
                else -> tracedKey
            }
            normalizedTraceCalls[normalizedKey] = (normalizedTraceCalls[normalizedKey] ?: 0) + count
        }

        // Filter all data sources - exclude functions matching filter patterns
        val filteredFunctions = socketAllDefinedFunctions.filter { !shouldExcludeFunction(it) }.toSet()
        val filteredTraceCalls = normalizedTraceCalls.filterKeys { !shouldExcludeFunction(it) }
        val filteredFunctionDefinitions = socketFunctionDefinitions.filterKeys { !shouldExcludeFunction(it) }

        // Filter call graph - only include edges where both caller and callee pass the filter
        val filteredCallGraph = callGraph
            .filterKeys { !shouldExcludeFunction(it) }
            .mapValues { entry -> entry.value.filter { !shouldExcludeFunction(it) } }
            .filterValues { it.isNotEmpty() }

        // Filter resolved call graph similarly
        val filteredResolvedCallGraph = socketResolvedCallGraph
            .filterKeys { !shouldExcludeFunction(it) }
            .mapValues { entry -> entry.value.filter { !shouldExcludeFunction(it) } }
            .filterValues { it.isNotEmpty() }

        // Recompute whyNotCovered for filtered functions (simplified version)
        val filteredWhyNotCovered = computeWhyNotCoveredForFilteredFunctions(
            filteredFunctions,
            filteredTraceCalls.keys,
            filteredCallGraph
        )

        // Update the Manim panel with filtered data
        manimVideoPanel.updateVisualizationData(
            allFunctions = filteredFunctions,
            calledFunctions = filteredTraceCalls,
            callTree = filteredCallGraph.mapValues { it.value.toList() },
            functionDefinitions = filteredFunctionDefinitions,
            whyNotCovered = filteredWhyNotCovered,
            resolvedCallGraph = filteredResolvedCallGraph,
            classInstantiationOrder = classFirstInitTimestamp,
            functionFirstCalledTimestamp = functionFirstCalledTimestamp
        )

        PluginLogger.info("[ToolWindow] Refreshed Interactive Explorer with ${filteredFunctions.size} filtered functions")
    }

    /**
     * Compute WhyNotCovered info for filtered functions.
     * Simplified version used when refreshing with filters.
     */
    private fun computeWhyNotCoveredForFilteredFunctions(
        allFunctions: Set<String>,
        calledFunctions: Set<String>,
        callGraph: Map<String, List<String>>
    ): Map<String, ManimVideoPanel.WhyNotCoveredInfo> {
        val whyNotCovered = mutableMapOf<String, ManimVideoPanel.WhyNotCoveredInfo>()
        val deadFunctions = allFunctions - calledFunctions

        // Build reverse call graph
        val reverseCallGraph = mutableMapOf<String, MutableList<String>>()
        callGraph.forEach { (caller, callees) ->
            callees.forEach { callee ->
                reverseCallGraph.getOrPut(callee) { mutableListOf() }.add(caller)
            }
        }

        for (func in deadFunctions) {
            val potentialCallers = reverseCallGraph[func] ?: emptyList()
            val reasons = mutableListOf<ManimVideoPanel.WhyNotCoveredReason>()
            var rootCauseType = "CALLER_NOT_EXECUTED"

            if (potentialCallers.isEmpty()) {
                // Orphan - no one calls this function
                rootCauseType = "NO_CALL_SITES"
            } else {
                // Check if callers are covered
                val coveredCallers = potentialCallers.filter { calledFunctions.contains(it) }
                val deadCallers = potentialCallers.filter { deadFunctions.contains(it) }

                if (coveredCallers.isNotEmpty()) {
                    // Has covered callers but wasn't called - likely a dead branch
                    rootCauseType = "BRANCH_NOT_TAKEN"
                    reasons.add(ManimVideoPanel.WhyNotCoveredReason(
                        type = "dead_branch",
                        caller = coveredCallers.first(),
                        explanation = "Caller ${coveredCallers.first()} is covered but doesn't call this function"
                    ))
                } else if (deadCallers.isNotEmpty()) {
                    // All callers are also dead - cascading effect
                    rootCauseType = "CALLER_NOT_EXECUTED"
                    reasons.add(ManimVideoPanel.WhyNotCoveredReason(
                        type = "cascading",
                        caller = deadCallers.first(),
                        explanation = "Caller ${deadCallers.first()} is also not covered"
                    ))
                }
            }

            whyNotCovered[func] = ManimVideoPanel.WhyNotCoveredInfo(
                function = func,
                rootCause = rootCauseType,
                rootCauseDetail = null,
                reasons = reasons
            )
        }

        return whyNotCovered
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

        // Save snapshot for AI context (async to not block UI)
        Thread { saveSnapshot() }.start()
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
            // Show a helpful message when no data is available
            val noDataMessage = """
                |sequenceDiagram
                |    Note over System: No trace data available yet.
                |    Note over System: Start a traced Python process to see the diagram.
                |    Note over System: Use 'Show Dead Call Trees' checkbox to include AST-based dead code.
            """.trimMargin()
            diagramTextArea.text = noDataMessage
            mermaidPreviewPanel?.updateDiagram(noDataMessage)
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

    /**
     * Save a comprehensive snapshot of all tab data for AI context.
     * Creates timestamped JSON files with performance, dead code, and diagram data.
     * Maintains only the last 5 snapshots to avoid disk bloat.
     * This is called automatically when trace data updates.
     */
    private fun saveSnapshot() {
        try {
            val traceDir = currentTraceDirectory ?: return

            // Create timestamped filename
            val timestamp = java.time.LocalDateTime.now()
                .format(java.time.format.DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"))
            val snapshotFile = File(traceDir, "snapshot_$timestamp.json")

            // Clean up old snapshots, keep only last 5
            cleanupOldSnapshots(traceDir, 5)

            val snapshot = buildString {
                append("{\n")

                // Performance data (hotspots)
                append("  \"performance\": {\n")
                append("    \"hotspots\": [\n")
                for (row in 0 until performanceTableModel.rowCount) {
                    if (row > 0) append(",\n")
                    append("      {\n")
                    append("        \"function\": \"")
                    append(performanceTableModel.getValueAt(row, 0)?.toString()?.replace("\"", "\\\"") ?: "")
                    append("\",\n")
                    append("        \"calls\": ")
                    append(performanceTableModel.getValueAt(row, 1)?.toString()?.toIntOrNull() ?: 0)
                    append(",\n")
                    append("        \"total_ms\": ")
                    append(performanceTableModel.getValueAt(row, 2)?.toString()?.toDoubleOrNull() ?: 0.0)
                    append(",\n")
                    append("        \"avg_ms\": ")
                    append(performanceTableModel.getValueAt(row, 3)?.toString()?.toDoubleOrNull() ?: 0.0)
                    append(",\n")
                    append("        \"file\": \"")
                    append(performanceTableModel.getValueAt(row, 5)?.toString()?.replace("\"", "\\\"") ?: "")
                    append("\"\n")
                    append("      }")
                }
                append("\n    ]\n")
                append("  },\n")

                // Dead code data
                append("  \"deadCode\": {\n")
                append("    \"dead_functions\": [\n")
                for (row in 0 until deadCodeTableModel.rowCount) {
                    if (row > 0) append(",\n")
                    append("      {\n")
                    append("        \"function\": \"")
                    append(deadCodeTableModel.getValueAt(row, 0)?.toString()?.replace("\"", "\\\"") ?: "")
                    append("\",\n")
                    append("        \"file\": \"")
                    append(deadCodeTableModel.getValueAt(row, 1)?.toString()?.replace("\"", "\\\"") ?: "")
                    append("\",\n")
                    append("        \"line\": ")
                    append(deadCodeTableModel.getValueAt(row, 2)?.toString()?.toIntOrNull() ?: 0)
                    append(",\n")
                    append("        \"status\": \"")
                    append(deadCodeTableModel.getValueAt(row, 3)?.toString()?.replace("\"", "\\\"") ?: "")
                    append("\"\n")
                    append("      }")
                }
                append("\n    ]\n")
                append("  },\n")

                // SQL Analysis data
                append("  \"sqlAnalysis\": {\n")
                val sqlData = sqlAnalyzerPanel.getSqlData()
                if (sqlData != null) {
                    append("    \"totalQueries\": ${sqlData.statistics.totalQueries},\n")
                    append("    \"nPlus1Issues\": ${sqlData.statistics.nPlus1Issues},\n")
                    append("    \"issues\": [\n")
                    sqlData.nPlus1Issues.forEachIndexed { idx, issue ->
                        if (idx > 0) append(",\n")
                        append("      {\n")
                        append("        \"severity\": \"${issue.severity}\",\n")
                        append("        \"pattern\": \"${issue.pattern.replace("\"", "\\\"").replace("\n", "\\n")}\",\n")
                        append("        \"count\": ${issue.count},\n")
                        append("        \"suggestion\": \"${issue.suggestion.replace("\"", "\\\"")}\"\n")
                        append("      }")
                    }
                    append("\n    ],\n")
                    append("    \"queries\": [\n")
                    sqlData.allQueries.take(20).forEachIndexed { idx, query ->
                        if (idx > 0) append(",\n")
                        append("      {\n")
                        append("        \"query\": \"${query.query.replace("\"", "\\\"").replace("\n", " ").take(200)}\",\n")
                        append("        \"module\": \"${query.module}\",\n")
                        append("        \"function\": \"${query.function}\"\n")
                        append("      }")
                    }
                    append("\n    ]\n")
                } else {
                    append("    \"totalQueries\": 0,\n")
                    append("    \"nPlus1Issues\": 0,\n")
                    append("    \"issues\": [],\n")
                    append("    \"queries\": []\n")
                }
                append("  },\n")

                // Diagram data
                append("  \"diagram\": {\n")
                append("    \"type\": \"")
                append(diagramTypeCombo.selectedItem?.toString() ?: "PlantUML")
                append("\",\n")
                append("    \"content\": ")
                // Escape the diagram content for JSON
                val escapedDiagram = diagramTextArea.text
                    .replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "")
                    .replace("\t", "\\t")
                append("\"$escapedDiagram\"\n")
                append("  },\n")

                // Metadata
                append("  \"metadata\": {\n")
                append("    \"timestamp\": \"")
                append(java.time.Instant.now().toString())
                append("\",\n")
                append("    \"totalCalls\": ")
                append(totalCallsLabel.text.substringAfter(": ").toIntOrNull() ?: 0)
                append(",\n")
                append("    \"deadCodeCount\": ")
                // deadCodeStatsLabel format: "Functions: X total, Y called, Z dead (P%)"
                val deadMatch = Regex("(\\d+) dead").find(deadCodeStatsLabel.text)
                append(deadMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0)
                append(",\n")
                append("    \"source\": \"pycharm\"\n")
                append("  }\n")

                append("}")
            }

            snapshotFile.writeText(snapshot)
        } catch (e: Exception) {
            // Silent fail - snapshot is auxiliary feature
        }
    }

    /**
     * Clean up old snapshot files, keeping only the most recent ones.
     */
    private fun cleanupOldSnapshots(traceDir: File, keepCount: Int) {
        try {
            val snapshotFiles = traceDir.listFiles { _, name ->
                name.startsWith("snapshot_") && name.endsWith(".json")
            }?.sortedByDescending { it.lastModified() } ?: return

            // Delete all but the most recent 'keepCount' files
            if (snapshotFiles.size > keepCount) {
                snapshotFiles.drop(keepCount).forEach { it.delete() }
            }
        } catch (e: Exception) {
            // Silent fail
        }
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

        // Preset management panel at top
        val presetPanel = JBPanel<JBPanel<*>>()
        presetPanel.layout = BoxLayout(presetPanel, BoxLayout.X_AXIS)
        presetPanel.border = JBUI.Borders.empty(0, 0, 10, 0)

        presetPanel.add(JBLabel("Preset: "))

        val presetCombo = com.intellij.openapi.ui.ComboBox<String>()
        presetCombo.isEditable = false
        val updatePresetCombo = {
            presetCombo.removeAllItems()
            presetCombo.addItem("(Custom)")
            traceFilter.getPresetNames().forEach { presetCombo.addItem(it) }
            val active = traceFilter.activePresetName
            if (active != null && traceFilter.hasPreset(active)) {
                presetCombo.selectedItem = active
            } else {
                presetCombo.selectedItem = "(Custom)"
            }
        }
        updatePresetCombo()

        presetCombo.addActionListener {
            val selected = presetCombo.selectedItem as? String
            if (selected != null && selected != "(Custom)" && traceFilter.hasPreset(selected)) {
                traceFilter.loadPreset(selected)
                dialog.dispose()
                showFilterManagementDialog() // Re-open to show updated values
            }
        }
        presetPanel.add(presetCombo)
        presetPanel.add(Box.createRigidArea(Dimension(10, 0)))

        val savePresetButton = JButton("Save As...")
        savePresetButton.addActionListener {
            val name = javax.swing.JOptionPane.showInputDialog(
                dialog,
                "Enter preset name:",
                "Save Filter Preset",
                javax.swing.JOptionPane.PLAIN_MESSAGE
            )
            if (!name.isNullOrBlank()) {
                traceFilter.savePreset(name.trim())
                updatePresetCombo()
                javax.swing.JOptionPane.showMessageDialog(
                    dialog,
                    "Preset '$name' saved successfully.",
                    "Preset Saved",
                    javax.swing.JOptionPane.INFORMATION_MESSAGE
                )
            }
        }
        presetPanel.add(savePresetButton)

        val deletePresetButton = JButton("Delete")
        deletePresetButton.addActionListener {
            val selected = presetCombo.selectedItem as? String
            if (selected != null && selected != "(Custom)") {
                val confirm = javax.swing.JOptionPane.showConfirmDialog(
                    dialog,
                    "Delete preset '$selected'?",
                    "Delete Preset",
                    javax.swing.JOptionPane.YES_NO_OPTION
                )
                if (confirm == javax.swing.JOptionPane.YES_OPTION) {
                    traceFilter.deletePreset(selected)
                    updatePresetCombo()
                }
            }
        }
        presetPanel.add(deletePresetButton)
        presetPanel.add(Box.createHorizontalGlue())

        mainPanel.add(presetPanel, BorderLayout.NORTH)

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

                    // Refresh Interactive Explorer with filtered data
                    refreshInteractiveVisualizationWithFilters()

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
