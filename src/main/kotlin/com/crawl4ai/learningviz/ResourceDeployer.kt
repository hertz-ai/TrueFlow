package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import java.io.File
import java.io.InputStream

/**
 * Deploys Python resources from plugin JAR to .pycharm_plugin directory.
 *
 * Python files must be embedded as resources in the plugin JAR.
 * At runtime, they are extracted to .pycharm_plugin/ for execution.
 *
 * NOTE: All visualizer files (ultimate_architecture_viz.py, etc.) are part of runtime_injector.
 * There is no separate manim_visualizer directory - all Python code is in one place.
 */
object ResourceDeployer {

    /**
     * Deploy runtime injector Python files to .pycharm_plugin/runtime_injector/
     * This includes ALL Python code: tracing, visualization, Manim scenes, etc.
     * Copies ALL files from bundled resources, not just a hardcoded list.
     */
    fun deployRuntimeInjector(project: Project) {
        val targetDir = PluginPaths.getRuntimeInjectorDir(project)

        PluginLogger.info("Deploying runtime injector files to: ${targetDir.absolutePath}")

        var deployedCount = 0
        var failedCount = 0

        try {
            // Get resource URL for the runtime_injector directory
            val resourceUrl = ResourceDeployer::class.java.getResource("/runtime_injector")

            if (resourceUrl != null) {
                // Resources found in JAR - extract ALL Python files
                PluginLogger.info("Extracting runtime injector from JAR resources")

                val jarFile = (resourceUrl.openConnection() as? java.net.JarURLConnection)?.jarFile

                if (jarFile != null) {
                    // Iterate through JAR entries
                    val entries = jarFile.entries()
                    while (entries.hasMoreElements()) {
                        val entry = entries.nextElement()
                        val entryName = entry.name

                        // Process ALL files in runtime_injector (not just .py)
                        if (entryName.startsWith("runtime_injector/") && !entry.isDirectory) {
                            try {
                                val relativePath = entryName.substringAfter("runtime_injector/")
                                if (relativePath.isEmpty()) continue

                                val targetFile = File(targetDir, relativePath)

                                // Create parent directories
                                targetFile.parentFile?.mkdirs()

                                // Extract file
                                jarFile.getInputStream(entry).use { input ->
                                    targetFile.outputStream().use { output ->
                                        input.copyTo(output)
                                    }
                                }

                                deployedCount++
                                PluginLogger.debug("Deployed: $relativePath")
                            } catch (e: Exception) {
                                PluginLogger.error("Failed to extract ${entry.name}: ${e.message}", e)
                                failedCount++
                            }
                        }
                    }
                } else {
                    // Not in JAR (development mode) - copy ALL files from filesystem
                    PluginLogger.info("Development mode: copying ALL runtime_injector files from source directory")
                    val sourceDir = File("${project.basePath}/pycharm-plugin/runtime_injector")

                    if (sourceDir.exists() && sourceDir.isDirectory) {
                        sourceDir.walk().filter { it.isFile }.forEach { sourceFile ->
                            try {
                                val relativePath = sourceFile.relativeTo(sourceDir).path
                                val targetFile = File(targetDir, relativePath)
                                targetFile.parentFile?.mkdirs()
                                sourceFile.copyTo(targetFile, overwrite = true)
                                deployedCount++
                                PluginLogger.debug("Deployed from source: $relativePath")
                            } catch (e: Exception) {
                                PluginLogger.error("Failed to copy ${sourceFile.name}: ${e.message}", e)
                                failedCount++
                            }
                        }
                    } else {
                        PluginLogger.error("Source directory not found: ${sourceDir.absolutePath}")
                        failedCount++
                    }
                }
            } else {
                // Fallback: try source directory
                PluginLogger.warn("Resources not found in JAR, trying source directory")
                val sourceDir = File("${project.basePath}/pycharm-plugin/runtime_injector")

                if (sourceDir.exists() && sourceDir.isDirectory) {
                    sourceDir.walk().filter { it.isFile }.forEach { sourceFile ->
                        try {
                            val relativePath = sourceFile.relativeTo(sourceDir).path
                            val targetFile = File(targetDir, relativePath)
                            targetFile.parentFile?.mkdirs()
                            sourceFile.copyTo(targetFile, overwrite = true)
                            deployedCount++
                            PluginLogger.debug("Deployed from source: $relativePath")
                        } catch (e: Exception) {
                            PluginLogger.error("Failed to copy ${sourceFile.name}: ${e.message}", e)
                            failedCount++
                        }
                    }
                } else {
                    PluginLogger.error("Neither JAR resources nor source directory found for runtime_injector")
                }
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to deploy runtime injector: ${e.message}", e)
            failedCount++
        }

        PluginLogger.info("Runtime injector deployment complete: $deployedCount deployed, $failedCount failed")
    }

    /**
     * Deploy all plugin resources.
     * Call this during plugin initialization.
     *
     * NOTE: All Python code (tracing, visualization, Manim scenes) is in runtime_injector.
     * @return true if this is a new version (hub should be restarted to pick up new code)
     */
    fun deployAll(project: Project): Boolean {
        PluginLogger.info("Starting resource deployment...")
        deployRuntimeInjector(project)
        ensureGitExclude(project)

        // Check if plugin version changed — hub needs restart to load new Python code
        val versionChanged = checkAndUpdateVersionMarker(project)
        if (versionChanged) {
            PluginLogger.info("Resource deployment completed — plugin version changed, hub restart needed")
        } else {
            PluginLogger.info("Resource deployment completed")
        }
        return versionChanged
    }

    /**
     * Ensure .pycharm_plugin/ is in .git/info/exclude so it never gets staged.
     * Only writes if the exclude file exists and doesn't already contain the entry.
     */
    private fun ensureGitExclude(project: Project) {
        try {
            val projectPath = project.basePath ?: return
            val excludeFile = File(projectPath, ".git/info/exclude")
            if (!excludeFile.exists()) return

            val content = excludeFile.readText()
            val entry = ".pycharm_plugin/"
            if (content.contains(entry)) return

            excludeFile.appendText("\n$entry\n")
            PluginLogger.info("Added $entry to .git/info/exclude")
        } catch (e: Exception) {
            PluginLogger.debug("Could not update git exclude: ${e.message}")
        }
    }

    /**
     * Write a version marker to .pycharm_plugin/.plugin_version.
     * Returns true if the version changed (or marker didn't exist).
     */
    private fun checkAndUpdateVersionMarker(project: Project): Boolean {
        val targetDir = PluginPaths.getRuntimeInjectorDir(project)
        val versionFile = File(targetDir, ".plugin_version")
        val currentVersion = getCurrentPluginVersion()

        val versionChanged = if (versionFile.exists()) {
            val deployedVersion = versionFile.readText().trim()
            deployedVersion != currentVersion
        } else {
            true // First deploy
        }

        versionFile.writeText(currentVersion)
        return versionChanged
    }

    /**
     * Read plugin version from plugin-version.properties bundled in the JAR.
     */
    private fun getCurrentPluginVersion(): String {
        return try {
            val stream = ResourceDeployer::class.java.getResourceAsStream("/plugin-version.properties")
            if (stream != null) {
                val props = java.util.Properties()
                props.load(stream)
                stream.close()
                props.getProperty("pluginVersion", "unknown")
            } else {
                "unknown"
            }
        } catch (_: Exception) {
            "unknown"
        }
    }
}
