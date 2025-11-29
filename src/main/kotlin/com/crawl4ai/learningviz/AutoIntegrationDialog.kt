package com.crawl4ai.learningviz

import com.intellij.execution.RunManager
import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.ConfigurationType
import com.intellij.openapi.fileChooser.FileChooser
import com.intellij.openapi.fileChooser.FileChooserDescriptor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.io.File
import javax.swing.*

/**
 * Dialog for automatically integrating auto-instrumentation into any Python repository.
 *
 * IMPORTANT: NEVER modifies user code! All integration via:
 * - Environment variables in run configurations
 * - .env file (optional)
 * - PyCharm settings
 *
 * User just selects the main entry point (e.g., main.py, app.py, manage.py)
 * and the dialog handles the rest - NO CODE CHANGES!
 */
class AutoIntegrationDialog(private val project: Project) : DialogWrapper(project) {

    private val entryPointField = JBTextField(40)
    private val entryPointButton = JButton("Browse...")
    private val traceDirectoryField = JBTextField(40)
    private val traceDirButton = JButton("Browse...")

    private val integrationMethodCombo = JComboBox(arrayOf(
        "PyCharm Run Configuration (Recommended - Zero code changes)",
        "Environment Variable File (.env - No code changes)"
    ))

    private val modulesToTraceField = JBTextField(40)
    private val excludeModulesField = JBTextField(40)

    private val createRunConfigCheckbox = JCheckBox("Create PyCharm run configuration", true)
    private val openTraceDirCheckbox = JCheckBox("Open trace directory after integration", true)

    private var selectedEntryPoint: VirtualFile? = null
    private var selectedTraceDir: VirtualFile? = null

    init {
        title = "Auto-Integrate Tracing into Repository"
        init()

        entryPointButton.addActionListener {
            selectEntryPoint()
        }

        traceDirButton.addActionListener {
            selectTraceDirectory()
        }

        // Set default trace directory
        traceDirectoryField.text = "${project.basePath}/traces"
    }

    override fun createCenterPanel(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = java.awt.Insets(5, 5, 5, 5)

        // Title
        val titleLabel = JBLabel("<html><h2>Auto-Integrate Tracing</h2><p>Select your Python entry point and configure tracing</p></html>")
        gbc.gridwidth = 3
        panel.add(titleLabel, gbc)

        gbc.gridy++
        gbc.gridwidth = 1

        // Entry point selection
        panel.add(JBLabel("Entry Point:"), gbc)
        gbc.gridx = 1
        entryPointField.isEditable = false
        entryPointField.toolTipText = "Entry point: .py, .bat, .sh, .ps1, docker-compose.yml, Dockerfile"
        panel.add(entryPointField, gbc)
        gbc.gridx = 2
        panel.add(entryPointButton, gbc)

        // Trace directory
        gbc.gridy++
        gbc.gridx = 0
        panel.add(JBLabel("Trace Directory:"), gbc)
        gbc.gridx = 1
        traceDirectoryField.toolTipText = "Where to save trace files"
        panel.add(traceDirectoryField, gbc)
        gbc.gridx = 2
        panel.add(traceDirButton, gbc)

        // Integration method
        gbc.gridy++
        gbc.gridx = 0
        panel.add(JBLabel("Integration Method:"), gbc)
        gbc.gridx = 1
        gbc.gridwidth = 2
        integrationMethodCombo.toolTipText = "How to enable tracing"
        panel.add(integrationMethodCombo, gbc)

        gbc.gridy++
        gbc.gridwidth = 3
        gbc.gridx = 0
        panel.add(JSeparator(), gbc)

        // Advanced options
        gbc.gridy++
        panel.add(JBLabel("<html><h3>Advanced Options</h3></html>"), gbc)

        // Modules to trace
        gbc.gridy++
        gbc.gridwidth = 1
        panel.add(JBLabel("Modules to Trace:"), gbc)
        gbc.gridx = 1
        gbc.gridwidth = 2
        modulesToTraceField.toolTipText = "Comma-separated list (e.g., myapp,mylib). Leave empty to trace all."
        panel.add(modulesToTraceField, gbc)

        // Exclude modules
        gbc.gridy++
        gbc.gridx = 0
        gbc.gridwidth = 1
        panel.add(JBLabel("Exclude Modules:"), gbc)
        gbc.gridx = 1
        gbc.gridwidth = 2
        excludeModulesField.text = "test,tests,pytest,unittest"
        excludeModulesField.toolTipText = "Comma-separated list of modules to exclude"
        panel.add(excludeModulesField, gbc)

        // Checkboxes
        gbc.gridy++
        gbc.gridx = 0
        gbc.gridwidth = 3
        panel.add(createRunConfigCheckbox, gbc)

        gbc.gridy++
        panel.add(openTraceDirCheckbox, gbc)

        // Info panel
        gbc.gridy++
        val infoPanel = JPanel()
        infoPanel.border = BorderFactory.createTitledBorder("What This Does")
        infoPanel.layout = BoxLayout(infoPanel, BoxLayout.Y_AXIS)

        infoPanel.add(JBLabel("\u2022 Automatically enables zero-code auto-instrumentation"))
        infoPanel.add(JBLabel("\u2022 Creates trace directory for output files"))
        infoPanel.add(JBLabel("\u2022 Optionally creates PyCharm run configuration"))
        infoPanel.add(JBLabel("\u2022 No manual setup required - just click OK!"))

        panel.add(infoPanel, gbc)

        return panel
    }

