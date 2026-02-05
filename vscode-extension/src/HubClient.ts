import WebSocket from 'ws';
import * as vscode from 'vscode';
import * as child_process from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

/**
 * TrueFlow Hub Client - WebSocket connection to MCP Hub
 *
 * Provides:
 * - Auto-connect to hub (starts hub if not running)
 * - Auto-reconnect on disconnect
 * - Event-driven message handling
 * - Project registration
 */

export interface HubMessage {
    type: string;
    timestamp?: string;
    data?: any;
    from_project?: string;
    command?: string;
    args?: any;
}

export type MessageHandler = (message: HubMessage) => void;

export class HubClient {
    private static instance: HubClient;
    private ws: WebSocket | null = null;
    private projectId: string;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;
    private reconnectDelay = 2000;
    private messageHandlers: Map<string, MessageHandler[]> = new Map();
    private hubProcess: child_process.ChildProcess | null = null;
    private isConnecting = false;

    private readonly HUB_URL = 'ws://127.0.0.1:5680';
    private readonly STATUS_FILE = path.join(os.homedir(), '.trueflow', 'hub_status.json');

    private constructor() {
        // Generate project ID from workspace
        const workspaceName = vscode.workspace.workspaceFolders?.[0]?.name || 'unknown';
        this.projectId = `vscode_${workspaceName}_${Date.now()}`;
    }

    public static getInstance(): HubClient {
        if (!HubClient.instance) {
            HubClient.instance = new HubClient();
        }
        return HubClient.instance;
    }

    public getProjectId(): string {
        return this.projectId;
    }

    public async connect(): Promise<boolean> {
        if (this.ws?.readyState === WebSocket.OPEN) {
            return true;
        }

        if (this.isConnecting) {
            return false;
        }

        this.isConnecting = true;

        try {
            // Try to connect to existing hub
            const connected = await this.tryConnect();
            if (connected) {
                this.isConnecting = false;
                return true;
            }

            // Start hub if not running
            console.log('[TrueFlow Hub] Hub not running, starting...');
            await this.startHub();

            // Hub needs time to start (Python startup + module imports + bind port)
            // Retry with backoff: 2s, 3s, 4s = ~9s total wait (matches PyCharm plugin)
            for (let attempt = 1; attempt <= 3; attempt++) {
                await new Promise(resolve => setTimeout(resolve, 1000 + attempt * 1000));
                console.log(`[TrueFlow Hub] Post-start connect attempt ${attempt}/3`);
                const connectedAfterStart = await this.tryConnect();
                if (connectedAfterStart) {
                    this.reconnectAttempts = 0;
                    this.isConnecting = false;
                    return true;
                }
            }

            console.warn('[TrueFlow Hub] Hub started but connection still failing');
            this.isConnecting = false;
            return false;

        } catch (error) {
            console.error('[TrueFlow Hub] Connection error:', error);
            this.isConnecting = false;
            return false;
        }
    }

    private tryConnect(): Promise<boolean> {
        return new Promise((resolve) => {
            try {
                this.ws = new WebSocket(this.HUB_URL);

                const timeout = setTimeout(() => {
                    this.ws?.close();
                    resolve(false);
                }, 3000);

                this.ws.on('open', () => {
                    clearTimeout(timeout);
                    console.log('[TrueFlow Hub] Connected to hub');
                    this.reconnectAttempts = 0;
                    this.register();
                    resolve(true);
                });

                this.ws.on('message', (data) => {
                    try {
                        const message: HubMessage = JSON.parse(data.toString());
                        this.handleMessage(message);
                    } catch (e) {
                        console.error('[TrueFlow Hub] Invalid message:', e);
                    }
                });

                this.ws.on('close', () => {
                    console.log('[TrueFlow Hub] Disconnected from hub');
                    this.ws = null;
                    this.scheduleReconnect();
                });

                this.ws.on('error', (error) => {
                    clearTimeout(timeout);
                    console.error('[TrueFlow Hub] WebSocket error:', error.message);
                    resolve(false);
                });

            } catch (error) {
                resolve(false);
            }
        });
    }

