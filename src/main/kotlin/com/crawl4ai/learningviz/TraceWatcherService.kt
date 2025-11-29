package com.crawl4ai.learningviz

import com.intellij.openapi.components.Service
import com.intellij.openapi.project.Project
import java.io.File
import java.nio.file.*
import java.util.concurrent.ConcurrentHashMap

@Service(Service.Level.PROJECT)
class TraceWatcherService(private val project: Project) {

    private val watchers = ConcurrentHashMap<String, WatchService>()
    private val listeners = mutableListOf<TraceFileListener>()

    interface TraceFileListener {
        fun onTraceFileCreated(file: File)
        fun onTraceFileModified(file: File)
    }

    fun watchDirectory(directory: File) {
        if (!directory.isDirectory) {
            println("Not a directory: ${directory.absolutePath}")
            return
        }

        try {
            val watchService = FileSystems.getDefault().newWatchService()
            val path = directory.toPath()

            path.register(
                watchService,
                StandardWatchEventKinds.ENTRY_CREATE,
                StandardWatchEventKinds.ENTRY_MODIFY
            )

            watchers[directory.absolutePath] = watchService

            // Start watching in background thread
            Thread {
                watchLoop(watchService, directory)
            }.start()

            println("Started watching directory: ${directory.absolutePath}")
        } catch (e: Exception) {
            println("Error watching directory: ${e.message}")
        }
    }

    private fun watchLoop(watchService: WatchService, directory: File) {
        while (true) {
            val key = try {
                watchService.take()
            } catch (e: InterruptedException) {
                break
            }

            for (event in key.pollEvents()) {
                val kind = event.kind()

                if (kind == StandardWatchEventKinds.OVERFLOW) {
                    continue
                }

                val fileName = event.context() as Path
                val file = File(directory, fileName.toString())

                // Only process JSON files
                if (!file.name.endsWith(".json")) {
                    continue
                }

                when (kind) {
                    StandardWatchEventKinds.ENTRY_CREATE -> {
                        listeners.forEach { it.onTraceFileCreated(file) }
                    }
                    StandardWatchEventKinds.ENTRY_MODIFY -> {
                        listeners.forEach { it.onTraceFileModified(file) }
                    }
                }
            }

            val valid = key.reset()
            if (!valid) {
                break
            }
        }
    }

    fun addListener(listener: TraceFileListener) {
        listeners.add(listener)
    }

    fun removeListener(listener: TraceFileListener) {
        listeners.remove(listener)
    }

    fun stopWatching(directory: String) {
        watchers[directory]?.close()
        watchers.remove(directory)
    }

    fun stopAll() {
        watchers.values.forEach { it.close() }
        watchers.clear()
    }
}
