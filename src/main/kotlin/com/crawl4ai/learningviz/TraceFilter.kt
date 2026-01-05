package com.crawl4ai.learningviz

import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Global trace filtering system.
 *
 * Provides centralized filtering logic for all tabs:
 * - Manim video generation
 * - Sequence diagrams
 * - Call traces
 * - Performance profiling
 * - Dead code detection
 * - Flamegraphs
 * - SQL analysis
 *
 * Filters are applied during trace processing, not just display.
 *
 * Filter configuration persists across IDE restarts via PersistentStateComponent.
 */
@Service(Service.Level.PROJECT)
@State(
    name = "TraceFilterConfiguration",
    storages = [Storage("crawl4ai-trace-filters.xml")]
)
class TraceFilter : PersistentStateComponent<TraceFilter.FilterState> {

    /**
     * Serializable preset containing filter configuration
     */
    data class FilterPreset(
        var excludedFolders: MutableList<String> = mutableListOf(),
        var excludedFiles: MutableList<String> = mutableListOf(),
        var excludedModules: MutableList<String> = mutableListOf(),
        var excludedPatternStrings: MutableList<String> = mutableListOf(),
        var includeOnly: MutableList<String> = mutableListOf()
    )

    /**
     * Serializable state for persistence
     */
    data class FilterState(
        var excludedFolders: MutableList<String> = mutableListOf(),
        var excludedFiles: MutableList<String> = mutableListOf(),
        var excludedModules: MutableList<String> = mutableListOf(),
        var excludedPatternStrings: MutableList<String> = mutableListOf(),
        var includeOnly: MutableList<String> = mutableListOf(),
        var savedPresets: MutableMap<String, FilterPreset> = mutableMapOf(),
        var activePresetName: String? = null
    ) {
        companion object {
            fun getDefault(): FilterState {
                return FilterState(
                    excludedFolders = mutableListOf(
                        // Python standard library and packages
                        "site-packages",
                        "dist-packages",
                        "__pycache__",

                        // Virtual environments
                        "venv",
                        ".venv",
                        "env",
                        ".env",

                        // Testing
                        "tests",
                        "test",
                        ".pytest_cache",
                        ".tox",

                        // Build and distribution
                        "build",
                        "dist",
                        ".eggs",
                        "*.egg-info",

                        // Version control
                        ".git",
                        ".svn",
                        ".hg",

                        // IDE and editors
                        ".idea",
                        ".vscode",
                        ".pycharm_plugin",

                        // Documentation
                        "docs",
                        "doc",

                        // Database migrations
                        "migrations",

                        // Node.js (for mixed projects)
                        "node_modules",

                        // Build tools
                        ".gradle",
                        ".mvn",

                        // Logs and temporary files
                        "logs",
                        "log",
                        "tmp",
                        "temp",

                        // Examples and demos
                        "examples",
                        "example",
                        "demos",
                        "demo",

                        // ML/AI specific
                        "vllm",
                        "models",
                        "checkpoints",
                        "runs",
                        "tensorboard"
                    ),
                    excludedModules = mutableListOf(
                        // Logging frameworks
                        "logging",
                        "loguru",
                        "structlog",

                        // Testing frameworks
                        "unittest",
                        "pytest",
                        "nose",

                        // Context managers (if too noisy)
                        "contextlib",
                        "contextvars"
                    )
                )
            }
        }
    }

    /**
     * Filter configuration (runtime, uses CopyOnWriteArrayList for thread-safety)
     */
    data class FilterConfig(
        val excludedFolders: MutableList<String> = CopyOnWriteArrayList(),
        val excludedFiles: MutableList<String> = CopyOnWriteArrayList(),
        val excludedModules: MutableList<String> = CopyOnWriteArrayList(),
        val excludedPatterns: MutableList<Regex> = CopyOnWriteArrayList(),
        val includeOnly: MutableList<String> = CopyOnWriteArrayList()
    )

    /**
     * Current filter configuration (initialized from persisted state)
     */
    var config: FilterConfig = FilterConfig()
        private set

    init {
        // Always start with defaults (loadState() will override if persisted state exists)
        loadStateIntoConfig(FilterState.getDefault())
    }

    /**
     * Load state into runtime config
     */
    private fun loadStateIntoConfig(state: FilterState) {
        config.excludedFolders.clear()
        config.excludedFolders.addAll(state.excludedFolders)

        config.excludedFiles.clear()
        config.excludedFiles.addAll(state.excludedFiles)

        config.excludedModules.clear()
        config.excludedModules.addAll(state.excludedModules)

        config.excludedPatterns.clear()
        state.excludedPatternStrings.forEach { pattern ->
            try {
                config.excludedPatterns.add(Regex(pattern))
            } catch (e: Exception) {
                // Invalid regex, skip
            }
        }

        config.includeOnly.clear()
        config.includeOnly.addAll(state.includeOnly)
    }

    /**
     * Listeners notified when filter changes
     */
    private val changeListeners = CopyOnWriteArrayList<() -> Unit>()

