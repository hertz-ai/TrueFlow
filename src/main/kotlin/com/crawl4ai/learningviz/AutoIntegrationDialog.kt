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
 * Dialog for automatically integrating auto-instrumentation into any Python or Java repository.
 *
 * IMPORTANT: NEVER modifies user code! All integration via:
 * - Environment variables in run configurations
 * - VM options (-javaagent) for Java
 * - .env file (optional)
 * - IDE settings
 *
 * User just selects the main entry point and the dialog handles the rest - NO CODE CHANGES!
 *
 * For Python: Uses PYTHONPATH + sitecustomize.py
 * For Java: Uses -javaagent VM option with bundled TrueFlow agent JAR
 */
class AutoIntegrationDialog(private val project: Project) : DialogWrapper(project) {

    // Project type detection
    private enum class ProjectType { PYTHON, JAVA, MIXED, UNKNOWN }
    private var detectedProjectType: ProjectType = ProjectType.UNKNOWN

    private val projectTypeCombo = JComboBox(arrayOf(
        "Python (sitecustomize.py injection)",
        "Java (javaagent injection)"
    ))

    private val entryPointField = JBTextField(40)
    private val entryPointButton = JButton("Browse...")
    private val traceDirectoryField = JBTextField(40)
    private val traceDirButton = JButton("Browse...")

    private val integrationMethodCombo = JComboBox(arrayOf(
        "IDE Run Configuration (Recommended - Zero code changes)",
        "Environment Variable File (.env - No code changes)"
    ))

    private val modulesToTraceField = JBTextField(40)
    private val excludeModulesField = JBTextField(40)

    // Java-specific options
    private val javaPackagesField = JBTextField(40)
    private val javaExcludeField = JBTextField(40)

    private val createRunConfigCheckbox = JCheckBox("Create IDE run configuration", true)
    private val openTraceDirCheckbox = JCheckBox("Open trace directory after integration", true)

    private var selectedEntryPoint: VirtualFile? = null
    private var selectedTraceDir: VirtualFile? = null

    init {
        title = "Auto-Integrate Tracing into Repository"
        init()

        // Detect project type automatically
        detectedProjectType = detectProjectType()
        when (detectedProjectType) {
            ProjectType.JAVA -> projectTypeCombo.selectedIndex = 1
            ProjectType.PYTHON -> projectTypeCombo.selectedIndex = 0
            ProjectType.MIXED -> projectTypeCombo.selectedIndex = 0  // Default to Python for mixed
            ProjectType.UNKNOWN -> projectTypeCombo.selectedIndex = 0
        }

        // Only show project type selector for mixed projects
        // For pure Python or pure Java projects, auto-detect and hide the combo
        projectTypeCombo.isVisible = (detectedProjectType == ProjectType.MIXED)

        entryPointButton.addActionListener {
            selectEntryPoint()
        }

        traceDirButton.addActionListener {
            selectTraceDirectory()
        }

        // Set default trace directory
        traceDirectoryField.text = "${project.basePath}/.trueflow/traces"

        // Update UI when project type changes
        projectTypeCombo.addActionListener {
            updateUIForProjectType()
        }
        updateUIForProjectType()
    }

    private fun detectProjectType(): ProjectType {
        val basePath = project.basePath ?: return ProjectType.UNKNOWN
        val baseDir = File(basePath)

        val hasPython = baseDir.walkTopDown().maxDepth(3).any { it.extension == "py" }
        val hasJava = baseDir.walkTopDown().maxDepth(3).any { it.extension == "java" } ||
                File(baseDir, "pom.xml").exists() ||
                File(baseDir, "build.gradle").exists() ||
                File(baseDir, "build.gradle.kts").exists()

        return when {
            hasPython && hasJava -> ProjectType.MIXED
            hasJava -> ProjectType.JAVA
            hasPython -> ProjectType.PYTHON
            else -> ProjectType.UNKNOWN
        }
    }

