package com.crawl4ai.learningviz

import com.intellij.execution.ExecutionListener
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindowManager
import java.util.concurrent.atomic.AtomicLong

/**
 * Supported run types that TrueFlow can instrument
 */
enum class RunType(val displayName: String, val isSupported: Boolean) {
    PYTHON("Python", true),          // Supported via sys.settrace()
    JAVA("Java", true),              // Supported via Java agents/bytecode instrumentation
    KOTLIN("Kotlin", true),          // Supported (same as Java, runs on JVM)
    NODE_JS("Node.js", false),       // Future: could use --inspect or instrumentation
    GO("Go", false),                 // Future: could use delve or instrumentation
    RUST("Rust", false),             // Future: could use tracing crate
    RUBY("Ruby", false),             // Future: could use TracePoint
    PHP("PHP", false),               // Future: could use xdebug
    UNSUPPORTED("Unsupported", false)
}

/**
 * Listens for process executions and prompts user to enable tracing
 * if they're running code without TrueFlow instrumentation.
 * Supports all languages TrueFlow can trace.
 */
class TracingExecutionListener : ExecutionListener {

    // Track when we last showed a notification to avoid spam
    private val lastNotificationTime = AtomicLong(0)
    private val notificationCooldownMs = 60000L  // 1 minute cooldown between notifications

    // Track dismissed notifications per project to not re-nag
    private val dismissedProjects = mutableSetOf<String>()

    override fun processStarted(executorId: String, env: ExecutionEnvironment, handler: ProcessHandler) {
        val project = env.project
        val runProfile = env.runProfile

        // Skip if user already dismissed for this project
        val projectKey = project.basePath ?: project.name
        if (dismissedProjects.contains(projectKey)) return

        // Check what type of run this is
        val configName = runProfile.name.lowercase()
        val configClass = runProfile.javaClass.name.lowercase()

        // Detect supported languages/frameworks
        val runType = detectRunType(configClass, configName)
        if (runType == RunType.UNSUPPORTED || !runType.isSupported) return

        // Check if this run has TrueFlow tracing enabled
        val commandLine = try {
            handler.toString()
        } catch (e: Exception) {
            ""
        }

        val hasTracing = checkTracingEnabled(commandLine, runType, project)

        if (hasTracing) {
            PluginLogger.info("[ExecutionListener] ${runType.displayName} process started WITH tracing: ${runProfile.name}")
            return
        }

        // Process without tracing - check if we should notify
        PluginLogger.info("[ExecutionListener] ${runType.displayName} process started WITHOUT tracing: ${runProfile.name}")

        // Check cooldown
        val now = System.currentTimeMillis()
        val lastTime = lastNotificationTime.get()
        if (now - lastTime < notificationCooldownMs) {
            return  // Too soon since last notification
        }

        // Check if project is already integrated
        if (isProjectIntegrated(project)) {
            // Project has tracing set up but this specific run config doesn't use it
            // This might be intentional, so we'll use a lighter notification
            showMissingTracingNotification(project, runProfile.name, runType)
        } else {
            // Project not integrated at all - suggest Auto-Integrate
            showAutoIntegrateNotification(project, runProfile.name, runType)
        }

        lastNotificationTime.set(now)
    }

    /**
     * Detect the type of run based on the configuration class and name
     */
    private fun detectRunType(configClass: String, configName: String): RunType {
        return when {
            // Python
            configClass.contains("python") ||
            configName.endsWith(".py") ||
            configClass.contains("pytest") ||
            configClass.contains("django") ||
            configClass.contains("flask") -> RunType.PYTHON

            // Node.js / JavaScript
            configClass.contains("node") ||
            configClass.contains("npm") ||
            configName.endsWith(".js") ||
            configName.endsWith(".ts") ||
            configClass.contains("javascript") -> RunType.NODE_JS

            // Java
            configClass.contains("java") && !configClass.contains("javascript") ||
            configClass.contains("application") && configName.endsWith("main") -> RunType.JAVA

            // Kotlin
            configClass.contains("kotlin") -> RunType.KOTLIN

            // Go
            configClass.contains("goland") ||
            configClass.contains("gorun") ||
            configName.endsWith(".go") -> RunType.GO

            // Rust
            configClass.contains("rust") ||
            configClass.contains("cargo") -> RunType.RUST

            // Ruby
            configClass.contains("ruby") ||
            configName.endsWith(".rb") -> RunType.RUBY

            // PHP
            configClass.contains("php") -> RunType.PHP

            else -> RunType.UNSUPPORTED
        }
    }

