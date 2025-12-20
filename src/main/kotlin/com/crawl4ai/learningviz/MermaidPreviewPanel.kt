package com.crawl4ai.learningviz

import com.intellij.ide.BrowserUtil
import com.intellij.openapi.project.Project
import com.intellij.ui.jcef.JBCefBrowser
import com.intellij.ui.jcef.JBCefBrowserBase
import com.intellij.ui.jcef.JBCefJSQuery
import java.awt.BorderLayout
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import javax.swing.JPanel

/**
 * Panel that renders Mermaid.js diagrams using JCEF (Chromium Embedded Framework).
 *
 * This provides live, interactive preview of Mermaid sequence diagrams,
 * flowcharts, and other diagram types directly in the IDE.
 */
class MermaidPreviewPanel(private val project: Project) : JPanel(BorderLayout()) {

    private var browser: JBCefBrowser? = null
    private var currentMermaidCode: String = ""

    init {
        try {
            // Create JCEF browser
            browser = JBCefBrowser()
            add(browser!!.component, BorderLayout.CENTER)

            // Load initial HTML with Mermaid.js
            browser!!.loadHTML(getBaseHtml(""))

            PluginLogger.info("MermaidPreviewPanel initialized with JCEF browser")
        } catch (e: Exception) {
            PluginLogger.error("Failed to initialize JCEF browser for Mermaid preview: ${e.message}")
            // Fallback: Show message that JCEF is not available
            add(javax.swing.JLabel(
                "<html><center><p>Mermaid preview requires JCEF support.</p>" +
                "<p>Please use a JetBrains IDE with JCEF enabled.</p></center></html>"
            ), BorderLayout.CENTER)
        }
    }

    /**
     * Update the Mermaid diagram with new code.
     */
    fun updateDiagram(mermaidCode: String) {
        currentMermaidCode = mermaidCode

        // Clean the mermaid code (remove markdown fence if present)
        val cleanCode = mermaidCode
            .replace("```mermaid", "")
            .replace("```", "")
            .trim()

        browser?.loadHTML(getBaseHtml(cleanCode))
    }

    /**
     * Get the current Mermaid code.
     */
    fun getMermaidCode(): String = currentMermaidCode

