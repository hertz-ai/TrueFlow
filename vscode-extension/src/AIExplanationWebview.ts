import * as vscode from 'vscode';
import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import * as child_process from 'child_process';
import { HubClient } from './HubClient';

/**
 * AI Explanation Webview - Interactive chat interface with local VLM (Qwen3-VL).
 *
 * Features:
 * - Chat interface with conversation history (last 3 exchanges)
 * - Image/screenshot support for visual queries
 * - Cross-tab context injection (dead code, performance, call traces)
 * - Public API for other panels to invoke explanations programmatically
 */

interface ModelPreset {
    displayName: string;
    repoId: string;
    fileName: string;
    sizeMB: number;
    description: string;
    hasVision: boolean;
    // Vision models require a multimodal projector (mmproj) file
    mmprojRepoId?: string;
    mmprojFileName?: string;
    mmprojSizeMB?: number;
}

interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
    imageBase64?: string;
    timestamp: string;
}

const MODEL_PRESETS: ModelPreset[] = [
    // Qwen3-VL models - excellent for code analysis
    {
        displayName: "Qwen3-VL-2B Instruct Q4_K_XL (Recommended)",
        repoId: "unsloth/Qwen3-VL-2B-Instruct-GGUF",
        fileName: "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 1500,
        description: "Vision+text, best for code analysis with diagrams",
        hasVision: true
    },
    {
        displayName: "Qwen3-VL-2B Thinking Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-2B-Thinking-GGUF",
        fileName: "Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf",
        sizeMB: 1500,
        description: "Vision+text with chain-of-thought reasoning",
        hasVision: true
    },
    {
        displayName: "Qwen3-VL-4B Instruct Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-4B-Instruct-GGUF",
        fileName: "Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 2800,
        description: "Larger model, better quality, needs ~6GB RAM",
        hasVision: true
    },
    // Gemma 3 models - Google's multimodal
    {
        displayName: "Gemma-3-4B IT Q4_K_XL",
        repoId: "unsloth/gemma-3-4b-it-GGUF",
        fileName: "gemma-3-4b-it-Q4_K_XL.gguf",
        sizeMB: 2700,
        description: "Vision+text, Google Gemma 3, well-tested multimodal",
        hasVision: true
    },
    {
        displayName: "Gemma-3-1B IT Q4_K_M",
        repoId: "unsloth/gemma-3-1b-it-GGUF",
        fileName: "gemma-3-1b-it-Q4_K_M.gguf",
        sizeMB: 600,
        description: "Vision+text, compact & fast, good for quick analysis",
        hasVision: true
    },
    // SmolVLM - ultra-compact vision model
    {
        displayName: "SmolVLM-256M-Instruct",
        repoId: "ggml-org/SmolVLM-256M-Instruct-GGUF",
        fileName: "SmolVLM-256M-Instruct-Q8_0.gguf",
        sizeMB: 280,
        description: "Tiny vision model, ultra-fast, basic image analysis",
        hasVision: true
    },
    // Text-only option
    {
        displayName: "Qwen3-2B Text-Only Q4_K_M",
        repoId: "unsloth/Qwen3-2B-Instruct-GGUF",
        fileName: "Qwen3-2B-Instruct-Q4_K_M.gguf",
        sizeMB: 1100,
        description: "Text-only, fastest, no vision support",
        hasVision: false
    }
];

// Shared server status file for cross-IDE coordination
interface ServerStatus {
    running: boolean;
    pid?: number;
    port: number;
    model?: string;
    startedBy: string;  // 'vscode' or 'pycharm'
    startedAt: string;
}

export class AIExplanationProvider {
    private static instance: AIExplanationProvider;
    private panel: vscode.WebviewPanel | undefined;
    private conversationHistory: ChatMessage[] = [];
    private maxHistorySize = 3;
    private serverProcess: child_process.ChildProcess | undefined;
    private currentModelFile: string | undefined;
    private currentModelHasVision = true;
    private statusCheckInterval: NodeJS.Timeout | undefined;
    private hubClient: HubClient;

    // Cross-tab context
    private deadCodeData: any = null;
    private performanceData: any = null;
    private callTraceData: any = null;
    private diagramData: string = '';

    private readonly modelsDir: string;
    private readonly apiBase = 'http://127.0.0.1:8080/v1';
    private readonly serverStatusFile: string;

    private constructor() {
        this.modelsDir = path.join(this.getHomeDir(), '.trueflow', 'models');
        this.serverStatusFile = path.join(this.getHomeDir(), '.trueflow', 'server_status.json');
        if (!fs.existsSync(this.modelsDir)) {
            fs.mkdirSync(this.modelsDir, { recursive: true });
        }

        // Initialize hub client
        this.hubClient = HubClient.getInstance();
        this.setupHubHandlers();
    }

    private setupHubHandlers(): void {
        // Handle AI server status updates from other IDEs
        this.hubClient.on('ai_server_status', (message) => {
            const data = message.data;
            if (data.running && !this.serverProcess) {
                // Server started by another IDE
                this.postMessage({
                    command: 'externalServerRunning',
                    startedBy: data.started_by || 'external',
                    model: data.model || 'unknown'
                });
            } else if (!data.running) {
                // Server stopped
                this.postMessage({ command: 'serverStopped' });
            }
        });

        // Handle legacy commands from MCP Hub
        this.hubClient.on('command', async (message) => {
            const command = message.command;

            switch (command) {
                case 'start_ai_server':
                    await this.startServer();
                    break;
                case 'stop_ai_server':
                    this.stopServer();
                    break;
            }
        });

        // Handle RPC requests from MCP Hub (with response)
        this.hubClient.on('rpc_request', (message: any) => {
            const requestId = message.request_id;
            const command = message.command;
            const args = message.args || {};

            let responseData: any = {};

            switch (command) {
                case 'get_trace_data':
                    responseData = {
                        calls: this.callTraceData?.calls || [],
                        total_calls: this.callTraceData?.total_calls || 0
                    };
                    break;

                case 'get_dead_code':
                    responseData = {
                        dead_functions: this.deadCodeData?.dead_functions || [],
                        called_functions: this.deadCodeData?.called_functions || []
                    };
                    break;

                case 'get_performance_data':
                    responseData = {
                        hotspots: this.performanceData?.hotspots || [],
                        total_time_ms: this.performanceData?.total_time_ms || 0
                    };
                    break;

                case 'export_diagram':
                    responseData = {
                        format: args.format || 'plantuml',
                        diagram: this.diagramData || ''
                    };
                    break;

                case 'start_ai_server':
                    this.startServer().then(() => {
                        this.hubClient.sendRpcResponse(requestId, {
                            status: 'started',
                            port: 8080
                        });
                    });
                    return; // Don't send response yet

                case 'stop_ai_server':
                    this.stopServer();
                    responseData = { status: 'stopped' };
                    break;

                default:
                    responseData = { error: `Unknown command: ${command}` };
            }

            // Send RPC response back to hub
            this.hubClient.sendRpcResponse(requestId, responseData);
        });
    }

    // Read shared server status (written by any IDE)
    private readServerStatus(): ServerStatus | null {
        try {
            if (fs.existsSync(this.serverStatusFile)) {
                const content = fs.readFileSync(this.serverStatusFile, 'utf-8');
                return JSON.parse(content) as ServerStatus;
            }
        } catch (e) {
            console.error('[TrueFlow] Failed to read server status:', e);
        }
        return null;
    }

    // Write shared server status
    private writeServerStatus(status: ServerStatus | null): void {
        try {
            if (status === null) {
                if (fs.existsSync(this.serverStatusFile)) {
                    fs.unlinkSync(this.serverStatusFile);
                }
            } else {
                fs.writeFileSync(this.serverStatusFile, JSON.stringify(status, null, 2));
            }
        } catch (e) {
            console.error('[TrueFlow] Failed to write server status:', e);
        }
    }

    // Check if server is running (by any IDE)
    private async isServerRunningAnywhere(): Promise<boolean> {
        // First check the status file
        const status = this.readServerStatus();
        if (status?.running) {
            // Verify the server is actually responding
            try {
                const healthy = await this.checkServerHealth();
                if (healthy) {
                    return true;
                }
                // Status file says running but server not responding - clean up
                this.writeServerStatus(null);
            } catch {
                this.writeServerStatus(null);
            }
        }

        // Also try direct health check in case status file is stale
        try {
            return await this.checkServerHealth();
        } catch {
            return false;
        }
    }

    // Start polling for server status changes
    private startStatusPolling(): void {
        if (this.statusCheckInterval) {
            return;
        }

        this.statusCheckInterval = setInterval(async () => {
            const status = this.readServerStatus();
            const isRunning = await this.isServerRunningAnywhere();

            // Update UI based on server state
            if (isRunning && !this.serverProcess) {
                // Server is running but not started by us
                this.postMessage({
                    command: 'externalServerRunning',
                    startedBy: status?.startedBy || 'external',
                    model: status?.model || 'unknown'
                });
            } else if (!isRunning && this.serverProcess) {
                // Our server died unexpectedly
                this.serverProcess = undefined;
                this.postMessage({ command: 'serverStopped' });
            }
        }, 2000);  // Check every 2 seconds
    }

