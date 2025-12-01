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

            // Wait a bit for hub to start
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Try connecting again
            const connectedAfterStart = await this.tryConnect();
            this.isConnecting = false;
            return connectedAfterStart;

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
            console.log('[TrueFlow Hub] Max reconnect attempts reached');
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
            // Start hub in background (WebSocket only mode for now)
            this.hubProcess = child_process.spawn('python', [hubScript, '--ws-only'], {
                detached: true,
                stdio: 'ignore'
            });
            this.hubProcess.unref();
            console.log('[TrueFlow Hub] Started hub process');
        } catch (error) {
            console.error('[TrueFlow Hub] Failed to start hub:', error);
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
