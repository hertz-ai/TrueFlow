package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.SimpleToolWindowPanel
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.ui.JBUI
import java.awt.BorderLayout
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import javax.swing.*

/**
 * DEPRECATED: This class has been superseded by EnhancedLearningFlowToolWindow.
 *
 * EnhancedLearningFlowToolWindow provides a 9-tab interface with:
 * - Diagram, Performance, Dead Code, Call Trace, Flamegraph,
 * - SQL Analyzer, Live Metrics, Distributed Architecture, Manim Videos
 *
 * This class is NOT registered in plugin.xml and is kept for reference only.
 *
 * @see EnhancedLearningFlowToolWindow
 */
@Deprecated("Use EnhancedLearningFlowToolWindow instead")
class LearningFlowToolWindow(private val project: Project) {

    private val mainPanel = SimpleToolWindowPanel(true, true)
    private val diagramPanel = JBPanel<JBPanel<*>>(BorderLayout())
    private val statsPanel = JBPanel<JBPanel<*>>(GridBagLayout())
    private val eventDetailsPanel = JBPanel<JBPanel<*>>(BorderLayout())

    private var currentSessionLabel = JBLabel("No session loaded")
    private var durationLabel = JBLabel("Duration: --")
    private var apiCallsLabel = JBLabel("API Calls: 0")
    private var correctionsLabel = JBLabel("Corrections: 0")
    private var learningEventsLabel = JBLabel("Learning Events: 0")
    private var oneShotRateLabel = JBLabel("1-Shot Rate: --%")

    private val diagramTextArea = JTextArea()
    private val eventDetailsTextArea = JTextArea()

    init {
        createToolbar()
        createMainContent()
        createStatsPanel()
        createDiagramPanel()
        createEventDetailsPanel()
        layoutComponents()
    }

    private fun createToolbar() {
        val toolbar = JToolBar()
        toolbar.isFloatable = false

        // Refresh button
        val refreshButton = JButton("Refresh")
        refreshButton.addActionListener {
            refreshDiagram()
        }
        toolbar.add(refreshButton)

        toolbar.addSeparator()

        // Select directory button
        val selectDirButton = JButton("Select Trace Directory")
        selectDirButton.addActionListener {
            selectTraceDirectory()
        }
        toolbar.add(selectDirButton)

        toolbar.addSeparator()

        // Export button
        val exportButton = JButton("Export")
        exportButton.addActionListener {
            exportDiagram()
        }
        toolbar.add(exportButton)

        mainPanel.toolbar = toolbar
    }

    private fun createMainContent() {
        val contentPanel = JBPanel<JBPanel<*>>(BorderLayout())
        contentPanel.border = JBUI.Borders.empty(5)
        mainPanel.setContent(contentPanel)
    }

    private fun createStatsPanel() {
        statsPanel.border = BorderFactory.createTitledBorder("Session Statistics")

        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = GridBagConstraints.RELATIVE
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = JBUI.insets(2, 5)

        // Session info
        statsPanel.add(currentSessionLabel, gbc)
        statsPanel.add(durationLabel, gbc)

        // Stats
        statsPanel.add(createStatLabel("Statistics:", true), gbc)
        statsPanel.add(apiCallsLabel, gbc)
        statsPanel.add(correctionsLabel, gbc)
        statsPanel.add(learningEventsLabel, gbc)
        statsPanel.add(oneShotRateLabel, gbc)
    }

    private fun createStatLabel(text: String, bold: Boolean = false): JBLabel {
        val label = JBLabel(text)
        if (bold) {
            val font = label.font
            label.font = font.deriveFont(font.style or java.awt.Font.BOLD)
        }
        return label
    }

    private fun createDiagramPanel() {
        diagramPanel.border = BorderFactory.createTitledBorder("Learning Flow Diagram")

        // For now, use text area to display Mermaid code
        // In production, this would be rendered as actual diagram
        diagramTextArea.isEditable = false
        diagramTextArea.lineWrap = true
        diagramTextArea.wrapStyleWord = true
        diagramTextArea.text = """
            ```mermaid
            sequenceDiagram
                participant Client
                participant API
                participant Learner

                Client->>API: chat(messages)
                API->>Learner: encode
                Learner-->>API: response

                Note: Load a trace to see diagram
            ```
        """.trimIndent()

        val scrollPane = JBScrollPane(diagramTextArea)
        diagramPanel.add(scrollPane, BorderLayout.CENTER)

        // Add info label
        val infoLabel = JBLabel("Select a trace directory to visualize learning flows")
        infoLabel.foreground = JBColor.GRAY
        infoLabel.border = JBUI.Borders.empty(5)
        diagramPanel.add(infoLabel, BorderLayout.NORTH)
    }

    private fun createEventDetailsPanel() {
        eventDetailsPanel.border = BorderFactory.createTitledBorder("Event Details")

        eventDetailsTextArea.isEditable = false
        eventDetailsTextArea.lineWrap = true
        eventDetailsTextArea.wrapStyleWord = true
        eventDetailsTextArea.text = "Click on an event in the diagram to see details"

        val scrollPane = JBScrollPane(eventDetailsTextArea)
        eventDetailsPanel.add(scrollPane, BorderLayout.CENTER)
    }