    /**
     * Register a listener to be notified when filters change
     */
    fun addChangeListener(listener: () -> Unit) {
        changeListeners.add(listener)
    }

    /**
     * Remove a change listener
     */
    fun removeChangeListener(listener: () -> Unit) {
        changeListeners.remove(listener)
    }

    /** Flag to prevent clearing preset name during preset load */
    private var isLoadingPreset = false

    /**
     * Notify all listeners that filters have changed
     */
    private fun notifyChange() {
        // Clear active preset if this change wasn't from loading a preset
        if (!isLoadingPreset) {
            activePresetName = null
        }
        changeListeners.forEach { it() }
    }

    /**
     * Check if a file path should be excluded
     */
    fun shouldExclude(filePath: String): Boolean {
        if (filePath.isBlank()) return false

        // Check include-only list first (if specified, only these are included)
        if (config.includeOnly.isNotEmpty()) {
            val included = config.includeOnly.any { includePattern ->
                filePath.contains(includePattern, ignoreCase = true)
            }
            if (!included) return true
        }

        // Check excluded folders
        if (config.excludedFolders.any { folder ->
            filePath.contains(folder, ignoreCase = true)
        }) return true

        // Check excluded files
        if (config.excludedFiles.any { file ->
            filePath.endsWith(file, ignoreCase = true)
        }) return true

        // Check excluded modules
        if (config.excludedModules.any { module ->
            filePath.contains("/$module/", ignoreCase = true) ||
            filePath.contains("\\$module\\", ignoreCase = true)
        }) return true

        // Check regex patterns
        if (config.excludedPatterns.any { pattern ->
            pattern.matches(filePath)
        }) return true

        return false
    }

    /**
     * Check if a module name should be excluded
     */
    fun shouldExcludeModule(moduleName: String): Boolean {
        if (moduleName.isBlank()) return false

        // Check include-only list
        if (config.includeOnly.isNotEmpty()) {
            val included = config.includeOnly.any { includePattern ->
                moduleName.contains(includePattern, ignoreCase = true)
            }
            if (!included) return true
        }

        // Check excluded modules
        return config.excludedModules.any { module ->
            moduleName.contains(module, ignoreCase = true)
        }
    }

    /**
     * Check if a string matches any excluded module pattern.
     * Unlike shouldExcludeModule, this ONLY checks exclusion patterns (not includeOnly).
     * Use this for checking class/method names where includeOnly doesn't apply.
     */
    fun matchesExcludedPattern(text: String): Boolean {
        if (text.isBlank()) return false
        return config.excludedModules.any { pattern ->
            text.contains(pattern, ignoreCase = true)
        }
    }

    /**
     * Filter a list of trace events
     */
    fun filterTraces(traces: List<Map<String, Any>>): List<Map<String, Any>> {
        return traces.filter { trace ->
            val filePath = trace["file"] as? String ?: ""
            val module = trace["module"] as? String ?: ""
            !shouldExclude(filePath) && !shouldExcludeModule(module)
        }
    }

    // === Configuration Management ===

    fun addExcludedFolder(folder: String) {
        if (folder.isNotBlank() && !config.excludedFolders.contains(folder)) {
            config.excludedFolders.add(folder)
            notifyChange()
        }
    }

    fun removeExcludedFolder(folder: String) {
        if (config.excludedFolders.remove(folder)) {
            notifyChange()
        }
    }

    fun addExcludedFile(file: String) {
        if (file.isNotBlank() && !config.excludedFiles.contains(file)) {
            config.excludedFiles.add(file)
            notifyChange()
        }
    }

    fun removeExcludedFile(file: String) {
        if (config.excludedFiles.remove(file)) {
            notifyChange()
        }
    }

    fun addExcludedModule(module: String) {
        if (module.isNotBlank() && !config.excludedModules.contains(module)) {
            config.excludedModules.add(module)
            notifyChange()
        }
    }

    fun removeExcludedModule(module: String) {
        if (config.excludedModules.remove(module)) {
            notifyChange()
        }
    }

    fun addExcludedPattern(pattern: String) {
        if (pattern.isNotBlank()) {
            try {
                val regex = Regex(pattern)
                if (!config.excludedPatterns.any { it.pattern == pattern }) {
                    config.excludedPatterns.add(regex)
                    notifyChange()
                }
            } catch (e: Exception) {
                // Invalid regex, ignore
            }
        }
    }

    fun removeExcludedPattern(pattern: String) {
        val removed = config.excludedPatterns.removeIf { it.pattern == pattern }
        if (removed) {
            notifyChange()
        }
    }

    fun addIncludeOnly(pattern: String) {
        if (pattern.isNotBlank() && !config.includeOnly.contains(pattern)) {
            config.includeOnly.add(pattern)
            notifyChange()
        }
    }

    fun removeIncludeOnly(pattern: String) {
        if (config.includeOnly.remove(pattern)) {
            notifyChange()
        }
    }

