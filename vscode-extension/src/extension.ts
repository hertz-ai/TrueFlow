import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as https from 'https';
import * as child_process from 'child_process';
import { TraceSocketClient, TraceEvent, PerformanceData } from './TraceSocketClient';
import { AIExplanationProvider } from './AIExplanationWebview';

// Model presets for AI explanation
interface ModelPreset {
    displayName: string;
    repoId: string;
    fileName: string;
    sizeMB: number;
    description: string;
}

// Model presets from https://docs.unsloth.ai/models/qwen3-vl-how-to-run-and-fine-tune
const MODEL_PRESETS: ModelPreset[] = [
    // Qwen3-VL Vision-Language Models (recommended for code understanding)
    {
        displayName: "Qwen3-VL-2B Instruct Q4_K_XL (Recommended)",
        repoId: "unsloth/Qwen3-VL-2B-Instruct-GGUF",
        fileName: "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 1500,
        description: "Vision+text, best for code analysis with diagrams"
    },
    {
        displayName: "Qwen3-VL-2B Thinking Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-2B-Thinking-GGUF",
        fileName: "Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf",
        sizeMB: 1500,
        description: "Vision+text with chain-of-thought reasoning"
    },
    // Larger models for better quality (need more RAM)
    {
        displayName: "Qwen3-VL-4B Instruct Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-4B-Instruct-GGUF",
        fileName: "Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 2800,
        description: "Larger model, better quality, needs ~6GB RAM"
    },
    {
        displayName: "Qwen3-VL-8B Instruct Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-8B-Instruct-GGUF",
        fileName: "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 5000,
        description: "Best quality for complex code, needs ~10GB RAM"
    },
    // Text-only models (faster, no vision support)
    {
        displayName: "Qwen3-2B Text-Only Q4_K_M",
        repoId: "unsloth/Qwen3-2B-Instruct-GGUF",
        fileName: "Qwen3-2B-Instruct-Q4_K_M.gguf",
        sizeMB: 1100,
        description: "Text-only, fastest, no vision support"
    }
];

let llmServerProcess: child_process.ChildProcess | undefined;
let currentModelPath: string | undefined;

/**
 * TrueFlow VS Code Extension
 *
 * Deterministic Code Visualizer & Explainer
 * Unblackbox LLM code with deterministic truth.
 *
 * Feature Parity with PyCharm Plugin:
 * - 9 tabs (Diagram, Performance, Dead Code, Call Trace, Flamegraph, SQL, Live Metrics, Distributed, Manim)
 * - Socket-based real-time tracing (port 5678)
 * - Complete Auto-Integrate (copy runtime injector, create launch.json)
 * - Mermaid.js live preview
 */

let traceViewerPanel: vscode.WebviewPanel | undefined;
let traceSocketClient: TraceSocketClient | undefined;
let statusBarItem: vscode.StatusBarItem;
let sidebarProvider: TrueFlowSidebarProvider | undefined;

/**
 * WebviewViewProvider for the TrueFlow sidebar
 * Shows the full tabbed interface in the activity bar
 */
class TrueFlowSidebarProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'trueflow.mainView';
    private _view?: vscode.WebviewView;

    constructor(private readonly _extensionContext: vscode.ExtensionContext) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionContext.extensionUri]
        };

        webviewView.webview.html = getSidebarHtml(traceSocketClient?.isConnected() || false);

        // Handle messages from webview
        webviewView.webview.onDidReceiveMessage(async message => {
            switch (message.type) {
                case 'connect':
                    await connectToSocket();
                    break;
                case 'disconnect':
                    disconnectSocket();
                    break;
                case 'openFullView':
                    showTraceViewer(this._extensionContext);
                    break;
                case 'autoIntegrate':
                    autoIntegrateProject(this._extensionContext);
                    break;
                case 'generateVideo':
                    generateManimVideo(this._extensionContext);
                    break;
                case 'openAIChat':
                    AIExplanationProvider.getInstance().show(this._extensionContext);
                    break;
                case 'info':
                    vscode.window.showInformationMessage(message.message);
                    break;
            }
        });
    }

    public postMessage(message: any) {
        if (this._view) {
            this._view.webview.postMessage(message);
        }
    }
}

export function activate(context: vscode.ExtensionContext) {
    console.log('TrueFlow extension is now active');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(debug-disconnect) TrueFlow';
    statusBarItem.tooltip = 'TrueFlow: Click to connect to trace server';
    statusBarItem.command = 'trueflow.connectSocket';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Initialize socket client
    traceSocketClient = new TraceSocketClient();
    setupSocketClientHandlers();

    // Register sidebar webview provider
    sidebarProvider = new TrueFlowSidebarProvider(context);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(TrueFlowSidebarProvider.viewType, sidebarProvider)
    );

    // Register commands
    const commands = [
        vscode.commands.registerCommand('trueflow.autoIntegrate', () => autoIntegrateProject(context)),
        vscode.commands.registerCommand('trueflow.showTraceViewer', () => showTraceViewer(context)),
        vscode.commands.registerCommand('trueflow.generateManimVideo', () => generateManimVideo(context)),
        vscode.commands.registerCommand('trueflow.exportDiagram', () => exportDiagram()),
        vscode.commands.registerCommand('trueflow.connectSocket', () => connectToSocket()),
        vscode.commands.registerCommand('trueflow.disconnectSocket', () => disconnectSocket()),
        vscode.commands.registerCommand('trueflow.downloadAIModel', () => downloadAIModel()),
        vscode.commands.registerCommand('trueflow.startAIServer', () => startAIServer()),
        vscode.commands.registerCommand('trueflow.stopAIServer', () => stopAIServer()),
        vscode.commands.registerCommand('trueflow.showAIChat', () => AIExplanationProvider.getInstance().show(context))
    ];

    context.subscriptions.push(...commands);

    // Watch for trace file changes
    setupTraceWatcher(context);
}

