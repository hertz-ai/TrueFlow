package com.crawl4ai.learningviz

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileCreateEvent
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTabbedPane
import com.intellij.ui.jcef.JBCefApp
import com.intellij.ui.jcef.JBCefBrowser
import com.intellij.ui.jcef.JBCefBrowserBase
import com.intellij.ui.jcef.JBCefJSQuery
import com.intellij.util.ui.JBUI
import com.google.gson.Gson
import com.google.gson.JsonObject
import java.awt.BorderLayout
import java.awt.Desktop
import java.awt.FlowLayout
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import javax.swing.*

/**
 * Panel for displaying and playing Manim animations.
 *
 * Features:
 * 1. Video List Tab: Lists generated Manim videos with timestamps
 * 2. Interactive Explorer Tab: Three.js visualization of execution flow with dead branch analysis
 *
 * The Interactive Explorer shows:
 * - Executed functions (green)
 * - Dead/uncovered functions (red)
 * - Branch points with conditions
 * - "Why Not Covered" analysis explaining why code wasn't executed
 */
class ManimVideoPanel(private val project: Project) : JBPanel<JBPanel<*>>(BorderLayout()), Disposable {

    private val videoListModel = DefaultListModel<VideoInfo>()
    private val videoList = JList(videoListModel)
    private val infoPanel = JBPanel<JBPanel<*>>(GridBagLayout())
    private val statusLabel = JBLabel("No videos found")

    // Interactive Explorer (JCEF browser)
    private var interactiveBrowser: JBCefBrowser? = null
    private var jsQuery: JBCefJSQuery? = null
    private val gson = Gson()

    // View mode toggle (Flow Explorer vs Watch Architecture)
    private enum class ViewMode { FLOW_EXPLORER, WATCH_ARCHITECTURE }
    private var currentViewMode = ViewMode.FLOW_EXPLORER
    private var viewToggleButton: JButton? = null

    // Data for interactive visualization
    private var visualizationData: InteractiveVisualizationData? = null

    // Track if the browser page is loaded and ready
    private var browserPageReady = false
    private var pendingDataRefresh = false

    // Live server for real-time browser viewing
    private var explorerServer: InteractiveExplorerServer? = null
    private var liveServerButton: JButton? = null

    // Manim output directory (use PluginPaths for single source of truth)
    private val manimOutputDir = PluginPaths.getVideosDir(project)

    // File watcher for auto-refresh
    private var fileWatcherConnection: com.intellij.util.messages.MessageBusConnection? = null

    data class VideoInfo(
        val file: File,
        val timestamp: Date,
        val name: String,
        val size: Long,
        val duration: String = "Unknown"
    ) {
        override fun toString(): String {
            val dateFormat = SimpleDateFormat("HH:mm:ss")
            val sizeKB = size / 1024
            return "${dateFormat.format(timestamp)} - $name (${sizeKB}KB)"
        }
    }

    /**
     * Data structure for the interactive Three.js visualization.
     * Contains functions, branches, call graph, and coverage analysis.
     */
    data class InteractiveVisualizationData(
        val functions: Map<String, FunctionInfo>,
        val callGraph: Map<String, List<String>>,
        val resolvedCallGraph: Map<String, List<String>>,  // Static call graph for cross-class connections
        val coveredFunctions: List<String>,
        val deadFunctions: List<String>,
        val whyNotCovered: Map<String, WhyNotCoveredInfo>
    )

    data class FunctionInfo(
        val name: String,
        val line: Int,
        val file: String? = null,
        val branches: List<BranchInfo> = emptyList(),
        val callCount: Int = 0
    )

    data class BranchInfo(
        val type: String,  // "if", "elif", "else", "try", "except", "for", "while"
        val line: Int,
        val condition: String
    )

    data class WhyNotCoveredInfo(
        val function: String,
        val rootCause: String,  // "NO_CALL_SITES", "CALLER_NOT_EXECUTED", "BRANCH_NOT_TAKEN"
        val rootCauseDetail: WhyNotCoveredDetail? = null,
        val reasons: List<WhyNotCoveredReason> = emptyList()
    )

    data class WhyNotCoveredDetail(
        val type: String,
        val caller: String? = null,
        val line: Int? = null,
        val branchType: String? = null,
        val branchCondition: String? = null,
        val branchLine: Int? = null
    )

    data class WhyNotCoveredReason(
        val type: String,
        val caller: String? = null,
        val line: Int? = null,
        val branchType: String? = null,
        val branchCondition: String? = null,
        val explanation: String? = null
    )

    init {
        border = JBUI.Borders.empty(10)
        createUI()
        scanForVideos()
        setupFileWatcher()
    }

    private fun setupFileWatcher() {
        try {
            // Connect to message bus for VFS events
            fileWatcherConnection = ApplicationManager.getApplication().messageBus.connect(this)

            fileWatcherConnection?.subscribe(
                com.intellij.openapi.vfs.VirtualFileManager.VFS_CHANGES,
                object : BulkFileListener {
                    override fun after(events: List<VFileEvent>) {
                        // Check if any events are video file creations in monitored directories
                        val hasNewVideo = events.any { event ->
                            if (event is VFileCreateEvent) {
                                val path = event.path
                                val isVideoFile = path.endsWith(".mp4", ignoreCase = true) ||
                                                path.endsWith(".mov", ignoreCase = true) ||
                                                path.endsWith(".avi", ignoreCase = true) ||
                                                path.endsWith(".webm", ignoreCase = true)

                                // Check if in monitored directories (use PluginPaths)
                                val isInMonitoredDir = path.contains(".pycharm_plugin") &&
                                                      (path.contains("manim/media/videos") || path.contains("manim/traces"))

                                isVideoFile && isInMonitoredDir
                            } else {
                                false
                            }
                        }

                        if (hasNewVideo) {
                            // Refresh UI on EDT
                            ApplicationManager.getApplication().invokeLater {
                                PluginLogger.info("New Manim video detected - auto-refreshing list")
                                scanForVideos()
                            }
                        }
                    }
                }
            )

            PluginLogger.info("File watcher enabled for Manim videos")
        } catch (e: Exception) {
            PluginLogger.error("Failed to setup file watcher", e)
        }
    }

