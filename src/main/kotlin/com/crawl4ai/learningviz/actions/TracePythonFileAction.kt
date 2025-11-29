package com.crawl4ai.learningviz.actions

import com.crawl4ai.learningviz.PluginLogger
import com.intellij.execution.ProgramRunnerUtil
import com.intellij.execution.RunManager
import com.intellij.execution.executors.DefaultRunExecutor
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.vfs.VirtualFile

/**
 * Action to run a Python file with TrueFlow tracing enabled.
 *
 * This action is only available when the Python plugin is installed.
 * It appears in the context menu for Python files.
 */
class TracePythonFileAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project: Project = e.project ?: return
        val file: VirtualFile = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return

        if (!file.name.endsWith(".py")) {
            Messages.showWarningDialog(
                project,
                "Please select a Python file to trace.",
                "TrueFlow"
            )
            return
        }

        // Try to find or create a run configuration with TrueFlow environment variables
        try {
            runWithTracing(project, file)
        } catch (ex: Exception) {
            PluginLogger.warn("Failed to run with tracing: ${ex.message}")
            Messages.showErrorDialog(
                project,
                "Failed to run with tracing: ${ex.message}\n\nPlease use Auto-Integrate first.",
                "TrueFlow Error"
            )
        }
    }

    private fun runWithTracing(project: Project, file: VirtualFile) {
        val runManager = RunManager.getInstance(project)

        // Look for existing TrueFlow configuration
        val existingConfig = runManager.allSettings.find {
            it.name.contains("TrueFlow") || it.name.contains("trueflow")
        }

        if (existingConfig != null) {
            // Use existing configuration
            runManager.selectedConfiguration = existingConfig
            ProgramRunnerUtil.executeConfiguration(existingConfig, DefaultRunExecutor.getRunExecutorInstance())
        } else {
            // No TrueFlow configuration found - suggest using Auto-Integrate
            Messages.showInfoMessage(
                project,
                "No TrueFlow run configuration found.\n\n" +
                "Please use 'Auto-Integrate into Repo' first to set up TrueFlow tracing.\n" +
                "Go to: Tools -> TrueFlow -> Auto-Integrate into Repo",
                "TrueFlow Setup Required"
            )
        }
    }

    override fun update(e: AnActionEvent) {
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)
        val isPythonFile = file?.name?.endsWith(".py") == true

        e.presentation.isEnabled = e.project != null && isPythonFile
        e.presentation.isVisible = isPythonFile
    }
}
