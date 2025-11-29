package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import java.io.File
import java.io.InputStream

/**
 * Deploys Python resources from plugin JAR to .pycharm_plugin directory.
 *
 * Python files must be embedded as resources in the plugin JAR.
 * At runtime, they are extracted to .pycharm_plugin/ for execution.
 */
object ResourceDeployer {

    /**
     * Deploy all Manim visualizer Python files to .pycharm_plugin/manim_visualizer/
     *
     * This must be called during plugin initialization to ensure Python files
     * are available for Manim video generation.
     */
    fun deployManimVisualizer(project: Project) {
        val targetDir = PluginPaths.getManimVisualizerDir(project)

        PluginLogger.info("Deploying Manim visualizer files to: ${targetDir.absolutePath}")

        // Copy ALL Python files from resources, preserving directory structure
        var deployedCount = 0
        var failedCount = 0

        try {
            // Get resource URL for the manim_visualizer directory
            val resourceUrl = ResourceDeployer::class.java.getResource("/manim_visualizer")

            if (resourceUrl != null) {
                // Resources found in JAR - extract them
                PluginLogger.info("Extracting Manim visualizer from JAR resources")

                // Use class loader to find all resources in manim_visualizer directory
                val jarFile = (resourceUrl.openConnection() as? java.net.JarURLConnection)?.jarFile

                if (jarFile != null) {
                    // Iterate through JAR entries
                    val entries = jarFile.entries()
                    while (entries.hasMoreElements()) {
                        val entry = entries.nextElement()
                        val entryName = entry.name

                        // Only process manim_visualizer files
                        if (entryName.startsWith("manim_visualizer/") && entryName.endsWith(".py")) {
                            try {
                                val relativePath = entryName.substringAfter("manim_visualizer/")
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
                    // Not in JAR (development mode) - copy from filesystem
                    PluginLogger.info("Development mode: copying from source directory")
                    val sourceDir = File("${project.basePath}/pycharm-plugin/manim_visualizer")

                    if (sourceDir.exists() && sourceDir.isDirectory) {
                        sourceDir.walk().filter { it.isFile && it.extension == "py" }.forEach { sourceFile ->
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
                val sourceDir = File("${project.basePath}/pycharm-plugin/manim_visualizer")

                if (sourceDir.exists() && sourceDir.isDirectory) {
                    sourceDir.walk().filter { it.isFile && it.extension == "py" }.forEach { sourceFile ->
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
                    PluginLogger.error("Neither JAR resources nor source directory found")
                }
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to deploy Manim visualizer: ${e.message}", e)
            failedCount++
        }

        PluginLogger.info("Manim visualizer deployment complete: $deployedCount deployed, $failedCount failed")
    }

    /**
     * Try to find Python file in source directory (development mode only).
     */
    private fun findSourceFile(project: Project, fileName: String): File? {
        val projectPath = project.basePath ?: return null
        val sourceFile = File("$projectPath/pycharm-plugin/manim_visualizer/$fileName")
        return if (sourceFile.exists()) sourceFile else null
    }

    /**
     * Deploy runtime injector Python files to .pycharm_plugin/runtime_injector/
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
     */
    fun deployAll(project: Project) {
        PluginLogger.info("Starting resource deployment...")
        deployManimVisualizer(project)
        deployRuntimeInjector(project)
        PluginLogger.info("Resource deployment completed")
    }
}
