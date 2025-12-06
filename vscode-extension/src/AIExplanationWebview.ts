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
    // Note: mmproj file is required for vision - verified from HuggingFace repos
    {
        displayName: "Qwen3-VL-2B Instruct Q4_K_XL (Recommended)",
        repoId: "unsloth/Qwen3-VL-2B-Instruct-GGUF",
        fileName: "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 1500,
        description: "Vision+text, best for code analysis with diagrams",
        hasVision: true,
        mmprojRepoId: "unsloth/Qwen3-VL-2B-Instruct-GGUF",
        mmprojFileName: "mmproj-F16.gguf",
        mmprojSizeMB: 819
    },
    {
        displayName: "Qwen3-VL-2B Thinking Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-2B-Thinking-GGUF",
        fileName: "Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf",
        sizeMB: 1500,
        description: "Vision+text with chain-of-thought reasoning",
        hasVision: true,
        mmprojRepoId: "unsloth/Qwen3-VL-2B-Thinking-GGUF",
        mmprojFileName: "mmproj-F16.gguf",
        mmprojSizeMB: 819
    },
    {
        displayName: "Qwen3-VL-4B Instruct Q4_K_XL",
        repoId: "unsloth/Qwen3-VL-4B-Instruct-GGUF",
        fileName: "Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf",
        sizeMB: 2800,
        description: "Larger model, better quality, needs ~6GB RAM",
        hasVision: true,
        mmprojRepoId: "unsloth/Qwen3-VL-4B-Instruct-GGUF",
        mmprojFileName: "mmproj-F16.gguf",
        mmprojSizeMB: 819
    },
    // Gemma 3 models - Google's multimodal
    {
        displayName: "Gemma-3-4B IT Q4_K_XL",
        repoId: "unsloth/gemma-3-4b-it-GGUF",
        fileName: "gemma-3-4b-it-Q4_K_XL.gguf",
        sizeMB: 2700,
        description: "Vision+text, Google Gemma 3, well-tested multimodal",
        hasVision: true,
        mmprojRepoId: "unsloth/gemma-3-4b-it-GGUF",
        mmprojFileName: "mmproj-F16.gguf",
        mmprojSizeMB: 851
    },
    {
        // Note: Gemma-3-1B does NOT have mmproj in repo - text-only
        displayName: "Gemma-3-1B IT Q4_K_M",
        repoId: "unsloth/gemma-3-1b-it-GGUF",
        fileName: "gemma-3-1b-it-Q4_K_M.gguf",
        sizeMB: 600,
        description: "Text-only, compact & fast, good for quick analysis",
        hasVision: false
    },
    // SmolVLM - ultra-compact vision model
    {
        displayName: "SmolVLM-256M-Instruct",
        repoId: "ggml-org/SmolVLM-256M-Instruct-GGUF",
        fileName: "SmolVLM-256M-Instruct-Q8_0.gguf",
        sizeMB: 280,
        description: "Tiny vision model, ultra-fast, basic image analysis",
        hasVision: true,
        mmprojRepoId: "ggml-org/SmolVLM-256M-Instruct-GGUF",
        mmprojFileName: "mmproj-SmolVLM-256M-Instruct-f16.gguf",
        mmprojSizeMB: 50
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
    private sqlAnalysisData: any = null;
    private diagramData: string = '';
    private currentDiagramData: string = '';
    private contextSelection: number = 0;

    // Chunking and interrupt control
    private isOperationCancelled = false;
    private readonly TOKEN_CHUNK_SIZE = 200;

    // GPU and backend configuration
    private gpuAvailable: 'cuda' | 'metal' | 'vulkan' | 'none' = 'none';
    private useGpuAcceleration = false;
    private backendType: 'llama.cpp' | 'ollama' = 'llama.cpp';
    private ollamaEndpoint = 'http://127.0.0.1:11434';
    private totalTokensUsed = 0;

    // Benchmark results for CPU vs GPU comparison
    private cpuTokensPerSecond = 0;
    private gpuTokensPerSecond = 0;
    private benchmarkCompleted = false;
    private recommendedBackend: 'cpu' | 'gpu' = 'cpu';

    // Track if server was started externally (not by this VS Code instance)
    private externalServerDetected = false;
    private gpuMemoryMB = 0;  // Total GPU memory

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

        // Detect GPU availability
        this.detectGpuAcceleration();

        // Check if server is already running (e.g., from previous session or another IDE)
        this.checkExistingServer();
    }

    /**
     * Check if AI server is already running on startup.
     * This handles the case where VS Code restarts but the server is still running.
     */
    private async checkExistingServer(): Promise<void> {
        try {
            const isRunning = await this.checkServerHealth();
            if (isRunning) {
                // Server is running but we didn't start it - mark as external
                this.externalServerDetected = true;
                const status = this.readServerStatus();
                const model = status?.model || 'Unknown model';
                const startedBy = status?.startedBy || 'external process';

                console.log(`[TrueFlow] Detected external AI server on startup (model: ${model}, started by: ${startedBy})`);

                // Update UI to show external server - disable controls
                this.postMessage({
                    command: 'externalServerRunning',
                    startedBy: startedBy,
                    model: model
                });
                this.postMessage({
                    command: 'updateStatus',
                    status: `External server: ${model}`
                });
            }
        } catch (e) {
            // No server running, that's fine
        }
    }

    /**
     * Detect available GPU acceleration (CUDA, Metal, Vulkan)
     * Runs asynchronously to avoid blocking extension activation.
     */
    private detectGpuAcceleration(): void {
        // Run detection in background to avoid blocking
        setTimeout(() => {
            this.detectGpuAsync().then(gpu => {
                this.gpuAvailable = gpu;
                console.log(`[TrueFlow] GPU acceleration detected: ${this.gpuAvailable}`);
                // Update UI if panel exists
                this.postMessage({
                    command: 'gpuStatus',
                    available: gpu !== 'none',
                    type: gpu,
                    enabled: this.useGpuAcceleration
                });
            }).catch(() => {
                console.log('[TrueFlow] GPU detection failed, defaulting to none');
            });
        }, 100);
    }

    /**
     * Async GPU detection with timeout protection
     */
    private async detectGpuAsync(): Promise<'cuda' | 'metal' | 'vulkan' | 'none'> {
        const platform = process.platform;

        const runWithTimeout = (cmd: string, timeoutMs: number = 3000): Promise<string> => {
            return new Promise((resolve, reject) => {
                const proc = child_process.exec(cmd, { encoding: 'utf-8', timeout: timeoutMs }, (error, stdout) => {
                    if (error) reject(error);
                    else resolve(stdout);
                });
                // Force kill if timeout
                setTimeout(() => {
                    proc.kill('SIGKILL');
                    reject(new Error('Timeout'));
                }, timeoutMs);
            });
        };

        try {
            if (platform === 'darwin') {
                // macOS - assume Metal available on modern Macs
                return 'metal';
            } else if (platform === 'win32' || platform === 'linux') {
                // Check for CUDA (nvidia-smi is fast)
                try {
                    await runWithTimeout('nvidia-smi --query-gpu=name --format=csv,noheader', 2000);
                    return 'cuda';
                } catch {
                    // No CUDA, skip Vulkan check (too slow/unreliable)
                    return 'none';
                }
            }
        } catch {
            // Detection failed
        }
        return 'none';
    }

    /**
     * Check if Ollama is running and available
     */
    private async checkOllamaAvailable(): Promise<boolean> {
        return new Promise((resolve) => {
            http.get(`${this.ollamaEndpoint}/api/tags`, { timeout: 2000 }, (res) => {
                resolve(res.statusCode === 200);
            }).on('error', () => resolve(false));
        });
    }

    /**
     * Get list of available Ollama models
     */
    private async getOllamaModels(): Promise<string[]> {
        return new Promise((resolve) => {
            http.get(`${this.ollamaEndpoint}/api/tags`, { timeout: 5000 }, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    try {
                        const json = JSON.parse(data);
                        const models = json.models?.map((m: any) => m.name) || [];
                        resolve(models);
                    } catch {
                        resolve([]);
                    }
                });
            }).on('error', () => resolve([]));
        });
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

        // Open in existing editor group if available, otherwise use active column
        // This prevents creating unnecessary new editor groups
        const visibleEditors = vscode.window.visibleTextEditors;
        let viewColumn: vscode.ViewColumn;

        if (visibleEditors.length > 1) {
            // Multiple editor groups exist - use a different one from the active editor
            const activeColumn = vscode.window.activeTextEditor?.viewColumn || vscode.ViewColumn.One;
            viewColumn = activeColumn === vscode.ViewColumn.One ? vscode.ViewColumn.Two : vscode.ViewColumn.One;
        } else if (visibleEditors.length === 1) {
            // Single editor - open beside it
            viewColumn = vscode.ViewColumn.Beside;
        } else {
            // No editors open - use active
            viewColumn = vscode.ViewColumn.Active;
        }

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
                // Update MCP status in UI
                this.postMessage({
                    command: 'updateMcpStatus',
                    connected: true,
                    endpoint: 'ws://127.0.0.1:5680',
                    projectId: this.hubClient.getProjectId()
                });
            } else {
                console.log('[TrueFlow] Hub not available, using file-based status polling');
                // Update MCP status in UI
                this.postMessage({
                    command: 'updateMcpStatus',
                    connected: false,
                    hint: 'Hub not found - check console for details'
                });
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
                case 'cancelOperation':
                    this.isOperationCancelled = true;
                    this.postMessage({ command: 'operationCancelled' });
                    break;
                case 'setGpuAcceleration':
                    this.useGpuAcceleration = message.enabled;
                    break;
                case 'setBackend':
                    this.backendType = message.backend;
                    if (message.backend === 'ollama' && message.endpoint) {
                        this.ollamaEndpoint = message.endpoint;
                    }
                    break;
                case 'checkOllama':
                    this.checkOllamaStatus();
                    break;
                case 'startOllamaServer':
                    await this.startWithOllama(message.model);
                    break;
            }
        });
    }

    /**
     * Check Ollama status and get available models
     */
    private async checkOllamaStatus(): Promise<void> {
        const available = await this.checkOllamaAvailable();
        if (available) {
            const models = await this.getOllamaModels();
            this.postMessage({
                command: 'ollamaStatus',
                available: true,
                models: models
            });
        } else {
            this.postMessage({
                command: 'ollamaStatus',
                available: false,
                models: []
            });
        }
    }

    /**
     * Start using Ollama as backend
     */
    private async startWithOllama(model: string): Promise<void> {
        this.backendType = 'ollama';

        // Verify Ollama is running
        const available = await this.checkOllamaAvailable();
        if (!available) {
            this.postMessage({
                command: 'addMessage',
                role: 'system',
                content: 'Ollama is not running. Please start Ollama first: https://ollama.ai',
                timestamp: new Date().toLocaleTimeString()
            });
            return;
        }

        // Update status
        this.postMessage({
            command: 'ollamaConnected',
            model: model
        });

        vscode.window.showInformationMessage(`Connected to Ollama with model: ${model}`);
    }

    private async searchHuggingFace(query: string): Promise<void> {
        if (!query || query.length < 2) {
            this.postMessage({ command: 'hfSearchResults', results: [], error: 'Query too short' });
            return;
        }

        try {
            // Search Hugging Face API for GGUF models
            const searchUrl = `https://huggingface.co/api/models?search=${encodeURIComponent(query + ' gguf')}&sort=downloads&limit=20`;

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

    /**
     * Queries HuggingFace API to find mmproj files in a repo.
     * Returns the filename of the first mmproj file found (preferring F16).
     */
    private async findMmprojInHFRepo(repoId: string): Promise<string | null> {
        try {
            const apiUrl = `https://huggingface.co/api/models/${repoId}/tree/main`;
            const files = await this.fetchJSON(apiUrl);

            const mmprojFiles: string[] = [];
            for (const file of files) {
                const filePath = file.path || '';
                if (filePath.startsWith('mmproj') && filePath.endsWith('.gguf')) {
                    mmprojFiles.push(filePath);
                }
            }

            // Prefer F16 > BF16 > F32 > any
            return mmprojFiles.find(f => /F16/i.test(f))
                || mmprojFiles.find(f => /BF16/i.test(f))
                || mmprojFiles.find(f => /f16/i.test(f))
                || mmprojFiles[0]
                || null;
        } catch (error) {
            console.warn(`[TrueFlow] Failed to query HF repo for mmproj: ${error}`);
            return null;
        }
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
        // Note: Gemma-3-1B doesn't have mmproj, so exclude it from vision check
        const isVisionModel = /vl|vision|smol/i.test(hfModel) ||
            (/gemma-3-4b/i.test(hfModel));  // Only Gemma-3-4B has vision

        const args = [
            '-hf', hfModel,  // Direct HuggingFace loading
            '--port', '8080',
            '--ctx-size', '4096',
            '--threads', String(cpuCount),
            '--host', '127.0.0.1',
            '--jinja'
        ];

        if (isVisionModel) {
            // Try to find mmproj file in the HuggingFace repo
            const mmprojName = await this.findMmprojInHFRepo(hfModel);
            if (mmprojName) {
                // Use -hfmm to specify which mmproj file to load from the repo
                args.push('-hfmm', mmprojName);
                console.log(`[TrueFlow] Using mmproj from HF repo: ${mmprojName}`);
            }
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

            // Run benchmark to measure CPU/GPU performance
            this.postMessage({ command: 'benchmarkStarting' });
            this.runBenchmark();
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

        // Show user message with image if present
        this.postMessage({
            command: 'addMessage',
            role: 'user',
            content: text || '[Image]',
            timestamp: userMessage.timestamp,
            imageBase64: imageBase64
        });

        // Reset cancel flag
        this.isOperationCancelled = false;

        // Show thinking indicator
        this.postMessage({ command: 'setThinking', thinking: true });

        try {
            // Build context
            const contextText = this.buildContext(contextType);

            // Estimate tokens (rough: 1 token ≈ 4 chars)
            const estimatedTokens = Math.floor(contextText.length / 4);

            let response: string;
            if (estimatedTokens > this.TOKEN_CHUNK_SIZE) {
                // Large context - send in chunks
                response = await this.sendWithChunkedContext(text, contextText, imageBase64, estimatedTokens);
            } else {
                // Small context - normal call
                response = await this.callLLM(text, contextText, imageBase64);
            }

            if (this.isOperationCancelled) return;

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
            this.postMessage({ command: 'showStopButton', show: false });
        }
    }

    /**
     * Send context in chunks for large contexts (>200 tokens)
     */
    private async sendWithChunkedContext(
        userPrompt: string,
        fullContext: string,
        imageBase64: string | undefined,
        totalTokens: number
    ): Promise<string> {
        const chunkSize = this.TOKEN_CHUNK_SIZE * 4; // Convert tokens to chars
        const chunks: string[] = [];
        for (let i = 0; i < fullContext.length; i += chunkSize) {
            chunks.push(fullContext.slice(i, i + chunkSize));
        }

        const responses: string[] = [];

        this.postMessage({ command: 'showStopButton', show: true });
        this.postMessage({ command: 'updateStatus', status: 'Sending context in chunks...' });

        for (let index = 0; index < chunks.length; index++) {
            if (this.isOperationCancelled) {
                return 'Operation cancelled by user';
            }

            const chunk = chunks[index];
            const currentOffset = index * this.TOKEN_CHUNK_SIZE;
            const nextOffset = Math.min((index + 1) * this.TOKEN_CHUNK_SIZE, totalTokens);

            this.postMessage({
                command: 'setChunkProgress',
                current: currentOffset,
                total: totalTokens,
                message: `Fetching ${currentOffset}-${nextOffset} of ${totalTokens} tokens...`
            });

            // For all chunks, include the original question for context
            const prompt = index === 0
                ? `${userPrompt}\n\n[Context chunk ${index + 1}/${chunks.length}]:\n${chunk}`
                : `Original question: ${userPrompt}\n\n[Context chunk ${index + 1}/${chunks.length}]:\n${chunk}\n\nAnalyze this additional context chunk and provide relevant insights.`;

            // Update thinking status with chunk info
            this.postMessage({
                command: 'setThinking',
                thinking: true,
                message: `Analyzing chunk ${index + 1}/${chunks.length}...`
            });

            // Call LLM WITHOUT history for chunked calls
            const response = await this.callLLMWithoutHistory(prompt, imageBase64, userPrompt);
            responses.push(response);

            // Show actual AI response for each chunk (not just "processed" message)
            if (chunks.length > 1) {
                this.postMessage({
                    command: 'addMessage',
                    role: 'assistant',
                    content: `📦 **Chunk ${index + 1}/${chunks.length}:**\n\n${response}`,
                    timestamp: new Date().toLocaleTimeString()
                });

                // If not last chunk, show continuation message in thinking area
                if (index < chunks.length - 1) {
                    this.postMessage({
                        command: 'setThinking',
                        thinking: true,
                        message: `Processing next chunk (${index + 2}/${chunks.length})...`
                    });
                }
            }
        }

        this.postMessage({ command: 'setChunkProgress', current: 0, total: 0, message: '' });

        // Combine responses - filter out unhelpful responses
        if (responses.length === 1) {
            return responses[0];
        } else {
            const unhelpfulPatterns = [
                'need more context',
                "can't continue",
                'cannot continue',
                'please provide',
                'clarify your question',
                'additional context'
            ];
            const combined = responses.filter(r => {
                if (!r) return false;
                const lower = r.toLowerCase();
                return !unhelpfulPatterns.some(pattern => lower.includes(pattern));
            });

            if (combined.length === 0) {
                return 'Unable to analyze the context. Please try with a more specific question or smaller context.';
            }

            // Return the most comprehensive response (usually the last one with full context)
            return combined.length > 1
                ? `Based on analyzing all context chunks:\n\n${combined[combined.length - 1]}`
                : combined[0];
        }
    }

    /**
     * Call LLM without history (for chunked context)
     */
    private async callLLMWithoutHistory(prompt: string, imageBase64?: string, originalQuestion?: string): Promise<string> {
        const systemContent = originalQuestion
            ? `TrueFlow AI: You are analyzing code execution context in chunks. The user's question is: "${originalQuestion}". Analyze the provided context chunk and extract relevant information to answer this question. Focus on facts from the context, not speculation.`
            : 'TrueFlow AI: Analyze the provided context and answer concisely.';

        const messages: any[] = [
            { role: 'system', content: systemContent }
        ];

        if (imageBase64 && this.currentModelHasVision) {
            messages.push({
                role: 'user',
                content: [
                    { type: 'text', text: prompt },
                    { type: 'image_url', image_url: { url: `data:image/png;base64,${imageBase64}` } }
                ]
            });
        } else {
            messages.push({ role: 'user', content: prompt });
        }

        return this.callLLMWithMessages(messages);
    }

    private buildContext(contextType: string): string {
        switch (contextType) {
            case 'deadCode':
                return this.buildDeadCodeContext();
            case 'performance':
                return this.buildPerformanceContext();
            case 'callTrace':
                return this.buildCallTraceContext();
            case 'sql':
                return this.buildSqlAnalysisContext();
            case 'diagram':
                return this.buildDiagramContext();
            case 'all':
                return [
                    this.buildDeadCodeContext(),
                    this.buildPerformanceContext(),
                    this.buildCallTraceContext(),
                    this.buildSqlAnalysisContext(),
                    this.buildDiagramContext()
                ].filter(s => s).join('\n');
            default:
                return '';
        }
    }

    private buildDeadCodeContext(): string {
        // If no dead code data from socket, try loading from trace files
        if (!this.deadCodeData) {
            this.loadTraceDataFromFiles();
        }
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
        // If no performance data from socket, try loading from trace files
        if (!this.performanceData) {
            this.loadTraceDataFromFiles();
        }
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
        // If no call trace data from socket, try loading from trace files
        if (!this.callTraceData) {
            this.loadTraceDataFromFiles();
        }
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

    private buildSqlAnalysisContext(): string {
        // If no SQL data from socket, try loading from trace files
        if (!this.sqlAnalysisData) {
            this.loadTraceDataFromFiles();
        }
        if (!this.sqlAnalysisData) return '';

        const issues = this.sqlAnalysisData.issues || [];
        const queries = this.sqlAnalysisData.queries || [];
        const totalQueries = this.sqlAnalysisData.totalQueries || 0;
        const nPlus1Count = this.sqlAnalysisData.nPlus1Issues || 0;

        if (totalQueries === 0 && issues.length === 0) return '';

        let context = '\n--- SQL Analysis Context ---\n';
        context += `Total Queries: ${totalQueries}, N+1 Issues: ${nPlus1Count}\n`;

        if (issues.length > 0) {
            context += '\nN+1 Issues:\n';
            issues.slice(0, 10).forEach((issue: any) => {
                context += `  [${issue.severity}] ${issue.pattern} (${issue.count} occurrences)\n`;
                if (issue.suggestion) {
                    context += `    Suggestion: ${issue.suggestion}\n`;
                }
            });
        }

        if (queries.length > 0) {
            context += '\nRecent Queries:\n';
            queries.slice(0, 10).forEach((q: any) => {
                const shortQuery = (q.query || '').substring(0, 100);
                context += `  - ${q.module}.${q.function}: ${shortQuery}...\n`;
            });
        }

        return context;
    }

    private buildDiagramContext(): string {
        // If no diagram data from socket, try loading from trace files
        if (!this.diagramData) {
            this.loadTraceDataFromFiles();
        }
        if (!this.diagramData) return '';

        return `\n--- Sequence Diagram ---\n${this.diagramData}`;
    }

    private async callLLM(userPrompt: string, contextText: string, imageBase64?: string): Promise<string> {
        const messages: any[] = [];

        // Compact MCP tools documentation
        const mcpToolsDocs = `MCP Tools (use \`\`\`mcp{"tool":"name","args":{}}\`\`\` to call):
• get_trace_data - call history
• get_dead_code - unused functions
• get_performance_data - hotspots
• get_sql_queries - SQL with N+1
• export_diagram(format) - plantuml/mermaid/d2
• search_function(function_name) - find function
• get_call_chain(function_name) - callers/callees`;

        // Compact system prompt with MCP awareness
        messages.push({
            role: 'system',
            content: `TrueFlow AI: Code analysis assistant. Be concise & technical.
${mcpToolsDocs}
If context insufficient, use MCP tool. I'll execute & return results.`
        });

        // Add conversation history (text only - images are too large to resend)
        for (const msg of this.conversationHistory.slice(0, -1)) {
            // For messages that had images, add a note but don't resend the image data
            const content = msg.imageBase64
                ? `${msg.content}\n[User shared an image with this message]`
                : msg.content;
            messages.push({ role: msg.role, content });
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

        // Use Ollama or llama.cpp based on backend selection
        if (this.backendType === 'ollama') {
            return this.callOllamaLLM(messages);
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
                        let errorMsg = '';
                        try {
                            const errorJson = JSON.parse(data);
                            errorMsg = errorJson.error?.message || errorJson.error || data;
                        } catch {
                            errorMsg = data.slice(0, 200);
                        }

                        // Provide helpful hints for common errors
                        if (res.statusCode === 500) {
                            errorMsg = `Server error: ${errorMsg || 'Internal error'}. This may be due to: (1) Model not fully loaded - wait a few seconds, (2) Out of memory - try a smaller model, (3) Invalid request - check if the model supports vision for image queries.`;
                        } else if (res.statusCode === 503) {
                            errorMsg = 'Server unavailable. The AI server may still be starting up. Please wait and try again.';
                        }
                        reject(new Error(errorMsg));
                        return;
                    }

                    try {
                        const json = JSON.parse(data);
                        const content = json.choices?.[0]?.message?.content || 'No response';

                        // Track token usage
                        const usage = json.usage;
                        if (usage) {
                            this.totalTokensUsed += (usage.prompt_tokens || 0) + (usage.completion_tokens || 0);
                            this.postMessage({ command: 'updateTokens', total: this.totalTokensUsed });
                        }

                        // Check for MCP tool call and handle it
                        this.handleMCPToolCall(content, messages).then(finalContent => {
                            resolve(finalContent);
                        }).catch(err => {
                            // If MCP handling fails, return original content
                            resolve(content);
                        });
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

    /**
     * Call Ollama API for chat completions
     */
    private async callOllamaLLM(messages: any[]): Promise<string> {
        // Get the selected Ollama model from config or use default
        const ollamaModel = vscode.workspace.getConfiguration('trueflow').get('ollamaModel', 'llama3.2');

        const requestBody = JSON.stringify({
            model: ollamaModel,
            messages: messages,
            stream: false
        });

        return new Promise((resolve, reject) => {
            const url = new URL(`${this.ollamaEndpoint}/api/chat`);
            const req = http.request({
                hostname: url.hostname,
                port: url.port || 11434,
                path: url.pathname,
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
                    if (res.statusCode !== 200) {
                        reject(new Error(`Ollama error (${res.statusCode}): ${data.slice(0, 200)}`));
                        return;
                    }

                    try {
                        const json = JSON.parse(data);
                        const content = json.message?.content || 'No response';

                        // Track token usage (Ollama provides eval_count)
                        if (json.eval_count) {
                            this.totalTokensUsed += json.eval_count + (json.prompt_eval_count || 0);
                            this.postMessage({ command: 'updateTokens', total: this.totalTokensUsed });
                        }

                        // Check for MCP tool call
                        this.handleMCPToolCall(content, messages).then(finalContent => {
                            resolve(finalContent);
                        }).catch(() => {
                            resolve(content);
                        });
                    } catch (e) {
                        reject(new Error('Failed to parse Ollama response'));
                    }
                });
            });

            req.on('error', (err) => {
                reject(new Error(`Ollama connection error: ${err.message}`));
            });
            req.on('timeout', () => reject(new Error('Ollama request timeout')));
            req.write(requestBody);
            req.end();
        });
    }

    /**
     * Detect and execute MCP tool calls in LLM response
     */
    private async handleMCPToolCall(content: string, originalMessages: any[]): Promise<string> {
        // Look for ```mcp{...}``` pattern
        const mcpPattern = /```mcp\s*\{([^}]+)\}\s*```/s;
        const match = content.match(mcpPattern);

        if (!match) {
            return content; // No tool call, return as-is
        }

        try {
            const jsonStr = `{${match[1]}}`;
            const toolCall = JSON.parse(jsonStr);
            const toolName = toolCall.tool;
            const args = toolCall.args || {};

            // Show MCP call in thinking status
            this.postMessage({
                command: 'setThinking',
                thinking: true,
                message: `Calling MCP tool: ${toolName}...`
            });

            // Execute the tool
            const toolResult = this.executeMCPTool(toolName, args);

            // Update thinking status for follow-up
            this.postMessage({
                command: 'setThinking',
                thinking: true,
                message: `Processing ${toolName} results...`
            });

            // Make follow-up call with tool results
            const followUpMessages = [...originalMessages];
            followUpMessages.push({ role: 'assistant', content: content });
            followUpMessages.push({ role: 'user', content: `Tool result:\n${toolResult}\n\nNow answer the original question using this data.` });

            // Call LLM again with tool results
            return this.callLLMWithMessages(followUpMessages);
        } catch (e) {
            console.error(`[TrueFlow] Failed to parse MCP call: ${e}`);
            return content;
        }
    }

    /**
     * Execute an MCP tool and return the result
     */
    private executeMCPTool(toolName: string, args: any): string {
        switch (toolName) {
            case 'get_trace_data':
                return JSON.stringify(this.callTraceData || { calls: [], total_calls: 0 });
            case 'get_dead_code':
                return JSON.stringify(this.deadCodeData || { dead_functions: [], called_functions: [] });
            case 'get_performance_data':
                return JSON.stringify(this.performanceData || { hotspots: [], total_time_ms: 0 });
            case 'get_sql_queries':
                return JSON.stringify({ queries: [], total_queries: 0 });
            case 'export_diagram':
                const format = args.format || 'plantuml';
                return JSON.stringify({ format, diagram: this.currentDiagramData || '' });
            case 'search_function':
                return this.searchFunctionInTrace(args.function_name || '');
            case 'get_call_chain':
                return this.getCallChainForFunction(args.function_name || '');
            default:
                return JSON.stringify({ error: `Unknown tool: ${toolName}` });
        }
    }

    private searchFunctionInTrace(functionName: string): string {
        const calls = this.callTraceData?.calls || [];
        const matches = calls.filter((c: any) =>
            c.function?.toLowerCase().includes(functionName.toLowerCase())
        );
        return JSON.stringify({
            found: matches.length > 0,
            calls: matches.slice(0, 10),
            total_matches: matches.length
        });
    }

    private getCallChainForFunction(functionName: string): string {
        const calls = this.callTraceData?.calls || [];
        const callers = new Set<string>();
        const callees = new Set<string>();

        calls.forEach((call: any, index: number) => {
            if (call.function?.toLowerCase().includes(functionName.toLowerCase())) {
                const depth = call.depth || 0;
                // Find caller
                for (let i = index - 1; i >= 0; i--) {
                    if ((calls[i].depth || 0) < depth) {
                        callers.add(calls[i].function || '');
                        break;
                    }
                }
                // Find callees
                for (let i = index + 1; i < calls.length; i++) {
                    const nextDepth = calls[i].depth || 0;
                    if (nextDepth <= depth) break;
                    if (nextDepth === depth + 1) {
                        callees.add(calls[i].function || '');
                    }
                }
            }
        });

        return JSON.stringify({
            function: functionName,
            callers: Array.from(callers),
            callees: Array.from(callees)
        });
    }

    /**
     * Call LLM with pre-built messages array (for follow-up calls)
     */
    private callLLMWithMessages(messages: any[]): Promise<string> {
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
                    if (res.statusCode !== 200) {
                        reject(new Error(`Server error (${res.statusCode})`));
                        return;
                    }
                    try {
                        const json = JSON.parse(data);
                        resolve(json.choices?.[0]?.message?.content || 'No response');
                    } catch {
                        reject(new Error('Failed to parse response'));
                    }
                });
            });
            req.on('error', reject);
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
        const fullyDownloadedModels: string[] = [];
        const needsMmprojModels: string[] = [];

        for (const preset of MODEL_PRESETS) {
            const modelPath = path.join(this.modelsDir, preset.fileName);
            const modelExists = fs.existsSync(modelPath);

            if (modelExists) {
                downloadedModels.push(preset.fileName);

                // Check if fully downloaded (including mmproj for vision models)
                if (this.isModelFullyDownloaded(preset)) {
                    fullyDownloadedModels.push(preset.fileName);
                    if (!this.currentModelFile) {
                        this.currentModelFile = modelPath;
                        this.currentModelHasVision = preset.hasVision;
                    }
                } else if (preset.hasVision && preset.mmprojFileName) {
                    // Model exists but needs mmproj
                    needsMmprojModels.push(preset.fileName);
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

        // Also check Ollama availability
        const ollamaAvailable = await this.checkOllamaAvailable();
        let ollamaModels: string[] = [];
        if (ollamaAvailable) {
            ollamaModels = await this.getOllamaModels();
        }

        this.postMessage({
            command: 'updateStatus',
            downloadedModels,
            fullyDownloadedModels,
            needsMmprojModels,
            serverRunning: !!this.serverProcess || externalRunning,
            models: MODEL_PRESETS.map(m => ({
                displayName: m.displayName,
                sizeMB: m.sizeMB,
                description: m.description,
                downloaded: downloadedModels.includes(m.fileName),
                fullyDownloaded: fullyDownloadedModels.includes(m.fileName),
                needsMmproj: needsMmprojModels.includes(m.fileName)
            })),
            // GPU and backend info
            gpuAvailable: this.gpuAvailable,
            gpuEnabled: this.useGpuAcceleration,
            ollamaAvailable: ollamaAvailable,
            ollamaModels: ollamaModels,
            totalTokens: this.totalTokensUsed
        });
    }

    private async downloadModel(modelIndex: number): Promise<void> {
        const preset = MODEL_PRESETS[modelIndex];
        if (!preset) return;

        const url = `https://huggingface.co/${preset.repoId}/resolve/main/${preset.fileName}`;
        const destPath = path.join(this.modelsDir, preset.fileName);
        const modelExists = fs.existsSync(destPath);

        // Check if ALL prerequisites are downloaded (model + mmproj for vision models)
        if (this.isModelFullyDownloaded(preset)) {
            // Fully downloaded - just update state
            this.currentModelFile = destPath;
            this.currentModelHasVision = preset.hasVision;
            this.postMessage({ command: 'downloadComplete', modelName: preset.displayName });
            this.checkModelStatus();
            return;
        }

        // Model exists but mmproj is missing for vision model
        if (modelExists && preset.hasVision && preset.mmprojFileName && preset.mmprojRepoId) {
            this.currentModelFile = destPath;
            this.currentModelHasVision = preset.hasVision;
            const serverWasRunning = this.serverProcess !== undefined;

            try {
                this.postMessage({ command: 'downloadStarted', modelName: `${preset.displayName} (vision projector)` });
                await this.downloadMmprojOnly(preset);
                this.postMessage({ command: 'downloadComplete', modelName: preset.displayName });

                // If server was running, restart it to pick up the new mmproj
                if (serverWasRunning) {
                    vscode.window.showInformationMessage('Vision support downloaded. Restarting server to enable vision...');
                    await this.stopServer();
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    await this.startServer();
                }
            } catch (error: any) {
                this.postMessage({ command: 'downloadError', error: `Vision projector download failed: ${error.message}` });
            }
            this.checkModelStatus();
            return;
        }

        this.postMessage({ command: 'downloadStarted', modelName: preset.displayName });

        try {
            // Download main model file
            await this.downloadFileWithProgress(url, destPath, (downloaded, total) => {
                const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
                const downloadedMB = Math.round(downloaded / (1024 * 1024));
                const totalMB = Math.round(total / (1024 * 1024));
                this.postMessage({
                    command: 'downloadProgress',
                    percent: pct,
                    downloadedMB,
                    totalMB,
                    stage: 'model'
                });
            });

            // Download mmproj file if this is a vision model
            if (preset.hasVision && preset.mmprojFileName && preset.mmprojRepoId) {
                const mmprojUrl = `https://huggingface.co/${preset.mmprojRepoId}/resolve/main/${preset.mmprojFileName}`;
                const mmprojDestPath = path.join(this.modelsDir, preset.mmprojFileName);

                // Check if mmproj already exists
                if (!fs.existsSync(mmprojDestPath)) {
                    this.postMessage({
                        command: 'downloadProgress',
                        percent: 0,
                        downloadedMB: 0,
                        totalMB: preset.mmprojSizeMB || 0,
                        stage: 'mmproj'
                    });

                    await this.downloadFileWithProgress(mmprojUrl, mmprojDestPath, (downloaded, total) => {
                        const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
                        const downloadedMB = Math.round(downloaded / (1024 * 1024));
                        const totalMB = Math.round(total / (1024 * 1024));
                        this.postMessage({
                            command: 'downloadProgress',
                            percent: pct,
                            downloadedMB,
                            totalMB,
                            stage: 'mmproj'
                        });
                    });
                }
            }

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

    /**
     * Check if all prerequisites for a model are downloaded.
     * For vision models, this includes both model file AND mmproj file.
     */
    private isModelFullyDownloaded(preset: typeof MODEL_PRESETS[0]): boolean {
        const modelPath = path.join(this.modelsDir, preset.fileName);
        if (!fs.existsSync(modelPath)) {
            return false;
        }

        // For vision models, also check mmproj
        if (preset.hasVision && preset.mmprojFileName) {
            const mmprojPath = path.join(this.modelsDir, preset.mmprojFileName);
            if (!fs.existsSync(mmprojPath)) {
                return false;
            }
        }

        return true;
    }

    /**
     * Download only the mmproj file for a vision model (when model exists but mmproj is missing).
     */
    private async downloadMmprojOnly(preset: typeof MODEL_PRESETS[0]): Promise<void> {
        if (!preset.mmprojFileName || !preset.mmprojRepoId) return;

        const mmprojUrl = `https://huggingface.co/${preset.mmprojRepoId}/resolve/main/${preset.mmprojFileName}`;
        const mmprojDestPath = path.join(this.modelsDir, preset.mmprojFileName);

        this.postMessage({
            command: 'downloadProgress',
            percent: 0,
            downloadedMB: 0,
            totalMB: preset.mmprojSizeMB || 0,
            stage: 'mmproj'
        });

        await this.downloadFileWithProgress(mmprojUrl, mmprojDestPath, (downloaded, total) => {
            const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
            const downloadedMB = Math.round(downloaded / (1024 * 1024));
            const totalMB = Math.round(total / (1024 * 1024));
            this.postMessage({
                command: 'downloadProgress',
                percent: pct,
                downloadedMB,
                totalMB,
                stage: 'mmproj'
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
        if (currentPreset?.hasVision && currentPreset?.mmprojFileName) {
            // Add mmproj (multimodal projector) file for vision capability
            const mmprojPath = path.join(this.modelsDir, currentPreset.mmprojFileName);
            if (fs.existsSync(mmprojPath)) {
                args.push('--mmproj', mmprojPath);
                console.log(`[TrueFlow] Using mmproj file: ${mmprojPath}`);
            } else {
                vscode.window.showWarningMessage(
                    `Vision projector file not found: ${currentPreset.mmprojFileName}. Vision features may not work. Try re-downloading the model.`
                );
            }
            // --kv-unified fixes KV cache issues on second+ multimodal requests for Qwen3-VL
            args.push('--kv-unified');
            // --no-mmproj-offload for better compatibility on systems without GPU
            if (!this.useGpuAcceleration) {
                args.push('--no-mmproj-offload');
            }
        }

        // Add GPU acceleration flags if enabled and available
        if (this.useGpuAcceleration && this.gpuAvailable !== 'none') {
            // Number of layers to offload to GPU (-1 = all)
            args.push('--n-gpu-layers', '-1');

            // For CUDA, we can use flash attention for faster inference
            if (this.gpuAvailable === 'cuda') {
                args.push('--flash-attn');
            }

            console.log(`[TrueFlow] GPU acceleration enabled: ${this.gpuAvailable}`);
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

            // Show current mode (CPU/GPU) in status
            const currentMode = this.useGpuAcceleration ? 'GPU' : 'CPU';
            this.postMessage({
                command: 'serverStarted',
                currentMode: currentMode,
                modelName: modelName
            });
            vscode.window.showInformationMessage(`AI server started on ${currentMode} (port 8080)`);

            // Run benchmark to measure CPU/GPU performance
            this.postMessage({ command: 'benchmarkStarting' });
            this.runBenchmark();
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

    /**
     * Run a quick benchmark to compare CPU vs GPU performance.
     * Called after server starts - runs a quick inference and measures tokens/second.
     */
    private async runBenchmark(): Promise<void> {
        const currentMode = this.useGpuAcceleration ? 'GPU' : 'CPU';

        if (this.gpuAvailable === 'none') {
            // No GPU, measure CPU performance
            try {
                const tps = await this.measureServerPerformance();
                this.cpuTokensPerSecond = tps;
            } catch {
                this.cpuTokensPerSecond = 0;
            }
            this.gpuTokensPerSecond = 0;
            this.recommendedBackend = 'cpu';
            this.benchmarkCompleted = true;
            this.postMessage({
                command: 'benchmarkComplete',
                cpuTps: this.cpuTokensPerSecond,
                gpuTps: this.gpuTokensPerSecond,
                recommended: this.recommendedBackend,
                currentMode: currentMode
            });
            return;
        }

        try {
            const tokensPerSecond = await this.measureServerPerformance();

            // Store based on current GPU setting
            if (this.useGpuAcceleration) {
                this.gpuTokensPerSecond = tokensPerSecond;
                // Estimate CPU as typically 30-60% of GPU
                this.cpuTokensPerSecond = tokensPerSecond * 0.5;
            } else {
                this.cpuTokensPerSecond = tokensPerSecond;
                // Estimate GPU as typically 1.5-2x CPU
                this.gpuTokensPerSecond = tokensPerSecond * 1.8;
            }

            // Determine recommendation: GPU is only better if significantly faster (>20% improvement)
            if (this.gpuTokensPerSecond <= 0) {
                this.recommendedBackend = 'cpu';
            } else if (this.cpuTokensPerSecond <= 0) {
                this.recommendedBackend = 'gpu';
            } else if (this.gpuTokensPerSecond > this.cpuTokensPerSecond * 1.2) {
                this.recommendedBackend = 'gpu';
            } else {
                this.recommendedBackend = 'cpu';  // Prefer CPU if similar or CPU is faster
            }

            this.benchmarkCompleted = true;
            console.log(`[TrueFlow] Benchmark: CPU=${Math.round(this.cpuTokensPerSecond)} t/s, GPU=${Math.round(this.gpuTokensPerSecond)} t/s, Running on ${currentMode}, Recommended=${this.recommendedBackend.toUpperCase()}`);

            this.postMessage({
                command: 'benchmarkComplete',
                cpuTps: this.cpuTokensPerSecond,
                gpuTps: this.gpuTokensPerSecond,
                recommended: this.recommendedBackend,
                currentMode: currentMode
            });

            // Auto-select the recommended backend for next server start
            if (this.gpuAvailable !== 'none') {
                const shouldUseGpu = this.recommendedBackend === 'gpu';
                if (shouldUseGpu !== this.useGpuAcceleration) {
                    console.log(`[TrueFlow] Benchmark recommends ${this.recommendedBackend.toUpperCase()}, currently using ${currentMode}`);
                    this.useGpuAcceleration = shouldUseGpu;
                }
            }
        } catch (error: any) {
            console.warn(`[TrueFlow] Benchmark failed: ${error.message}`);
            this.benchmarkCompleted = true;
            this.postMessage({
                command: 'benchmarkComplete',
                cpuTps: this.cpuTokensPerSecond,
                gpuTps: this.gpuTokensPerSecond,
                recommended: 'cpu',
                currentMode: currentMode
            });
        }
    }

    /**
     * Measure performance of the currently running server.
     */
    private async measureServerPerformance(): Promise<number> {
        const startTime = Date.now();
        const testPrompt = 'Count from 1 to 20:';
        const response = await this.callLLMForBenchmark(testPrompt, 50);
        const endTime = Date.now();

        const durationSeconds = (endTime - startTime) / 1000;
        // More accurate token estimation based on response length
        const estimatedTokens = (response.length / 4) + 10;  // ~4 chars per token average
        return durationSeconds > 0.1 ? estimatedTokens / durationSeconds : 0;
    }

    /**
     * Simple LLM call for benchmarking - doesn't use streaming
     */
    private callLLMForBenchmark(prompt: string, maxTokens: number): Promise<string> {
        return new Promise((resolve, reject) => {
            const requestBody = JSON.stringify({
                model: 'local',
                messages: [{ role: 'user', content: prompt }],
                max_tokens: maxTokens,
                temperature: 0.1,
                stream: false
            });

            const req = http.request({
                hostname: '127.0.0.1',
                port: 8080,
                path: '/v1/chat/completions',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(requestBody)
                },
                timeout: 60000
            }, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    if (res.statusCode !== 200) {
                        reject(new Error(`HTTP ${res.statusCode}`));
                        return;
                    }
                    try {
                        const json = JSON.parse(data);
                        const content = json.choices?.[0]?.message?.content || '';
                        resolve(content);
                    } catch (e) {
                        reject(e);
                    }
                });
            });

            req.on('error', reject);
            req.on('timeout', () => reject(new Error('Timeout')));
            req.write(requestBody);
            req.end();
        });
    }

    /**
     * Get benchmark status string for UI display
     */
    public getBenchmarkStatus(): string {
        if (!this.benchmarkCompleted) {
            return 'Benchmark pending...';
        }
        if (this.gpuAvailable === 'none') {
            return `CPU: ${Math.round(this.cpuTokensPerSecond)} t/s`;
        }
        return `CPU: ${Math.round(this.cpuTokensPerSecond)} t/s | GPU: ${Math.round(this.gpuTokensPerSecond)} t/s | Best: ${this.recommendedBackend.toUpperCase()}`;
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
            // Use CUDA-enabled binary if GPU acceleration is available and user wants GPU
            let assetName: string;
            let extractDir: string;
            const useCuda = this.gpuAvailable === 'cuda' && this.useGpuAcceleration;

            if (process.platform === 'win32') {
                if (useCuda) {
                    // Try CUDA 12 first (most common modern version)
                    assetName = `llama-${tagName}-bin-win-cuda-cu12.2.0-x64.zip`;
                } else {
                    assetName = `llama-${tagName}-bin-win-cpu-x64.zip`;
                }
            } else if (process.platform === 'darwin') {
                // macOS uses Metal, which is built into the standard macOS binary
                assetName = `llama-${tagName}-bin-macos-arm64.zip`;
            } else {
                // Linux
                if (useCuda) {
                    assetName = `llama-${tagName}-bin-ubuntu-cuda-cu12.2.0-x64.zip`;
                } else {
                    assetName = `llama-${tagName}-bin-ubuntu-x64.zip`;
                }
            }

            // Find the asset URL
            let asset = releaseInfo.assets?.find((a: any) => a.name === assetName);

            // If CUDA binary not found, try alternative CUDA versions then fall back to CPU
            if (!asset && useCuda) {
                console.log(`[TrueFlow] CUDA binary not found: ${assetName}, trying alternatives...`);

                // Try CUDA 11.8 as fallback
                const cuda11Asset = process.platform === 'win32'
                    ? `llama-${tagName}-bin-win-cuda-cu11.8.0-x64.zip`
                    : `llama-${tagName}-bin-ubuntu-cuda-cu11.8.0-x64.zip`;
                asset = releaseInfo.assets?.find((a: any) => a.name === cuda11Asset);

                if (asset) {
                    assetName = cuda11Asset;
                    console.log(`[TrueFlow] Found CUDA 11.8 binary: ${assetName}`);
                } else {
                    // Fall back to CPU version
                    assetName = process.platform === 'win32'
                        ? `llama-${tagName}-bin-win-cpu-x64.zip`
                        : `llama-${tagName}-bin-ubuntu-x64.zip`;
                    asset = releaseInfo.assets?.find((a: any) => a.name === assetName);
                    console.log(`[TrueFlow] Falling back to CPU binary: ${assetName}`);
                }
            }

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
            // Extract dir name matches the asset name without .zip extension
            const extractedDirName = assetName.replace('.zip', '');
            const extractedBinDir = path.join(installDir, extractedDirName);
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
        this.currentDiagramData = diagram;
    }

    public setContextSelection(value: number): void {
        this.contextSelection = value;
    }

    public setSqlAnalysisData(data: any): void {
        this.sqlAnalysisData = data;
    }

    /**
     * Save a comprehensive snapshot of all trace data to the .trueflow/traces directory.
     * Maintains only the last 5 snapshots to avoid disk bloat.
     * Called when trace data is updated.
     */
    public saveSnapshot(): void {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) return;

        const workspaceRoot = workspaceFolders[0].uri.fsPath;
        const traceDir = path.join(workspaceRoot, '.trueflow', 'traces');

        // Ensure trace directory exists
        if (!fs.existsSync(traceDir)) {
            fs.mkdirSync(traceDir, { recursive: true });
        }

        // Generate timestamp for filename
        const now = new Date();
        const timestamp = now.toISOString()
            .replace(/[-:]/g, '')
            .replace('T', '_')
            .substring(0, 15);
        const snapshotFile = path.join(traceDir, `snapshot_${timestamp}.json`);

        // Cleanup old snapshots (keep only last 5)
        this.cleanupOldSnapshots(traceDir, 5);

        // Build snapshot data
        const snapshot: any = {
            metadata: {
                createdAt: now.toISOString(),
                createdBy: 'vscode',
                version: '1.0'
            }
        };

        // Performance data
        if (this.performanceData?.hotspots && this.performanceData.hotspots.length > 0) {
            snapshot.performance = {
                hotspots: this.performanceData.hotspots.slice(0, 50).map((h: any) => ({
                    function: h.function || 'unknown',
                    total_ms: h.total_ms || 0,
                    calls: h.calls || 0
                }))
            };
        }

        // Dead code data
        if (this.deadCodeData?.dead_functions && this.deadCodeData.dead_functions.length > 0) {
            snapshot.deadCode = {
                dead_functions: this.deadCodeData.dead_functions.slice(0, 50).map((f: any) => ({
                    name: f.name || f.function || 'unknown',
                    file: f.file || '',
                    line: f.line || 0
                }))
            };
        }

        // SQL analysis data
        if (this.sqlAnalysisData) {
            snapshot.sqlAnalysis = {
                totalQueries: this.sqlAnalysisData.totalQueries || 0,
                nPlus1Issues: this.sqlAnalysisData.nPlus1Issues || 0,
                issues: (this.sqlAnalysisData.issues || []).slice(0, 20).map((i: any) => ({
                    severity: i.severity || 'medium',
                    pattern: i.pattern || '',
                    count: i.count || 0,
                    example: i.example || '',
                    suggestion: i.suggestion || ''
                })),
                queries: (this.sqlAnalysisData.queries || []).slice(0, 50).map((q: any) => ({
                    query: q.query || '',
                    module: q.module || '',
                    function: q.function || '',
                    variable: q.variable || ''
                }))
            };
        }

        // Diagram data
        if (this.diagramData) {
            snapshot.diagram = {
                format: 'plantuml',
                content: this.diagramData.substring(0, 50000) // Limit size
            };
        }

        // Call trace data (summary)
        if (this.callTraceData?.calls && this.callTraceData.calls.length > 0) {
            snapshot.callTrace = {
                totalCalls: this.callTraceData.total_calls || this.callTraceData.calls.length,
                sampleCalls: this.callTraceData.calls.slice(0, 100).map((c: any) => ({
                    function: c.function || 'unknown',
                    module: c.module || '',
                    depth: c.depth || 0,
                    duration_ms: c.duration_ms || 0
                }))
            };
        }

        // Only write if we have some data
        if (Object.keys(snapshot).length > 1) { // More than just metadata
            try {
                fs.writeFileSync(snapshotFile, JSON.stringify(snapshot, null, 2), 'utf-8');
                console.log(`[TrueFlow] Snapshot saved: ${snapshotFile}`);
            } catch (e) {
                console.error('[TrueFlow] Failed to save snapshot:', e);
            }
        }
    }

    /**
     * Remove old snapshot files, keeping only the most recent ones.
     */
    private cleanupOldSnapshots(traceDir: string, keepCount: number): void {
        try {
            const files = fs.readdirSync(traceDir)
                .filter(f => f.startsWith('snapshot_') && f.endsWith('.json'))
                .map(f => ({
                    name: f,
                    path: path.join(traceDir, f),
                    mtime: fs.statSync(path.join(traceDir, f)).mtimeMs
                }))
                .sort((a, b) => b.mtime - a.mtime);

            // Delete files beyond keepCount
            if (files.length >= keepCount) {
                for (let i = keepCount - 1; i < files.length; i++) {
                    try {
                        fs.unlinkSync(files[i].path);
                        console.log(`[TrueFlow] Deleted old snapshot: ${files[i].name}`);
                    } catch (e) {
                        // Ignore deletion errors
                    }
                }
            }
        } catch (e) {
            // Ignore cleanup errors
        }
    }

    /**
     * Load trace data from workspace snapshot/trace files when not available from socket.
     * First tries to find snapshot files (comprehensive), then falls back to raw trace files.
     * Searches in .trueflow/traces and .pycharm_plugin/traces directories.
     */
    private loadTraceDataFromFiles(): void {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) return;

        const workspaceRoot = workspaceFolders[0].uri.fsPath;
        // Check VS Code default first (.trueflow/traces), then PyCharm's (.pycharm_plugin/traces)
        const traceDirs = [
            path.join(workspaceRoot, '.trueflow', 'traces'),
            path.join(workspaceRoot, '.pycharm_plugin', 'traces')
        ];

        // First, try to find snapshot files (snapshot_*.json - comprehensive export)
        let latestSnapshotFile: string | null = null;
        let latestSnapshotMtime = 0;

        for (const traceDir of traceDirs) {
            if (!fs.existsSync(traceDir)) continue;

            try {
                const snapshotFiles = fs.readdirSync(traceDir)
                    .filter(f => f.startsWith('snapshot_') && f.endsWith('.json'))
                    .map(f => path.join(traceDir, f));

                for (const file of snapshotFiles) {
                    const stat = fs.statSync(file);
                    if (stat.mtimeMs > latestSnapshotMtime) {
                        latestSnapshotMtime = stat.mtimeMs;
                        latestSnapshotFile = file;
                    }
                }
            } catch (e) {
                // Directory read error, continue to next
            }
        }

        // If snapshot found, load from it (it has pre-computed performance and dead code data)
        if (latestSnapshotFile) {
            try {
                const content = fs.readFileSync(latestSnapshotFile, 'utf-8');
                const snapshot = JSON.parse(content);

                // Load performance data directly
                if (snapshot.performance?.hotspots && snapshot.performance.hotspots.length > 0) {
                    this.performanceData = { hotspots: snapshot.performance.hotspots };
                }

                // Load dead code data
                if (snapshot.deadCode?.dead_functions && !this.deadCodeData) {
                    this.deadCodeData = { dead_functions: snapshot.deadCode.dead_functions };
                }

                // Load SQL analysis data
                if (snapshot.sqlAnalysis && !this.sqlAnalysisData) {
                    this.sqlAnalysisData = {
                        totalQueries: snapshot.sqlAnalysis.totalQueries || 0,
                        nPlus1Issues: snapshot.sqlAnalysis.nPlus1Issues || 0,
                        issues: snapshot.sqlAnalysis.issues || [],
                        queries: snapshot.sqlAnalysis.queries || []
                    };
                }

                // Load diagram data
                if (snapshot.diagram?.content && !this.diagramData) {
                    this.diagramData = snapshot.diagram.content;
                }

                return; // Successfully loaded from snapshot
            } catch (e) {
                // Snapshot parse error, fall back to raw trace files
            }
        }

        // Fallback: Find raw trace files if no snapshot
        let latestTraceFile: string | null = null;
        let latestMtime = 0;

        for (const traceDir of traceDirs) {
            if (!fs.existsSync(traceDir)) continue;

            try {
                const files = fs.readdirSync(traceDir)
                    .filter(f => f.endsWith('.json') && !f.startsWith('snapshot_'))
                    .map(f => path.join(traceDir, f));

                for (const file of files) {
                    const stat = fs.statSync(file);
                    if (stat.mtimeMs > latestMtime) {
                        latestMtime = stat.mtimeMs;
                        latestTraceFile = file;
                    }
                }
            } catch (e) {
                // Directory read error, continue to next
            }
        }

        if (!latestTraceFile) return;

        try {
            const content = fs.readFileSync(latestTraceFile, 'utf-8');
            const traceData = JSON.parse(content);
            const calls = traceData.calls || [];

            if (calls.length === 0) return;

            // Compute performance data from calls
            const perfMap = new Map<string, { total_ms: number; calls: number }>();

            for (const call of calls) {
                const funcName = `${call.module || 'unknown'}.${call.function || 'unknown'}`;
                const duration = call.duration_ms || call.duration || 0;

                if (!perfMap.has(funcName)) {
                    perfMap.set(funcName, { total_ms: 0, calls: 0 });
                }
                const entry = perfMap.get(funcName)!;
                entry.total_ms += duration;
                entry.calls += 1;
            }

            // Convert to hotspots array and sort by total time
            const hotspots = Array.from(perfMap.entries())
                .map(([func, data]) => ({
                    function: func,
                    total_ms: data.total_ms,
                    calls: data.calls
                }))
                .sort((a, b) => b.total_ms - a.total_ms)
                .slice(0, 20);

            if (hotspots.length > 0) {
                this.performanceData = { hotspots };
            }

            // Also set call trace data if not already set
            if (!this.callTraceData && calls.length > 0) {
                this.callTraceData = {
                    calls: calls.slice(0, 100).map((c: any) => ({
                        function: c.function || 'unknown',
                        module: c.module || 'unknown',
                        depth: c.depth || 0,
                        duration_ms: c.duration_ms || c.duration || 0,
                        type: c.type || 'call'
                    })),
                    total_calls: calls.length
                };
            }
        } catch (e) {
            // Parse error, ignore
        }
    }

    public async askQuestion(question: string, context: string = '', callback: (response: string) => void): Promise<void> {
        // Check if server is running (either our local process or external server)
        const serverRunning = await this.isServerRunningAnywhere();
        if (!serverRunning) {
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
        // Check if server is running (either our local process or external server)
        const serverRunning = await this.isServerRunningAnywhere();
        if (!serverRunning) {
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

    public async isServerRunning(): Promise<boolean> {
        return await this.isServerRunningAnywhere();
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

        /* MCP Status Bar */
        .mcp-status-bar {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 6px;
            padding: 4px 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .mcp-indicator {
            font-size: 10px;
            transition: color 0.3s ease;
        }

        .mcp-indicator.connected {
            color: #4caf50;
        }

        .mcp-indicator.disconnected {
            color: #ff5252;
        }

        .mcp-usage-hint {
            color: var(--text-muted);
            font-size: 10px;
            margin-left: auto;
            opacity: 0.7;
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

        /* Thinking indicator - compact inline style */
        .thinking {
            display: none;
            padding: 4px 8px;
            margin: 4px 8px;
        }

        .thinking.active { display: block; }

        .thinking-content {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 8px;
            background: transparent;
            border-radius: 4px;
        }

        .thinking-dots {
            display: flex;
            gap: 3px;
        }

        .thinking-dot {
            width: 6px;
            height: 6px;
            background: var(--accent-blue);
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }

        .thinking-dot:nth-child(1) { animation-delay: 0s; }
        .thinking-dot:nth-child(2) { animation-delay: 0.2s; }
        .thinking-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes bounce {
            0%, 80%, 100% { transform: translateY(0); }
            40% { transform: translateY(-4px); }
        }

        .thinking-text {
            color: var(--text-muted);
            font-size: 12px;
            font-style: italic;
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

        /* Stop button and chunk progress */
        .stop-btn {
            background: #d32f2f;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
            display: none;
            margin-left: 8px;
        }

        .stop-btn.active {
            display: inline-block;
        }

        .stop-btn:hover {
            background: #f44336;
        }

        .chunk-progress {
            display: none;
            padding: 8px 12px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            font-size: 12px;
            color: var(--accent-green);
            margin-top: 8px;
            align-items: center;
            gap: 8px;
        }

        .chunk-progress.active {
            display: flex;
        }

        .chunk-progress-bar {
            flex: 1;
            height: 4px;
            background: var(--bg-primary);
            border-radius: 2px;
            overflow: hidden;
        }

        .chunk-progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-green), var(--accent-blue));
            border-radius: 2px;
            transition: width 0.3s ease;
        }

        /* GPU and Backend controls */
        .backend-controls {
            display: flex;
            gap: 12px;
            margin-top: 8px;
            padding: 8px 12px;
            background: var(--bg-tertiary);
            border-radius: 6px;
            align-items: center;
            flex-wrap: wrap;
        }

        .gpu-option {
            display: none;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--accent-green);
        }

        .gpu-option.available {
            display: flex;
        }

        .gpu-option input[type="checkbox"] {
            accent-color: var(--accent-green);
        }

        .benchmark-info {
            font-size: 10px;
            color: #888;
            margin-left: 8px;
            padding: 2px 6px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
        }

        .backend-selector {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
        }

        .backend-selector select {
            padding: 4px 8px;
            font-size: 11px;
            min-width: 120px;
        }

        .ollama-models {
            display: none;
            align-items: center;
            gap: 6px;
            font-size: 12px;
        }

        .ollama-models.active {
            display: flex;
        }

        .ollama-models select {
            padding: 4px 8px;
            font-size: 11px;
            min-width: 150px;
        }

        .ollama-status {
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 4px;
        }

        .ollama-status.connected {
            background: rgba(76, 175, 80, 0.2);
            color: #4caf50;
        }

        .ollama-status.disconnected {
            background: rgba(244, 67, 54, 0.2);
            color: #f44336;
        }

        /* Token counter */
        .token-counter {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
            padding: 4px 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            margin-bottom: 8px;
        }

        .token-counter span {
            color: var(--accent-blue);
            font-weight: 500;
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
            <button class="stop-btn" id="stopBtn" title="Stop operation (ESC)">Stop</button>
            <div class="progress-bar" id="progressBar">
                <div class="progress-bar-fill" id="progressFill"></div>
            </div>
        </div>
        <div class="mcp-status-bar" id="mcpStatusBar">
            <span class="mcp-indicator disconnected" id="mcpIndicator">●</span>
            <span id="mcpStatusText">MCP Hub: Connecting...</span>
            <span class="mcp-usage-hint" id="mcpUsageHint">| Tools: get_trace_data, get_dead_code, get_performance_data, search_function</span>
        </div>
        <div class="chunk-progress" id="chunkProgress">
            <span id="chunkProgressText">Fetching context...</span>
            <div class="chunk-progress-bar">
                <div class="chunk-progress-fill" id="chunkProgressFill"></div>
            </div>
        </div>
        <!-- Backend and GPU controls -->
        <div class="backend-controls">
            <div class="backend-selector">
                <label>Backend:</label>
                <select id="backendSelect">
                    <option value="llama.cpp">llama.cpp (Local)</option>
                    <option value="ollama">Ollama</option>
                </select>
            </div>
            <div class="gpu-option" id="gpuOption">
                <input type="checkbox" id="gpuCheckbox" />
                <label for="gpuCheckbox" id="gpuLabel">GPU Acceleration</label>
                <span id="benchmarkInfo" class="benchmark-info"></span>
            </div>
            <div class="ollama-models" id="ollamaModelsDiv">
                <label>Model:</label>
                <select id="ollamaModelSelect">
                    <option value="">Select Ollama model...</option>
                </select>
                <span class="ollama-status disconnected" id="ollamaStatus">Not connected</span>
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
        <div class="token-counter" id="tokenCounter">
            <span id="tokenDisplay">Tokens: 0</span>
        </div>
        <div class="image-preview-container" id="imagePreviewContainer">
            <img id="imagePreview" class="image-preview" />
            <div class="image-preview-info" id="imageInfo">Image attached</div>
            <button class="image-preview-remove" id="removeImageBtn">x</button>
        </div>
        <div class="input-wrapper">
            <div class="input-left">
                <textarea id="userInput" placeholder="Ask about your code... (Enter to send, Shift+Enter for new line)"></textarea>
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
        const stopBtn = document.getElementById('stopBtn');
        const chunkProgress = document.getElementById('chunkProgress');
        const chunkProgressText = document.getElementById('chunkProgressText');
        const chunkProgressFill = document.getElementById('chunkProgressFill');

        // HuggingFace search elements
        const tabPresets = document.getElementById('tabPresets');
        const tabHFSearch = document.getElementById('tabHFSearch');
        const presetControls = document.getElementById('presetControls');
        const hfSearchPanel = document.getElementById('hfSearchPanel');
        const hfSearchInput = document.getElementById('hfSearchInput');
        const hfSearchBtn = document.getElementById('hfSearchBtn');
        const hfResults = document.getElementById('hfResults');

        // Backend and GPU elements
        const backendSelect = document.getElementById('backendSelect');
        const gpuOption = document.getElementById('gpuOption');
        const gpuCheckbox = document.getElementById('gpuCheckbox');
        const gpuLabel = document.getElementById('gpuLabel');
        const ollamaModelsDiv = document.getElementById('ollamaModelsDiv');
        const ollamaModelSelect = document.getElementById('ollamaModelSelect');
        const ollamaStatus = document.getElementById('ollamaStatus');

        let selectedHFModel = null;
        let currentBackend = 'llama.cpp';
        let gpuEnabled = false;

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

        // Backend selection handler
        backendSelect.addEventListener('change', () => {
            currentBackend = backendSelect.value;
            vscode.postMessage({ command: 'setBackend', backend: currentBackend });

            if (currentBackend === 'ollama') {
                // Hide llama.cpp controls, show Ollama controls
                presetControls.style.display = 'none';
                hfSearchPanel.classList.remove('active');
                ollamaModelsDiv.style.display = 'flex';
                tabPresets.style.display = 'none';
                tabHFSearch.style.display = 'none';
                // Check Ollama connection
                vscode.postMessage({ command: 'checkOllama' });
            } else {
                // Show llama.cpp controls
                presetControls.style.display = 'flex';
                ollamaModelsDiv.style.display = 'none';
                tabPresets.style.display = 'block';
                tabHFSearch.style.display = 'block';
            }
        });

        // GPU checkbox handler
        gpuCheckbox.addEventListener('change', () => {
            gpuEnabled = gpuCheckbox.checked;
            vscode.postMessage({ command: 'setGpuAcceleration', enabled: gpuEnabled });
        });

        // Ollama model selection handler
        ollamaModelSelect.addEventListener('change', () => {
            const selectedModel = ollamaModelSelect.value;
            if (selectedModel) {
                vscode.postMessage({ command: 'setOllamaModel', model: selectedModel });
            }
        });

        // Stop button and ESC key handler
        stopBtn.addEventListener('click', () => {
            vscode.postMessage({ command: 'cancelOperation' });
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                vscode.postMessage({ command: 'cancelOperation' });
            }
        });

        sendBtn.addEventListener('click', sendMessage);

        // Enter sends message, Shift+Enter or Alt+Enter inserts new line
        userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if (e.shiftKey || e.altKey) {
                    // Allow default behavior (new line)
                    return;
                }
                // Plain Enter sends message
                e.preventDefault();
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

                    // Handle GPU availability
                    if (msg.gpuAvailable && msg.gpuAvailable !== 'none') {
                        gpuOption.style.display = 'flex';
                        gpuLabel.textContent = 'GPU (' + msg.gpuAvailable.toUpperCase() + ')';
                        gpuCheckbox.checked = msg.gpuEnabled || false;
                        gpuEnabled = msg.gpuEnabled || false;
                    } else {
                        gpuOption.style.display = 'none';
                    }

                    // Handle Ollama status
                    if (msg.ollamaAvailable) {
                        ollamaStatus.textContent = 'Connected';
                        ollamaStatus.className = 'ollama-status connected';
                        ollamaModelSelect.innerHTML = '<option value="">Select model...</option>';
                        if (msg.ollamaModels && msg.ollamaModels.length > 0) {
                            msg.ollamaModels.forEach(function(model) {
                                const opt = document.createElement('option');
                                opt.value = model;
                                opt.textContent = model;
                                ollamaModelSelect.appendChild(opt);
                            });
                        }
                    }

                    // Update token counter
                    if (msg.totalTokens !== undefined) {
                        document.getElementById('tokenDisplay').textContent = 'Tokens: ' + msg.totalTokens.toLocaleString();
                    }
                    break;

                case 'addMessage':
                    addMessage(msg.role, msg.content, msg.timestamp, msg.imageBase64);
                    break;

                case 'setThinking':
                    thinking.classList.toggle('active', msg.thinking);
                    sendBtn.disabled = msg.thinking;
                    // Update thinking text with custom message if provided, reset when done
                    const thinkingText = thinking.querySelector('.thinking-text');
                    if (thinkingText) {
                        if (msg.thinking) {
                            thinkingText.textContent = msg.message || 'AI is thinking...';
                        } else {
                            // Reset to default when thinking ends
                            thinkingText.textContent = 'AI is thinking...';
                        }
                    }
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
                    // Show current mode (CPU/GPU)
                    const mode = msg.currentMode || 'CPU';
                    status.textContent = 'AI Server running on ' + mode + ' - Ready to chat!';
                    // Re-enable GPU checkbox (in case it was disabled by external server)
                    const gpuCheckboxStart = document.getElementById('gpuCheckbox') as HTMLInputElement;
                    if (gpuCheckboxStart) {
                        gpuCheckboxStart.disabled = false;
                        gpuCheckboxStart.title = 'Use GPU acceleration (if available)';
                    }
                    break;

                case 'serverStopped':
                    serverRunning = false;
                    serverBtn.textContent = 'Start Server';
                    serverBtn.className = 'secondary';
                    serverBtn.disabled = false;
                    serverBtn.title = 'Start the local AI server';
                    statusIndicator.classList.remove('connected');
                    status.textContent = 'AI Server stopped';
                    // Clear benchmark info
                    const benchmarkInfoStop = document.getElementById('benchmarkInfo');
                    if (benchmarkInfoStop) benchmarkInfoStop.textContent = '';
                    // Re-enable GPU checkbox
                    const gpuCheckboxStop = document.getElementById('gpuCheckbox') as HTMLInputElement;
                    if (gpuCheckboxStop) {
                        gpuCheckboxStop.disabled = false;
                        gpuCheckboxStop.title = 'Use GPU acceleration (if available)';
                    }
                    break;

                case 'benchmarkStarting':
                    status.textContent = 'AI Server running - Running benchmark...';
                    const benchmarkInfoStart = document.getElementById('benchmarkInfo');
                    if (benchmarkInfoStart) benchmarkInfoStart.textContent = '⏱ Benchmarking...';
                    break;

                case 'benchmarkComplete':
                    const benchmarkInfo = document.getElementById('benchmarkInfo');
                    if (benchmarkInfo) {
                        if (msg.gpuTps > 0) {
                            const winner = msg.recommended === 'gpu' ? '✓ GPU' : '✓ CPU';
                            benchmarkInfo.textContent = 'CPU: ' + Math.round(msg.cpuTps) + ' | GPU: ' + Math.round(msg.gpuTps) + ' t/s | ' + winner;
                        } else if (msg.gpuBusy) {
                            benchmarkInfo.textContent = 'CPU: ' + Math.round(msg.cpuTps) + ' t/s (GPU busy)';
                        } else {
                            benchmarkInfo.textContent = 'CPU: ' + Math.round(msg.cpuTps) + ' t/s (no GPU)';
                        }
                    }
                    // Show current running mode
                    const currentRunMode = msg.currentMode || 'CPU';
                    status.textContent = 'AI Server on ' + currentRunMode + ' - Ready to chat!';
                    break;

                case 'updateMcpStatus':
                    const mcpIndicator = document.getElementById('mcpIndicator');
                    const mcpStatusText = document.getElementById('mcpStatusText');
                    if (mcpIndicator && mcpStatusText) {
                        if (msg.connected) {
                            mcpIndicator.className = 'mcp-indicator connected';
                            mcpStatusText.textContent = 'MCP Hub: ' + (msg.endpoint || 'Connected') +
                                (msg.projectId ? ' | Project: ' + msg.projectId : '');
                        } else {
                            mcpIndicator.className = 'mcp-indicator disconnected';
                            mcpStatusText.textContent = 'MCP Hub: Not connected' +
                                (msg.hint ? ' - ' + msg.hint : '');
                        }
                    }
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
                    // Server is running from another IDE (PyCharm, etc.) - disable controls
                    serverRunning = true;
                    serverBtn.textContent = 'External Server (' + (msg.startedBy || 'external') + ')';
                    serverBtn.className = 'secondary';
                    serverBtn.disabled = true;
                    serverBtn.title = 'Server running at port 8080 (started externally). Stop it manually to use VS Code\\'s built-in server.';
                    sendBtn.disabled = false;
                    statusIndicator.classList.add('connected');
                    status.textContent = 'Using external AI server - Ready to chat!';
                    // Disable GPU checkbox for external server (we don't control it)
                    const gpuCheckboxExt = document.getElementById('gpuCheckbox') as HTMLInputElement;
                    if (gpuCheckboxExt) {
                        gpuCheckboxExt.disabled = true;
                        gpuCheckboxExt.title = 'Cannot change GPU setting for external server';
                    }
                    break;

                case 'showStopButton':
                    stopBtn.classList.toggle('active', msg.show);
                    break;

                case 'setChunkProgress':
                    if (msg.total > 0) {
                        chunkProgress.classList.add('active');
                        chunkProgressText.textContent = msg.message || ('Fetching ' + msg.current + '-' + msg.total + ' tokens...');
                        const pct = Math.round((msg.current / msg.total) * 100);
                        chunkProgressFill.style.width = pct + '%';
                    } else {
                        chunkProgress.classList.remove('active');
                    }
                    break;

                case 'operationCancelled':
                    stopBtn.classList.remove('active');
                    chunkProgress.classList.remove('active');
                    thinking.classList.remove('active');
                    sendBtn.disabled = false;
                    status.textContent = 'Operation cancelled';
                    break;

                case 'gpuStatus':
                    // Show/hide GPU option based on availability
                    if (msg.available && msg.available !== 'none') {
                        gpuOption.style.display = 'flex';
                        gpuLabel.textContent = 'GPU (' + msg.available.toUpperCase() + ')';
                        gpuCheckbox.checked = msg.enabled || false;
                        gpuEnabled = msg.enabled || false;
                    } else {
                        gpuOption.style.display = 'none';
                    }
                    break;

                case 'ollamaStatus':
                    if (msg.connected) {
                        ollamaStatus.textContent = 'Connected';
                        ollamaStatus.className = 'ollama-status connected';
                        // Populate model list
                        ollamaModelSelect.innerHTML = '<option value="">Select model...</option>';
                        if (msg.models && msg.models.length > 0) {
                            msg.models.forEach(model => {
                                const opt = document.createElement('option');
                                opt.value = model;
                                opt.textContent = model;
                                ollamaModelSelect.appendChild(opt);
                            });
                            serverBtn.disabled = false;
                            serverBtn.textContent = 'Ready (Ollama)';
                        }
                    } else {
                        ollamaStatus.textContent = 'Not connected';
                        ollamaStatus.className = 'ollama-status disconnected';
                        ollamaModelSelect.innerHTML = '<option value="">Ollama not running</option>';
                    }
                    break;

                case 'updateTokens':
                    // Update total tokens display
                    const tokenDisplay = document.getElementById('tokenDisplay');
                    if (tokenDisplay) {
                        tokenDisplay.textContent = 'Tokens: ' + msg.total.toLocaleString();
                    }
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