    /**
     * Check if the run has TrueFlow tracing enabled
     */
    private fun checkTracingEnabled(commandLine: String, runType: RunType, project: Project): Boolean {
        // Common TrueFlow markers for all languages
        val commonMarkers = listOf(
            "TRUEFLOW_TRACE_ENABLED",
            ".trueflow",
            "[TrueFlow]",
            "(Traced)"
        )

        for (marker in commonMarkers) {
            if (commandLine.contains(marker, ignoreCase = true)) {
                return true
            }
        }

        // Language-specific markers
        when (runType) {
            RunType.PYTHON -> {
                val pythonMarkers = listOf(
                    "PYCHARM_PLUGIN_TRACE_ENABLED",
                    "CRAWL4AI_TRACE",
                    "sitecustomize",
                    ".pycharm_plugin"
                )
                for (marker in pythonMarkers) {
                    if (commandLine.contains(marker, ignoreCase = true)) {
                        return true
                    }
                }
            }
            RunType.JAVA, RunType.KOTLIN -> {
                val jvmMarkers = listOf(
                    // Agent JAR detection
                    "-javaagent:.*trueflow",        // Agent JAR in javaagent flag (regex-like)
                    "trueflow-agent.jar",           // Agent JAR name
                    "-javaagent:trueflow",          // Simple agent reference
                    // Environment variables (from TrueFlowAgent.java)
                    "TRUEFLOW_ENABLED",             // Main env var for Java agent
                    "TRUEFLOW_PORT",                // Port config env var
                    "TRUEFLOW_INCLUDES",            // Package filter env var
                    "TRUEFLOW_EXCLUDES",            // Package exclusion env var
                    "TRUEFLOW_TRACE_DIR",           // Trace output directory
                    // System properties
                    "-Dtrueflow.enabled=true"       // System property alternative
                )
                for (marker in jvmMarkers) {
                    if (commandLine.contains(marker, ignoreCase = true)) {
                        return true
                    }
                }
            }
            else -> { /* No additional markers for unsupported languages */ }
        }

        return false
    }

    private fun isProjectIntegrated(project: Project): Boolean {
        // Check for .pycharm_plugin directory or other integration markers
        val basePath = project.basePath ?: return false

        val integrationMarkers = listOf(
            ".pycharm_plugin",
            ".trueflow"
        )

        for (marker in integrationMarkers) {
            val markerDir = java.io.File(basePath, marker)
            if (markerDir.exists() && markerDir.isDirectory) {
                return true
            }
        }

        return false
    }

    private fun showAutoIntegrateNotification(project: Project, configName: String, runType: RunType) {
        try {
            val notificationGroup = NotificationGroupManager.getInstance()
                .getNotificationGroup("TrueFlow Notifications")

            val notification = notificationGroup.createNotification(
                "Enable TrueFlow for ${runType.displayName}?",
                "Running '$configName' without code tracing. Enable TrueFlow to visualize execution flow, find dead code, and track performance.",
                NotificationType.INFORMATION
            )

            // Add action to open Auto-Integrate
            notification.addAction(object : com.intellij.notification.NotificationAction("Auto-Integrate") {
                override fun actionPerformed(e: com.intellij.openapi.actionSystem.AnActionEvent, notification: com.intellij.notification.Notification) {
                    notification.expire()
                    openTrueFlowAndAutoIntegrate(project)
                }
            })

            // Add action to dismiss permanently for this project
            notification.addAction(object : com.intellij.notification.NotificationAction("Don't Ask Again") {
                override fun actionPerformed(e: com.intellij.openapi.actionSystem.AnActionEvent, notification: com.intellij.notification.Notification) {
                    notification.expire()
                    val projectKey = project.basePath ?: project.name
                    dismissedProjects.add(projectKey)
                }
            })

            // Add action to dismiss temporarily
            notification.addAction(object : com.intellij.notification.NotificationAction("Not Now") {
                override fun actionPerformed(e: com.intellij.openapi.actionSystem.AnActionEvent, notification: com.intellij.notification.Notification) {
                    notification.expire()
                }
            })

            notification.notify(project)

        } catch (e: Exception) {
            PluginLogger.warn("[ExecutionListener] Failed to show notification: ${e.message}")
        }
    }

    private fun showMissingTracingNotification(project: Project, configName: String, runType: RunType) {
        try {
            val notificationGroup = NotificationGroupManager.getInstance()
                .getNotificationGroup("TrueFlow Notifications")

            val notification = notificationGroup.createNotification(
                "TrueFlow: ${runType.displayName} Tracing Not Active",
                "Config '$configName' is running without tracing. Use a TrueFlow-enabled run configuration for full instrumentation.",
                NotificationType.INFORMATION
            )

            // Add action to open TrueFlow panel
            notification.addAction(object : com.intellij.notification.NotificationAction("Open TrueFlow") {
                override fun actionPerformed(e: com.intellij.openapi.actionSystem.AnActionEvent, notification: com.intellij.notification.Notification) {
                    notification.expire()
                    openTrueFlowPanel(project)
                }
            })

            // Add dismiss
            notification.addAction(object : com.intellij.notification.NotificationAction("Ignore") {
                override fun actionPerformed(e: com.intellij.openapi.actionSystem.AnActionEvent, notification: com.intellij.notification.Notification) {
                    notification.expire()
                }
            })

            notification.notify(project)

        } catch (e: Exception) {
            PluginLogger.warn("[ExecutionListener] Failed to show notification: ${e.message}")
        }
    }

    private fun openTrueFlowAndAutoIntegrate(project: Project) {
        javax.swing.SwingUtilities.invokeLater {
            val toolWindowManager = ToolWindowManager.getInstance(project)
            val toolWindow = toolWindowManager.getToolWindow("TrueFlow")

            if (toolWindow != null) {
                toolWindow.show {
                    // After showing, try to trigger Auto-Integrate
                    // The tool window content should handle this
                    PluginLogger.info("[ExecutionListener] TrueFlow panel opened for Auto-Integrate")
                }
            }
        }
    }

    private fun openTrueFlowPanel(project: Project) {
        javax.swing.SwingUtilities.invokeLater {
            val toolWindowManager = ToolWindowManager.getInstance(project)
            val toolWindow = toolWindowManager.getToolWindow("TrueFlow")
            toolWindow?.show()
        }
    }
}