    private fun updateUIForProjectType() {
        val isJava = projectTypeCombo.selectedIndex == 1
        // Update field labels and defaults based on project type
        if (isJava) {
            modulesToTraceField.toolTipText = "Java packages to trace (e.g., com.myapp,com.mylib). Leave empty to trace all."
            excludeModulesField.text = "org.springframework,org.hibernate"
            excludeModulesField.toolTipText = "Packages to exclude from tracing"
            entryPointField.toolTipText = "Main class with main() method, or any .java file"
        } else {
            modulesToTraceField.toolTipText = "Comma-separated list (e.g., myapp,mylib). Leave empty to trace all."
            excludeModulesField.text = "test,tests,pytest,unittest"
            excludeModulesField.toolTipText = "Comma-separated list of modules to exclude"
            entryPointField.toolTipText = "Entry point: .py, .bat, .sh, .ps1, docker-compose.yml, Dockerfile"
        }
    }

    override fun createCenterPanel(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = 0
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = java.awt.Insets(5, 5, 5, 5)

        // Title - customize based on detected project type
        val projectTypeDisplay = when (detectedProjectType) {
            ProjectType.JAVA -> "Java/Kotlin"
            ProjectType.PYTHON -> "Python"
            ProjectType.MIXED -> "Python or Java/Kotlin"
            ProjectType.UNKNOWN -> "Python or Java/Kotlin"
        }
        val titleLabel = JBLabel("<html><h2>Auto-Integrate Tracing</h2><p>Detected: <b>$projectTypeDisplay</b> project - Select entry point to configure tracing</p></html>")
        gbc.gridwidth = 3
        panel.add(titleLabel, gbc)

        // Project type selection - only shown for mixed projects
        if (detectedProjectType == ProjectType.MIXED || detectedProjectType == ProjectType.UNKNOWN) {
            gbc.gridy++
            gbc.gridwidth = 1
            panel.add(JBLabel("Project Type:"), gbc)
            gbc.gridx = 1
            gbc.gridwidth = 2
            projectTypeCombo.toolTipText = "Auto-detected as mixed project - select which language to trace"
            panel.add(projectTypeCombo, gbc)
        }

        gbc.gridy++
        gbc.gridx = 0
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
        val isJava = projectTypeCombo.selectedIndex == 1

        val descriptor = FileChooserDescriptor(true, false, false, false, false, false)
            .withTitle("Select Entry Point")
            .withDescription(if (isJava)
                "Select Java/Kotlin main class (.java, .kt) or build file (pom.xml, build.gradle)"
                else "Select entry point: .py, .bat, .sh, .ps1, docker-compose.yml, Dockerfile, etc.")
            .withFileFilter { file ->
                val ext = file.extension?.lowercase()
                if (isJava) {
                    ext in listOf("java", "kt", "kts", "xml", "gradle") ||
                    file.name in listOf("pom.xml", "build.gradle", "build.gradle.kts")
                } else {
                    ext in listOf("py", "bat", "sh", "ps1", "cmd", "yml", "yaml") ||
                    file.name.lowercase() in listOf("dockerfile", "docker-compose.yml", "docker-compose.yaml")
                }
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
        val isJava = projectTypeCombo.selectedIndex == 1
        val entryType = if (isJava) "Java/Kotlin" else "Python"

        if (selectedEntryPoint == null) {
            Messages.showErrorDialog(project, "Please select a $entryType entry point", "Error")
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
        val isJava = projectTypeCombo.selectedIndex == 1

        // Create trace directory
        val traceDirFile = File(traceDir)
        if (!traceDirFile.exists()) {
            traceDirFile.mkdirs()
        }

        if (isJava) {
            // Java/Kotlin integration
            performJavaIntegration(entryPoint, traceDir, modulesToTrace, excludeModules)
        } else {
            // Python integration
            // IMPORTANT: NEVER modify user code - always use environment variables!
            when (integrationMethod) {
                0 -> integrateViaRunConfiguration(entryPoint, traceDir, modulesToTrace, excludeModules)
                1 -> integrateViaEnvFile(entryPoint, traceDir, modulesToTrace, excludeModules)
            }

            // Create run configuration (always - this is the main integration method)
            createRunConfiguration(entryPoint, traceDir, modulesToTrace, excludeModules)
        }

        // Open trace directory if requested
        if (openTraceDirCheckbox.isSelected) {
            val watcherService = project.getService(TraceWatcherService::class.java)
            watcherService.watchDirectory(traceDirFile)
        }

        // Show success message
        val language = if (isJava) "Java/Kotlin" else "Python"
        val method = if (isJava) "-javaagent VM option" else
            (if (integrationMethod == 0) "IDE Run Configuration" else "Environment File (.env)")
        val message = """
            $language Integration complete! NO CODE CHANGES MADE.

            Entry point: ${entryPoint.name}
            Trace directory: $traceDir
            Method: $method

            Next steps:
            1. Run your application using the created configuration
            2. Open "TrueFlow" tool window
            3. View traces in real-time!
        """.trimIndent()

        Messages.showInfoMessage(project, message, "Integration Successful")
    }

    /**
     * Perform Java/Kotlin integration:
     * 1. Extract bundled Java agent JAR to .trueflow/java-agent/
     * 2. Create/modify run configuration with -javaagent VM option
     */
    private fun performJavaIntegration(
        entryPoint: VirtualFile,
        traceDir: String,
        packagesToTrace: List<String>,
        excludePackages: List<String>
    ) {
        // Extract Java agent JAR
        val agentPath = extractJavaAgent()
        if (agentPath == null) {
            Messages.showErrorDialog(
                project,
                "Failed to extract Java agent. Please check plugin installation.",
                "Java Agent Error"
            )
            return
        }

        // Create Java run configuration
        createJavaRunConfiguration(entryPoint, traceDir, packagesToTrace, excludePackages, agentPath)
    }

    /**
     * Extract the bundled Java agent JAR to ~/.trueflow/java-agent/
     * Returns the path to the extracted JAR, or null on failure.
     */
    private fun extractJavaAgent(): String? {
        val trueflowDir = File(System.getProperty("user.home"), ".trueflow")
        val javaAgentDir = File(trueflowDir, "java-agent")
        javaAgentDir.mkdirs()

        val agentJar = File(javaAgentDir, "trueflow-agent.jar")

        // Check if already extracted
        if (agentJar.exists()) {
            PluginLogger.info("[TrueFlow] Java agent already exists: ${agentJar.absolutePath}")
            return agentJar.absolutePath
        }

        try {
            // Extract from plugin resources
            val resourceStream = javaClass.getResourceAsStream("/java-agent/trueflow-agent.jar")

            if (resourceStream != null) {
                resourceStream.use { input ->
                    agentJar.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
                PluginLogger.info("[TrueFlow] Extracted Java agent to: ${agentJar.absolutePath}")
                return agentJar.absolutePath
            } else {
                // Try development fallback
                val devJar = File("${project.basePath}/java-agent/build/libs/trueflow-agent.jar")
                if (devJar.exists()) {
                    devJar.copyTo(agentJar, overwrite = true)
                    PluginLogger.info("[TrueFlow] Copied Java agent from dev build: ${agentJar.absolutePath}")
                    return agentJar.absolutePath
                }

                // Try alternative location
                val altJar = File("java-agent/build/libs/trueflow-agent-0.1.0.jar")
                if (altJar.exists()) {
                    altJar.copyTo(agentJar, overwrite = true)
                    PluginLogger.info("[TrueFlow] Copied Java agent from alt location: ${agentJar.absolutePath}")
                    return agentJar.absolutePath
                }

                PluginLogger.error("[TrueFlow] Java agent JAR not found in resources or dev locations")
                return null
            }
        } catch (e: Exception) {
            PluginLogger.error("[TrueFlow] Failed to extract Java agent: ${e.message}")
            return null
        }
    }

    /**
     * Create a Java/Kotlin run configuration with -javaagent VM option.
     */
    private fun createJavaRunConfiguration(
        entryPoint: VirtualFile,
        traceDir: String,
        packagesToTrace: List<String>,
        excludePackages: List<String>,
        agentPath: String
    ) {
        val configName = "Trace: ${entryPoint.nameWithoutExtension}"

        // Build agent arguments
        val agentArgs = buildList {
            add("enabled=true")
            add("port=5679")  // Java uses port 5679
            if (packagesToTrace.isNotEmpty()) {
                add("includes=${packagesToTrace.joinToString(";")}")
            }
            if (excludePackages.isNotEmpty()) {
                add("excludes=${excludePackages.joinToString(";")}")
            }
            add("traceDir=$traceDir")
        }.joinToString(",")

        val javaAgentVmOption = "-javaagent:$agentPath=$agentArgs"

        try {
            val runManager = RunManager.getInstance(project)
            val allConfigTypes = ConfigurationType.CONFIGURATION_TYPE_EP.extensionList

            // Find Java or Application configuration type
            val configType = allConfigTypes.find {
                it.displayName.contains("Application", ignoreCase = true) ||
                it.displayName.contains("Java", ignoreCase = true) ||
                it.displayName.contains("Kotlin", ignoreCase = true)
            }

            if (configType == null) {
                // Show manual instructions
                Messages.showInfoMessage(
                    project,
                    """
                    Java Application plugin not found. Please manually configure:

                    1. Create a Run Configuration for your main class
                    2. Add VM options:
                       $javaAgentVmOption

                    3. Add environment variable:
                       TRUEFLOW_ENABLED=1

                    Or run from command line:
                       java $javaAgentVmOption -jar your-app.jar
                    """.trimIndent(),
                    "Manual Configuration Required"
                )
                return
            }

            val factory = configType.configurationFactories.firstOrNull()
            if (factory == null) {
                Messages.showWarningDialog(project, "Could not find configuration factory", "Error")
                return
            }

            // Create run configuration
            val runConfigSettings = runManager.createConfiguration(configName, factory)
            val runConfig = runConfigSettings.configuration

            try {
                // Set main class if it's a Java file
                if (entryPoint.extension == "java" || entryPoint.extension == "kt") {
                    // Try to extract class name from file
                    val className = extractMainClassName(entryPoint)
                    if (className != null) {
                        try {
                            val setMainClassMethod = runConfig.javaClass.getMethod("setMainClassName", String::class.java)
                            setMainClassMethod.invoke(runConfig, className)
                        } catch (e: NoSuchMethodException) {
                            // Try alternative method name
                            try {
                                val setMainMethod = runConfig.javaClass.getMethod("setMainClass", String::class.java)
                                setMainMethod.invoke(runConfig, className)
                            } catch (e2: Exception) {
                                PluginLogger.warn("[TrueFlow] Could not set main class: ${e2.message}")
                            }
                        }
                    }
                }

                // Set VM options with -javaagent
                try {
                    val setVmOptionsMethod = runConfig.javaClass.getMethod("setVMParameters", String::class.java)
                    setVmOptionsMethod.invoke(runConfig, javaAgentVmOption)
                } catch (e: NoSuchMethodException) {
                    try {
                        val setVmMethod = runConfig.javaClass.getMethod("setVmParameters", String::class.java)
                        setVmMethod.invoke(runConfig, javaAgentVmOption)
                    } catch (e2: Exception) {
                        PluginLogger.warn("[TrueFlow] Could not set VM options: ${e2.message}")
                    }
                }

                // Set environment variables
                val envVars = mutableMapOf<String, String>()
                envVars["TRUEFLOW_ENABLED"] = "1"
                envVars["TRUEFLOW_PORT"] = "5679"
                envVars["TRUEFLOW_TRACE_DIR"] = traceDir
                if (packagesToTrace.isNotEmpty()) {
                    envVars["TRUEFLOW_INCLUDES"] = packagesToTrace.joinToString(",")
                }

                try {
                    val setEnvMethod = runConfig.javaClass.getMethod("setEnvs", Map::class.java)
                    setEnvMethod.invoke(runConfig, envVars)
                } catch (e: Exception) {
                    PluginLogger.warn("[TrueFlow] Could not set environment variables: ${e.message}")
                }

            } catch (e: Exception) {
                PluginLogger.warn("[TrueFlow] Warning configuring Java run config: ${e.message}")
            }

            // Add configuration
            runManager.addConfiguration(runConfigSettings)
            runManager.selectedConfiguration = runConfigSettings

            Messages.showInfoMessage(
                project,
                """
                Java/Kotlin run configuration created: "$configName"

                VM Options:
                  $javaAgentVmOption

                Environment:
                  TRUEFLOW_ENABLED=1
                  TRUEFLOW_PORT=5679

                Agent JAR: $agentPath
                Trace output: $traceDir

                To run:
                1. Click the green play button next to "$configName"
                2. Or select from Run menu
                3. Traces stream to TrueFlow on port 5679
                """.trimIndent(),
                "Java Run Configuration Created"
            )

        } catch (e: Exception) {
            Messages.showErrorDialog(
                project,
                """
                Failed to create run configuration: ${e.message}

                Manual setup:
                1. Edit your run configuration
                2. Add VM option: $javaAgentVmOption
                3. Set TRUEFLOW_ENABLED=1 environment variable
                """.trimIndent(),
                "Configuration Error"
            )
        }
    }

    /**
     * Extract main class name from a Java/Kotlin file.
     */
    private fun extractMainClassName(file: VirtualFile): String? {
        return try {
            val content = String(file.contentsToByteArray())

            // Extract package
            val packageMatch = Regex("""package\s+([a-zA-Z0-9_.]+)""").find(content)
            val packageName = packageMatch?.groupValues?.get(1)

            // Extract class name (simple heuristic - look for public class or class with main)
            val classMatch = Regex("""(?:public\s+)?class\s+(\w+)""").find(content)
            val className = classMatch?.groupValues?.get(1) ?: file.nameWithoutExtension

            if (packageName != null) {
                "$packageName.$className"
            } else {
                className
            }
        } catch (e: Exception) {
            null
        }
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

    /**
     * Check if runtime injector is already deployed and up-to-date.
     * Returns true if injection can be skipped, false if (re)injection needed.
     */
    private fun isRuntimeInjectorDeployed(): Pair<Boolean, String> {
        val pluginDir = File("${project.basePath}/.pycharm_plugin")
        val runtimeInjectorDir = File(pluginDir, "runtime_injector")

        // Check if directory exists
        if (!runtimeInjectorDir.exists()) {
            return Pair(false, "Runtime injector directory not found")
        }

        // Check for essential files
        val essentialFiles = listOf(
            "python_runtime_instrumentor.py",
            "sitecustomize.py",
            "enable_tracing.bat",
            "enable_tracing.sh",
            "enable_tracing.ps1",
            "tracing_wrapper.py"
        )

        val missingFiles = essentialFiles.filter { !File(runtimeInjectorDir, it).exists() }
        if (missingFiles.isNotEmpty()) {
            return Pair(false, "Missing files: ${missingFiles.joinToString(", ")}")
        }

        // Check version marker file (if present)
        val versionFile = File(runtimeInjectorDir, ".version")
        val currentVersion = "1.0.13"  // Should match plugin version

        if (versionFile.exists()) {
            val deployedVersion = versionFile.readText().trim()
            if (deployedVersion == currentVersion) {
                return Pair(true, "Already deployed (version $deployedVersion)")
            } else {
                return Pair(false, "Version mismatch: deployed=$deployedVersion, current=$currentVersion")
            }
        }

        // Files exist but no version marker - assume needs update
        return Pair(false, "No version marker found, will update")
    }

    private fun copyRuntimeInjectorToProject(): Boolean {
        // Check if already deployed
        val (isDeployed, statusMessage) = isRuntimeInjectorDeployed()

        if (isDeployed) {
            println("[Plugin] Runtime injector: $statusMessage - skipping deployment")
            return true
        }

        println("[Plugin] Runtime injector: $statusMessage - deploying...")

        // Copy ALL runtime_injector files to .pycharm_plugin/runtime_injector/
        // This includes sitecustomize.py, project_scanner.py, local_llm_server.py, etc.
        val pluginDir = File("${project.basePath}/.pycharm_plugin")
        val runtimeInjectorDir = File(pluginDir, "runtime_injector")
        runtimeInjectorDir.mkdirs()

        var deployedCount = 0
        var failedCount = 0

        try {
            // Get resource URL for the runtime_injector directory
            val resourceUrl = javaClass.getResource("/runtime_injector")

            if (resourceUrl != null) {
                val jarFile = (resourceUrl.openConnection() as? java.net.JarURLConnection)?.jarFile

                if (jarFile != null) {
                    // Iterate through JAR entries and copy ALL files
                    val entries = jarFile.entries()
                    while (entries.hasMoreElements()) {
                        val entry = entries.nextElement()
                        val entryName = entry.name

                        // Process ALL files in runtime_injector (not just specific ones)
                        if (entryName.startsWith("runtime_injector/") && !entry.isDirectory) {
                            try {
                                val relativePath = entryName.substringAfter("runtime_injector/")
                                if (relativePath.isEmpty()) continue

                                val targetFile = File(runtimeInjectorDir, relativePath)

                                // Create parent directories for subdirectories
                                targetFile.parentFile?.mkdirs()

                                // Extract file
                                jarFile.getInputStream(entry).use { input ->
                                    targetFile.outputStream().use { output ->
                                        input.copyTo(output)
                                    }
                                }

                                deployedCount++
                            } catch (e: Exception) {
                                println("[Plugin] Failed to extract ${entry.name}: ${e.message}")
                                failedCount++
                            }
                        }
                    }
                } else {
                    // Development mode - copy from source directory
                    println("[Plugin] Development mode: copying from source directory")

                    // Try multiple possible source locations
                    val possibleSourceDirs = listOf(
                        File("${project.basePath}/pycharm-plugin/runtime_injector"),
                        File(System.getProperty("user.home") + "/PycharmProjects/TrueFlow/src/main/resources/runtime_injector")
                    )

                    val sourceDir = possibleSourceDirs.find { it.exists() && it.isDirectory }

                    if (sourceDir != null) {
                        sourceDir.walk().filter { it.isFile }.forEach { sourceFile ->
                            try {
                                val relativePath = sourceFile.relativeTo(sourceDir).path
                                val targetFile = File(runtimeInjectorDir, relativePath)
                                targetFile.parentFile?.mkdirs()
                                sourceFile.copyTo(targetFile, overwrite = true)
                                deployedCount++
                            } catch (e: Exception) {
                                println("[Plugin] Failed to copy ${sourceFile.name}: ${e.message}")
                                failedCount++
                            }
                        }
                    } else {
                        println("[Plugin] ERROR: Source directory not found in any expected location")
                        failedCount++
                    }
                }
            } else {
                println("[Plugin] WARNING: Resources not found in JAR")
            }
        } catch (e: Exception) {
            println("[Plugin] ERROR deploying runtime injector: ${e.message}")
            e.printStackTrace()
            return false
        }

        // Write version marker for future checks
        if (deployedCount > 0) {
            try {
                val versionFile = File(runtimeInjectorDir, ".version")
                versionFile.writeText("1.0.13")
                println("[Plugin] Version marker written: 1.0.13")
            } catch (e: Exception) {
                println("[Plugin] Warning: Could not write version marker: ${e.message}")
            }
        }

        println("[Plugin] Runtime injector deployment complete: $deployedCount deployed, $failedCount failed to: ${runtimeInjectorDir.absolutePath}")
        return deployedCount > 0 && failedCount == 0
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
            val isPowerShell = entryPoint.name.endsWith(".ps1")
            val isScriptFile = isBatchFile || isShellScript || isPowerShell

            val configType = when {
                isScriptFile -> {
                    // Find Shell Script / Batch / PowerShell configuration type
                    allConfigTypes.find {
                        it.displayName.contains("Shell Script", ignoreCase = true) ||
                        it.displayName.contains("Batch", ignoreCase = true) ||
                        it.displayName.contains("PowerShell", ignoreCase = true)
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
                val typeName = when {
                    isBatchFile -> "Batch"
                    isShellScript -> "Shell Script"
                    isPowerShell -> "PowerShell"
                    else -> "Python"
                }
                val runtimeInjectorDir = "$pluginDir/runtime_injector"
                Messages.showWarningDialog(
                    project,
                    "$typeName plugin not found. Please install the plugin and manually create run configuration.\n\n" +
                    "Run with tracing from command line:\n" +
                    "  Batch:      .pycharm_plugin\\runtime_injector\\enable_tracing.bat ${entryPoint.name}\n" +
                    "  PowerShell: .pycharm_plugin\\runtime_injector\\enable_tracing.ps1 ${entryPoint.name}\n" +
                    "  Shell:      .pycharm_plugin/runtime_injector/enable_tracing.sh ${entryPoint.name}\n\n" +
                    "Or for Python directly:\n" +
                    "  python .pycharm_plugin\\runtime_injector\\tracing_wrapper.py ${entryPoint.name}\n\n" +
                    "Environment variables needed:\n" +
                    "PYCHARM_PLUGIN_TRACE_ENABLED=1\n" +
                    "PYCHARM_PLUGIN_SOCKET_TRACE=1\n" +
                    "CRAWL4AI_TRACE_DIR=$traceDir\n" +
                    "PYTHONPATH=$runtimeInjectorDir",
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
                if (isScriptFile) {
                    // For batch/shell/PowerShell files, configure to use enable_tracing wrapper
                    val runtimeInjectorDir = "$pluginDir/runtime_injector"
                    val wrapperScript = when {
                        isBatchFile -> "$runtimeInjectorDir/enable_tracing.bat"
                        isPowerShell -> "$runtimeInjectorDir/enable_tracing.ps1"
                        else -> "$runtimeInjectorDir/enable_tracing.sh"
                    }

                    // Try to set the wrapper script as the entry point with original script as argument
                    try {
                        val setScriptMethod = runConfig.javaClass.getMethod("setScriptName", String::class.java)
                        setScriptMethod.invoke(runConfig, wrapperScript)

                        // Set the original script as script parameters
                        try {
                            val setParamsMethod = runConfig.javaClass.getMethod("setScriptParameters", String::class.java)
                            setParamsMethod.invoke(runConfig, entryPoint.path)
                        } catch (e: NoSuchMethodException) {
                            // Some versions use different method names
                            println("[Plugin] Could not set script parameters: ${e.message}")
                        }
                    } catch (e: NoSuchMethodException) {
                        // Fallback: Try alternative method names
                        try {
                            val setPathMethod = runConfig.javaClass.getMethod("setScriptPath", String::class.java)
                            setPathMethod.invoke(runConfig, wrapperScript)
                        } catch (e2: Exception) {
                            println("[Plugin] Could not set script path: ${e2.message}")
                        }
                    }

                    // Show helpful message about the wrapper setup
                    val wrapperType = when {
                        isBatchFile -> "Batch (.bat)"
                        isPowerShell -> "PowerShell (.ps1)"
                        else -> "Shell (.sh)"
                    }
                    Messages.showInfoMessage(
                        project,
                        """
                        $wrapperType file detected: ${entryPoint.name}

                        TrueFlow has configured a tracing wrapper:

                        Wrapper:    ${wrapperScript.replace(project.basePath ?: "", ".")}
                        Target:     ${entryPoint.path.replace(project.basePath ?: "", ".")}

                        The run configuration uses enable_tracing wrapper which:
                        - Sets up PYTHONPATH for sitecustomize.py
                        - Enables socket tracing on port 5678
                        - Creates trace output directory

                        Run from command line (choose your shell):
                          Batch:      .pycharm_plugin\runtime_injector\enable_tracing.bat ${entryPoint.name}
                          PowerShell: .pycharm_plugin\runtime_injector\enable_tracing.ps1 ${entryPoint.name}
                          Bash/Sh:    .pycharm_plugin/runtime_injector/enable_tracing.sh ${entryPoint.name}
                        """.trimIndent(),
                        "$wrapperType Tracing Configuration"
                    )
                } else {
                    // Python configuration
                    val runtimeInjectorDir = "$pluginDir/runtime_injector"

                    val setScriptPathMethod = runConfig.javaClass.getMethod("setScriptName", String::class.java)
                    setScriptPathMethod.invoke(runConfig, entryPoint.path)

                    val setWorkingDirMethod = runConfig.javaClass.getMethod("setWorkingDirectory", String::class.java)
                    setWorkingDirMethod.invoke(runConfig, project.basePath)

                    // Set environment variables (Python config)
                    // PYTHONPATH must point to runtime_injector for sitecustomize.py to work
                    val envVars = mutableMapOf<String, String>()
                    envVars["PYCHARM_PLUGIN_TRACE_ENABLED"] = "1"
                    envVars["PYCHARM_PLUGIN_SOCKET_TRACE"] = "1"
                    envVars["PYCHARM_PLUGIN_TRACE_PORT"] = "5678"
                    envVars["PYCHARM_PLUGIN_TRACE_HOST"] = "127.0.0.1"
                    envVars["CRAWL4AI_TRACE_DIR"] = traceDir
                    envVars["PYTHONPATH"] = runtimeInjectorDir

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
