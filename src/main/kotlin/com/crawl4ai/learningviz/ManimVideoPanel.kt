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

    // Data for interactive visualization
    private var visualizationData: InteractiveVisualizationData? = null

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
    }

    private fun createUI() {
        // Create tabbed pane with two views
        val tabbedPane = JBTabbedPane()

        // Tab 1: Video List (existing functionality)
        val videoListPanel = createVideoListPanel()
        tabbedPane.addTab("Video List", videoListPanel)

        // Tab 2: Interactive Explorer (new Three.js visualization)
        val interactivePanel = createInteractiveExplorerPanel()
        tabbedPane.addTab("Interactive Explorer", interactivePanel)

        add(tabbedPane, BorderLayout.CENTER)

        // Listen for tab changes to load data when Interactive Explorer is selected
        tabbedPane.addChangeListener { e ->
            if (tabbedPane.selectedIndex == 1) {
                // Interactive Explorer tab selected - refresh visualization
                refreshInteractiveVisualization()
            }
        }
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

            // Load the Three.js visualization HTML from resources
            val htmlContent = loadInteractiveHtml()
            interactiveBrowser?.loadHTML(htmlContent)

            // Setup JS query for communication from JS to Kotlin
            jsQuery = JBCefJSQuery.create(interactiveBrowser as JBCefBrowserBase)
            jsQuery?.addHandler { request ->
                handleJsCallback(request)
                JBCefJSQuery.Response("ok")
            }

            // Top: Refresh button
            val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
            val refreshBtn = JButton("Refresh Visualization")
            refreshBtn.addActionListener { refreshInteractiveVisualization() }
            topPanel.add(refreshBtn, BorderLayout.EAST)

            val infoLabel = JBLabel("<html>Interactive 3D visualization of code execution. " +
                    "<b>Red</b> = not executed, <b>Green</b> = executed. Click nodes for details.</html>")
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
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to handle JS callback", e)
        }
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
     * Builds visualization data from current trace and dead code analysis.
     * This combines data from the Dead Code tab and Call Tree tab.
     */
    private fun buildVisualizationData(): Map<String, Any> {
        // This will be populated by the EnhancedLearningFlowToolWindow
        // For now, return demo data structure
        return mapOf(
            "functions" to emptyMap<String, Any>(),
            "call_graph" to emptyMap<String, Any>(),
            "covered_functions" to emptyList<String>(),
            "dead_functions" to emptyList<String>(),
            "why_not_covered" to emptyMap<String, Any>()
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
        whyNotCovered: Map<String, WhyNotCoveredInfo>
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
                "branches" to emptyList<Any>()  // Will be populated by branch analyzer
            )
        }

        val data = mapOf(
            "functions" to functions,
            "call_graph" to callTree,
            "covered_functions" to coveredFunctions,
            "dead_functions" to deadFunctions,
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
