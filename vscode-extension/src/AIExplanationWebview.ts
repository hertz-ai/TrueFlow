import * as vscode from 'vscode';
import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import * as child_process from 'child_process';

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
}

interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
    imageBase64?: string;
    timestamp: string;
}

const MODEL_PRESETS: ModelPreset[] = [
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
    {
        displayName: "Qwen3-2B Text-Only Q4_K_M",
        repoId: "unsloth/Qwen3-2B-Instruct-GGUF",
        fileName: "Qwen3-2B-Instruct-Q4_K_M.gguf",
        sizeMB: 1100,
        description: "Text-only, fastest, no vision support",
        hasVision: false
    }
];

export class AIExplanationProvider {
    private static instance: AIExplanationProvider;
    private panel: vscode.WebviewPanel | undefined;
    private conversationHistory: ChatMessage[] = [];
    private maxHistorySize = 3;
    private serverProcess: child_process.ChildProcess | undefined;
    private currentModelFile: string | undefined;
    private currentModelHasVision = true;

    // Cross-tab context
    private deadCodeData: any = null;
    private performanceData: any = null;
    private callTraceData: any = null;
    private diagramData: string = '';

    private readonly modelsDir: string;
    private readonly apiBase = 'http://127.0.0.1:8080/v1';

    private constructor() {
        this.modelsDir = path.join(this.getHomeDir(), '.trueflow', 'models');
        if (!fs.existsSync(this.modelsDir)) {
            fs.mkdirSync(this.modelsDir, { recursive: true });
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

        this.panel = vscode.window.createWebviewPanel(
            'trueflowAI',
            'TrueFlow AI Assistant',
            vscode.ViewColumn.Two,
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        this.panel.webview.html = this.getWebviewContent();
        this.setupMessageHandlers();

        this.panel.onDidDispose(() => {
            this.panel = undefined;
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
            }
        });
    }

    private async handleUserMessage(text: string, imageBase64: string | undefined, contextType: string): Promise<void> {
        if (!text && !imageBase64) return;

        if (!this.serverProcess) {
            this.postMessage({
                command: 'addMessage',
                role: 'system',
                content: 'Please start the AI server first.',
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
                    try {
                        const json = JSON.parse(data);
                        const content = json.choices?.[0]?.message?.content || 'No response';
                        resolve(content);
                    } catch (e) {
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

    private checkModelStatus(): void {
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

        this.postMessage({
            command: 'updateStatus',
            downloadedModels,
            serverRunning: !!this.serverProcess,
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

        if (!this.currentModelFile) {
            vscode.window.showErrorMessage('No model downloaded. Please download a model first.');
            return;
        }

        const llamaServer = this.findLlamaServer();
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

        this.postMessage({ command: 'serverStarting' });

        const cpuCount = require('os').cpus().length;
        const args = [
            '--model', this.currentModelFile,
            '--port', '8080',
            '--ctx-size', '4096',
            '--threads', String(cpuCount),
            '--host', '127.0.0.1'
        ];

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
            this.postMessage({ command: 'serverStopped' });
            vscode.window.showInformationMessage('AI server stopped');
        }
    }

    private findLlamaServer(): string | null {
        const homeDir = this.getHomeDir();
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

        try {
            const which = process.platform === 'win32' ? 'where' : 'which';
            const result = child_process.execSync(`${which} llama-server`, { encoding: 'utf-8' });
            return result.trim().split('\n')[0];
        } catch {
            return null;
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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family);
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            padding: 10px;
            background: var(--vscode-sideBar-background);
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        .header h2 { margin-bottom: 10px; }
        .controls {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }
        select, button {
            padding: 6px 12px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        select {
            background: var(--vscode-dropdown-background);
            color: var(--vscode-dropdown-foreground);
            border: 1px solid var(--vscode-dropdown-border);
        }
        button:hover { background: var(--vscode-button-hoverBackground); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .status {
            font-size: 12px;
            color: var(--vscode-descriptionForeground);
            margin-top: 5px;
        }
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
        }
        .message {
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 8px;
            max-width: 85%;
        }
        .message.user {
            background: var(--vscode-button-background);
            margin-left: auto;
        }
        .message.assistant {
            background: var(--vscode-sideBar-background);
        }
        .message.system {
            background: var(--vscode-inputValidation-warningBackground);
            text-align: center;
            max-width: 100%;
        }
        .message-header {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 5px;
        }
        .message-content {
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .thinking {
            display: none;
            padding: 10px;
            font-style: italic;
            color: var(--vscode-descriptionForeground);
        }
        .thinking.active { display: block; }
        .input-area {
            padding: 10px;
            background: var(--vscode-sideBar-background);
            border-top: 1px solid var(--vscode-panel-border);
        }
        .input-row {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
        }
        textarea {
            flex: 1;
            min-height: 60px;
            padding: 8px;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            resize: vertical;
            font-family: inherit;
        }
        .button-row {
            display: flex;
            gap: 10px;
            justify-content: space-between;
            flex-wrap: wrap;
        }
        .progress-bar {
            width: 100%;
            height: 6px;
            background: var(--vscode-progressBar-background);
            border-radius: 3px;
            margin-top: 5px;
            display: none;
        }
        .progress-bar.active { display: block; }
        .progress-bar-fill {
            height: 100%;
            background: var(--vscode-progressBar-background);
            border-radius: 3px;
            transition: width 0.3s;
        }
        .image-preview {
            max-width: 200px;
            max-height: 100px;
            margin-top: 10px;
            border-radius: 4px;
            display: none;
        }
        .image-preview.active { display: block; }
    </style>
</head>
<body>
    <div class="header">
        <h2>🤖 TrueFlow AI Assistant</h2>
        <div class="controls">
            <select id="modelSelect">
                <option value="">Select a model...</option>
            </select>
            <button id="downloadBtn" disabled>Download Model</button>
            <button id="serverBtn" disabled>Start Server</button>
            <button id="clearBtn">Clear Chat</button>
        </div>
        <div class="status" id="status">Initializing...</div>
        <div class="progress-bar" id="progressBar">
            <div class="progress-bar-fill" id="progressFill"></div>
        </div>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="message system">
            <div class="message-content">Welcome to TrueFlow AI Assistant!

I can help you understand your code execution traces:
• Explain why code is dead/unreachable
• Analyze performance bottlenecks
• Explain exceptions and errors
• Analyze screenshots (paste with Ctrl+V)

Setup:
1. Select and download a model
2. Start the AI server
3. Ask your questions!</div>
        </div>
    </div>

    <div class="thinking" id="thinking">🤔 Thinking...</div>

    <div class="input-area">
        <div class="input-row">
            <textarea id="userInput" placeholder="Type your question here... (Ctrl+Enter to send)"></textarea>
        </div>
        <img id="imagePreview" class="image-preview" />
        <div class="button-row">
            <div>
                <select id="contextSelect">
                    <option value="">No context</option>
                    <option value="deadCode">Dead Code</option>
                    <option value="performance">Performance</option>
                    <option value="callTrace">Call Trace</option>
                    <option value="diagram">Diagram</option>
                    <option value="all">All Data</option>
                </select>
                <button id="pasteImageBtn">📋 Paste Image</button>
                <input type="file" id="imageInput" accept="image/*" style="display:none">
                <button id="attachImageBtn">📎 Attach</button>
            </div>
            <button id="sendBtn">Send</button>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        let pendingImageBase64 = null;
        let serverRunning = false;

        // Elements
        const modelSelect = document.getElementById('modelSelect');
        const downloadBtn = document.getElementById('downloadBtn');
        const serverBtn = document.getElementById('serverBtn');
        const clearBtn = document.getElementById('clearBtn');
        const status = document.getElementById('status');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const chatContainer = document.getElementById('chatContainer');
        const thinking = document.getElementById('thinking');
        const userInput = document.getElementById('userInput');
        const contextSelect = document.getElementById('contextSelect');
        const sendBtn = document.getElementById('sendBtn');
        const pasteImageBtn = document.getElementById('pasteImageBtn');
        const attachImageBtn = document.getElementById('attachImageBtn');
        const imageInput = document.getElementById('imageInput');
        const imagePreview = document.getElementById('imagePreview');

        // Event listeners
        modelSelect.addEventListener('change', () => {
            const idx = modelSelect.selectedIndex - 1;
            downloadBtn.disabled = idx < 0;
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

        pasteImageBtn.addEventListener('click', async () => {
            try {
                const items = await navigator.clipboard.read();
                for (const item of items) {
                    if (item.types.includes('image/png')) {
                        const blob = await item.getType('image/png');
                        const reader = new FileReader();
                        reader.onload = () => {
                            pendingImageBase64 = reader.result.split(',')[1];
                            imagePreview.src = reader.result;
                            imagePreview.classList.add('active');
                            status.textContent = 'Image pasted from clipboard';
                        };
                        reader.readAsDataURL(blob);
                        return;
                    }
                }
                status.textContent = 'No image in clipboard';
            } catch (err) {
                status.textContent = 'Failed to paste: ' + err.message;
            }
        });

        attachImageBtn.addEventListener('click', () => imageInput.click());

        imageInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = () => {
                    pendingImageBase64 = reader.result.split(',')[1];
                    imagePreview.src = reader.result;
                    imagePreview.classList.add('active');
                    status.textContent = 'Image attached: ' + file.name;
                };
                reader.readAsDataURL(file);
            }
        });

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
            pendingImageBase64 = null;
            imagePreview.classList.remove('active');
        }

        function addMessage(role, content, timestamp) {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.innerHTML = \`
                <div class="message-header">\${role === 'user' ? 'You' : role === 'assistant' ? 'AI' : 'System'} • \${timestamp}</div>
                <div class="message-content">\${escapeHtml(content)}</div>
            \`;
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Handle messages from extension
        window.addEventListener('message', (event) => {
            const msg = event.data;
            switch (msg.command) {
                case 'updateStatus':
                    // Populate model select
                    modelSelect.innerHTML = '<option value="">Select a model...</option>';
                    msg.models.forEach((m, i) => {
                        const opt = document.createElement('option');
                        opt.value = i;
                        opt.textContent = m.displayName + (m.downloaded ? ' ✓' : ' (' + m.sizeMB + 'MB)');
                        modelSelect.appendChild(opt);
                    });
                    serverBtn.disabled = msg.downloadedModels.length === 0;
                    serverRunning = msg.serverRunning;
                    serverBtn.textContent = serverRunning ? 'Stop Server' : 'Start Server';
                    status.textContent = serverRunning ? 'AI Server running - Ready!' :
                        (msg.downloadedModels.length > 0 ? 'Model ready. Click Start Server.' : 'No model downloaded.');
                    break;

                case 'addMessage':
                    addMessage(msg.role, msg.content, msg.timestamp);
                    break;

                case 'setThinking':
                    thinking.classList.toggle('active', msg.thinking);
                    sendBtn.disabled = msg.thinking;
                    break;

                case 'historyCleared':
                    chatContainer.innerHTML = '';
                    addMessage('system', 'Chat history cleared.', new Date().toLocaleTimeString());
                    break;

                case 'downloadStarted':
                    status.textContent = 'Downloading ' + msg.modelName + '...';
                    progressBar.classList.add('active');
                    downloadBtn.disabled = true;
                    break;

                case 'downloadProgress':
                    progressFill.style.width = msg.percent + '%';
                    status.textContent = 'Downloading... ' + msg.downloadedMB + 'MB / ' + msg.totalMB + 'MB (' + msg.percent + '%)';
                    break;

                case 'downloadComplete':
                    progressBar.classList.remove('active');
                    status.textContent = 'Download complete: ' + msg.modelName;
                    downloadBtn.disabled = false;
                    break;

                case 'downloadError':
                    progressBar.classList.remove('active');
                    status.textContent = 'Download error: ' + msg.error;
                    downloadBtn.disabled = false;
                    break;

                case 'serverStarting':
                    status.textContent = 'Starting AI server... ' + (msg.progress || 0) + '/60';
                    serverBtn.disabled = true;
                    break;

                case 'serverStarted':
                    serverRunning = true;
                    serverBtn.textContent = 'Stop Server';
                    serverBtn.disabled = false;
                    status.textContent = 'AI Server running - Ready to chat!';
                    break;

                case 'serverStopped':
                    serverRunning = false;
                    serverBtn.textContent = 'Start Server';
                    serverBtn.disabled = false;
                    status.textContent = 'AI Server stopped';
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
