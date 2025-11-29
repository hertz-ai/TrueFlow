package com.crawl4ai.learningviz

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileCreateEvent
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.ui.JBUI
import java.awt.BorderLayout
import java.awt.Desktop
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import javax.swing.*

/**
 * Panel for displaying and playing Manim animations.
 *
 * Since embedding video players in IntelliJ plugins is complex and requires
 * JavaFX dependencies, this panel instead:
 * 1. Lists generated Manim videos with timestamps
 * 2. Shows video metadata (duration, resolution, file size)
 * 3. Opens videos in system default player
 * 4. Auto-refreshes when new videos are detected via VFS listener
 *
 * This approach is more reliable and works on all platforms.
 */
class ManimVideoPanel(private val project: Project) : JBPanel<JBPanel<*>>(BorderLayout()), Disposable {

    private val videoListModel = DefaultListModel<VideoInfo>()
    private val videoList = JList(videoListModel)
    private val infoPanel = JBPanel<JBPanel<*>>(GridBagLayout())
    private val statusLabel = JBLabel("No videos found")

    // Manim output directory (use PluginPaths for single source of truth)
    private val manimOutputDir = PluginPaths.getVideosDir(project)

    // File watcher for auto-refresh
    private var fileWatcherConnection: com.intellij.util.messages.MessageBusConnection? = null

    data class VideoInfo(
        val file: File,
        val timestamp: Date,
        val name: String,
        val size: Long,
        val duration: String = "Unknown"
    ) {
        override fun toString(): String {
            val dateFormat = SimpleDateFormat("HH:mm:ss")
            val sizeKB = size / 1024
            return "${dateFormat.format(timestamp)} - $name (${sizeKB}KB)"
        }
    }

    init {
        border = JBUI.Borders.empty(10)
        createUI()
        scanForVideos()
        setupFileWatcher()
    }

    private fun setupFileWatcher() {
        try {
            // Connect to message bus for VFS events
            fileWatcherConnection = ApplicationManager.getApplication().messageBus.connect(this)

            fileWatcherConnection?.subscribe(
                com.intellij.openapi.vfs.VirtualFileManager.VFS_CHANGES,
                object : BulkFileListener {
                    override fun after(events: List<VFileEvent>) {
                        // Check if any events are video file creations in monitored directories
                        val hasNewVideo = events.any { event ->
                            if (event is VFileCreateEvent) {
                                val path = event.path
                                val isVideoFile = path.endsWith(".mp4", ignoreCase = true) ||
                                                path.endsWith(".mov", ignoreCase = true) ||
                                                path.endsWith(".avi", ignoreCase = true) ||
                                                path.endsWith(".webm", ignoreCase = true)

                                // Check if in monitored directories (use PluginPaths)
                                val isInMonitoredDir = path.contains(".pycharm_plugin") &&
                                                      (path.contains("manim/media/videos") || path.contains("manim/traces"))

                                isVideoFile && isInMonitoredDir
                            } else {
                                false
                            }
                        }

                        if (hasNewVideo) {
                            // Refresh UI on EDT
                            ApplicationManager.getApplication().invokeLater {
                                PluginLogger.info("New Manim video detected - auto-refreshing list")
                                scanForVideos()
                            }
                        }
                    }
                }
            )

            PluginLogger.info("File watcher enabled for Manim videos")
        } catch (e: Exception) {
            PluginLogger.error("Failed to setup file watcher", e)
        }
    }

    override fun dispose() {
        fileWatcherConnection?.disconnect()
    }

