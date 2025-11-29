package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory

/**
 * DEPRECATED: This factory has been superseded by EnhancedLearningFlowToolWindowFactory.
 *
 * EnhancedLearningFlowToolWindowFactory creates EnhancedLearningFlowToolWindow
 * which provides a 9-tab interface for comprehensive visualization.
 *
 * This class is NOT registered in plugin.xml and is kept for reference only.
 *
 * @see EnhancedLearningFlowToolWindowFactory
 */
@Deprecated("Use EnhancedLearningFlowToolWindowFactory instead")
class LearningFlowToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val learningFlowToolWindow = LearningFlowToolWindow(project)
        val content = ContentFactory.getInstance().createContent(
            learningFlowToolWindow.getContent(),
            "",
            false
        )
        toolWindow.contentManager.addContent(content)
    }

    override fun shouldBeAvailable(project: Project): Boolean = true
}
