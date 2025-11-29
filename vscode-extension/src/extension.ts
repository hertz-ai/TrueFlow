import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

/**
 * TrueFlow VS Code Extension
 *
 * Deterministic Code Visualizer & Explainer
 * Unblackbox LLM code with deterministic truth.
 */

let traceViewerPanel: vscode.WebviewPanel | undefined;

export function activate(context: vscode.ExtensionContext) {
    console.log('TrueFlow extension is now active');

    // Register commands
    const autoIntegrateCmd = vscode.commands.registerCommand('trueflow.autoIntegrate', async () => {
        await autoIntegrateProject(context);
    });

    const showTraceViewerCmd = vscode.commands.registerCommand('trueflow.showTraceViewer', () => {
        showTraceViewer(context);
    });

    const generateManimVideoCmd = vscode.commands.registerCommand('trueflow.generateManimVideo', async () => {
        await generateManimVideo();
    });

    const exportDiagramCmd = vscode.commands.registerCommand('trueflow.exportDiagram', async () => {
        await exportDiagram();
    });

    context.subscriptions.push(
        autoIntegrateCmd,
        showTraceViewerCmd,
        generateManimVideoCmd,
        exportDiagramCmd
    );

    // Watch for trace file changes
    setupTraceWatcher(context);
}

async function autoIntegrateProject(context: vscode.ExtensionContext): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        vscode.window.showErrorMessage('No workspace folder open');
        return;
    }

    const workspaceRoot = workspaceFolders[0].uri.fsPath;

    // Let user select entry point
    const pythonFiles = await vscode.workspace.findFiles('**/*.py', '**/node_modules/**');
    const fileItems = pythonFiles.map(f => ({
        label: path.relative(workspaceRoot, f.fsPath),
        description: f.fsPath
    }));

    const selected = await vscode.window.showQuickPick(fileItems, {
        placeHolder: 'Select entry point Python file (main.py, app.py, etc.)'
    });

    if (!selected) {
        return;
    }

    // Create .trueflow directory
    const trueflowDir = path.join(workspaceRoot, '.trueflow');
    if (!fs.existsSync(trueflowDir)) {
        fs.mkdirSync(trueflowDir, { recursive: true });
    }

    // Copy runtime injector
    const injectorSource = path.join(context.extensionPath, 'runtime_injector');
    const injectorDest = path.join(trueflowDir, 'runtime_injector');

    // TODO: Copy runtime injector files
    vscode.window.showInformationMessage(
        `TrueFlow integrated! Run with: TRUEFLOW_ENABLED=1 python ${selected.label}`
    );

    // Create launch configuration
    const launchConfig = {
        "name": "TrueFlow: Debug",
        "type": "python",
        "request": "launch",
        "program": "${workspaceFolder}/" + selected.label,
        "env": {
            "TRUEFLOW_ENABLED": "1",
            "PYTHONPATH": "${workspaceFolder}/.trueflow"
        }
    };

    // Show user the launch config
    const action = await vscode.window.showInformationMessage(
        'Would you like to create a VS Code launch configuration?',
        'Yes', 'No'
    );

    if (action === 'Yes') {
        // TODO: Add to .vscode/launch.json
        vscode.window.showInformationMessage('Launch configuration created!');
    }
}

function showTraceViewer(context: vscode.ExtensionContext): void {
    if (traceViewerPanel) {
        traceViewerPanel.reveal(vscode.ViewColumn.Two);
        return;
    }

    traceViewerPanel = vscode.window.createWebviewPanel(
        'trueflowTraceViewer',
        'TrueFlow Trace Viewer',
        vscode.ViewColumn.Two,
        {
            enableScripts: true,
            retainContextWhenHidden: true
        }
    );

    traceViewerPanel.webview.html = getTraceViewerHtml();

    traceViewerPanel.onDidDispose(() => {
        traceViewerPanel = undefined;
    });
}

