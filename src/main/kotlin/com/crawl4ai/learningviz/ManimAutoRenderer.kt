package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Auto-renderer that buffers trace events and generates Manim videos.
 *
 * Architecture:
 * 1. Buffer trace events per correlation ID
 * 2. Detect when correlation ID goes idle (no events for N seconds)
 * 3. Write trace JSON file
 * 4. Invoke Python BatchTraceVisualizer to generate video
 * 5. Notify when video is ready
 */
class ManimAutoRenderer(
    private val project: Project,
    private val onVideoGenerated: (File) -> Unit = {}
) {
    // Global trace filter
    private val traceFilter = TraceFilter.getInstance(project)

    // Event buffers per correlation ID
    private val eventBuffers = ConcurrentHashMap<String, MutableList<TraceEvent>>()
    private val lastEventTime = ConcurrentHashMap<String, Long>()

    // Correlation IDs being processed
    private val processingIds = ConcurrentHashMap.newKeySet<String>()

    // Path hash -> Video file mapping for deduplication
    private val pathHashToVideo = ConcurrentHashMap<String, File>()

    private val projectPath = project.basePath ?: "."
    private val traceOutputDir = PluginPaths.getManimTracesDir(project)
    private val videoOutputDir = PluginPaths.getVideosDir(project)

    private val gson: Gson = GsonBuilder().setPrettyPrinting().create()

    // Background executor for idle detection and video generation
    private val executor = Executors.newScheduledThreadPool(2)

    // Configuration
    private val idleTimeoutMs = 5000L  // 5 seconds of no events = cycle complete
    private val checkIntervalMs = 2000L  // Check for idle cycles every 2 seconds

    init {
        traceOutputDir.mkdirs()
        videoOutputDir.mkdirs()

        PluginLogger.info("ManimAutoRenderer initialized")
        PluginLogger.info("Trace output: ${traceOutputDir.absolutePath}")
        PluginLogger.info("Video output: ${videoOutputDir.absolutePath}")

        // Start idle detection loop
        startIdleDetectionLoop()
    }

    /**
     * Handle incoming trace event - buffer it or process immediately if cycle_complete.
     */
    fun onTraceEvent(event: TraceEvent) {
        // Handle cycle_complete events immediately (contains full trace JSON)
        if (event.type == "cycle_complete" && event.traceData != null) {
            val correlationId = event.traceData.get("correlation_id")?.asString
            if (correlationId != null) {
                PluginLogger.info("Received cycle_complete event for: $correlationId, generating video immediately...")
                processingIds.add(correlationId)

                // Generate video directly from trace data
                executor.submit {
                    try {
                        // Parse events from trace data and apply global filter
                        val calls = event.traceData.getAsJsonArray("calls")
                        val filteredCalls = mutableListOf<com.google.gson.JsonObject>()
                        val allEvents = mutableListOf<TraceEvent>()

                        calls?.forEach { callObj ->
                            val obj = callObj.asJsonObject
                            val file = obj.get("file_path")?.asString ?: ""
                            val module = obj.get("module")?.asString ?: ""

                            // Apply global filter to each call
                            if (!traceFilter.shouldExclude(file) && !traceFilter.shouldExcludeModule(module)) {
                                filteredCalls.add(obj)
                                // Also create TraceEvent for path hash calculation
                            allEvents.add(TraceEvent(
                                callId = obj.get("call_id")?.asString ?: "",
                                type = obj.get("type")?.asString ?: "call",
                                timestamp = obj.get("timestamp")?.asDouble ?: 0.0,
                                module = module,
                                function = obj.get("function")?.asString ?: "",
                                file = file,
                                line = obj.get("line_number")?.asInt ?: 0,
                                depth = obj.get("depth")?.asInt ?: 0,
                                parentId = obj.get("parent_id")?.asString,
                                correlationId = obj.get("correlation_id")?.asString,
                                learningPhase = obj.get("learning_phase")?.asString,
                                sessionId = "",
                                processId = 0,
                                traceData = null
                            ))
                            }
                        }

                        PluginLogger.info("Filtered: ${calls?.size() ?: 0} calls → ${filteredCalls.size} kept for $correlationId")

                        if (filteredCalls.isEmpty()) {
                            PluginLogger.info("No calls after filtering, skipping video generation for $correlationId")
                            processingIds.remove(correlationId)
                            return@submit
                        }

                        // Create modified trace data with only filtered calls
                        val modifiedTraceData = com.google.gson.JsonObject()
                        modifiedTraceData.addProperty("correlation_id", correlationId)
                        modifiedTraceData.addProperty("event_count", filteredCalls.size)
                        val filteredCallsArray = com.google.gson.JsonArray()
                        filteredCalls.forEach { filteredCallsArray.add(it) }
                        modifiedTraceData.add("calls", filteredCallsArray)

                        // Write filtered trace data to temporary file
                        val tempFile = java.io.File.createTempFile("cycle_complete_$correlationId", ".json")
                        tempFile.writeText(modifiedTraceData.toString())

                        // Calculate path hash for deduplication using filtered events
                        val pathHash = calculatePathHash(allEvents)

                        // Check if video already exists
                        val existingVideo = pathHashToVideo[pathHash]
                        if (existingVideo != null && existingVideo.exists()) {
                            PluginLogger.info("Video already exists for cycle_complete path hash $pathHash: ${existingVideo.name} (skipping)")
                            tempFile.delete()
                            processingIds.remove(correlationId)
                            onVideoGenerated(existingVideo)
                            return@submit
                        }

                        // Generate video from temp file
                        val videoFile = generateVideo(correlationId, tempFile, pathHash)

                        // Clean up temp file
                        tempFile.delete()

                        processingIds.remove(correlationId)
                        if (videoFile != null) {
                            PluginLogger.info("Video generated for cycle_complete: $correlationId -> ${videoFile.name}")
                            pathHashToVideo[pathHash] = videoFile
                        } else {
                            PluginLogger.warn("Video generation returned null for $correlationId")
                        }
                    } catch (e: Exception) {
                        processingIds.remove(correlationId)
                        PluginLogger.error("Failed to generate video for cycle_complete $correlationId: ${e.message}", e)
                    }
                }
            }
            return
        }

        // Regular event buffering (for call/return events)
        // Apply global filter for regular events
        if (traceFilter.shouldExclude(event.file) || traceFilter.shouldExcludeModule(event.module)) {
            return // Skip filtered events
        }

        val correlationId = event.correlationId ?: return

        // Buffer event
        eventBuffers.computeIfAbsent(correlationId) { mutableListOf() }.add(event)

        // Update last event time
        lastEventTime[correlationId] = System.currentTimeMillis()

        // Log first event for this correlation ID
        if (eventBuffers[correlationId]?.size == 1) {
            PluginLogger.info("Started buffering events for correlation ID: $correlationId")
        }
    }

    /**
     * Start background loop to detect idle correlation IDs and generate videos.
     */
    private fun startIdleDetectionLoop() {
        executor.scheduleAtFixedRate({
            try {
                detectAndProcessIdleCycles()
            } catch (e: Exception) {
                PluginLogger.error("Error in idle detection loop: ${e.message}")
            }
        }, checkIntervalMs, checkIntervalMs, TimeUnit.MILLISECONDS)
    }

    /**
     * Detect correlation IDs that have gone idle and process them.
     */
    private fun detectAndProcessIdleCycles() {
        val now = System.currentTimeMillis()

        for ((correlationId, lastTime) in lastEventTime) {
            // Skip if already processing
            if (processingIds.contains(correlationId)) {
                continue
            }

            // Check if idle
            val idleTime = now - lastTime
            if (idleTime >= idleTimeoutMs) {
                PluginLogger.info("Correlation ID $correlationId is idle (${idleTime}ms), generating video...")
                processingIds.add(correlationId)

                // Process in background
                executor.submit {
                    try {
                        processCorrelationId(correlationId)
                    } catch (e: Exception) {
                        PluginLogger.error("Error processing correlation ID $correlationId: ${e.message}")
                    } finally {
                        processingIds.remove(correlationId)
                        // Clean up buffers
                        eventBuffers.remove(correlationId)
                        lastEventTime.remove(correlationId)
                    }
                }
            }
        }
    }

    /**
     * Process a complete correlation ID: write trace file and generate video.
     */
    private fun processCorrelationId(correlationId: String) {
        val events = eventBuffers[correlationId] ?: return

        if (events.isEmpty()) {
            PluginLogger.warn("No events for correlation ID $correlationId")
            return
        }

        PluginLogger.info("Processing ${events.size} events for correlation ID: $correlationId")

        // Calculate path hash for deduplication
        val pathHash = calculatePathHash(events)

        // Check if video already exists for this execution path
        val existingVideo = pathHashToVideo[pathHash]
        if (existingVideo != null && existingVideo.exists()) {
            PluginLogger.info("Video already exists for path hash $pathHash: ${existingVideo.name} (skipping generation)")
            onVideoGenerated(existingVideo)
            return
        }

        // Write trace JSON file
        val traceFile = writeTraceFile(correlationId, events)

        // Generate video
        val videoFile = generateVideo(correlationId, traceFile, pathHash)

        if (videoFile != null && videoFile.exists()) {
            PluginLogger.info("Video generated successfully: ${videoFile.name}")
            pathHashToVideo[pathHash] = videoFile
            onVideoGenerated(videoFile)
        } else {
            PluginLogger.warn("Video generation failed for correlation ID: $correlationId")
        }
    }

    /**
     * Calculate hash of execution path for deduplication.
     * Hash based on module.function sequence (ignores timestamps, call IDs, etc.)
     */
    private fun calculatePathHash(events: List<TraceEvent>): String {
        val pathSignature = events
            .filter { it.type == "call" }  // Only consider call events
            .joinToString("|") { "${it.module}.${it.function}" }
        return pathSignature.hashCode().toString()
    }

    /**
     * Write trace events to JSON file.
     */
    private fun writeTraceFile(correlationId: String, events: List<TraceEvent>): File {
        val timestamp = System.currentTimeMillis()
        val traceFile = File(traceOutputDir, "trace_${correlationId}_${timestamp}.json")

        // Convert TraceEvent objects to JSON format expected by BatchTraceVisualizer
        val traceData = mapOf(
            "correlation_id" to correlationId,
            "timestamp" to timestamp,
            "event_count" to events.size,
            "calls" to events.map { event ->
                mapOf(
                    "call_id" to event.callId,
                    "type" to event.type,
                    "timestamp" to event.timestamp,
                    "module" to event.module,
                    "function" to event.function,
                    "file_path" to event.file,
                    "line_number" to event.line,
                    "depth" to event.depth,
                    "parent_id" to event.parentId,
                    "correlation_id" to event.correlationId,
                    "learning_phase" to event.learningPhase
                )
            }
        )

        traceFile.writeText(gson.toJson(traceData))
        PluginLogger.info("Wrote trace file: ${traceFile.name} (${traceFile.length()} bytes)")

        return traceFile
    }

    /**
     * Generate Manim video by invoking Python BatchTraceVisualizer.
     */
    private fun generateVideo(correlationId: String, traceFile: File, pathHash: String): File? {
        // Use path hash in filename for deduplication
        val videoFile = File(videoOutputDir, "video_${correlationId}_${pathHash}.mp4")

        try {
            PluginLogger.info("Invoking BatchTraceVisualizer for correlation ID: $correlationId")

            // Find Python executable
            val pythonExe = findPythonExecutable()
            if (pythonExe == null) {
                PluginLogger.error("Python executable not found")
                return null
            }

            // Fix Windows path escaping: Convert backslashes to forward slashes
            val tracePath = traceFile.absolutePath.replace("\\", "/")
            val projectPathPosix = projectPath.replace("\\", "/")

            // Get visualizer directory from PluginPaths (single source of truth)
            val visualizerDir = PluginPaths.getManimVisualizerDir(project)
            val visualizerPathPosix = PluginPaths.toPosixPath(visualizerDir)

            // Build command to invoke AdvancedOperationScene visualizer
            // Use advanced_operation_viz.py for per-operation 3D animations with multi-camera
            val visualizerScript = File(visualizerDir, "advanced_operation_viz.py")
            if (!visualizerScript.exists()) {
                PluginLogger.error("Advanced visualizer script not found: ${visualizerScript.absolutePath}")
                // Fallback to procedural trace viz
                val fallbackScript = File(visualizerDir, "procedural_trace_viz.py")
                if (fallbackScript.exists()) {
                    PluginLogger.info("Using fallback procedural visualizer")
                    val scriptContent = """
                        import sys
                        sys.path.insert(0, '$visualizerPathPosix')
                        from procedural_trace_viz import ProceduralTraceScene
                        from manim import config
                        from pathlib import Path

                        # Configure Manim output directory
                        project_root = Path('$projectPathPosix')
                        plugin_media = project_root / '.pycharm_plugin' / 'manim' / 'media'
                        plugin_media.mkdir(parents=True, exist_ok=True)

                        config.media_dir = str(plugin_media)
                        config.quality = 'medium_quality'
                        config.output_file = 'video_${correlationId}_${pathHash}'
                        config['video_dir'] = '{media_dir}/videos/{quality}'
                        config['images_dir'] = '{media_dir}/images/{quality}'
                        config['text_dir'] = '{media_dir}/texts'

                        print(f"Manim media configured to: {config.media_dir}/")

                        scene = ProceduralTraceScene('$tracePath')
                        scene.render()
                        print('Video saved to:', scene.renderer.file_writer.movie_file_path)
                        """.trimIndent()

                    val tempScript = java.io.File.createTempFile("manim_fallback_", ".py")
                    tempScript.writeText(scriptContent)

                    val command = listOf(pythonExe, tempScript.absolutePath)
                    try {
                        return executeVisualizerCommand(command, videoFile)
                    } finally {
                        tempScript.delete()
                    }
                }
                return null
            }

            // NEW FRAMEWORK-BASED VISUALIZATION
            // Uses coordinate tracking, proper 3D stacking, readable billboard text, auto data flow detection
            // Write Python script to temp file to avoid Windows command line escaping issues
            val scriptContent = """
                import sys
                import json
                from pathlib import Path
                sys.path.insert(0, '$visualizerPathPosix')

                # === CLEANUP CORRUPTED SVG CACHE ===
                # Prevents cascading failures from corrupted cache files
                def cleanup_corrupted_svg_cache():
                    cleaned = 0
                    try:
                        from manim import config
                        text_dir = config.get_dir("text_dir")
                        if text_dir and text_dir.exists():
                            for svg_file in text_dir.glob("*.svg"):
                                if svg_file.stat().st_size == 0:
                                    print(f"Removing corrupted SVG: {svg_file.name}")
                                    svg_file.unlink()
                                    cleaned += 1
                        # Also check common locations
                        for dir_path in [Path(".pycharm_plugin/manim/media/texts"), Path("media/texts")]:
                            if dir_path.exists():
                                for svg_file in dir_path.glob("*.svg"):
                                    if svg_file.stat().st_size == 0:
                                        print(f"Removing corrupted SVG: {svg_file}")
                                        svg_file.unlink()
                                        cleaned += 1
                        if cleaned > 0:
                            print(f"Cleaned {cleaned} corrupted SVG cache files")
                    except Exception as e:
                        print(f"Warning: SVG cache cleanup error: {e}")
                    return cleaned

                # Run cleanup before any rendering
                cleanup_corrupted_svg_cache()

                # Load trace to determine best visualization type
                with open('$tracePath', 'r') as f:
                    trace_data = json.load(f)

                calls = trace_data.get('calls', [])

                # Check for errors/issues (use debug viz)
                has_errors = any('error' in str(c.get('return_value', '')).lower() or
                               'exception' in str(c.get('return_value', '')).lower()
                               for c in calls)

                # Check module count (use architecture viz if many modules)
                modules = set(c.get('module', '') for c in calls if c.get('module'))
                is_architectural = len(modules) > 5

                event_count = len(calls)

                # NEW FRAMEWORK-BASED VISUALIZER
                # SystemArchitecture3DScene uses:
                # - CoordinateTracker (no position chaos)
                # - ArchitectureLayoutEngine (proper 3D depth stacking)
                # - ImprovedBillboardText (readable labels with backgrounds)
                # - DataFlowDetector (auto-detected data paths)
                # 3Blue1Brown quality: smooth camera, proper depth, no overlaps

                print("FRAMEWORK MODE: Using new coordinate-tracked visualization system")
                print(f"Modules detected: {len(modules)}")
                print(f"Events: {event_count}")

                # Import ultimate architecture visualizer
                try:
                    from ultimate_architecture_viz import UltimateArchitectureScene
                    from manim import config
                    from pathlib import Path

                    # Configure Manim to output to plugin media directory
                    # Unified structure: .pycharm_plugin/manim/media/
                    # Manim generates: videos, images, texts
                    # Structure: {media_dir}/videos/{module_name}/{quality}/{output_file}.mp4
                    # We want: .pycharm_plugin/manim/media/videos/{quality}/{output_file}.mp4
                    project_root = Path('$projectPathPosix')
                    plugin_media = project_root / '.pycharm_plugin' / 'manim' / 'media'
                    plugin_media.mkdir(parents=True, exist_ok=True)

                    config.media_dir = str(plugin_media)
                    config.quality = 'high_quality'
                    config.output_file = 'video_${correlationId}_${pathHash}'
                    config.frame_rate = 30
                    # Override directory templates to remove module_name nesting
                    config['video_dir'] = '{media_dir}/videos/{quality}'
                    config['images_dir'] = '{media_dir}/images/{quality}'
                    config['text_dir'] = '{media_dir}/texts'

                    print(f"Manim media configured to: {config.media_dir}/")

                    # Create and render ultimate architecture scene
                    scene = UltimateArchitectureScene(trace_file='$tracePath')
                    scene.render()

                    print('Video saved to:', scene.renderer.file_writer.movie_file_path)

                except ImportError as e:
                    print(f"Framework visualizer not available: {e}")
                    print("Falling back to coherent unified visualizer...")

                    # Fallback to coherent_unified_viz
                    from simple_trace_viz import SimpleTraceScene
                    from manim import config
                    from pathlib import Path

                    # Configure Manim output directory (same as framework mode)
                    project_root = Path('$projectPathPosix')
                    plugin_media = project_root / '.pycharm_plugin' / 'manim' / 'media'
                    plugin_media.mkdir(parents=True, exist_ok=True)

                    config.media_dir = str(plugin_media)
                    config.quality = 'medium_quality'
                    config.output_file = 'video_${correlationId}_${pathHash}'
                    config['video_dir'] = '{media_dir}/videos/{quality}'
                    config['images_dir'] = '{media_dir}/images/{quality}'
                    config['text_dir'] = '{media_dir}/texts'

                    print(f"Manim media configured to: {config.media_dir}/")

                    scene = SimpleTraceScene(trace_file='$tracePath')
                    scene.render()

                    print('Video saved to:', scene.renderer.file_writer.movie_file_path)

                except Exception as e:
                    print(f"Error in framework visualization: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
                """.trimIndent()

            // Write to temporary Python file
            val tempScript = java.io.File.createTempFile("manim_viz_", ".py")
            tempScript.writeText(scriptContent)

            val command = listOf(
                pythonExe,
                tempScript.absolutePath
            )

            try {
                return executeVisualizerCommand(command, videoFile)
            } finally {
                // Clean up temp script after execution
                tempScript.delete()
            }

        } catch (e: Exception) {
            PluginLogger.error("Exception during video generation: ${e.message}")
            e.printStackTrace()
            return null
        }
    }

    /**
     * Execute visualizer command and wait for completion.
     */
    private fun executeVisualizerCommand(command: List<String>, videoFile: File? = null): File? {
        try {
            PluginLogger.info("=== EXECUTING VISUALIZER ===")
            PluginLogger.info("Command: ${command.joinToString(" ")}")
            PluginLogger.info("Working directory: $projectPath")
            PluginLogger.info("Expected video file: ${videoFile?.absolutePath ?: "null"}")

            // Execute command
            val processBuilder = ProcessBuilder(command)
            processBuilder.directory(File(projectPath))
            processBuilder.redirectErrorStream(true)

            PluginLogger.info("Starting process...")
            val process = processBuilder.start()
            PluginLogger.info("Process started, PID: ${process.pid()}")

            // Read output
            PluginLogger.info("Reading process output...")
            val output = process.inputStream.bufferedReader().readText()
            PluginLogger.info("Process output (${output.length} chars): $output")

            // Wait for completion (max 120 seconds for 3D rendering)
            PluginLogger.info("Waiting for process completion (max 120s)...")
            val completed = process.waitFor(120, TimeUnit.SECONDS)

            if (!completed) {
                PluginLogger.error("Video generation timed out after 120 seconds")
                PluginLogger.error("Process still running, killing forcibly...")
                process.destroyForcibly()
                return null
            }

            val exitCode = process.exitValue()
            PluginLogger.info("Process completed with exit code: $exitCode")

            if (exitCode == 0) {
                PluginLogger.info("Video generation completed successfully")

                // Parse actual video path from Manim output
                // Look for: "File ready at 'path'" or "Video saved to: path"
                val videoPathRegex = Regex("""(?:File ready at '(.+?)'|Video saved to: (.+))""")
                val match = videoPathRegex.find(output)
                val actualVideoPath = match?.groupValues?.firstOrNull { it.isNotEmpty() && it != match.value }

                if (actualVideoPath != null) {
                    PluginLogger.info("Parsed video path from output: $actualVideoPath")
                    val actualFile = File(actualVideoPath.trim().replace("'", ""))
                    if (actualFile.exists()) {
                        PluginLogger.info("Found video at: ${actualFile.absolutePath}")
                        // Copy to expected location if different
                        if (videoFile != null && actualFile.absolutePath != videoFile.absolutePath) {
                            actualFile.copyTo(videoFile, overwrite = true)
                            PluginLogger.info("Copied video to: ${videoFile.absolutePath}")
                            return videoFile
                        }
                        return actualFile
                    } else {
                        PluginLogger.warn("Parsed video path doesn't exist: ${actualFile.absolutePath}")
                    }
                } else {
                    PluginLogger.warn("Could not parse video path from output")
                }

                // Check if expected file exists anyway
                if (videoFile != null && videoFile.exists()) {
                    PluginLogger.info("Expected video file exists: ${videoFile.absolutePath}")
                    return videoFile
                }

                PluginLogger.warn("No video file found after successful execution")
                return null
            } else {
                PluginLogger.error("Video generation failed with exit code: $exitCode")
                PluginLogger.error("Full output: $output")
                return null
            }
        } catch (e: Exception) {
            PluginLogger.error("Exception executing visualizer: ${e.message}")
            PluginLogger.error("Stack trace:", e)
            e.printStackTrace()
            return null
        }
    }

    /**
     * Find Python executable (check common locations).
     */
    private fun findPythonExecutable(): String? {
        val candidates = listOf(
            "C:/Python310/python.exe",
            "C:/Python39/python.exe",
            "C:/Python38/python.exe",
            "python",
            "python3"
        )

        for (candidate in candidates) {
            try {
                val process = ProcessBuilder(candidate, "--version").start()
                if (process.waitFor(2, TimeUnit.SECONDS) && process.exitValue() == 0) {
                    PluginLogger.info("Found Python: $candidate")
                    return candidate
                }
            } catch (e: Exception) {
                // Try next candidate
            }
        }

        return null
    }

    /**
     * Get statistics.
     */
    fun getStats(): Map<String, Any> {
        return mapOf(
            "active_buffers" to eventBuffers.size,
            "processing_ids" to processingIds.size,
            "total_buffered_events" to eventBuffers.values.sumOf { it.size }
        )
    }

    /**
     * Cleanup and shutdown.
     */
    fun dispose() {
        PluginLogger.info("Shutting down ManimAutoRenderer...")
        executor.shutdown()
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow()
            }
        } catch (e: InterruptedException) {
            executor.shutdownNow()
        }
    }
}

    /**
     * Check if Manim is installed.
     */
    private fun checkManimInstalled(pythonExe: String): Boolean {
        try {
            val process = ProcessBuilder(pythonExe, "-c", "import manim; print(manim.__version__)").start()
            if (process.waitFor(5, TimeUnit.SECONDS) && process.exitValue() == 0) {
                val version = process.inputStream.bufferedReader().readText().trim()
                PluginLogger.info("Manim installed: version $version")
                return true
            }
        } catch (e: Exception) {
            PluginLogger.warn("Manim not installed: ${e.message}")
        }
        return false
    }
