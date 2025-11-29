package com.crawl4ai.learningviz

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import java.io.File
import java.io.FileWriter
import java.io.PrintWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Properties

/**
 * Custom logger that writes to .pycharm_plugin/logs directory
 * Ensures all plugin activity is logged to a persistent file.
 *
 * This logger maintains separate log files per project to avoid
 * log interference when multiple projects are open.
 */
object PluginLogger {
    // Read version from plugin-version.properties embedded in JAR at build time
    val PLUGIN_VERSION: String by lazy {
        try {
            // Try to load from resources (embedded in JAR)
            val resourceStream = PluginLogger::class.java.classLoader.getResourceAsStream("plugin-version.properties")
            if (resourceStream != null) {
                val props = Properties()
                resourceStream.use { props.load(it) }
                props.getProperty("pluginVersion", "1.0.0")
            } else {
                "1.0.0"
            }
        } catch (e: Exception) {
            "1.0.0"
        }
    }

    private val ideaLogger = Logger.getInstance(PluginLogger::class.java)
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS")

    // Per-project loggers to prevent log switching when multiple projects open
    private val projectLoggers = mutableMapOf<String, ProjectLogContext>()

    // Current active project (used for convenience methods)
    private var currentProject: Project? = null

    private data class ProjectLogContext(
        val projectName: String,
        val logWriter: PrintWriter,
        val logFile: File
    )

    /**
     * Initialize logging for the project
     */
    fun initialize(project: Project) {
        try {
            val projectPath = project.basePath ?: run {
                ideaLogger.warn("No project base path available for logging")
                return
            }

            // Check if already initialized for this project
            if (projectLoggers.containsKey(projectPath)) {
                currentProject = project
                info("Logger already initialized for project: ${project.name}")
                return
            }

            // Get logs directory from PluginPaths (single source of truth)
            val logsDir = PluginPaths.getLogsDir(project)

            // Create log file with timestamp
            val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss").format(Date())
            val logFile = File(logsDir, "plugin_$timestamp.log")

            // Create file writer
            val logWriter = PrintWriter(FileWriter(logFile, true), true)

            // Store per-project context
            projectLoggers[projectPath] = ProjectLogContext(project.name, logWriter, logFile)
            currentProject = project

            // Log initialization (use project-specific logging)
            logToProject(projectPath, "INFO", "Using logs directory: ${logsDir.absolutePath}")
            logToProject(projectPath, "INFO", "=".repeat(80))
            logToProject(projectPath, "INFO", "Learning Flow Visualizer Plugin Started")
            logToProject(projectPath, "INFO", "Version: $PLUGIN_VERSION")
            logToProject(projectPath, "INFO", "Project: ${project.name}")
            logToProject(projectPath, "INFO", "Log file: ${logFile.absolutePath}")
            logToProject(projectPath, "INFO", "=".repeat(80))

        } catch (e: Exception) {
            ideaLogger.error("Failed to initialize plugin logger", e)
        }
    }

    /**
     * Set current active project for convenience logging
     */
    fun setCurrentProject(project: Project) {
        currentProject = project
    }

    /**
     * Log to specific project's log file
     */
    @Synchronized
    private fun logToProject(projectPath: String, level: String, message: String) {
        val context = projectLoggers[projectPath] ?: return
        val formatted = formatMessage(level, message)
        context.logWriter.println(formatted)
        context.logWriter.flush()
    }

    /**
     * Get current project path
     */
    private fun getCurrentProjectPath(): String? {
        return currentProject?.basePath
    }

    /**
     * Log info message
     */
    @Synchronized
    fun info(message: String) {
        val projectPath = getCurrentProjectPath()
        if (projectPath != null) {
            logToProject(projectPath, "INFO", message)
        }
        ideaLogger.info(message)
        println("[LearningFlowViz] $message")  // Also to console for debugging
    }

    /**
     * Log warning message
     */
    @Synchronized
    fun warn(message: String) {
        val projectPath = getCurrentProjectPath()
        if (projectPath != null) {
            logToProject(projectPath, "WARN", message)
        }
        ideaLogger.warn(message)
        println("[LearningFlowViz] WARNING: $message")
    }

    /**
     * Log error message
     */
    @Synchronized
    fun error(message: String, throwable: Throwable? = null) {
        val projectPath = getCurrentProjectPath()
        if (projectPath != null) {
            logToProject(projectPath, "ERROR", message)
            if (throwable != null) {
                val context = projectLoggers[projectPath]
                context?.logWriter?.println("Exception: ${throwable.message}")
                throwable.printStackTrace(context?.logWriter)
                context?.logWriter?.flush()
            }
        }

        if (throwable != null) {
            ideaLogger.error(message, throwable)
        } else {
            ideaLogger.error(message)
        }
        println("[LearningFlowViz] ERROR: $message")
    }

    /**
     * Log debug message
     */
    @Synchronized
    fun debug(message: String) {
        val projectPath = getCurrentProjectPath()
        if (projectPath != null) {
            logToProject(projectPath, "DEBUG", message)
        }
        ideaLogger.debug(message)
        if (System.getProperty("idea.plugin.debug") == "true") {
            println("[LearningFlowViz] DEBUG: $message")
        }
    }

    /**
     * Format log message with timestamp and level
     */
    private fun formatMessage(level: String, message: String): String {
        val timestamp = dateFormat.format(Date())
        return "[$timestamp] [$level] $message"
    }

    /**
     * Close the log writer for a specific project
     */
    fun close(project: Project) {
        try {
            val projectPath = project.basePath ?: return
            val context = projectLoggers.remove(projectPath)
            context?.logWriter?.flush()
            context?.logWriter?.close()
        } catch (e: Exception) {
            ideaLogger.error("Failed to close plugin logger", e)
        }
    }

    /**
     * Close all log writers
     */
    fun closeAll() {
        try {
            projectLoggers.values.forEach { context ->
                context.logWriter.flush()
                context.logWriter.close()
            }
            projectLoggers.clear()
        } catch (e: Exception) {
            ideaLogger.error("Failed to close plugin loggers", e)
        }
    }

    /**
     * Get current log file path for the active project
     */
    fun getLogFilePath(): String? {
        val projectPath = getCurrentProjectPath() ?: return null
        return projectLoggers[projectPath]?.logFile?.absolutePath
    }

    /**
     * Get log file path for a specific project
     */
    fun getLogFilePath(project: Project): String? {
        val projectPath = project.basePath ?: return null
        return projectLoggers[projectPath]?.logFile?.absolutePath
    }
}