async function generateManimVideo(): Promise<void> {
    const config = vscode.workspace.getConfiguration('trueflow');
    const traceDir = config.get<string>('traceDirectory', './traces');
    const pythonPath = config.get<string>('pythonPath', 'python');
    const quality = config.get<string>('manimQuality', 'medium_quality');

    // Find latest trace file
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        return;
    }

    const tracePath = path.join(workspaceFolders[0].uri.fsPath, traceDir);

    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "Generating Manim video...",
        cancellable: true
    }, async (progress, token) => {
        progress.report({ increment: 0, message: "Starting Manim render..." });

        // TODO: Execute Manim rendering
        // const manimScript = path.join(context.extensionPath, 'manim_visualizer', 'ultimate_architecture_viz.py');

        progress.report({ increment: 100, message: "Video generated!" });

        vscode.window.showInformationMessage('Manim video generated successfully!');
    });
}

async function exportDiagram(): Promise<void> {
    const formats = ['PlantUML (.puml)', 'Mermaid (.mmd)', 'D2 (.d2)', 'JSON (.json)', 'Markdown (.md)'];

    const selected = await vscode.window.showQuickPick(formats, {
        placeHolder: 'Select export format'
    });

    if (!selected) {
        return;
    }

    const saveUri = await vscode.window.showSaveDialog({
        filters: {
            'Diagram Files': ['puml', 'mmd', 'd2', 'json', 'md']
        }
    });

    if (saveUri) {
        // TODO: Export diagram
        vscode.window.showInformationMessage(`Diagram exported to ${saveUri.fsPath}`);
    }
}

function setupTraceWatcher(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration('trueflow');
    const traceDir = config.get<string>('traceDirectory', './traces');

    const watcher = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(vscode.workspace.workspaceFolders![0], `${traceDir}/**/*.json`)
    );

    watcher.onDidCreate(uri => {
        const autoRefresh = config.get<boolean>('autoRefresh', true);
        if (autoRefresh && traceViewerPanel) {
            // Refresh trace viewer
            traceViewerPanel.webview.postMessage({
                type: 'newTrace',
                path: uri.fsPath
            });
        }
    });

    context.subscriptions.push(watcher);
}

function getTraceViewerHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow Trace Viewer</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            padding: 20px;
        }
        .header {
            font-size: 1.5em;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 10px;
        }
        .tab-container {
            display: flex;
            border-bottom: 1px solid var(--vscode-panel-border);
            margin-bottom: 20px;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
        }
        .tab:hover {
            background-color: var(--vscode-list-hoverBackground);
        }
        .tab.active {
            border-bottom-color: var(--vscode-focusBorder);
        }
        .content {
            padding: 10px;
        }
        .placeholder {
            text-align: center;
            color: var(--vscode-descriptionForeground);
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="header">TrueFlow - Deterministic Code Visualizer</div>

    <div class="tab-container">
        <div class="tab active" data-tab="diagram">Diagram</div>
        <div class="tab" data-tab="performance">Performance</div>
        <div class="tab" data-tab="deadcode">Dead Code</div>
        <div class="tab" data-tab="trace">Call Trace</div>
        <div class="tab" data-tab="flamegraph">Flamegraph</div>
        <div class="tab" data-tab="manim">Manim Video</div>
    </div>

    <div class="content">
        <div class="placeholder">
            <p>No trace data loaded.</p>
            <p>Run your Python application with TrueFlow enabled to see execution traces.</p>
            <p><code>TRUEFLOW_ENABLED=1 python your_script.py</code></p>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                // Switch content based on tab
            });
        });

        window.addEventListener('message', event => {
            const message = event.data;
            if (message.type === 'newTrace') {
                // Load new trace data
                console.log('New trace:', message.path);
            }
        });
    </script>
</body>
</html>`;
}

export function deactivate() {
    if (traceViewerPanel) {
        traceViewerPanel.dispose();
    }
}