    override fun dispose() {
        fileWatcherConnection?.disconnect()
        jsQuery?.dispose()
        interactiveBrowser?.dispose()
        // Stop live server if running
        explorerServer?.stop()
        explorerServer = null
    }

    private fun createUI() {
        // Create tabbed pane with two views
        val tabbedPane = JBTabbedPane()

        // Tab 1: Interactive Explorer (default tab - Three.js visualization)
        val interactivePanel = createInteractiveExplorerPanel()
        tabbedPane.addTab("Interactive Explorer", interactivePanel)

        // Tab 2: Video List
        val videoListPanel = createVideoListPanel()
        tabbedPane.addTab("Video List", videoListPanel)

        add(tabbedPane, BorderLayout.CENTER)

        // Listen for tab changes to load data when Interactive Explorer is selected
        tabbedPane.addChangeListener { e ->
            if (tabbedPane.selectedIndex == 0) {
                // Interactive Explorer tab selected - refresh visualization
                refreshInteractiveVisualization()
            }
        }

        // Load Interactive Explorer data on startup
        refreshInteractiveVisualization()
    }

    /**
     * Creates the Video List panel (existing functionality).
     */
    private fun createVideoListPanel(): JPanel {
        val panel = JBPanel<JBPanel<*>>(BorderLayout())
        panel.border = JBUI.Borders.empty(10)

        // Top: Status and refresh button
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
        topPanel.add(statusLabel, BorderLayout.WEST)

        val refreshButton = JButton("Refresh")
        refreshButton.addActionListener { scanForVideos() }
        topPanel.add(refreshButton, BorderLayout.EAST)

        panel.add(topPanel, BorderLayout.NORTH)

        // Left: Video list
        videoList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        videoList.addListSelectionListener { updateInfoPanel() }

        // Add double-click listener to play video
        videoList.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) {
                    val selectedVideo = videoList.selectedValue
                    if (selectedVideo != null) {
                        openVideoInSystemPlayer(selectedVideo.file)
                    }
                }
            }
        })

        val listScrollPane = JBScrollPane(videoList)
        listScrollPane.preferredSize = JBUI.size(300, 400)

        // Right: Video info and controls
        updateInfoPanel()
        val infoScrollPane = JBScrollPane(infoPanel)

        // Split pane
        val splitPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, listScrollPane, infoScrollPane)
        splitPane.resizeWeight = 0.4
        panel.add(splitPane, BorderLayout.CENTER)

        // Bottom: Instructions
        val instructions = JBLabel("<html>Manim animations are generated every 5 seconds when trace data is received.<br>" +
                "<b>Double-click</b> a video to play, or select and press 'Play' button.</html>")
        instructions.border = JBUI.Borders.empty(10, 0, 0, 0)
        panel.add(instructions, BorderLayout.SOUTH)

        return panel
    }

    /**
     * Creates the Interactive Explorer panel with JCEF browser for Three.js visualization.
     */
    private fun createInteractiveExplorerPanel(): JPanel {
        val panel = JBPanel<JBPanel<*>>(BorderLayout())
        panel.border = JBUI.Borders.empty(5)

        // Check if JCEF is supported
        if (!JBCefApp.isSupported()) {
            val errorLabel = JBLabel("<html><center>Interactive Explorer requires JCEF support.<br>" +
                    "Please use a JetBrains Runtime with JCEF enabled.</center></html>")
            errorLabel.horizontalAlignment = SwingConstants.CENTER
            panel.add(errorLabel, BorderLayout.CENTER)
            return panel
        }

        try {
            // Create JCEF browser
            interactiveBrowser = JBCefBrowser()

            // Add load handler to detect when page is ready
            val cefBrowser = interactiveBrowser?.cefBrowser
            if (cefBrowser != null) {
                interactiveBrowser?.jbCefClient?.addLoadHandler(object : org.cef.handler.CefLoadHandlerAdapter() {
                    override fun onLoadEnd(browser: org.cef.browser.CefBrowser?, frame: org.cef.browser.CefFrame?, httpStatusCode: Int) {
                        if (frame?.isMain == true) {
                            browserPageReady = true
                            PluginLogger.info("Interactive Explorer page loaded, ready for data (mode: $currentViewMode)")

                            // Inject the cefQuery function for JS to Kotlin communication
                            injectCefQuery()

                            // If we have pending data, send it now based on current view mode
                            if (pendingDataRefresh || visualizationData != null) {
                                pendingDataRefresh = false
                                ApplicationManager.getApplication().invokeLater {
                                    when (currentViewMode) {
                                        ViewMode.FLOW_EXPLORER -> refreshInteractiveVisualization()
                                        ViewMode.WATCH_ARCHITECTURE -> sendDataToWatchArchitecture()
                                    }
                                }
                            }
                        }
                    }

                    override fun onLoadStart(browser: org.cef.browser.CefBrowser?, frame: org.cef.browser.CefFrame?, transitionType: org.cef.network.CefRequest.TransitionType?) {
                        if (frame?.isMain == true) {
                            browserPageReady = false
                        }
                    }
                }, cefBrowser)
            }

            // Load the Three.js visualization HTML from resources
            val htmlContent = loadInteractiveHtml()
            interactiveBrowser?.loadHTML(htmlContent)

            // Setup JS query for communication from JS to Kotlin
            jsQuery = JBCefJSQuery.create(interactiveBrowser as JBCefBrowserBase)
            jsQuery?.addHandler { request ->
                handleJsCallback(request)
                JBCefJSQuery.Response("ok")
            }

            // Top: Toolbar with buttons
            val topPanel = JBPanel<JBPanel<*>>(BorderLayout())

            // Right side: buttons
            val buttonsPanel = JBPanel<JBPanel<*>>(FlowLayout(FlowLayout.RIGHT, 5, 0))

            // View toggle button (Flow Explorer ↔ Watch Architecture)
            viewToggleButton = JButton("📹 Watch Architecture")
            viewToggleButton?.toolTipText = "Switch to Watch Architecture view for real-time data flow visualization"
            viewToggleButton?.addActionListener { toggleViewMode() }
            buttonsPanel.add(viewToggleButton)

            val refreshBtn = JButton("🔄 Refresh")
            refreshBtn.addActionListener { refreshInteractiveVisualization() }
            buttonsPanel.add(refreshBtn)

            // Open in Browser button - serves live HTML with real-time updates
            liveServerButton = JButton("🌐 Open in Browser")
            liveServerButton?.toolTipText = "Open visualization in browser with real-time updates"
            liveServerButton?.addActionListener { toggleLiveServer() }
            buttonsPanel.add(liveServerButton)

            // Snapshot export button (static HTML file)
            val exportSnapshotBtn = JButton("📸 Export Snapshot")
            exportSnapshotBtn.toolTipText = "Export current visualization as static HTML file"
            exportSnapshotBtn.addActionListener { exportSnapshot() }
            buttonsPanel.add(exportSnapshotBtn)

            topPanel.add(buttonsPanel, BorderLayout.EAST)

            val infoLabel = JBLabel("<html>Interactive 3D visualization of code execution. " +
                    "<b>Red</b> = not executed, <b>Green</b> = executed, <b>Yellow</b> = partial. Click nodes for details.</html>")
            topPanel.add(infoLabel, BorderLayout.WEST)
            panel.add(topPanel, BorderLayout.NORTH)

            // Browser component
            panel.add(interactiveBrowser!!.component, BorderLayout.CENTER)

        } catch (e: Exception) {
            PluginLogger.error("Failed to create Interactive Explorer", e)
            val errorLabel = JBLabel("<html><center>Failed to initialize Interactive Explorer:<br>${e.message}</center></html>")
            errorLabel.horizontalAlignment = SwingConstants.CENTER
            panel.add(errorLabel, BorderLayout.CENTER)
        }

        return panel
    }

    /**
     * Loads the Three.js visualization HTML from resources.
     */
    private fun loadInteractiveHtml(): String {
        return try {
            val inputStream = javaClass.getResourceAsStream("/interactive_viz/interactive_flow_explorer.html")
            inputStream?.bufferedReader()?.readText() ?: getDefaultInteractiveHtml()
        } catch (e: Exception) {
            PluginLogger.error("Failed to load interactive HTML from resources", e)
            getDefaultInteractiveHtml()
        }
    }

    /**
     * Loads the Watch Architecture HTML from resources.
     */
    private fun loadWatchArchitectureHtml(): String {
        return try {
            val inputStream = javaClass.getResourceAsStream("/interactive_viz/watch_architecture.html")
            inputStream?.bufferedReader()?.readText() ?: "<html><body>Watch Architecture not found</body></html>"
        } catch (e: Exception) {
            PluginLogger.error("Failed to load Watch Architecture HTML from resources", e)
            "<html><body>Failed to load Watch Architecture</body></html>"
        }
    }

    /**
     * Toggles between Flow Explorer and Watch Architecture views.
     */
    private fun toggleViewMode() {
        currentViewMode = when (currentViewMode) {
            ViewMode.FLOW_EXPLORER -> ViewMode.WATCH_ARCHITECTURE
            ViewMode.WATCH_ARCHITECTURE -> ViewMode.FLOW_EXPLORER
        }

        // Update button text
        viewToggleButton?.text = when (currentViewMode) {
            ViewMode.FLOW_EXPLORER -> "📹 Watch Architecture"
            ViewMode.WATCH_ARCHITECTURE -> "🔍 Flow Explorer"
        }

        // Load the appropriate HTML
        val htmlContent = when (currentViewMode) {
            ViewMode.FLOW_EXPLORER -> loadInteractiveHtml()
            ViewMode.WATCH_ARCHITECTURE -> loadWatchArchitectureHtml()
        }

        // Mark page as not ready - the load handler will refresh when ready
        browserPageReady = false
        pendingDataRefresh = true  // Flag to send data when page loads

        interactiveBrowser?.loadHTML(htmlContent)

        // The load handler (onLoadEnd) will automatically:
        // - For Flow Explorer: call refreshInteractiveVisualization() when page is ready
        // - For Watch Architecture: we still need to send data after load
        if (currentViewMode == ViewMode.WATCH_ARCHITECTURE) {
            // Use a slight delay to ensure the page is loaded
            ApplicationManager.getApplication().invokeLater {
                Thread.sleep(500)
                sendDataToWatchArchitecture()
            }
        }
        // For Flow Explorer, the onLoadEnd handler will call refreshInteractiveVisualization()
    }

    /**
     * Sends visualization data to Watch Architecture view.
     * Uses resolvedCallGraph for complete static analysis including cross-class connections.
     */
    private fun sendDataToWatchArchitecture() {
        if (interactiveBrowser == null || visualizationData == null) return

        try {
            // Use resolved call graph for complete picture, fallback to runtime call graph
            val completeCallGraph = if (visualizationData!!.resolvedCallGraph.isNotEmpty()) {
                visualizationData!!.resolvedCallGraph
            } else {
                visualizationData!!.callGraph
            }

            val jsonData = gson.toJson(mapOf(
                "functions" to visualizationData!!.functions.mapValues { (funcName, info) ->
                    mapOf(
                        "name" to funcName,
                        "line" to info.line,
                        "file" to info.file,
                        "call_count" to info.callCount,
                        "branches" to info.branches.map { branch ->
                            mapOf("type" to branch.type, "condition" to branch.condition)
                        }
                    )
                },
                "call_graph" to completeCallGraph,
                "resolved_call_graph" to visualizationData!!.resolvedCallGraph,
                "runtime_call_graph" to visualizationData!!.callGraph,
                "covered_functions" to visualizationData!!.coveredFunctions,
                "dead_functions" to visualizationData!!.deadFunctions,
                // Build complete data flows from resolved call graph (static analysis)
                "data_flows" to completeCallGraph.flatMap { (caller, callees) ->
                    callees.map { callee ->
                        val isExecuted = visualizationData!!.coveredFunctions.contains(caller) &&
                                        visualizationData!!.coveredFunctions.contains(callee)
                        mapOf(
                            "from" to caller,
                            "to" to callee,
                            "type" to if (isExecuted) "executed_call" else "potential_call",
                            "executed" to isExecuted
                        )
                    }
                },
                // Add why_not_covered for dead code explanation
                "why_not_covered" to visualizationData!!.whyNotCovered.mapValues { (_, info) ->
                    mapOf(
                        "function" to info.function,
                        "root_cause" to info.rootCause
                    )
                }
            ))

            ApplicationManager.getApplication().invokeLater {
                interactiveBrowser?.cefBrowser?.executeJavaScript(
                    "if (typeof loadWatchData === 'function') { loadWatchData($jsonData); }",
                    "", 0
                )
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to send data to Watch Architecture", e)
        }
    }

    /**
     * Exports the current visualization as a static HTML snapshot file.
     */
    private fun exportSnapshot() {
        try {
            // Load the HTML template
            val htmlTemplate = loadInteractiveHtml()

            // Build data JSON with full data for re-rendering
            val data = if (visualizationData != null) {
                mapOf(
                    "functions" to visualizationData!!.functions.mapValues { (_, info) ->
                        mapOf(
                            "name" to info.name,
                            "line" to info.line,
                            "file" to info.file,
                            "call_count" to info.callCount,
                            "branches" to info.branches.map { branch ->
                                mapOf(
                                    "type" to branch.type,
                                    "line" to branch.line,
                                    "condition" to branch.condition
                                )
                            }
                        )
                    },
                    "call_graph" to visualizationData!!.callGraph,
                    "resolved_call_graph" to visualizationData!!.resolvedCallGraph,
                    "covered_functions" to visualizationData!!.coveredFunctions,
                    "dead_functions" to visualizationData!!.deadFunctions,
                    "why_not_covered" to visualizationData!!.whyNotCovered.mapValues { (_, info) ->
                        mapOf(
                            "function" to info.function,
                            "root_cause" to info.rootCause,
                            "root_cause_detail" to (info.rootCauseDetail?.let { detail ->
                                mapOf(
                                    "type" to detail.type,
                                    "caller" to detail.caller,
                                    "line" to detail.line,
                                    "branch_type" to detail.branchType,
                                    "branch_condition" to detail.branchCondition,
                                    "branch_line" to detail.branchLine
                                )
                            }),
                            "reasons" to info.reasons.map { reason ->
                                mapOf(
                                    "type" to reason.type,
                                    "caller" to reason.caller,
                                    "line" to reason.line,
                                    "branch_type" to reason.branchType,
                                    "branch_condition" to reason.branchCondition,
                                    "explanation" to reason.explanation
                                )
                            },
                            "call_chain" to emptyList<String>()  // Will be populated by client
                        )
                    }
                )
            } else {
                emptyMap<String, Any>()
            }

            val jsonData = gson.toJson(data)

            // Inject data and auto-load script
            val dataScript = "<script>window.TRUEFLOW_DATA = $jsonData;</script>"
            val autoLoadScript = """<script>
                document.addEventListener('DOMContentLoaded', function() {
                    if (window.TRUEFLOW_DATA && typeof loadVisualizationData === 'function') {
                        setTimeout(function() { loadVisualizationData(window.TRUEFLOW_DATA); }, 500);
                    }
                });
            </script>"""

            var modifiedHtml = htmlTemplate.replace("</head>", "$dataScript</head>")
            modifiedHtml = modifiedHtml.replace("</body>", "$autoLoadScript</body>")

            // Write to temp file
            val tempDir = java.io.File(System.getProperty("java.io.tmpdir"), "trueflow")
            tempDir.mkdirs()
            val tempFile = java.io.File(tempDir, "interactive_explorer_${System.currentTimeMillis()}.html")
            tempFile.writeText(modifiedHtml)

            // Open in default browser
            java.awt.Desktop.getDesktop().browse(tempFile.toURI())
            PluginLogger.info("Opened Interactive Explorer in browser: ${tempFile.absolutePath}")

        } catch (e: Exception) {
            PluginLogger.error("Failed to open explorer in browser", e)
        }
    }

    /**
     * Toggles the live server on/off for real-time browser viewing.
     */
    private fun toggleLiveServer() {
        if (explorerServer?.isRunning() == true) {
            stopLiveServer()
        } else {
            startLiveServer()
        }
    }

    /**
     * Starts the live server and opens browser.
     */
    private fun startLiveServer() {
        try {
            explorerServer = InteractiveExplorerServer(
                port = 8765,
                onServerStarted = { url ->
                    SwingUtilities.invokeLater {
                        updateLiveServerButton(true, url)
                        // Open browser automatically
                        try {
                            Desktop.getDesktop().browse(java.net.URI(url))
                        } catch (e: Exception) {
                            PluginLogger.warn("Could not open browser: ${e.message}")
                        }
                    }
                },
                onServerStopped = {
                    SwingUtilities.invokeLater {
                        updateLiveServerButton(false, null)
                    }
                },
                onError = { e ->
                    SwingUtilities.invokeLater {
                        updateLiveServerButton(false, null)
                        JOptionPane.showMessageDialog(
                            this,
                            "Failed to start server: ${e.message}\n\nPort 8765 may already be in use.",
                            "Server Error",
                            JOptionPane.ERROR_MESSAGE
                        )
                    }
                }
            )

            if (explorerServer?.start() == true) {
                // Push current data if available
                pushCurrentDataToServer()
            }

        } catch (e: Exception) {
            PluginLogger.error("Failed to start live server", e)
            updateLiveServerButton(false, null)
        }
    }

    /**
     * Stops the live server.
     */
    private fun stopLiveServer() {
        explorerServer?.stop()
        explorerServer = null
        updateLiveServerButton(false, null)
    }

    /**
     * Updates the browser button appearance.
     */
    private fun updateLiveServerButton(isRunning: Boolean, url: String?) {
        liveServerButton?.apply {
            if (isRunning && url != null) {
                text = "✕ Close Browser"
                toolTipText = "Live at $url - Click to close"
                background = java.awt.Color(76, 175, 80) // Green (active)
                foreground = java.awt.Color.WHITE
                isOpaque = true
                isContentAreaFilled = true
            } else {
                text = "🌐 Open in Browser"
                toolTipText = "Open visualization in browser with real-time updates"
                background = null
                foreground = null
                isOpaque = false
                isContentAreaFilled = true
            }
            repaint()
        }
    }

    /**
     * Builds the data map for the server from current visualization data.
     */
    private fun buildServerDataMap(): Map<String, Any> {
        return if (visualizationData != null) {
            mapOf(
                "functions" to visualizationData!!.functions.mapValues { (_, info) ->
                    mapOf(
                        "name" to info.name,
                        "line" to info.line,
                        "file" to info.file,
                        "call_count" to info.callCount,
                        "branches" to info.branches.map { branch ->
                            mapOf(
                                "type" to branch.type,
                                "line" to branch.line,
                                "condition" to branch.condition
                            )
                        }
                    )
                },
                "call_graph" to visualizationData!!.callGraph,
                "resolved_call_graph" to visualizationData!!.resolvedCallGraph,
                "covered_functions" to visualizationData!!.coveredFunctions,
                "dead_functions" to visualizationData!!.deadFunctions,
                "why_not_covered" to visualizationData!!.whyNotCovered.mapValues { (_, info) ->
                    mapOf(
                        "function" to info.function,
                        "root_cause" to info.rootCause,
                        "root_cause_detail" to (info.rootCauseDetail?.let { detail ->
                            mapOf(
                                "type" to detail.type,
                                "caller" to detail.caller,
                                "line" to detail.line,
                                "branch_type" to detail.branchType,
                                "branch_condition" to detail.branchCondition,
                                "branch_line" to detail.branchLine
                            )
                        }),
                        "reasons" to info.reasons.map { reason ->
                            mapOf(
                                "type" to reason.type,
                                "caller" to reason.caller,
                                "line" to reason.line,
                                "branch_type" to reason.branchType,
                                "branch_condition" to reason.branchCondition,
                                "explanation" to reason.explanation
                            )
                        },
                        "call_chain" to emptyList<String>()
                    )
                },
                "timestamp" to System.currentTimeMillis()
            )
        } else {
            mapOf("timestamp" to System.currentTimeMillis())
        }
    }

    /**
     * Pushes current visualization data to the live server (if running).
     */
    private fun pushCurrentDataToServer() {
        if (explorerServer?.isRunning() == true) {
            val data = buildServerDataMap()
            explorerServer?.pushTraceData(data)
            PluginLogger.debug("Pushed trace data to live server")
        }
    }

    /**
     * Default HTML if resource loading fails.
     */
    private fun getDefaultInteractiveHtml(): String {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {
                        font-family: sans-serif;
                        background: #1a1a2e;
                        color: #eee;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .message { text-align: center; }
                </style>
            </head>
            <body>
                <div class="message">
                    <h2>Interactive Explorer</h2>
                    <p>Run your code to generate visualization data.</p>
                    <p>The visualization will appear here showing executed and dead branches.</p>
                </div>
            </body>
            </html>
        """.trimIndent()
    }

    /**
     * Handles callbacks from JavaScript.
     */
    private fun handleJsCallback(request: String) {
        try {
            val json = gson.fromJson(request, JsonObject::class.java)
            val action = json.get("action")?.asString

            when (action) {
                "navigate" -> {
                    // Navigate to file:line in editor
                    val file = json.get("file")?.asString
                    val line = json.get("line")?.asInt ?: 0
                    if (file != null) {
                        navigateToSource(file, line)
                    }
                }
                "log" -> {
                    val message = json.get("message")?.asString
                    PluginLogger.info("[InteractiveExplorer] $message")
                }
                "explain" -> {
                    // Request AI explanation for a function
                    val funcName = json.get("function")?.asString
                    val funcFile = json.get("file")?.asString
                    val funcLine = json.get("line")?.asInt ?: 0
                    val isAlive = json.get("isAlive")?.asBoolean ?: false
                    val isDead = json.get("isDead")?.asBoolean ?: false
                    val callCount = json.get("callCount")?.asInt ?: 0
                    val whyNotCovered = json.get("whyNotCovered")?.asString

                    if (funcName != null) {
                        handleExplainRequest(funcName, funcFile, funcLine, isAlive, isDead, callCount, whyNotCovered)
                    }
                }
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to handle JS callback", e)
        }
    }

    /**
     * Handles AI explanation request from Interactive Explorer.
     * Checks if LLM server is running and sends appropriate response.
     */
    private fun handleExplainRequest(
        funcName: String,
        funcFile: String?,
        funcLine: Int,
        isAlive: Boolean,
        isDead: Boolean,
        callCount: Int,
        whyNotCovered: String?
    ) {
        ApplicationManager.getApplication().invokeLater {
            // Check if LLM server is running by looking for AIExplanationPanel
            val toolWindowManager = com.intellij.openapi.wm.ToolWindowManager.getInstance(project)
            val toolWindow = toolWindowManager.getToolWindow("TrueFlow")

            // Try to find AIExplanationPanel and check server status
            val aiPanel = findAIExplanationPanel()
            val serverRunning = aiPanel?.isServerRunning() ?: false

            if (!serverRunning) {
                // Show prompt in Interactive Explorer to start server
                showLLMNotRunningMessage()
            } else {
                // Server is running, request explanation
                requestAIExplanation(funcName, funcFile, funcLine, isAlive, isDead, callCount, whyNotCovered, aiPanel!!)
            }
        }
    }

    /**
     * Find the AIExplanationPanel instance.
     */
    private fun findAIExplanationPanel(): AIExplanationPanel? {
        val toolWindowManager = com.intellij.openapi.wm.ToolWindowManager.getInstance(project)
        val toolWindow = toolWindowManager.getToolWindow("TrueFlow") ?: return null

        // The AIExplanationPanel is in the AI Explainer tab
        val content = toolWindow.contentManager.contents
        for (c in content) {
            val component = c.component
            if (component is javax.swing.JTabbedPane) {
                for (i in 0 until component.tabCount) {
                    val tabComponent = component.getComponentAt(i)
                    if (tabComponent is AIExplanationPanel) {
                        return tabComponent
                    }
                }
            }
        }
        return null
    }

    /**
     * Show message in Interactive Explorer that LLM server needs to be started.
     */
    private fun showLLMNotRunningMessage() {
        val message = """
            {
                "type": "llm_status",
                "status": "not_running",
                "message": "AI server is not running. Please go to 'AI Explainer' tab and click 'Start Server' to enable AI explanations."
            }
        """.trimIndent()

        interactiveBrowser?.cefBrowser?.executeJavaScript(
            "if (typeof handleLLMStatus === 'function') { handleLLMStatus($message); }",
            "", 0
        )
    }

    /**
     * Request AI explanation for a function.
     */
    private fun requestAIExplanation(
        funcName: String,
        funcFile: String?,
        funcLine: Int,
        isAlive: Boolean,
        isDead: Boolean,
        callCount: Int,
        whyNotCovered: String?,
        aiPanel: AIExplanationPanel
    ) {
        // Show loading state
        val loadingMessage = """
            {
                "type": "llm_status",
                "status": "loading",
                "message": "Asking AI to explain $funcName..."
            }
        """.trimIndent()

        interactiveBrowser?.cefBrowser?.executeJavaScript(
            "if (typeof handleLLMStatus === 'function') { handleLLMStatus($loadingMessage); }",
            "", 0
        )

        // Build context for the explanation
        val context = buildString {
            append("Function: $funcName\n")
            if (funcFile != null) append("File: $funcFile\n")
            if (funcLine > 0) append("Line: $funcLine\n")
            append("Status: ${if (isAlive) "Executed" else "Not Executed"}\n")
            if (callCount > 0) append("Call count: $callCount\n")
            if (isDead && whyNotCovered != null) {
                append("Why not covered: $whyNotCovered\n")
            }
        }

        // Use AIExplanationPanel's explain functionality
        java.util.concurrent.CompletableFuture.runAsync {
            try {
                // Read the function source code if file is available
                val sourceCode = if (funcFile != null && funcLine > 0) {
                    try {
                        val file = java.io.File(funcFile)
                        if (file.exists()) {
                            val lines = file.readLines()
                            val startLine = maxOf(0, funcLine - 1)
                            val endLine = minOf(lines.size, funcLine + 20)
                            lines.subList(startLine, endLine).joinToString("\n")
                        } else ""
                    } catch (e: Exception) { "" }
                } else ""

                val prompt = buildString {
                    append("Explain this function's purpose and behavior:\n\n")
                    append("Context:\n$context\n")
                    if (sourceCode.isNotEmpty()) {
                        append("\nSource code:\n```\n$sourceCode\n```\n")
                    }
                    append("\nProvide a concise explanation of what this function does.")
                    if (isDead) {
                        append(" Also explain why it might not be executed and suggest how to test it.")
                    }
                }

                // Call the LLM via AIExplanationPanel's askQuestion method
                aiPanel.askQuestion(prompt, sourceCode, null) { response ->
                    // Send response back to Interactive Explorer
                    val escapedResponse = response.replace("\\", "\\\\")
                        .replace("\"", "\\\"")
                        .replace("\n", "\\n")
                        .replace("\r", "")

                    val responseMessage = """
                        {
                            "type": "llm_response",
                            "function": "$funcName",
                            "explanation": "$escapedResponse"
                        }
                    """.trimIndent()

                    ApplicationManager.getApplication().invokeLater {
                        interactiveBrowser?.cefBrowser?.executeJavaScript(
                            "if (typeof handleLLMResponse === 'function') { handleLLMResponse($responseMessage); }",
                            "", 0
                        )
                    }
                }
            } catch (e: Exception) {
                PluginLogger.error("Failed to get AI explanation", e)
                val errorMessage = """
                    {
                        "type": "llm_status",
                        "status": "error",
                        "message": "Failed to get AI explanation: ${e.message?.replace("\"", "'")}"
                    }
                """.trimIndent()

                ApplicationManager.getApplication().invokeLater {
                    interactiveBrowser?.cefBrowser?.executeJavaScript(
                        "if (typeof handleLLMStatus === 'function') { handleLLMStatus($errorMessage); }",
                        "", 0
                    )
                }
            }
        }
    }

    /**
     * Inject the cefQuery function into JavaScript for JS to Kotlin communication.
     */
    private fun injectCefQuery() {
        if (jsQuery == null || interactiveBrowser == null) return

        val jsCode = jsQuery!!.inject("request",
            "window.cefQueryCallback",
            "(function(error_code, error_message) { console.error('cefQuery failed:', error_code, error_message); })"
        )

        // Wrap to create window.cefQuery function
        val wrappedJs = """
            window.cefQuery = function(params) {
                $jsCode
            };
            console.log('[Explorer] cefQuery function injected');
        """.trimIndent()

        interactiveBrowser?.cefBrowser?.executeJavaScript(wrappedJs, "", 0)
    }

    /**
     * Navigate to source file at line.
     */
    private fun navigateToSource(filePath: String, line: Int) {
        ApplicationManager.getApplication().invokeLater {
            try {
                val virtualFile = LocalFileSystem.getInstance().findFileByPath(filePath)
                if (virtualFile != null) {
                    com.intellij.openapi.fileEditor.OpenFileDescriptor(
                        project, virtualFile, line - 1, 0
                    ).navigate(true)
                }
            } catch (e: Exception) {
                PluginLogger.error("Failed to navigate to $filePath:$line", e)
            }
        }
    }

    /**
     * Refreshes the interactive visualization with current data.
     */
    fun refreshInteractiveVisualization() {
        if (interactiveBrowser == null) return

        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                // Build visualization data from current trace data
                val data = buildVisualizationData()
                val jsonData = gson.toJson(data)

                // Inject data into the browser
                ApplicationManager.getApplication().invokeLater {
                    interactiveBrowser?.cefBrowser?.executeJavaScript(
                        "if (typeof loadVisualizationData === 'function') { loadVisualizationData($jsonData); }",
                        "", 0
                    )
                }
            } catch (e: Exception) {
                PluginLogger.error("Failed to refresh interactive visualization", e)
            }
        }
    }

    /**
     * Builds visualization data from stored visualization data.
     * Returns the cached data from updateVisualizationData() calls.
     */
    private fun buildVisualizationData(): Map<String, Any> {
        // Return stored visualization data if available
        val data = visualizationData ?: return mapOf(
            "functions" to emptyMap<String, Any>(),
            "call_graph" to emptyMap<String, Any>(),
            "resolved_call_graph" to emptyMap<String, Any>(),
            "covered_functions" to emptyList<String>(),
            "dead_functions" to emptyList<String>(),
            "why_not_covered" to emptyMap<String, Any>()
        )

        // Convert stored FunctionInfo objects to proper map format
        return mapOf(
            "functions" to data.functions.mapValues { (funcName, info) ->
                mapOf(
                    "name" to funcName,
                    "line" to info.line,
                    "file" to (info.file ?: ""),
                    "call_count" to info.callCount,
                    "branches" to info.branches.map { branch ->
                        mapOf(
                            "type" to branch.type,
                            "line" to branch.line,
                            "condition" to branch.condition
                        )
                    }
                )
            },
            "call_graph" to data.callGraph,
            "resolved_call_graph" to data.resolvedCallGraph,
            "covered_functions" to data.coveredFunctions,
            "dead_functions" to data.deadFunctions,
            "why_not_covered" to data.whyNotCovered.mapValues { (_, info) ->
                mapOf(
                    "function" to info.function,
                    "root_cause" to info.rootCause,
                    "root_cause_detail" to (info.rootCauseDetail?.let { detail ->
                        mapOf(
                            "type" to detail.type,
                            "caller" to detail.caller,
                            "line" to detail.line,
                            "branch_type" to detail.branchType,
                            "branch_condition" to detail.branchCondition,
                            "branch_line" to detail.branchLine
                        )
                    }),
                    "reasons" to info.reasons.map { reason ->
                        mapOf(
                            "type" to reason.type,
                            "caller" to reason.caller,
                            "line" to reason.line,
                            "branch_type" to reason.branchType,
                            "branch_condition" to reason.branchCondition,
                            "explanation" to reason.explanation
                        )
                    }
                )
            }
        )
    }

    /**
     * Updates the visualization with data from the main tool window.
     * Called by EnhancedLearningFlowToolWindow when trace data changes.
     */
    fun updateVisualizationData(
        allFunctions: Set<String>,
        calledFunctions: Map<String, Int>,
        callTree: Map<String, List<String>>,
        functionDefinitions: Map<String, Pair<String, Int>>,  // func -> (file, line)
        whyNotCovered: Map<String, WhyNotCoveredInfo>,
        resolvedCallGraph: Map<String, List<String>> = emptyMap(),  // Static call graph for cross-class connections
        classInstantiationOrder: Map<String, Double> = emptyMap(),  // className -> first init timestamp (for ordering)
        functionFirstCalledTimestamp: Map<String, Double> = emptyMap()  // funcKey -> first call timestamp
    ) {
        val coveredFunctions = calledFunctions.keys.toList()
        val deadFunctions = allFunctions.filter { it !in calledFunctions.keys }

        val functions = allFunctions.associateWith { func ->
            val (file, line) = functionDefinitions[func] ?: ("" to 0)
            mapOf(
                "name" to func,
                "line" to line,
                "file" to file,
                "call_count" to (calledFunctions[func] ?: 0),
                "first_called" to (functionFirstCalledTimestamp[func]),  // When this function was first invoked
                "branches" to emptyList<Any>()  // Will be populated by branch analyzer
            )
        }

        // Store visualization data for Open in Browser and export functionality
        val functionInfoMap = allFunctions.associateWith { func ->
            val (file, line) = functionDefinitions[func] ?: ("" to 0)
            FunctionInfo(
                name = func,
                line = line,
                file = file,
                callCount = calledFunctions[func] ?: 0
            )
        }

        visualizationData = InteractiveVisualizationData(
            functions = functionInfoMap,
            callGraph = callTree,
            resolvedCallGraph = resolvedCallGraph,
            coveredFunctions = coveredFunctions,
            deadFunctions = deadFunctions,
            whyNotCovered = whyNotCovered
        )

        // Push to live server if running
        pushCurrentDataToServer()

        val data = mapOf(
            "functions" to functions,
            "call_graph" to callTree,
            "resolved_call_graph" to resolvedCallGraph,  // Include for cross-class static connections
            "covered_functions" to coveredFunctions,
            "dead_functions" to deadFunctions,
            "class_instantiation_order" to classInstantiationOrder,  // For ordering class containers by init time
            "why_not_covered" to whyNotCovered.mapValues { (_, info) ->
                mapOf(
                    "function" to info.function,
                    "root_cause" to info.rootCause,
                    "root_cause_detail" to (info.rootCauseDetail?.let { detail ->
                        mapOf(
                            "type" to detail.type,
                            "caller" to detail.caller,
                            "line" to detail.line,
                            "branch_type" to detail.branchType,
                            "branch_condition" to detail.branchCondition,
                            "branch_line" to detail.branchLine
                        )
                    }),
                    "reasons" to info.reasons.map { reason ->
                        mapOf(
                            "type" to reason.type,
                            "caller" to reason.caller,
                            "line" to reason.line,
                            "branch_type" to reason.branchType,
                            "branch_condition" to reason.branchCondition,
                            "explanation" to reason.explanation
                        )
                    }
                )
            }
        )

        val jsonData = gson.toJson(data)

        // Log what we're sending to help debug data flow
        PluginLogger.info("[ManimVideoPanel] Sending to Interactive Explorer:")
        PluginLogger.info("[ManimVideoPanel]   allFunctions.size: ${allFunctions.size}")
        PluginLogger.info("[ManimVideoPanel]   calledFunctions.size: ${calledFunctions.size}")
        PluginLogger.info("[ManimVideoPanel]   coveredFunctions.size: ${coveredFunctions.size}")
        PluginLogger.info("[ManimVideoPanel]   deadFunctions.size: ${deadFunctions.size}")
        PluginLogger.info("[ManimVideoPanel]   callTree.size: ${callTree.size}")
        if (allFunctions.isNotEmpty()) {
            PluginLogger.info("[ManimVideoPanel]   Sample allFunctions: ${allFunctions.take(3)}")
        }
        if (calledFunctions.isNotEmpty()) {
            PluginLogger.info("[ManimVideoPanel]   Sample calledFunctions: ${calledFunctions.keys.take(3)}")
        }

        ApplicationManager.getApplication().invokeLater {
            interactiveBrowser?.cefBrowser?.executeJavaScript(
                "if (typeof loadVisualizationData === 'function') { loadVisualizationData($jsonData); }",
                "", 0
            )
        }
    }

    private fun updateInfoPanel() {
        infoPanel.removeAll()

        val selectedVideo = videoList.selectedValue
        if (selectedVideo == null) {
            val gbc = GridBagConstraints()
            gbc.gridx = 0
            gbc.gridy = 0
            gbc.anchor = GridBagConstraints.CENTER
            infoPanel.add(JBLabel("Select a video to see details"), gbc)
            infoPanel.revalidate()
            infoPanel.repaint()
            return
        }

        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = GridBagConstraints.RELATIVE
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = JBUI.insets(5)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0

        // Video info
        infoPanel.add(createBoldLabel("Video Information"), gbc)
        infoPanel.add(JBLabel("File: ${selectedVideo.name}"), gbc)
        infoPanel.add(JBLabel("Size: ${selectedVideo.size / 1024} KB"), gbc)
        infoPanel.add(JBLabel("Created: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(selectedVideo.timestamp)}"), gbc)
        infoPanel.add(JBLabel("Path: ${selectedVideo.file.absolutePath}"), gbc)

        // Spacer
        gbc.gridy++
        gbc.insets = JBUI.insets(20, 5, 5, 5)
        infoPanel.add(Box.createVerticalStrut(10), gbc)

        // Play button
        gbc.insets = JBUI.insets(5)
        val playButton = JButton("Play in External Player")
        playButton.addActionListener {
            openVideoInSystemPlayer(selectedVideo.file)
        }
        infoPanel.add(playButton, gbc)

        // Open folder button
        val openFolderButton = JButton("Open Containing Folder")
        openFolderButton.addActionListener {
            openFileInExplorer(selectedVideo.file.parentFile)
        }
        infoPanel.add(openFolderButton, gbc)

        // Delete button
        val deleteButton = JButton("Delete Video")
        deleteButton.addActionListener {
            if (JOptionPane.showConfirmDialog(
                    this,
                    "Are you sure you want to delete this video?",
                    "Delete Video",
                    JOptionPane.YES_NO_OPTION
                ) == JOptionPane.YES_OPTION
            ) {
                selectedVideo.file.delete()
                scanForVideos()
            }
        }
        infoPanel.add(deleteButton, gbc)

        infoPanel.revalidate()
        infoPanel.repaint()
    }

    private fun createBoldLabel(text: String): JBLabel {
        val label = JBLabel(text)
        val font = label.font
        label.font = font.deriveFont(font.style or java.awt.Font.BOLD, font.size + 2f)
        return label
    }

    private fun scanForVideos() {
        videoListModel.clear()

        val videoFiles = mutableListOf<File>()

        // Scan manim output directory (recursive to catch all subdirectories)
        // IMPORTANT: Filter out partial_movie_files - these are Manim's internal rendering fragments
        // Only show complete videos (those NOT in partial_movie_files directories)
        // Complete videos are named: video_${correlationId}_${pathHash}.mp4 or SceneName.mp4
        if (manimOutputDir.exists()) {
            manimOutputDir.walkTopDown()
                .filter { file ->
                    file.isFile &&
                    file.extension.lowercase() in listOf("mp4", "mov", "avi", "webm") &&
                    !file.absolutePath.contains("partial_movie_files") // Exclude Manim internal fragments
                }
                .forEach { videoFiles.add(it) }
        }

        // Also scan manim_traces directory for any videos
        val tracesDir = PluginPaths.getManimTracesDir(project)
        if (tracesDir.exists()) {
            tracesDir.walkTopDown()
                .filter { file ->
                    file.isFile &&
                    file.extension.lowercase() in listOf("mp4", "mov", "avi", "webm") &&
                    !file.absolutePath.contains("partial_movie_files") // Exclude Manim internal fragments
                }
                .forEach { videoFiles.add(it) }
        }

        // Sort by modification time (newest first)
        videoFiles.sortByDescending { it.lastModified() }

        // Add to list model
        videoFiles.forEach { file ->
            val videoInfo = VideoInfo(
                file = file,
                timestamp = Date(file.lastModified()),
                name = file.name,
                size = file.length()
            )
            videoListModel.addElement(videoInfo)
        }

        // Update status
        statusLabel.text = "Found ${videoFiles.size} video(s)"

        if (videoFiles.isEmpty()) {
            PluginLogger.info("No Manim videos found. Videos will appear here when generated.")
        } else {
            PluginLogger.info("Found ${videoFiles.size} Manim videos")
        }
    }

    private fun openVideoInSystemPlayer(file: File) {
        try {
            if (Desktop.isDesktopSupported()) {
                Desktop.getDesktop().open(file)
                PluginLogger.info("Opened video in system player: ${file.name}")
            } else {
                JOptionPane.showMessageDialog(
                    this,
                    "Desktop operations not supported on this platform.\nVideo location: ${file.absolutePath}",
                    "Cannot Open Video",
                    JOptionPane.WARNING_MESSAGE
                )
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to open video: ${file.name}", e)
            JOptionPane.showMessageDialog(
                this,
                "Failed to open video: ${e.message}\nVideo location: ${file.absolutePath}",
                "Error",
                JOptionPane.ERROR_MESSAGE
            )
        }
    }

    private fun openFileInExplorer(directory: File) {
        try {
            if (Desktop.isDesktopSupported()) {
                Desktop.getDesktop().open(directory)
                PluginLogger.info("Opened folder: ${directory.absolutePath}")
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to open folder: ${directory.absolutePath}", e)
        }
    }

    /**
     * Auto-refresh when new videos are detected.
     * Call this from file watcher or periodically.
     */
    fun refresh() {
        scanForVideos()
    }
}
