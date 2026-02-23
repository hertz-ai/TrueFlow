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
    @Volatile private var browserPageReady = false
    @Volatile private var pendingDataRefresh = false

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

    // ==================== AUTO-EXPLAIN CACHE SYSTEM ====================

    /**
     * Cached AI explanation for a dead function.
     * Keyed by function signature + content hash for invalidation.
     */
    data class CachedExplanation(
        val functionName: String,
        val filePath: String,
        val line: Int,
        val contentHash: String,  // Hash of function source for cache invalidation
        val whyNotCovered: String,  // Root cause type
        val explanation: String,  // AI-generated explanation
        val timestamp: Long,  // When this was generated
        val modelUsed: String = "unknown"  // Which model generated this
    )

    /**
     * Cache manager for auto-explain functionality.
     * Stores explanations persistently and manages background processing.
     */
    private inner class ExplanationCacheManager {
        private val cache = mutableMapOf<String, CachedExplanation>()
        private val cacheFile = File(PluginPaths.getPluginRoot(project), "explanation_cache.json")
        private val pendingQueue = java.util.concurrent.ConcurrentLinkedQueue<String>()  // Function names to explain
        private val priorityFunctions = java.util.concurrent.ConcurrentHashMap<String, Long>()  // funcName -> priority timestamp
        private var isProcessing = false
        private var lastUserRequestTime = System.currentTimeMillis()
        private val idleThresholdMs = 5000L  // 5 seconds of idle before auto-processing
        private var backgroundWorker: java.util.concurrent.ScheduledExecutorService? = null
        private var isShutdown = false

        init {
            loadCache()
            startBackgroundWorker()
        }

        fun getCacheKey(funcName: String, filePath: String): String {
            return "$funcName@$filePath"
        }

        fun getExplanation(funcName: String, filePath: String): CachedExplanation? {
            val key = getCacheKey(funcName, filePath)
            return cache[key]
        }

        fun hasValidExplanation(funcName: String, filePath: String, contentHash: String): Boolean {
            val cached = getExplanation(funcName, filePath)
            return cached != null && cached.contentHash == contentHash
        }

        fun storeExplanation(explanation: CachedExplanation) {
            val key = getCacheKey(explanation.functionName, explanation.filePath)
            cache[key] = explanation
            saveCache()

            // Notify Interactive Explorer of the cached explanation
            notifyExplorerOfCachedExplanation(explanation)
        }

        fun markUserActivity() {
            lastUserRequestTime = System.currentTimeMillis()
        }

        fun isIdle(): Boolean {
            return System.currentTimeMillis() - lastUserRequestTime > idleThresholdMs
        }

        /**
         * Prioritize a function for explanation (user searched or focused on it).
         * These get processed before regular queue items.
         */
        fun prioritizeFunction(funcName: String, reason: String = "user_interaction") {
            // Add to priority map with current timestamp (higher = more recent = higher priority)
            priorityFunctions[funcName] = System.currentTimeMillis()

            // Also ensure it's in the pending queue
            if (!pendingQueue.contains(funcName)) {
                pendingQueue.add(funcName)
            }
            PluginLogger.info("[AutoExplain] Prioritized: $funcName ($reason)")
        }

        /**
         * Prioritize multiple functions (e.g., search results).
         */
        fun prioritizeFunctions(funcNames: List<String>, reason: String = "search") {
            val timestamp = System.currentTimeMillis()
            funcNames.forEach { funcName ->
                priorityFunctions[funcName] = timestamp
                if (!pendingQueue.contains(funcName)) {
                    pendingQueue.add(funcName)
                }
            }
            if (funcNames.isNotEmpty()) {
                PluginLogger.info("[AutoExplain] Prioritized ${funcNames.size} functions ($reason)")
            }
        }

        fun queueForExplanation(funcName: String) {
            if (!pendingQueue.contains(funcName)) {
                pendingQueue.add(funcName)
                PluginLogger.info("[AutoExplain] Queued: $funcName (queue size: ${pendingQueue.size})")
            }
        }

        fun queueDeadFunctions(deadFunctions: List<String>) {
            deadFunctions.forEach { funcName ->
                val funcInfo = visualizationData?.functions?.get(funcName)
                val filePath = funcInfo?.file ?: ""
                val contentHash = computeContentHash(funcName, filePath, funcInfo?.line ?: 0)

                // Only queue if not already cached with valid hash
                if (!hasValidExplanation(funcName, filePath, contentHash)) {
                    queueForExplanation(funcName)
                }
            }
            PluginLogger.info("[AutoExplain] Queued ${pendingQueue.size} functions for auto-explanation")
        }

        /**
         * Compute a content hash that captures everything affecting the explanation:
         * 1. Source code of the function
         * 2. Coverage status (dead/alive)
         * 3. Callers (who calls this function)
         * 4. Callees (what this function calls)
         * 5. whyNotCovered reason
         *
         * Cache is invalidated when any of these change.
         */
        private fun computeContentHash(funcName: String, filePath: String, line: Int): String {
            val data = visualizationData ?: return "no_data"
            if (filePath.isEmpty() || line <= 0) return "unknown"

            try {
                val sb = StringBuilder()

                // 1. Source code hash
                val file = File(filePath)
                if (file.exists()) {
                    val lines = file.readLines()
                    val startIdx = maxOf(0, line - 1)
                    val endIdx = minOf(lines.size, line + 50)
                    val sourceCode = lines.subList(startIdx, endIdx).joinToString("\n")
                    sb.append("src:${sourceCode.hashCode()};")
                }

                // 2. Coverage status (dead/alive)
                val isAlive = data.coveredFunctions?.contains(funcName) == true
                sb.append("alive:$isAlive;")

                // 3. Callers (sorted for consistent hash)
                val callers = data.callGraph?.filterValues { it.contains(funcName) }?.keys?.sorted() ?: emptyList()
                val aliveCallers = callers.filter { data.coveredFunctions?.contains(it) == true }
                val deadCallers = callers.filter { data.coveredFunctions?.contains(it) != true }
                sb.append("callers:${callers.hashCode()};")
                sb.append("aliveCallers:${aliveCallers.size};deadCallers:${deadCallers.size};")

                // 4. Callees (what this function calls)
                val callees = data.callGraph?.get(funcName)?.sorted() ?: emptyList()
                sb.append("callees:${callees.hashCode()};")

                // 5. whyNotCovered reason
                val whyInfo = data.whyNotCovered?.get(funcName)
                val whyReason = whyInfo?.rootCause ?: ""
                sb.append("why:$whyReason;")

                return sb.toString().hashCode().toString(16)
            } catch (e: Exception) {
                return "error"
            }
        }

        private fun startBackgroundWorker() {
            backgroundWorker = java.util.concurrent.Executors.newSingleThreadScheduledExecutor { r ->
                Thread(r, "TrueFlow-AutoExplain").apply { isDaemon = true }
            }

            backgroundWorker?.scheduleWithFixedDelay({
                if (!isShutdown) {
                    processQueueIfIdle()
                }
            }, 10, 3, java.util.concurrent.TimeUnit.SECONDS)  // Check every 3 seconds
        }

        /**
         * Select the next function to process, prioritizing user-interacted items.
         * Returns null if queue is empty.
         */
        private fun selectNextFunction(): String? {
            if (pendingQueue.isEmpty()) return null

            // Find highest priority item (most recently user-interacted)
            val prioritized = pendingQueue.filter { priorityFunctions.containsKey(it) }
            if (prioritized.isNotEmpty()) {
                // Sort by timestamp descending (most recent first)
                val best = prioritized.maxByOrNull { priorityFunctions[it] ?: 0L }
                if (best != null) {
                    pendingQueue.remove(best)
                    return best
                }
            }

            // No priority items, just poll normally
            return pendingQueue.poll()
        }

        private fun processQueueIfIdle() {
            if (isProcessing || pendingQueue.isEmpty()) return

            // Check if AI is idle (no user requests recently)
            if (!isIdle()) {
                return
            }

            // Check if AI server is running and not busy
            val aiPanel = findAIExplanationPanel()
            if (aiPanel == null || !aiPanel.isServerRunning()) {
                return
            }

            // Process priority items first (user searches/focused nodes)
            val funcName = selectNextFunction() ?: return
            isProcessing = true

            val isPriority = priorityFunctions.containsKey(funcName)
            priorityFunctions.remove(funcName)  // Clear priority after selection
            PluginLogger.info("[AutoExplain] Processing${if (isPriority) " (PRIORITY)" else ""}: $funcName (remaining: ${pendingQueue.size})")

            // Notify explorer that auto-explain is active
            notifyAutoExplainStatus(funcName, active = true)

            try {
                processAutoExplain(funcName, aiPanel)
            } catch (e: Exception) {
                PluginLogger.error("[AutoExplain] Error processing $funcName", e)
                isProcessing = false
                notifyAutoExplainStatus(null, active = false)
            }
        }

        private fun processAutoExplain(funcName: String, aiPanel: AIExplanationPanel) {
            val data = visualizationData ?: run {
                isProcessing = false
                return
            }

            val funcInfo = data.functions[funcName]
            val whyInfo = data.whyNotCovered[funcName]

            if (funcInfo == null || whyInfo == null) {
                isProcessing = false
                return
            }

            val filePath = funcInfo.file ?: ""
            val line = funcInfo.line
            val contentHash = computeContentHash(funcName, filePath, line)

            // Check cache again (might have been filled by user request)
            if (hasValidExplanation(funcName, filePath, contentHash)) {
                PluginLogger.info("[AutoExplain] Already cached: $funcName")
                isProcessing = false
                return
            }

            // Build rich context for auto-explain with call chain and root cause branch
            val sourceCode = readFunctionSource(filePath, line)
            val rootCause = whyInfo.rootCause
            val callerInfo = whyInfo.rootCauseDetail
            val reasons = whyInfo.reasons

            // Trace call chain from root caller to this dead function
            val callChain = traceCallChainToFunction(funcName, data)

            // Read root caller source (where the branch decision happens)
            val rootCallerSource = if (callerInfo?.caller != null) {
                val callerFunc = data.functions[callerInfo.caller]
                if (callerFunc?.file != null) {
                    readFunctionSource(callerFunc.file, callerFunc.line)
                } else ""
            } else ""

            val prompt = buildAutoExplainPrompt(funcName, rootCause, sourceCode, callerInfo, callChain, rootCallerSource, reasons)

            // Call AI asynchronously
            java.util.concurrent.CompletableFuture.runAsync {
                try {
                    aiPanel.askQuestion(prompt, sourceCode, null, silent = true) { response ->
                        // Store in cache
                        val explanation = CachedExplanation(
                            functionName = funcName,
                            filePath = filePath,
                            line = line,
                            contentHash = contentHash,
                            whyNotCovered = rootCause,
                            explanation = response,
                            timestamp = System.currentTimeMillis(),
                            modelUsed = "auto"
                        )
                        storeExplanation(explanation)
                        PluginLogger.info("[AutoExplain] Cached explanation for: $funcName")
                        isProcessing = false
                        notifyAutoExplainStatus(null, active = false)
                    }
                } catch (e: Exception) {
                    PluginLogger.error("[AutoExplain] Failed to get explanation for $funcName", e)
                    isProcessing = false
                    notifyAutoExplainStatus(null, active = false)
                }
            }
        }

        private fun notifyAutoExplainStatus(funcName: String?, active: Boolean) {
            val totalDead = visualizationData?.deadFunctions?.size ?: 0
            val cachedCount = cache.size
            val js = """
                if (typeof handleAutoExplainStatus === 'function') {
                    handleAutoExplainStatus({
                        active: $active,
                        function: "${funcName?.replace("\"", "\\\"") ?: ""}",
                        cached: $cachedCount,
                        total: $totalDead
                    });
                }
            """.trimIndent()
            ApplicationManager.getApplication().invokeLater {
                interactiveBrowser?.cefBrowser?.executeJavaScript(js, "", 0)
            }
            // Also push to SSE for browser mode
            explorerServer?.pushAutoExplainStatus(active, funcName, cachedCount, totalDead)
        }

        private fun readFunctionSource(filePath: String, line: Int): String {
            if (filePath.isEmpty() || line <= 0) return ""
            try {
                val file = File(filePath)
                if (!file.exists()) return ""
                val lines = file.readLines()
                val startIdx = maxOf(0, line - 1)
                val endIdx = minOf(lines.size, line + 30)
                return lines.subList(startIdx, endIdx).joinToString("\n")
            } catch (e: Exception) {
                return ""
            }
        }

        /**
         * Trace the call chain from root caller down to a dead function using the call graph.
         * Returns a list like: [root_entry_point, intermediate_caller, ..., dead_function]
         */
        private fun traceCallChainToFunction(funcName: String, data: InteractiveVisualizationData): List<String> {
            val chain = mutableListOf<String>()
            val visited = mutableSetOf<String>()
            var current = funcName
            chain.add(current)

            // Walk upward through the call graph (find callers)
            val reverseGraph = mutableMapOf<String, MutableList<String>>()
            for ((caller, callees) in data.callGraph) {
                for (callee in callees) {
                    reverseGraph.getOrPut(callee) { mutableListOf() }.add(caller)
                }
            }
            // Also check resolved call graph
            for ((caller, callees) in data.resolvedCallGraph) {
                for (callee in callees) {
                    reverseGraph.getOrPut(callee) { mutableListOf() }.add(caller)
                }
            }

            // Walk up to root (max 20 levels to avoid cycles)
            for (i in 0 until 20) {
                if (visited.contains(current)) break
                visited.add(current)
                val callers = reverseGraph[current] ?: break
                if (callers.isEmpty()) break
                // Pick first caller (prefer covered callers for branch-not-taken cases)
                val coveredSet = data.coveredFunctions.toSet()
                val nextCaller = callers.firstOrNull { coveredSet.contains(it) } ?: callers.first()
                chain.add(0, nextCaller)
                current = nextCaller
            }
            return chain
        }

        private fun buildAutoExplainPrompt(
            funcName: String,
            rootCause: String,
            sourceCode: String,
            callerInfo: WhyNotCoveredDetail?,
            callChain: List<String> = emptyList(),
            rootCallerSource: String = "",
            reasons: List<WhyNotCoveredReason> = emptyList()
        ): String {
            return buildString {
                append("Explain why this function is not executed:\n\n")
                append("Function: $funcName\n")
                append("Root cause: $rootCause\n")

                // Branch info from root cause
                if (callerInfo != null) {
                    if (callerInfo.caller != null) {
                        append("\nRoot caller (where the decision happens): ${callerInfo.caller}\n")
                    }
                    if (callerInfo.branchCondition != null) {
                        append("Branch not taken: ${callerInfo.branchType ?: "if"} ${callerInfo.branchCondition}")
                        if (callerInfo.branchLine != null) {
                            append(" (line ${callerInfo.branchLine})")
                        }
                        append("\n")
                    }
                }

                // Call chain from root to dead function
                if (callChain.size > 1) {
                    append("\nCall chain (root → dead):\n")
                    append("  ${callChain.joinToString(" → ")}\n")
                }

                // Chain explanation from reasons (may contain "Chain: A → B → C")
                for (reason in reasons) {
                    if (reason.explanation != null && reason.explanation.contains("Chain:")) {
                        append("\n${reason.explanation}\n")
                        break
                    }
                }

                // Root caller source (where the branch decision is made)
                if (rootCallerSource.isNotEmpty()) {
                    append("\nRoot caller source:\n```python\n$rootCallerSource\n```\n")
                }

                // Dead function source
                if (sourceCode.isNotEmpty()) {
                    append("\nDead function source:\n```python\n$sourceCode\n```\n")
                }

                append("\nProvide a concise 2-3 sentence explanation of why this function is dead and what condition would need to change to make it execute.")
            }
        }

        private fun loadCache() {
            try {
                if (cacheFile.exists()) {
                    val json = cacheFile.readText()
                    val type = object : com.google.gson.reflect.TypeToken<Map<String, CachedExplanation>>() {}.type
                    val loaded: Map<String, CachedExplanation>? = gson.fromJson<Map<String, CachedExplanation>>(json, type)
                    if (loaded != null) {
                        cache.clear()
                        cache.putAll(loaded)
                    }
                    PluginLogger.info("[AutoExplain] Loaded ${cache.size} cached explanations")
                }
            } catch (e: Exception) {
                PluginLogger.warn("[AutoExplain] Failed to load cache: ${e.message}")
            }
        }

        private fun saveCache() {
            try {
                cacheFile.parentFile?.mkdirs()
                val json = gson.toJson(cache)
                cacheFile.writeText(json)
            } catch (e: Exception) {
                PluginLogger.warn("[AutoExplain] Failed to save cache: ${e.message}")
            }
        }

        fun shutdown() {
            isShutdown = true
            backgroundWorker?.shutdown()
            saveCache()
        }

        fun getCacheStats(): Map<String, Any> {
            return mapOf(
                "totalCached" to cache.size,
                "pendingQueue" to pendingQueue.size,
                "isProcessing" to isProcessing,
                "isIdle" to isIdle()
            )
        }
    }

    // Explanation cache instance
    private var explanationCache: ExplanationCacheManager? = null

    /**
     * Public accessor for cached AI explanations (used by MCP RPC handlers).
     */
    fun getCachedExplanation(funcName: String, filePath: String): CachedExplanation? {
        return explanationCache?.getExplanation(funcName, filePath)
    }

    private fun notifyExplorerOfCachedExplanation(explanation: CachedExplanation) {
        ApplicationManager.getApplication().invokeLater {
            val escapedExplanation = explanation.explanation
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "")

            val message = """
                {
                    "type": "cached_explanation",
                    "function": "${explanation.functionName}",
                    "explanation": "$escapedExplanation",
                    "whyNotCovered": "${explanation.whyNotCovered}",
                    "cached": true
                }
            """.trimIndent()

            interactiveBrowser?.cefBrowser?.executeJavaScript(
                "if (typeof handleCachedExplanation === 'function') { handleCachedExplanation($message); }",
                "", 0
            )
        }
    }

    // ==================== END AUTO-EXPLAIN CACHE SYSTEM ====================

    init {
        border = JBUI.Borders.empty(10)
        createUI()
        scanForVideos()
        setupFileWatcher()
        // Initialize auto-explain cache
        explanationCache = ExplanationCacheManager()
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
        // Shutdown auto-explain cache
        explanationCache?.shutdown()
        explanationCache = null
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
                            PluginLogger.info("[ManimVideoPanel] onLoadEnd: page ready (mode=$currentViewMode, pendingDataRefresh=$pendingDataRefresh, hasVisualizationData=${visualizationData != null})")

                            // Inject the cefQuery function for JS to Kotlin communication
                            injectCefQuery()

                            // If we have pending data, send it now based on current view mode
                            if (pendingDataRefresh || visualizationData != null) {
                                PluginLogger.info("[ManimVideoPanel] onLoadEnd: sending pending data to browser")
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

            // Forward JCEF console messages to plugin log (for debugging JS issues)
            if (cefBrowser != null) {
                interactiveBrowser?.jbCefClient?.addDisplayHandler(object : org.cef.handler.CefDisplayHandlerAdapter() {
                    override fun onConsoleMessage(browser: org.cef.browser.CefBrowser?, level: org.cef.CefSettings.LogSeverity?,
                                                  message: String?, source: String?, line: Int): Boolean {
                        if (message != null) {
                            PluginLogger.info("[JCEF Console] $message")
                        }
                        return false
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
                },
                // Unified explain handler - routes through same logic as IDE mode
                onExplainRequest = { funcName, filePath, isDead, whyNotCovered, onResult ->
                    handleHttpExplainRequest(funcName, filePath, isDead, whyNotCovered, onResult)
                },
                // Prioritize handler - for preemptive caching based on user searches/focus
                onPrioritizeRequest = { funcNames, reason ->
                    funcNames.forEach { funcName ->
                        explanationCache?.prioritizeFunction(funcName, reason)
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
     * Handle explain request from HTTP server (browser mode).
     * Uses same caching and prompt logic as IDE mode.
     */
    private fun handleHttpExplainRequest(
        funcName: String,
        filePath: String,
        isDead: Boolean,
        whyNotCovered: String?,
        onResult: (String?, Boolean) -> Unit
    ) {
        // Mark user activity (pauses auto-explain)
        explanationCache?.markUserActivity()

        // Check cache first
        if (isDead && filePath.isNotEmpty()) {
            val cached = explanationCache?.getExplanation(funcName, filePath)
            if (cached != null) {
                PluginLogger.info("[HttpExplain] Using cached explanation for: $funcName")
                onResult(cached.explanation, true)
                return
            }
        }

        // Check if AI server is running
        val aiPanel = findAIExplanationPanel()
        if (aiPanel == null || !aiPanel.isServerRunning()) {
            PluginLogger.warn("[HttpExplain] AI server not running")
            onResult(null, false)
            return
        }

        // Get function info from visualization data
        val funcInfo = visualizationData?.functions?.get(funcName)
        val funcLine = funcInfo?.line ?: 0
        val whyInfo = visualizationData?.whyNotCovered?.get(funcName)

        // Build context and prompt (same as IDE mode)
        java.util.concurrent.CompletableFuture.runAsync {
            try {
                // Read function source
                val sourceCode = if (filePath.isNotEmpty() && funcLine > 0) {
                    try {
                        val file = File(filePath)
                        if (file.exists()) {
                            val lines = file.readLines()
                            val startLine = maxOf(0, funcLine - 1)
                            val endLine = minOf(lines.size, funcLine + 30)
                            lines.subList(startLine, endLine).joinToString("\n")
                        } else ""
                    } catch (e: Exception) { "" }
                } else ""

                // Build prompt based on status
                val prompt = buildString {
                    if (isDead) {
                        append("Analyze why this function is NOT being executed:\n\n")
                        append("Function: $funcName\n")
                        append("File: $filePath\n")
                        if (whyNotCovered != null) {
                            append("Root cause: $whyNotCovered\n")
                        }
                        if (sourceCode.isNotEmpty()) {
                            append("\nSource code:\n```python\n$sourceCode\n```\n")
                        }
                        append("\nExplain why this code is not being executed and what would trigger it.")
                    } else {
                        append("Explain this function's purpose and behavior:\n\n")
                        append("Function: $funcName\n")
                        append("File: $filePath\n")
                        if (sourceCode.isNotEmpty()) {
                            append("\nSource code:\n```python\n$sourceCode\n```\n")
                        }
                        append("\nProvide a concise explanation.")
                    }
                }

                // Call AI (silent — result goes to explorer panel, not chat)
                aiPanel.askQuestion(prompt, sourceCode, null, silent = true) { response ->
                    // Cache the result for dead functions
                    if (isDead && filePath.isNotEmpty() && whyNotCovered != null) {
                        try {
                            val file = File(filePath)
                            val contentHash = if (file.exists() && funcLine > 0) {
                                val lines = file.readLines()
                                val startIdx = maxOf(0, funcLine - 1)
                                val endIdx = minOf(lines.size, funcLine + 50)
                                lines.subList(startIdx, endIdx).joinToString("\n").hashCode().toString(16)
                            } else "unknown"

                            val cached = CachedExplanation(
                                functionName = funcName,
                                filePath = filePath,
                                line = funcLine,
                                contentHash = contentHash,
                                whyNotCovered = whyNotCovered,
                                explanation = response,
                                timestamp = System.currentTimeMillis(),
                                modelUsed = "http-request"
                            )
                            explanationCache?.storeExplanation(cached)
                            PluginLogger.info("[HttpExplain] Cached explanation for: $funcName")
                        } catch (e: Exception) {
                            PluginLogger.warn("[HttpExplain] Failed to cache: ${e.message}")
                        }
                    }

                    onResult(response, false)
                }
            } catch (e: Exception) {
                PluginLogger.error("[HttpExplain] Error: ${e.message}", e)
                onResult(null, false)
            }
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

                    // Enhanced context from call graph analysis
                    val rootCauseDetail = json.getAsJsonObject("rootCauseDetail")
                    val callChain = json.getAsJsonArray("callChain")?.map { it.asString } ?: emptyList()
                    val upstreamPath = json.getAsJsonArray("upstreamPath")?.map { it.asString } ?: emptyList()
                    val downstreamPath = json.getAsJsonArray("downstreamPath")?.map { it.asString } ?: emptyList()
                    val directCallers = json.getAsJsonArray("directCallers")?.map { it.asString } ?: emptyList()
                    val directCallees = json.getAsJsonArray("directCallees")?.map { it.asString } ?: emptyList()
                    val chainFiles = json.getAsJsonArray("chainFiles")
                    val chainDefs = json.getAsJsonArray("chainDefs")

                    // Partial incoming coverage info
                    val hasDeadIncomingPaths = json.get("hasDeadIncomingPaths")?.asBoolean ?: false
                    val deadCallers = json.getAsJsonArray("deadCallers")?.map { it.asString } ?: emptyList()
                    val aliveCallers = json.getAsJsonArray("aliveCallers")?.map { it.asString } ?: emptyList()
                    val deadCallerFiles = json.getAsJsonArray("deadCallerFiles")  // File info to read dead caller source

                    if (funcName != null) {
                        handleExplainRequest(
                            funcName, funcFile, funcLine, isAlive, isDead, callCount, whyNotCovered,
                            rootCauseDetail, callChain, upstreamPath, downstreamPath,
                            directCallers, directCallees, chainFiles, chainDefs,
                            hasDeadIncomingPaths, deadCallers, aliveCallers, deadCallerFiles
                        )
                    }
                }
                "prioritize" -> {
                    // Prioritize functions for auto-explain (user search/focus)
                    val reason = json.get("reason")?.asString ?: "user_interaction"
                    val funcName = json.get("function")?.asString
                    val funcNames = json.getAsJsonArray("functions")?.mapNotNull { it.asString }

                    if (funcName != null) {
                        explanationCache?.prioritizeFunction(funcName, reason)
                    } else if (funcNames != null && funcNames.isNotEmpty()) {
                        explanationCache?.prioritizeFunctions(funcNames, reason)
                    }
                }
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to handle JS callback", e)
        }
    }

    /**
     * Handles AI explanation request from Interactive Explorer.
     * Checks cache first, then LLM server if no cached explanation.
     */
    private fun handleExplainRequest(
        funcName: String,
        funcFile: String?,
        funcLine: Int,
        isAlive: Boolean,
        isDead: Boolean,
        callCount: Int,
        whyNotCovered: String?,
        rootCauseDetail: com.google.gson.JsonObject?,
        callChain: List<String>,
        upstreamPath: List<String>,
        downstreamPath: List<String>,
        directCallers: List<String>,
        directCallees: List<String>,
        chainFiles: com.google.gson.JsonArray?,
        chainDefs: com.google.gson.JsonArray?,
        hasDeadIncomingPaths: Boolean,
        deadCallers: List<String>,
        aliveCallers: List<String>,
        deadCallerFiles: com.google.gson.JsonArray?
    ) {
        // Mark user activity (pauses auto-explain background processing)
        explanationCache?.markUserActivity()

        ApplicationManager.getApplication().invokeLater {
            // Check cache first for dead functions
            if (isDead && funcFile != null) {
                val cached = explanationCache?.getExplanation(funcName, funcFile)
                if (cached != null) {
                    PluginLogger.info("[Explain] Using cached explanation for: $funcName")
                    // Send cached response immediately
                    sendCachedExplanationToExplorer(funcName, cached.explanation, cached.whyNotCovered)
                    return@invokeLater
                }
            }

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
                // Server is running, request explanation with enhanced context
                requestAIExplanation(
                    funcName, funcFile, funcLine, isAlive, isDead, callCount, whyNotCovered,
                    rootCauseDetail, callChain, upstreamPath, downstreamPath,
                    directCallers, directCallees, chainFiles, chainDefs,
                    hasDeadIncomingPaths, deadCallers, aliveCallers, deadCallerFiles, aiPanel!!
                )
            }
        }
    }

    /**
     * Send a cached explanation to the Interactive Explorer.
     */
    private fun sendCachedExplanationToExplorer(funcName: String, explanation: String, whyNotCovered: String) {
        val escapedResponse = explanation.replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "")

        val responseMessage = """
            {
                "type": "llm_response",
                "function": "$funcName",
                "explanation": "$escapedResponse",
                "cached": true,
                "whyNotCovered": "$whyNotCovered"
            }
        """.trimIndent()

        interactiveBrowser?.cefBrowser?.executeJavaScript(
            "if (typeof handleLLMResponse === 'function') { handleLLMResponse($responseMessage); }",
            "", 0
        )
    }

    /**
     * Find the AIExplanationPanel instance.
     */
    private fun findAIExplanationPanel(): AIExplanationPanel? {
        val toolWindowManager = com.intellij.openapi.wm.ToolWindowManager.getInstance(project)
        val toolWindow = toolWindowManager.getToolWindow("TrueFlow") ?: return null

        // Recursively search the component tree for AIExplanationPanel
        val content = toolWindow.contentManager.contents
        for (c in content) {
            val found = findComponentOfType(c.component, AIExplanationPanel::class.java)
            if (found != null) return found
        }
        return null
    }

    private fun <T> findComponentOfType(root: java.awt.Component, type: Class<T>): T? {
        if (type.isInstance(root)) {
            @Suppress("UNCHECKED_CAST")
            return root as T
        }
        if (root is java.awt.Container) {
            for (child in root.components) {
                val found = findComponentOfType(child, type)
                if (found != null) return found
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
     * Request AI explanation for a function with full call graph context.
     */
    private fun requestAIExplanation(
        funcName: String,
        funcFile: String?,
        funcLine: Int,
        isAlive: Boolean,
        isDead: Boolean,
        callCount: Int,
        whyNotCovered: String?,
        rootCauseDetail: com.google.gson.JsonObject?,
        callChain: List<String>,
        upstreamPath: List<String>,
        downstreamPath: List<String>,
        directCallers: List<String>,
        directCallees: List<String>,
        chainFiles: com.google.gson.JsonArray?,
        chainDefs: com.google.gson.JsonArray?,
        hasDeadIncomingPaths: Boolean,
        deadCallers: List<String>,
        aliveCallers: List<String>,
        deadCallerFiles: com.google.gson.JsonArray?,
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

        // Extract root cause details
        val branchCaller = rootCauseDetail?.get("caller")?.asString
        val branchCondition = rootCauseDetail?.get("branch_condition")?.asString
        val branchLine = rootCauseDetail?.get("branch_line")?.asString

        // Build enhanced context for the explanation
        val context = buildString {
            append("Function: $funcName\n")
            if (funcFile != null) append("File: $funcFile\n")
            if (funcLine > 0) append("Line: $funcLine\n")
            append("Status: ${if (isAlive) "Executed" else "Not Executed"}\n")
            if (callCount > 0) append("Call count: $callCount\n")
            if (isDead && whyNotCovered != null) {
                append("\n=== WHY NOT COVERED ===\n")
                append("Root cause: $whyNotCovered\n")
                if (branchCaller != null) {
                    append("Branch decision in: $branchCaller\n")
                    if (branchCondition != null) append("Condition: $branchCondition\n")
                    if (branchLine != null) append("At line: $branchLine\n")
                }
                if (callChain.isNotEmpty()) {
                    append("Call chain: ${callChain.joinToString(" → ")}\n")
                }
            }
            append("\n=== CALL GRAPH CONTEXT ===\n")
            if (directCallers.isNotEmpty()) {
                append("Direct callers (${directCallers.size}): ${directCallers.take(5).joinToString(", ")}${if (directCallers.size > 5) "..." else ""}\n")
            } else {
                append("Direct callers: NONE (orphaned)\n")
            }
            if (directCallees.isNotEmpty()) {
                append("Direct callees (${directCallees.size}): ${directCallees.take(5).joinToString(", ")}${if (directCallees.size > 5) "..." else ""}\n")
            }
            append("Total upstream (transitive callers): ${upstreamPath.size}\n")
            append("Total downstream (transitive callees): ${downstreamPath.size}\n")

            // Partial incoming coverage info
            if (hasDeadIncomingPaths && isAlive) {
                append("\n=== PARTIAL INCOMING COVERAGE ===\n")
                append("This function is ALIVE but has DEAD CALLERS (paths not exercised).\n")
                append("Alive callers (${aliveCallers.size}): ${aliveCallers.take(3).joinToString(", ")}${if (aliveCallers.size > 3) "..." else ""}\n")
                append("Dead callers (${deadCallers.size}): ${deadCallers.take(3).joinToString(", ")}${if (deadCallers.size > 3) "..." else ""}\n")
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
                            val endLine = minOf(lines.size, funcLine + 30)  // Read more lines
                            lines.subList(startLine, endLine).joinToString("\n")
                        } else ""
                    } catch (e: Exception) { "" }
                } else ""

                // Helper function to read entire Python function from file
                fun readEntireFunction(lines: List<String>, funcDefLine: Int, maxLines: Int = 200): Pair<Int, Int> {
                    if (funcDefLine < 1 || funcDefLine > lines.size) return Pair(0, minOf(50, lines.size))

                    val startIdx = funcDefLine - 1  // Convert to 0-indexed
                    val defLine = lines.getOrNull(startIdx) ?: return Pair(startIdx, minOf(startIdx + 50, lines.size))

                    // Get the indentation of the function definition
                    val defIndent = defLine.takeWhile { it == ' ' || it == '\t' }.length

                    // Find the end of the function by looking for:
                    // 1. Another def/class at same or lesser indentation
                    // 2. A non-empty line with lesser indentation (dedent)
                    var endIdx = startIdx + 1
                    while (endIdx < lines.size && endIdx < startIdx + maxLines) {
                        val line = lines[endIdx]
                        val trimmed = line.trim()

                        // Skip empty lines and comments
                        if (trimmed.isEmpty() || trimmed.startsWith("#")) {
                            endIdx++
                            continue
                        }

                        val lineIndent = line.takeWhile { it == ' ' || it == '\t' }.length

                        // Check for new function/class definition at same or lesser indentation
                        if (lineIndent <= defIndent && (trimmed.startsWith("def ") || trimmed.startsWith("async def ") || trimmed.startsWith("class "))) {
                            break
                        }

                        // Check for dedent to module/class level (non-empty line with less indent)
                        if (lineIndent < defIndent && trimmed.isNotEmpty() && !trimmed.startsWith("@")) {
                            break
                        }

                        endIdx++
                    }

                    return Pair(maxOf(0, startIdx - 2), endIdx)  // Include 2 lines before for decorators
                }

                // Read source code for ALL callers in the chain (especially the root cause)
                val callersSourceCode = buildString {
                    if (chainFiles != null && chainFiles.size() > 0) {
                        // Read source code for each caller in the chain
                        for (i in 0 until minOf(chainFiles.size(), 3)) {  // Limit to 3 callers to avoid too much context
                            try {
                                val callerObj = chainFiles[i].asJsonObject
                                val callerFunc = callerObj.get("function")?.asString ?: "Unknown"
                                val callerFile = callerObj.get("file")?.asString
                                val callerLine = callerObj.get("line")?.asInt ?: 0
                                val isRootCause = callerObj.get("isRootCause")?.asBoolean ?: false

                                if (callerFile != null) {
                                    val file = java.io.File(callerFile)
                                    if (file.exists()) {
                                        val lines = file.readLines()
                                        val (startLine, endLine) = readEntireFunction(lines, callerLine)

                                        val marker = if (isRootCause) "ROOT CAUSE CALLER" else "CALLER"
                                        append("\n// === $marker: $callerFunc ===\n")
                                        append("// File: $callerFile (line $callerLine)\n")
                                        append(lines.subList(startLine, endLine).mapIndexed { idx, line ->
                                            val lineNum = startLine + idx + 1
                                            val lineMarker = if (lineNum == callerLine) ">>>" else "   "
                                            "$lineMarker $lineNum: $line"
                                        }.joinToString("\n"))
                                        append("\n")
                                    }
                                }
                            } catch (e: Exception) {
                                PluginLogger.warn("Failed to read caller source: ${e.message}")
                            }
                        }
                    }
                }

                // Keep backwards compatibility - extract just the root cause caller source for simple cases
                val callerSourceCode = callersSourceCode

                // Read function DEFINITIONS only for entire call chain (to trace the path)
                val chainDefsCode = buildString {
                    if (chainDefs != null && chainDefs.size() > 0) {
                        append("\n// === CALL CHAIN (function definitions to trace the path) ===\n")
                        for (i in 0 until chainDefs.size()) {
                            try {
                                val defObj = chainDefs[i].asJsonObject
                                val defFunc = defObj.get("function")?.asString ?: "Unknown"
                                val defFile = defObj.get("file")?.asString
                                val defLine = defObj.get("line")?.asInt ?: 0
                                val chainIndex = defObj.get("chainIndex")?.asInt ?: i

                                if (defFile != null) {
                                    val file = java.io.File(defFile)
                                    if (file.exists()) {
                                        val lines = file.readLines()
                                        val startLine = maxOf(0, defLine - 1)
                                        val endLine = minOf(lines.size, defLine + 12)  // Just ~12 lines for def

                                        append("\n// [$chainIndex] $defFunc\n")
                                        append("// File: $defFile:$defLine\n")
                                        append(lines.subList(startLine, endLine).mapIndexed { idx, line ->
                                            val lineNum = startLine + idx + 1
                                            "$lineNum: $line"
                                        }.joinToString("\n"))
                                        append("\n")
                                    }
                                }
                            } catch (e: Exception) {
                                PluginLogger.warn("Failed to read chain def: ${e.message}")
                            }
                        }
                    }
                }

                // Read source code for DEAD CALLERS (for partial coverage analysis)
                val deadCallersSourceCode = buildString {
                    if (deadCallerFiles != null && deadCallerFiles.size() > 0) {
                        append("\n// === DEAD CALLERS SOURCE (paths not exercised) ===\n")
                        for (i in 0 until minOf(deadCallerFiles.size(), 5)) {  // Limit to 5 dead callers
                            try {
                                val callerObj = deadCallerFiles[i].asJsonObject
                                val callerFunc = callerObj.get("function")?.asString ?: "Unknown"
                                val callerFile = callerObj.get("file")?.asString
                                val callerLine = callerObj.get("line")?.asInt ?: 0

                                if (callerFile != null) {
                                    val file = java.io.File(callerFile)
                                    if (file.exists()) {
                                        val lines = file.readLines()
                                        val (startLine, endLine) = readEntireFunction(lines, callerLine)

                                        append("\n// ❌ DEAD CALLER: $callerFunc\n")
                                        append("// File: $callerFile (line $callerLine)\n")
                                        append(lines.subList(startLine, endLine).mapIndexed { idx, line ->
                                            val lineNum = startLine + idx + 1
                                            val lineMarker = if (lineNum == callerLine) ">>>" else "   "
                                            "$lineMarker $lineNum: $line"
                                        }.joinToString("\n"))
                                        append("\n")
                                    }
                                }
                            } catch (e: Exception) {
                                PluginLogger.warn("Failed to read dead caller source: ${e.message}")
                            }
                        }
                    }
                }

                val prompt = buildString {
                    if (isDead) {
                        // For dead/uncovered code, focus on WHY it's not covered with full context
                        append("Analyze why this function is NOT being executed. You have full call graph context.\n\n")
                        append("=== ANALYSIS CONTEXT ===\n$context\n")

                        if (sourceCode.isNotEmpty()) {
                            append("\n=== TARGET FUNCTION SOURCE ===\n```python\n$sourceCode\n```\n")
                        }

                        if (callerSourceCode.isNotEmpty()) {
                            append("\n=== CALLER SOURCE (where branch decision happens) ===\n```python\n$callerSourceCode\n```\n")
                        }

                        if (chainDefsCode.isNotEmpty()) {
                            append("\n=== CALL CHAIN TRACE ===\n```python\n$chainDefsCode\n```\n")
                        }

                        append("\n=== YOUR ANALYSIS TASK ===\n")
                        when (whyNotCovered) {
                            "NO_CALL_SITES" -> {
                                append("This function has NO CALL SITES - nothing in the codebase calls it.\n\n")
                                append("Analyze:\n")
                                append("1. Based on the function name and code, what is its intended purpose?\n")
                                append("2. Is this likely:\n")
                                append("   - Dead code that should be deleted?\n")
                                append("   - A planned feature not yet integrated?\n")
                                append("   - A utility awaiting usage?\n")
                                append("   - An entry point for external triggers (API, CLI, tests)?\n")
                                append("3. If it should be called, where in the codebase would be appropriate?\n")
                            }
                            "UNREACHABLE_FROM_ENTRY" -> {
                                append("This function exists in an ORPHANED CALL CHAIN - the entire chain has no entry point.\n\n")
                                append("Call chain: ${callChain.joinToString(" → ")}\n\n")
                                append("Analyze:\n")
                                append("1. What entry point (main, API route, CLI command) is missing?\n")
                                append("2. Is this an abandoned feature or incomplete integration?\n")
                                append("3. How could this chain be connected to the application's execution flow?\n")
                            }
                            "BRANCH_NOT_TAKEN" -> {
                                append("This function is DEAD due to a BRANCH NOT TAKEN.\n\n")
                                append("The caller '$branchCaller' was executed but did NOT call this function '$funcName'.\n")
                                if (branchLine != null) {
                                    append("Caller defined at line: $branchLine\n")
                                }
                                append("\n=== CRITICAL: FIND THE EXACT BRANCH ===\n")
                                append("Look in the CALLER SOURCE CODE above and find:\n")
                                append("1. The EXACT LINE with 'if', 'elif', 'else', 'match', 'case', 'for', 'while', or 'try/except' that controls whether '$funcName' gets called\n")
                                append("2. Quote the EXACT condition code (e.g., 'if some_flag:', 'elif x > 10:', 'except ValueError:')\n")
                                append("3. The line number where this branch condition appears\n\n")
                                append("=== YOUR ANALYSIS ===\n")
                                append("Format your response as:\n")
                                append("**Branch Location:** Line X: `<exact condition code>`\n")
                                append("**Why Not Taken:** <explain what value/state caused this branch to be skipped>\n")
                                append("**To Execute This Path:** <specific input/state needed to take this branch>\n")
                                append("**Test Scenario:** <concrete test case that would call $funcName>\n")
                            }
                            else -> {
                                append("Analyze why this function is not being executed and what would trigger it.\n")
                            }
                        }
                        append("\nBe SPECIFIC and ACTIONABLE. Reference actual code from the context provided.")
                    } else if (hasDeadIncomingPaths) {
                        // For alive code with dead incoming paths - partial coverage
                        append("Analyze this function's PARTIAL INCOMING COVERAGE.\n\n")
                        append("This function '$funcName' IS executed via some paths, but other code paths to it are NOT being exercised.\n\n")
                        append("=== ANALYSIS CONTEXT ===\n$context\n")
                        if (sourceCode.isNotEmpty()) {
                            append("\n=== TARGET FUNCTION SOURCE ===\n```python\n$sourceCode\n```\n")
                        }
                        if (deadCallersSourceCode.isNotEmpty()) {
                            append("\n=== DEAD CALLERS SOURCE CODE ===\n```python\n$deadCallersSourceCode\n```\n")
                        }
                        append("\n=== COVERAGE STATUS ===\n")
                        append("✅ ALIVE callers (paths exercised): ${aliveCallers.joinToString(", ")}\n")
                        append("❌ DEAD callers (paths NOT exercised): ${deadCallers.joinToString(", ")}\n\n")
                        append("=== YOUR ANALYSIS TASK ===\n")
                        append("For EACH dead caller in the source code above, find:\n")
                        append("1. **The exact line** where the dead caller is defined\n")
                        append("2. **The branch condition** (if/elif/else/match/try-except) that prevented this caller from being executed\n")
                        append("3. **What would trigger it** - specific test input or state to exercise this path\n\n")
                        append("Format your response with a section for each dead caller:\n")
                        append("### Dead Caller: `<caller_name>`\n")
                        append("**Branch Location:** Line X: `<exact condition from source>`\n")
                        append("**Why Not Executed:** <explain what state caused this branch to not be taken>\n")
                        append("**Test Scenario:** <specific test case to exercise this path>\n")
                    } else {
                        // For alive/covered code, explain what it does
                        append("Explain this function's purpose and behavior:\n\n")
                        append("Context:\n$context\n")
                        if (sourceCode.isNotEmpty()) {
                            append("\nSource code:\n```python\n$sourceCode\n```\n")
                        }
                        append("\nProvide a concise explanation of what this function does and its role in the call graph.")
                    }
                }

                // Call the LLM (silent — result goes to explorer panel, not chat)
                aiPanel.askQuestion(prompt, sourceCode, null, silent = true) { response ->
                    // Cache the explanation for dead functions
                    if (isDead && funcFile != null && whyNotCovered != null) {
                        try {
                            val file = java.io.File(funcFile)
                            val contentHash = if (file.exists() && funcLine > 0) {
                                val lines = file.readLines()
                                val startIdx = maxOf(0, funcLine - 1)
                                val endIdx = minOf(lines.size, funcLine + 50)
                                lines.subList(startIdx, endIdx).joinToString("\n").hashCode().toString(16)
                            } else "unknown"

                            val cached = CachedExplanation(
                                functionName = funcName,
                                filePath = funcFile,
                                line = funcLine,
                                contentHash = contentHash,
                                whyNotCovered = whyNotCovered,
                                explanation = response,
                                timestamp = System.currentTimeMillis(),
                                modelUsed = "user-request"
                            )
                            explanationCache?.storeExplanation(cached)
                            PluginLogger.info("[Explain] Cached user-requested explanation for: $funcName")
                        } catch (e: Exception) {
                            PluginLogger.warn("[Explain] Failed to cache explanation: ${e.message}")
                        }
                    }

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

        val jsCode = jsQuery!!.inject("params.request",
            "params.onSuccess || function(){}",
            "(params.onFailure || function(error_code, error_message) { console.error('cefQuery failed:', error_code, error_message); })"
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
        functionFirstCalledTimestamp: Map<String, Double> = emptyMap(),  // funcKey -> first call timestamp
        functionProtocols: Map<String, Map<String, Int>> = emptyMap(),  // funcKey -> {proto -> count}
        functionFrameworks: Map<String, String> = emptyMap(),  // funcKey -> framework name
        functionAiAgents: Set<String> = emptySet()  // funcKeys that are AI agents
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
                "branches" to emptyList<Any>(),  // Will be populated by branch analyzer
                "protocols" to (functionProtocols[func] ?: emptyMap<String, Int>()),
                "framework" to functionFrameworks[func],
                "is_ai_agent" to (func in functionAiAgents)
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

        // Queue dead functions for auto-explain (background processing when AI is idle)
        explanationCache?.queueDeadFunctions(deadFunctions)

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

        if (browserPageReady) {
            ApplicationManager.getApplication().invokeLater {
                PluginLogger.info("[ManimVideoPanel] Injecting data via executeJavaScript (browserPageReady=true)")
                interactiveBrowser?.cefBrowser?.executeJavaScript(
                    "if (typeof loadVisualizationData === 'function') { loadVisualizationData($jsonData); }",
                    "", 0
                )
            }
        } else {
            // Browser not ready yet — the onLoadEnd handler will pick up visualizationData
            pendingDataRefresh = true
            PluginLogger.info("[ManimVideoPanel] Browser not ready, set pendingDataRefresh=true (data stored in visualizationData)")
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
