package com.crawl4ai.learningviz.actions

import com.crawl4ai.learningviz.AutoIntegrationDialog
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project

/**
 * Action to open the auto-integration dialog.
 *
 * This allows users to automatically integrate tracing into any Python repository
 * by just selecting the main entry point.
 */
class AutoIntegrateAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project: Project = e.project ?: return

        val dialog = AutoIntegrationDialog(project)
        dialog.show()
    }

    override fun update(e: AnActionEvent) {
        // Only enable if we have a project
        e.presentation.isEnabled = e.project != null
    }
}