function setupSocketClientHandlers(): void {
    if (!traceSocketClient) return;

    traceSocketClient.on('connected', () => {
        statusBarItem.text = '$(debug-alt) TrueFlow';
        statusBarItem.tooltip = 'TrueFlow: Connected to trace server';
        statusBarItem.backgroundColor = undefined;
        vscode.window.showInformationMessage('TrueFlow: Connected to trace server');

        // Update webview
        if (traceViewerPanel) {
            traceViewerPanel.webview.postMessage({ type: 'socketConnected' });
        }
    });

    traceSocketClient.on('disconnected', () => {
        statusBarItem.text = '$(debug-disconnect) TrueFlow';
        statusBarItem.tooltip = 'TrueFlow: Disconnected from trace server';
    });

    traceSocketClient.on('error', (err: Error) => {
        statusBarItem.text = '$(error) TrueFlow';
        statusBarItem.tooltip = `TrueFlow: Error - ${err.message}`;
    });

    traceSocketClient.on('event', (event: TraceEvent) => {
        // Send event to webview for real-time updates
        if (traceViewerPanel) {
            traceViewerPanel.webview.postMessage({
                type: 'traceEvent',
                event
            });
        }
    });

    traceSocketClient.on('batch', (events: TraceEvent[]) => {
        // Send performance data on batch updates
        if (traceViewerPanel && traceSocketClient) {
            traceViewerPanel.webview.postMessage({
                type: 'updatePerformance',
                data: traceSocketClient.getPerformanceData()
            });
        }
    });
}

