package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import com.intellij.openapi.project.ProjectManagerListener

class ProjectOpenListener : ProjectManagerListener {
    override fun projectOpened(project: Project) {
        // Initialize logging and trace watcher when project opens
        PluginLogger.initialize(project)
        PluginLogger.info("Project opened: ${project.name}")
        PluginLogger.info("Project base path: ${project.basePath}")
    }

    override fun projectClosed(project: Project) {
        // Clean up watchers when project closes
        PluginLogger.info("Project closed: ${project.name}")
        PluginLogger.close(project)
    }
}