    private stopStatusPolling(): void {
        if (this.statusCheckInterval) {
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = undefined;
        }
    }

    public static getInstance(): AIExplanationProvider {
        if (!AIExplanationProvider.instance) {
            AIExplanationProvider.instance = new AIExplanationProvider();
        }
        return AIExplanationProvider.instance;
    }

    public show(context: vscode.ExtensionContext): void {
        if (this.panel) {
            this.panel.reveal();
            return;
        }

        // Use ViewColumn.Beside to add to existing editor group, or Active if there's already content
        // This prevents creating unnecessary new editor groups
        const viewColumn = vscode.window.activeTextEditor?.viewColumn === vscode.ViewColumn.One
            ? vscode.ViewColumn.Beside
            : vscode.ViewColumn.Active;

        this.panel = vscode.window.createWebviewPanel(
            'trueflowAI',
            'TrueFlow AI Assistant',
            { viewColumn, preserveFocus: false },
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        this.panel.webview.html = this.getWebviewContent();
        this.setupMessageHandlers();

        this.panel.onDidDispose(() => {
            this.panel = undefined;
            this.stopStatusPolling();
        });

        // Connect to MCP Hub for real-time cross-IDE coordination
        this.hubClient.connect().then(connected => {
            if (connected) {
                console.log('[TrueFlow] Connected to MCP Hub for cross-IDE coordination');
            } else {
                console.log('[TrueFlow] Hub not available, using file-based status polling');
                // Fall back to polling if hub not available
                this.startStatusPolling();
            }
        });

        // Check initial model status
        this.checkModelStatus();
    }

    private setupMessageHandlers(): void {
        if (!this.panel) return;

        this.panel.webview.onDidReceiveMessage(async (message) => {
            switch (message.command) {
                case 'sendMessage':
                    await this.handleUserMessage(message.text, message.imageBase64, message.contextType);
                    break;
                case 'downloadModel':
                    await this.downloadModel(message.modelIndex);
                    break;
                case 'startServer':
                    await this.startServer();
                    break;
                case 'stopServer':
                    this.stopServer();
                    break;
                case 'clearHistory':
                    this.conversationHistory = [];
                    this.postMessage({ command: 'historyCleared' });
                    break;
                case 'checkStatus':
                    this.checkModelStatus();
                    break;
                case 'browseImages':
                    await this.browseImages();
                    break;
                case 'searchHuggingFace':
                    await this.searchHuggingFace(message.query);
                    break;
                case 'downloadHFModel':
                    await this.downloadHFModel(message.repoId, message.fileName);
                    break;
                case 'startServerWithHF':
                    await this.startServerWithHF(message.hfModel);
                    break;
            }
        });
    }

    private async searchHuggingFace(query: string): Promise<void> {
        if (!query || query.length < 2) {
            this.postMessage({ command: 'hfSearchResults', results: [], error: 'Query too short' });
            return;
        }

        try {
            // Search Hugging Face API for GGUF models
            const searchUrl = `https://huggingface.co/api/models?search=${encodeURIComponent(query)}&library=gguf&sort=trending&limit=20`;

            const results = await this.fetchJSON(searchUrl);

            // Format results for display
            const formattedResults = results.map((model: any) => ({
                id: model.id || model.modelId,
                downloads: model.downloads || 0,
                likes: model.likes || 0,
                tags: model.tags || [],
                lastModified: model.lastModified || ''
            }));

            this.postMessage({ command: 'hfSearchResults', results: formattedResults });
        } catch (error: any) {
            console.error('[TrueFlow] HF search error:', error);
            this.postMessage({ command: 'hfSearchResults', results: [], error: error.message });
        }
    }

    private async fetchJSON(url: string): Promise<any> {
        return new Promise((resolve, reject) => {
            https.get(url, { headers: { 'User-Agent': 'TrueFlow/1.0' } }, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    try {
                        resolve(JSON.parse(data));
                    } catch (e) {
                        reject(new Error('Failed to parse response'));
                    }
                });
            }).on('error', reject);
        });
    }

    private async downloadHFModel(repoId: string, fileName: string): Promise<void> {
        const url = `https://huggingface.co/${repoId}/resolve/main/${fileName}`;
        const destPath = path.join(this.modelsDir, fileName);

        this.postMessage({ command: 'downloadStarted', modelName: `${repoId}/${fileName}` });

        try {
            await this.downloadFileWithProgress(url, destPath, (downloaded, total) => {
                const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
                const downloadedMB = Math.round(downloaded / (1024 * 1024));
                const totalMB = Math.round(total / (1024 * 1024));
                this.postMessage({
                    command: 'downloadProgress',
                    percent: pct,
                    downloadedMB,
                    totalMB
                });
            });

            this.currentModelFile = destPath;
            // Assume vision if model name contains VL, vision, gemma-3, smol
            this.currentModelHasVision = /vl|vision|gemma-3|smol/i.test(fileName);
            this.postMessage({ command: 'downloadComplete', modelName: fileName });
            this.checkModelStatus();

        } catch (error: any) {
            this.postMessage({ command: 'downloadError', error: error.message });
        }
    }

    private async startServerWithHF(hfModel: string): Promise<void> {
        // Use llama-server's -hf flag to load directly from HuggingFace
        if (this.serverProcess) {
            vscode.window.showWarningMessage('AI server is already running');
            return;
        }

        let llamaServer = this.findLlamaServer();
        if (!llamaServer) {
            const install = await vscode.window.showErrorMessage(
                'llama.cpp not found. Would you like to install it automatically?',
                'Install', 'Cancel'
            );
            if (install === 'Install') {
                const success = await this.installLlamaCpp();
                if (success) {
                    llamaServer = this.findLlamaServer();
                }
                if (!llamaServer) return;
            } else {
                return;
            }
        }

        this.postMessage({ command: 'serverStarting' });

        const cpuCount = require('os').cpus().length;
        const isVisionModel = /vl|vision|gemma-3|smol/i.test(hfModel);

        const args = [
            '-hf', hfModel,  // Direct HuggingFace loading
            '--port', '8080',
            '--ctx-size', '4096',
            '--threads', String(cpuCount),
            '--host', '127.0.0.1',
            '--jinja'
        ];

        if (isVisionModel) {
            args.push('--kv-unified');
            args.push('--no-mmproj-offload');
        }

        console.log(`[TrueFlow] Starting llama-server with HF: ${llamaServer} ${args.join(' ')}`);

        this.serverProcess = child_process.spawn(llamaServer, args);
        this.currentModelHasVision = isVisionModel;

        this.serverProcess.stdout?.on('data', (data) => {
            console.log('[LLM Server]', data.toString());
        });

        this.serverProcess.stderr?.on('data', (data) => {
            console.log('[LLM Server]', data.toString());
        });

        this.serverProcess.on('close', (code) => {
            this.serverProcess = undefined;
            this.postMessage({ command: 'serverStopped' });
            if (code !== 0) {
                vscode.window.showErrorMessage(`AI server exited with code ${code}`);
            }
        });

        // Wait for server to be ready
        let ready = false;
        for (let i = 0; i < 120; i++) {  // Longer timeout for HF download
            await new Promise(resolve => setTimeout(resolve, 1000));
            try {
                const response = await this.checkServerHealth();
                if (response) {
                    ready = true;
                    break;
                }
            } catch {}
            this.postMessage({ command: 'serverStarting', progress: i + 1, message: 'Downloading and loading model...' });
        }

        if (ready) {
            // Write shared status for file-based fallback
            this.writeServerStatus({
                running: true,
                pid: this.serverProcess?.pid,
                port: 8080,
                model: hfModel,
                startedBy: 'vscode',
                startedAt: new Date().toISOString()
            });

            // Notify via WebSocket hub (real-time)
            this.hubClient.notifyAIServerStarted(8080, hfModel);

            this.postMessage({ command: 'serverStarted' });
            vscode.window.showInformationMessage('AI server started with HuggingFace model');
        } else {
            this.stopServer();
            vscode.window.showErrorMessage('AI server failed to start');
        }
    }

    private async browseImages(): Promise<void> {
        // Default to workspace folder or home directory
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri;
        const defaultUri = workspaceFolder || vscode.Uri.file(this.getHomeDir());

        const result = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            defaultUri: defaultUri,
            filters: {
                'Images': ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'],
                'All files': ['*']
            },
            title: 'Select an image to attach'
        });

        if (result && result[0]) {
            try {
                const filePath = result[0].fsPath;
                const imageBuffer = fs.readFileSync(filePath);
                const imageBase64 = imageBuffer.toString('base64');
                const fileName = path.basename(filePath);

                this.postMessage({
                    command: 'imageSelected',
                    imageBase64: imageBase64,
                    fileName: fileName
                });
            } catch (error: any) {
                vscode.window.showErrorMessage(`Failed to read image: ${error.message}`);
            }
        }
    }

    private async handleUserMessage(text: string, imageBase64: string | undefined, contextType: string): Promise<void> {
        if (!text && !imageBase64) return;

        // Check if server is running (either by us or externally)
        const serverRunning = await this.isServerRunningAnywhere();
        if (!serverRunning) {
            this.postMessage({
                command: 'addMessage',
                role: 'system',
                content: 'Please start the AI server first. The server is not responding on port 8080.',
                timestamp: new Date().toLocaleTimeString()
            });
            return;
        }

        // Add user message to history
        const userMessage: ChatMessage = {
            role: 'user',
            content: text,
            imageBase64,
            timestamp: new Date().toLocaleTimeString()
        };
        this.conversationHistory.push(userMessage);
        this.trimHistory();

        // Show user message
        this.postMessage({
            command: 'addMessage',
            role: 'user',
            content: imageBase64 ? `${text}\n[Image attached]` : text,
            timestamp: userMessage.timestamp
        });

        // Show thinking indicator
        this.postMessage({ command: 'setThinking', thinking: true });

        try {
            // Build context
            const contextText = this.buildContext(contextType);

            // Call LLM
            const response = await this.callLLM(text, contextText, imageBase64);

            // Add assistant response
            const assistantMessage: ChatMessage = {
                role: 'assistant',
                content: response,
                timestamp: new Date().toLocaleTimeString()
            };
            this.conversationHistory.push(assistantMessage);
            this.trimHistory();

            this.postMessage({
                command: 'addMessage',
                role: 'assistant',
                content: response,
                timestamp: assistantMessage.timestamp
            });
        } catch (error: any) {
            this.postMessage({
                command: 'addMessage',
                role: 'system',
                content: `Error: ${error.message}`,
                timestamp: new Date().toLocaleTimeString()
            });
        } finally {
            this.postMessage({ command: 'setThinking', thinking: false });
        }
    }

    private buildContext(contextType: string): string {
        switch (contextType) {
            case 'deadCode':
                return this.buildDeadCodeContext();
            case 'performance':
                return this.buildPerformanceContext();
            case 'callTrace':
                return this.buildCallTraceContext();
            case 'diagram':
                return this.diagramData ? `\n--- Current Diagram ---\n${this.diagramData}` : '';
            case 'all':
                return [
                    this.buildDeadCodeContext(),
                    this.buildPerformanceContext(),
                    this.buildCallTraceContext(),
                    this.diagramData ? `\n--- Current Diagram ---\n${this.diagramData}` : ''
                ].filter(s => s).join('\n');
            default:
                return '';
        }
    }

    private buildDeadCodeContext(): string {
        if (!this.deadCodeData) return '';
        const deadFunctions = this.deadCodeData.dead_functions || [];
        if (deadFunctions.length === 0) return '';

        let context = '\n--- Dead Code Context ---\n';
        context += `Dead/Unreachable functions (${deadFunctions.length}):\n`;
        deadFunctions.slice(0, 20).forEach((func: string) => {
            context += `  - ${func}\n`;
        });
        return context;
    }

    private buildPerformanceContext(): string {
        if (!this.performanceData) return '';
        const hotspots = this.performanceData.hotspots || [];
        if (hotspots.length === 0) return '';

        let context = '\n--- Performance Context ---\n';
        context += 'Performance hotspots:\n';
        hotspots.slice(0, 10).forEach((item: any) => {
            context += `  - ${item.function}: ${item.total_ms?.toFixed(2) || '?'}ms (${item.calls || '?'} calls)\n`;
        });
        return context;
    }

    private buildCallTraceContext(): string {
        if (!this.callTraceData) return '';
        const calls = this.callTraceData.calls || [];
        if (calls.length === 0) return '';

        let context = '\n--- Call Trace Context ---\n';
        context += 'Recent call sequence:\n';
        calls.slice(0, 30).forEach((item: any) => {
            const indent = '  '.repeat(item.depth || 0);
            context += `${indent}→ ${item.module || '?'}.${item.function || '?'}()\n`;
        });
        return context;
    }

    private async callLLM(userPrompt: string, contextText: string, imageBase64?: string): Promise<string> {
        const messages: any[] = [];

        // System prompt
        messages.push({
            role: 'system',
            content: `You are TrueFlow AI, a code analysis assistant. You help developers understand:
1. Why code is marked as dead/unreachable by analyzing call trees
2. Performance issues by tracing through execution paths
3. Exceptions and errors by examining trace data
4. Code flow from sequence diagrams

Be concise and technical. When analyzing images, describe what you see and relate it to code concepts.`
        });

        // Add conversation history
        for (const msg of this.conversationHistory.slice(0, -1)) {
            if (msg.imageBase64 && this.currentModelHasVision) {
                messages.push({
                    role: msg.role,
                    content: [
                        { type: 'text', text: msg.content },
                        { type: 'image_url', image_url: { url: `data:image/png;base64,${msg.imageBase64}` } }
                    ]
                });
            } else {
                messages.push({ role: msg.role, content: msg.content });
            }
        }

        // Current message with context
        const fullPrompt = contextText ? `${userPrompt}\n${contextText}` : userPrompt;

        if (imageBase64 && this.currentModelHasVision) {
            messages.push({
                role: 'user',
                content: [
                    { type: 'text', text: fullPrompt },
                    { type: 'image_url', image_url: { url: `data:image/png;base64,${imageBase64}` } }
                ]
            });
        } else {
            messages.push({ role: 'user', content: fullPrompt });
        }

        const requestBody = JSON.stringify({
            model: 'qwen3-vl',
            messages,
            max_tokens: 1024,
            temperature: 0.7
        });

        return new Promise((resolve, reject) => {
            const req = http.request(`${this.apiBase}/chat/completions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(requestBody)
                },
                timeout: 120000
            }, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    // Handle non-200 responses
                    if (res.statusCode !== 200) {
                        console.error(`[TrueFlow] Server returned ${res.statusCode}: ${data}`);
                        try {
                            const errorJson = JSON.parse(data);
                            const errorMsg = errorJson.error?.message || errorJson.error || data;
                            reject(new Error(`Server error (${res.statusCode}): ${errorMsg}`));
                        } catch {
                            reject(new Error(`Server error (${res.statusCode}): ${data.slice(0, 200)}`));
                        }
                        return;
                    }

                    try {
                        const json = JSON.parse(data);
                        const content = json.choices?.[0]?.message?.content || 'No response';
                        resolve(content);
                    } catch (e) {
                        console.error(`[TrueFlow] Failed to parse response: ${data.slice(0, 500)}`);
                        reject(new Error('Failed to parse response'));
                    }
                });
            });

            req.on('error', (err) => {
                console.error(`[TrueFlow] Request error: ${err.message}`);
                reject(err);
            });
            req.on('timeout', () => reject(new Error('Request timeout')));
            req.write(requestBody);
            req.end();
        });
    }

    private trimHistory(): void {
        while (this.conversationHistory.length > this.maxHistorySize * 2) {
            this.conversationHistory.shift();
        }
    }

    private async checkModelStatus(): Promise<void> {
        const downloadedModels: string[] = [];

        for (const preset of MODEL_PRESETS) {
            const modelPath = path.join(this.modelsDir, preset.fileName);
            if (fs.existsSync(modelPath)) {
                downloadedModels.push(preset.fileName);
                if (!this.currentModelFile) {
                    this.currentModelFile = modelPath;
                    this.currentModelHasVision = preset.hasVision;
                }
            }
        }

        // Check if server is running from another IDE
        const externalStatus = this.readServerStatus();
        const externalRunning = externalStatus?.running && !this.serverProcess;
        if (externalRunning) {
            const isHealthy = await this.checkServerHealth();
            if (isHealthy) {
                this.postMessage({
                    command: 'externalServerRunning',
                    startedBy: externalStatus?.startedBy || 'external',
                    model: externalStatus?.model || 'unknown'
                });
            } else {
                // Stale status file
                this.writeServerStatus(null);
            }
        }

        this.postMessage({
            command: 'updateStatus',
            downloadedModels,
            serverRunning: !!this.serverProcess || externalRunning,
            models: MODEL_PRESETS.map(m => ({
                displayName: m.displayName,
                sizeMB: m.sizeMB,
                description: m.description,
                downloaded: downloadedModels.includes(m.fileName)
            }))
        });
    }

    private async downloadModel(modelIndex: number): Promise<void> {
        const preset = MODEL_PRESETS[modelIndex];
        if (!preset) return;

        const url = `https://huggingface.co/${preset.repoId}/resolve/main/${preset.fileName}`;
        const destPath = path.join(this.modelsDir, preset.fileName);

        this.postMessage({ command: 'downloadStarted', modelName: preset.displayName });

        try {
            await this.downloadFileWithProgress(url, destPath, (downloaded, total) => {
                const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
                const downloadedMB = Math.round(downloaded / (1024 * 1024));
                const totalMB = Math.round(total / (1024 * 1024));
                this.postMessage({
                    command: 'downloadProgress',
                    percent: pct,
                    downloadedMB,
                    totalMB
                });
            });

            this.currentModelFile = destPath;
            this.currentModelHasVision = preset.hasVision;
            this.postMessage({ command: 'downloadComplete', modelName: preset.displayName });
            this.checkModelStatus();

        } catch (error: any) {
            this.postMessage({ command: 'downloadError', error: error.message });
        }
    }

    private downloadFileWithProgress(
        urlString: string,
        destPath: string,
        progressCallback: (downloaded: number, total: number) => void
    ): Promise<void> {
        return new Promise((resolve, reject) => {
            const file = fs.createWriteStream(destPath);
            let downloaded = 0;

            const handleResponse = (response: http.IncomingMessage) => {
                const total = parseInt(response.headers['content-length'] || '0', 10);

                response.on('data', (chunk: Buffer) => {
                    downloaded += chunk.length;
                    progressCallback(downloaded, total);
                });

                response.pipe(file);

                file.on('finish', () => {
                    file.close();
                    resolve();
                });
            };

            https.get(urlString, { headers: { 'User-Agent': 'TrueFlow/1.0' } }, (response) => {
                if (response.statusCode === 302 || response.statusCode === 301) {
                    const redirectUrl = response.headers.location;
                    if (redirectUrl) {
                        https.get(redirectUrl, { headers: { 'User-Agent': 'TrueFlow/1.0' } }, handleResponse)
                            .on('error', reject);
                        return;
                    }
                }
                handleResponse(response);
            }).on('error', (err) => {
                fs.unlink(destPath, () => {});
                reject(err);
            });
        });
    }

    private async startServer(): Promise<void> {
        if (this.serverProcess) {
            vscode.window.showWarningMessage('AI server is already running');
            return;
        }

        // Check if server is already running from another IDE
        const existingStatus = this.readServerStatus();
        if (existingStatus?.running) {
            const isHealthy = await this.checkServerHealth();
            if (isHealthy) {
                vscode.window.showInformationMessage(
                    `AI server already running (started by ${existingStatus.startedBy}). Using existing server.`
                );
                this.postMessage({
                    command: 'externalServerRunning',
                    startedBy: existingStatus.startedBy,
                    model: existingStatus.model
                });
                return;
            }
            // Server status file exists but server not responding - clean up
            this.writeServerStatus(null);
        }

        if (!this.currentModelFile) {
            vscode.window.showErrorMessage('No model downloaded. Please download a model first.');
            return;
        }

        let llamaServer = this.findLlamaServer();
        if (!llamaServer) {
            const install = await vscode.window.showErrorMessage(
                'llama.cpp not found. Would you like to install it automatically?',
                'Install', 'Manual Instructions', 'Cancel'
            );
            if (install === 'Install') {
                const success = await this.installLlamaCpp();
                if (success) {
                    llamaServer = this.findLlamaServer();
                }
                if (!llamaServer) {
                    return;
                }
            } else if (install === 'Manual Instructions') {
                vscode.env.openExternal(vscode.Uri.parse('https://github.com/ggerganov/llama.cpp#build'));
                return;
            } else {
                return;
            }
        }

        this.postMessage({ command: 'serverStarting' });

        const cpuCount = require('os').cpus().length;

        // Find the current model preset to check if it has vision
        const currentPreset = MODEL_PRESETS.find(p => this.currentModelFile?.includes(p.fileName));

        const args = [
            '--model', this.currentModelFile,
            '--port', '8080',
            '--ctx-size', '4096',
            '--threads', String(cpuCount),
            '--host', '127.0.0.1',
            '--jinja'  // Required for vision models chat template support
        ];

        // Add vision model specific flags
        if (currentPreset?.hasVision) {
            // --kv-unified fixes KV cache issues on second+ multimodal requests for Qwen3-VL
            args.push('--kv-unified');
            // --no-mmproj-offload for better compatibility on systems without GPU
            args.push('--no-mmproj-offload');
        }

        // Log the full command for debugging
        console.log(`[TrueFlow] Starting llama-server: ${llamaServer} ${args.join(' ')}`);

        this.serverProcess = child_process.spawn(llamaServer, args);

        this.serverProcess.stdout?.on('data', (data) => {
            console.log('[LLM Server]', data.toString());
        });

        this.serverProcess.stderr?.on('data', (data) => {
            console.log('[LLM Server]', data.toString());
        });

        this.serverProcess.on('close', (code) => {
            this.serverProcess = undefined;
            this.postMessage({ command: 'serverStopped' });
            if (code !== 0) {
                vscode.window.showErrorMessage(`AI server exited with code ${code}`);
            }
        });

        // Wait for server to be ready
        let ready = false;
        for (let i = 0; i < 60; i++) {
            await new Promise(resolve => setTimeout(resolve, 1000));
            try {
                const response = await this.checkServerHealth();
                if (response) {
                    ready = true;
                    break;
                }
            } catch {}
            this.postMessage({ command: 'serverStarting', progress: i + 1 });
        }

        if (ready) {
            const modelName = this.currentModelFile ? path.basename(this.currentModelFile) : 'unknown';

            // Write shared status so other IDEs know the server is running (file-based fallback)
            this.writeServerStatus({
                running: true,
                pid: this.serverProcess?.pid,
                port: 8080,
                model: modelName,
                startedBy: 'vscode',
                startedAt: new Date().toISOString()
            });

            // Notify via WebSocket hub (real-time)
            this.hubClient.notifyAIServerStarted(8080, modelName);

            this.postMessage({ command: 'serverStarted' });
            vscode.window.showInformationMessage('AI server started on port 8080');
        } else {
            this.stopServer();
            vscode.window.showErrorMessage('AI server failed to start');
        }
    }

    private checkServerHealth(): Promise<boolean> {
        return new Promise((resolve) => {
            http.get('http://127.0.0.1:8080/health', { timeout: 2000 }, (res) => {
                resolve(res.statusCode === 200);
            }).on('error', () => resolve(false));
        });
    }

    private stopServer(): void {
        if (this.serverProcess) {
            this.serverProcess.kill();
            this.serverProcess = undefined;

            // Clear shared status so other IDEs know server stopped (file-based fallback)
            this.writeServerStatus(null);

            // Notify via WebSocket hub (real-time)
            this.hubClient.notifyAIServerStopped();

            this.postMessage({ command: 'serverStopped' });
            vscode.window.showInformationMessage('AI server stopped');
        }
    }

    private findLlamaServer(): string | null {
        const homeDir = this.getHomeDir();
        const possiblePaths = [
            // Prebuilt binary location (preferred - from GitHub releases)
            path.join(homeDir, '.trueflow', 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe'),
            path.join(homeDir, '.trueflow', 'llama.cpp', 'build', 'bin', 'Release', 'llama-server'),
            // Windows MSVC build output (Release config goes to bin/Release/)
            path.join(homeDir, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server.exe'),
            // Linux/macOS build output
            path.join(homeDir, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server'),
            // Fallback paths
            path.join(homeDir, 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe'),
            path.join(homeDir, 'llama.cpp', 'build', 'bin', 'llama-server'),
            path.join(homeDir, 'llama.cpp', 'build', 'bin', 'llama-server.exe'),
            '/usr/local/bin/llama-server',
            'C:\\llama.cpp\\build\\bin\\Release\\llama-server.exe',
            'C:\\llama.cpp\\build\\bin\\llama-server.exe'
        ];

        for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
                return p;
            }
        }

        try {
            const which = process.platform === 'win32' ? 'where' : 'which';
            const result = child_process.execSync(`${which} llama-server`, { encoding: 'utf-8' });
            return result.trim().split('\n')[0];
        } catch {
            return null;
        }
    }

    public async installLlamaCpp(): Promise<boolean> {
        const homeDir = this.getHomeDir();
        const installDir = path.join(homeDir, '.trueflow', 'llama.cpp');

        return vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Installing llama.cpp',
            cancellable: false
        }, async (progress) => {
            try {
                // First try to download prebuilt binaries (faster and more reliable)
                progress.report({ message: 'Checking for prebuilt binaries...' });

                const prebuiltSuccess = await this.tryDownloadPrebuiltLlama(progress, installDir);
                if (prebuiltSuccess) {
                    return true;
                }

                // Fall back to building from source
                progress.report({ message: 'Prebuilt not available, building from source...' });

                // Step 1: Clone llama.cpp repository
                progress.report({ message: 'Cloning llama.cpp repository...' });

                // Remove existing directory if present
                if (fs.existsSync(installDir)) {
                    fs.rmSync(installDir, { recursive: true, force: true });
                }
                fs.mkdirSync(path.dirname(installDir), { recursive: true });

                const cloneResult = child_process.spawnSync('git', [
                    'clone', '--depth', '1',
                    'https://github.com/ggml-org/llama.cpp',
                    installDir
                ], { encoding: 'utf-8', timeout: 300000 });

                if (cloneResult.status !== 0) {
                    vscode.window.showErrorMessage(`Failed to clone llama.cpp: ${cloneResult.stderr}`);
                    return false;
                }

                // Step 2: Configure with CMake
                progress.report({ message: 'Configuring build with CMake...' });

                const buildDir = path.join(installDir, 'build');
                fs.mkdirSync(buildDir, { recursive: true });

                const cmakeArgs = [
                    '-B', buildDir,
                    '-S', installDir,
                    '-DCMAKE_BUILD_TYPE=Release',
                    '-DLLAMA_BUILD_SERVER=ON'  // Required to build llama-server executable
                ];
                if (process.platform === 'win32') {
                    cmakeArgs.push('-G', 'Visual Studio 17 2022', '-A', 'x64');
                }

                const configResult = child_process.spawnSync('cmake', cmakeArgs, {
                    encoding: 'utf-8',
                    timeout: 300000,
                    cwd: installDir
                });

                if (configResult.status !== 0) {
                    vscode.window.showErrorMessage(`CMake configure failed: ${configResult.stderr}`);
                    return false;
                }

                // Step 3: Build with CMake
                progress.report({ message: 'Building llama.cpp (this may take several minutes)...' });

                const cpuCount = require('os').cpus().length;
                const buildResult = child_process.spawnSync('cmake', [
                    '--build', buildDir,
                    '--config', 'Release',
                    '--parallel', String(cpuCount),
                    '--target', 'llama-server'
                ], { encoding: 'utf-8', timeout: 600000, cwd: installDir });

                if (buildResult.status !== 0) {
                    vscode.window.showErrorMessage(`Build failed: ${buildResult.stderr}`);
                    return false;
                }

                // Verify installation
                const serverPath = this.findLlamaServer();
                if (serverPath) {
                    vscode.window.showInformationMessage(`llama.cpp installed successfully at ${serverPath}`);
                    return true;
                } else {
                    vscode.window.showErrorMessage('Build completed but llama-server not found');
                    return false;
                }

            } catch (error: any) {
                vscode.window.showErrorMessage(`Installation failed: ${error.message}`);
                return false;
            }
        });
    }

    private async tryDownloadPrebuiltLlama(progress: vscode.Progress<{ message?: string }>, installDir: string): Promise<boolean> {
        try {
            // Get latest release info from GitHub API
            progress.report({ message: 'Fetching latest release info...' });

            const releaseInfo = await this.fetchJSON('https://api.github.com/repos/ggml-org/llama.cpp/releases/latest');
            const tagName = releaseInfo.tag_name;

            // Determine the right binary for this platform
            let assetName: string;
            let extractDir: string;

            if (process.platform === 'win32') {
                assetName = `llama-${tagName}-bin-win-cpu-x64.zip`;
            } else if (process.platform === 'darwin') {
                assetName = `llama-${tagName}-bin-macos-arm64.zip`;
            } else {
                // Linux - use ubuntu as it's most compatible
                assetName = `llama-${tagName}-bin-ubuntu-x64.zip`;
            }

            // Find the asset URL
            const asset = releaseInfo.assets?.find((a: any) => a.name === assetName);
            if (!asset) {
                console.log(`[TrueFlow] Prebuilt binary not found: ${assetName}`);
                return false;
            }

            const downloadUrl = asset.browser_download_url;
            progress.report({ message: `Downloading prebuilt llama.cpp (${tagName})...` });

            // Create install directory
            fs.mkdirSync(installDir, { recursive: true });

            // Download the zip file
            const zipPath = path.join(installDir, assetName);
            await this.downloadFileWithProgress(downloadUrl, zipPath, (downloaded, total) => {
                const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
                progress.report({ message: `Downloading... ${pct}%` });
            });

            // Extract the zip
            progress.report({ message: 'Extracting binaries...' });

            if (process.platform === 'win32') {
                // Use PowerShell to extract on Windows
                const extractResult = child_process.spawnSync('powershell', [
                    '-Command',
                    `Expand-Archive -Path "${zipPath}" -DestinationPath "${installDir}" -Force`
                ], { encoding: 'utf-8', timeout: 60000 });

                if (extractResult.status !== 0) {
                    console.error(`[TrueFlow] Extract failed: ${extractResult.stderr}`);
                    return false;
                }
            } else {
                // Use unzip on Unix
                const extractResult = child_process.spawnSync('unzip', ['-o', zipPath, '-d', installDir], {
                    encoding: 'utf-8',
                    timeout: 60000
                });

                if (extractResult.status !== 0) {
                    console.error(`[TrueFlow] Extract failed: ${extractResult.stderr}`);
                    return false;
                }
            }

            // Clean up zip file
            fs.unlinkSync(zipPath);

            // Create a build/bin/Release structure for compatibility with findLlamaServer
            const binDir = path.join(installDir, 'build', 'bin', 'Release');
            fs.mkdirSync(binDir, { recursive: true });

            // Find llama-server in extracted files and copy/link to expected location
            const serverExe = process.platform === 'win32' ? 'llama-server.exe' : 'llama-server';
            const extractedBinDir = path.join(installDir, `llama-${tagName}-bin-${process.platform === 'win32' ? 'win-cpu-x64' : process.platform === 'darwin' ? 'macos-arm64' : 'ubuntu-x64'}`);
            const srcServer = path.join(extractedBinDir, serverExe);
            const destServer = path.join(binDir, serverExe);

            if (fs.existsSync(srcServer)) {
                fs.copyFileSync(srcServer, destServer);
                if (process.platform !== 'win32') {
                    fs.chmodSync(destServer, 0o755);
                }
                console.log(`[TrueFlow] Installed llama-server to: ${destServer}`);
                vscode.window.showInformationMessage(`llama.cpp ${tagName} installed successfully!`);
                return true;
            } else {
                // Try to find it in the root of extracted folder
                const altSrcServer = path.join(installDir, serverExe);
                if (fs.existsSync(altSrcServer)) {
                    fs.copyFileSync(altSrcServer, destServer);
                    if (process.platform !== 'win32') {
                        fs.chmodSync(destServer, 0o755);
                    }
                    console.log(`[TrueFlow] Installed llama-server to: ${destServer}`);
                    vscode.window.showInformationMessage(`llama.cpp ${tagName} installed successfully!`);
                    return true;
                }
                console.error(`[TrueFlow] llama-server not found in extracted files`);
                return false;
            }

        } catch (error: any) {
            console.error(`[TrueFlow] Prebuilt download failed: ${error.message}`);
            return false;
        }
    }

    private getHomeDir(): string {
        return process.env.HOME || process.env.USERPROFILE || '';
    }

    private postMessage(message: any): void {
        this.panel?.webview.postMessage(message);
    }

    // ==================== Public API for Other Panels ====================

    public setDeadCodeData(data: any): void {
        this.deadCodeData = data;
    }

    public setPerformanceData(data: any): void {
        this.performanceData = data;
    }

    public setCallTraceData(data: any): void {
        this.callTraceData = data;
    }

    public setDiagramData(diagram: string): void {
        this.diagramData = diagram;
    }

    public async askQuestion(question: string, context: string = '', callback: (response: string) => void): Promise<void> {
        if (!this.serverProcess) {
            callback('AI server not running. Please start it from the AI Explanation tab.');
            return;
        }

        try {
            const response = await this.callLLM(question, context, undefined);
            callback(response);
        } catch (error: any) {
            callback(`Error: ${error.message}`);
        }
    }

    public async explainDeadCode(functionName: string, callTree: string, callback: (response: string) => void): Promise<void> {
        const question = `Why is the function '${functionName}' marked as dead/unreachable?

Call tree context:
${callTree}

Explain:
1. What paths could reach this function?
2. Why aren't those paths being executed?
3. Is this likely intentional or a bug?`;

        await this.askQuestion(question, this.buildDeadCodeContext(), callback);
    }

    public async explainPerformance(functionName: string, stats: string, callSequence: string, callback: (response: string) => void): Promise<void> {
        const question = `Why is '${functionName}' a performance bottleneck?

Stats: ${stats}
Call sequence leading to it:
${callSequence}

Explain:
1. Why is this function slow?
2. What's causing repeated calls?
3. Potential optimizations?`;

        await this.askQuestion(question, this.buildPerformanceContext(), callback);
    }

    public async getMethodSummary(methodName: string, methodCode: string, callback: (summary: string) => void): Promise<void> {
        if (!this.serverProcess) {
            callback(methodName);
            return;
        }

        const question = `In ONE brief sentence (max 15 words), what does this method do?

Method: ${methodName}
Code:
\`\`\`
${methodCode}
\`\`\``;

        try {
            const response = await this.callLLM(question, '', undefined);
            const summary = response.split('.')[0].trim();
            callback(summary.length > 80 ? summary.slice(0, 77) + '...' : summary);
        } catch {
            callback(methodName);
        }
    }

    public isServerRunning(): boolean {
        return !!this.serverProcess;
    }

    public dispose(): void {
        this.stopServer();
        this.panel?.dispose();
    }

    private getWebviewContent(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow AI Assistant</title>
    <style>
        :root {
            --bg-primary: #1e1e1e;
            --bg-secondary: #252526;
            --bg-tertiary: #2d2d30;
            --bg-hover: #3c3c3c;
            --text-primary: #ffffff;
            --text-secondary: #cccccc;
            --text-muted: #858585;
            --accent-blue: #0078d4;
            --accent-green: #4ec9b0;
            --accent-purple: #c586c0;
            --accent-orange: #ce9178;
            --border-color: #3c3c3c;
            --user-bubble: #264f78;
            --assistant-bubble: #2d2d30;
            --system-bubble: #3d3d40;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            line-height: 1.5;
        }

        /* Header */
        .header {
            padding: 12px 16px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
        }

        .header-title {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
        }

        .header-title h2 {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .status-indicator {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #f44336;
        }

        .status-indicator.connected { background: #4caf50; }

        .controls {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }

        select, button {
            padding: 6px 12px;
            font-size: 12px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }

        select {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            min-width: 200px;
        }

        select:focus {
            outline: none;
            border-color: var(--accent-blue);
        }

        button {
            background: var(--accent-blue);
            color: white;
            border: none;
            font-weight: 500;
        }

        button:hover:not(:disabled) {
            background: #1a8cd8;
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        button.secondary {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
        }

        button.secondary:hover:not(:disabled) {
            background: var(--bg-hover);
        }

        button.danger {
            background: #d32f2f;
        }

        button.danger:hover:not(:disabled) {
            background: #f44336;
        }

        .status-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 8px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .progress-bar {
            flex: 1;
            height: 4px;
            background: var(--bg-tertiary);
            border-radius: 2px;
            overflow: hidden;
            display: none;
        }

        .progress-bar.active { display: block; }

        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
            border-radius: 2px;
            transition: width 0.3s ease;
        }

        /* Chat Container */
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            scroll-behavior: smooth;
        }

        .chat-container::-webkit-scrollbar {
            width: 8px;
        }

        .chat-container::-webkit-scrollbar-track {
            background: transparent;
        }

        .chat-container::-webkit-scrollbar-thumb {
            background: var(--bg-hover);
            border-radius: 4px;
        }

        .chat-container::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }

        /* Messages */
        .message {
            margin-bottom: 16px;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-wrapper {
            display: flex;
            gap: 12px;
            max-width: 90%;
        }

        .message.user .message-wrapper {
            margin-left: auto;
            flex-direction: row-reverse;
        }

        .message-avatar {
            width: 32px;
            height: 32px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            flex-shrink: 0;
        }

        .message.user .message-avatar {
            background: var(--accent-blue);
        }

        .message.assistant .message-avatar {
            background: var(--accent-purple);
        }

        .message.system .message-avatar {
            background: var(--accent-orange);
        }

        .message-bubble {
            padding: 12px 16px;
            border-radius: 12px;
            position: relative;
        }

        .message.user .message-bubble {
            background: var(--user-bubble);
            border-bottom-right-radius: 4px;
        }

        .message.assistant .message-bubble {
            background: var(--assistant-bubble);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 4px;
        }

        .message.system .message-bubble {
            background: var(--system-bubble);
            border: 1px solid var(--border-color);
            max-width: 100%;
            text-align: center;
        }

        .message.system .message-wrapper {
            max-width: 100%;
            justify-content: center;
        }

        .message-header {
            font-size: 11px;
            color: var(--text-muted);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .message-role {
            font-weight: 600;
            color: var(--text-secondary);
        }

        .message-content {
            color: var(--text-primary);
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
            line-height: 1.6;
        }

        .message-content code {
            background: var(--bg-primary);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Cascadia Code', 'Fira Code', monospace;
            font-size: 12px;
        }

        /* Image in message */
        .message-image {
            max-width: 300px;
            max-height: 200px;
            border-radius: 8px;
            margin-top: 8px;
            cursor: pointer;
            transition: transform 0.2s;
            border: 1px solid var(--border-color);
        }

        .message-image:hover {
            transform: scale(1.02);
        }

        /* Thinking indicator */
        .thinking {
            display: none;
            padding: 16px;
            margin: 0 16px;
        }

        .thinking.active { display: block; }

        .thinking-content {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            background: var(--bg-secondary);
            border-radius: 12px;
            border: 1px solid var(--border-color);
        }

        .thinking-dots {
            display: flex;
            gap: 4px;
        }

        .thinking-dot {
            width: 8px;
            height: 8px;
            background: var(--accent-blue);
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }

        .thinking-dot:nth-child(1) { animation-delay: 0s; }
        .thinking-dot:nth-child(2) { animation-delay: 0.2s; }
        .thinking-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes bounce {
            0%, 80%, 100% { transform: translateY(0); }
            40% { transform: translateY(-8px); }
        }

        .thinking-text {
            color: var(--text-muted);
            font-size: 13px;
        }

        /* Input Area */
        .input-area {
            padding: 16px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
        }

        .image-preview-container {
            display: none;
            margin-bottom: 12px;
            padding: 8px;
            background: var(--bg-tertiary);
            border-radius: 8px;
            position: relative;
        }

        .image-preview-container.active { display: flex; align-items: center; gap: 12px; }

        .image-preview {
            max-width: 120px;
            max-height: 80px;
            border-radius: 6px;
            object-fit: cover;
        }

        .image-preview-info {
            flex: 1;
            font-size: 12px;
            color: var(--text-secondary);
        }

        .image-preview-remove {
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            padding: 4px 8px;
            font-size: 18px;
        }

        .image-preview-remove:hover {
            color: #f44336;
        }

        .input-wrapper {
            display: flex;
            gap: 12px;
            align-items: flex-end;
        }

        .input-left {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        textarea {
            width: 100%;
            min-height: 80px;
            max-height: 200px;
            padding: 12px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            resize: none;
            font-family: inherit;
            font-size: 13px;
            line-height: 1.5;
        }

        textarea:focus {
            outline: none;
            border-color: var(--accent-blue);
        }

        textarea::placeholder {
            color: var(--text-muted);
        }

        .input-actions {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }

        .input-actions select {
            font-size: 11px;
            padding: 4px 8px;
        }

        .input-actions button {
            padding: 6px 10px;
            font-size: 12px;
        }

        .icon-btn {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            width: 32px;
            height: 32px;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .icon-btn:hover:not(:disabled) {
            background: var(--bg-hover);
            border-color: var(--accent-blue);
        }

        .send-btn {
            height: 80px;
            padding: 0 24px;
            font-size: 14px;
            border-radius: 8px;
        }

        /* Image Gallery Modal */
        .image-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .image-modal.active { display: flex; }

        .image-modal img {
            max-width: 90%;
            max-height: 90%;
            border-radius: 8px;
        }

        .image-modal-close {
            position: absolute;
            top: 20px;
            right: 20px;
            background: none;
            border: none;
            color: white;
            font-size: 32px;
            cursor: pointer;
        }

        /* Welcome card styling */
        .welcome-card {
            background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }

        .welcome-card h3 {
            color: var(--accent-green);
            margin-bottom: 12px;
            font-size: 14px;
        }

        .welcome-card ul {
            list-style: none;
            padding: 0;
        }

        .welcome-card li {
            padding: 6px 0;
            color: var(--text-secondary);
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .welcome-card li::before {
            content: '';
            width: 6px;
            height: 6px;
            background: var(--accent-blue);
            border-radius: 50%;
        }

        /* HuggingFace Search Panel */
        .hf-search-panel {
            display: none;
            padding: 12px;
            background: var(--bg-tertiary);
            border-bottom: 1px solid var(--border-color);
        }

        .hf-search-panel.active { display: block; }

        .hf-search-row {
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
        }

        .hf-search-input {
            flex: 1;
            padding: 8px 12px;
            background: var(--bg-primary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            font-size: 13px;
        }

        .hf-search-input:focus {
            outline: none;
            border-color: var(--accent-blue);
        }

        .hf-results {
            max-height: 200px;
            overflow-y: auto;
            background: var(--bg-primary);
            border-radius: 4px;
            border: 1px solid var(--border-color);
        }

        .hf-result-item {
            padding: 10px 12px;
            border-bottom: 1px solid var(--border-color);
            cursor: pointer;
            transition: background 0.2s;
        }

        .hf-result-item:last-child { border-bottom: none; }

        .hf-result-item:hover {
            background: var(--bg-hover);
        }

        .hf-result-name {
            font-weight: 500;
            color: var(--text-primary);
            font-size: 13px;
        }

        .hf-result-meta {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .hf-result-meta span {
            margin-right: 12px;
        }

        .hf-no-results {
            padding: 16px;
            text-align: center;
            color: var(--text-muted);
            font-size: 12px;
        }

        .hf-loading {
            padding: 16px;
            text-align: center;
            color: var(--text-muted);
        }

        .tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 8px;
        }

        .tab-btn {
            padding: 6px 12px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 11px;
            cursor: pointer;
            border-radius: 4px;
        }

        .tab-btn.active {
            background: var(--accent-blue);
            color: white;
            border-color: var(--accent-blue);
        }

        .tab-btn:hover:not(.active) {
            background: var(--bg-hover);
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h2>TrueFlow AI Assistant</h2>
            <div class="status-indicator" id="statusIndicator"></div>
        </div>
        <div class="tabs">
            <button class="tab-btn active" id="tabPresets">Preset Models</button>
            <button class="tab-btn" id="tabHFSearch">Search HuggingFace</button>
        </div>
        <div class="controls" id="presetControls">
            <select id="modelSelect">
                <option value="">Select a model...</option>
            </select>
            <button id="downloadBtn" disabled>Download</button>
            <button id="serverBtn" class="secondary" disabled>Start Server</button>
            <button id="clearBtn" class="secondary">Clear</button>
        </div>
        <div class="status-bar">
            <span id="status">Initializing...</span>
            <div class="progress-bar" id="progressBar">
                <div class="progress-bar-fill" id="progressFill"></div>
            </div>
        </div>
    </div>

    <!-- HuggingFace Search Panel -->
    <div class="hf-search-panel" id="hfSearchPanel">
        <div class="hf-search-row">
            <input type="text" id="hfSearchInput" class="hf-search-input" placeholder="Search GGUF models on HuggingFace (e.g., qwen, llama, gemma)..." />
            <button id="hfSearchBtn">Search</button>
        </div>
        <div class="hf-results" id="hfResults">
            <div class="hf-no-results">Enter a search term to find GGUF models</div>
        </div>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="welcome-card">
            <h3>Welcome to TrueFlow AI</h3>
            <ul>
                <li>Explain dead/unreachable code</li>
                <li>Analyze performance bottlenecks</li>
                <li>Debug exceptions and errors</li>
                <li>Analyze screenshots and diagrams</li>
            </ul>
        </div>
    </div>

    <div class="thinking" id="thinking">
        <div class="thinking-content">
            <div class="thinking-dots">
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
            </div>
            <span class="thinking-text">AI is thinking...</span>
        </div>
    </div>

    <div class="input-area">
        <div class="image-preview-container" id="imagePreviewContainer">
            <img id="imagePreview" class="image-preview" />
            <div class="image-preview-info" id="imageInfo">Image attached</div>
            <button class="image-preview-remove" id="removeImageBtn">x</button>
        </div>
        <div class="input-wrapper">
            <div class="input-left">
                <textarea id="userInput" placeholder="Ask about your code... (Ctrl+Enter to send)"></textarea>
                <div class="input-actions">
                    <select id="contextSelect">
                        <option value="">No context</option>
                        <option value="deadCode">Dead Code</option>
                        <option value="performance">Performance</option>
                        <option value="callTrace">Call Trace</option>
                        <option value="all">All Data</option>
                    </select>
                    <button id="pasteImageBtn" class="icon-btn" title="Paste image from clipboard">📋</button>
                    <button id="attachImageBtn" class="icon-btn" title="Attach image file">📎</button>
                    <button id="browseImagesBtn" class="icon-btn" title="Browse images folder">🖼️</button>
                    <input type="file" id="imageInput" accept="image/*" style="display:none">
                </div>
            </div>
            <button id="sendBtn" class="send-btn">Send</button>
        </div>
    </div>

    <!-- Image modal for full view -->
    <div class="image-modal" id="imageModal">
        <button class="image-modal-close" id="closeModal">x</button>
        <img id="modalImage" />
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        let pendingImageBase64 = null;
        let serverRunning = false;
        let downloadedModels = [];

        // Elements
        const modelSelect = document.getElementById('modelSelect');
        const downloadBtn = document.getElementById('downloadBtn');
        const serverBtn = document.getElementById('serverBtn');
        const clearBtn = document.getElementById('clearBtn');
        const status = document.getElementById('status');
        const statusIndicator = document.getElementById('statusIndicator');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const chatContainer = document.getElementById('chatContainer');
        const thinking = document.getElementById('thinking');
        const userInput = document.getElementById('userInput');
        const contextSelect = document.getElementById('contextSelect');
        const sendBtn = document.getElementById('sendBtn');
        const pasteImageBtn = document.getElementById('pasteImageBtn');
        const attachImageBtn = document.getElementById('attachImageBtn');
        const browseImagesBtn = document.getElementById('browseImagesBtn');
        const imageInput = document.getElementById('imageInput');
        const imagePreview = document.getElementById('imagePreview');
        const imagePreviewContainer = document.getElementById('imagePreviewContainer');
        const imageInfo = document.getElementById('imageInfo');
        const removeImageBtn = document.getElementById('removeImageBtn');
        const imageModal = document.getElementById('imageModal');
        const modalImage = document.getElementById('modalImage');
        const closeModal = document.getElementById('closeModal');

        // HuggingFace search elements
        const tabPresets = document.getElementById('tabPresets');
        const tabHFSearch = document.getElementById('tabHFSearch');
        const presetControls = document.getElementById('presetControls');
        const hfSearchPanel = document.getElementById('hfSearchPanel');
        const hfSearchInput = document.getElementById('hfSearchInput');
        const hfSearchBtn = document.getElementById('hfSearchBtn');
        const hfResults = document.getElementById('hfResults');

        let selectedHFModel = null;

        // Tab switching
        tabPresets.addEventListener('click', () => {
            tabPresets.classList.add('active');
            tabHFSearch.classList.remove('active');
            presetControls.style.display = 'flex';
            hfSearchPanel.classList.remove('active');
        });

        tabHFSearch.addEventListener('click', () => {
            tabHFSearch.classList.add('active');
            tabPresets.classList.remove('active');
            presetControls.style.display = 'none';
            hfSearchPanel.classList.add('active');
        });

        // HuggingFace search
        hfSearchBtn.addEventListener('click', () => {
            const query = hfSearchInput.value.trim();
            if (query.length >= 2) {
                hfResults.innerHTML = '<div class="hf-loading">Searching...</div>';
                vscode.postMessage({ command: 'searchHuggingFace', query: query });
            }
        });

        hfSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                hfSearchBtn.click();
            }
        });

        function formatNumber(num) {
            if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
            return num.toString();
        }

        function renderHFResults(results) {
            if (!results || results.length === 0) {
                hfResults.innerHTML = '<div class="hf-no-results">No GGUF models found. Try a different search term.</div>';
                return;
            }

            hfResults.innerHTML = results.map(model => \`
                <div class="hf-result-item" data-model-id="\${model.id}">
                    <div class="hf-result-name">\${model.id}</div>
                    <div class="hf-result-meta">
                        <span>Downloads: \${formatNumber(model.downloads)}</span>
                        <span>Likes: \${formatNumber(model.likes)}</span>
                    </div>
                </div>
            \`).join('');

            // Add click handlers
            document.querySelectorAll('.hf-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    selectedHFModel = item.dataset.modelId;
                    // Highlight selection
                    document.querySelectorAll('.hf-result-item').forEach(i => i.style.background = '');
                    item.style.background = 'var(--accent-blue)';
                    status.textContent = 'Selected: ' + selectedHFModel + ' - Click "Start with HF" to load';
                    serverBtn.textContent = 'Start with HF';
                    serverBtn.disabled = false;
                });
            });
        }

        // Model selection - disable download for already downloaded models
        modelSelect.addEventListener('change', () => {
            const idx = modelSelect.selectedIndex - 1;
            if (idx < 0) {
                downloadBtn.disabled = true;
                return;
            }
            const selectedOption = modelSelect.options[modelSelect.selectedIndex];
            const isDownloaded = selectedOption.textContent.includes('\\u2713');
            downloadBtn.disabled = isDownloaded;
            downloadBtn.textContent = isDownloaded ? 'Downloaded' : 'Download';
        });

        downloadBtn.addEventListener('click', () => {
            const idx = modelSelect.selectedIndex - 1;
            if (idx >= 0) {
                vscode.postMessage({ command: 'downloadModel', modelIndex: idx });
            }
        });

        serverBtn.addEventListener('click', () => {
            if (serverRunning) {
                vscode.postMessage({ command: 'stopServer' });
            } else if (selectedHFModel) {
                // Start with HuggingFace model
                vscode.postMessage({ command: 'startServerWithHF', hfModel: selectedHFModel });
            } else {
                vscode.postMessage({ command: 'startServer' });
            }
        });

        clearBtn.addEventListener('click', () => {
            vscode.postMessage({ command: 'clearHistory' });
        });

        sendBtn.addEventListener('click', sendMessage);

        userInput.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                sendMessage();
            }
        });

        // Auto-resize textarea
        userInput.addEventListener('input', () => {
            userInput.style.height = 'auto';
            userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
        });

        pasteImageBtn.addEventListener('click', async () => {
            try {
                const items = await navigator.clipboard.read();
                for (const item of items) {
                    if (item.types.includes('image/png')) {
                        const blob = await item.getType('image/png');
                        handleImageBlob(blob, 'Pasted from clipboard');
                        return;
                    }
                }
                status.textContent = 'No image in clipboard';
            } catch (err) {
                status.textContent = 'Failed to paste: ' + err.message;
            }
        });

        attachImageBtn.addEventListener('click', () => imageInput.click());

        browseImagesBtn.addEventListener('click', () => {
            vscode.postMessage({ command: 'browseImages' });
        });

        imageInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                handleImageFile(file);
            }
        });

        removeImageBtn.addEventListener('click', () => {
            clearImage();
        });

        function handleImageFile(file) {
            const reader = new FileReader();
            reader.onload = () => {
                pendingImageBase64 = reader.result.split(',')[1];
                imagePreview.src = reader.result;
                imageInfo.textContent = file.name + ' (' + formatFileSize(file.size) + ')';
                imagePreviewContainer.classList.add('active');
                status.textContent = 'Image attached';
            };
            reader.readAsDataURL(file);
        }

        function handleImageBlob(blob, name) {
            const reader = new FileReader();
            reader.onload = () => {
                pendingImageBase64 = reader.result.split(',')[1];
                imagePreview.src = reader.result;
                imageInfo.textContent = name;
                imagePreviewContainer.classList.add('active');
                status.textContent = 'Image attached';
            };
            reader.readAsDataURL(blob);
        }

        function clearImage() {
            pendingImageBase64 = null;
            imagePreviewContainer.classList.remove('active');
            imageInput.value = '';
        }

        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function sendMessage() {
            const text = userInput.value.trim();
            if (!text && !pendingImageBase64) return;

            vscode.postMessage({
                command: 'sendMessage',
                text: text,
                imageBase64: pendingImageBase64,
                contextType: contextSelect.value
            });

            userInput.value = '';
            userInput.style.height = 'auto';
            clearImage();
        }

        function addMessage(role, content, timestamp, imageBase64) {
            const div = document.createElement('div');
            div.className = 'message ' + role;

            const avatarEmoji = role === 'user' ? '👤' : role === 'assistant' ? '🤖' : '💡';
            const roleName = role === 'user' ? 'You' : role === 'assistant' ? 'AI' : 'System';

            let imageHtml = '';
            if (imageBase64) {
                imageHtml = '<img class="message-image" src="data:image/png;base64,' + imageBase64 + '" onclick="showImageModal(this.src)" />';
            }

            div.innerHTML = \`
                <div class="message-wrapper">
                    <div class="message-avatar">\${avatarEmoji}</div>
                    <div class="message-bubble">
                        <div class="message-header">
                            <span class="message-role">\${roleName}</span>
                            <span>\${timestamp}</span>
                        </div>
                        <div class="message-content">\${escapeHtml(content)}</div>
                        \${imageHtml}
                    </div>
                </div>
            \`;
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Image modal
        window.showImageModal = function(src) {
            modalImage.src = src;
            imageModal.classList.add('active');
        };

        closeModal.addEventListener('click', () => {
            imageModal.classList.remove('active');
        });

        imageModal.addEventListener('click', (e) => {
            if (e.target === imageModal) {
                imageModal.classList.remove('active');
            }
        });

        // Handle messages from extension
        window.addEventListener('message', (event) => {
            const msg = event.data;
            switch (msg.command) {
                case 'updateStatus':
                    downloadedModels = msg.downloadedModels || [];
                    modelSelect.innerHTML = '<option value="">Select a model...</option>';
                    msg.models.forEach((m, i) => {
                        const opt = document.createElement('option');
                        opt.value = i;
                        opt.dataset.downloaded = m.downloaded ? 'true' : 'false';
                        opt.textContent = m.displayName + (m.downloaded ? ' \\u2713' : ' (' + m.sizeMB + 'MB)');
                        modelSelect.appendChild(opt);
                    });
                    serverBtn.disabled = downloadedModels.length === 0;
                    serverRunning = msg.serverRunning;
                    serverBtn.textContent = serverRunning ? 'Stop Server' : 'Start Server';
                    serverBtn.className = serverRunning ? 'danger' : 'secondary';
                    statusIndicator.className = 'status-indicator' + (serverRunning ? ' connected' : '');
                    status.textContent = serverRunning ? 'AI Server running - Ready!' :
                        (downloadedModels.length > 0 ? 'Model ready. Start server to chat.' : 'Download a model to begin.');
                    // Reset download button state
                    downloadBtn.disabled = modelSelect.selectedIndex <= 0;
                    downloadBtn.textContent = 'Download';
                    break;

                case 'addMessage':
                    addMessage(msg.role, msg.content, msg.timestamp, msg.imageBase64);
                    break;

                case 'setThinking':
                    thinking.classList.toggle('active', msg.thinking);
                    sendBtn.disabled = msg.thinking;
                    break;

                case 'historyCleared':
                    chatContainer.innerHTML = '<div class="welcome-card"><h3>Chat Cleared</h3><ul><li>Ready for new conversation</li></ul></div>';
                    break;

                case 'downloadStarted':
                    status.textContent = 'Downloading ' + msg.modelName + '...';
                    progressBar.classList.add('active');
                    downloadBtn.disabled = true;
                    downloadBtn.textContent = 'Downloading...';
                    break;

                case 'downloadProgress':
                    progressFill.style.width = msg.percent + '%';
                    status.textContent = 'Downloading... ' + msg.downloadedMB + 'MB / ' + msg.totalMB + 'MB (' + msg.percent + '%)';
                    break;

                case 'downloadComplete':
                    progressBar.classList.remove('active');
                    status.textContent = 'Download complete: ' + msg.modelName;
                    downloadBtn.disabled = true;
                    downloadBtn.textContent = 'Downloaded';
                    vscode.postMessage({ command: 'checkStatus' });
                    break;

                case 'downloadError':
                    progressBar.classList.remove('active');
                    status.textContent = 'Download error: ' + msg.error;
                    downloadBtn.disabled = false;
                    downloadBtn.textContent = 'Retry';
                    break;

                case 'serverStarting':
                    status.textContent = 'Starting AI server... ' + (msg.progress || 0) + '/60s';
                    serverBtn.disabled = true;
                    serverBtn.textContent = 'Starting...';
                    break;

                case 'serverStarted':
                    serverRunning = true;
                    serverBtn.textContent = 'Stop Server';
                    serverBtn.className = 'danger';
                    serverBtn.disabled = false;
                    statusIndicator.classList.add('connected');
                    status.textContent = 'AI Server running - Ready to chat!';
                    break;

                case 'serverStopped':
                    serverRunning = false;
                    serverBtn.textContent = 'Start Server';
                    serverBtn.className = 'secondary';
                    serverBtn.disabled = false;
                    statusIndicator.classList.remove('connected');
                    status.textContent = 'AI Server stopped';
                    break;

                case 'imageSelected':
                    if (msg.imageBase64) {
                        pendingImageBase64 = msg.imageBase64;
                        imagePreview.src = 'data:image/png;base64,' + msg.imageBase64;
                        imageInfo.textContent = msg.fileName || 'Selected image';
                        imagePreviewContainer.classList.add('active');
                        status.textContent = 'Image selected';
                    }
                    break;

                case 'hfSearchResults':
                    if (msg.error) {
                        hfResults.innerHTML = '<div class="hf-no-results">Error: ' + msg.error + '</div>';
                    } else {
                        renderHFResults(msg.results);
                    }
                    break;

                case 'externalServerRunning':
                    // Server is running from another IDE (PyCharm, etc.)
                    serverRunning = true;
                    serverBtn.textContent = 'Using External Server';
                    serverBtn.className = 'secondary';
                    serverBtn.disabled = true;
                    sendBtn.disabled = false;
                    statusIndicator.classList.add('connected');
                    status.textContent = 'AI Server running (started by ' + msg.startedBy + ') - Ready!';
                    break;
            }
        });

        // Initial status check
        vscode.postMessage({ command: 'checkStatus' });
    </script>
</body>
</html>`;
    }
}
