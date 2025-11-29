package com.crawl4ai.learningviz

import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent

class TraceFileListener : BulkFileListener {
    override fun after(events: MutableList<out VFileEvent>) {
        events.forEach { event ->
            if (event.file?.extension == "json" && event.file?.path?.contains("traces") == true) {
                // Handle trace file event
                println("Trace file event: ${event.file?.path}")
            }
        }
    }
}
