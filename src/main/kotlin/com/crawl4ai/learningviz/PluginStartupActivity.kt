package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.StartupActivity
import com.intellij.openapi.wm.ToolWindowManager

/**
 * Automatically opens the SequenceDiagramPython tool window when a project is opened.
 */
class PluginStartupActivity : StartupActivity {
    override fun runActivity(project: Project) {
        try {
            // Initialize logging first
            PluginLogger.initialize(project)
            PluginLogger.info("Plugin startup activity started for project: ${project.name}")

            // Auto-open the tool window when project opens
            val toolWindowManager = ToolWindowManager.getInstance(project)
            val toolWindow = toolWindowManager.getToolWindow("SequenceDiagramPython")

            if (toolWindow != null) {
                if (!toolWindow.isVisible) {
                    toolWindow.show()
                    PluginLogger.info("Tool window opened automatically")
                } else {
                    PluginLogger.info("Tool window already visible")
                }
            } else {
                PluginLogger.warn("Tool window 'SequenceDiagramPython' not found")
            }

            PluginLogger.info("Plugin startup completed successfully")
        } catch (e: Exception) {
            PluginLogger.error("Error during plugin startup", e)
        }
    }
}
