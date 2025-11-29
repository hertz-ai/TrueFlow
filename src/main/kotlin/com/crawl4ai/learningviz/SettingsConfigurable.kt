package com.crawl4ai.learningviz

import com.intellij.openapi.options.Configurable
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JLabel
import java.awt.BorderLayout

class SettingsConfigurable : Configurable {

    private var settingsPanel: JPanel? = null

    override fun getDisplayName(): String = "Learning Flow Visualizer"

    override fun createComponent(): JComponent {
        settingsPanel = JPanel(BorderLayout())
        settingsPanel?.add(JLabel("Settings panel - Coming soon!"), BorderLayout.CENTER)
        return settingsPanel!!
    }

    override fun isModified(): Boolean = false

    override fun apply() {
        // Save settings
    }

    override fun reset() {
        // Reset to defaults
    }

    override fun disposeUIResources() {
        settingsPanel = null
    }
}