    /**
     * Open the current diagram in the default browser for fullscreen viewing.
     * @param showDeadCallTrees Whether dead call trees are being shown
     * @param diagramType The type of diagram (mermaid or plantuml)
     */
    fun openInBrowser(showDeadCallTrees: Boolean = false, diagramType: String = "mermaid") {
        if (currentMermaidCode.isBlank()) {
            PluginLogger.warn("No diagram to open in browser")
            return
        }

        val cleanCode = currentMermaidCode
            .replace("```mermaid", "")
            .replace("```", "")
            .trim()

        val timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))
        val deadTreesLabel = if (showDeadCallTrees) "Including Dead Call Trees" else "Runtime Calls Only"

        val fullscreenHtml = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow Sequence Diagram - Fullscreen</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #1e1e1e;
            color: #d4d4d4;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: #252526;
            padding: 12px 20px;
            border-bottom: 1px solid #3c3c3c;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header h1 {
            font-size: 16px;
            font-weight: 500;
            color: #569cd6;
        }
        .header-info {
            font-size: 12px;
            color: #808080;
        }
        .header-info span {
            margin-left: 15px;
            padding: 3px 8px;
            background: #3c3c3c;
            border-radius: 3px;
        }
        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .controls button {
            background: #0e639c;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }
        .controls button:hover {
            background: #1177bb;
        }
        .controls button.secondary {
            background: #3c3c3c;
        }
        .controls button.secondary:hover {
            background: #4c4c4c;
        }
        .diagram-container {
            flex: 1;
            overflow: auto;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }
        .mermaid {
            background: #2d2d2d;
            padding: 20px;
            border-radius: 8px;
            min-width: 300px;
        }
        .mermaid svg {
            max-width: 100%;
            height: auto;
        }
        .zoom-controls {
            position: fixed;
            bottom: 20px;
            right: 20px;
            display: flex;
            gap: 5px;
            background: #252526;
            padding: 8px;
            border-radius: 5px;
            border: 1px solid #3c3c3c;
        }
        .zoom-controls button {
            width: 32px;
            height: 32px;
            background: #3c3c3c;
            border: none;
            color: white;
            border-radius: 3px;
            cursor: pointer;
            font-size: 16px;
        }
        .zoom-controls button:hover {
            background: #4c4c4c;
        }
        .zoom-level {
            padding: 0 10px;
            line-height: 32px;
            font-size: 12px;
        }
        @media print {
            .header, .zoom-controls { display: none; }
            body { background: white; }
            .diagram-container { padding: 0; }
            .mermaid { background: white; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>TrueFlow Sequence Diagram</h1>
            <div class="header-info">
                <span>Type: ${if (diagramType == "mermaid") "Mermaid" else "PlantUML"}</span>
                <span>$deadTreesLabel</span>
                <span>Generated: $timestamp</span>
            </div>
        </div>
        <div class="controls">
            <button onclick="window.print()" class="secondary">Print / Save PDF</button>
            <button onclick="downloadSVG()">Download SVG</button>
        </div>
    </div>
    <div class="diagram-container" id="diagram-container">
        <div class="mermaid" id="mermaid-diagram">
$cleanCode
        </div>
    </div>
    <div class="zoom-controls">
        <button onclick="zoomOut()">-</button>
        <span class="zoom-level" id="zoom-level">100%</span>
        <button onclick="zoomIn()">+</button>
        <button onclick="resetZoom()">Reset</button>
    </div>
    <script>
        let currentZoom = 1;
        const diagram = document.getElementById('mermaid-diagram');

        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose',
            sequence: {
                diagramMarginX: 50,
                diagramMarginY: 10,
                actorMargin: 50,
                width: 150,
                height: 65,
                boxMargin: 10,
                boxTextMargin: 5,
                noteMargin: 10,
                messageMargin: 35,
                mirrorActors: true,
                useMaxWidth: false
            }
        });

        function zoomIn() {
            currentZoom = Math.min(currentZoom + 0.1, 3);
            applyZoom();
        }

        function zoomOut() {
            currentZoom = Math.max(currentZoom - 0.1, 0.3);
            applyZoom();
        }

        function resetZoom() {
            currentZoom = 1;
            applyZoom();
        }

        function applyZoom() {
            diagram.style.transform = 'scale(' + currentZoom + ')';
            diagram.style.transformOrigin = 'top center';
            document.getElementById('zoom-level').textContent = Math.round(currentZoom * 100) + '%';
        }

        function downloadSVG() {
            const svg = diagram.querySelector('svg');
            if (!svg) {
                alert('No diagram rendered yet');
                return;
            }
            const svgData = new XMLSerializer().serializeToString(svg);
            const blob = new Blob([svgData], { type: 'image/svg+xml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'trueflow-sequence-diagram.svg';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === '+' || e.key === '=') zoomIn();
            if (e.key === '-') zoomOut();
            if (e.key === '0') resetZoom();
            if (e.key === 'p' && e.ctrlKey) { e.preventDefault(); window.print(); }
        });
    </script>
</body>
</html>
        """.trimIndent()

        try {
            // Create a temporary HTML file
            val tempDir = System.getProperty("java.io.tmpdir")
            val tempFile = File(tempDir, "trueflow-diagram-${System.currentTimeMillis()}.html")
            tempFile.writeText(fullscreenHtml)
            tempFile.deleteOnExit()

            // Open in browser
            BrowserUtil.browse(tempFile.toURI())
            PluginLogger.info("Opened diagram in browser: ${tempFile.absolutePath}")
        } catch (e: Exception) {
            PluginLogger.error("Failed to open diagram in browser: ${e.message}")
        }
    }

    /**
     * Generate the HTML page with Mermaid.js for rendering.
     */
    private fun getBaseHtml(mermaidCode: String): String {
        // Escape the mermaid code for embedding in HTML
        val escapedCode = mermaidCode
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("<", "&lt;")
            .replace(">", "&gt;")

        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mermaid Preview</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            min-height: 100vh;
        }

        .mermaid {
            background-color: #2d2d2d;
            border-radius: 8px;
            padding: 20px;
            overflow: auto;
        }

        .mermaid svg {
            max-width: 100%;
            height: auto;
        }

        /* Custom theme for dark mode */
        .mermaid .node rect,
        .mermaid .node circle,
        .mermaid .node ellipse,
        .mermaid .node polygon {
            fill: #3c3c3c;
            stroke: #569cd6;
        }

        .mermaid .node .label {
            color: #d4d4d4;
        }

        .mermaid .edgePath .path {
            stroke: #569cd6;
        }

        .mermaid .edgeLabel {
            background-color: #2d2d2d;
            color: #d4d4d4;
        }

        .mermaid .actor {
            fill: #3c3c3c;
            stroke: #569cd6;
        }

        .mermaid .actor-line {
            stroke: #569cd6;
        }

        .mermaid text.actor {
            fill: #d4d4d4;
        }

        .mermaid .messageLine0,
        .mermaid .messageLine1 {
            stroke: #4ec9b0;
        }

        .mermaid .messageText {
            fill: #d4d4d4;
        }

        .mermaid .activation0,
        .mermaid .activation1,
        .mermaid .activation2 {
            fill: #264f78;
            stroke: #569cd6;
        }

        .mermaid .note {
            fill: #4d4d00;
            stroke: #808000;
        }

        .mermaid .noteText {
            fill: #d4d4d4;
        }

        /* Highlight for dead code (red) */
        .mermaid .messageLine0.dead,
        .mermaid .messageLine1.dead {
            stroke: #f44747 !important;
            stroke-dasharray: 5, 5;
        }

        .error-message {
            color: #f44747;
            padding: 20px;
            text-align: center;
        }

        .placeholder {
            color: #808080;
            text-align: center;
            padding: 40px;
        }

        /* Zoom controls */
        .zoom-controls {
            position: fixed;
            bottom: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
            z-index: 1000;
        }

        .zoom-controls button {
            background: #3c3c3c;
            color: #d4d4d4;
            border: 1px solid #569cd6;
            border-radius: 4px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 14px;
        }

        .zoom-controls button:hover {
            background: #4c4c4c;
        }
    </style>
</head>
<body>
    <div id="diagram" class="mermaid">
${if (mermaidCode.isNotBlank()) escapedCode else "sequenceDiagram\n    Note over User: No diagram loaded"}
    </div>

    <div class="zoom-controls">
        <button onclick="zoomIn()">+</button>
        <button onclick="zoomOut()">-</button>
        <button onclick="resetZoom()">Reset</button>
    </div>

    <script>
        // Initialize Mermaid with dark theme
        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose',
            sequence: {
                diagramMarginX: 50,
                diagramMarginY: 10,
                actorMargin: 50,
                width: 150,
                height: 65,
                boxMargin: 10,
                boxTextMargin: 5,
                noteMargin: 10,
                messageMargin: 35,
                mirrorActors: true,
                bottomMarginAdj: 1,
                useMaxWidth: true,
                rightAngles: false,
                showSequenceNumbers: false
            },
            flowchart: {
                htmlLabels: true,
                curve: 'basis'
            },
            themeVariables: {
                darkMode: true,
                primaryColor: '#3c3c3c',
                primaryTextColor: '#d4d4d4',
                primaryBorderColor: '#569cd6',
                lineColor: '#4ec9b0',
                secondaryColor: '#264f78',
                tertiaryColor: '#4d4d00',
                background: '#1e1e1e',
                mainBkg: '#2d2d2d',
                secondBkg: '#3c3c3c',
                border1: '#569cd6',
                border2: '#4ec9b0',
                arrowheadColor: '#4ec9b0',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                fontSize: '14px',
                textColor: '#d4d4d4',
                actorBorder: '#569cd6',
                actorBkg: '#3c3c3c',
                actorTextColor: '#d4d4d4',
                actorLineColor: '#569cd6',
                signalColor: '#4ec9b0',
                signalTextColor: '#d4d4d4',
                labelBoxBkgColor: '#2d2d2d',
                labelBoxBorderColor: '#569cd6',
                labelTextColor: '#d4d4d4',
                loopTextColor: '#d4d4d4',
                noteBorderColor: '#808000',
                noteBkgColor: '#4d4d00',
                noteTextColor: '#d4d4d4',
                activationBorderColor: '#569cd6',
                activationBkgColor: '#264f78',
                sequenceNumberColor: '#d4d4d4'
            }
        });

        let currentZoom = 1;

        function zoomIn() {
            currentZoom = Math.min(currentZoom + 0.1, 3);
            applyZoom();
        }

        function zoomOut() {
            currentZoom = Math.max(currentZoom - 0.1, 0.3);
            applyZoom();
        }

        function resetZoom() {
            currentZoom = 1;
            applyZoom();
        }

        function applyZoom() {
            const diagram = document.getElementById('diagram');
            diagram.style.transform = 'scale(' + currentZoom + ')';
            diagram.style.transformOrigin = 'top left';
        }

        // Re-render on error
        mermaid.parseError = function(err, hash) {
            console.error('Mermaid parse error:', err);
            document.getElementById('diagram').innerHTML =
                '<div class="error-message">Error parsing diagram: ' + err + '</div>';
        };
    </script>
</body>
</html>
        """.trimIndent()
    }

    /**
     * Dispose of the browser when panel is closed.
     */
    fun dispose() {
        browser?.dispose()
        browser = null
    }
}