    private fun selectEntryPoint() {
        val descriptor = FileChooserDescriptor(true, false, false, false, false, false)
            .withTitle("Select Entry Point")
            .withDescription("Select entry point: .py, .bat, .sh, .ps1, docker-compose.yml, Dockerfile, etc.")
            .withFileFilter { file ->
                val ext = file.extension?.lowercase()
                ext in listOf("py", "bat", "sh", "ps1", "cmd", "yml", "yaml") ||
                file.name.lowercase() in listOf("dockerfile", "docker-compose.yml", "docker-compose.yaml")
            }

        val file = FileChooser.chooseFile(descriptor, project, project.baseDir)
        if (file != null) {
            selectedEntryPoint = file
            entryPointField.text = file.path
        }
    }

    private fun selectTraceDirectory() {
        val descriptor = FileChooserDescriptor(false, true, false, false, false, false)
            .withTitle("Select Trace Directory")
            .withDescription("Where to save trace files")

        val file = FileChooser.chooseFile(descriptor, project, project.baseDir)
        if (file != null) {
            selectedTraceDir = file
            traceDirectoryField.text = file.path
        }
    }

    override fun doOKAction() {
        if (selectedEntryPoint == null) {
            Messages.showErrorDialog(project, "Please select a Python entry point", "Error")
            return
        }

        try {
            performIntegration()
            super.doOKAction()
        } catch (e: Exception) {
            Messages.showErrorDialog(project, "Integration failed: ${e.message}", "Error")
        }
    }

    private fun performIntegration() {
        val entryPoint = selectedEntryPoint ?: return
        val traceDir = traceDirectoryField.text
        val integrationMethod = integrationMethodCombo.selectedIndex
        val modulesToTrace = modulesToTraceField.text.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val excludeModules = excludeModulesField.text.split(",").map { it.trim() }.filter { it.isNotEmpty() }

        // Create trace directory
        val traceDirFile = File(traceDir)
        if (!traceDirFile.exists()) {
            traceDirFile.mkdirs()
        }

        // IMPORTANT: NEVER modify user code - always use environment variables!
        when (integrationMethod) {
            0 -> integrateViaRunConfiguration(entryPoint, traceDir, modulesToTrace, excludeModules)
            1 -> integrateViaEnvFile(entryPoint, traceDir, modulesToTrace, excludeModules)
        }

        // Create run configuration (always - this is the main integration method)
        createRunConfiguration(entryPoint, traceDir, modulesToTrace, excludeModules)

        // Open trace directory if requested
        if (openTraceDirCheckbox.isSelected) {
            val watcherService = project.getService(TraceWatcherService::class.java)
            watcherService.watchDirectory(traceDirFile)
        }

        // Show success message
        val method = if (integrationMethod == 0) "PyCharm Run Configuration" else "Environment File (.env)"
        val message = """
            Integration complete! NO CODE CHANGES MADE.

            Entry point: ${entryPoint.name}
            Trace directory: $traceDir
            Method: $method

            Next steps:
            1. Run "${entryPoint.nameWithoutExtension}" configuration (green play button)
            2. Open "Learning Flow Visualizer" tool window
            3. View traces in real-time!
        """.trimIndent()

        Messages.showInfoMessage(project, message, "Integration Successful")
    }

    private fun integrateViaRunConfiguration(
        entryPoint: VirtualFile,
        traceDir: String,
        modulesToTrace: List<String>,
        excludeModules: List<String>
    ) {
        // No file changes - all via run configuration environment variables
    }

