package com.crawl4ai.learningviz

import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project

/**
 * Persistent settings for trace session auto-save/restore behavior.
 * Stored in <project>/.idea/trueflow-session-settings.xml
 */
@Service(Service.Level.PROJECT)
@State(
    name = "TraceSessionSettings",
    storages = [Storage("trueflow-session-settings.xml")]
)
class SessionSettings : PersistentStateComponent<SessionSettings.State> {

    data class State(
        var autoSaveEnabled: Boolean = true,
        var autoSaveIntervalMinutes: Int = 5,
        var autoRestoreOnStartup: Boolean = true,
        var maxAutoSavedSessions: Int = 10
    )

    private var myState = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    companion object {
        fun getInstance(project: Project): SessionSettings = project.service()
    }
}