async function connectToSocket(): Promise<void> {
    const config = vscode.workspace.getConfiguration('trueflow');
    const host = config.get<string>('socketHost', 'localhost');
    const port = config.get<number>('socketPort', 5678);

    if (traceSocketClient?.isConnected()) {
        vscode.window.showInformationMessage('Already connected to trace server');
        return;
    }

    try {
        await traceSocketClient?.connect(host, port);
    } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to connect to trace server: ${err.message}`);
    }
}

function disconnectSocket(): void {
    traceSocketClient?.disconnect();
    vscode.window.showInformationMessage('Disconnected from trace server');
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

    if (fileItems.length === 0) {
        vscode.window.showErrorMessage('No Python files found in workspace');
        return;
    }

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

    // Create traces directory
    const tracesDir = path.join(trueflowDir, 'traces');
    if (!fs.existsSync(tracesDir)) {
        fs.mkdirSync(tracesDir, { recursive: true });
    }

    // Copy runtime injector from extension bundle
    const injectorDest = path.join(trueflowDir, 'runtime_injector');
    await copyRuntimeInjector(context.extensionPath, injectorDest);

    // Create sitecustomize.py for automatic tracing
    const sitecustomizePath = path.join(trueflowDir, 'sitecustomize.py');
    const sitecustomizeContent = `# TrueFlow Auto-Instrumentation
# This file is automatically loaded when Python starts (via PYTHONPATH)
import os
import sys

# Only activate if TRUEFLOW_ENABLED is set
if os.environ.get('TRUEFLOW_ENABLED', '0') == '1':
    # Add runtime injector to path
    injector_path = os.path.join(os.path.dirname(__file__), 'runtime_injector')
    if injector_path not in sys.path:
        sys.path.insert(0, injector_path)

    # Import and start the instrumentor
    try:
        from python_runtime_instrumentor import RuntimeInstrumentor

        # Configure from environment
        trace_dir = os.environ.get('TRUEFLOW_TRACE_DIR', os.path.join(os.path.dirname(__file__), 'traces'))
        socket_port = int(os.environ.get('TRUEFLOW_SOCKET_PORT', '5678'))
        modules_to_trace = os.environ.get('TRUEFLOW_MODULES', '').split(',') if os.environ.get('TRUEFLOW_MODULES') else None
        exclude_modules = os.environ.get('TRUEFLOW_EXCLUDE', 'logging,asyncio,concurrent,socket,threading').split(',')

        # Start tracing
        instrumentor = RuntimeInstrumentor(
            trace_dir=trace_dir,
            socket_port=socket_port,
            modules_to_trace=modules_to_trace,
            exclude_modules=exclude_modules
        )
        instrumentor.start()

        print(f"[TrueFlow] Runtime instrumentation active - traces: {trace_dir}, socket: {socket_port}")
    except Exception as e:
        print(f"[TrueFlow] Failed to start instrumentation: {e}")
`;
    fs.writeFileSync(sitecustomizePath, sitecustomizeContent);

    // Ask user about launch configuration
    const action = await vscode.window.showInformationMessage(
        'TrueFlow integrated! Would you like to create a VS Code launch configuration?',
        'Yes', 'No'
    );

    if (action === 'Yes') {
        await createLaunchConfiguration(workspaceRoot, selected.label, trueflowDir);
    }

    vscode.window.showInformationMessage(
        `TrueFlow integrated! Run with: TRUEFLOW_ENABLED=1 python ${selected.label}`
    );
}

async function copyRuntimeInjector(extensionPath: string, destPath: string): Promise<void> {
    // Check if runtime_injector exists in extension
    const srcPath = path.join(extensionPath, 'runtime_injector');

    if (!fs.existsSync(destPath)) {
        fs.mkdirSync(destPath, { recursive: true });
    }

    if (fs.existsSync(srcPath)) {
        // Copy all files from source to destination
        const files = fs.readdirSync(srcPath);
        for (const file of files) {
            const srcFile = path.join(srcPath, file);
            const destFile = path.join(destPath, file);

            if (fs.statSync(srcFile).isFile()) {
                fs.copyFileSync(srcFile, destFile);
            }
        }
        console.log('[TrueFlow] Runtime injector copied successfully');
    } else {
        // Create a minimal runtime injector stub
        const stubContent = `# TrueFlow Runtime Instrumentor
# This is a stub - the full instrumentor should be bundled with the extension

import sys
import os
import json
import socket
import time
from datetime import datetime

class RuntimeInstrumentor:
    def __init__(self, trace_dir=None, socket_port=5678, modules_to_trace=None, exclude_modules=None):
        self.trace_dir = trace_dir or os.path.join(os.getcwd(), '.trueflow', 'traces')
        self.socket_port = socket_port
        self.modules_to_trace = set(modules_to_trace) if modules_to_trace else None
        self.exclude_modules = set(exclude_modules) if exclude_modules else set()
        self.call_id = 0
        self.depth = 0
        self.socket_client = None
        self.trace_file = None

    def start(self):
        os.makedirs(self.trace_dir, exist_ok=True)

        # Try to connect to socket server
        try:
            self.socket_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket_client.connect(('localhost', self.socket_port))
            self.socket_client.setblocking(False)
        except:
            self.socket_client = None

        # Create trace file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.trace_file = open(os.path.join(self.trace_dir, f'trace_{timestamp}.json'), 'w')

        # Install trace function
        sys.settrace(self.trace_func)

    def trace_func(self, frame, event, arg):
        if event not in ('call', 'return'):
            return self.trace_func

        module = frame.f_globals.get('__name__', '')

        # Skip excluded modules
        for exclude in self.exclude_modules:
            if module.startswith(exclude):
                return self.trace_func

        # Filter to specific modules if configured
        if self.modules_to_trace:
            if not any(module.startswith(m) for m in self.modules_to_trace):
                return self.trace_func

        self.call_id += 1

        trace_event = {
            'type': event,
            'timestamp': time.time(),
            'call_id': str(self.call_id),
            'module': module,
            'function': frame.f_code.co_name,
            'file': frame.f_code.co_filename,
            'line': frame.f_lineno,
            'depth': self.depth
        }

        if event == 'call':
            self.depth += 1
        elif event == 'return':
            self.depth = max(0, self.depth - 1)

        # Write to file
        if self.trace_file:
            self.trace_file.write(json.dumps(trace_event) + '\\n')
            self.trace_file.flush()

        # Send to socket
        if self.socket_client:
            try:
                self.socket_client.sendall((json.dumps(trace_event) + '\\n').encode())
            except:
                pass

        return self.trace_func

    def stop(self):
        sys.settrace(None)
        if self.trace_file:
            self.trace_file.close()
        if self.socket_client:
            self.socket_client.close()
`;
        fs.writeFileSync(path.join(destPath, 'python_runtime_instrumentor.py'), stubContent);
        console.log('[TrueFlow] Created runtime injector stub');
    }
}

async function createLaunchConfiguration(workspaceRoot: string, entryPoint: string, trueflowDir: string): Promise<void> {
    const vscodeDir = path.join(workspaceRoot, '.vscode');
    if (!fs.existsSync(vscodeDir)) {
        fs.mkdirSync(vscodeDir, { recursive: true });
    }

    const launchJsonPath = path.join(vscodeDir, 'launch.json');

    let launchConfig: any = {
        version: '0.2.0',
        configurations: []
    };

    // Read existing launch.json if it exists
    if (fs.existsSync(launchJsonPath)) {
        try {
            const content = fs.readFileSync(launchJsonPath, 'utf-8');
            // Remove comments for JSON parsing
            const jsonContent = content.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
            launchConfig = JSON.parse(jsonContent);
        } catch (e) {
            console.log('[TrueFlow] Could not parse existing launch.json, creating new');
        }
    }

    // Add TrueFlow configuration
    const trueflowConfig = {
        name: 'TrueFlow: Debug with Tracing',
        type: 'debugpy',
        request: 'launch',
        program: '${workspaceFolder}/' + entryPoint,
        console: 'integratedTerminal',
        env: {
            TRUEFLOW_ENABLED: '1',
            TRUEFLOW_TRACE_DIR: '${workspaceFolder}/.trueflow/traces',
            TRUEFLOW_SOCKET_PORT: '5678',
            PYTHONPATH: '${workspaceFolder}/.trueflow:${env:PYTHONPATH}'
        }
    };

    // Check if already exists
    const existingIndex = launchConfig.configurations.findIndex(
        (c: any) => c.name === 'TrueFlow: Debug with Tracing'
    );

    if (existingIndex >= 0) {
        launchConfig.configurations[existingIndex] = trueflowConfig;
    } else {
        launchConfig.configurations.push(trueflowConfig);
    }

    fs.writeFileSync(launchJsonPath, JSON.stringify(launchConfig, null, 4));
    vscode.window.showInformationMessage('TrueFlow launch configuration created!');
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

    // Handle messages from webview
    traceViewerPanel.webview.onDidReceiveMessage(async message => {
        switch (message.type) {
            case 'connect':
                await connectToSocket();
                break;
            case 'refresh':
                if (traceSocketClient) {
                    traceViewerPanel?.webview.postMessage({
                        type: 'updatePerformance',
                        data: traceSocketClient.getPerformanceData()
                    });
                }
                break;
            case 'info':
                vscode.window.showInformationMessage(message.message);
                break;
        }
    });

    traceViewerPanel.onDidDispose(() => {
        traceViewerPanel = undefined;
    });

    // Send initial connection status
    if (traceSocketClient?.isConnected()) {
        traceViewerPanel.webview.postMessage({ type: 'socketConnected' });
    }
}

async function generateManimVideo(context: vscode.ExtensionContext): Promise<void> {
    const config = vscode.workspace.getConfiguration('trueflow');
    const pythonPath = config.get<string>('pythonPath', 'python');
    const quality = config.get<string>('manimQuality', 'medium_quality');

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
        vscode.window.showErrorMessage('No workspace folder open');
        return;
    }

    const traceDir = path.join(workspaceFolders[0].uri.fsPath, '.trueflow', 'traces');

    // Find latest trace file
    if (!fs.existsSync(traceDir)) {
        vscode.window.showErrorMessage('No trace directory found. Run your application with TrueFlow first.');
        return;
    }

    const traceFiles = fs.readdirSync(traceDir)
        .filter(f => f.endsWith('.json'))
        .sort()
        .reverse();

    if (traceFiles.length === 0) {
        vscode.window.showErrorMessage('No trace files found. Run your application with TrueFlow first.');
        return;
    }

    const latestTrace = path.join(traceDir, traceFiles[0]);

    // Check for Manim visualizer script
    const manimScript = path.join(context.extensionPath, 'manim_visualizer', 'ultimate_architecture_viz.py');

    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Generating Manim video...',
        cancellable: true
    }, async (progress, token) => {
        progress.report({ increment: 0, message: 'Starting Manim render...' });

        return new Promise<void>((resolve, reject) => {
            const args = [
                manimScript,
                'UltimateArchitectureScene',
                '-q', quality.replace('_quality', '').charAt(0), // 'l', 'm', 'h'
                '--trace_file', latestTrace
            ];

            const proc = child_process.spawn(pythonPath, args, {
                cwd: workspaceFolders![0].uri.fsPath
            });

            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data) => {
                stdout += data.toString();
                progress.report({ increment: 10, message: 'Rendering...' });
            });

            proc.stderr.on('data', (data) => {
                stderr += data.toString();
            });

            proc.on('close', (code) => {
                if (code === 0) {
                    progress.report({ increment: 100, message: 'Video generated!' });
                    vscode.window.showInformationMessage('Manim video generated successfully!');
                    resolve();
                } else {
                    vscode.window.showErrorMessage(`Manim generation failed: ${stderr}`);
                    reject(new Error(stderr));
                }
            });

            token.onCancellationRequested(() => {
                proc.kill();
                reject(new Error('Cancelled'));
            });
        });
    });
}

async function exportDiagram(): Promise<void> {
    const formats = [
        { label: 'PlantUML (.puml)', ext: 'puml' },
        { label: 'Mermaid (.mmd)', ext: 'mmd' },
        { label: 'D2 (.d2)', ext: 'd2' },
        { label: 'JSON (.json)', ext: 'json' },
        { label: 'Markdown (.md)', ext: 'md' }
    ];

    const selected = await vscode.window.showQuickPick(formats, {
        placeHolder: 'Select export format'
    });

    if (!selected) {
        return;
    }

    const saveUri = await vscode.window.showSaveDialog({
        filters: {
            'Diagram Files': [selected.ext]
        },
        defaultUri: vscode.Uri.file(`diagram.${selected.ext}`)
    });

    if (saveUri) {
        // Get current diagram from webview if available
        if (traceViewerPanel) {
            // Request diagram content from webview
            // For now, export a placeholder
            const content = `# TrueFlow Export - ${selected.label}\n\n<!-- Export generated by TrueFlow -->`;
            fs.writeFileSync(saveUri.fsPath, content);
            vscode.window.showInformationMessage(`Diagram exported to ${saveUri.fsPath}`);
        }
    }
}