    private fun createUI() {
        // Top: Status and refresh button
        val topPanel = JBPanel<JBPanel<*>>(BorderLayout())
        topPanel.add(statusLabel, BorderLayout.WEST)

        val refreshButton = JButton("Refresh")
        refreshButton.addActionListener { scanForVideos() }
        topPanel.add(refreshButton, BorderLayout.EAST)

        add(topPanel, BorderLayout.NORTH)

        // Left: Video list
        videoList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        videoList.addListSelectionListener { updateInfoPanel() }

        // Add double-click listener to play video
        videoList.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) {
                    val selectedVideo = videoList.selectedValue
                    if (selectedVideo != null) {
                        openVideoInSystemPlayer(selectedVideo.file)
                    }
                }
            }
        })

        val listScrollPane = JBScrollPane(videoList)
        listScrollPane.preferredSize = JBUI.size(300, 400)

        // Right: Video info and controls
        updateInfoPanel()
        val infoScrollPane = JBScrollPane(infoPanel)

        // Split pane
        val splitPane = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, listScrollPane, infoScrollPane)
        splitPane.resizeWeight = 0.4
        add(splitPane, BorderLayout.CENTER)

        // Bottom: Instructions
        val instructions = JBLabel("<html>Manim animations are generated every 5 seconds when trace data is received.<br>" +
                "<b>Double-click</b> a video to play, or select and press 'Play' button.</html>")
        instructions.border = JBUI.Borders.empty(10, 0, 0, 0)
        add(instructions, BorderLayout.SOUTH)
    }

    private fun updateInfoPanel() {
        infoPanel.removeAll()

        val selectedVideo = videoList.selectedValue
        if (selectedVideo == null) {
            val gbc = GridBagConstraints()
            gbc.gridx = 0
            gbc.gridy = 0
            gbc.anchor = GridBagConstraints.CENTER
            infoPanel.add(JBLabel("Select a video to see details"), gbc)
            infoPanel.revalidate()
            infoPanel.repaint()
            return
        }

        val gbc = GridBagConstraints()
        gbc.gridx = 0
        gbc.gridy = GridBagConstraints.RELATIVE
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = JBUI.insets(5)
        gbc.fill = GridBagConstraints.HORIZONTAL
        gbc.weightx = 1.0

        // Video info
        infoPanel.add(createBoldLabel("Video Information"), gbc)
        infoPanel.add(JBLabel("File: ${selectedVideo.name}"), gbc)
        infoPanel.add(JBLabel("Size: ${selectedVideo.size / 1024} KB"), gbc)
        infoPanel.add(JBLabel("Created: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(selectedVideo.timestamp)}"), gbc)
        infoPanel.add(JBLabel("Path: ${selectedVideo.file.absolutePath}"), gbc)

        // Spacer
        gbc.gridy++
        gbc.insets = JBUI.insets(20, 5, 5, 5)
        infoPanel.add(Box.createVerticalStrut(10), gbc)

        // Play button
        gbc.insets = JBUI.insets(5)
        val playButton = JButton("Play in External Player")
        playButton.addActionListener {
            openVideoInSystemPlayer(selectedVideo.file)
        }
        infoPanel.add(playButton, gbc)

        // Open folder button
        val openFolderButton = JButton("Open Containing Folder")
        openFolderButton.addActionListener {
            openFileInExplorer(selectedVideo.file.parentFile)
        }
        infoPanel.add(openFolderButton, gbc)

        // Delete button
        val deleteButton = JButton("Delete Video")
        deleteButton.addActionListener {
            if (JOptionPane.showConfirmDialog(
                    this,
                    "Are you sure you want to delete this video?",
                    "Delete Video",
                    JOptionPane.YES_NO_OPTION
                ) == JOptionPane.YES_OPTION
            ) {
                selectedVideo.file.delete()
                scanForVideos()
            }
        }
        infoPanel.add(deleteButton, gbc)

        infoPanel.revalidate()
        infoPanel.repaint()
    }

    private fun createBoldLabel(text: String): JBLabel {
        val label = JBLabel(text)
        val font = label.font
        label.font = font.deriveFont(font.style or java.awt.Font.BOLD, font.size + 2f)
        return label
    }

    private fun scanForVideos() {
        videoListModel.clear()

        val videoFiles = mutableListOf<File>()

        // Scan manim output directory (recursive to catch all subdirectories)
        // IMPORTANT: Filter out partial_movie_files - these are Manim's internal rendering fragments
        // Only show complete videos (those NOT in partial_movie_files directories)
        // Complete videos are named: video_${correlationId}_${pathHash}.mp4 or SceneName.mp4
        if (manimOutputDir.exists()) {
            manimOutputDir.walkTopDown()
                .filter { file ->
                    file.isFile &&
                    file.extension.lowercase() in listOf("mp4", "mov", "avi", "webm") &&
                    !file.absolutePath.contains("partial_movie_files") // Exclude Manim internal fragments
                }
                .forEach { videoFiles.add(it) }
        }

        // Also scan manim_traces directory for any videos
        val tracesDir = PluginPaths.getManimTracesDir(project)
        if (tracesDir.exists()) {
            tracesDir.walkTopDown()
                .filter { file ->
                    file.isFile &&
                    file.extension.lowercase() in listOf("mp4", "mov", "avi", "webm") &&
                    !file.absolutePath.contains("partial_movie_files") // Exclude Manim internal fragments
                }
                .forEach { videoFiles.add(it) }
        }

        // Sort by modification time (newest first)
        videoFiles.sortByDescending { it.lastModified() }

        // Add to list model
        videoFiles.forEach { file ->
            val videoInfo = VideoInfo(
                file = file,
                timestamp = Date(file.lastModified()),
                name = file.name,
                size = file.length()
            )
            videoListModel.addElement(videoInfo)
        }

        // Update status
        statusLabel.text = "Found ${videoFiles.size} video(s)"

        if (videoFiles.isEmpty()) {
            PluginLogger.info("No Manim videos found. Videos will appear here when generated.")
        } else {
            PluginLogger.info("Found ${videoFiles.size} Manim videos")
        }
    }

    private fun openVideoInSystemPlayer(file: File) {
        try {
            if (Desktop.isDesktopSupported()) {
                Desktop.getDesktop().open(file)
                PluginLogger.info("Opened video in system player: ${file.name}")
            } else {
                JOptionPane.showMessageDialog(
                    this,
                    "Desktop operations not supported on this platform.\nVideo location: ${file.absolutePath}",
                    "Cannot Open Video",
                    JOptionPane.WARNING_MESSAGE
                )
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to open video: ${file.name}", e)
            JOptionPane.showMessageDialog(
                this,
                "Failed to open video: ${e.message}\nVideo location: ${file.absolutePath}",
                "Error",
                JOptionPane.ERROR_MESSAGE
            )
        }
    }

    private fun openFileInExplorer(directory: File) {
        try {
            if (Desktop.isDesktopSupported()) {
                Desktop.getDesktop().open(directory)
                PluginLogger.info("Opened folder: ${directory.absolutePath}")
            }
        } catch (e: Exception) {
            PluginLogger.error("Failed to open folder: ${directory.absolutePath}", e)
        }
    }

    /**
     * Auto-refresh when new videos are detected.
     * Call this from file watcher or periodically.
     */
    fun refresh() {
        scanForVideos()
    }
}
