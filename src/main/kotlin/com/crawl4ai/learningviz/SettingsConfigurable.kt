package com.crawl4ai.learningviz

import com.intellij.openapi.options.Configurable
import com.intellij.openapi.project.Project
import com.intellij.util.ui.JBUI
import javax.swing.*
import java.awt.GridBagConstraints
import java.awt.GridBagLayout

class SettingsConfigurable(private val project: Project) : Configurable {

    private var settingsPanel: JPanel? = null
    private lateinit var autoSaveCheckbox: JCheckBox
    private lateinit var autoSaveIntervalSpinner: JSpinner
    private lateinit var autoRestoreCheckbox: JCheckBox
    private lateinit var maxSessionsSpinner: JSpinner

    override fun getDisplayName(): String = "TrueFlow"

    override fun createComponent(): JComponent {
        val settings = SessionSettings.getInstance(project)
        val state = settings.state

        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints().apply {
            anchor = GridBagConstraints.WEST
            insets = JBUI.insets(4)
            fill = GridBagConstraints.HORIZONTAL
        }

        // Section header
        gbc.gridx = 0; gbc.gridy = 0; gbc.gridwidth = 2
        panel.add(JLabel("<html><b>Session Auto-Save</b></html>"), gbc)

        // Auto-save enabled
        gbc.gridy = 1; gbc.gridwidth = 2
        autoSaveCheckbox = JCheckBox("Enable auto-save of trace sessions", state.autoSaveEnabled)
        autoSaveCheckbox.toolTipText = "Automatically save trace data at regular intervals"
        panel.add(autoSaveCheckbox, gbc)

        // Auto-save interval
        gbc.gridy = 2; gbc.gridwidth = 1
        panel.add(JLabel("Auto-save interval (minutes):"), gbc)
        gbc.gridx = 1
        autoSaveIntervalSpinner = JSpinner(SpinnerNumberModel(state.autoSaveIntervalMinutes, 1, 60, 1))
        autoSaveIntervalSpinner.toolTipText = "How often to auto-save trace data (1-60 minutes)"
        panel.add(autoSaveIntervalSpinner, gbc)

        // Section header
        gbc.gridx = 0; gbc.gridy = 3; gbc.gridwidth = 2
        gbc.insets = JBUI.insets(12, 4, 4, 4)
        panel.add(JLabel("<html><b>Session Restore</b></html>"), gbc)
        gbc.insets = JBUI.insets(4)

        // Auto-restore on startup
        gbc.gridy = 4; gbc.gridwidth = 2
        autoRestoreCheckbox = JCheckBox("Restore most recent session on startup", state.autoRestoreOnStartup)
        autoRestoreCheckbox.toolTipText = "Load saved trace data when IDE opens (skipped if live trace server detected)"
        panel.add(autoRestoreCheckbox, gbc)

        // Max auto-saved sessions
        gbc.gridy = 5; gbc.gridwidth = 1
        panel.add(JLabel("Max auto-saved sessions:"), gbc)
        gbc.gridx = 1
        maxSessionsSpinner = JSpinner(SpinnerNumberModel(state.maxAutoSavedSessions, 5, 50, 5))
        maxSessionsSpinner.toolTipText = "Oldest auto-saves are deleted when this limit is reached"
        panel.add(maxSessionsSpinner, gbc)

        // Spacer
        gbc.gridx = 0; gbc.gridy = 6; gbc.gridwidth = 2; gbc.weighty = 1.0
        gbc.fill = GridBagConstraints.BOTH
        panel.add(JPanel(), gbc)

        settingsPanel = panel
        return panel
    }

    override fun isModified(): Boolean {
        val state = SessionSettings.getInstance(project).state
        return autoSaveCheckbox.isSelected != state.autoSaveEnabled ||
                (autoSaveIntervalSpinner.value as Int) != state.autoSaveIntervalMinutes ||
                autoRestoreCheckbox.isSelected != state.autoRestoreOnStartup ||
                (maxSessionsSpinner.value as Int) != state.maxAutoSavedSessions
    }

    override fun apply() {
        val settings = SessionSettings.getInstance(project)
        settings.loadState(SessionSettings.State(
            autoSaveEnabled = autoSaveCheckbox.isSelected,
            autoSaveIntervalMinutes = autoSaveIntervalSpinner.value as Int,
            autoRestoreOnStartup = autoRestoreCheckbox.isSelected,
            maxAutoSavedSessions = maxSessionsSpinner.value as Int
        ))
    }

    override fun reset() {
        val state = SessionSettings.getInstance(project).state
        autoSaveCheckbox.isSelected = state.autoSaveEnabled
        autoSaveIntervalSpinner.value = state.autoSaveIntervalMinutes
        autoRestoreCheckbox.isSelected = state.autoRestoreOnStartup
        maxSessionsSpinner.value = state.maxAutoSavedSessions
    }

    override fun disposeUIResources() {
        settingsPanel = null
    }
}
