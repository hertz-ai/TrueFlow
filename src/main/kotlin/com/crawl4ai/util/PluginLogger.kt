package com.crawl4ai.util

import com.intellij.openapi.diagnostic.Logger
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Centralized logger for PyCharm plugin.
 * Logs to both IntelliJ log and custom log files in .pycharm_plugin/logs/
 */
object PluginLogger {
    private val LOG = Logger.getInstance("com.crawl4ai.plugin")

    private val logDir = File(System.getProperty("user.dir"), ".pycharm_plugin/logs").apply {
        mkdirs()
    }

    private val dateFormatter = DateTimeFormatter.ofPattern("yyyyMMdd")
    private val timeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    /**
     * Get logger for a specific component.
     */
    fun getLogger(componentName: String): ComponentLogger {
        return ComponentLogger(componentName)
    }

    class ComponentLogger(private val componentName: String) {
        private val logFile: File by lazy {
            val date = LocalDateTime.now().format(dateFormatter)
            File(logDir, "${componentName}_${date}.log")
        }

        fun debug(message: String) {
            LOG.debug("[$componentName] $message")
            writeToFile("DEBUG", message)
        }

        fun info(message: String) {
            LOG.info("[$componentName] $message")
            writeToFile("INFO", message)
        }

        fun warn(message: String, throwable: Throwable? = null) {
            LOG.warn("[$componentName] $message", throwable)
            writeToFile("WARN", message, throwable)
        }

        fun error(message: String, throwable: Throwable? = null) {
            LOG.error("[$componentName] $message", throwable)
            writeToFile("ERROR", message, throwable)
        }

        private fun writeToFile(level: String, message: String, throwable: Throwable? = null) {
            try {
                val timestamp = LocalDateTime.now().format(timeFormatter)
                val logLine = "$timestamp | $level | $componentName | $message"

                logFile.appendText("$logLine\n")

                // Add stack trace if exception
                throwable?.let {
                    logFile.appendText("${it.stackTraceToString()}\n")
                }
            } catch (e: Exception) {
                // Fallback to console only if file write fails
                LOG.warn("Failed to write to log file: ${e.message}")
            }
        }
    }

    /**
     * Clean up old log files.
     */
    fun cleanupOldLogs(days: Int = 7) {
        try {
            val cutoffTime = System.currentTimeMillis() - (days * 24 * 60 * 60 * 1000L)
            logDir.listFiles()?.forEach { file ->
                if (file.lastModified() < cutoffTime && file.extension == "log") {
                    file.delete()
                }
            }
        } catch (e: Exception) {
            LOG.warn("Failed to cleanup old logs: ${e.message}")
        }
    }
}