    private register(): void {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        this.send({
            type: 'register',
            data: {
                project_id: this.projectId,
                ide: 'vscode',
                project_path: workspaceFolder?.uri.fsPath,
                project_name: workspaceFolder?.name,
                capabilities: [
                    'ai_server',
                    'trace_collection',
                    'manim_generation',
                    'dead_code_analysis',
                    'performance_analysis'
                ]
            }
        });
    }

    private handleMessage(message: HubMessage): void {
        // Dispatch to registered handlers
        const handlers = this.messageHandlers.get(message.type) || [];
        handlers.forEach(handler => {
            try {
                handler(message);
            } catch (e) {
                console.error('[TrueFlow Hub] Handler error:', e);
            }
        });

        // Also dispatch to wildcard handlers
        const wildcardHandlers = this.messageHandlers.get('*') || [];
        wildcardHandlers.forEach(handler => {
            try {
                handler(message);
            } catch (e) {
                console.error('[TrueFlow Hub] Wildcard handler error:', e);
            }
        });
    }

    private scheduleReconnect(): void {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[TrueFlow Hub] Max reconnect attempts reached, will restart hub on next connect()');
            // Reset so next explicit connect() call will restart the hub
            this.reconnectAttempts = 0;
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`[TrueFlow Hub] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => {
            this.connect();
        }, delay);
    }

    /**
     * Check if hub is already running by reading status file and verifying process.
     */
    private isHubRunning(): boolean {
        try {
            if (!fs.existsSync(this.STATUS_FILE)) {
                return false;
            }

            const content = fs.readFileSync(this.STATUS_FILE, 'utf-8');
            const status = JSON.parse(content);

            if (!status.running || !status.pid) {
                return false;
            }

            // Check if the process is still alive
            try {
                process.kill(status.pid, 0); // Signal 0 just checks if process exists
                console.log(`[TrueFlow Hub] Hub already running (PID: ${status.pid})`);
                return true;
            } catch {
                // Process doesn't exist, status file is stale
                console.log('[TrueFlow Hub] Stale status file, hub not running');
                return false;
            }
        } catch (error) {
            return false;
        }
    }

    private async startHub(): Promise<void> {
        // Check if hub is already running before starting a new one
        if (this.isHubRunning()) {
            console.log('[TrueFlow Hub] Hub already running, skipping start');
            return;
        }

        // Find the hub script - try multiple locations
        const extensionPath = vscode.extensions.getExtension('hevolve-ai.trueflow')?.extensionPath;
        const homeDir = process.env.HOME || process.env.USERPROFILE || '';
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];

        const possiblePaths = [
            // 1. Extension path (bundled with extension)
            extensionPath ? path.join(extensionPath, 'runtime_injector', 'trueflow_mcp_hub.py') : '',
            // 2. Workspace .trueflow path (VS Code auto-integrated projects)
            workspaceFolder ? path.join(workspaceFolder.uri.fsPath, '.trueflow', 'runtime_injector', 'trueflow_mcp_hub.py') : '',
            // 3. Workspace .pycharm_plugin path (PyCharm auto-integrated projects)
            workspaceFolder ? path.join(workspaceFolder.uri.fsPath, '.pycharm_plugin', 'runtime_injector', 'trueflow_mcp_hub.py') : '',
            // 4. Workspace src path (for TrueFlow development)
            workspaceFolder ? path.join(workspaceFolder.uri.fsPath, 'src', 'main', 'resources', 'runtime_injector', 'trueflow_mcp_hub.py') : '',
            // 5. Home directory
            path.join(homeDir, '.trueflow', 'trueflow_mcp_hub.py'),
        ].filter(p => p !== '');

        let hubScript = '';
        for (const scriptPath of possiblePaths) {
            if (fs.existsSync(scriptPath)) {
                hubScript = scriptPath;
                console.log(`[TrueFlow Hub] Found hub script at: ${scriptPath}`);
                break;
            }
        }

        if (!hubScript) {
            console.error('[TrueFlow Hub] Hub script not found in any location. Tried:', possiblePaths);
            return;
        }

        try {
            const python = await this.findPython();
            console.log(`[TrueFlow Hub] Starting hub from: ${hubScript} (python: ${python})`);

            // Ensure hub dependencies are installed locally
            const depsDir = await this.ensureHubDependencies(python, workspaceFolder?.uri.fsPath);

            // Build environment with PYTHONPATH pointing to local deps
            const env: Record<string, string | undefined> = { ...process.env };
            if (depsDir && fs.existsSync(depsDir)) {
                const existing = env.PYTHONPATH || '';
                env.PYTHONPATH = existing ? `${depsDir}${path.delimiter}${existing}` : depsDir;
                console.log(`[TrueFlow Hub] PYTHONPATH includes: ${depsDir}`);
            }

            // Start hub in background (WebSocket only mode - no MCP stdio)
            this.hubProcess = child_process.spawn(python, [hubScript, '--ws-only'], {
                detached: true,
                stdio: ['ignore', 'pipe', 'pipe'],
                env
            });
            this.hubProcess.unref();

            // Capture hub output for debugging
            this.hubProcess.stdout?.on('data', (data: Buffer) => {
                console.log(`[TrueFlow Hub stdout] ${data.toString().trim()}`);
            });
            this.hubProcess.stderr?.on('data', (data: Buffer) => {
                console.error(`[TrueFlow Hub stderr] ${data.toString().trim()}`);
            });
            this.hubProcess.on('exit', (code: number | null) => {
                if (code !== 0 && code !== null) {
                    console.warn(`[TrueFlow Hub] Hub process exited with code ${code}`);
                } else {
                    console.log('[TrueFlow Hub] Hub process exited normally');
                }
            });

            console.log('[TrueFlow Hub] Started hub process');
        } catch (error) {
            console.error('[TrueFlow Hub] Failed to start hub:', error);
        }
    }

    /**
     * Find a working Python executable, preferring project venv and conda.
     */
    private async findPython(): Promise<string> {
        const homeDir = os.homedir();
        const isWindows = process.platform === 'win32';
        const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        const candidates: string[] = [];

        // 1. Project virtualenv
        if (workspacePath) {
            if (isWindows) {
                candidates.push(path.join(workspacePath, '.venv', 'Scripts', 'python.exe'));
                candidates.push(path.join(workspacePath, 'venv', 'Scripts', 'python.exe'));
            } else {
                candidates.push(path.join(workspacePath, '.venv', 'bin', 'python'));
                candidates.push(path.join(workspacePath, 'venv', 'bin', 'python'));
            }
        }

        // 2. Conda/miniconda
        if (isWindows) {
            candidates.push(path.join(homeDir, 'miniconda3', 'python.exe'));
            candidates.push(path.join(homeDir, 'anaconda3', 'python.exe'));
            candidates.push(path.join(homeDir, 'miniconda3', 'Scripts', 'python.exe'));
            candidates.push(path.join(homeDir, 'anaconda3', 'Scripts', 'python.exe'));
        } else {
            candidates.push(path.join(homeDir, 'miniconda3', 'bin', 'python'));
            candidates.push(path.join(homeDir, 'anaconda3', 'bin', 'python'));
        }

        // 3. System Python
        candidates.push('python3', 'python');

        for (const candidate of candidates) {
            try {
                // For absolute paths, check file exists first
                if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) {
                    continue;
                }
                const result = child_process.spawnSync(candidate, ['--version'], { timeout: 3000 });
                if (result.status === 0) {
                    console.log(`[TrueFlow Hub] Found Python: ${candidate}`);
                    return candidate;
                }
            } catch (_) { /* try next */ }
        }

        console.warn('[TrueFlow Hub] No Python found, falling back to "python"');
        return 'python';
    }

    /**
     * Ensure hub Python dependencies are installed locally.
     */
    private async ensureHubDependencies(python: string, workspacePath?: string): Promise<string | null> {
        const depsDir = workspacePath
            ? path.join(workspacePath, '.pycharm_plugin', 'hub_deps')
            : path.join(os.homedir(), '.trueflow', 'hub_deps');

        const markerFile = path.join(depsDir, '.deps_installed');
        if (fs.existsSync(markerFile)) {
            return depsDir;
        }

        try {
            fs.mkdirSync(depsDir, { recursive: true });
            console.log(`[TrueFlow Hub] Installing hub dependencies to: ${depsDir}`);

            const packages = ['websockets', 'mcp', 'starlette', 'uvicorn'];
            const args = ['-m', 'pip', 'install', '--target', depsDir, '--upgrade', '--quiet', ...packages];

            const result = child_process.spawnSync(python, args, { timeout: 120000 });
            if (result.status === 0) {
                fs.writeFileSync(markerFile, `installed=${Date.now()}`);
                console.log('[TrueFlow Hub] Hub dependencies installed successfully');
            } else {
                const stderr = result.stderr?.toString() || '';
                console.warn(`[TrueFlow Hub] pip install failed (exit ${result.status}): ${stderr}`);
            }
            return depsDir;
        } catch (e: any) {
            console.warn(`[TrueFlow Hub] Failed to install hub dependencies: ${e.message}`);
            return depsDir;
        }
    }

    // ==================== Public API ====================

    public send(message: HubMessage): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.warn('[TrueFlow Hub] Cannot send - not connected');
        }
    }

    public on(messageType: string, handler: MessageHandler): void {
        if (!this.messageHandlers.has(messageType)) {
            this.messageHandlers.set(messageType, []);
        }
        this.messageHandlers.get(messageType)!.push(handler);
    }

    public off(messageType: string, handler: MessageHandler): void {
        const handlers = this.messageHandlers.get(messageType);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index !== -1) {
                handlers.splice(index, 1);
            }
        }
    }

    public isConnected(): boolean {
        return this.ws?.readyState === WebSocket.OPEN;
    }

    public disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        if (this.hubProcess) {
            this.hubProcess.kill();
            this.hubProcess = null;
        }
    }

    /**
     * Stop hub process by reading PID from status file (parity with PyCharm HubClient.stopHub).
     */
    public stopHub(): void {
        this.disconnect();
        try {
            if (!fs.existsSync(this.STATUS_FILE)) { return; }
            const content = fs.readFileSync(this.STATUS_FILE, 'utf-8');
            const status = JSON.parse(content);
            const pid = status.pid;
            if (!pid) { return; }

            try {
                process.kill(pid, 'SIGTERM');
                console.log(`[TrueFlow Hub] Stopped hub process (PID: ${pid})`);
            } catch (_) {
                // Process already dead
            }
            fs.unlinkSync(this.STATUS_FILE);
        } catch (e) {
            console.warn('[TrueFlow Hub] Failed to stop hub:', e);
        }
    }

    /**
     * Restart hub (kill old process + reconnect). Used after extension/plugin version change.
     */
    public async restartHub(): Promise<boolean> {
        console.log('[TrueFlow Hub] Restarting hub (extension updated)...');
        this.stopHub();
        await new Promise(resolve => setTimeout(resolve, 1000));
        this.reconnectAttempts = 0;
        return this.connect();
    }

    // ==================== Convenience Methods ====================

    public notifyAIServerStarted(port: number, model: string): void {
        this.send({
            type: 'ai_server_started',
            data: {
                port,
                model,
                started_by: this.projectId
            }
        });
    }

    public notifyAIServerStopped(): void {
        this.send({
            type: 'ai_server_stopped',
            data: {}
        });
    }

    public sendTraceUpdate(traceData: any): void {
        this.send({
            type: 'trace_update',
            data: traceData
        });
    }

    public requestFromProject(targetProject: string, command: string, args: any = {}): void {
        this.send({
            type: 'request',
            data: {
                target_project: targetProject,
                command,
                args
            }
        });
    }

    public respondToProject(targetProject: string, data: any): void {
        this.send({
            type: 'response',
            data: {
                target_project: targetProject,
                ...data
            }
        });
    }

    /**
     * Send RPC response back to hub for a specific request
     */
    public sendRpcResponse(requestId: string, data: any): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'rpc_response',
                request_id: requestId,
                data: data
            }));
        } else {
            console.warn('[TrueFlow Hub] Cannot send RPC response - not connected');
        }
    }
}
