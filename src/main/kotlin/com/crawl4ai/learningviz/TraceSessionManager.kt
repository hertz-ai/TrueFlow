package com.crawl4ai.learningviz

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.reflect.TypeToken
import com.intellij.openapi.project.Project
import java.io.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream

/**
 * Manages saving and restoring TrueFlow runtime trace sessions.
 * Sessions are stored as gzipped JSON in <project>/.trueflow/sessions/
 */
class TraceSessionManager(private val project: Project) {

    private val gson: Gson = GsonBuilder().setPrettyPrinting().create()

    data class SessionInfo(
        val name: String,
        val timestamp: String,
        val file: File,
        val sizeMb: Double
    )

    private fun sessionsDir(): File {
        val dir = File(project.basePath ?: ".", ".trueflow/sessions")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    /**
     * Save a trace session to a gzipped JSON file.
     * @param name User-provided session name
     * @param state JsonObject containing all 18 trace data structures + metadata
     * @return The saved file
     */
    fun saveSession(name: String, state: JsonObject): File {
        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss").format(Date())
        val sanitizedName = name.replace(Regex("[^a-zA-Z0-9_\\-]"), "_")
        val fileName = "${sanitizedName}_${timestamp}.trueflow"
        val file = File(sessionsDir(), fileName)

        // Add metadata
        state.addProperty("_session_name", name)
        state.addProperty("_session_timestamp", timestamp)
        state.addProperty("_project_path", project.basePath ?: "")
        state.addProperty("_plugin_version", PluginLogger.PLUGIN_VERSION)

        // Write gzipped JSON
        GZIPOutputStream(BufferedOutputStream(FileOutputStream(file))).use { gzip ->
            OutputStreamWriter(gzip, Charsets.UTF_8).use { writer ->
                gson.toJson(state, writer)
            }
        }

        PluginLogger.info("[TraceSessionManager] Saved session '$name' to ${file.name} (${file.length() / 1024} KB)")
        return file
    }

    /**
     * Restore a trace session from a gzipped JSON file.
     * @return JsonObject containing all saved trace data
     */
    fun restoreSession(file: File): JsonObject {
        val json = GZIPInputStream(BufferedInputStream(FileInputStream(file))).use { gzip ->
            InputStreamReader(gzip, Charsets.UTF_8).use { reader ->
                gson.fromJson(reader, JsonObject::class.java)
            }
        }
        PluginLogger.info("[TraceSessionManager] Restored session from ${file.name}")
        return json
    }

    /**
     * List all saved sessions, newest first.
     */
    fun listSessions(): List<SessionInfo> {
        val dir = sessionsDir()
        if (!dir.exists()) return emptyList()

        return dir.listFiles { f -> f.extension == "trueflow" }
            ?.sortedByDescending { it.lastModified() }
            ?.map { file ->
                val name = file.nameWithoutExtension
                    .replace(Regex("_\\d{8}_\\d{6}$"), "") // Strip timestamp suffix
                    .replace("_", " ")
                val timestamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss")
                    .format(Date(file.lastModified()))
                val sizeMb = file.length().toDouble() / (1024 * 1024)
                SessionInfo(name, timestamp, file, sizeMb)
            } ?: emptyList()
    }

    /**
     * Delete a saved session file.
     */
    fun deleteSession(file: File): Boolean {
        val deleted = file.delete()
        if (deleted) {
            PluginLogger.info("[TraceSessionManager] Deleted session: ${file.name}")
        }
        return deleted
    }

    companion object {
        /**
         * Serialize a CallTraceNode tree to JSON recursively.
         */
        fun callTraceNodeToJson(node: Any): JsonObject {
            // Use reflection-free approach: node is passed as a map-like structure
            // The caller (ToolWindow) will handle the actual conversion since CallTraceNode is private
            return JsonObject() // Placeholder — actual conversion done in ToolWindow
        }

        /**
         * Deserialize a list of Pair<String, Int> from JSON array of [string, int] arrays.
         */
        fun pairListFromJson(arr: JsonArray): Map<String, Pair<String, Int>> {
            val map = mutableMapOf<String, Pair<String, Int>>()
            for (entry in arr) {
                val obj = entry.asJsonObject
                val key = obj.get("key").asString
                val file = obj.get("file").asString
                val line = obj.get("line").asInt
                map[key] = Pair(file, line)
            }
            return map
        }

        /**
         * Serialize a Map<String, Pair<String, Int>> to JSON array.
         */
        fun pairMapToJson(map: Map<String, Pair<String, Int>>): JsonArray {
            val arr = JsonArray()
            for ((key, pair) in map) {
                val obj = JsonObject()
                obj.addProperty("key", key)
                obj.addProperty("file", pair.first)
                obj.addProperty("line", pair.second)
                arr.add(obj)
            }
            return arr
        }
    }
}