    fun clearIncludeOnly() {
        if (config.includeOnly.isNotEmpty()) {
            config.includeOnly.clear()
            notifyChange()
        }
    }

    fun resetToDefaults() {
        loadStateIntoConfig(FilterState.getDefault())
        notifyChange()
    }

    fun clearAllFilters() {
        config.excludedFolders.clear()
        config.excludedFiles.clear()
        config.excludedModules.clear()
        config.excludedPatterns.clear()
        config.includeOnly.clear()
        notifyChange()
    }

    /**
     * Get filter statistics as a short string
     */
    fun getStats(): String {
        val totalExclusions = config.excludedFolders.size + config.excludedFiles.size +
                              config.excludedModules.size + config.excludedPatterns.size
        val includeCount = config.includeOnly.size
        return if (includeCount > 0) {
            "${totalExclusions} excluded, ${includeCount} include-only"
        } else {
            "${totalExclusions} exclusions"
        }
    }

    /**
     * Check if using default filters (no custom exclusions beyond defaults)
     */
    fun isDefault(): Boolean {
        // Check if all filter lists are at their default sizes or empty
        // Default folders are: site-packages, venv, .git, __pycache__, node_modules, .idea, .vscode
        val defaultFolderCount = 7
        val defaultModuleCount = 5  // logging, asyncio, concurrent, socket, threading

        return config.excludedFolders.size <= defaultFolderCount &&
               config.excludedFiles.isEmpty() &&
               config.excludedModules.size <= defaultModuleCount &&
               config.excludedPatterns.isEmpty() &&
               config.includeOnly.isEmpty()
    }

    // === Preset Management ===

    /** Currently active preset name (null if custom/unsaved) */
    var activePresetName: String? = null
        private set

    /** Saved presets */
    private val savedPresets = mutableMapOf<String, FilterPreset>()

    /**
     * Save current filter configuration as a named preset
     */
    fun savePreset(name: String) {
        val preset = FilterPreset(
            excludedFolders = config.excludedFolders.toMutableList(),
            excludedFiles = config.excludedFiles.toMutableList(),
            excludedModules = config.excludedModules.toMutableList(),
            excludedPatternStrings = config.excludedPatterns.map { it.pattern }.toMutableList(),
            includeOnly = config.includeOnly.toMutableList()
        )
        savedPresets[name] = preset
        activePresetName = name
        notifyChange()
    }

    /**
     * Load a named preset
     */
    fun loadPreset(name: String): Boolean {
        val preset = savedPresets[name] ?: return false

        isLoadingPreset = true
        try {
            config.excludedFolders.clear()
            config.excludedFolders.addAll(preset.excludedFolders)

            config.excludedFiles.clear()
            config.excludedFiles.addAll(preset.excludedFiles)

            config.excludedModules.clear()
            config.excludedModules.addAll(preset.excludedModules)

            config.excludedPatterns.clear()
            preset.excludedPatternStrings.forEach { pattern ->
                try {
                    config.excludedPatterns.add(Regex(pattern))
                } catch (e: Exception) {
                    // Invalid regex, skip
                }
            }

            config.includeOnly.clear()
            config.includeOnly.addAll(preset.includeOnly)

            activePresetName = name
            notifyChange()
        } finally {
            isLoadingPreset = false
        }
        return true
    }

    /**
     * Delete a saved preset
     */
    fun deletePreset(name: String): Boolean {
        val removed = savedPresets.remove(name) != null
        if (removed && activePresetName == name) {
            activePresetName = null
        }
        if (removed) notifyChange()
        return removed
    }

    /**
     * Get list of saved preset names
     */
    fun getPresetNames(): List<String> = savedPresets.keys.toList().sorted()

    /**
     * Check if a preset with the given name exists
     */
    fun hasPreset(name: String): Boolean = savedPresets.containsKey(name)

    /**
     * Mark current config as modified (no longer matching saved preset)
     */
    fun markAsModified() {
        activePresetName = null
    }

    // === PersistentStateComponent Implementation ===

    /**
     * Get state for persistence (called by IntelliJ when saving)
     */
    override fun getState(): FilterState {
        return FilterState(
            excludedFolders = config.excludedFolders.toMutableList(),
            excludedFiles = config.excludedFiles.toMutableList(),
            excludedModules = config.excludedModules.toMutableList(),
            excludedPatternStrings = config.excludedPatterns.map { it.pattern }.toMutableList(),
            includeOnly = config.includeOnly.toMutableList(),
            savedPresets = savedPresets.toMutableMap(),
            activePresetName = activePresetName
        )
    }

    /**
     * Load state from persistence (called by IntelliJ when loading)
     */
    override fun loadState(state: FilterState) {
        loadStateIntoConfig(state)
        // Load presets
        savedPresets.clear()
        savedPresets.putAll(state.savedPresets)
        activePresetName = state.activePresetName
    }

    companion object {
        /**
         * Get the TraceFilter service for a project
         */
        fun getInstance(project: Project): TraceFilter {
            return project.service<TraceFilter>()
        }
    }
}