function setupTraceWatcher(context: vscode.ExtensionContext): void {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) return;

    const config = vscode.workspace.getConfiguration('trueflow');
    const traceDir = config.get<string>('traceDirectory', '.trueflow/traces');

    const watcher = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(workspaceFolders[0], `${traceDir}/**/*.json`)
    );

    watcher.onDidCreate(uri => {
        const autoRefresh = config.get<boolean>('autoRefresh', true);
        if (autoRefresh && traceViewerPanel) {
            traceViewerPanel.webview.postMessage({
                type: 'newTrace',
                path: uri.fsPath
            });
        }
    });

    context.subscriptions.push(watcher);
}

/**
 * Get HTML for the sidebar view - a compact dashboard with quick actions
 */
function getSidebarHtml(isConnected: boolean): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: var(--vscode-font-family);
            background-color: var(--vscode-sideBar-background);
            color: var(--vscode-sideBar-foreground);
            padding: 12px;
            font-size: 13px;
        }
        .logo {
            text-align: center;
            padding: 10px 0 15px;
            border-bottom: 1px solid var(--vscode-sideBarSectionHeader-border);
            margin-bottom: 15px;
        }
        .logo h2 {
            font-size: 16px;
            font-weight: 600;
            color: var(--vscode-sideBarTitle-foreground);
        }
        .logo p {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            margin-top: 4px;
        }
        .status-section {
            background: var(--vscode-sideBarSectionHeader-background);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 12px;
        }
        .status-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .status-row:last-child { margin-bottom: 0; }
        .status-label {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
        }
        .status-badge {
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
        }
        .status-connected { background: #2e7d32; color: white; }
        .status-disconnected { background: #c62828; color: white; }
        .metric-value {
            font-size: 14px;
            font-weight: 600;
            color: var(--vscode-charts-blue);
        }
        .action-buttons {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .action-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            text-align: left;
            transition: background 0.2s;
        }
        .action-btn:hover {
            background: var(--vscode-button-secondaryHoverBackground);
        }
        .action-btn.primary {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
        }
        .action-btn.primary:hover {
            background: var(--vscode-button-hoverBackground);
        }
        .action-btn .icon {
            font-size: 14px;
            width: 16px;
            text-align: center;
        }
        .section-title {
            font-size: 11px;
            font-weight: 600;
            color: var(--vscode-sideBarSectionHeader-foreground);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 15px 0 10px;
        }
        .quick-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 12px;
        }
        .stat-card {
            background: var(--vscode-sideBarSectionHeader-background);
            padding: 10px;
            border-radius: 4px;
            text-align: center;
        }
        .stat-value {
            font-size: 18px;
            font-weight: 700;
            color: var(--vscode-charts-green);
        }
        .stat-label {
            font-size: 10px;
            color: var(--vscode-descriptionForeground);
            margin-top: 2px;
        }
        .tabs {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 12px;
        }
        .tab {
            padding: 6px 10px;
            background: var(--vscode-sideBarSectionHeader-background);
            border: none;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            color: var(--vscode-sideBar-foreground);
        }
        .tab:hover {
            background: var(--vscode-list-hoverBackground);
        }
        .tab.active {
            background: var(--vscode-focusBorder);
            color: white;
        }
    </style>
</head>
<body>
    <div class="logo">
        <h2>TrueFlow</h2>
        <p>Deterministic Code Visualizer</p>
    </div>

    <div class="status-section">
        <div class="status-row">
            <span class="status-label">Connection</span>
            <span id="connection-status" class="status-badge ${isConnected ? 'status-connected' : 'status-disconnected'}">
                ${isConnected ? 'Connected' : 'Disconnected'}
            </span>
        </div>
        <div class="status-row">
            <span class="status-label">Events</span>
            <span id="event-count" class="metric-value">0</span>
        </div>
    </div>

    <div class="quick-stats">
        <div class="stat-card">
            <div id="stat-functions" class="stat-value">0</div>
            <div class="stat-label">Functions</div>
        </div>
        <div class="stat-card">
            <div id="stat-depth" class="stat-value">0</div>
            <div class="stat-label">Max Depth</div>
        </div>
    </div>

    <div class="section-title">Quick Actions</div>
    <div class="action-buttons">
        <button class="action-btn primary" onclick="action('autoIntegrate')">
            <span class="icon">⚡</span>
            <span>Auto-Integrate Project</span>
        </button>
        <button class="action-btn" onclick="action('${isConnected ? 'disconnect' : 'connect'}')">
            <span class="icon">${isConnected ? '🔴' : '🟢'}</span>
            <span>${isConnected ? 'Disconnect' : 'Connect to Server'}</span>
        </button>
        <button class="action-btn" onclick="action('openFullView')">
            <span class="icon">📊</span>
            <span>Open Full Trace Viewer</span>
        </button>
        <button class="action-btn" onclick="action('generateVideo')">
            <span class="icon">🎬</span>
            <span>Generate Manim Video</span>
        </button>
        <button class="action-btn" onclick="action('openAIChat')">
            <span class="icon">🤖</span>
            <span>AI Code Explainer</span>
        </button>
    </div>

    <div class="section-title">View Tabs</div>
    <div class="tabs">
        <button class="tab active" onclick="openTab('diagram')">Diagram</button>
        <button class="tab" onclick="openTab('performance')">Perf</button>
        <button class="tab" onclick="openTab('deadcode')">Dead</button>
        <button class="tab" onclick="openTab('trace')">Trace</button>
        <button class="tab" onclick="openTab('flamegraph')">Flame</button>
        <button class="tab" onclick="openTab('sql')">SQL</button>
        <button class="tab" onclick="openTab('manim')">Video</button>
    </div>

    <script>
        const vscode = acquireVsCodeApi();

        function action(type) {
            vscode.postMessage({ type: type });
        }

        function openTab(tab) {
            // Open full view with specific tab
            vscode.postMessage({ type: 'openFullView', tab: tab });
        }

        // Handle messages from extension
        window.addEventListener('message', event => {
            const message = event.data;
            switch (message.type) {
                case 'updateStats':
                    document.getElementById('event-count').textContent = message.events || 0;
                    document.getElementById('stat-functions').textContent = message.functions || 0;
                    document.getElementById('stat-depth').textContent = message.depth || 0;
                    break;
                case 'socketConnected':
                    document.getElementById('connection-status').textContent = 'Connected';
                    document.getElementById('connection-status').className = 'status-badge status-connected';
                    break;
                case 'socketDisconnected':
                    document.getElementById('connection-status').textContent = 'Disconnected';
                    document.getElementById('connection-status').className = 'status-badge status-disconnected';
                    break;
            }
        });
    </script>
</body>
</html>`;
}

function getTraceViewerHtml(): string {
    const isConnected = traceSocketClient?.isConnected() || false;

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow Trace Viewer</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: var(--vscode-font-family);
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            padding: 10px;
            min-height: 100vh;
        }
        .header {
            font-size: 1.2em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--vscode-panel-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header-title {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-badge {
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: bold;
        }
        .status-connected {
            background: #2e7d32;
            color: white;
        }
        .status-disconnected {
            background: #c62828;
            color: white;
        }
        .header-actions {
            display: flex;
            gap: 8px;
        }
        .header-actions button {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 4px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 11px;
        }
        .header-actions button:hover {
            background: var(--vscode-button-hoverBackground);
        }
        .tab-container {
            display: flex;
            border-bottom: 1px solid var(--vscode-panel-border);
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 2px;
        }
        .tab {
            padding: 8px 14px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
            font-size: 12px;
        }
        .tab:hover {
            background-color: var(--vscode-list-hoverBackground);
        }
        .tab.active {
            border-bottom-color: var(--vscode-focusBorder);
            background-color: var(--vscode-list-activeSelectionBackground);
        }
        .content {
            display: none;
            height: calc(100vh - 140px);
            overflow: auto;
        }
        .content.active {
            display: block;
        }
        .placeholder {
            text-align: center;
            color: var(--vscode-descriptionForeground);
            padding: 40px;
        }

        /* Diagram Tab */
        .diagram-container {
            display: flex;
            gap: 15px;
            height: 100%;
        }
        .diagram-code {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .diagram-code textarea {
            flex: 1;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
            resize: none;
            border-radius: 4px;
        }
        .diagram-preview {
            flex: 1;
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            overflow: auto;
            padding: 15px;
        }
        .diagram-preview .mermaid {
            display: flex;
            justify-content: center;
        }
        .diagram-toolbar {
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
            align-items: center;
            flex-wrap: wrap;
        }
        .diagram-toolbar select,
        .diagram-toolbar button {
            background: var(--vscode-dropdown-background);
            color: var(--vscode-dropdown-foreground);
            border: 1px solid var(--vscode-dropdown-border);
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
        }
        .diagram-toolbar button {
            cursor: pointer;
        }
        .diagram-toolbar button:hover {
            background: var(--vscode-button-secondaryHoverBackground);
        }

        /* Table Styles */
        .data-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        .data-table th,
        .data-table td {
            padding: 6px 10px;
            text-align: left;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        .data-table th {
            background: var(--vscode-editor-lineHighlightBackground);
            cursor: pointer;
            position: sticky;
            top: 0;
        }
        .data-table th:hover {
            background: var(--vscode-list-hoverBackground);
        }
        .data-table tr:hover {
            background: var(--vscode-list-hoverBackground);
        }

        /* Call Trace Tree */
        .call-tree {
            font-family: monospace;
            font-size: 12px;
        }
        .call-node {
            padding: 2px 0;
        }
        .call-node .module {
            color: var(--vscode-symbolIcon-namespaceForeground);
        }
        .call-node .function {
            color: var(--vscode-symbolIcon-functionForeground);
        }
        .call-node .duration {
            color: var(--vscode-descriptionForeground);
            margin-left: 10px;
        }

        /* Flamegraph placeholder */
        .flamegraph-container {
            height: 100%;
            display: flex;
            flex-direction: column;
        }
        .flamegraph-canvas {
            flex: 1;
            background: #1e1e1e;
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
        }

        /* Live Metrics */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            padding: 10px;
        }
        .metric-card {
            background: var(--vscode-editor-lineHighlightBackground);
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: var(--vscode-charts-blue);
        }
        .metric-label {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            margin-top: 5px;
        }

        /* SQL Tab */
        .sql-query {
            background: var(--vscode-editor-lineHighlightBackground);
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
        }
        .sql-warning {
            color: #f9a825;
            font-weight: bold;
        }
        .sql-error {
            color: #e53935;
            font-weight: bold;
        }

        /* Zoom controls */
        .zoom-controls {
            position: fixed;
            bottom: 20px;
            right: 20px;
            display: none;
            gap: 4px;
            z-index: 1000;
        }
        .zoom-controls.visible {
            display: flex;
        }
        .zoom-controls button {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            width: 28px;
            height: 28px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }

        /* Event counter */
        .event-counter {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <span>TrueFlow</span>
            <span id="connection-status" class="status-badge ${isConnected ? 'status-connected' : 'status-disconnected'}">
                ${isConnected ? 'Connected' : 'Disconnected'}
            </span>
            <span id="event-counter" class="event-counter"></span>
        </div>
        <div class="header-actions">
            <button onclick="connectSocket()">Connect</button>
            <button onclick="refreshData()">Refresh</button>
        </div>
    </div>

    <div class="tab-container">
        <div class="tab active" data-tab="diagram">Diagram</div>
        <div class="tab" data-tab="performance">Performance</div>
        <div class="tab" data-tab="deadcode">Dead Code</div>
        <div class="tab" data-tab="trace">Call Trace</div>
        <div class="tab" data-tab="flamegraph">Flamegraph</div>
        <div class="tab" data-tab="sql">SQL Analyzer</div>
        <div class="tab" data-tab="metrics">Live Metrics</div>
        <div class="tab" data-tab="distributed">Distributed</div>
        <div class="tab" data-tab="manim">Manim Video</div>
    </div>

    <!-- Diagram Tab -->
    <div class="content active" id="diagram-content">
        <div class="diagram-toolbar">
            <select id="diagram-type" onchange="updateDiagramType()">
                <option value="mermaid" selected>Mermaid</option>
                <option value="plantuml">PlantUML</option>
            </select>
            <button onclick="renderDiagram()">Render</button>
            <button onclick="copyDiagram()">Copy</button>
            <span id="diagram-status"></span>
        </div>
        <div class="diagram-container">
            <div class="diagram-code">
                <textarea id="diagram-code" placeholder="Mermaid code...">sequenceDiagram
    participant User
    participant App
    participant Database

    Note over User,Database: TrueFlow Sequence Diagram

    User->>App: Request
    activate App
    App->>Database: Query
    activate Database
    Database-->>App: Results
    deactivate Database
    App-->>User: Response
    deactivate App</textarea>
            </div>
            <div class="diagram-preview">
                <div id="mermaid-output" class="mermaid">sequenceDiagram
    participant User
    participant App
    participant Database

    Note over User,Database: TrueFlow Sequence Diagram

    User->>App: Request
    activate App
    App->>Database: Query
    activate Database
    Database-->>App: Results
    deactivate Database
    App-->>User: Response
    deactivate App</div>
            </div>
        </div>
    </div>

    <!-- Performance Tab -->
    <div class="content" id="performance-content">
        <table class="data-table">
            <thead>
                <tr>
                    <th onclick="sortTable('module')">Module</th>
                    <th onclick="sortTable('function')">Function</th>
                    <th onclick="sortTable('calls')">Calls</th>
                    <th onclick="sortTable('total')">Total (ms)</th>
                    <th onclick="sortTable('avg')">Avg (ms)</th>
                    <th onclick="sortTable('min')">Min (ms)</th>
                    <th onclick="sortTable('max')">Max (ms)</th>
                </tr>
            </thead>
            <tbody id="performance-body">
                <tr><td colspan="7" class="placeholder">Connect to trace server to see performance data</td></tr>
            </tbody>
        </table>
    </div>

    <!-- Dead Code Tab -->
    <div class="content" id="deadcode-content">
        <div id="deadcode-list">
            <div class="placeholder">
                <p>Run your application with TrueFlow to detect uncovered functions.</p>
            </div>
        </div>
    </div>

    <!-- Call Trace Tab -->
    <div class="content" id="trace-content">
        <div id="call-tree" class="call-tree">
            <div class="placeholder">
                <p>Connect to trace server to see live call traces.</p>
            </div>
        </div>
    </div>

    <!-- Flamegraph Tab -->
    <div class="content" id="flamegraph-content">
        <div class="flamegraph-container">
            <div class="flamegraph-canvas" id="flamegraph">
                <div class="placeholder">
                    <p>Performance flamegraph will be rendered here from trace data.</p>
                </div>
            </div>
        </div>
    </div>

    <!-- SQL Analyzer Tab -->
    <div class="content" id="sql-content">
        <h3>SQL Query Analyzer</h3>
        <p>SQL queries and potential N+1 problems will appear here.</p>
        <div id="sql-queries">
            <div class="placeholder">
                <p>No SQL queries detected yet. Run your application with TrueFlow.</p>
            </div>
        </div>
    </div>

    <!-- Live Metrics Tab -->
    <div class="content" id="metrics-content">
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value" id="metric-events">0</div>
                <div class="metric-label">Events Processed</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="metric-functions">0</div>
                <div class="metric-label">Functions Traced</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="metric-depth">0</div>
                <div class="metric-label">Max Call Depth</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="metric-rate">0</div>
                <div class="metric-label">Events/sec</div>
            </div>
        </div>
    </div>

    <!-- Distributed Tab -->
    <div class="content" id="distributed-content">
        <h3>Distributed Architecture</h3>
        <p>WebSocket, gRPC, Kafka, and other distributed calls will appear here.</p>
        <div id="distributed-calls">
            <div class="placeholder">
                <p>No distributed calls detected yet.</p>
            </div>
        </div>
    </div>

    <!-- Manim Video Tab -->
    <div class="content" id="manim-content">
        <h3>Manim Video</h3>
        <p>Use "TrueFlow: Generate Manim Video" command to create visualizations.</p>
        <div id="video-container">
            <div class="placeholder">
                <p>Generated execution flow videos will appear here.</p>
            </div>
        </div>
    </div>

    <div class="zoom-controls" id="zoom-controls">
        <button onclick="zoomIn()">+</button>
        <button onclick="zoomOut()">-</button>
        <button onclick="resetZoom()">R</button>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        let currentZoom = 1;
        let eventCount = 0;
        let functionCount = 0;
        let maxDepth = 0;
        let lastEventTime = Date.now();
        let eventsPerSecond = 0;
        let performanceData = [];
        let callTrace = [];

        // Initialize Mermaid
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
                useMaxWidth: true,
                mirrorActors: true
            },
            themeVariables: {
                darkMode: true,
                primaryColor: '#3c3c3c',
                primaryTextColor: '#d4d4d4',
                primaryBorderColor: '#569cd6',
                lineColor: '#4ec9b0',
                background: '#1e1e1e',
                mainBkg: '#2d2d2d',
                textColor: '#d4d4d4'
            }
        });

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                document.querySelectorAll('.content').forEach(c => c.classList.remove('active'));
                document.getElementById(tabName + '-content').classList.add('active');

                // Show zoom controls only for diagram tab
                document.getElementById('zoom-controls').classList.toggle('visible', tabName === 'diagram');
            });
        });

        // Diagram functions
        function updateDiagramType() {
            const type = document.getElementById('diagram-type').value;
            if (type === 'plantuml') {
                document.getElementById('diagram-status').textContent = 'PlantUML: Use Mermaid for preview';
            } else {
                document.getElementById('diagram-status').textContent = '';
                renderDiagram();
            }
        }

        function renderDiagram() {
            const code = document.getElementById('diagram-code').value;
            const output = document.getElementById('mermaid-output');

            try {
                output.innerHTML = code;
                output.removeAttribute('data-processed');
                mermaid.init(undefined, output);
                document.getElementById('diagram-status').textContent = 'Rendered';
            } catch (e) {
                document.getElementById('diagram-status').textContent = 'Error: ' + e.message;
            }
        }

        function copyDiagram() {
            const code = document.getElementById('diagram-code').value;
            navigator.clipboard.writeText(code);
            vscode.postMessage({ type: 'info', message: 'Diagram code copied!' });
        }

        function connectSocket() {
            vscode.postMessage({ type: 'connect' });
        }

        function refreshData() {
            vscode.postMessage({ type: 'refresh' });
        }

        // Zoom functions
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
            const preview = document.querySelector('.diagram-preview');
            preview.style.transform = 'scale(' + currentZoom + ')';
            preview.style.transformOrigin = 'top left';
        }

        // Table sorting
        let sortColumn = 'total';
        let sortAsc = false;

        function sortTable(column) {
            if (sortColumn === column) {
                sortAsc = !sortAsc;
            } else {
                sortColumn = column;
                sortAsc = false;
            }
            updatePerformanceTable(performanceData);
        }

        function updatePerformanceTable(data) {
            performanceData = data;
            const tbody = document.getElementById('performance-body');

            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="placeholder">No performance data available</td></tr>';
                return;
            }

            // Sort data
            const sorted = [...data].sort((a, b) => {
                const aVal = a[sortColumn];
                const bVal = b[sortColumn];
                return sortAsc ? (aVal > bVal ? 1 : -1) : (aVal < bVal ? 1 : -1);
            });

            tbody.innerHTML = sorted.map(row =>
                '<tr>' +
                '<td>' + escapeHtml(row.module) + '</td>' +
                '<td>' + escapeHtml(row.function) + '</td>' +
                '<td>' + row.calls + '</td>' +
                '<td>' + row.total.toFixed(2) + '</td>' +
                '<td>' + row.avg.toFixed(2) + '</td>' +
                '<td>' + row.min.toFixed(2) + '</td>' +
                '<td>' + row.max.toFixed(2) + '</td>' +
                '</tr>'
            ).join('');

            functionCount = data.length;
            document.getElementById('metric-functions').textContent = functionCount;
        }

        function updateCallTrace(events) {
            callTrace = events;
            const container = document.getElementById('call-tree');

            if (!events || events.length === 0) {
                container.innerHTML = '<div class="placeholder">No call trace data</div>';
                return;
            }

            container.innerHTML = events.slice(-50).map(e => {
                const indent = '  '.repeat(e.depth);
                const arrow = e.type === 'call' ? '→' : '←';
                const duration = e.duration_ms ? ' (' + e.duration_ms.toFixed(2) + 'ms)' : '';
                return '<div class="call-node">' + indent + arrow + ' ' +
                    '<span class="module">' + escapeHtml(e.module) + '</span>.' +
                    '<span class="function">' + escapeHtml(e.function) + '</span>' +
                    '<span class="duration">' + duration + '</span></div>';
            }).join('');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Handle messages from extension
        window.addEventListener('message', event => {
            const message = event.data;

            switch (message.type) {
                case 'socketConnected':
                    document.getElementById('connection-status').textContent = 'Connected';
                    document.getElementById('connection-status').className = 'status-badge status-connected';
                    break;

                case 'socketDisconnected':
                    document.getElementById('connection-status').textContent = 'Disconnected';
                    document.getElementById('connection-status').className = 'status-badge status-disconnected';
                    break;

                case 'traceEvent':
                    eventCount++;
                    maxDepth = Math.max(maxDepth, message.event.depth);
                    document.getElementById('event-counter').textContent = eventCount + ' events';
                    document.getElementById('metric-events').textContent = eventCount;
                    document.getElementById('metric-depth').textContent = maxDepth;

                    // Calculate events per second
                    const now = Date.now();
                    eventsPerSecond = Math.round(1000 / (now - lastEventTime));
                    lastEventTime = now;
                    document.getElementById('metric-rate').textContent = eventsPerSecond;

                    // Add to call trace
                    callTrace.push(message.event);
                    if (callTrace.length > 1000) callTrace.shift();
                    updateCallTrace(callTrace);
                    break;

                case 'updatePerformance':
                    updatePerformanceTable(message.data);
                    break;

                case 'updateDiagram':
                    document.getElementById('diagram-code').value = message.code;
                    renderDiagram();
                    break;

                case 'newTrace':
                    document.getElementById('diagram-status').textContent = 'New trace: ' + message.path;
                    break;
            }
        });

        // Auto-render on code change
        let renderTimeout;
        document.getElementById('diagram-code').addEventListener('input', () => {
            clearTimeout(renderTimeout);
            renderTimeout = setTimeout(renderDiagram, 500);
        });

        // Initial render
        setTimeout(renderDiagram, 100);
    </script>
</body>
</html>`;
}

