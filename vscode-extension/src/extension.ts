import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as https from 'https';
import * as net from 'net';
import * as child_process from 'child_process';
import { TraceSocketClient, TraceEvent, PerformanceData } from './TraceSocketClient';
import { AIExplanationProvider } from './AIExplanationWebview';
import { InteractiveExplorerServer } from './InteractiveExplorerServer';
import { HubClient } from './HubClient';

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
let currentContextSelection: number = 0;

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
let mcpStatusBarItem: vscode.StatusBarItem;
let sidebarProvider: TrueFlowSidebarProvider | undefined;
let explorerServer: InteractiveExplorerServer | undefined;

// Per-function protocol accumulation from trace events (for explorer visualization)
const functionProtocols: Map<string, Record<string, number>> = new Map();
const functionFrameworks: Map<string, string> = new Map();
const functionAiAgents: Set<string> = new Set();

/**
 * Get the global TraceSocketClient instance (for session save/restore and RPC fallback).
 */
export function getGlobalTraceSocketClient(): TraceSocketClient | undefined {
    return traceSocketClient;
}

/**
 * Push restored session data to the trace viewer webview (called after session restore).
 */
export function pushRestoredSessionToViewer(diagramCode?: string, deadCodeData?: any, performanceData?: any): void {
    if (!traceViewerPanel) { return; }

    if (diagramCode) {
        traceViewerPanel.webview.postMessage({ type: 'updateDiagram', code: diagramCode });
    }
    if (performanceData) {
        traceViewerPanel.webview.postMessage({ type: 'updatePerformance', data: performanceData });
    }
}

// Track active processes started by this VS Code instance (without tracing)
let activeProcessesWithoutTracing = new Set<string>();
let statusBarPulseInterval: NodeJS.Timeout | undefined;

// Global trace filter state (applies to all tabs)
interface TraceFilter {
    includeModules: string[];  // Modules to include (empty = all)
    excludeModules: string[];  // Modules to exclude
    minDepth: number;          // Minimum call depth to show
    maxDepth: number;          // Maximum call depth to show (0 = unlimited)
}

let traceFilter: TraceFilter = {
    includeModules: [],
    excludeModules: ['logging', 'asyncio', 'concurrent', 'socket', 'threading', '_frozen_importlib'],
    minDepth: 0,
    maxDepth: 0
};

function getFilterStats(): string {
    const parts: string[] = [];
    if (traceFilter.includeModules.length > 0) {
        parts.push(`+${traceFilter.includeModules.length} inc`);
    }
    if (traceFilter.excludeModules.length > 0) {
        parts.push(`-${traceFilter.excludeModules.length} exc`);
    }
    if (traceFilter.maxDepth > 0) {
        parts.push(`depth<=${traceFilter.maxDepth}`);
    }
    return parts.length > 0 ? parts.join(', ') : 'None';
}

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
                    showTraceViewer(this._extensionContext, message.tab);
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
                case 'manageFilters':
                    showFilterManagementDialog();
                    break;
                case 'contextChanged':
                    // Store context selection for AI panel to use
                    currentContextSelection = message.value;
                    AIExplanationProvider.getInstance().setContextSelection(message.value);
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

// Server auto-detection state
let serverDetectionInterval: NodeJS.Timeout | undefined;
let lastServerNotificationTime = 0;
let lastServerDetectedPort = 0;  // Store detected port for direct connect
const SERVER_DETECTION_INTERVAL_MS = 3000;
const SERVER_NOTIFICATION_COOLDOWN_MS = 60000;
let serverNotificationShown = false;
let serverIsUp = false;          // Tracks DOWN->UP transitions
let consecutiveServerMisses = 0;
const MISSES_TO_RESET = 3;

// Hub restart debounce - prevent multiple simultaneous start attempts
let lastHubRestartAttempt = 0;
const HUB_RESTART_DEBOUNCE_MS = 15000; // 15 seconds between restart attempts
let hubRestartInProgress = false;

/**
 * Debounced hub restart - ensures only one restart attempt within HUB_RESTART_DEBOUNCE_MS.
 * Returns true if this call won the debounce and should proceed.
 */
function tryEnsureHubRunning(reason: string): boolean {
    const now = Date.now();
    if (now - lastHubRestartAttempt < HUB_RESTART_DEBOUNCE_MS) {
        console.log(`[TrueFlow] Hub restart debounced (${reason}), last attempt ${now - lastHubRestartAttempt}ms ago`);
        return false;
    }
    if (hubRestartInProgress) {
        console.log(`[TrueFlow] Hub restart already in progress (${reason})`);
        return false;
    }
    lastHubRestartAttempt = now;
    hubRestartInProgress = true;
    console.log(`[TrueFlow] ${reason}, ensuring MCP hub is running...`);
    HubClient.getInstance().connect()
        .catch((e: any) => console.log('[TrueFlow] Hub ensure attempt failed:', e))
        .finally(() => { hubRestartInProgress = false; });
    return true;
}

// Task/run detection state
let taskDetectionDisabled = false;
let lastTaskNotificationTime = 0;
const TASK_NOTIFICATION_COOLDOWN_MS = 60000;

export function activate(context: vscode.ExtensionContext) {
    console.log('TrueFlow extension is now active');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(debug-disconnect) TrueFlow';
    statusBarItem.tooltip = 'TrueFlow: Click to connect to trace server';
    statusBarItem.command = 'trueflow.connectSocket';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // MCP/AI Server status bar item
    mcpStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 99);
    mcpStatusBarItem.text = '$(circle-outline) MCP';
    mcpStatusBarItem.tooltip = 'MCP/AI Server: Not running - start llama.cpp on port 8080 for AI features';
    mcpStatusBarItem.show();
    context.subscriptions.push(mcpStatusBarItem);

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
        vscode.commands.registerCommand('trueflow.showAIChat', () => AIExplanationProvider.getInstance().show(context)),
        vscode.commands.registerCommand('trueflow.exposeAsMCPTool', () => exposeEditorFunctionAsMCPTool())
    ];

    context.subscriptions.push(...commands);

    // Watch for trace file changes
    setupTraceWatcher(context);

    // Start server auto-detection
    startServerDetection(context);

    // Listen for task/terminal executions to detect un-traced runs
    setupTaskDetection(context);
}

