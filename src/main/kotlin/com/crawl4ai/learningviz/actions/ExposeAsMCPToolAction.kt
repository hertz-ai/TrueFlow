package com.crawl4ai.learningviz.actions

import com.crawl4ai.learningviz.PluginLogger
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * Editor context menu action: "Expose as MCP Tool"
 *
 * Right-click on a Python function in the editor -> generates a standalone
 * MCP server wrapping that function via the TrueFlow Hub.
 *
 * Works without the Python plugin by scanning the document text for
 * the enclosing def/async def at the cursor position.
 */
class ExposeAsMCPToolAction : AnAction(
    "Expose as MCP Tool",
    "Generate a standalone MCP server wrapping this function",
    null
) {

    override fun actionPerformed(e: AnActionEvent) {
        val project: Project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val virtualFile = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return

        val document = editor.document
        val caretLine = editor.caretModel.logicalPosition.line

        // Search upward from cursor to find enclosing def/async def
        val defPattern = Regex("""^\s*(async\s+)?def\s+(\w+)\s*\(""")
        var funcName: String? = null
        var funcLine = 0

        for (line in caretLine downTo 0) {
            val lineText = document.getText(
                com.intellij.openapi.util.TextRange(
                    document.getLineStartOffset(line),
                    document.getLineEndOffset(line)
                )
            )
            val match = defPattern.find(lineText)
            if (match != null) {
                funcName = match.groupValues[2]
                funcLine = line + 1 // 1-based
                break
            }
        }

        if (funcName == null) {
            Messages.showWarningDialog(
                project,
                "Place your cursor inside a Python function definition.",
                "TrueFlow: Expose as MCP Tool"
            )
            return
        }

        // Check if inside a class - scan upward for class def with less indentation
        val funcLineText = document.getText(
            com.intellij.openapi.util.TextRange(
                document.getLineStartOffset(funcLine - 1),
                document.getLineEndOffset(funcLine - 1)
            )
        )
        val funcIndent = funcLineText.length - funcLineText.trimStart().length
        val classPattern = Regex("""^\s*class\s+(\w+)""")
        var className: String? = null

        if (funcIndent > 0) {
            for (line in (funcLine - 2) downTo 0) {
                val lineText = document.getText(
                    com.intellij.openapi.util.TextRange(
                        document.getLineStartOffset(line),
                        document.getLineEndOffset(line)
                    )
                )
                val lineIndent = lineText.length - lineText.trimStart().length
                if (lineIndent < funcIndent) {
                    val classMatch = classPattern.find(lineText)
                    if (classMatch != null) {
                        className = classMatch.groupValues[1]
                    }
                    break
                }
            }
        }

        // Build qualified function name
        val qualifiedFunc = if (className != null) "$className.$funcName" else funcName

        // Derive module from file path relative to project root
        val projectRoot = project.basePath ?: ""
        val filePath = virtualFile.path
        val moduleName = deriveModuleName(filePath, projectRoot)

        // POST to Hub
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val url = URL("http://127.0.0.1:5681/expose_tool")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                conn.connectTimeout = 10000
                conn.readTimeout = 10000

                val json = """{"function_name":"$qualifiedFunc","module":"$moduleName","file":"${filePath.replace("\\", "\\\\")}","line":$funcLine}"""
                OutputStreamWriter(conn.outputStream, "UTF-8").use { it.write(json) }

                val responseCode = conn.responseCode
                val responseBody = if (responseCode in 200..299) {
                    conn.inputStream.bufferedReader().readText()
                } else {
                    conn.errorStream?.bufferedReader()?.readText() ?: "HTTP $responseCode"
                }

                ApplicationManager.getApplication().invokeLater {
                    if (responseCode in 200..299 && responseBody.contains("tool_name")) {
                        // Parse tool_name and server_path from JSON response
                        val toolNameMatch = Regex(""""tool_name"\s*:\s*"([^"]+)"""").find(responseBody)
                        val serverPathMatch = Regex(""""server_path"\s*:\s*"([^"]+)"""").find(responseBody)
                        val toolName = toolNameMatch?.groupValues?.get(1) ?: qualifiedFunc
                        val serverPath = serverPathMatch?.groupValues?.get(1) ?: ""

                        val configSnippet = """
                            |"$toolName": {
                            |    "command": "python",
                            |    "args": ["$serverPath"]
                            |}
                        """.trimMargin()

                        val choice = Messages.showYesNoDialog(
                            project,
                            "MCP Tool Created: $toolName\n\nServer: $serverPath\n\nClaude Desktop config:\n$configSnippet\n\nCopy config to clipboard?",
                            "TrueFlow: MCP Tool Generated",
                            "Copy Config",
                            "Close",
                            Messages.getInformationIcon()
                        )
                        if (choice == Messages.YES) {
                            val clipboard = java.awt.Toolkit.getDefaultToolkit().systemClipboard
                            clipboard.setContents(java.awt.datatransfer.StringSelection(configSnippet), null)
                        }
                    } else {
                        // Try to extract error message
                        val errorMatch = Regex(""""error"\s*:\s*"([^"]+)"""").find(responseBody)
                        val errorMsg = errorMatch?.groupValues?.get(1) ?: responseBody
                        Messages.showErrorDialog(
                            project,
                            "MCP Tool Generation Failed:\n$errorMsg",
                            "TrueFlow Error"
                        )
                    }
                }
            } catch (ex: java.net.ConnectException) {
                ApplicationManager.getApplication().invokeLater {
                    Messages.showErrorDialog(
                        project,
                        "TrueFlow Hub not reachable at :5681.\nStart the Hub first.",
                        "TrueFlow: Hub Not Running"
                    )
                }
            } catch (ex: Exception) {
                PluginLogger.warn("ExposeAsMCPTool failed: ${ex.message}")
                ApplicationManager.getApplication().invokeLater {
                    Messages.showErrorDialog(
                        project,
                        "Failed to generate MCP tool: ${ex.message}",
                        "TrueFlow Error"
                    )
                }
            }
        }
    }

    /**
     * Derive Python module path from file path relative to project root.
     * e.g., /project/src/mymod/utils.py -> src.mymod.utils
     */
    private fun deriveModuleName(filePath: String, projectRoot: String): String {
        val normalizedFile = filePath.replace("\\", "/")
        val normalizedRoot = projectRoot.replace("\\", "/").trimEnd('/')
        val relative = if (normalizedFile.startsWith(normalizedRoot)) {
            normalizedFile.substring(normalizedRoot.length).trimStart('/')
        } else {
            normalizedFile.substringAfterLast("/")
        }
        return relative
            .removeSuffix(".py")
            .removeSuffix("/__init__")
            .replace("/", ".")
    }

    override fun update(e: AnActionEvent) {
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)
        val isPythonFile = file?.name?.endsWith(".py") == true
        e.presentation.isEnabledAndVisible = e.project != null && isPythonFile
    }
}