    private fun integrateViaEnvFile(
        entryPoint: VirtualFile,
        traceDir: String,
        modulesToTrace: List<String>,
        excludeModules: List<String>
    ) {
        // Create or update .env file (NO CODE CHANGES!)
        val envFile = File("${project.basePath}/.env")

        val envVars = buildMap {
            put("CRAWL4AI_AUTO_TRACE", "1")
            put("CRAWL4AI_TRACE_DIR", traceDir)

            if (modulesToTrace.isNotEmpty()) {
                put("CRAWL4AI_TRACE_MODULES", modulesToTrace.joinToString(","))
            }

            if (excludeModules.isNotEmpty()) {
                put("CRAWL4AI_EXCLUDE_MODULES", excludeModules.joinToString(","))
            }
        }

        // Append to .env file (or create if doesn't exist)
        val envContent = buildString {
            if (envFile.exists()) {
                appendLine(envFile.readText())
            }

            appendLine("\n# Auto-instrumentation - Added by Learning Flow Visualizer")
            envVars.forEach { (key, value) ->
                appendLine("$key=$value")
            }
        }

        envFile.writeText(envContent)
    }

    private fun copyRuntimeInjectorToProject() {
        // Copy runtime_instrumentor.py, sitecustomize.py, and enable_tracing.bat to project (embedded in plugin JAR)
        val pluginDir = File("${project.basePath}/.pycharm_plugin")
        pluginDir.mkdirs()

        // Copy python_runtime_instrumentor.py
        val injectorSource = javaClass.getResourceAsStream("/runtime_injector/python_runtime_instrumentor.py")
        val injectorDest = File(pluginDir, "python_runtime_instrumentor.py")
        injectorDest.writeBytes(injectorSource?.readBytes() ?: return)

        // Copy sitecustomize.py
        val sitecustomizeSource = javaClass.getResourceAsStream("/runtime_injector/sitecustomize.py")
        val sitecustomizeDest = File(pluginDir, "sitecustomize.py")
        sitecustomizeDest.writeBytes(sitecustomizeSource?.readBytes() ?: return)

        // Copy enable_tracing.bat for direct .bat execution
        val batSource = javaClass.getResourceAsStream("/runtime_injector/enable_tracing.bat")
        if (batSource != null) {
            val batDest = File(pluginDir, "enable_tracing.bat")
            batDest.writeBytes(batSource.readBytes())
            println("[Plugin] Copied enable_tracing.bat to: ${batDest.absolutePath}")
        }

        println("[Plugin] Copied runtime injector to: ${injectorDest.absolutePath}")
        println("[Plugin] Copied sitecustomize.py to: ${sitecustomizeDest.absolutePath}")
    }

