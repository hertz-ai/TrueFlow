package com.crawl4ai.learningviz

import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory

/**
 * Factory for creating the enhanced learning flow tool window with PlantUML support,
 * dead code detection, and performance profiling.
 */
class EnhancedLearningFlowToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        try {
            PluginLogger.info("Creating tool window content for project: ${project.name}")

            val enhancedToolWindow = EnhancedLearningFlowToolWindow(project)
            val contentFactory = ContentFactory.getInstance()
            val content = contentFactory.createContent(enhancedToolWindow.getContent(), "", false)

            // Register disposal for ManimVideoPanel
            content.setDisposer(object : Disposable {
                override fun dispose() {
                    enhancedToolWindow.dispose()
                }
            })

            toolWindow.contentManager.addContent(content)

            PluginLogger.info("Tool window content created successfully")
        } catch (e: Exception) {
            PluginLogger.error("Failed to create tool window content", e)
        }
    }

    override fun shouldBeAvailable(project: Project): Boolean {
        val available = true  // Always available for all projects
        PluginLogger.debug("Tool window availability check for ${project.name}: $available")
        return available
    }
}