    private fun layoutComponents() {
        val splitPane = JSplitPane(JSplitPane.VERTICAL_SPLIT)
        splitPane.topComponent = createTopPanel()
        splitPane.bottomComponent = eventDetailsPanel
        splitPane.resizeWeight = 0.7

        mainPanel.add(splitPane, BorderLayout.CENTER)
    }

    private fun createTopPanel(): JPanel {
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())

        val leftSplitPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT)
        leftSplitPane.leftComponent = statsPanel
        leftSplitPane.rightComponent = diagramPanel
        leftSplitPane.resizeWeight = 0.3

        topPanel.add(leftSplitPane, BorderLayout.CENTER)

        return topPanel
    }

    fun getContent(): JComponent = mainPanel

    private fun refreshDiagram() {
        // TODO: Implement diagram refresh
        JOptionPane.showMessageDialog(
            mainPanel,
            "Diagram refresh functionality will reload the latest trace",
            "Refresh",
            JOptionPane.INFORMATION_MESSAGE
        )
    }

    private fun selectTraceDirectory() {
        val fileChooser = JFileChooser()
        fileChooser.fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
        fileChooser.dialogTitle = "Select Trace Directory"

        val result = fileChooser.showOpenDialog(mainPanel)
        if (result == JFileChooser.APPROVE_OPTION) {
            val directory = fileChooser.selectedFile
            loadTracesFromDirectory(directory.absolutePath)
        }
    }

    private fun loadTracesFromDirectory(directoryPath: String) {
        // TODO: Implement trace loading
        JOptionPane.showMessageDialog(
            mainPanel,
            "Loading traces from: $directoryPath",
            "Load Traces",
            JOptionPane.INFORMATION_MESSAGE
        )

        // Update UI with mock data for demonstration
        currentSessionLabel.text = "Session: session_20250108_143022_0"
        durationLabel.text = "Duration: 34.6s"
        apiCallsLabel.text = "API Calls: 5"
        correctionsLabel.text = "Corrections: 2"
        learningEventsLabel.text = "Learning Events: 2"
        oneShotRateLabel.text = "1-Shot Rate: 50.0%"

        // Update diagram
        diagramTextArea.text = """
            ```mermaid
            sequenceDiagram
                autonumber
                participant Client
                participant API
                participant Agent
                participant Learner
                participant TCM

                Client->>API: chat("What is diabetes?")
                API->>Agent: step(action, observation)
                Agent->>Agent: encode_vision_language
                Agent->>Learner: generate_response
                Learner-->>API: response

                Client->>API: expert_correction
                API->>Learner: add_factual_correction
                Learner->>TCM: predict_next_state
                Note over TCM: Error: 0.43
                Learner->>Learner: learn_from_reality
                Note over Learner: Error reduction: 0.31
                Learner-->>API: success
            ```
        """.trimIndent()

        // Update event details
        eventDetailsTextArea.text = """
            Event: learn_from_reality
            Type: learning | Category: one_shot_learning
            Duration: 1234.5ms | Memory: +12.3 MB

            Learning Stats:
              error_before: 0.43
              error_after: 0.12
              error_reduction: 0.31 ✓
              true_one_shot_success: True ✓

            Model Updates:
              lora_updated: True (slot 47)
              ssm_updated: False

            Source: reality_grounded_learner.py:390
        """.trimIndent()
    }

    private fun exportDiagram() {
        val fileChooser = JFileChooser()
        fileChooser.dialogTitle = "Export Diagram"
        fileChooser.selectedFile = java.io.File("learning_flow_diagram.md")

        val result = fileChooser.showSaveDialog(mainPanel)
        if (result == JFileChooser.APPROVE_OPTION) {
            val file = fileChooser.selectedFile
            try {
                file.writeText(diagramTextArea.text)
                JOptionPane.showMessageDialog(
                    mainPanel,
                    "Diagram exported to: ${file.absolutePath}",
                    "Export Successful",
                    JOptionPane.INFORMATION_MESSAGE
                )
            } catch (e: Exception) {
                JOptionPane.showMessageDialog(
                    mainPanel,
                    "Error exporting diagram: ${e.message}",
                    "Export Error",
                    JOptionPane.ERROR_MESSAGE
                )
            }
        }
    }

    fun updateSession(sessionData: Map<String, Any>) {
        // Update statistics from session data
        currentSessionLabel.text = "Session: ${sessionData["session_id"]}"
        durationLabel.text = "Duration: ${sessionData["duration_s"]}s"
        apiCallsLabel.text = "API Calls: ${sessionData["total_api_calls"]}"
        correctionsLabel.text = "Corrections: ${sessionData["total_corrections"]}"
        learningEventsLabel.text = "Learning Events: ${sessionData["total_learning_events"]}"
        oneShotRateLabel.text = "1-Shot Rate: ${sessionData["one_shot_success_rate"]}%"
    }

    fun updateDiagram(mermaidCode: String) {
        diagramTextArea.text = mermaidCode
    }

    fun updateEventDetails(details: String) {
        eventDetailsTextArea.text = details
    }
}
