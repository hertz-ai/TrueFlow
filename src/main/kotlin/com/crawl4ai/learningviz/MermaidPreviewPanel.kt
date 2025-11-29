package com.crawl4ai.learningviz

import com.intellij.openapi.project.Project
import com.intellij.ui.jcef.JBCefBrowser
import com.intellij.ui.jcef.JBCefBrowserBase
import com.intellij.ui.jcef.JBCefJSQuery
import java.awt.BorderLayout
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