// AI Model Download and Server Management

async function downloadAIModel(): Promise<void> {
    // Let user select model
    const modelItems = MODEL_PRESETS.map(m => ({
        label: m.displayName,
        description: `${m.sizeMB}MB - ${m.description}`,
        preset: m
    }));

    // Add custom URL option
    modelItems.push({
        label: "Custom HuggingFace Model...",
        description: "Enter a custom GGUF model URL",
        preset: null as any
    });

    const selected = await vscode.window.showQuickPick(modelItems, {
        placeHolder: 'Select an AI model to download'
    });

    if (!selected) {
        return;
    }

    let downloadUrl: string;
    let fileName: string;

    if (selected.preset) {
        downloadUrl = `https://huggingface.co/${selected.preset.repoId}/resolve/main/${selected.preset.fileName}`;
        fileName = selected.preset.fileName;
    } else {
        // Custom URL
        const customUrl = await vscode.window.showInputBox({
            prompt: 'Enter HuggingFace GGUF model URL',
            placeHolder: 'https://huggingface.co/user/repo/resolve/main/model.gguf',
            validateInput: (value) => {
                if (!value.endsWith('.gguf')) {
                    return 'URL must point to a .gguf file';
                }
                return null;
            }
        });

        if (!customUrl) {
            return;
        }

        downloadUrl = customUrl;
        fileName = customUrl.split('/').pop() || 'model.gguf';
    }

    // Create models directory
    const modelsDir = path.join(getHomeDir(), '.trueflow', 'models');
    if (!fs.existsSync(modelsDir)) {
        fs.mkdirSync(modelsDir, { recursive: true });
    }

    const destPath = path.join(modelsDir, fileName);

    // Check if already downloaded
    if (fs.existsSync(destPath)) {
        const overwrite = await vscode.window.showWarningMessage(
            `Model ${fileName} already exists. Overwrite?`,
            'Yes', 'No'
        );
        if (overwrite !== 'Yes') {
            currentModelPath = destPath;
            vscode.window.showInformationMessage(`Using existing model: ${fileName}`);
            return;
        }
    }

    // Download with progress
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `Downloading ${fileName}...`,
        cancellable: true
    }, async (progress, token) => {
        return new Promise<void>((resolve, reject) => {
            const file = fs.createWriteStream(destPath);
            let downloadedBytes = 0;
            let totalBytes = 0;

            const request = https.get(downloadUrl, {
                headers: { 'User-Agent': 'TrueFlow/1.0' }
            }, (response) => {
                // Handle redirects
                if (response.statusCode === 302 || response.statusCode === 301) {
                    const redirectUrl = response.headers.location;
                    if (redirectUrl) {
                        https.get(redirectUrl, {
                            headers: { 'User-Agent': 'TrueFlow/1.0' }
                        }, handleResponse).on('error', reject);
                        return;
                    }
                }
                handleResponse(response);
            });

            function handleResponse(response: any) {
                totalBytes = parseInt(response.headers['content-length'] || '0', 10);

                response.pipe(file);

                response.on('data', (chunk: Buffer) => {
                    downloadedBytes += chunk.length;
                    const pct = totalBytes > 0 ? Math.round((downloadedBytes / totalBytes) * 100) : 0;
                    const downloadedMB = Math.round(downloadedBytes / (1024 * 1024));
                    const totalMB = Math.round(totalBytes / (1024 * 1024));
                    progress.report({
                        increment: pct / 100,
                        message: `${downloadedMB}MB / ${totalMB}MB (${pct}%)`
                    });
                });

                file.on('finish', () => {
                    file.close();
                    currentModelPath = destPath;
                    vscode.window.showInformationMessage(`Model downloaded: ${fileName}`);
                    resolve();
                });
            }

            request.on('error', (err) => {
                fs.unlink(destPath, () => {});
                reject(err);
            });

            token.onCancellationRequested(() => {
                request.destroy();
                fs.unlink(destPath, () => {});
                reject(new Error('Download cancelled'));
            });
        });
    });
}