function setupSocketClientHandlers(): void {
    if (!traceSocketClient) return;

    traceSocketClient.on('connected', () => {
        statusBarItem.text = '$(debug-alt) TrueFlow';
        statusBarItem.tooltip = 'TrueFlow: Connected to trace server';
        statusBarItem.backgroundColor = undefined;
        vscode.window.showInformationMessage('TrueFlow: Connected to trace server');

        // Update webviews
        if (traceViewerPanel) {
            traceViewerPanel.webview.postMessage({ type: 'socketConnected' });
        }
        if (sidebarProvider) {
            sidebarProvider.postMessage({ type: 'socketConnected' });
        }

        // Ensure MCP Hub is also running (may have been killed by taskkill /F /IM python.exe)
        let hubConnected = false;
        try { hubConnected = HubClient.getInstance().isConnected(); } catch (_) { /* not initialized */ }
        if (!hubConnected) {
            tryEnsureHubRunning('Trace server connected but hub down');
        }
    });

    traceSocketClient.on('disconnected', () => {
        statusBarItem.text = '$(debug-disconnect) TrueFlow';
        statusBarItem.tooltip = 'TrueFlow: Disconnected from trace server';

        // Notify panels
        if (sidebarProvider) {
            sidebarProvider.postMessage({ type: 'socketDisconnected' });
        }
        if (traceViewerPanel) {
            traceViewerPanel.webview.postMessage({ type: 'socketDisconnected' });
        }
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

        // Accumulate per-function protocol data for Interactive Explorer
        const funcKey = `${event.module}.${event.function}`;
        if (event.type === 'call') {
            if (event.framework) {
                functionFrameworks.set(funcKey, event.framework);
            }
            if (event.is_ai_agent) {
                functionAiAgents.add(funcKey);
            }
        } else if (event.type === 'return' && event.protocol_summary) {
            const existing = functionProtocols.get(funcKey) || {};
            for (const [proto, count] of Object.entries(event.protocol_summary)) {
                existing[proto] = (existing[proto] || 0) + (typeof count === 'number' ? count : 1);
            }
            functionProtocols.set(funcKey, existing);
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

        // Update AI panel with trace data for context injection
        if (traceSocketClient) {
            const perfData = traceSocketClient.getPerformanceData();
            const aiProvider = AIExplanationProvider.getInstance();
            const callTraceData = {
                calls: events.map(e => ({
                    function: e.function,
                    module: e.module,
                    depth: e.depth,
                    duration_ms: e.duration_ms || 0,
                    type: e.type
                })),
                total_calls: events.length
            };
            aiProvider.setCallTraceData(callTraceData);
            aiProvider.setPerformanceData(perfData);
            // Update rich dead code data for MCP RPC
            buildAndSetRichDeadCodeData();
            // Save snapshot after data update
            aiProvider.saveSnapshot();
        }
    });

    // Handle function registry for dead code detection
    traceSocketClient.on('functionRegistry', (event: TraceEvent) => {
        if (traceViewerPanel) {
            traceViewerPanel.webview.postMessage({
                type: 'functionRegistry',
                data: event.trace_data
            });
        }
        // Update RPC dead code data when registry changes
        buildAndSetRichDeadCodeData();
    });

    // Handle branch registry for "Why Not Covered" with actual branch conditions
    traceSocketClient.on('branchRegistry', (event: TraceEvent) => {
        if (traceViewerPanel) {
            traceViewerPanel.webview.postMessage({
                type: 'branchRegistry',
                data: event.trace_data
            });
        }
        // Update RPC dead code data when call graph changes
        buildAndSetRichDeadCodeData();
    });
}

/**
 * Build rich dead code data (matching PyCharm's updateAIExplanationPanel) and pass to AI provider for RPC.
 * Uses data from TraceSocketClient: functionRegistry, callStats, resolvedCallGraph, callSites.
 */
function buildAndSetRichDeadCodeData(): void {
    if (!traceSocketClient) return;

    const functionRegistry = traceSocketClient.getFunctionRegistry();
    const callStats = traceSocketClient.getCallStats();
    const resolvedCallGraph = traceSocketClient.getResolvedCallGraph();
    const callSites = traceSocketClient.getCallSites();

    if (functionRegistry.size === 0) return; // No registry yet

    // All defined functions from registry
    const allDefined = new Set(functionRegistry.keys());

    // Add functions from resolved call graph that aren't in registry
    for (const [caller, callees] of Object.entries(resolvedCallGraph)) {
        allDefined.add(caller);
        for (const callee of callees) {
            allDefined.add(callee);
        }
    }

    // Covered functions (those with call stats)
    const coveredKeys = new Set(callStats.keys());

    // Build reverse call graph
    const reverseGraph: Record<string, string[]> = {};
    for (const [caller, callees] of Object.entries(resolvedCallGraph)) {
        for (const callee of callees) {
            if (!reverseGraph[callee]) reverseGraph[callee] = [];
            if (!reverseGraph[callee].includes(caller)) {
                reverseGraph[callee].push(caller);
            }
        }
    }

    // Root cause tracing (same as PyCharm)
    function traceToRootCause(func: string, visited: Set<string>, chain: string[]): { type: string; rootFunc: string; chain: string[] } | null {
        if (visited.has(func)) return null;
        visited.add(func);
        chain.push(func);
        const callers = reverseGraph[func] || [];
        if (callers.length === 0) return { type: 'NO_CALL_SITES', rootFunc: func, chain: [...chain] };
        for (const caller of callers) {
            if (coveredKeys.has(caller)) return { type: 'BRANCH_NOT_TAKEN', rootFunc: caller, chain: [...chain] };
        }
        for (const caller of callers) {
            const result = traceToRootCause(caller, visited, chain);
            if (result) return result;
        }
        return { type: 'UNREACHABLE_FROM_ENTRY', rootFunc: chain[chain.length - 1], chain: [...chain] };
    }

    // Helper to build callers array with alive/dead status
    function buildCallersArray(funcKey: string): any[] {
        const directCallers = reverseGraph[funcKey] || [];
        return directCallers.map(caller => {
            const parts = caller.split('.');
            const isAlive = coveredKeys.has(caller);
            return {
                key: caller,
                module: parts.slice(0, -1).join('.') || '__main__',
                function: parts[parts.length - 1] || caller,
                status: isAlive ? 'ALIVE' : 'DEAD',
                call_count: callStats.get(caller)?.count || 0,
                has_call_site: (resolvedCallGraph[caller] || []).includes(funcKey),
                actually_called: isAlive && coveredKeys.has(funcKey)
            };
        });
    }

    // Categorize functions
    const deadFunctions: any[] = [];
    const aliveFunctions: any[] = [];
    const externalFunctions: any[] = [];

    // Dead functions (in registry, never called)
    for (const funcKey of [...allDefined].sort()) {
        if (coveredKeys.has(funcKey)) continue;
        const parts = funcKey.split('.');
        const regInfo = functionRegistry.get(funcKey);

        const rootCause = traceToRootCause(funcKey, new Set(), []) ||
            { type: 'UNKNOWN', rootFunc: funcKey, chain: [funcKey] };

        const whyObj: any = {
            root_cause: rootCause.type,
            root_cause_function: rootCause.rootFunc,
            call_chain: rootCause.chain
        };

        if (rootCause.type === 'BRANCH_NOT_TAKEN') {
            const firstDeadInChain = rootCause.chain[0] || funcKey;
            const relevantCallSite = callSites.find(site => {
                const fullCaller = site.caller_module + '.' + site.caller;
                return (fullCaller === rootCause.rootFunc || site.caller === rootCause.rootFunc) &&
                    (site.callee === firstDeadInChain ||
                     rootCause.chain.some(chainFunc => site.callee === chainFunc || chainFunc.endsWith('.' + site.callee)));
            });
            if (relevantCallSite?.in_branch) {
                whyObj.branch_type = relevantCallSite.in_branch.type || 'if';
                whyObj.branch_condition = relevantCallSite.in_branch.condition || 'condition was False';
                whyObj.branch_line = relevantCallSite.in_branch.line || 0;
            }
        }

        deadFunctions.push({
            key: funcKey,
            status: 'DEAD',
            module: parts.slice(0, -1).join('.') || '__main__',
            function: parts[parts.length - 1] || funcKey,
            file: regInfo?.file || '-',
            line: regInfo?.line || 0,
            call_count: 0,
            callers: buildCallersArray(funcKey),
            why_not_covered: whyObj
        });

        // Add cached AI explanation if available
        const cache = explorerServer?.getCache();
        if (cache) {
            const cached = cache.getExplanation(funcKey, regInfo?.file || '');
            if (cached) {
                deadFunctions[deadFunctions.length - 1].ai_explanation = {
                    explanation: cached.explanation,
                    why_not_covered: cached.whyNotCovered,
                    model: cached.modelUsed,
                    timestamp: cached.timestamp
                };
            }
        }
    }

    // Alive functions (in registry and called, sorted by call count desc)
    const aliveEntries: [string, { count: number }][] = [];
    for (const [funcKey, stats] of callStats.entries()) {
        if (allDefined.has(funcKey)) {
            aliveEntries.push([funcKey, stats]);
        }
    }
    aliveEntries.sort((a, b) => b[1].count - a[1].count);

    for (const [funcKey, stats] of aliveEntries) {
        const parts = funcKey.split('.');
        const regInfo = functionRegistry.get(funcKey);
        aliveFunctions.push({
            key: funcKey,
            status: 'ALIVE',
            module: parts.slice(0, -1).join('.') || '__main__',
            function: parts[parts.length - 1] || funcKey,
            file: regInfo?.file || '-',
            line: regInfo?.line || 0,
            call_count: stats.count,
            callers: buildCallersArray(funcKey)
        });
    }

    // External functions (called but not in registry)
    for (const [funcKey, stats] of callStats.entries()) {
        if (!allDefined.has(funcKey)) {
            const parts = funcKey.split('.');
            externalFunctions.push({
                key: funcKey,
                status: 'EXTERNAL',
                module: parts.slice(0, -1).join('.') || '__main__',
                function: parts[parts.length - 1] || funcKey,
                file: '-',
                line: 0,
                call_count: stats.count
            });
        }
    }
    externalFunctions.sort((a, b) => b.call_count - a.call_count);

    // Summary stats
    const totalDefined = allDefined.size;
    const deadCount = deadFunctions.length;
    const calledCount = aliveFunctions.length;
    const externalCount = externalFunctions.length;
    const deadPercent = totalDefined > 0 ? Math.round((deadCount / totalDefined) * 1000) / 10 : 0;

    // Module breakdown
    const moduleGroups: Record<string, { total: number; dead: number; alive: number }> = {};
    for (const funcKey of allDefined) {
        const parts = funcKey.split('.');
        const mod = parts.slice(0, -1).join('.') || '__main__';
        if (!moduleGroups[mod]) moduleGroups[mod] = { total: 0, dead: 0, alive: 0 };
        moduleGroups[mod].total++;
        if (coveredKeys.has(funcKey)) {
            moduleGroups[mod].alive++;
        } else {
            moduleGroups[mod].dead++;
        }
    }
    const moduleBreakdown: Record<string, any> = {};
    for (const [mod, counts] of Object.entries(moduleGroups)) {
        moduleBreakdown[mod] = {
            ...counts,
            dead_percent: counts.total > 0 ? Math.round((counts.dead / counts.total) * 1000) / 10 : 0
        };
    }

    const richData = {
        dead_functions: deadFunctions,
        alive_functions: aliveFunctions,
        external_functions: externalFunctions,
        called_functions: [...coveredKeys],
        total_functions: totalDefined,
        total_dead: deadCount,
        total_called: calledCount,
        total_external: externalCount,
        dead_percent: deadPercent,
        module_breakdown: moduleBreakdown
    };

    // Pass to AI provider for RPC handler
    AIExplanationProvider.getInstance().setDeadCodeData(richData);
}

async function connectToSocket(detectedPort?: number): Promise<void> {
    const config = vscode.workspace.getConfiguration('trueflow');
    const host = config.get<string>('socketHost', 'localhost');
    // Use: 1) explicit detectedPort, 2) stored lastServerDetectedPort, 3) config
    const port = detectedPort ?? (lastServerDetectedPort > 0 ? lastServerDetectedPort : config.get<number>('socketPort', 5678));

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

    // Notify both sidebar and trace viewer panel about disconnect
    if (sidebarProvider) {
        sidebarProvider.postMessage({ type: 'socketDisconnected' });
    }
    if (traceViewerPanel) {
        traceViewerPanel.webview.postMessage({ type: 'socketDisconnected' });
    }

    vscode.window.showInformationMessage('Detached from trace server');
}

async function showFilterManagementDialog(): Promise<void> {
    // Show a multi-step quick pick dialog for filter management
    const filterAction = await vscode.window.showQuickPick([
        { label: '$(add) Add Module to Include', description: 'Only trace these modules', value: 'addInclude' },
        { label: '$(dash) Add Module to Exclude', description: 'Never trace these modules', value: 'addExclude' },
        { label: '$(list-flat) Clear Include List', description: 'Remove all include filters', value: 'clearInclude' },
        { label: '$(list-flat) Clear Exclude List', description: 'Remove all exclude filters', value: 'clearExclude' },
        { label: '$(layers) Set Max Depth', description: `Current: ${traceFilter.maxDepth || 'unlimited'}`, value: 'setDepth' },
        { label: '$(info) Show Current Filters', description: 'View all active filters', value: 'show' }
    ], {
        placeHolder: 'Manage Trace Filters (applies to all tabs)'
    });

    if (!filterAction) return;

    switch (filterAction.value) {
        case 'addInclude': {
            const module = await vscode.window.showInputBox({
                prompt: 'Enter module name to include (e.g., myapp, myapp.models)',
                placeHolder: 'module.name'
            });
            if (module) {
                traceFilter.includeModules.push(module);
                vscode.window.showInformationMessage(`Added '${module}' to include list`);
                updateFilterStats();
            }
            break;
        }
        case 'addExclude': {
            const module = await vscode.window.showInputBox({
                prompt: 'Enter module name to exclude (e.g., logging, asyncio)',
                placeHolder: 'module.name'
            });
            if (module) {
                traceFilter.excludeModules.push(module);
                vscode.window.showInformationMessage(`Added '${module}' to exclude list`);
                updateFilterStats();
            }
            break;
        }
        case 'clearInclude':
            traceFilter.includeModules = [];
            vscode.window.showInformationMessage('Cleared include list - now tracing all modules');
            updateFilterStats();
            break;
        case 'clearExclude':
            traceFilter.excludeModules = [];
            vscode.window.showInformationMessage('Cleared exclude list - now tracing all modules');
            updateFilterStats();
            break;
        case 'setDepth': {
            const depthStr = await vscode.window.showInputBox({
                prompt: 'Enter maximum call depth (0 = unlimited)',
                value: String(traceFilter.maxDepth),
                validateInput: (v) => isNaN(parseInt(v)) ? 'Must be a number' : null
            });
            if (depthStr !== undefined) {
                traceFilter.maxDepth = parseInt(depthStr);
                vscode.window.showInformationMessage(`Set max depth to ${traceFilter.maxDepth || 'unlimited'}`);
                updateFilterStats();
            }
            break;
        }
        case 'show': {
            const message = [
                `Include modules: ${traceFilter.includeModules.length > 0 ? traceFilter.includeModules.join(', ') : '(all)'}`,
                `Exclude modules: ${traceFilter.excludeModules.join(', ') || '(none)'}`,
                `Max depth: ${traceFilter.maxDepth || 'unlimited'}`
            ].join('\n');
            vscode.window.showInformationMessage(message, { modal: true });
            break;
        }
    }
}

function updateFilterStats(): void {
    const stats = getFilterStats();
    // Update sidebar
    sidebarProvider?.postMessage({ type: 'updateFilters', stats });
    // Update trace viewer if open
    traceViewerPanel?.webview.postMessage({ type: 'updateFilters', stats });
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

        // Version-aware deployment: track extension version and restart hub if changed
        const versionFile = path.join(destPath, '.extension_version');
        const pkgPath = path.join(extensionPath, 'package.json');
        let currentVersion = 'unknown';
        try {
            if (fs.existsSync(pkgPath)) {
                currentVersion = JSON.parse(fs.readFileSync(pkgPath, 'utf-8')).version || 'unknown';
            }
        } catch (_) { /* ignore */ }

        let versionChanged = true;
        if (fs.existsSync(versionFile)) {
            const deployedVersion = fs.readFileSync(versionFile, 'utf-8').trim();
            versionChanged = deployedVersion !== currentVersion;
        }
        fs.writeFileSync(versionFile, currentVersion);

        if (versionChanged) {
            console.log(`[TrueFlow] Extension version changed to ${currentVersion}, restarting hub...`);
            try {
                await HubClient.getInstance().restartHub();
            } catch (e) {
                console.warn('[TrueFlow] Hub restart after version change failed:', e);
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

async function openExplorerInExternalBrowser(context: vscode.ExtensionContext, data: any): Promise<void> {
    try {
        // Read the interactive_flow_explorer.html template
        const htmlPath = path.join(context.extensionPath, 'resources', 'interactive_viz', 'interactive_flow_explorer.html');
        let htmlContent: string;

        if (fs.existsSync(htmlPath)) {
            htmlContent = fs.readFileSync(htmlPath, 'utf8');
        } else {
            // Fallback: generate standalone HTML with embedded data
            htmlContent = generateStandaloneExplorerHtml(data);
        }

        // Inject data into the HTML
        const dataScript = `<script>window.TRUEFLOW_DATA = ${JSON.stringify(data)};</script>`;
        htmlContent = htmlContent.replace('</head>', `${dataScript}</head>`);

        // Add auto-load script
        const autoLoadScript = `<script>
            document.addEventListener('DOMContentLoaded', function() {
                if (window.TRUEFLOW_DATA && typeof loadVisualizationData === 'function') {
                    setTimeout(function() { loadVisualizationData(window.TRUEFLOW_DATA); }, 500);
                }
            });
        </script>`;
        htmlContent = htmlContent.replace('</body>', `${autoLoadScript}</body>`);

        // Write to temp file and open in browser
        const tempDir = path.join(context.extensionPath, '.temp');
        if (!fs.existsSync(tempDir)) {
            fs.mkdirSync(tempDir, { recursive: true });
        }

        const tempFile = path.join(tempDir, 'interactive_explorer_' + Date.now() + '.html');
        fs.writeFileSync(tempFile, htmlContent);

        // Open in default browser
        vscode.env.openExternal(vscode.Uri.file(tempFile));
        vscode.window.showInformationMessage('Interactive Flow Explorer opened in browser!');

    } catch (error) {
        vscode.window.showErrorMessage('Failed to open explorer in browser: ' + (error as Error).message);
    }
}

/**
 * Toggle the live server for real-time browser viewing.
 */
function toggleExplorerLiveServer(
    context: vscode.ExtensionContext,
    data: any,
    panel: vscode.WebviewPanel | undefined
): void {
    if (explorerServer?.isRunning()) {
        // Stop the server
        explorerServer.stop();
        explorerServer = undefined;

        // Update button in webview
        panel?.webview.postMessage({
            type: 'liveServerStatus',
            isRunning: false,
            url: null
        });

        vscode.window.showInformationMessage('TrueFlow live server stopped');
    } else {
        // Start the server
        const resourcesPath = path.join(context.extensionPath, 'resources');

        explorerServer = new InteractiveExplorerServer(
            8765,
            resourcesPath,
            (url) => {
                // Server started - update button and open browser
                panel?.webview.postMessage({
                    type: 'liveServerStatus',
                    isRunning: true,
                    url: url
                });

                // Open browser
                vscode.env.openExternal(vscode.Uri.parse(url));
                vscode.window.showInformationMessage(`TrueFlow live server running at ${url}`);
            },
            () => {
                // Server stopped
                panel?.webview.postMessage({
                    type: 'liveServerStatus',
                    isRunning: false,
                    url: null
                });
            },
            (error) => {
                // Error
                vscode.window.showErrorMessage(`Failed to start live server: ${error.message}`);
                panel?.webview.postMessage({
                    type: 'liveServerStatus',
                    isRunning: false,
                    url: null
                });
            }
        );

        // Initialize explanation cache
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (workspaceFolder) {
            const cacheDir = path.join(workspaceFolder.uri.fsPath, '.trueflow');
            explorerServer.initCache(cacheDir);
        }

        explorerServer.start();

        // Push initial data
        if (data) {
            explorerServer.pushTraceData(data);
        }
    }
}

/**
 * Push current trace data to the live server (if running).
 */
function pushToLiveServer(data: any): void {
    if (explorerServer?.isRunning()) {
        explorerServer.pushTraceData(data);
    }
}

function generateStandaloneExplorerHtml(data: any): string {
    // Generate a standalone HTML with Three.js for the 3D explorer
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow Interactive Flow Explorer</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: system-ui, sans-serif; background: #0a0a1a; color: #e0e0e0; overflow: hidden; }
        #container { width: 100vw; height: 100vh; }
        #info { position: absolute; top: 10px; left: 10px; background: rgba(26,26,46,0.9); padding: 15px; border-radius: 8px; }
        h1 { color: #7dd3fc; font-size: 18px; margin-bottom: 10px; }
        .stat { display: inline-block; margin-right: 20px; }
        .stat-value { font-size: 24px; font-weight: bold; color: #4ade80; }
        .stat-label { font-size: 11px; color: #888; }
        .legend { margin-top: 15px; display: flex; gap: 15px; font-size: 11px; }
        .legend span { display: flex; align-items: center; gap: 5px; }
        .legend-dot { width: 12px; height: 12px; border-radius: 2px; }
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="info">
        <h1>TrueFlow Interactive Flow Explorer</h1>
        <div>
            <span class="stat"><span class="stat-value" id="total-count">${Object.keys(data.functions || {}).length}</span><span class="stat-label"> Functions</span></span>
            <span class="stat"><span class="stat-value" style="color: #4ade80;" id="covered-count">${(data.covered_functions || []).length}</span><span class="stat-label"> Covered</span></span>
            <span class="stat"><span class="stat-value" style="color: #ef4444;" id="dead-count">${(data.dead_functions || []).length}</span><span class="stat-label"> Dead</span></span>
        </div>
        <div class="legend">
            <span><span class="legend-dot" style="background: #4ade80;"></span>Executed</span>
            <span><span class="legend-dot" style="background: #ef4444;"></span>Orphaned</span>
            <span><span class="legend-dot" style="background: #a78bfa;"></span>Dead Branch</span>
        </div>
    </div>
    <script>
        const data = ${JSON.stringify(data)};
        console.log('TrueFlow Explorer Data:', data);
        // Three.js visualization would be initialized here
        // For now, show data summary
    </script>
</body>
</html>`;
}

function showTraceViewer(context: vscode.ExtensionContext, initialTab?: string): void {
    const needsTabSelection = traceViewerPanel && initialTab;

    if (traceViewerPanel) {
        traceViewerPanel.reveal();
        // If panel already exists and a tab was specified, select it
        if (initialTab) {
            traceViewerPanel.webview.postMessage({ type: 'selectTab', tab: initialTab });
        }
        return;
    }

    // Open in existing editor group if available, otherwise use active column
    // ViewColumn.Two opens in second group if it exists, otherwise creates it beside
    // Check if there are visible editors to determine if we should use existing group
    const visibleEditors = vscode.window.visibleTextEditors;
    let viewColumn: vscode.ViewColumn;

    if (visibleEditors.length > 1) {
        // Multiple editor groups exist - use the second one (or the one not currently active)
        const activeColumn = vscode.window.activeTextEditor?.viewColumn || vscode.ViewColumn.One;
        viewColumn = activeColumn === vscode.ViewColumn.One ? vscode.ViewColumn.Two : vscode.ViewColumn.One;
    } else if (visibleEditors.length === 1) {
        // Single editor - open beside it
        viewColumn = vscode.ViewColumn.Beside;
    } else {
        // No editors open - use active/first column
        viewColumn = vscode.ViewColumn.Active;
    }

    traceViewerPanel = vscode.window.createWebviewPanel(
        'trueflowTraceViewer',
        'TrueFlow Trace Viewer',
        { viewColumn, preserveFocus: false },
        {
            enableScripts: true,
            retainContextWhenHidden: true
        }
    );

    traceViewerPanel.webview.html = getTraceViewerHtml(initialTab);

    // Handle messages from webview
    traceViewerPanel.webview.onDidReceiveMessage(async message => {
        switch (message.type) {
            case 'connect':
                await connectToSocket();
                break;
            case 'manageFilters':
                await showFilterManagementDialog();
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
            case 'openExplorerInBrowser':
            case 'exportSnapshot':
                // Open interactive flow explorer in external browser (static snapshot)
                openExplorerInExternalBrowser(context, message.data);
                break;
            case 'toggleLiveServer':
                // Toggle the live server for real-time browser viewing
                toggleExplorerLiveServer(context, message.data, traceViewerPanel);
                break;
            case 'getExplorerHtml':
                // Load the Three.js interactive flow explorer HTML for iframe embedding
                try {
                    const htmlPath = path.join(context.extensionPath, 'resources', 'interactive_viz', 'interactive_flow_explorer.html');
                    if (fs.existsSync(htmlPath)) {
                        const htmlContent = fs.readFileSync(htmlPath, 'utf8');
                        traceViewerPanel?.webview.postMessage({
                            type: 'explorerHtml',
                            html: htmlContent
                        });
                    } else {
                        console.error('[TrueFlow] Explorer HTML not found at:', htmlPath);
                    }
                } catch (error) {
                    console.error('[TrueFlow] Failed to load explorer HTML:', error);
                }
                break;
            case 'exposeMCPTool': {
                // Right-click "Expose as MCP Tool" from Dead Code tab
                const toolData = message.data;
                try {
                    const http = await import('http');
                    const postBody = JSON.stringify(toolData);
                    const req = http.request({
                        hostname: '127.0.0.1',
                        port: 5681,
                        path: '/expose_tool',
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Content-Length': Buffer.byteLength(postBody)
                        },
                        timeout: 10000
                    }, (res) => {
                        let body = '';
                        res.on('data', (chunk: Buffer) => { body += chunk.toString(); });
                        res.on('end', () => {
                            try {
                                const result = JSON.parse(body);
                                if (result.error) {
                                    vscode.window.showErrorMessage('MCP Tool Generation Failed: ' + result.error);
                                } else {
                                    const config = JSON.stringify({
                                        [result.tool_name]: { command: 'python', args: [result.server_path] }
                                    }, null, 2);
                                    vscode.window.showInformationMessage(
                                        'MCP Tool Created: ' + result.tool_name,
                                        'Copy Config'
                                    ).then(action => {
                                        if (action === 'Copy Config') {
                                            vscode.env.clipboard.writeText(config);
                                        }
                                    });
                                }
                            } catch (parseErr) {
                                vscode.window.showErrorMessage('MCP Tool: Invalid response from Hub');
                            }
                        });
                    });
                    req.on('error', (err: Error) => {
                        vscode.window.showErrorMessage('MCP Tool: Hub not reachable at :5681. Start TrueFlow Hub first.');
                    });
                    req.write(postBody);
                    req.end();
                } catch (err) {
                    vscode.window.showErrorMessage('MCP Tool: Failed to connect to Hub');
                }
                break;
            }
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

/**
 * Editor context menu: "Expose as MCP Tool"
 * Finds the enclosing Python function at the cursor and sends it to the Hub.
 */
async function exposeEditorFunctionAsMCPTool(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== 'python') {
        vscode.window.showWarningMessage('Place cursor inside a Python function to expose as MCP tool.');
        return;
    }

    const doc = editor.document;
    const cursorLine = editor.selection.active.line;

    // Search upward for enclosing def/async def
    const defPattern = /^\s*(async\s+)?def\s+(\w+)\s*\(/;
    let funcName: string | null = null;
    let funcLine = 0;
    let funcIndent = 0;

    for (let line = cursorLine; line >= 0; line--) {
        const text = doc.lineAt(line).text;
        const match = defPattern.exec(text);
        if (match) {
            funcName = match[2];
            funcLine = line + 1; // 1-based
            funcIndent = text.length - text.trimStart().length;
            break;
        }
    }

    if (!funcName) {
        vscode.window.showWarningMessage('No Python function found at cursor position.');
        return;
    }

    // Check for enclosing class (less indentation above the def)
    const classPattern = /^\s*class\s+(\w+)/;
    let className: string | null = null;
    if (funcIndent > 0) {
        for (let line = funcLine - 2; line >= 0; line--) {
            const text = doc.lineAt(line).text;
            const lineIndent = text.length - text.trimStart().length;
            if (lineIndent < funcIndent) {
                const classMatch = classPattern.exec(text);
                if (classMatch) {
                    className = classMatch[1];
                }
                break;
            }
        }
    }

    const qualifiedFunc = className ? `${className}.${funcName}` : funcName;

    // Derive module name from file path
    const filePath = doc.uri.fsPath;
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    let moduleName = filePath;
    if (workspaceRoot && filePath.startsWith(workspaceRoot)) {
        moduleName = filePath.substring(workspaceRoot.length);
    }
    moduleName = moduleName
        .replace(/\\/g, '/')
        .replace(/^\//, '')
        .replace(/\.py$/, '')
        .replace(/\/__init__$/, '')
        .replace(/\//g, '.');

    // POST to Hub
    const http = await import('http');
    const postBody = JSON.stringify({
        function_name: qualifiedFunc,
        module: moduleName,
        file: filePath,
        line: funcLine
    });

    const req = http.request({
        hostname: '127.0.0.1',
        port: 5681,
        path: '/expose_tool',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postBody)
        },
        timeout: 10000
    }, (res) => {
        let body = '';
        res.on('data', (chunk: Buffer) => { body += chunk.toString(); });
        res.on('end', () => {
            try {
                const result = JSON.parse(body);
                if (result.error) {
                    vscode.window.showErrorMessage('MCP Tool Generation Failed: ' + result.error);
                } else {
                    const config = JSON.stringify({
                        [result.tool_name]: { command: 'python', args: [result.server_path] }
                    }, null, 2);
                    vscode.window.showInformationMessage(
                        `MCP Tool Created: ${result.tool_name}`,
                        'Copy Config'
                    ).then(action => {
                        if (action === 'Copy Config') {
                            vscode.env.clipboard.writeText(config);
                        }
                    });
                }
            } catch {
                vscode.window.showErrorMessage('MCP Tool: Invalid response from Hub');
            }
        });
    });
    req.on('error', () => {
        vscode.window.showErrorMessage('MCP Tool: Hub not reachable at :5681. Start TrueFlow Hub first.');
    });
    req.write(postBody);
    req.end();
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
 * Check if the workspace already has TrueFlow integration.
 * Returns true if .trueflow/runtime_injector or .pycharm_plugin/runtime_injector exists.
 */
function isProjectAlreadyIntegrated(): boolean {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        return false;
    }

    const workspaceRoot = workspaceFolders[0].uri.fsPath;

    // Check for VS Code integration (.trueflow)
    const trueflowInjector = path.join(workspaceRoot, '.trueflow', 'runtime_injector', 'sitecustomize.py');
    if (fs.existsSync(trueflowInjector)) {
        return true;
    }

    // Check for PyCharm integration (.pycharm_plugin)
    const pycharmInjector = path.join(workspaceRoot, '.pycharm_plugin', 'runtime_injector', 'sitecustomize.py');
    if (fs.existsSync(pycharmInjector)) {
        return true;
    }

    return false;
}

/**
 * Get HTML for the sidebar view - a compact dashboard with quick actions
 */
function getSidebarHtml(isConnected: boolean): string {
    const isIntegrated = isProjectAlreadyIntegrated();
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
        .context-selector {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 10px;
            background: var(--vscode-sideBarSectionHeader-background);
            border-radius: 4px;
            margin-bottom: 12px;
        }
        .context-selector label {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            white-space: nowrap;
        }
        .context-selector select {
            flex: 1;
            padding: 4px 6px;
            font-size: 11px;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 3px;
            cursor: pointer;
        }
        .context-badge {
            font-size: 9px;
            padding: 2px 5px;
            background: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            border-radius: 8px;
            display: none;
        }
        .context-badge.active { display: inline-block; }
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
                ${isConnected ? 'Attached' : 'Detached'}
            </span>
        </div>
        <div class="status-row">
            <span class="status-label">Events</span>
            <span id="event-count" class="metric-value">0</span>
        </div>
        <div class="status-row">
            <span class="status-label">Filters</span>
            <span id="filter-stats" class="metric-value" style="font-size: 11px; color: var(--vscode-charts-green);">None</span>
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

    <div class="section-title">AI Context</div>
    <div class="context-selector">
        <label>📊</label>
        <select id="contextSelect" onchange="onContextChange()">
            <option value="0">No context</option>
            <option value="1">Dead Code</option>
            <option value="2">Performance</option>
            <option value="3">Call Trace</option>
            <option value="4">Diagram</option>
            <option value="5">All Data</option>
        </select>
        <span class="context-badge" id="contextBadge">+</span>
    </div>

    <div class="section-title">Session Actions</div>
    <div class="action-buttons">
        ${!isIntegrated ? `<button class="action-btn primary" onclick="action('autoIntegrate')">
            <span class="icon">⚡</span>
            <span>Auto-Integrate Project</span>
        </button>` : ''}
        <button id="attach-btn" class="action-btn" onclick="action('${isConnected ? 'disconnect' : 'connect'}')">
            <span class="icon">${isConnected ? '🔴' : '🟢'}</span>
            <span>${isConnected ? 'Detach from Server' : 'Attach to Server'}</span>
        </button>
        <button class="action-btn" onclick="action('manageFilters')">
            <span class="icon">🔧</span>
            <span>Manage Filters</span>
        </button>
        <button class="action-btn" onclick="action('generateVideo')">
            <span class="icon">🎬</span>
            <span>Generate Architecture Video</span>
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

        function onContextChange() {
            const select = document.getElementById('contextSelect');
            const badge = document.getElementById('contextBadge');
            const value = select.value;

            // Show badge when context is selected
            badge.classList.toggle('active', value !== '0');

            // Notify VS Code extension
            vscode.postMessage({ type: 'contextChanged', value: parseInt(value) });
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
                    document.getElementById('connection-status').textContent = 'Attached';
                    document.getElementById('connection-status').className = 'status-badge status-connected';
                    document.getElementById('attach-btn').innerHTML = '<span class="icon">🔴</span><span>Detach from Server</span>';
                    document.getElementById('attach-btn').onclick = function() { action('disconnect'); };
                    break;
                case 'socketDisconnected':
                    document.getElementById('connection-status').textContent = 'Detached';
                    document.getElementById('connection-status').className = 'status-badge status-disconnected';
                    document.getElementById('attach-btn').innerHTML = '<span class="icon">🟢</span><span>Attach to Server</span>';
                    document.getElementById('attach-btn').onclick = function() { action('connect'); };
                    break;
                case 'updateFilters':
                    document.getElementById('filter-stats').textContent = message.stats || 'None';
                    break;
            }
        });
    </script>
</body>
</html>`;
}

function getTraceViewerHtml(initialTab?: string): string {
    const isConnected = traceSocketClient?.isConnected() || false;
    // Map tab names to their data-tab values
    const tabMap: {[key: string]: string} = {
        'diagram': 'diagram',
        'performance': 'performance',
        'perf': 'performance',
        'deadcode': 'deadcode',
        'dead': 'deadcode',
        'trace': 'trace',
        'flamegraph': 'flamegraph',
        'flame': 'flamegraph',
        'sql': 'sql',
        'metrics': 'metrics',
        'distributed': 'distributed',
        'manim': 'manim',
        'video': 'manim'
    };
    const activeTab = initialTab ? (tabMap[initialTab.toLowerCase()] || 'diagram') : 'diagram';

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

        /* Sub-tabs for nested navigation (e.g., Manim tab) */
        .sub-tab-container {
            display: flex;
            border-bottom: 1px solid var(--vscode-panel-border);
            margin-bottom: 10px;
            gap: 2px;
        }
        .sub-tab {
            padding: 6px 12px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
        }
        .sub-tab:hover {
            background-color: var(--vscode-list-hoverBackground);
            color: var(--vscode-editor-foreground);
        }
        .sub-tab.active {
            border-bottom-color: var(--vscode-focusBorder);
            color: var(--vscode-editor-foreground);
        }
        .sub-content {
            display: none;
        }
        .sub-content.active {
            display: block;
        }

        /* Interactive Explorer styles */
        .explorer-toolbar {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 10px;
            padding: 8px;
            background: var(--vscode-editor-lineHighlightBackground);
            border-radius: 4px;
        }
        .explorer-toolbar button {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 4px 12px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 11px;
        }
        .explorer-toolbar button:hover {
            background: var(--vscode-button-hoverBackground);
        }
        .explorer-stats {
            font-size: 12px;
            color: var(--vscode-descriptionForeground);
        }
        #explorer-canvas {
            position: relative;
        }
        .explorer-node {
            position: absolute;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            white-space: nowrap;
            max-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .explorer-node:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10;
        }
        .explorer-node.alive {
            background: #166534;
            border: 1px solid #4ade80;
            color: #fff;
        }
        .explorer-node.dead {
            background: #7f1d1d;
            border: 1px solid #f87171;
            color: #fca5a5;
        }
        .explorer-node.dead-orphan {
            background: #7f1d1d;
            border: 1px solid #ef4444;
            color: #fca5a5;
        }
        .explorer-node.dead-branch {
            background: #4c1d95;
            border: 1px solid #a78bfa;
            color: #ddd6fe;
        }
        .explorer-node.selected {
            box-shadow: 0 0 0 2px #7dd3fc;
        }
        .explorer-branch-marker {
            position: absolute;
            width: 12px;
            height: 12px;
            background: #fbbf24;
            transform: rotate(45deg);
            z-index: 5;
            cursor: pointer;
        }
        .explorer-branch-marker:hover {
            background: #fcd34d;
            box-shadow: 0 0 8px rgba(251, 191, 36, 0.6);
        }
        .explorer-edge {
            position: absolute;
            pointer-events: none;
        }
        .why-not-covered {
            margin-top: 12px;
            padding: 10px;
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.4);
            border-radius: 6px;
        }
        .why-not-covered h5 {
            color: #f87171;
            font-size: 12px;
            margin-bottom: 6px;
        }
        .why-not-covered .reason {
            font-size: 11px;
            color: #fca5a5;
            margin-bottom: 4px;
            padding-left: 8px;
            border-left: 2px solid #f87171;
        }
        .why-not-covered .condition {
            font-family: monospace;
            background: rgba(0,0,0,0.3);
            padding: 3px 6px;
            border-radius: 3px;
            margin-top: 4px;
            font-size: 10px;
            color: #fde68a;
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
                ${isConnected ? 'Attached' : 'Detached'}
            </span>
            <span id="event-counter" class="event-counter"></span>
            <span id="filter-stats" style="font-size: 11px; color: var(--vscode-charts-green); margin-left: 10px;">Filters: ${getFilterStats()}</span>
        </div>
        <div class="header-actions">
            <button onclick="connectSocket()">${isConnected ? 'Detach' : 'Attach'}</button>
            <button onclick="manageFilters()">Manage Filters</button>
            <button onclick="refreshData()">Refresh</button>
        </div>
    </div>

    <div class="tab-container">
        <div class="tab${activeTab === 'diagram' ? ' active' : ''}" data-tab="diagram">Diagram</div>
        <div class="tab${activeTab === 'performance' ? ' active' : ''}" data-tab="performance">Performance</div>
        <div class="tab${activeTab === 'deadcode' ? ' active' : ''}" data-tab="deadcode">Dead Code</div>
        <div class="tab${activeTab === 'trace' ? ' active' : ''}" data-tab="trace">Call Trace</div>
        <div class="tab${activeTab === 'flamegraph' ? ' active' : ''}" data-tab="flamegraph">Flamegraph</div>
        <div class="tab${activeTab === 'sql' ? ' active' : ''}" data-tab="sql">SQL Analyzer</div>
        <div class="tab${activeTab === 'metrics' ? ' active' : ''}" data-tab="metrics">Live Metrics</div>
        <div class="tab${activeTab === 'distributed' ? ' active' : ''}" data-tab="distributed">Distributed</div>
        <div class="tab${activeTab === 'manim' ? ' active' : ''}" data-tab="manim">Architecture Video</div>
    </div>

    <!-- Diagram Tab -->
    <div class="content${activeTab === 'diagram' ? ' active' : ''}" id="diagram-content">
        <div class="diagram-toolbar">
            <select id="diagram-type" onchange="updateDiagramType()">
                <option value="mermaid" selected>Mermaid</option>
                <option value="plantuml">PlantUML</option>
            </select>
            <label style="display: flex; align-items: center; gap: 4px; margin-left: 10px;">
                <input type="checkbox" id="show-dead-call-trees" onchange="toggleDeadCallTrees()">
                <span style="font-size: 11px;">Show Dead Call Trees</span>
            </label>
            <button onclick="renderDiagram()">Render</button>
            <button onclick="copyDiagram()">Copy</button>
            <button onclick="openDiagramInBrowser()" title="Open fullscreen in browser">View Fullscreen</button>
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
    <div class="content${activeTab === 'performance' ? ' active' : ''}" id="performance-content">
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
    <div class="content${activeTab === 'deadcode' ? ' active' : ''}" id="deadcode-content">
        <div id="deadcode-list">
            <div class="placeholder">
                <p>Run your application with TrueFlow to detect uncovered functions.</p>
            </div>
        </div>
    </div>

    <!-- Call Trace Tab -->
    <div class="content${activeTab === 'trace' ? ' active' : ''}" id="trace-content">
        <div id="call-tree" class="call-tree">
            <div class="placeholder">
                <p>Connect to trace server to see live call traces.</p>
            </div>
        </div>
    </div>

    <!-- Flamegraph Tab -->
    <div class="content${activeTab === 'flamegraph' ? ' active' : ''}" id="flamegraph-content">
        <div class="flamegraph-container">
            <div class="flamegraph-canvas" id="flamegraph">
                <div class="placeholder">
                    <p>Performance flamegraph will be rendered here from trace data.</p>
                </div>
            </div>
        </div>
    </div>

    <!-- SQL Analyzer Tab -->
    <div class="content${activeTab === 'sql' ? ' active' : ''}" id="sql-content">
        <h3>SQL Query Analyzer</h3>
        <p>SQL queries and potential N+1 problems will appear here.</p>
        <div id="sql-queries">
            <div class="placeholder">
                <p>No SQL queries detected yet. Run your application with TrueFlow.</p>
            </div>
        </div>
    </div>

    <!-- Live Metrics Tab -->
    <div class="content${activeTab === 'metrics' ? ' active' : ''}" id="metrics-content">
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
    <div class="content${activeTab === 'distributed' ? ' active' : ''}" id="distributed-content">
        <h3>Distributed Architecture</h3>
        <p>WebSocket, gRPC, Kafka, and other distributed calls will appear here.</p>
        <div id="distributed-calls">
            <div class="placeholder">
                <p>No distributed calls detected yet.</p>
            </div>
        </div>
    </div>

    <!-- Architecture Video Tab with Sub-tabs -->
    <div class="content${activeTab === 'manim' ? ' active' : ''}" id="manim-content">
        <div class="sub-tab-container">
            <div class="sub-tab active" data-subtab="interactive-explorer">Interactive Explorer</div>
            <div class="sub-tab" data-subtab="video-list">Video List</div>
            <div class="sub-tab" data-subtab="watch-architecture">📹 Watch Architecture</div>
        </div>

        <!-- Interactive Explorer Sub-tab (default) -->
        <div class="sub-content active" id="interactive-explorer-subcontent">
            <div class="explorer-toolbar" style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px; background: var(--vscode-editor-lineHighlightBackground); border-radius: 4px; margin-bottom: 8px;">
                <button onclick="refreshInteractiveExplorer()" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px;">Refresh</button>
                <button id="live-server-btn" onclick="toggleLiveServer()" title="Open visualization in browser with real-time updates" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px;">🌐 Open in Browser</button>
                <button onclick="exportSnapshot()" title="Export current visualization as static HTML file" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px;">📸 Export Snapshot</button>
                <select id="explorer-filter-coverage" onchange="applyExplorerFilters()" style="background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 5px 8px; border-radius: 4px; font-size: 11px;">
                    <option value="all">All Functions</option>
                    <option value="covered">Covered Only</option>
                    <option value="dead">Dead Only</option>
                    <option value="orphan">Orphaned Only</option>
                    <option value="branch">Dead Branch Only</option>
                </select>
                <input type="text" id="explorer-filter-module" placeholder="Filter by module..." oninput="applyExplorerFilters()" style="background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 5px 8px; border-radius: 4px; font-size: 11px; width: 150px;" />
                <span class="explorer-stats" style="margin-left: auto; font-size: 11px;">
                    Functions: <span id="explorer-total">0</span> |
                    Covered: <span id="explorer-covered" style="color: #4ade80;">0</span> |
                    Dead: <span id="explorer-dead" style="color: #f87171;">0</span>
                </span>
            </div>
            <div id="interactive-explorer-container" style="width: 100%; height: calc(100vh - 250px); position: relative;">
                <div id="explorer-loading" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #888; z-index: 10; pointer-events: none;">
                    Run your code to generate visualization data
                </div>
                <iframe id="explorer-3d-iframe" style="width: 100%; height: 100%; border: none; border-radius: 8px; background: #1a1a2e;"></iframe>
            </div>
            <div class="explorer-legend" style="margin-top: 10px; display: flex; gap: 15px; font-size: 11px; color: #888; flex-wrap: wrap;">
                <span><span style="display: inline-block; width: 12px; height: 12px; background: #4ade80; border-radius: 2px; margin-right: 5px;"></span>Executed</span>
                <span><span style="display: inline-block; width: 12px; height: 12px; background: #ef4444; border-radius: 2px; margin-right: 5px;"></span>Orphaned (No Callers)</span>
                <span><span style="display: inline-block; width: 12px; height: 12px; background: #a78bfa; border-radius: 2px; margin-right: 5px;"></span>Dead Branch</span>
                <span><span style="display: inline-block; width: 12px; height: 12px; background: #fbbf24; transform: rotate(45deg); margin-right: 5px;"></span>Branch Divergence</span>
            </div>
        </div>

        <!-- Video List Sub-tab -->
        <div class="sub-content" id="video-list-subcontent">
            <p style="margin-bottom: 10px;">Use "TrueFlow: Generate Architecture Video" command to create visualizations.</p>
            <div id="video-container">
                <div class="placeholder">
                    <p>Generated execution flow videos will appear here.</p>
                </div>
            </div>
        </div>

        <!-- Watch Architecture Sub-tab - Football-style data flow visualization -->
        <div class="sub-content" id="watch-architecture-subcontent">
            <!-- Controls Bar -->
            <div class="watch-controls" style="display: flex; align-items: center; gap: 10px; padding: 10px; background: var(--vscode-editor-lineHighlightBackground); border-radius: 4px; margin-bottom: 10px; flex-wrap: wrap;">
                <button id="watch-record-btn" onclick="toggleWatchRecording()" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px;">
                    ⏺ Record
                </button>
                <button onclick="toggleWatchPlayback()" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px;">
                    ▶ Play
                </button>
                <input type="range" id="watch-timeline" min="0" max="100" value="0" style="width: 150px;">
                <span id="watch-time-display" style="font-size: 11px; font-family: monospace; color: var(--vscode-descriptionForeground);">00:00.000</span>

                <!-- Camera Controls -->
                <div style="display: flex; gap: 4px; margin-left: 15px; border-left: 1px solid var(--vscode-panel-border); padding-left: 15px;">
                    <span style="font-size: 10px; color: var(--vscode-descriptionForeground); margin-right: 5px;">Camera:</span>
                    <button class="camera-btn active" data-camera="overview" onclick="setWatchCamera('overview')" title="Overview">🎥</button>
                    <button class="camera-btn" data-camera="flyby" onclick="setWatchCamera('flyby')" title="Fly-by">✈️</button>
                    <button class="camera-btn" data-camera="tele" onclick="setWatchCamera('tele')" title="Telephoto">🔭</button>
                    <button class="camera-btn" data-camera="follow" onclick="setWatchCamera('follow')" title="Follow Data">⚽</button>
                </div>

                <!-- Recording Duration -->
                <div id="watch-recording-duration" style="display: none; margin-left: auto; background: rgba(239, 68, 68, 0.2); padding: 4px 10px; border-radius: 4px;">
                    <span style="color: #ef4444; font-size: 11px;">⏱️ <span id="watch-duration">00:00:00</span></span>
                </div>

                <!-- Export/Open Buttons -->
                <button onclick="showWatchExportModal()" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 10px;">
                    📤 Export
                </button>
                <button onclick="openWatchInBrowser()" title="Open in external browser" style="background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 11px;">
                    🌐 Open in Browser
                </button>
            </div>

            <!-- Main Visualization Container -->
            <div style="display: flex; gap: 10px; height: calc(100vh - 280px);">
                <!-- Left Panel - Data Sources -->
                <div id="watch-sources-panel" style="width: 180px; background: var(--vscode-editor-lineHighlightBackground); border-radius: 8px; padding: 10px; overflow-y: auto;">
                    <h4 style="font-size: 11px; color: var(--vscode-descriptionForeground); margin-bottom: 10px; text-transform: uppercase;">Data Sources</h4>
                    <div class="watch-source-item video" onclick="filterWatchBySource('video')" style="padding: 8px; margin-bottom: 6px; background: var(--vscode-input-background); border-radius: 4px; border-left: 3px solid #f472b6; cursor: pointer;">
                        <span>📹 Video Frame</span>
                        <div style="font-size: 9px; color: var(--vscode-descriptionForeground);">Camera Feed</div>
                    </div>
                    <div class="watch-source-item api" onclick="filterWatchBySource('api')" style="padding: 8px; margin-bottom: 6px; background: var(--vscode-input-background); border-radius: 4px; border-left: 3px solid #60a5fa; cursor: pointer;">
                        <span>🌐 API Request</span>
                        <div style="font-size: 9px; color: var(--vscode-descriptionForeground);">REST/WebSocket</div>
                    </div>
                    <div class="watch-source-item screen" onclick="filterWatchBySource('screen')" style="padding: 8px; margin-bottom: 6px; background: var(--vscode-input-background); border-radius: 4px; border-left: 3px solid #a78bfa; cursor: pointer;">
                        <span>🖥️ Screen Data</span>
                        <div style="font-size: 9px; color: var(--vscode-descriptionForeground);">Display Capture</div>
                    </div>
                    <div class="watch-source-item audio" onclick="filterWatchBySource('audio')" style="padding: 8px; margin-bottom: 6px; background: var(--vscode-input-background); border-radius: 4px; border-left: 3px solid #fbbf24; cursor: pointer;">
                        <span>🎤 Audio Input</span>
                        <div style="font-size: 9px; color: var(--vscode-descriptionForeground);">Microphone</div>
                    </div>

                    <h4 style="font-size: 11px; color: var(--vscode-descriptionForeground); margin-top: 20px; margin-bottom: 10px; text-transform: uppercase; border-top: 1px solid var(--vscode-panel-border); padding-top: 10px;">Importance</h4>
                    <div id="watch-importance-list" style="font-size: 10px; color: var(--vscode-descriptionForeground);">
                        <!-- Populated dynamically with importance scores -->
                    </div>

                    <div style="margin-top: 15px; padding-top: 10px; border-top: 1px solid var(--vscode-panel-border);">
                        <div style="font-size: 9px; color: var(--vscode-descriptionForeground); margin-bottom: 5px;">LLM Status:</div>
                        <div id="watch-llm-status" style="font-size: 10px; color: #888;">Checking...</div>
                    </div>
                </div>

                <!-- Center - Main Visualization SVG -->
                <div id="watch-viz-container" style="flex: 1; background: #0d0d20; border-radius: 8px; position: relative; overflow: hidden;">
                    <svg id="watch-flow-svg" viewBox="0 0 800 500" style="width: 100%; height: 100%;">
                        <defs>
                            <marker id="watch-arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                                <polygon points="0 0, 10 3.5, 0 7" fill="#4a4a6a" />
                            </marker>
                            <filter id="watch-glow">
                                <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                                <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
                            </filter>
                        </defs>
                        <g id="watch-grid"></g>
                        <g id="watch-edges"></g>
                        <g id="watch-nodes"></g>
                        <g id="watch-particles"></g>
                    </svg>
                    <div id="watch-loading" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: #888;">
                        <div style="font-size: 14px; margin-bottom: 10px;">🔍 Watch Architecture</div>
                        <div style="font-size: 11px;">Run code to visualize data flow</div>
                    </div>
                </div>

                <!-- Right Panel - Details -->
                <div id="watch-details-panel" style="width: 280px; background: var(--vscode-editor-lineHighlightBackground); border-radius: 8px; padding: 10px; overflow-y: auto;">
                    <h4 style="font-size: 12px; margin-bottom: 10px;">Select a node</h4>
                    <div id="watch-details-content" style="font-size: 11px; color: var(--vscode-descriptionForeground);">
                        Click on any function to see data flow details, importance score, and transformation info.
                    </div>
                </div>
            </div>

            <!-- Bottom Timeline -->
            <div id="watch-timeline-panel" style="height: 80px; background: var(--vscode-editor-lineHighlightBackground); border-radius: 8px; margin-top: 10px; padding: 10px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-size: 10px; color: var(--vscode-descriptionForeground); text-transform: uppercase;">Execution Timeline</span>
                    <span id="watch-event-count" style="font-size: 10px; color: var(--vscode-descriptionForeground);">0 events</span>
                </div>
                <div id="watch-timeline-view" style="height: 45px; background: var(--vscode-input-background); border-radius: 4px; position: relative; overflow-x: auto;">
                    <!-- Timeline events rendered here -->
                </div>
            </div>

            <!-- Legend -->
            <div style="display: flex; gap: 15px; margin-top: 10px; font-size: 10px; color: var(--vscode-descriptionForeground); flex-wrap: wrap;">
                <span><span style="display: inline-block; width: 10px; height: 10px; background: #a78bfa; border-radius: 2px; margin-right: 4px;"></span>Tensor</span>
                <span><span style="display: inline-block; width: 10px; height: 10px; background: #60a5fa; border-radius: 2px; margin-right: 4px;"></span>Message</span>
                <span><span style="display: inline-block; width: 10px; height: 10px; background: #4ade80; border-radius: 2px; margin-right: 4px;"></span>Class</span>
                <span><span style="display: inline-block; width: 10px; height: 10px; background: #fbbf24; border-radius: 2px; margin-right: 4px;"></span>Primitive</span>
                <span style="margin-left: auto;"><span style="color: #ef4444;">●</span> High Importance | <span style="color: #fbbf24;">●</span> Medium | <span style="color: #4ade80;">●</span> Low</span>
            </div>
        </div>

        <!-- Watch Architecture Export Modal -->
        <div id="watch-export-modal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center;">
            <div style="background: var(--vscode-editor-background); border-radius: 12px; padding: 20px; width: 450px; max-height: 80vh; overflow-y: auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h3 style="font-size: 14px;">Export with Rationales</h3>
                    <button onclick="hideWatchExportModal()" style="background: none; border: none; color: var(--vscode-descriptionForeground); font-size: 18px; cursor: pointer;">&times;</button>
                </div>
                <div style="margin-bottom: 10px;">
                    <label style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--vscode-input-background); border-radius: 6px; cursor: pointer; margin-bottom: 6px;">
                        <input type="checkbox" id="watch-export-trace" checked>
                        <div><div style="font-size: 12px;">Execution Trace</div><div style="font-size: 10px; color: var(--vscode-descriptionForeground);">Complete call graph with timing</div></div>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--vscode-input-background); border-radius: 6px; cursor: pointer; margin-bottom: 6px;">
                        <input type="checkbox" id="watch-export-importance" checked>
                        <div><div style="font-size: 12px;">Importance Scores</div><div style="font-size: 10px; color: var(--vscode-descriptionForeground);">LLM or fallback importance analysis</div></div>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--vscode-input-background); border-radius: 6px; cursor: pointer; margin-bottom: 6px;">
                        <input type="checkbox" id="watch-export-missing" checked>
                        <div><div style="font-size: 12px;">Missing Calls Analysis</div><div style="font-size: 10px; color: var(--vscode-descriptionForeground);">Expected calls that didn't happen</div></div>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; padding: 10px; background: var(--vscode-input-background); border-radius: 6px; cursor: pointer; margin-bottom: 6px;">
                        <input type="checkbox" id="watch-export-standalone" checked>
                        <div><div style="font-size: 12px;">Standalone HTML</div><div style="font-size: 10px; color: var(--vscode-descriptionForeground);">Self-contained file with embedded data</div></div>
                    </label>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 15px;">
                    <button onclick="exportWatchData('json')" style="flex: 1; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 8px; border-radius: 4px; cursor: pointer;">JSON</button>
                    <button onclick="exportWatchData('html')" style="flex: 1; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 8px; border-radius: 4px; cursor: pointer;">HTML Report</button>
                    <button onclick="exportWatchData('standalone')" style="flex: 1; background: #059669; color: white; border: none; padding: 8px; border-radius: 4px; cursor: pointer;">Standalone</button>
                </div>
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
        let showDeadCallTrees = false;
        let activeParticipants = new Set();  // Modules that have at least one call
        let allDefinedFunctions = new Set(); // All functions from static analysis (AST)

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

                // Refresh Interactive Explorer when Manim tab is opened
                if (tabName === 'manim') {
                    refreshInteractiveExplorer();
                }
            });
        });

        // Sub-tab switching (for Manim tab)
        document.querySelectorAll('.sub-tab').forEach(subtab => {
            subtab.addEventListener('click', () => {
                const subtabName = subtab.dataset.subtab;
                const container = subtab.closest('.content');
                container.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
                subtab.classList.add('active');
                container.querySelectorAll('.sub-content').forEach(c => c.classList.remove('active'));
                document.getElementById(subtabName + '-subcontent').classList.add('active');

                // Initialize explorer when switching to it
                if (subtabName === 'interactive-explorer') {
                    refreshInteractiveExplorer();
                }
            });
        });

        // Interactive Explorer data and state
        let explorerData = {
            functions: {},
            callGraph: {},
            coveredFunctions: [],
            deadFunctions: [],
            whyNotCovered: {}
        };
        let selectedExplorerNode = null;
        let explorerDataSignature = '';  // Cache signature to skip recreation

        // Registry data for "Why Not Covered" with actual branch conditions
        let functionRegistryData = new Map(); // funcKey -> {file, line}
        let callSitesData = []; // Call sites with branch info
        let functionBranchesData = new Map(); // funcKey -> branches[]
        let resolvedCallGraphData = {}; // Resolved static call graph for cross-class connections
        let classAttributesData = {}; // Class attribute types for display

        // Build Interactive Explorer data from trace
        function buildExplorerData() {
            const functions = {};
            const callGraph = {};
            const coveredFunctions = [];
            const deadFunctions = [];
            const whyNotCovered = {};

            // Build from performance data and call trace
            performanceData.forEach(p => {
                const funcKey = p.module + '.' + p.function;
                functions[funcKey] = {
                    name: p.function,
                    module: p.module,
                    line: p.line || 0,
                    file: p.file || '',
                    callCount: p.calls || 0,
                    branches: []
                };
                coveredFunctions.push(funcKey);
                if (!callGraph[funcKey]) {
                    callGraph[funcKey] = [];
                }
            });

            // Add call relationships from trace
            callTrace.forEach(event => {
                if (event.type === 'call' && event.parent_id) {
                    const parentKey = event.parent_module + '.' + event.parent_function;
                    const childKey = event.module + '.' + event.function;
                    if (callGraph[parentKey] && !callGraph[parentKey].includes(childKey)) {
                        callGraph[parentKey].push(childKey);
                    }
                }
            });

            // Merge resolved static call graph for cross-class connections
            // This adds edges AND ensures all static functions exist as nodes
            if (resolvedCallGraphData && Object.keys(resolvedCallGraphData).length > 0) {
                const staticFuncsAdded = new Set();

                Object.entries(resolvedCallGraphData).forEach(([caller, callees]) => {
                    // Ensure caller exists in functions
                    if (!functions[caller]) {
                        functions[caller] = {
                            name: caller.split('.').pop(),
                            module: caller.split('.').slice(0, -1).join('.') || '__static__',
                            line: 0,
                            file: '',
                            callCount: 0,
                            branches: [],
                            isStatic: true  // Mark as from static analysis
                        };
                        staticFuncsAdded.add(caller);
                    }

                    if (!callGraph[caller]) {
                        callGraph[caller] = [];
                    }

                    (callees as string[]).forEach(callee => {
                        // Ensure callee exists in functions
                        if (!functions[callee]) {
                            functions[callee] = {
                                name: callee.split('.').pop(),
                                module: callee.split('.').slice(0, -1).join('.') || '__static__',
                                line: 0,
                                file: '',
                                callCount: 0,
                                branches: [],
                                isStatic: true
                            };
                            staticFuncsAdded.add(callee);
                        }

                        if (!callGraph[caller].includes(callee)) {
                            callGraph[caller].push(callee);
                        }
                    });
                });

                console.log('[TrueFlow] Merged resolved call graph:',
                    Object.keys(callGraph).length, 'callers,',
                    staticFuncsAdded.size, 'static functions added');

                // Add static functions to allDefinedFunctions for dead code analysis
                staticFuncsAdded.forEach(func => allDefinedFunctions.add(func));
            }

            // Build reverse call graph (callee -> callers) for root cause tracing
            const reverseCallGraph = {};
            Object.entries(callGraph).forEach(([caller, callees]) => {
                callees.forEach(callee => {
                    if (!reverseCallGraph[callee]) {
                        reverseCallGraph[callee] = [];
                    }
                    if (!reverseCallGraph[callee].includes(caller)) {
                        reverseCallGraph[callee].push(caller);
                    }
                });
            });

            /**
             * ROOT CAUSE TRACING: Recursively trace up the call chain to find
             * the TOPMOST executed function that blocked execution.
             * @param func - The dead function to analyze
             * @param visited - Set of visited functions (prevent cycles)
             * @param chain - Call chain built so far (from dead func upward)
             * @returns {type, rootFunc, chain} or null
             */
            function traceToRootCause(func, visited, chain) {
                if (visited.has(func)) return null; // Cycle detected
                visited.add(func);
                chain.push(func);

                const callers = reverseCallGraph[func] || [];

                if (callers.length === 0) {
                    // No callers - this function has no call sites
                    return { type: 'NO_CALL_SITES', rootFunc: func, chain: [...chain] };
                }

                // Check each caller - if ANY is executed, that's our root cause
                for (const caller of callers) {
                    if (coveredFunctions.includes(caller)) {
                        // FOUND ROOT CAUSE! Caller was executed but didn't call this function
                        return { type: 'BRANCH_NOT_TAKEN', rootFunc: caller, chain: [...chain] };
                    }
                }

                // All callers are also dead - recurse up to find root
                for (const caller of callers) {
                    const result = traceToRootCause(caller, visited, chain);
                    if (result) return result;
                }

                // No executed function found - unreachable from entry points
                return { type: 'UNREACHABLE_FROM_ENTRY', rootFunc: chain[chain.length - 1], chain: [...chain] };
            }

            // Find dead functions with ROOT CAUSE TRACING
            allDefinedFunctions.forEach(func => {
                if (!coveredFunctions.includes(func)) {
                    deadFunctions.push(func);
                    functions[func] = functions[func] || {
                        name: func.split('.').pop(),
                        module: func.split('.').slice(0, -1).join('.'),
                        line: 0,
                        file: '',
                        callCount: 0,
                        branches: []
                    };

                    // Trace to ROOT CAUSE (not just immediate caller)
                    const rootCauseResult = traceToRootCause(func, new Set(), []);
                    const { type: rootCauseType, rootFunc, chain: callChain } = rootCauseResult ||
                        { type: 'UNKNOWN', rootFunc: func, chain: [func] };

                    const chainStr = callChain.length > 1
                        ? callChain.slice().reverse().join(' → ')
                        : func;

                    let reason;
                    switch (rootCauseType) {
                        case 'NO_CALL_SITES':
                            reason = {
                                type: 'NO_CALL_SITES',
                                explanation: "No code in the project calls '" + func + "'. May be dead code or only called externally."
                            };
                            break;
                        case 'BRANCH_NOT_TAKEN':
                            // Find ACTUAL branch condition from callSitesData
                            const firstDeadInChain = callChain[0] || func;
                            const relevantCallSite = callSitesData.find(site => {
                                const fullCaller = site.callerModule + '.' + site.caller;
                                return (fullCaller === rootFunc || site.caller === rootFunc) &&
                                    (site.callee === firstDeadInChain ||
                                     callChain.some(chainFunc => site.callee === chainFunc || chainFunc.endsWith('.' + site.callee)));
                            });

                            const actualBranchType = relevantCallSite?.inBranch?.type || 'if';
                            const actualCondition = relevantCallSite?.inBranch?.condition || 'condition was False';
                            const actualBranchLine = relevantCallSite?.inBranch?.line || 0;

                            reason = {
                                type: 'BRANCH_NOT_TAKEN',
                                caller: rootFunc,
                                branchType: actualBranchType,
                                branchCondition: actualCondition,
                                branchLine: actualBranchLine,
                                explanation: "Branch in '" + rootFunc + "' (line " + actualBranchLine + "): " + actualBranchType + " " + actualCondition + ". Chain: " + chainStr
                            };
                            break;
                        case 'UNREACHABLE_FROM_ENTRY':
                            reason = {
                                type: 'UNREACHABLE_FROM_ENTRY',
                                explanation: "Function '" + func + "' is unreachable from any entry point. Orphaned chain: " + chainStr
                            };
                            break;
                        default:
                            reason = {
                                type: 'UNKNOWN',
                                explanation: "Could not determine why '" + func + "' wasn't called"
                            };
                    }

                    whyNotCovered[func] = {
                        function: func,
                        rootCause: rootCauseType,
                        rootCauseDetail: rootCauseType === 'BRANCH_NOT_TAKEN' ? {
                            type: rootCauseType,
                            caller: rootFunc,
                            branchType: reason.branchType || 'if',
                            branchCondition: reason.branchCondition || 'condition was False',
                            branchLine: reason.branchLine || 0
                        } : null,
                        callChain: callChain,
                        reasons: [reason]
                    };
                }
            });

            explorerData = { functions, callGraph, coveredFunctions, deadFunctions, whyNotCovered };
            return explorerData;
        }

        // Debounce timer for explorer rendering
        let explorerRenderDebounceTimer = null;
        let explorerRenderPending = false;

        // Refresh Interactive Explorer visualization (debounced)
        function refreshInteractiveExplorer() {
            buildExplorerData();
            updateDeadCodeList();
            scheduleExplorerRender(true);
        }

        // Apply explorer filters and re-render (debounced)
        function applyExplorerFilters() {
            scheduleExplorerRender(true);
        }

        // Schedule a debounced render to avoid blocking UI
        function scheduleExplorerRender(forceRecreate = false) {
            if (explorerRenderDebounceTimer) {
                clearTimeout(explorerRenderDebounceTimer);
            }
            explorerRenderPending = true;

            // Show loading state immediately
            const loading = document.getElementById('explorer-loading');
            if (loading) {
                loading.style.display = 'block';
                loading.textContent = 'Rendering...';
            }

            // Debounce the actual render
            explorerRenderDebounceTimer = setTimeout(() => {
                requestAnimationFrame(() => {
                    renderExplorerVisualization(forceRecreate);
                    updateExplorerStats();
                    explorerRenderPending = false;
                });
            }, 100);  // 100ms debounce
        }

        // Get filtered function names based on current filter settings
        function getFilteredFunctions() {
            const coverageFilter = (document.getElementById('explorer-filter-coverage') as HTMLSelectElement)?.value || 'all';
            const moduleFilter = (document.getElementById('explorer-filter-module') as HTMLInputElement)?.value?.toLowerCase() || '';

            const coveredSet = new Set(explorerData.coveredFunctions);
            const deadSet = new Set(explorerData.deadFunctions);

            return Object.keys(explorerData.functions).filter(funcName => {
                // Apply module filter
                if (moduleFilter && !funcName.toLowerCase().includes(moduleFilter)) {
                    return false;
                }

                // Apply coverage filter
                const isCovered = coveredSet.has(funcName);
                const isDead = deadSet.has(funcName);
                const why = explorerData.whyNotCovered[funcName];
                const isOrphan = isDead && why && why.rootCause === 'NO_CALL_SITES';
                const isBranch = isDead && why && (why.rootCause === 'BRANCH_NOT_TAKEN' || why.rootCause === 'UNREACHABLE_FROM_ENTRY');

                switch (coverageFilter) {
                    case 'covered':
                        return isCovered;
                    case 'dead':
                        return isDead;
                    case 'orphan':
                        return isOrphan;
                    case 'branch':
                        return isBranch;
                    case 'all':
                    default:
                        return true;
                }
            });
        }

        // Update stats display (respects filters)
        function updateExplorerStats() {
            const filteredFuncs = getFilteredFunctions();
            const coveredSet = new Set(explorerData.coveredFunctions);
            const deadSet = new Set(explorerData.deadFunctions);

            const total = filteredFuncs.length;
            const covered = filteredFuncs.filter(f => coveredSet.has(f)).length;
            const dead = filteredFuncs.filter(f => deadSet.has(f)).length;

            document.getElementById('explorer-total').textContent = String(total);
            document.getElementById('explorer-covered').textContent = String(covered);
            document.getElementById('explorer-dead').textContent = String(dead);
        }

        // Three.js iframe state
        let explorerIframeInitialized = false;
        let explorerIframeReady = false;
        let pendingExplorerData = null;

        // Render visualization using Three.js iframe (parity with PyCharm)
        function renderExplorerVisualization(forceRecreate = false) {
            const iframe = document.getElementById('explorer-3d-iframe') as HTMLIFrameElement;
            const loading = document.getElementById('explorer-loading');

            if (!iframe) {
                console.error('[Explorer] Iframe not found');
                return;
            }

            // Get current filter state
            const coverageFilter = (document.getElementById('explorer-filter-coverage') as HTMLSelectElement)?.value || 'all';
            const moduleFilter = (document.getElementById('explorer-filter-module') as HTMLInputElement)?.value || '';

            // Build data object for Three.js visualization
            const vizData = {
                functions: explorerData.functions,
                call_graph: explorerData.callGraph,
                resolved_call_graph: resolvedCallGraphData || {},
                covered_functions: explorerData.coveredFunctions,
                dead_functions: explorerData.deadFunctions,
                why_not_covered: explorerData.whyNotCovered
            };

            // Merge accumulated protocol data into function entries for explorer
            for (const funcKey of Object.keys(vizData.functions)) {
                const protos = functionProtocols.get(funcKey);
                if (protos) {
                    (vizData.functions as any)[funcKey].protocols = protos;
                }
                const fw = functionFrameworks.get(funcKey);
                if (fw) {
                    (vizData.functions as any)[funcKey].framework = fw;
                }
                if (functionAiAgents.has(funcKey)) {
                    (vizData.functions as any)[funcKey].is_ai_agent = true;
                }
            }

            const funcCount = Object.keys(vizData.functions).length;

            // Create signature to detect if data changed
            const newSignature = JSON.stringify({
                functions: Object.keys(vizData.functions).sort(),
                callGraph: Object.keys(vizData.call_graph).sort(),
                covered: vizData.covered_functions.slice().sort(),
                dead: vizData.dead_functions.slice().sort(),
                filters: { coverage: coverageFilter, module: moduleFilter }
            });

            // Skip if data hasn't changed
            if (!forceRecreate && explorerDataSignature === newSignature && explorerIframeReady) {
                console.log('[Explorer] Data unchanged, sending filter update only');
                // Just send filter update
                iframe.contentWindow?.postMessage({
                    type: 'applyFilters',
                    filters: { coverage: coverageFilter, module: moduleFilter }
                }, '*');
                loading.style.display = 'none';
                return;
            }

            console.log('[Explorer] Updating Three.js visualization with', funcCount, 'functions');
            explorerDataSignature = newSignature;

            if (funcCount === 0) {
                loading.style.display = 'block';
                loading.textContent = coverageFilter === 'all' ? 'Run your code to generate visualization data' : 'No functions match the current filter';
                loading.style.color = '';
                return;
            }

            loading.style.display = 'none';

            // Initialize iframe if not done yet
            if (!explorerIframeInitialized) {
                initializeExplorerIframe(iframe, vizData);
                explorerIframeInitialized = true;
            } else if (explorerIframeReady) {
                // Send data to iframe
                iframe.contentWindow?.postMessage({
                    type: 'loadData',
                    data: vizData
                }, '*');
            } else {
                // Iframe not ready yet, store data for later
                pendingExplorerData = vizData;
            }
        }

        // Initialize the Three.js iframe with HTML content
        function initializeExplorerIframe(iframe: HTMLIFrameElement, initialData: any) {
            // Request the Three.js HTML content from extension
            vscode.postMessage({ type: 'getExplorerHtml' });

            // Store initial data to send once iframe is ready
            pendingExplorerData = initialData;

            // Listen for iframe ready message
            window.addEventListener('message', function handleIframeReady(event) {
                if (event.data && event.data.type === 'explorerReady') {
                    explorerIframeReady = true;
                    if (pendingExplorerData) {
                        iframe.contentWindow?.postMessage({
                            type: 'loadData',
                            data: pendingExplorerData
                        }, '*');
                        pendingExplorerData = null;
                    }
                }
            });
        }

        // Handle response from extension with HTML content
        function handleExplorerHtmlResponse(htmlContent: string) {
            const iframe = document.getElementById('explorer-3d-iframe') as HTMLIFrameElement;
            if (!iframe) return;

            // Inject ready signal into HTML
            const readyScript = '<script>window.parent.postMessage({type: "explorerReady"}, "*");</script>';
            const modifiedHtml = htmlContent.replace('</body>', readyScript + '</body>');

            // Set iframe content via srcdoc
            iframe.srcdoc = modifiedHtml;
        }

        // Legacy function stubs for compatibility (2D functions no longer used)
        function selectExplorerNode(funcName: string) {
            // Node selection now handled inside iframe
            console.log('[Explorer] Node selected:', funcName);
        }

        function showExplorerNodeDetails(funcName: string) {
            // Details panel now handled inside iframe
            console.log('[Explorer] Show details for:', funcName);
        }

        // Note: Legacy 2D helper functions removed - visualization now handled by Three.js iframe
        // The centerOnExplorerNode function is kept for potential future use but not actively called

        // Center the explorer view on a node with smooth animation (legacy - not used with iframe)
        function centerOnExplorerNode(node) {
            const container = document.getElementById('interactive-explorer-container');
            if (!container || !node) return;

            const canvas = document.getElementById('explorer-canvas');
            if (!canvas) return;

            // Get node position
            const nodeLeft = parseInt(node.style.left) || 0;
            const nodeTop = parseInt(node.style.top) || 0;
            const nodeWidth = node.offsetWidth || 100;
            const nodeHeight = node.offsetHeight || 30;

            // Calculate center position
            const containerWidth = container.clientWidth;
            const containerHeight = container.clientHeight;

            const targetScrollLeft = nodeLeft - (containerWidth / 2) + (nodeWidth / 2);
            const targetScrollTop = nodeTop - (containerHeight / 2) + (nodeHeight / 2);

            // Smooth scroll animation
            const startScrollLeft = container.scrollLeft;
            const startScrollTop = container.scrollTop;
            const duration = 300;
            const startTime = performance.now();

            function animateScroll() {
                const elapsed = performance.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const easeProgress = 1 - Math.pow(1 - progress, 3); // Ease out cubic

                container.scrollLeft = startScrollLeft + (targetScrollLeft - startScrollLeft) * easeProgress;
                container.scrollTop = startScrollTop + (targetScrollTop - startScrollTop) * easeProgress;

                if (progress < 1) {
                    requestAnimationFrame(animateScroll);
                }
            }

            animateScroll();
        }

        // Show class details when clicking on a class container
        function showExplorerClassDetails(className, methods, allDead) {
            const panel = document.getElementById('explorer-info-panel');
            const title = document.getElementById('explorer-info-title');
            const content = document.getElementById('explorer-info-content');

            if (title) title.textContent = className;

            const coveredMethods = methods.filter(m => explorerData.coveredFunctions.includes(m));
            const deadMethods = methods.filter(m => explorerData.deadFunctions.includes(m));

            let html = '<div style="font-size: 12px; margin-bottom: 8px;">';
            html += '<div><span style="color: #888; width: 80px; display: inline-block;">Type:</span>';
            html += '<span style="color: #7dd3fc;">Class</span></div>';
            html += '<div><span style="color: #888; width: 80px; display: inline-block;">Methods:</span>' + methods.length + '</div>';
            html += '<div><span style="color: #888; width: 80px; display: inline-block;">Covered:</span>';
            html += '<span style="color: #4ade80;">' + coveredMethods.length + '</span></div>';
            html += '<div><span style="color: #888; width: 80px; display: inline-block;">Dead:</span>';
            html += '<span style="color: #f87171;">' + deadMethods.length + '</span></div>';
            html += '<div><span style="color: #888; width: 80px; display: inline-block;">Status:</span>';
            html += '<span style="color: ' + (allDead ? '#f87171' : '#4ade80') + ';">' + (allDead ? 'FULLY DEAD' : 'ACTIVE') + '</span></div>';
            html += '</div>';

            html += '<div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid #333;">';
            html += '<div style="color: #888; font-size: 11px; margin-bottom: 6px;">Methods:</div>';
            html += '<ul style="margin: 0; padding-left: 16px; font-size: 11px;">';
            methods.forEach(m => {
                const methodName = m.split('.').pop();
                const isAlive = explorerData.coveredFunctions.includes(m);
                const color = isAlive ? '#4ade80' : '#f87171';
                html += '<li style="color: ' + color + '; margin-bottom: 2px;">' + methodName + '</li>';
            });
            html += '</ul></div>';

            if (content) content.innerHTML = html;
            if (panel) panel.style.display = 'block';
        }

        // ============================================================
        // WATCH ARCHITECTURE - Football-style data flow visualization
        // ============================================================
        let watchData = {
            functions: {},
            callGraph: {},
            coveredFunctions: [],
            deadFunctions: [],
            dataFlows: []
        };
        let watchDataSignature = '';  // Cache signature to skip recreation
        let watchRecording = false;
        let watchPlaying = false;
        let watchRecordedEvents = [];
        let watchRecordStartTime = null;
        let watchRecordDurationMs = 0;
        let watchDurationTimer = null;
        let watchCameraMode = 'auto';  // auto (intelligent follow + zoom), follow (just follow), overview (static)
        let watchLastDataPosition = null;
        let watchLastDataTime = 0;
        let watchDataVelocity = 0;
        let watchImportanceScores = new Map();
        let watchSelectedNode = null;
        let watchLlmEndpoint = null;

        // Playback state (viewer mode - not recording)
        let watchTraceEvents = [];  // All events from socket since start
        let watchCurrentEventIndex = 0;
        let watchPlaybackSpeed = 1.0;

        // Source filters (show/hide by type)
        let watchSourceFilters = {
            all: true,
            video: true,
            api: true,
            screen: true,
            audio: true
        };
        let watchShowBranchesNotTaken = false;

        // Importance scoring patterns (fallback when no LLM)
        const watchImportancePatterns = {
            high: ['api', 'request', 'response', 'model', 'inference', 'predict', 'forward', 'train', 'loss', 'gradient'],
            medium: ['process', 'encode', 'decode', 'parse', 'convert', 'extract', 'filter', 'validate'],
            low: ['log', 'debug', 'print', 'helper', 'util', 'init', '__', 'get_', 'set_']
        };

        // Data type classifiers
        const watchDataTypes = {
            tensor: ['ndarray', 'Tensor', 'tensor', 'np.array', 'torch.Tensor'],
            message: ['Message', 'Request', 'Response', 'Event', 'Packet'],
            primitive: ['int', 'float', 'str', 'bool', 'list', 'dict']
        };

        // Source patterns
        const watchSourcePatterns = {
            video: ['frame', 'camera', 'video', 'image', 'cv2', 'PIL'],
            api: ['request', 'response', 'http', 'websocket', 'api', 'fetch'],
            screen: ['screen', 'display', 'monitor', 'screenshot'],
            audio: ['audio', 'sound', 'microphone', 'wav', 'speech']
        };

        function initWatchArchitecture() {
            // Try to connect to local LLM
            tryConnectWatchLLM();
            // Draw grid
            drawWatchGrid();
            // Build data from existing trace
            buildWatchData();
        }

        async function tryConnectWatchLLM() {
            const endpoints = [
                'http://localhost:11434/api/generate',
                'http://localhost:8080/v1/completions',
                'http://localhost:1234/v1/completions'
            ];

            for (const endpoint of endpoints) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 2000);
                    const response = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ prompt: 'test', max_tokens: 1 }),
                        signal: controller.signal
                    });
                    clearTimeout(timeoutId);
                    if (response.ok || response.status === 400) {
                        watchLlmEndpoint = endpoint;
                        document.getElementById('watch-llm-status').innerHTML = '<span style="color: #4ade80;">● Connected</span>';
                        return;
                    }
                } catch (e) {
                    // Try next endpoint
                }
            }
            document.getElementById('watch-llm-status').innerHTML = '<span style="color: #fbbf24;">● Using fallback rules</span>';
        }

        function drawWatchGrid() {
            const grid = document.getElementById('watch-grid');
            if (!grid) return;
            grid.innerHTML = '';

            for (let x = 0; x <= 800; x += 50) {
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', x);
                line.setAttribute('y1', 0);
                line.setAttribute('x2', x);
                line.setAttribute('y2', 500);
                line.setAttribute('stroke', '#1a1a3a');
                line.setAttribute('stroke-width', '1');
                grid.appendChild(line);
            }
            for (let y = 0; y <= 500; y += 50) {
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', 0);
                line.setAttribute('y1', y);
                line.setAttribute('x2', 800);
                line.setAttribute('y2', y);
                line.setAttribute('stroke', '#1a1a3a');
                line.setAttribute('stroke-width', '1');
                grid.appendChild(line);
            }
        }

        function buildWatchData() {
            // Use existing explorer data
            watchData.functions = explorerData.functions;
            // Use resolved call graph for complete picture (static analysis), fallback to runtime
            watchData.callGraph = (resolvedCallGraphData && Object.keys(resolvedCallGraphData).length > 0)
                ? resolvedCallGraphData
                : explorerData.callGraph;
            watchData.runtimeCallGraph = explorerData.callGraph;  // Keep runtime for comparison
            watchData.coveredFunctions = explorerData.coveredFunctions;
            watchData.deadFunctions = explorerData.deadFunctions;
            watchData.whyNotCovered = explorerData.whyNotCovered;

            console.log('[Watch] Built data with', Object.keys(watchData.functions).length, 'functions,',
                Object.keys(watchData.callGraph).length, 'call graph entries');

            // Calculate importance scores
            Object.entries(watchData.functions).forEach(([name, info]) => {
                const importance = calculateWatchImportance(name, info);
                watchImportanceScores.set(name, importance);
            });

            // Update visualization
            renderWatchVisualization();
            updateWatchImportanceList();
        }

        function calculateWatchImportance(funcName, info) {
            const nameLower = funcName.toLowerCase();
            let importance = 0.5;

            // Check pattern matches
            for (const pattern of watchImportancePatterns.high) {
                if (nameLower.includes(pattern)) {
                    importance = Math.max(importance, 0.8 + Math.random() * 0.2);
                    break;
                }
            }
            for (const pattern of watchImportancePatterns.medium) {
                if (nameLower.includes(pattern)) {
                    importance = Math.max(importance, 0.5 + Math.random() * 0.2);
                    break;
                }
            }
            for (const pattern of watchImportancePatterns.low) {
                if (nameLower.includes(pattern)) {
                    importance = Math.min(importance, 0.2 + Math.random() * 0.1);
                    break;
                }
            }

            // Data type bonus
            const dataType = classifyWatchDataType(info);
            if (dataType === 'tensor') importance += 0.3;
            else if (dataType === 'message') importance += 0.2;

            // Connectivity bonus
            const callees = (watchData.callGraph[funcName] || []).length;
            const callers = Object.values(watchData.callGraph).filter(c => c.includes(funcName)).length;
            importance += Math.min((callees + callers) * 0.05, 0.2);

            return Math.min(Math.max(importance, 0), 1);
        }

        function classifyWatchDataType(info) {
            if (!info) return 'primitive';
            const typeStr = JSON.stringify(info).toLowerCase();
            for (const [type, patterns] of Object.entries(watchDataTypes)) {
                if (patterns.some(p => typeStr.includes(p.toLowerCase()))) {
                    return type;
                }
            }
            return 'primitive';
        }

        function classifyWatchSource(name, info) {
            const nameStr = (name + ' ' + JSON.stringify(info || {})).toLowerCase();
            for (const [source, patterns] of Object.entries(watchSourcePatterns)) {
                if (patterns.some(p => nameStr.includes(p))) {
                    return source;
                }
            }
            return null;
        }

        function renderWatchVisualization(forceRecreate = false) {
            const nodesGroup = document.getElementById('watch-nodes');
            const edgesGroup = document.getElementById('watch-edges');
            if (!nodesGroup || !edgesGroup) return;

            const functions = Object.keys(watchData.functions);

            // Create signature to detect if data changed
            const newSignature = JSON.stringify({
                functions: functions.slice().sort(),
                callGraph: Object.keys(watchData.callGraph).sort(),
                covered: watchData.coveredFunctions.slice().sort(),
                dead: watchData.deadFunctions.slice().sort()
            });

            // Skip recreation if data hasn't changed and we have nodes
            if (!forceRecreate && watchDataSignature === newSignature && nodesGroup.children.length > 0) {
                console.log('[Watch] Data unchanged, skipping recreation');
                document.getElementById('watch-loading').style.display = 'none';
                return;
            }

            console.log('[Watch] Creating visualization...');
            watchDataSignature = newSignature;

            nodesGroup.innerHTML = '';
            edgesGroup.innerHTML = '';

            if (functions.length === 0) {
                document.getElementById('watch-loading').style.display = 'block';
                return;
            }
            document.getElementById('watch-loading').style.display = 'none';

            // Calculate positions
            const positions = {};
            functions.forEach((name, i) => {
                positions[name] = {
                    x: 100 + (i % 4) * 180,
                    y: 60 + Math.floor(i / 4) * 90
                };
            });

            // Draw edges
            Object.entries(watchData.callGraph).forEach(([caller, callees]) => {
                const callerPos = positions[caller];
                if (!callerPos) return;
                callees.forEach(callee => {
                    const calleePos = positions[callee];
                    if (!calleePos) return;

                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    const midX = (callerPos.x + calleePos.x) / 2;
                    const midY = (callerPos.y + calleePos.y) / 2 - 20;
                    path.setAttribute('d', 'M ' + callerPos.x + ' ' + (callerPos.y + 15) + ' Q ' + midX + ' ' + midY + ' ' + calleePos.x + ' ' + (calleePos.y - 15));
                    path.setAttribute('fill', 'none');
                    path.setAttribute('stroke', '#3a3a5a');
                    path.setAttribute('stroke-width', '2');
                    path.setAttribute('marker-end', 'url(#watch-arrowhead)');
                    edgesGroup.appendChild(path);
                });
            });

            // Draw nodes
            functions.forEach(name => {
                const pos = positions[name];
                if (!pos) return;

                const importance = watchImportanceScores.get(name) || 0.5;
                const isAlive = watchData.coveredFunctions.includes(name);
                const color = importance > 0.7 ? '#ef4444' : importance > 0.4 ? '#fbbf24' : '#4ade80';

                const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                group.setAttribute('class', 'watch-node');
                group.setAttribute('transform', 'translate(' + pos.x + ', ' + pos.y + ')');
                group.setAttribute('data-name', name);
                group.style.cursor = 'pointer';

                const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                rect.setAttribute('x', -60);
                rect.setAttribute('y', -18);
                rect.setAttribute('width', 120);
                rect.setAttribute('height', 36);
                rect.setAttribute('rx', 6);
                rect.setAttribute('fill', isAlive ? '#1a3a1a' : '#3a1a1a');
                rect.setAttribute('stroke', color);
                rect.setAttribute('stroke-width', importance > 0.7 ? 3 : 2);

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('y', 4);
                text.setAttribute('fill', '#e0e0e0');
                text.setAttribute('font-size', '10');
                // Show method name for Class.method patterns
                let displayName = name;
                const dotIdx = name.lastIndexOf('.');
                if (dotIdx > 0) {
                    displayName = name.substring(dotIdx + 1);
                }
                if (displayName.length > 14) {
                    displayName = displayName.slice(0, 11) + '...';
                }
                text.textContent = displayName;

                const badge = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                badge.setAttribute('x', 50);
                badge.setAttribute('y', -10);
                badge.setAttribute('font-size', '8');
                badge.setAttribute('fill', color);
                badge.textContent = importance.toFixed(1);

                group.appendChild(rect);
                group.appendChild(text);
                group.appendChild(badge);

                group.addEventListener('click', () => selectWatchNode(name));
                nodesGroup.appendChild(group);
            });

            // Update event count
            document.getElementById('watch-event-count').textContent = watchRecordedEvents.length + ' events';
        }

        function updateWatchImportanceList() {
            const container = document.getElementById('watch-importance-list');
            if (!container) return;

            const sorted = Array.from(watchImportanceScores.entries())
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8);

            container.innerHTML = sorted.map(([name, score]) => {
                const colorClass = score > 0.7 ? '#ef4444' : score > 0.4 ? '#fbbf24' : '#4ade80';
                const shortName = name.length > 15 ? '...' + name.slice(-13) : name;
                return '<div style="display: flex; justify-content: space-between; padding: 4px; margin-bottom: 3px; background: var(--vscode-input-background); border-radius: 3px; border-left: 2px solid ' + colorClass + ';">' +
                    '<span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">' + shortName + '</span>' +
                    '<span style="color: ' + colorClass + ';">' + score.toFixed(2) + '</span></div>';
            }).join('');
        }

        function selectWatchNode(name) {
            watchSelectedNode = name;

            // Update selection visual
            document.querySelectorAll('.watch-node rect').forEach(rect => {
                rect.setAttribute('stroke-width', '2');
            });
            const selectedNode = document.querySelector('.watch-node[data-name="' + name + '"] rect');
            if (selectedNode) selectedNode.setAttribute('stroke-width', '4');

            // Update details panel
            const func = watchData.functions[name] || {};
            const importance = watchImportanceScores.get(name) || 0.5;
            const isAlive = watchData.coveredFunctions.includes(name);
            const source = classifyWatchSource(name, func);
            const dataType = classifyWatchDataType(func);

            let html = '<div style="margin-bottom: 12px;">';
            html += '<div style="font-size: 13px; font-weight: bold; margin-bottom: 8px;">' + name + '</div>';
            html += '<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px;">';
            html += '<span style="padding: 2px 6px; border-radius: 4px; font-size: 9px; background: rgba(' + (isAlive ? '74, 222, 128' : '248, 113, 113') + ', 0.2); color: ' + (isAlive ? '#4ade80' : '#f87171') + ';">' + (isAlive ? 'ALIVE' : 'DEAD') + '</span>';
            html += '<span style="padding: 2px 6px; border-radius: 4px; font-size: 9px; background: rgba(' + (importance > 0.7 ? '239, 68, 68' : importance > 0.4 ? '251, 191, 36' : '74, 222, 128') + ', 0.2); color: ' + (importance > 0.7 ? '#ef4444' : importance > 0.4 ? '#fbbf24' : '#4ade80') + ';">Importance: ' + importance.toFixed(2) + '</span>';
            if (source) html += '<span style="padding: 2px 6px; border-radius: 4px; font-size: 9px; background: rgba(255,255,255,0.1);">' + source + '</span>';
            html += '</div></div>';

            html += '<div style="margin-bottom: 12px; padding: 8px; background: var(--vscode-input-background); border-radius: 4px;">';
            html += '<div style="font-size: 10px; color: var(--vscode-descriptionForeground); margin-bottom: 4px;">Data Type</div>';
            html += '<div style="font-size: 11px;">' + dataType + '</div>';
            html += '</div>';

            if (func.line) {
                html += '<div style="font-size: 10px; color: var(--vscode-descriptionForeground);">Line: ' + func.line + '</div>';
            }

            document.getElementById('watch-details-content').innerHTML = html;

            // Camera: tele mode zooms to selected node
            if (watchCameraMode === 'tele') {
                zoomWatchToNode(name);
            }
        }

        function toggleWatchRecording() {
            if (watchRecording) {
                stopWatchRecording();
            } else {
                startWatchRecording();
            }
        }

        function startWatchRecording() {
            watchRecording = true;
            watchRecordedEvents = [];
            watchRecordStartTime = Date.now();
            watchRecordDurationMs = 0;

            document.getElementById('watch-record-btn').innerHTML = '⏹ Stop';
            document.getElementById('watch-record-btn').style.background = 'rgba(239, 68, 68, 0.3)';
            document.getElementById('watch-recording-duration').style.display = 'block';

            watchDurationTimer = setInterval(() => {
                watchRecordDurationMs = Date.now() - watchRecordStartTime;
                updateWatchDurationDisplay();
            }, 100);
        }

        function stopWatchRecording() {
            watchRecording = false;
            watchRecordDurationMs = Date.now() - watchRecordStartTime;

            document.getElementById('watch-record-btn').innerHTML = '⏺ Record';
            document.getElementById('watch-record-btn').style.background = '';

            if (watchDurationTimer) {
                clearInterval(watchDurationTimer);
                watchDurationTimer = null;
            }
            updateWatchDurationDisplay();
        }

        function updateWatchDurationDisplay() {
            const totalSeconds = Math.floor(watchRecordDurationMs / 1000);
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const seconds = totalSeconds % 60;
            const display = String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
            document.getElementById('watch-duration').textContent = display;
        }

        function getWatchDurationFormatted() {
            const totalSeconds = Math.floor(watchRecordDurationMs / 1000);
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const seconds = totalSeconds % 60;
            if (hours > 0) return hours + 'h ' + minutes + 'm ' + seconds + 's';
            if (minutes > 0) return minutes + 'm ' + seconds + 's';
            return seconds + 's';
        }

        function toggleWatchPlayback() {
            if (watchPlaying) {
                stopWatchPlayback();
            } else {
                startWatchPlayback();
            }
        }

        function startWatchPlayback() {
            // Use trace events if available, otherwise use recorded events
            if (watchTraceEvents.length === 0 && watchRecordedEvents.length > 0) {
                watchTraceEvents = watchRecordedEvents;
            }
            if (watchTraceEvents.length === 0) {
                console.log('No events to play back');
                return;
            }

            watchPlaying = true;
            const playIcon = document.getElementById('watch-play-icon');
            if (playIcon) playIcon.textContent = '⏸';
            watchPlaybackLoop();
        }

        function stopWatchPlayback() {
            watchPlaying = false;
            const playIcon = document.getElementById('watch-play-icon');
            if (playIcon) playIcon.textContent = '▶';
        }

        function watchPlaybackLoop() {
            if (!watchPlaying) return;

            const event = watchTraceEvents[watchCurrentEventIndex];
            if (!event) {
                stopWatchPlayback();
                return;
            }

            // Get importance-adjusted delay
            const funcName = event.function || event.module || '';
            const importance = watchImportanceScores.get(funcName) || 0.5;
            const baseDelay = 100;
            const importanceMultiplier = importance > 0.7 ? 3 : importance > 0.4 ? 1.5 : 1;
            const delay = (baseDelay * importanceMultiplier) / watchPlaybackSpeed;

            // Visualize current event
            visualizeWatchEventAtIndex(watchCurrentEventIndex);
            updateWatchPlaybackDisplay();

            // Move to next event
            watchCurrentEventIndex++;

            if (watchCurrentEventIndex >= watchTraceEvents.length) {
                stopWatchPlayback();
                return;
            }

            setTimeout(() => watchPlaybackLoop(), delay);
        }

        function visualizeWatchEventAtIndex(index) {
            if (index < 0 || index >= watchTraceEvents.length) return;

            const event = watchTraceEvents[index];
            const funcName = event.function || event.module || '';

            // Highlight the current node
            highlightWatchNode(funcName, true);

            // Auto-camera: focus on action
            if (watchCameraMode === 'auto' || watchCameraMode === 'follow') {
                autoWatchCameraFocusOn(funcName, event);
            }
        }

        function highlightWatchNode(name, active) {
            const node = document.querySelector('.watch-node[data-name="' + name + '"] rect');
            if (!node) return;

            if (active) {
                node.setAttribute('fill', 'rgba(74, 222, 128, 0.3)');
                setTimeout(() => highlightWatchNode(name, false), 500);
            } else {
                const isAlive = watchData.coveredFunctions.includes(name);
                node.setAttribute('fill', isAlive ? '#1a3a1a' : '#3a1a1a');
            }
        }

        function autoWatchCameraFocusOn(funcName, event) {
            const node = document.querySelector('.watch-node[data-name="' + funcName + '"]');
            if (!node) return;

            const transform = node.getAttribute('transform');
            const match = transform.match(/translate\\((\\d+(?:\\.\\d+)?),\\s*(\\d+(?:\\.\\d+)?)\\)/);
            if (!match) return;

            const x = parseFloat(match[1]);
            const y = parseFloat(match[2]);
            const now = performance.now();

            // Calculate data velocity (how fast data is moving between nodes)
            if (watchLastDataPosition) {
                const dx = x - watchLastDataPosition.x;
                const dy = y - watchLastDataPosition.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                const timeDelta = now - watchLastDataTime;
                watchDataVelocity = timeDelta > 0 ? distance / timeDelta : 0;
            }
            watchLastDataPosition = { x, y };
            watchLastDataTime = now;

            const importance = watchImportanceScores.get(funcName) || 0.5;

            // AUTO MODE: Intelligent zoom based on importance & velocity
            let viewWidth, viewHeight;

            if (watchCameraMode === 'auto') {
                const velocityFactor = Math.min(watchDataVelocity * 50, 1);  // 0-1 scale

                if (importance > 0.7) {
                    // Critical call - zoom in tight
                    viewWidth = 150 + velocityFactor * 50;
                    viewHeight = viewWidth * 0.75;
                } else if (importance > 0.4 || velocityFactor > 0.5) {
                    // Medium importance or fast movement
                    viewWidth = 250 + velocityFactor * 100;
                    viewHeight = viewWidth * 0.75;
                } else {
                    // Normal follow
                    viewWidth = 350;
                    viewHeight = 260;
                }

                // Fast data movement = zoom out to show trajectory
                if (velocityFactor > 0.7) {
                    viewWidth = Math.min(viewWidth + 150, 600);
                    viewHeight = viewWidth * 0.75;
                }
            } else if (watchCameraMode === 'follow') {
                // Simple follow - consistent zoom
                viewWidth = 300;
                viewHeight = 225;
            } else {
                // Overview - don't move
                return;
            }

            document.getElementById('watch-flow-svg').setAttribute('viewBox',
                (x - viewWidth/2) + ' ' + (y - viewHeight/2) + ' ' + viewWidth + ' ' + viewHeight);

            // Show importance indicator for important events
            const indicator = document.getElementById('watch-branch-indicator');
            if (indicator && importance > 0.7) {
                indicator.style.display = 'block';
                indicator.style.background = importance > 0.8 ? '#ef4444' : '#fbbf24';
                indicator.style.color = importance > 0.8 ? 'white' : 'black';
                indicator.textContent = 'Important: ' + funcName.split('.').pop();
                setTimeout(() => { indicator.style.display = 'none'; }, 2000);
            }
        }

        function updateWatchPlaybackDisplay() {
            const current = watchCurrentEventIndex;
            const total = watchTraceEvents.length;

            // Update event counter
            const eventIndex = document.getElementById('watch-event-index');
            const totalEvents = document.getElementById('watch-total-events');
            if (eventIndex) eventIndex.textContent = current.toString();
            if (totalEvents) totalEvents.textContent = total.toString();

            // Update timeline scrubber
            const scrubber = document.getElementById('watch-timeline-scrubber');
            if (scrubber && total > 0) {
                scrubber.value = ((current / total) * 100).toString();
            }
        }

        function scrubWatchTimeline(value) {
            const percent = parseFloat(value) / 100;
            const totalEvents = watchTraceEvents.length;
            if (totalEvents === 0) return;

            watchCurrentEventIndex = Math.floor(percent * totalEvents);
            updateWatchPlaybackDisplay();
            visualizeWatchEventAtIndex(watchCurrentEventIndex);
        }

        function setWatchPlaybackSpeed(speed) {
            watchPlaybackSpeed = parseFloat(speed);
        }

        function watchStepBack() {
            watchCurrentEventIndex = Math.max(0, watchCurrentEventIndex - 1);
            updateWatchPlaybackDisplay();
            visualizeWatchEventAtIndex(watchCurrentEventIndex);
        }

        function watchStepForward() {
            watchCurrentEventIndex = Math.min(
                watchTraceEvents.length - 1,
                watchCurrentEventIndex + 1
            );
            updateWatchPlaybackDisplay();
            visualizeWatchEventAtIndex(watchCurrentEventIndex);
        }

        // Source filter functions
        function toggleWatchSourceFilter(source) {
            if (source === 'all') {
                const newState = !watchSourceFilters.all;
                watchSourceFilters = {
                    all: newState,
                    video: newState,
                    api: newState,
                    screen: newState,
                    audio: newState
                };
            } else {
                watchSourceFilters[source] = !watchSourceFilters[source];
                watchSourceFilters.all = ['video', 'api', 'screen', 'audio']
                    .every(s => watchSourceFilters[s]);
            }

            // Update button states
            const btn = document.querySelector('.watch-source-filter[data-source="' + source + '"]');
            if (btn) btn.classList.toggle('active');

            if (source === 'all') {
                document.querySelectorAll('.watch-source-filter:not([data-source="all"])').forEach(b => {
                    b.classList.toggle('active', watchSourceFilters.all);
                });
            } else {
                const allBtn = document.querySelector('.watch-source-filter[data-source="all"]');
                if (allBtn) allBtn.classList.toggle('active', watchSourceFilters.all);
            }

            updateWatchNodeVisibilityBySource();
        }

        function updateWatchNodeVisibilityBySource() {
            document.querySelectorAll('.watch-node').forEach(node => {
                const name = node.getAttribute('data-name');
                const source = classifyWatchSource(name, watchData.functions[name] || {});
                const visible = watchSourceFilters.all ||
                    (source && watchSourceFilters[source]) ||
                    (!source && watchSourceFilters.all);

                node.style.display = visible ? '' : 'none';
            });
        }

        // Branch display toggle
        function toggleWatchBranchDisplay() {
            watchShowBranchesNotTaken = !watchShowBranchesNotTaken;
            const btn = document.getElementById('watch-branch-toggle');
            if (btn) {
                btn.classList.toggle('active', watchShowBranchesNotTaken);
                btn.style.background = watchShowBranchesNotTaken ? 'rgba(239, 68, 68, 0.2)' : '';
                btn.style.borderColor = watchShowBranchesNotTaken ? '#ef4444' : '';
            }

            updateWatchBranchMarkers();
        }

        function updateWatchBranchMarkers() {
            // Remove existing branch markers
            document.querySelectorAll('.watch-branch-marker').forEach(m => m.remove());

            if (!watchShowBranchesNotTaken) return;

            const nodesGroup = document.getElementById('watch-nodes');
            if (!nodesGroup) return;

            // Add markers for dead functions
            watchData.deadFunctions.forEach(funcName => {
                const node = document.querySelector('.watch-node[data-name="' + funcName + '"]');
                if (!node) return;

                const transform = node.getAttribute('transform');
                const match = transform.match(/translate\\((\\d+(?:\\.\\d+)?),\\s*(\\d+(?:\\.\\d+)?)\\)/);
                if (!match) return;

                const x = parseFloat(match[1]);
                const y = parseFloat(match[2]);

                // Create X marker
                const marker = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                marker.setAttribute('class', 'watch-branch-marker');
                marker.setAttribute('transform', 'translate(' + x + ', ' + (y - 25) + ')');

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('r', '10');
                circle.setAttribute('fill', 'rgba(239, 68, 68, 0.3)');
                circle.setAttribute('stroke', '#ef4444');
                circle.setAttribute('stroke-width', '2');

                const line1 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line1.setAttribute('x1', '-5'); line1.setAttribute('y1', '-5');
                line1.setAttribute('x2', '5'); line1.setAttribute('y2', '5');
                line1.setAttribute('stroke', '#ef4444'); line1.setAttribute('stroke-width', '2');

                const line2 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line2.setAttribute('x1', '5'); line2.setAttribute('y1', '-5');
                line2.setAttribute('x2', '-5'); line2.setAttribute('y2', '5');
                line2.setAttribute('stroke', '#ef4444'); line2.setAttribute('stroke-width', '2');

                marker.appendChild(circle);
                marker.appendChild(line1);
                marker.appendChild(line2);
                nodesGroup.appendChild(marker);
            });

            // Add dashed lines for expected but not called
            Object.entries(watchData.functions).forEach(([name, info]) => {
                if (info.expected_but_not_called) {
                    const fromNode = document.querySelector('.watch-node[data-name="' + name + '"]');
                    if (!fromNode) return;

                    const fromTransform = fromNode.getAttribute('transform');
                    const fromMatch = fromTransform.match(/translate\\((\\d+(?:\\.\\d+)?),\\s*(\\d+(?:\\.\\d+)?)\\)/);
                    if (!fromMatch) return;

                    info.expected_but_not_called.forEach(expected => {
                        const targetFunc = expected.function || expected;
                        const toNode = document.querySelector('.watch-node[data-name="' + targetFunc + '"]');
                        if (!toNode) return;

                        const toTransform = toNode.getAttribute('transform');
                        const toMatch = toTransform.match(/translate\\((\\d+(?:\\.\\d+)?),\\s*(\\d+(?:\\.\\d+)?)\\)/);
                        if (!toMatch) return;

                        const path = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        path.setAttribute('class', 'watch-branch-marker');
                        path.setAttribute('x1', fromMatch[1]);
                        path.setAttribute('y1', fromMatch[2]);
                        path.setAttribute('x2', toMatch[1]);
                        path.setAttribute('y2', toMatch[2]);
                        path.setAttribute('stroke', '#ef4444');
                        path.setAttribute('stroke-width', '2');
                        path.setAttribute('stroke-dasharray', '5,5');
                        path.setAttribute('opacity', '0.6');
                        document.getElementById('watch-edges').appendChild(path);
                    });
                }
            });
        }

        // Load trace events from external source
        function loadWatchTraceEvents(events) {
            watchTraceEvents = events;
            const totalEl = document.getElementById('watch-total-events');
            if (totalEl) totalEl.textContent = events.length.toString();
            const countEl = document.getElementById('watch-event-count');
            if (countEl) countEl.textContent = events.length + ' events';
            console.log('Loaded ' + events.length + ' trace events for playback');
        }

        function setWatchCamera(mode) {
            watchCameraMode = mode;

            // Update button states
            document.querySelectorAll('.camera-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-camera') === mode);
            });

            // Handle camera modes
            switch (mode) {
                case 'overview':
                    document.getElementById('watch-flow-svg').setAttribute('viewBox', '0 0 800 500');
                    break;
                case 'flyby':
                    // Animate through nodes
                    animateWatchFlyby();
                    break;
                case 'tele':
                    if (watchSelectedNode) {
                        zoomWatchToNode(watchSelectedNode);
                    }
                    break;
                case 'follow':
                    // Follow mode activates during playback
                    break;
            }
        }

        function animateWatchFlyby() {
            const nodes = document.querySelectorAll('.watch-node');
            if (nodes.length === 0) return;

            let currentIndex = 0;
            const flyToNext = () => {
                if (watchCameraMode !== 'flyby') return;

                const node = nodes[currentIndex];
                const transform = node.getAttribute('transform');
                const match = transform.match(/translate\\((\\d+(?:\\.\\d+)?),\\s*(\\d+(?:\\.\\d+)?)\\)/);
                if (match) {
                    const x = parseFloat(match[1]);
                    const y = parseFloat(match[2]);
                    document.getElementById('watch-flow-svg').setAttribute('viewBox', (x - 150) + ' ' + (y - 100) + ' 300 200');
                }

                currentIndex = (currentIndex + 1) % nodes.length;
                setTimeout(flyToNext, 2000);
            };
            flyToNext();
        }

        function zoomWatchToNode(name) {
            const node = document.querySelector('.watch-node[data-name="' + name + '"]');
            if (!node) return;

            const transform = node.getAttribute('transform');
            const match = transform.match(/translate\\((\\d+(?:\\.\\d+)?),\\s*(\\d+(?:\\.\\d+)?)\\)/);
            if (match) {
                const x = parseFloat(match[1]);
                const y = parseFloat(match[2]);
                document.getElementById('watch-flow-svg').setAttribute('viewBox', (x - 100) + ' ' + (y - 75) + ' 200 150');
            }
        }

        function filterWatchBySource(source) {
            // Highlight nodes matching source
            document.querySelectorAll('.watch-node').forEach(node => {
                const name = node.getAttribute('data-name');
                const func = watchData.functions[name];
                const nodeSource = classifyWatchSource(name, func);
                node.style.opacity = (!source || nodeSource === source) ? 1 : 0.3;
            });
        }

        function showWatchExportModal() {
            document.getElementById('watch-export-modal').style.display = 'flex';
        }

        function hideWatchExportModal() {
            document.getElementById('watch-export-modal').style.display = 'none';
        }

        function exportWatchData(format) {
            const includeTrace = document.getElementById('watch-export-trace').checked;
            const includeImportance = document.getElementById('watch-export-importance').checked;
            const includeMissing = document.getElementById('watch-export-missing').checked;
            const includeStandalone = document.getElementById('watch-export-standalone').checked;

            const exportData = {
                metadata: {
                    exported_at: new Date().toISOString(),
                    total_events: watchRecordedEvents.length,
                    total_functions: Object.keys(watchData.functions).length,
                    recording_duration_ms: watchRecordDurationMs,
                    recording_duration_formatted: getWatchDurationFormatted(),
                    camera_mode: watchCameraMode,
                    llm_available: !!watchLlmEndpoint
                }
            };

            if (includeTrace) {
                exportData.execution_trace = watchRecordedEvents;
                exportData.call_graph = watchData.callGraph;
                exportData.functions = watchData.functions;
            }

            if (includeImportance) {
                exportData.importance_scores = Object.fromEntries(watchImportanceScores);
            }

            if (includeMissing) {
                exportData.missing_calls = watchData.deadFunctions.map(f => ({
                    function: f,
                    reason: 'Not called during execution'
                }));
            }

            if (format === 'json') {
                downloadWatchJSON(exportData);
            } else if (format === 'standalone') {
                downloadWatchStandalone(exportData);
            } else {
                downloadWatchHTMLReport(exportData);
            }

            hideWatchExportModal();
        }

        function downloadWatchJSON(data) {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'trueflow_watch_' + new Date().toISOString().slice(0, 19).replace(/[:-]/g, '') + '.json';
            a.click();
            URL.revokeObjectURL(url);
        }

        function downloadWatchHTMLReport(data) {
            var html = '<!DOCTYPE html><html><head><title>TrueFlow Watch Report</title>';
            html += '<style>body{font-family:system-ui;background:#0a0a1a;color:#e0e0e0;padding:20px;max-width:1200px;margin:0 auto;}';
            html += 'h1{color:#7dd3fc;}h2{color:#a78bfa;border-bottom:1px solid #2a2a4a;padding-bottom:10px;}';
            html += '.section{background:#12122a;padding:20px;border-radius:8px;margin-bottom:20px;}';
            html += '.stat{display:inline-block;margin-right:30px;}.stat-value{font-size:24px;font-weight:bold;color:#4ade80;}';
            html += '.stat-label{font-size:12px;color:#888;}</style></head><body>';
            html += '<h1>TrueFlow Watch Architecture Report</h1>';
            html += '<p>Generated: ' + data.metadata.exported_at + '</p>';
            html += '<div class="section"><h2>Summary</h2>';
            html += '<div class="stat"><div class="stat-value">' + data.metadata.total_functions + '</div><div class="stat-label">Functions</div></div>';
            html += '<div class="stat"><div class="stat-value">' + data.metadata.total_events + '</div><div class="stat-label">Events</div></div>';
            html += '<div class="stat"><div class="stat-value">' + data.metadata.recording_duration_formatted + '</div><div class="stat-label">Duration</div></div>';
            html += '</div>';
            html += '<div class="section"><h2>Data</h2><pre style="overflow:auto;max-height:500px;background:#0d0d20;padding:15px;border-radius:4px;">' + JSON.stringify(data, null, 2) + '</pre></div>';
            html += '</body></html>';

            const blob = new Blob([html], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'trueflow_watch_report_' + new Date().toISOString().slice(0, 19).replace(/[:-]/g, '') + '.html';
            a.click();
            URL.revokeObjectURL(url);
        }

        function downloadWatchStandalone(data) {
            var html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>TrueFlow Standalone</title>';
            html += '<style>*{margin:0;padding:0;box-sizing:border-box;}body{font-family:system-ui;background:#0a0a1a;color:#e0e0e0;}';
            html += '.header{background:linear-gradient(90deg,#1a1a3a,#2a2a5a);padding:15px 20px;border-bottom:2px solid #3b82f6;display:flex;justify-content:space-between;align-items:center;}';
            html += '.header h1{font-size:18px;color:#7dd3fc;}.meta{font-size:11px;color:#888;display:flex;gap:20px;}';
            html += '.container{display:flex;height:calc(100vh-60px);}.sidebar{width:280px;background:#12122a;padding:15px;overflow-y:auto;}';
            html += '.main{flex:1;padding:20px;overflow:auto;}.section{margin-bottom:20px;}';
            html += '.section h3{font-size:12px;color:#7dd3fc;margin-bottom:10px;text-transform:uppercase;}';
            html += '.card{background:#1a1a3a;padding:12px;border-radius:8px;margin-bottom:8px;}';
            html += '.stat-value{font-size:20px;font-weight:bold;color:#4ade80;}.stat-label{font-size:11px;color:#888;}';
            html += 'pre{background:#0d0d20;padding:15px;border-radius:8px;overflow:auto;font-size:11px;}</style></head>';
            html += '<body><div class="header"><h1>TrueFlow Watch Architecture</h1>';
            html += '<div class="meta"><span>Exported: ' + data.metadata.exported_at + '</span>';
            html += '<span>Duration: ' + data.metadata.recording_duration_formatted + '</span>';
            html += '<span>Functions: ' + data.metadata.total_functions + '</span>';
            html += '<span>Events: ' + data.metadata.total_events + '</span></div></div>';
            html += '<div class="container"><div class="sidebar">';
            html += '<div class="section"><h3>Stats</h3>';
            html += '<div class="card"><div class="stat-value">' + data.metadata.recording_duration_formatted + '</div><div class="stat-label">Recording Duration</div></div>';
            html += '<div class="card"><div class="stat-value">' + data.metadata.total_functions + '</div><div class="stat-label">Functions Traced</div></div>';
            html += '<div class="card"><div class="stat-value">' + (data.metadata.llm_available ? 'Yes' : 'Fallback') + '</div><div class="stat-label">LLM Used</div></div>';
            html += '</div></div><div class="main">';
            html += '<h2 style="color:#7dd3fc;margin-bottom:20px;">Embedded Data</h2>';
            html += '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            html += '</div></div>';
            html += '<script>const TRUEFLOW_DATA = ' + JSON.stringify(data) + ';console.log("TrueFlow Standalone loaded", TRUEFLOW_DATA);<\\/script>';
            html += '</body></html>';

            const blob = new Blob([html], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'trueflow_standalone_' + new Date().toISOString().slice(0, 19).replace(/[:-]/g, '') + '.html';
            a.click();
            URL.revokeObjectURL(url);
        }

        // Live server state
        let liveServerRunning = false;

        function toggleLiveServer() {
            // Build current data for the server
            const data = {
                functions: explorerData.functions,
                call_graph: explorerData.callGraph,
                resolved_call_graph: resolvedCallGraphData,
                covered_functions: explorerData.coveredFunctions,
                dead_functions: explorerData.deadFunctions,
                why_not_covered: explorerData.whyNotCovered,
                timestamp: Date.now()
            };

            vscode.postMessage({
                type: 'toggleLiveServer',
                data: data
            });
        }

        function updateLiveServerButton(isRunning, url) {
            const btn = document.getElementById('live-server-btn');
            if (btn) {
                liveServerRunning = isRunning;
                if (isRunning && url) {
                    btn.textContent = '✕ Close Browser';
                    btn.title = 'Live at ' + url + ' - Click to close';
                    btn.style.background = '#4CAF50';
                    btn.style.color = 'white';
                } else {
                    btn.textContent = '🌐 Open in Browser';
                    btn.title = 'Open visualization in browser with real-time updates';
                    btn.style.background = '';
                    btn.style.color = '';
                }
            }
        }

        function exportSnapshot() {
            // Build data for the 3D explorer (static snapshot)
            const data = {
                functions: explorerData.functions,
                call_graph: explorerData.callGraph,
                resolved_call_graph: resolvedCallGraphData,
                covered_functions: explorerData.coveredFunctions,
                dead_functions: explorerData.deadFunctions,
                why_not_covered: explorerData.whyNotCovered
            };

            // Request the HTML template from the extension
            vscode.postMessage({
                type: 'exportSnapshot',
                data: data
            });
        }

        // Keep old function name for backward compatibility
        function openExplorerInBrowser() {
            exportSnapshot();
        }

        function openWatchInBrowser() {
            const data = {
                functions: watchData.functions,
                call_graph: watchData.callGraph,
                resolved_call_graph: resolvedCallGraphData,
                runtime_call_graph: watchData.runtimeCallGraph || explorerData.callGraph,
                covered_functions: watchData.coveredFunctions,
                dead_functions: watchData.deadFunctions,
                why_not_covered: watchData.whyNotCovered || explorerData.whyNotCovered,
                importance_scores: Object.fromEntries(watchImportanceScores),
                recorded_events: watchRecordedEvents,
                recording_duration_ms: watchRecordDurationMs
            };

            var html = '<!DOCTYPE html><html><head><title>TrueFlow Full Screen</title>';
            html += '<style>body{margin:0;padding:20px;background:#0a0a1a;color:#e0e0e0;font-family:system-ui;}';
            html += 'h1{color:#7dd3fc;}.info{background:#12122a;padding:15px;border-radius:8px;margin-bottom:20px;}';
            html += '.stat{display:inline-block;margin-right:30px;}.stat-value{font-size:24px;font-weight:bold;color:#4ade80;}';
            html += '.stat-label{font-size:12px;color:#888;}pre{background:#1a1a3a;padding:15px;border-radius:8px;overflow:auto;max-height:80vh;}</style></head>';
            html += '<body><h1>TrueFlow Watch Architecture Data</h1>';
            html += '<div class="info"><div class="stat"><div class="stat-value">' + Object.keys(data.functions).length + '</div><div class="stat-label">Functions</div></div>';
            html += '<div class="stat"><div class="stat-value">' + (data.recorded_events?.length || 0) + '</div><div class="stat-label">Events</div></div>';
            html += '<div class="stat"><div class="stat-value">' + getWatchDurationFormatted() + '</div><div class="stat-label">Duration</div></div></div>';
            html += '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            html += '<script>console.log("TrueFlow data:", ' + JSON.stringify(data) + ');<\\/script></body></html>';

            const blob = new Blob([html], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            const newWindow = window.open(url, '_blank');
            if (!newWindow) {
                const a = document.createElement('a');
                a.href = url;
                a.download = 'trueflow_fullscreen.html';
                a.click();
                vscode.postMessage({ type: 'info', message: 'Popup blocked. File downloaded instead.' });
            }
            setTimeout(() => URL.revokeObjectURL(url), 10000);
        }

        // Initialize Watch Architecture when its tab is shown
        document.querySelectorAll('.sub-tab').forEach(subtab => {
            subtab.addEventListener('click', () => {
                if (subtab.dataset.subtab === 'watch-architecture') {
                    initWatchArchitecture();
                }
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

        function openDiagramInBrowser() {
            const code = document.getElementById('diagram-code').value;
            const diagramType = document.getElementById('diagram-type').value;
            const showingDeadTrees = document.getElementById('show-dead-call-trees').checked;

            // Build a standalone HTML page with the diagram using string concatenation
            // to avoid nested template literal issues
            var htmlParts = [];
            htmlParts.push('<!DOCTYPE html>');
            htmlParts.push('<html lang="en">');
            htmlParts.push('<head>');
            htmlParts.push('<meta charset="UTF-8">');
            htmlParts.push('<meta name="viewport" content="width=device-width, initial-scale=1.0">');
            htmlParts.push('<title>TrueFlow Sequence Diagram - Fullscreen</title>');
            htmlParts.push('<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"><\\/script>');
            htmlParts.push('<style>');
            htmlParts.push('* { margin: 0; padding: 0; box-sizing: border-box; }');
            htmlParts.push('body { background: #1e1e1e; color: #d4d4d4; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; min-height: 100vh; display: flex; flex-direction: column; }');
            htmlParts.push('.header { background: #252526; padding: 12px 20px; border-bottom: 1px solid #3c3c3c; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }');
            htmlParts.push('.header h1 { font-size: 16px; font-weight: 500; color: #569cd6; }');
            htmlParts.push('.header-info { font-size: 12px; color: #808080; }');
            htmlParts.push('.header-info span { margin-left: 15px; padding: 3px 8px; background: #3c3c3c; border-radius: 3px; }');
            htmlParts.push('.controls { display: flex; gap: 10px; align-items: center; }');
            htmlParts.push('.controls button { background: #0e639c; color: white; border: none; padding: 6px 12px; border-radius: 3px; cursor: pointer; font-size: 12px; }');
            htmlParts.push('.controls button:hover { background: #1177bb; }');
            htmlParts.push('.controls button.secondary { background: #3c3c3c; }');
            htmlParts.push('.controls button.secondary:hover { background: #4c4c4c; }');
            htmlParts.push('.diagram-container { flex: 1; overflow: auto; padding: 20px; display: flex; justify-content: center; align-items: flex-start; }');
            htmlParts.push('.mermaid { background: #2d2d2d; padding: 20px; border-radius: 8px; min-width: 300px; }');
            htmlParts.push('.mermaid svg { max-width: 100%; height: auto; }');
            htmlParts.push('.zoom-controls { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 5px; background: #252526; padding: 8px; border-radius: 5px; border: 1px solid #3c3c3c; }');
            htmlParts.push('.zoom-controls button { width: 32px; height: 32px; background: #3c3c3c; border: none; color: white; border-radius: 3px; cursor: pointer; font-size: 16px; }');
            htmlParts.push('.zoom-controls button:hover { background: #4c4c4c; }');
            htmlParts.push('.zoom-level { padding: 0 10px; line-height: 32px; font-size: 12px; }');
            htmlParts.push('@media print { .header, .zoom-controls { display: none; } body { background: white; } .diagram-container { padding: 0; } .mermaid { background: white; } }');
            htmlParts.push('</style>');
            htmlParts.push('</head>');
            htmlParts.push('<body>');
            htmlParts.push('<div class="header">');
            htmlParts.push('<div>');
            htmlParts.push('<h1>TrueFlow Sequence Diagram</h1>');
            htmlParts.push('<div class="header-info">');
            htmlParts.push('<span id="diagram-type-label">Type: ' + (diagramType === 'mermaid' ? 'Mermaid' : 'PlantUML') + '</span>');
            htmlParts.push('<span id="dead-trees-label">' + (showingDeadTrees ? 'Including Dead Call Trees' : 'Runtime Calls Only') + '</span>');
            htmlParts.push('<span id="generated-label">Generated: ' + new Date().toLocaleString() + '</span>');
            htmlParts.push('</div>');
            htmlParts.push('</div>');
            htmlParts.push('<div class="controls">');
            htmlParts.push('<button onclick="window.print()" class="secondary">Print / Save PDF</button>');
            htmlParts.push('<button onclick="downloadSVG()">Download SVG</button>');
            htmlParts.push('</div>');
            htmlParts.push('</div>');
            htmlParts.push('<div class="diagram-container" id="diagram-container">');
            htmlParts.push('<div class="mermaid" id="mermaid-diagram">');
            htmlParts.push(code.replace(/</g, '&lt;').replace(/>/g, '&gt;'));
            htmlParts.push('</div>');
            htmlParts.push('</div>');
            htmlParts.push('<div class="zoom-controls">');
            htmlParts.push('<button onclick="zoomOut()">-</button>');
            htmlParts.push('<span class="zoom-level" id="zoom-level">100%</span>');
            htmlParts.push('<button onclick="zoomIn()">+</button>');
            htmlParts.push('<button onclick="resetZoom()">Reset</button>');
            htmlParts.push('</div>');
            htmlParts.push('<script>');
            htmlParts.push('var currentZoom = 1;');
            htmlParts.push('var container = document.getElementById("diagram-container");');
            htmlParts.push('var diagram = document.getElementById("mermaid-diagram");');
            htmlParts.push('mermaid.initialize({ startOnLoad: true, theme: "dark", securityLevel: "loose", sequence: { diagramMarginX: 50, diagramMarginY: 10, actorMargin: 50, width: 150, height: 65, boxMargin: 10, boxTextMargin: 5, noteMargin: 10, messageMargin: 35, mirrorActors: true, useMaxWidth: false } });');
            htmlParts.push('function zoomIn() { currentZoom = Math.min(currentZoom + 0.1, 3); applyZoom(); }');
            htmlParts.push('function zoomOut() { currentZoom = Math.max(currentZoom - 0.1, 0.3); applyZoom(); }');
            htmlParts.push('function resetZoom() { currentZoom = 1; applyZoom(); }');
            htmlParts.push('function applyZoom() { diagram.style.transform = "scale(" + currentZoom + ")"; diagram.style.transformOrigin = "top center"; document.getElementById("zoom-level").textContent = Math.round(currentZoom * 100) + "%"; }');
            htmlParts.push('function downloadSVG() { var svg = diagram.querySelector("svg"); if (!svg) { alert("No diagram rendered yet"); return; } var svgData = new XMLSerializer().serializeToString(svg); var blob = new Blob([svgData], { type: "image/svg+xml" }); var url = URL.createObjectURL(blob); var a = document.createElement("a"); a.href = url; a.download = "trueflow-sequence-diagram.svg"; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url); }');
            htmlParts.push('document.addEventListener("keydown", function(e) { if (e.key === "+" || e.key === "=") zoomIn(); if (e.key === "-") zoomOut(); if (e.key === "0") resetZoom(); if (e.key === "p" && e.ctrlKey) { e.preventDefault(); window.print(); } });');
            htmlParts.push('<\\/script>');
            htmlParts.push('</body>');
            htmlParts.push('</html>');
            var htmlContent = htmlParts.join('\\n');

            // Create a Blob and open in new tab
            var blob = new Blob([htmlContent], { type: 'text/html' });
            var blobUrl = URL.createObjectURL(blob);
            window.open(blobUrl, '_blank');

            // Clean up the URL after a short delay
            setTimeout(function() { URL.revokeObjectURL(blobUrl); }, 1000);

            vscode.postMessage({ type: 'info', message: 'Diagram opened in browser!' });
        }

        function toggleDeadCallTrees() {
            showDeadCallTrees = document.getElementById('show-dead-call-trees').checked;
            updateDiagramFromTrace();
        }

        // Generate diagram showing only active participants (with at least one call)
        // and optionally dead call trees from AST analysis
        function updateDiagramFromTrace() {
            if (callTrace.length === 0) {
                const noDataMessage = showDeadCallTrees
                    ? 'sequenceDiagram\\n    Note over System: No trace data yet.\\n    Note over System: Dead call trees will show AST-based uncalled functions.\\n    Note over System: Start a traced process to see live data.'
                    : 'sequenceDiagram\\n    Note over System: No trace data yet.\\n    Note over System: Start a traced Python process to see the diagram.\\n    Note over System: Enable Show Dead Call Trees for static analysis.';
                document.getElementById('diagram-code').value = noDataMessage;
                renderDiagram();
                return;
            }

            // Build participants only from modules that have actual calls
            const activeModules = new Set();
            const calls = [];

            for (const event of callTrace) {
                if (event.type === 'call') {
                    const module = event.module || '__main__';
                    activeModules.add(module);
                    calls.push(event);
                }
            }

            // Build the Mermaid sequence diagram
            let diagram = 'sequenceDiagram\\n';

            // Add only ACTIVE participants (modules with at least one call)
            for (const module of activeModules) {
                const safeName = module.replace(/[^a-zA-Z0-9_]/g, '_');
                diagram += '    participant ' + safeName + ' as ' + module + '\\n';
            }

            // Add calls between participants
            let prevModule = null;
            for (const event of calls.slice(-30)) { // Last 30 calls
                const module = (event.module || '__main__').replace(/[^a-zA-Z0-9_]/g, '_');
                const func = event.function || 'unknown';

                if (prevModule && prevModule !== module) {
                    diagram += '    ' + prevModule + '->>' + module + ': ' + func + '()\\n';
                } else if (prevModule === module) {
                    diagram += '    ' + module + '->>+' + module + ': ' + func + '()\\n';
                    diagram += '    ' + module + '-->>-' + module + ': return\\n';
                }
                prevModule = module;
            }

            // If showDeadCallTrees is enabled, add note about dead code
            if (showDeadCallTrees && allDefinedFunctions.size > 0) {
                const deadFunctions = [...allDefinedFunctions].filter(f => !activeParticipants.has(f));
                if (deadFunctions.length > 0) {
                    diagram += '    Note over System: Dead functions (never called):\\n';
                    for (const func of deadFunctions.slice(0, 10)) {
                        diagram += '    Note over System: - ' + func + '\\n';
                    }
                }
            }

            document.getElementById('diagram-code').value = diagram;
            renderDiagram();
        }

        function connectSocket() {
            vscode.postMessage({ type: 'connect' });
        }

        function manageFilters() {
            vscode.postMessage({ type: 'manageFilters' });
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

        // Dead Code list rendering with right-click context menu
        let activeContextMenu = null;
        function updateDeadCodeList() {
            const container = document.getElementById('deadcode-list');
            if (!container || !explorerData) return;

            const allFuncs = explorerData.functions || {};
            const deadSet = new Set(explorerData.deadFunctions || []);
            const coveredSet = new Set(explorerData.coveredFunctions || []);
            const whyNot = explorerData.whyNotCovered || {};

            // Combine dead + alive into a sorted list
            const rows = [];
            for (const [funcKey, info] of Object.entries(allFuncs)) {
                const isDead = deadSet.has(funcKey);
                const isAlive = coveredSet.has(funcKey);
                const status = isAlive ? 'ALIVE' : (isDead ? 'DEAD' : 'UNKNOWN');
                const parts = funcKey.split('.');
                const funcName = parts.pop() || funcKey;
                const moduleName = parts.join('.') || info.module || '';
                rows.push({
                    status: status,
                    module: moduleName,
                    function: funcName,
                    funcKey: funcKey,
                    file: info.file || '',
                    line: info.line || 0,
                    callCount: info.callCount || 0,
                    reason: whyNot[funcKey] ? whyNot[funcKey].reasons?.[0]?.explanation : ''
                });
            }

            if (rows.length === 0) {
                container.innerHTML = '<div class="placeholder"><p>Run your application with TrueFlow to detect uncovered functions.</p></div>';
                return;
            }

            // Sort: DEAD first, then by module
            rows.sort((a, b) => {
                if (a.status !== b.status) return a.status === 'DEAD' ? -1 : 1;
                return a.module.localeCompare(b.module) || a.function.localeCompare(b.function);
            });

            // Update dead count stat
            const deadCountEl = document.getElementById('dead-count');
            if (deadCountEl) deadCountEl.textContent = String(rows.filter(r => r.status === 'DEAD').length);

            // Build table
            let html = '<table class="data-table" style="width:100%;">';
            html += '<thead><tr>';
            html += '<th style="width:70px;">Status</th>';
            html += '<th>Module</th>';
            html += '<th>Function</th>';
            html += '<th>File:Line</th>';
            html += '<th style="width:60px;">Calls</th>';
            html += '</tr></thead><tbody>';

            rows.forEach(row => {
                const statusColor = row.status === 'ALIVE' ? '#4ade80' : (row.status === 'DEAD' ? '#f87171' : '#888');
                const statusBg = row.status === 'ALIVE' ? 'rgba(74,222,128,0.15)' : (row.status === 'DEAD' ? 'rgba(248,113,113,0.15)' : 'rgba(136,136,136,0.1)');
                const fileLine = row.file ? (row.file + ':' + row.line) : '';
                html += '<tr class="deadcode-row" data-funckey="' + escapeHtml(row.funcKey) + '" data-module="' + escapeHtml(row.module) + '" data-function="' + escapeHtml(row.function) + '" data-file="' + escapeHtml(row.file) + '" data-line="' + row.line + '" title="' + escapeHtml(row.reason || '') + '">';
                html += '<td><span style="padding:2px 6px;border-radius:4px;font-size:10px;background:' + statusBg + ';color:' + statusColor + ';">' + row.status + '</span></td>';
                html += '<td style="font-size:11px;color:#888;">' + escapeHtml(row.module) + '</td>';
                html += '<td style="font-weight:500;">' + escapeHtml(row.function) + '</td>';
                html += '<td style="font-size:11px;color:#888;">' + escapeHtml(fileLine) + '</td>';
                html += '<td style="text-align:center;">' + row.callCount + '</td>';
                html += '</tr>';
            });

            html += '</tbody></table>';
            container.innerHTML = html;

            // Attach right-click context menu to each row
            container.querySelectorAll('.deadcode-row').forEach(rowEl => {
                rowEl.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showDeadCodeContextMenu(e, rowEl.dataset);
                });
            });
        }

        function showDeadCodeContextMenu(e, data) {
            // Remove existing context menu if any
            if (activeContextMenu) {
                activeContextMenu.remove();
                activeContextMenu = null;
            }

            const menu = document.createElement('div');
            menu.style.cssText = 'position:fixed;z-index:10000;background:var(--vscode-menu-background,#252526);border:1px solid var(--vscode-menu-border,#454545);border-radius:4px;padding:4px 0;box-shadow:0 4px 12px rgba(0,0,0,0.5);min-width:180px;font-size:12px;';

            // Expose as MCP Tool
            const exposeItem = document.createElement('div');
            exposeItem.textContent = 'Expose as MCP Tool';
            exposeItem.style.cssText = 'padding:6px 20px;cursor:pointer;color:var(--vscode-menu-foreground,#ccc);';
            exposeItem.addEventListener('mouseenter', () => { exposeItem.style.background = 'var(--vscode-menu-selectionBackground,#094771)'; });
            exposeItem.addEventListener('mouseleave', () => { exposeItem.style.background = ''; });
            exposeItem.addEventListener('click', () => {
                vscode.postMessage({
                    type: 'exposeMCPTool',
                    data: {
                        function_name: data.function,
                        module: data.module,
                        file: data.file,
                        line: parseInt(data.line) || 0
                    }
                });
                menu.remove();
                activeContextMenu = null;
            });
            menu.appendChild(exposeItem);

            // Separator
            const sep = document.createElement('div');
            sep.style.cssText = 'height:1px;background:var(--vscode-menu-separatorBackground,#454545);margin:4px 0;';
            menu.appendChild(sep);

            // Copy function name
            const copyItem = document.createElement('div');
            copyItem.textContent = 'Copy Function Name';
            copyItem.style.cssText = 'padding:6px 20px;cursor:pointer;color:var(--vscode-menu-foreground,#ccc);';
            copyItem.addEventListener('mouseenter', () => { copyItem.style.background = 'var(--vscode-menu-selectionBackground,#094771)'; });
            copyItem.addEventListener('mouseleave', () => { copyItem.style.background = ''; });
            copyItem.addEventListener('click', () => {
                navigator.clipboard.writeText(data.funckey || (data.module + '.' + data.function));
                menu.remove();
                activeContextMenu = null;
            });
            menu.appendChild(copyItem);

            // Position menu
            menu.style.left = e.clientX + 'px';
            menu.style.top = e.clientY + 'px';
            document.body.appendChild(menu);
            activeContextMenu = menu;

            // Close on click outside
            const closeHandler = (ev) => {
                if (!menu.contains(ev.target)) {
                    menu.remove();
                    activeContextMenu = null;
                    document.removeEventListener('click', closeHandler);
                }
            };
            setTimeout(() => document.addEventListener('click', closeHandler), 10);
        }

        // Protocol data tracking
        let sqlQueryCount = 0;
        const sqlCallers = new Map();
        const distributedEvents = [];

        function updateProtocolData(event) {
            const summary = event.protocol_summary || {};
            const details = event.protocol_details || {};
            const funcKey = event.module + '.' + event.function;

            // Update SQL tab
            if (summary.sql) {
                sqlQueryCount += summary.sql;
                sqlCallers.set(funcKey, (sqlCallers.get(funcKey) || 0) + summary.sql);

                const sqlContainer = document.getElementById('sql-queries');
                if (sqlContainer) {
                    // Build live SQL view
                    let html = '<div class="sql-stats">' +
                        '<strong>Live SQL:</strong> ' + sqlQueryCount + ' queries from ' +
                        sqlCallers.size + ' callers</div>';

                    // Show callers with high query counts (potential N+1)
                    const sortedCallers = Array.from(sqlCallers.entries())
                        .sort((a, b) => b[1] - a[1]);

                    html += '<table class="perf-table"><tr><th>Function</th><th>Queries</th><th>Detail</th></tr>';
                    for (const [caller, count] of sortedCallers.slice(0, 20)) {
                        const warning = count >= 10 ? ' sql-warning' : (count >= 5 ? ' sql-error' : '');
                        html += '<tr class="' + warning + '"><td>' + escapeHtml(caller) +
                            '</td><td>' + count + '</td><td>' +
                            escapeHtml((details.sql || '').substring(0, 80)) + '</td></tr>';
                    }
                    html += '</table>';
                    sqlContainer.innerHTML = html;
                }
            }

            // Update distributed tab
            for (const proto of ['websocket', 'webrtc', 'mcp', 'agent', 'process',
                                  'grpc', 'graphql', 'mqtt', 'amqp', 'kafka', 'redis']) {
                if (summary[proto]) {
                    distributedEvents.push({
                        protocol: proto,
                        module: event.module,
                        function: event.function,
                        count: summary[proto],
                        detail: details[proto] || funcKey + '()',
                        timestamp: event.timestamp
                    });
                }
            }

            // Update distributed section if we have events
            if (distributedEvents.length > 0) {
                const distContainer = document.getElementById('distributed-content');
                if (distContainer) {
                    const recentEvents = distributedEvents.slice(-50);
                    let html = '<div><strong>Live Distributed Events:</strong> ' +
                        distributedEvents.length + ' total</div>';
                    html += '<table class="perf-table"><tr><th>Protocol</th><th>Function</th>' +
                        '<th>Count</th><th>Detail</th></tr>';
                    for (const evt of recentEvents.reverse()) {
                        html += '<tr><td>' + evt.protocol.toUpperCase() + '</td><td>' +
                            escapeHtml(evt.module + '.' + evt.function) + '</td><td>' +
                            evt.count + '</td><td>' +
                            escapeHtml(evt.detail.substring(0, 80)) + '</td></tr>';
                    }
                    html += '</table>';
                    // Update the distributed content area
                    const existing = distContainer.querySelector('.live-distributed');
                    if (existing) {
                        existing.innerHTML = html;
                    } else {
                        const div = document.createElement('div');
                        div.className = 'live-distributed';
                        div.innerHTML = html;
                        distContainer.prepend(div);
                    }
                }
            }
        }

        // Handle messages from extension
        window.addEventListener('message', event => {
            const message = event.data;

            switch (message.type) {
                case 'socketConnected':
                    document.getElementById('connection-status').textContent = 'Attached';
                    document.getElementById('connection-status').className = 'status-badge status-connected';
                    break;

                case 'socketDisconnected':
                    document.getElementById('connection-status').textContent = 'Detached';
                    document.getElementById('connection-status').className = 'status-badge status-disconnected';
                    break;

                case 'updateFilters':
                    document.getElementById('filter-stats').textContent = 'Filters: ' + (message.stats || 'None');
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

                    // Track active participants (modules with calls)
                    if (message.event.type === 'call' && message.event.module) {
                        activeParticipants.add(message.event.module + '.' + message.event.function);
                    }

                    // Add to call trace
                    callTrace.push(message.event);
                    if (callTrace.length > 1000) callTrace.shift();
                    updateCallTrace(callTrace);

                    // Handle protocol detections from return events
                    if (message.event.protocol_summary) {
                        updateProtocolData(message.event);
                    }

                    // Update diagram with active participants only (throttled)
                    if (eventCount % 10 === 0) {
                        updateDiagramFromTrace();
                    }
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

                case 'functionRegistry':
                    // Receive function registry for dead code detection
                    if (message.data && message.data.functions) {
                        functionRegistryData.clear();
                        message.data.functions.forEach(func => {
                            const key = func.module + '.' + func.function;
                            functionRegistryData.set(key, { file: func.file, line: func.line });
                            allDefinedFunctions.add(key);
                        });
                        console.log('[TrueFlow] Received function registry:', functionRegistryData.size, 'functions');
                        refreshInteractiveExplorer();
                    }
                    break;

                case 'branchRegistry':
                    // Receive branch registry for "Why Not Covered" with actual conditions
                    if (message.data) {
                        callSitesData = (message.data.call_sites || []).map(site => ({
                            callee: site.callee,
                            caller: site.caller,
                            callerModule: site.caller_module,
                            file: site.file,
                            line: site.line,
                            inBranch: site.in_branch ? {
                                type: site.in_branch.type,
                                condition: site.in_branch.condition,
                                line: site.in_branch.line,
                                endLine: site.in_branch.end_line
                            } : null
                        }));
                        functionBranchesData.clear();
                        const funcBranches = message.data.function_branches || {};
                        for (const [funcKey, data] of Object.entries(funcBranches)) {
                            functionBranchesData.set(funcKey, data.branches || []);
                        }
                        // Store resolved call graph for cross-class connection visualization
                        resolvedCallGraphData = message.data.resolved_call_graph || {};
                        classAttributesData = message.data.class_attributes || {};
                        console.log('[TrueFlow] Received branch registry:', callSitesData.length, 'call sites,',
                            Object.keys(resolvedCallGraphData).length, 'resolved call graph entries');
                        refreshInteractiveExplorer();
                    }
                    break;

                case 'selectTab':
                    // Programmatically select a tab
                    const targetTab = message.tab;
                    if (targetTab) {
                        // Deselect all tabs
                        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                        document.querySelectorAll('.content').forEach(c => c.classList.remove('active'));

                        // Select the target tab
                        const tabEl = document.querySelector('.tab[data-tab="' + targetTab + '"]');
                        const contentEl = document.getElementById(targetTab + '-content');
                        if (tabEl) tabEl.classList.add('active');
                        if (contentEl) contentEl.classList.add('active');

                        // Show zoom controls only for diagram tab
                        document.getElementById('zoom-controls').classList.toggle('visible', targetTab === 'diagram');
                    }
                    break;

                case 'explorerHtml':
                    // Received Three.js HTML for iframe embedding
                    if (message.html && typeof handleExplorerHtmlResponse === 'function') {
                        handleExplorerHtmlResponse(message.html);
                    }
                    break;

                case 'liveServerStatus':
                    // Update the live server button state
                    if (typeof updateLiveServerButton === 'function') {
                        updateLiveServerButton(message.isRunning, message.url);
                    }
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

// === Server Auto-Detection ===

function startServerDetection(context: vscode.ExtensionContext): void {
    // Check immediately on start
    checkForTraceServer();

    // Then check periodically
    serverDetectionInterval = setInterval(() => {
        checkForTraceServer();
    }, SERVER_DETECTION_INTERVAL_MS);

    context.subscriptions.push({
        dispose: () => {
            if (serverDetectionInterval) {
                clearInterval(serverDetectionInterval);
            }
        }
    });
}

async function checkForTraceServer(): Promise<void> {
    // Check MCP Hub status (WebSocket on port 5680) + AI server (llama.cpp on port 8080)
    let hubConnected = false;
    try { hubConnected = HubClient.getInstance().isConnected(); } catch (_) { /* not initialized */ }
    const hubPortUp = hubConnected ? true : await isPortListening('127.0.0.1', 5680);
    const aiPort = 8080;
    const aiAvailable = await isPortListening('127.0.0.1', aiPort);

    if (hubConnected && aiAvailable) {
        mcpStatusBarItem.text = '$(circle-filled) MCP  $(circle-filled) AI';
        mcpStatusBarItem.tooltip = `MCP Hub connected (ws://127.0.0.1:5680) | AI server running on port ${aiPort}`;
        mcpStatusBarItem.backgroundColor = undefined;
    } else if (hubConnected && !aiAvailable) {
        mcpStatusBarItem.text = '$(circle-filled) MCP  $(circle-outline) AI';
        mcpStatusBarItem.tooltip = `MCP Hub connected (ws://127.0.0.1:5680) | AI server offline - start llama.cpp on port ${aiPort}`;
        mcpStatusBarItem.backgroundColor = undefined;
    } else if (hubPortUp && !hubConnected) {
        mcpStatusBarItem.text = '$(circle-slash) MCP  $(circle-${aiAvailable ? "filled" : "outline"}) AI';
        mcpStatusBarItem.tooltip = 'MCP Hub running but not connected (ws://127.0.0.1:5680) - reconnecting...';
        mcpStatusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        // Auto-reconnect: hub port is up but HubClient is disconnected (debounced)
        tryEnsureHubRunning('Hub port up but WebSocket disconnected');
    } else if (!hubConnected && !hubPortUp && traceSocketClient?.isConnected()) {
        // Hub is completely down but trace server is active - restart hub (debounced)
        mcpStatusBarItem.text = '$(circle-outline) MCP  $(circle-${aiAvailable ? "filled" : "outline"}) AI';
        mcpStatusBarItem.tooltip = 'MCP Hub offline - restarting...';
        mcpStatusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        tryEnsureHubRunning('Hub down but trace server active');
    } else if (!hubConnected && aiAvailable) {
        mcpStatusBarItem.text = '$(circle-outline) MCP  $(circle-filled) AI';
        mcpStatusBarItem.tooltip = `MCP Hub offline | AI server running on port ${aiPort}`;
        mcpStatusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    } else {
        mcpStatusBarItem.text = '$(circle-outline) MCP  $(circle-outline) AI';
        mcpStatusBarItem.tooltip = 'MCP Hub offline (ws://127.0.0.1:5680) | AI server offline (port 8080)';
        mcpStatusBarItem.backgroundColor = undefined;
    }

    // Update AI availability for explanation cache
    explorerServer?.setAIAvailable(aiAvailable);

    // Check if we should pulse for auto-integrate (Python running without tracing)
    const isIntegrated = isProjectAlreadyIntegrated();
    const shouldPulse = activeProcessesWithoutTracing.size > 0 && !isIntegrated;
    updateStatusBarPulse(shouldPulse);

    // Don't check if already connected
    if (traceSocketClient?.isConnected()) {
        return;
    }

    const port = 5678;  // Default TrueFlow port
    const isAvailable = await isPortListening('127.0.0.1', port);

    if (isAvailable) {
        consecutiveServerMisses = 0;

        // DOWN -> UP transition => new epoch
        const wasUp = serverIsUp;
        serverIsUp = true;
        if (!wasUp) {
            serverNotificationShown = false;
        }

        const now = Date.now();
        const portChanged = lastServerDetectedPort !== port;
        const cooldownPassed = (now - lastServerNotificationTime) >= SERVER_NOTIFICATION_COOLDOWN_MS;
        const wasShown = serverNotificationShown;
        serverNotificationShown = true; // Mark as shown immediately

        const firstTimeForThisDetection = portChanged || !wasShown;

        if (firstTimeForThisDetection && cooldownPassed) {
            lastServerDetectedPort = port;
            lastServerNotificationTime = now;
            showServerDetectedNotification(port);
        } else {
            lastServerDetectedPort = port;
        }
    } else {
        consecutiveServerMisses++;
        if (consecutiveServerMisses >= MISSES_TO_RESET) {
            serverIsUp = false;
            if (lastServerDetectedPort === port) {
                lastServerDetectedPort = 0;
            }
        }
    }
}

let pulsePhase = 0;
function updateStatusBarPulse(shouldPulse: boolean): void {
    if (shouldPulse && !statusBarPulseInterval) {
        // Start pulsing
        pulsePhase = 0;
        statusBarPulseInterval = setInterval(() => {
            pulsePhase = (pulsePhase + 1) % 4;
            const icons = ['$(circle-outline)', '$(circle-small)', '$(circle-filled)', '$(circle-small)'];
            statusBarItem.text = `${icons[pulsePhase]} TrueFlow - Setup Required`;
            statusBarItem.tooltip = 'Python process running without TrueFlow tracing. Click to auto-integrate.';
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        }, 500);
    } else if (!shouldPulse && statusBarPulseInterval) {
        // Stop pulsing
        clearInterval(statusBarPulseInterval);
        statusBarPulseInterval = undefined;
        if (!traceSocketClient?.isConnected()) {
            statusBarItem.text = '$(debug-disconnect) TrueFlow';
            statusBarItem.tooltip = 'TrueFlow: Click to connect to trace server';
            statusBarItem.backgroundColor = undefined;
        }
    }
}

function isPortListening(host: string, port: number): Promise<boolean> {
    return new Promise((resolve) => {
        const socket = new net.Socket();

        socket.setTimeout(1000);

        socket.on('connect', () => {
            socket.destroy();
            resolve(true);
        });

        socket.on('timeout', () => {
            socket.destroy();
            resolve(false);
        });

        socket.on('error', () => {
            socket.destroy();
            resolve(false);
        });

        socket.connect(port, host);
    });
}

function showServerDetectedNotification(port: number): void {
    const message = `TrueFlow trace server detected on port ${port}. Connect to start receiving traces.`;

    vscode.window.showInformationMessage(message, 'Connect Now', 'Ignore').then(selection => {
        if (selection === 'Connect Now') {
            connectToSocket(port);  // Pass detected port directly
        }
    });

    // Also update status bar to flash
    const originalText = statusBarItem.text;
    statusBarItem.text = '$(zap) Server Detected!';
    statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');

    setTimeout(() => {
        if (!traceSocketClient?.isConnected()) {
            statusBarItem.text = originalText;
            statusBarItem.backgroundColor = undefined;
        }
    }, 3000);
}

// === Task/Run Detection ===

function setupTaskDetection(context: vscode.ExtensionContext): void {
    // Listen for task executions
    context.subscriptions.push(
        vscode.tasks.onDidStartTask(event => {
            checkTaskForTracing(event.execution.task);
        })
    );

    // Listen for task end to remove from active processes
    context.subscriptions.push(
        vscode.tasks.onDidEndTask(event => {
            const taskId = `task:${event.execution.task.name}`;
            activeProcessesWithoutTracing.delete(taskId);
        })
    );

    // Listen for debug sessions
    context.subscriptions.push(
        vscode.debug.onDidStartDebugSession(session => {
            checkDebugSessionForTracing(session);
        })
    );

    // Listen for debug session end to remove from active processes
    context.subscriptions.push(
        vscode.debug.onDidTerminateDebugSession(session => {
            const sessionId = `debug:${session.id}`;
            activeProcessesWithoutTracing.delete(sessionId);
        })
    );

    // Listen for terminal creation (catches manual runs)
    context.subscriptions.push(
        vscode.window.onDidOpenTerminal(terminal => {
            // We can't easily inspect terminal commands, but we can prompt
            // for projects that aren't integrated
            checkProjectIntegration();
        })
    );
}

function checkTaskForTracing(task: vscode.Task): void {
    // Check if this is a supported task type
    // TrueFlow supports Python, Java, and Kotlin
    const taskDef = task.definition;
    const taskType = taskDef.type?.toLowerCase() || '';
    const taskName = task.name.toLowerCase();

    // Python support
    const isPythonTask = taskType.includes('python') ||
                        taskName.endsWith('.py') ||
                        taskType.includes('pytest') ||
                        taskType.includes('django') ||
                        taskType.includes('flask');

    // Java/Kotlin support
    const isJvmTask = taskType.includes('java') ||
                     taskType.includes('kotlin') ||
                     taskType.includes('gradle') ||
                     taskType.includes('maven') ||
                     taskName.endsWith('.java') ||
                     taskName.endsWith('.kt');

    if (!isPythonTask && !isJvmTask) return;

    // Check if tracing is enabled (look for env vars in task definition)
    const hasTracing = checkTaskHasTracing(task);

    // Track process for pulsing status bar
    const taskId = `task:${task.name}`;
    if (!hasTracing) {
        activeProcessesWithoutTracing.add(taskId);
    } else {
        activeProcessesWithoutTracing.delete(taskId);
    }

    if (taskDetectionDisabled) return;

    const now = Date.now();
    if (now - lastTaskNotificationTime < TASK_NOTIFICATION_COOLDOWN_MS) return;

    if (hasTracing) return;

    // Show notification
    lastTaskNotificationTime = now;
    showTaskTracingNotification(task.name);
}

function checkTaskHasTracing(task: vscode.Task): boolean {
    const taskDef = task.definition as any;

    // Check for TrueFlow environment variables (Python and general)
    const envMarkers = [
        'PYCHARM_PLUGIN_TRACE_ENABLED',
        'TRUEFLOW_TRACE_ENABLED',
        'CRAWL4AI_TRACE',
        'TRUEFLOW_JAVA_AGENT'
    ];

    if (taskDef.env) {
        for (const marker of envMarkers) {
            if (taskDef.env[marker]) return true;
        }
    }

    // Check options.env
    if (taskDef.options?.env) {
        for (const marker of envMarkers) {
            if (taskDef.options.env[marker]) return true;
        }
    }

    // Check for Java agent in args/vmArgs
    const args = taskDef.args?.join(' ') || '';
    const vmArgs = taskDef.vmArgs?.join(' ') || '';
    const allArgs = `${args} ${vmArgs}`.toLowerCase();

    if (allArgs.includes('-javaagent:') && allArgs.includes('trueflow')) {
        return true;
    }
    if (allArgs.includes('-dtrueflow.enabled=true')) {
        return true;
    }

    return false;
}

function checkDebugSessionForTracing(session: vscode.DebugSession): void {
    // Check supported debug types (Python and JVM)
    const debugType = session.type.toLowerCase();
    const supportedTypes = ['python', 'debugpy', 'java', 'kotlin'];

    if (!supportedTypes.some(t => debugType.includes(t))) return;

    // Check if this is a TrueFlow-enabled launch config
    const config = session.configuration;

    // Check env variables
    const hasEnvTracing = config.env?.PYCHARM_PLUGIN_TRACE_ENABLED ||
                         config.env?.TRUEFLOW_TRACE_ENABLED ||
                         config.env?.TRUEFLOW_JAVA_AGENT;

    // Check for [TrueFlow] in name
    const hasNameMarker = config.name?.includes('[TrueFlow]');

    // Check for Java agent in vmArgs
    const vmArgs = (config.vmArgs || []).join(' ').toLowerCase();
    const hasJavaAgent = vmArgs.includes('-javaagent:') && vmArgs.includes('trueflow');

    const hasTracing = hasEnvTracing || hasNameMarker || hasJavaAgent;

    // Track process for pulsing status bar
    const sessionId = `debug:${session.id}`;
    if (!hasTracing) {
        activeProcessesWithoutTracing.add(sessionId);
    } else {
        activeProcessesWithoutTracing.delete(sessionId);
    }

    if (taskDetectionDisabled) return;

    const now = Date.now();
    if (now - lastTaskNotificationTime < TASK_NOTIFICATION_COOLDOWN_MS) return;

    if (hasTracing) return;

    // Show notification
    lastTaskNotificationTime = now;
    showTaskTracingNotification(session.name);
}

function checkProjectIntegration(): void {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) return;

    const pluginDir = path.join(workspaceFolder.uri.fsPath, '.pycharm_plugin');
    const trueflowDir = path.join(workspaceFolder.uri.fsPath, '.trueflow');

    if (fs.existsSync(pluginDir) || fs.existsSync(trueflowDir)) return;

    // Project not integrated - could show a subtle hint
    // But don't spam the user
}

function showTaskTracingNotification(taskName: string): void {
    const message = `Running '${taskName}' without TrueFlow tracing. Enable tracing to visualize execution flow.`;

    vscode.window.showInformationMessage(message, 'Auto-Integrate', "Don't Ask Again", 'Ignore').then(selection => {
        if (selection === 'Auto-Integrate') {
            vscode.commands.executeCommand('trueflow.autoIntegrate');
        } else if (selection === "Don't Ask Again") {
            taskDetectionDisabled = true;
        }
    });
}

export function deactivate() {
    // Stop server detection
    if (serverDetectionInterval) {
        clearInterval(serverDetectionInterval);
    }

    // Stop status bar pulse animation
    if (statusBarPulseInterval) {
        clearInterval(statusBarPulseInterval);
    }

    if (traceViewerPanel) {
        traceViewerPanel.dispose();
    }
    if (traceSocketClient) {
        traceSocketClient.disconnect();
    }
    if (llmServerProcess) {
        llmServerProcess.kill();
    }
    // Stop the interactive explorer live server
    if (explorerServer) {
        explorerServer.stop();
        explorerServer = undefined;
    }
}