    private fun createRunConfiguration(
        entryPoint: VirtualFile,
        traceDir: String,
        modulesToTrace: List<String>,
        excludeModules: List<String>
    ) {
        // Copy runtime injector to project first
        copyRuntimeInjectorToProject()

        val configName = "Trace: ${entryPoint.nameWithoutExtension}"
        val pluginDir = "${project.basePath}/.pycharm_plugin"

        try {
            val runManager = RunManager.getInstance(project)
            val allConfigTypes = ConfigurationType.CONFIGURATION_TYPE_EP.extensionList

            // Determine configuration type based on file extension
            val isBatchFile = entryPoint.name.endsWith(".bat") || entryPoint.name.endsWith(".cmd")
            val isShellScript = entryPoint.name.endsWith(".sh")

            val configType = when {
                isBatchFile || isShellScript -> {
                    // Find Shell Script / Batch configuration type
                    allConfigTypes.find {
                        it.displayName.contains("Shell Script", ignoreCase = true) ||
                        it.displayName.contains("Batch", ignoreCase = true)
                    }
                }
                else -> {
                    // Default to Python for .py files
                    allConfigTypes.find {
                        it.displayName.contains("Python", ignoreCase = true)
                    }
                }
            }

            if (configType == null) {
                val typeName = if (isBatchFile || isShellScript) "Shell Script/Batch" else "Python"
                Messages.showWarningDialog(
                    project,
                    "$typeName plugin not found. Please install the plugin and manually create run configuration.\n\n" +
                    "For .bat files, use: .pycharm_plugin\\enable_tracing.bat ${entryPoint.name}\n\n" +
                    "Environment variables needed:\n" +
                    "PYCHARM_PLUGIN_TRACE_ENABLED=1\n" +
                    "CRAWL4AI_TRACE_DIR=$traceDir\n" +
                    "PYTHONPATH=$pluginDir",
                    "$typeName Plugin Required"
                )
                return
            }

            // Get factory from configuration type
            val factory = configType.configurationFactories.firstOrNull()
            if (factory == null) {
                Messages.showWarningDialog(project, "Could not find configuration factory", "Error")
                return
            }

            // Create new run configuration
            val runConfigSettings = runManager.createConfiguration(configName, factory)
            val runConfig = runConfigSettings.configuration

            // Set script path and environment using reflection
            try {
                if (isBatchFile || isShellScript) {
                    // Batch/Shell configuration uses different methods
                    // Try to set script name/path
                    try {
                        val setScriptMethod = runConfig.javaClass.getMethod("setScriptName", String::class.java)
                        setScriptMethod.invoke(runConfig, entryPoint.path)
                    } catch (e: NoSuchMethodException) {
                        // Try alternative method names
                        val setPathMethod = runConfig.javaClass.getMethod("setScriptPath", String::class.java)
                        setPathMethod.invoke(runConfig, entryPoint.path)
                    }

                    // For batch files, we need to wrap with enable_tracing.bat
                    Messages.showInfoMessage(
                        project,
                        """
                        Batch file detected: ${entryPoint.name}

                        IMPORTANT: To enable tracing for .bat files, you need to:

                        Option 1 (Recommended): Modify the run configuration
                        1. Edit run configuration "$configName"
                        2. Change Script path to: .pycharm_plugin\enable_tracing.bat
                        3. Add Script parameters: ${entryPoint.path}

                        Option 2: Run directly from command line
                        .pycharm_plugin\enable_tracing.bat ${entryPoint.name}

                        The batch configuration was created but needs manual adjustment.
                        """.trimIndent(),
                        "Batch File Configuration"
                    )
                } else {
                    // Python configuration
                    val setScriptPathMethod = runConfig.javaClass.getMethod("setScriptName", String::class.java)
                    setScriptPathMethod.invoke(runConfig, entryPoint.path)

                    val setWorkingDirMethod = runConfig.javaClass.getMethod("setWorkingDirectory", String::class.java)
                    setWorkingDirMethod.invoke(runConfig, project.basePath)

                    // Set environment variables (Python config)
                    val envVars = mutableMapOf<String, String>()
                    envVars["PYCHARM_PLUGIN_TRACE_ENABLED"] = "1"
                    envVars["CRAWL4AI_TRACE_DIR"] = traceDir
                    envVars["PYTHONPATH"] = pluginDir

                    if (modulesToTrace.isNotEmpty()) {
                        envVars["CRAWL4AI_TRACE_MODULES"] = modulesToTrace.joinToString(",")
                    }

                    if (excludeModules.isNotEmpty()) {
                        envVars["CRAWL4AI_EXCLUDE_MODULES"] = excludeModules.joinToString(",")
                    }

                    val setEnvMethod = runConfig.javaClass.getMethod("setEnvs", Map::class.java)
                    setEnvMethod.invoke(runConfig, envVars)
                }

            } catch (e: Exception) {
                println("[Plugin] Warning: Could not set config properties via reflection: ${e.message}")
                e.printStackTrace()
            }

            // Add to run manager
            runManager.addConfiguration(runConfigSettings)
            runManager.selectedConfiguration = runConfigSettings

            // Show success message (only for Python files, batch files showed custom message above)
            if (!isBatchFile && !isShellScript) {
                val envVarsStr = "PYCHARM_PLUGIN_TRACE_ENABLED=1\nCRAWL4AI_TRACE_DIR=$traceDir\nPYTHONPATH=$pluginDir"

                Messages.showInfoMessage(
                    project,
                    """
                    Run configuration created: "$configName"

                    Runtime injection configured:
                    - Runtime injector: .pycharm_plugin/sitecustomize.py
                    - Script: ${entryPoint.name}
                    - Working directory: ${project.basePath}

                    Environment variables:
                    $envVarsStr

                    To run:
                    1. Click the green play button next to "$configName"
                    2. Or select from Run menu
                    3. Traces will appear in: $traceDir

                    To run .bat files directly with tracing:
                    .pycharm_plugin\enable_tracing.bat your_script.bat
                    (This sets up the environment outside PyCharm)
                    """.trimIndent(),
                    "Run Configuration Created"
                )
            }

        } catch (e: Exception) {
            Messages.showErrorDialog(
                project,
                "Failed to create run configuration: ${e.message}\n\n" +
                "Please manually create Python run configuration with:\n" +
                "PYCHARM_PLUGIN_TRACE_ENABLED=1\n" +
                "CRAWL4AI_TRACE_DIR=$traceDir\n" +
                "PYTHONPATH=$pluginDir",
                "Configuration Error"
            )
            e.printStackTrace()
        }
    }
}