async function startAIServer(): Promise<void> {
    if (llmServerProcess) {
        vscode.window.showWarningMessage('AI server is already running');
        return;
    }

    // Find model
    const modelsDir = path.join(getHomeDir(), '.trueflow', 'models');
    if (!fs.existsSync(modelsDir)) {
        vscode.window.showErrorMessage('No models found. Please download a model first.');
        return;
    }

    const modelFiles = fs.readdirSync(modelsDir).filter(f => f.endsWith('.gguf'));
    if (modelFiles.length === 0) {
        vscode.window.showErrorMessage('No GGUF models found. Please download a model first.');
        return;
    }

    // Let user select model if multiple
    let modelPath: string;
    if (modelFiles.length === 1) {
        modelPath = path.join(modelsDir, modelFiles[0]);
    } else {
        const selected = await vscode.window.showQuickPick(modelFiles, {
            placeHolder: 'Select model to load'
        });
        if (!selected) {
            return;
        }
        modelPath = path.join(modelsDir, selected);
    }

    // Find llama-server
    const llamaServer = findLlamaServer();
    if (!llamaServer) {
        const install = await vscode.window.showErrorMessage(
            'llama.cpp not found. Would you like to see installation instructions?',
            'Yes', 'No'
        );
        if (install === 'Yes') {
            vscode.env.openExternal(vscode.Uri.parse('https://github.com/ggerganov/llama.cpp#build'));
        }
        return;
    }

    // Start server
    const cpuCount = require('os').cpus().length;
    const args = [
        '--model', modelPath,
        '--port', '8080',
        '--ctx-size', '4096',
        '--threads', String(cpuCount),
        '--host', '127.0.0.1'
    ];

    vscode.window.showInformationMessage('Starting AI server...');

    llmServerProcess = child_process.spawn(llamaServer, args);

    llmServerProcess.stdout?.on('data', (data) => {
        console.log('[LLM Server]', data.toString());
    });

    llmServerProcess.stderr?.on('data', (data) => {
        console.log('[LLM Server]', data.toString());
    });

    llmServerProcess.on('close', (code) => {
        llmServerProcess = undefined;
        if (code !== 0) {
            vscode.window.showErrorMessage(`AI server exited with code ${code}`);
        }
    });

    // Wait for server to be ready
    await new Promise(resolve => setTimeout(resolve, 5000));
    vscode.window.showInformationMessage('AI server started on port 8080');
}

