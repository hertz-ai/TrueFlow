package com.crawl4ai.learningviz.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.wm.ToolWindowManager

class RefreshAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val toolWindow = ToolWindowManager.getInstance(project)
            .getToolWindow("Learning Flow Visualizer") ?: return

        // Trigger refresh in tool window
        // Implementation would communicate with LearningFlowToolWindow
    }
}
