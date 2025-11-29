package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import java.io.File

/**
 * Single source of truth for all plugin-related paths and directories.
 *
 * ALL file operations, logging, and artifact storage MUST use these paths.
 * This ensures consistency across the plugin and Python runtime.
 */
object PluginPaths {
    /**
     * Root directory for all plugin data: .pycharm_plugin/
     */
    fun getPluginRoot(project: Project): File {
        val projectPath = project.basePath ?: "."
        return File(projectPath, ".pycharm_plugin")
    }

    /**
     * Logs directory: .pycharm_plugin/logs/
     * All plugin logs (Kotlin and Python) go here.
     */
    fun getLogsDir(project: Project): File {
        return File(getPluginRoot(project), "logs").also { it.mkdirs() }
    }

    /**
     * Manim root directory: .pycharm_plugin/manim/
     * Contains all Manim-related content (media, traces)
     */
    fun getManimRoot(project: Project): File {
        return File(getPluginRoot(project), "manim").also { it.mkdirs() }
    }

    /**
     * Media root directory: .pycharm_plugin/manim/media/
     * Contains all Manim-generated media (videos, images, texts)
     */
    fun getMediaRoot(project: Project): File {
        return File(getManimRoot(project), "media").also { it.mkdirs() }
    }

    /**
     * Manim traces directory: .pycharm_plugin/manim/traces/
     * Trace JSON files for Manim video generation are written here.
     * (Different from getTracesRoot() which is for file-based tracing)
     */
    fun getManimTracesDir(project: Project): File {
        return File(getManimRoot(project), "traces").also { it.mkdirs() }
    }

    /**
     * Videos directory: .pycharm_plugin/manim/media/videos/
     * Manim-rendered MP4 files stored by quality level
     */
    fun getVideosDir(project: Project): File {
        return File(getMediaRoot(project), "videos").also { it.mkdirs() }
    }

    /**
     * Images directory: .pycharm_plugin/manim/media/images/
     * Manim-generated images stored by quality level
     */
    fun getImagesDir(project: Project): File {
        return File(getMediaRoot(project), "images").also { it.mkdirs() }
    }

    /**
     * Text directory: .pycharm_plugin/manim/media/texts/
     * Manim-generated text files
     */
    fun getTextsDir(project: Project): File {
        return File(getMediaRoot(project), "texts").also { it.mkdirs() }
    }

    /**
     * Runtime injector directory: .pycharm_plugin/runtime_injector/
     * Python runtime instrumentation code.
     */
    fun getRuntimeInjectorDir(project: Project): File {
        return File(getPluginRoot(project), "runtime_injector").also { it.mkdirs() }
    }

    /**
     * Manim visualizer directory: .pycharm_plugin/manim_visualizer/
     * Python Manim visualization scripts.
     */
    fun getManimVisualizerDir(project: Project): File {
        return File(getPluginRoot(project), "manim_visualizer").also { it.mkdirs() }
    }

    /**
     * Traces root directory: traces/
     * (Note: This is at project root, not in .pycharm_plugin)
     */
    fun getTracesRoot(project: Project): File {
        val projectPath = project.basePath ?: "."
        return File(projectPath, "traces").also { it.mkdirs() }
    }

    /**
     * Get POSIX-style path (forward slashes) for Python scripts.
     * Required for Windows compatibility in Python string literals.
     */
    fun toPosixPath(file: File): String {
        return file.absolutePath.replace("\\", "/")
    }

    /**
     * Get POSIX-style path string directly.
     */
    fun toPosixPath(path: String): String {
        return path.replace("\\", "/")
    }

    /**
     * Initialize all directories - call this during plugin startup.
     */
    fun initializeAll(project: Project) {
        getPluginRoot(project)
        getLogsDir(project)
        getManimRoot(project)
        getMediaRoot(project)
        getManimTracesDir(project)
        getVideosDir(project)
        getImagesDir(project)
        getTextsDir(project)
        getRuntimeInjectorDir(project)
        getManimVisualizerDir(project)
    }
}