function stopAIServer(): void {
    if (llmServerProcess) {
        llmServerProcess.kill();
        llmServerProcess = undefined;
        vscode.window.showInformationMessage('AI server stopped');
    } else {
        vscode.window.showWarningMessage('AI server is not running');
    }
}

function findLlamaServer(): string | null {
    const homeDir = getHomeDir();
    const possiblePaths = [
        path.join(homeDir, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server'),
        path.join(homeDir, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server.exe'),
        path.join(homeDir, 'llama.cpp', 'build', 'bin', 'llama-server'),
        path.join(homeDir, 'llama.cpp', 'build', 'bin', 'llama-server.exe'),
        '/usr/local/bin/llama-server',
        'C:\\llama.cpp\\build\\bin\\llama-server.exe'
    ];

    for (const p of possiblePaths) {
        if (fs.existsSync(p)) {
            return p;
        }
    }

    // Check PATH
    try {
        const which = process.platform === 'win32' ? 'where' : 'which';
        const result = child_process.execSync(`${which} llama-server`, { encoding: 'utf-8' });
        return result.trim().split('\n')[0];
    } catch {
        return null;
    }
}

function getHomeDir(): string {
    return process.env.HOME || process.env.USERPROFILE || '';
}

export function deactivate() {
    if (traceViewerPanel) {
        traceViewerPanel.dispose();
    }
    if (traceSocketClient) {
        traceSocketClient.disconnect();
    }
    if (llmServerProcess) {
        llmServerProcess.kill();
    }
}
