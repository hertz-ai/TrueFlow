import * as http from 'http';
import * as https from 'https';
import * as fs from 'fs';
import * as path from 'path';
import { ExplanationCacheManager, CachedExplanation, VisualizationData } from './ExplanationCacheManager';

/**
 * HTTP Server that serves the Interactive Explorer with real-time updates via SSE.
 *
 * Features:
 * - Serves the interactive_flow_explorer.html at /
 * - Provides Server-Sent Events (SSE) at /events for real-time trace updates
 * - Provides JSON API at /api/data for current trace data
 */
export class InteractiveExplorerServer {
    private server: http.Server | null = null;
    private sseClients: http.ServerResponse[] = [];
    private currentTraceData: any = null;
    private htmlTemplate: string | null = null;
    private port: number;
    private resourcesPath: string;
    private llmEndpoint: string;  // llama.cpp server (OpenAI-compatible)
    private explanationCache: ExplanationCacheManager | null = null;

    constructor(
        port: number = 8765,
        resourcesPath: string,
        private onServerStarted?: (url: string) => void,
        private onServerStopped?: () => void,
        private onError?: (error: Error) => void,
        llmEndpoint: string = 'http://127.0.0.1:8080/v1'  // llama.cpp server
    ) {
        this.port = port;
        this.resourcesPath = resourcesPath;
        this.llmEndpoint = llmEndpoint;
    }

    /**
     * Initialize the explanation cache manager.
     * Call after construction with the project's cache directory.
     */
    initCache(cacheDir: string): void {
        this.explanationCache = new ExplanationCacheManager(
            cacheDir,
            this.llmEndpoint,
            // Notify SSE clients when a cached explanation is ready
            (explanation: CachedExplanation) => {
                this.pushCachedExplanation(explanation);
            },
            // Check if AI server is available
            () => this.isAIAvailable,
            // Notify SSE clients of auto-explain progress
            (active: boolean, funcName: string | null, cached: number, total: number) => {
                this.pushAutoExplainStatus(active, funcName, cached, total);
            }
        );
        console.log('[ExplorerServer] Explanation cache initialized');
    }

    private isAIAvailable = false;

    /**
     * Update AI server availability status.
     */
    setAIAvailable(available: boolean): void {
        this.isAIAvailable = available;
    }

    /**
     * Get the explanation cache manager (for external access).
     */
    getCache(): ExplanationCacheManager | null {
        return this.explanationCache;
    }

    start(): boolean {
        if (this.server) {
            console.log('[ExplorerServer] Server already running');
            return false;
        }

        try {
            this.server = http.createServer((req, res) => {
                this.handleRequest(req, res);
            });

            this.server.listen(this.port, () => {
                const url = `http://localhost:${this.port}`;
                console.log(`[ExplorerServer] Started at ${url}`);
                this.onServerStarted?.(url);
            });

            this.server.on('error', (err: NodeJS.ErrnoException) => {
                console.error('[ExplorerServer] Server error:', err.message);
                this.onError?.(err);
            });

            return true;
        } catch (error) {
            console.error('[ExplorerServer] Failed to start:', error);
            this.onError?.(error as Error);
            return false;
        }
    }

    stop(): void {
        // Shutdown explanation cache
        this.explanationCache?.shutdown();

        // Close all SSE connections
        this.sseClients.forEach(client => {
            try {
                client.end();
            } catch (e) {
                // Ignore close errors
            }
        });
        this.sseClients = [];

        if (this.server) {
            this.server.close();
            this.server = null;
            console.log('[ExplorerServer] Stopped');
            this.onServerStopped?.();
        }
    }

    isRunning(): boolean {
        return this.server !== null;
    }

    getUrl(): string {
        return `http://localhost:${this.port}`;
    }

    /**
     * Push new trace data to all connected SSE clients.
     */
    pushTraceData(data: any): void {
        this.currentTraceData = data;

        // Update explanation cache with new visualization data
        if (this.explanationCache && data.functions) {
            this.explanationCache.updateVisualizationData(data as VisualizationData);
        }

        const jsonData = JSON.stringify(data);
        const sseMessage = `event: traceUpdate\ndata: ${jsonData}\n\n`;

        // Send to all connected SSE clients
        const deadClients: http.ServerResponse[] = [];

        for (const client of this.sseClients) {
            try {
                client.write(sseMessage);
            } catch (e) {
                deadClients.push(client);
            }
        }

        // Clean up dead connections
        this.sseClients = this.sseClients.filter(c => !deadClients.includes(c));

        console.log(`[ExplorerServer] Pushed update to ${this.sseClients.length} clients`);
    }

    private handleRequest(req: http.IncomingMessage, res: http.ServerResponse): void {
        const url = req.url || '/';

        // CORS headers
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

        if (req.method === 'OPTIONS') {
            res.writeHead(200);
            res.end();
            return;
        }

        if (url === '/' || url === '/index.html') {
            this.handleMainPage(req, res);
        } else if (url === '/events') {
            this.handleSSE(req, res);
        } else if (url === '/api/data') {
            this.handleDataApi(req, res);
        } else if (url === '/api/ai/status') {
            this.handleAIStatus(req, res);
        } else if (url === '/api/ai/explain') {
            this.handleAIExplain(req, res);
        } else if (url === '/api/ai/prioritize') {
            this.handleAIPrioritize(req, res);
        } else if (url === '/api/ai/cache-stats') {
            this.handleCacheStats(req, res);
        } else {
            res.writeHead(404);
            res.end('Not Found');
        }
    }

    /**
     * Serve the main HTML page with embedded SSE client.
     */
    private handleMainPage(req: http.IncomingMessage, res: http.ServerResponse): void {
        try {
            const html = this.getHtmlWithSSE();

            res.writeHead(200, {
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'no-cache'
            });
            res.end(html);
        } catch (error) {
            console.error('[ExplorerServer] Error serving main page:', error);
            res.writeHead(500);
            res.end('Internal Server Error');
        }
    }

    /**
     * Handle Server-Sent Events connection for real-time updates.
     */
    private handleSSE(req: http.IncomingMessage, res: http.ServerResponse): void {
        try {
            // Set SSE headers
            res.writeHead(200, {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*'
            });

            // Add to clients list
            this.sseClients.push(res);
            console.log(`[ExplorerServer] SSE client connected (${this.sseClients.length} total)`);

            // Send initial data if available
            if (this.currentTraceData) {
                const jsonData = JSON.stringify(this.currentTraceData);
                const initialMessage = `event: traceUpdate\ndata: ${jsonData}\n\n`;
                res.write(initialMessage);
            }

            // Handle client disconnect
            req.on('close', () => {
                this.sseClients = this.sseClients.filter(c => c !== res);
                console.log(`[ExplorerServer] SSE client disconnected (${this.sseClients.length} remaining)`);
            });

        } catch (error) {
            console.error('[ExplorerServer] Error handling SSE:', error);
            this.sseClients = this.sseClients.filter(c => c !== res);
        }
    }

    /**
     * Handle JSON API requests for current trace data.
     */
    private handleDataApi(req: http.IncomingMessage, res: http.ServerResponse): void {
        try {
            const data = this.currentTraceData || {};
            const json = JSON.stringify(data);

            res.writeHead(200, {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            });
            res.end(json);
        } catch (error) {
            console.error('[ExplorerServer] Error handling data API:', error);
            res.writeHead(500);
            res.end('Internal Server Error');
        }
    }

    /**
     * Handle AI status check - returns whether llama.cpp server is available.
     */
    private async handleAIStatus(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
        try {
            const { available, model } = await this.checkLLMStatus();
            const json = JSON.stringify({
                available,
                endpoint: this.llmEndpoint,
                model
            });

            res.writeHead(200, {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            });
            res.end(json);
        } catch (error) {
            console.error('[ExplorerServer] Error checking AI status:', error);
            res.writeHead(200, {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            });
            res.end(JSON.stringify({ available: false, error: String(error) }));
        }
    }

    /**
     * Handle AI explanation request - checks cache first, then proxies to llama.cpp server.
     */
    private async handleAIExplain(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
        if (req.method !== 'POST') {
            res.writeHead(405, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Method not allowed' }));
            return;
        }

        // Mark user activity for idle detection
        this.explanationCache?.markUserActivity();

        try {
            // Read request body
            const body = await this.readRequestBody(req);
            const parsed = JSON.parse(body);
            const { prompt, function: funcName, file: filePath } = parsed;

            if (!prompt) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Missing prompt' }));
                return;
            }

            // Check cache first (if function name and file provided)
            if (funcName && filePath && this.explanationCache) {
                const cached = this.explanationCache.getExplanation(funcName, filePath);
                if (cached) {
                    console.log(`[ExplorerServer] Cache hit for: ${funcName}`);
                    res.writeHead(200, {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    });
                    res.end(JSON.stringify({ success: true, explanation: cached.explanation, cached: true }));
                    return;
                }
            }

            console.log('[ExplorerServer] AI explain request, prompt length:', prompt.length);

            // Call llama.cpp server
            const response = await this.callLLM(prompt);

            // Store in cache if function info provided
            if (funcName && filePath && this.explanationCache) {
                const data = this.currentTraceData;
                const whyInfo = data?.why_not_covered?.[funcName];
                this.explanationCache.storeExplanation({
                    functionName: funcName,
                    filePath,
                    line: data?.functions?.[funcName]?.line || 0,
                    contentHash: 'user_request', // Will be properly computed on next data update
                    whyNotCovered: whyInfo?.root_cause || 'unknown',
                    explanation: response,
                    timestamp: Date.now(),
                    modelUsed: 'user_request'
                });
            }

            res.writeHead(200, {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            });
            // Match Kotlin format: { success, explanation }
            res.end(JSON.stringify({ success: true, explanation: response, cached: false }));

        } catch (error) {
            console.error('[ExplorerServer] Error handling AI explain:', error);
            res.writeHead(500, {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            });
            // Match Kotlin format: { success, error }
            res.end(JSON.stringify({ success: false, error: String(error) }));
        }
    }

    /**
     * Handle AI prioritize request - for preemptive caching based on user searches/focus.
     * Matches PyCharm's /api/ai/prioritize endpoint.
     */
    private async handleAIPrioritize(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
        if (req.method !== 'POST') {
            res.writeHead(405, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Method not allowed' }));
            return;
        }

        try {
            const body = await this.readRequestBody(req);
            const request = JSON.parse(body);

            const reason = request.reason || 'user_interaction';
            const funcNames: string[] = [];

            // Support both single function and array of functions
            if (request.function) {
                funcNames.push(request.function);
            }
            if (request.functions && Array.isArray(request.functions)) {
                funcNames.push(...request.functions);
            }

            if (funcNames.length === 0) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'No functions specified' }));
                return;
            }

            if (this.explanationCache) {
                this.explanationCache.prioritizeFunctions(funcNames, reason);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true, prioritized: funcNames.length, reason }));
            } else {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: false, message: 'Cache not initialized' }));
            }
        } catch (error) {
            console.error('[ExplorerServer] Error handling AI prioritize:', error);
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Internal Server Error' }));
        }
    }

    /**
     * Handle cache stats request.
     */
    private handleCacheStats(req: http.IncomingMessage, res: http.ServerResponse): void {
        const stats = this.explanationCache?.getCacheStats() || {
            totalCached: 0, pendingQueue: 0, isProcessing: false, isIdle: true
        };
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(stats));
    }

    /**
     * Push a cached explanation to all connected SSE clients.
     */
    private pushCachedExplanation(explanation: CachedExplanation): void {
        const message = JSON.stringify({
            type: 'cached_explanation',
            function: explanation.functionName,
            explanation: explanation.explanation,
            whyNotCovered: explanation.whyNotCovered,
            cached: true
        });

        const sseMessage = `event: cachedExplanation\ndata: ${message}\n\n`;

        this.sseClients = this.sseClients.filter(client => {
            try {
                client.write(sseMessage);
                return true;
            } catch (e) {
                return false; // Remove dead client
            }
        });
    }

    private pushAutoExplainStatus(active: boolean, funcName: string | null, cached: number, total: number): void {
        const message = JSON.stringify({
            type: 'auto_explain_status',
            active,
            funcName,
            cached,
            total
        });

        const sseMessage = `event: autoExplainStatus\ndata: ${message}\n\n`;

        this.sseClients = this.sseClients.filter(client => {
            try {
                client.write(sseMessage);
                return true;
            } catch (e) {
                return false;
            }
        });
    }

    /**
     * Read the request body as a string.
     */
    private readRequestBody(req: http.IncomingMessage): Promise<string> {
        return new Promise((resolve, reject) => {
            const chunks: Buffer[] = [];
            req.on('data', (chunk: Buffer) => chunks.push(chunk));
            req.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
            req.on('error', reject);
        });
    }

    /**
     * Check if llama.cpp server is running and get model info.
     * Returns { available: boolean, model: string }
     */
    private checkLLMStatus(): Promise<{ available: boolean; model: string }> {
        return new Promise((resolve) => {
            // Defensive check for llmEndpoint
            if (!this.llmEndpoint) {
                console.error('[ExplorerServer] llmEndpoint is not configured');
                resolve({ available: false, model: '' });
                return;
            }

            // First check /health endpoint
            const healthUrl = new URL(this.llmEndpoint.replace('/v1', '/health'));
            const healthOptions = {
                hostname: healthUrl.hostname,
                port: healthUrl.port || 8080,
                path: healthUrl.pathname,
                method: 'GET',
                timeout: 5000
            };

            const healthReq = http.request(healthOptions, (res) => {
                if (res.statusCode !== 200) {
                    resolve({ available: false, model: '' });
                    return;
                }

                // Now get model name from /v1/models
                const modelsUrl = new URL(`${this.llmEndpoint}/models`);
                const modelsOptions = {
                    hostname: modelsUrl.hostname,
                    port: modelsUrl.port || 8080,
                    path: modelsUrl.pathname,
                    method: 'GET',
                    timeout: 5000
                };

                const modelsReq = http.request(modelsOptions, (modelsRes) => {
                    if (modelsRes.statusCode !== 200) {
                        resolve({ available: true, model: 'llama.cpp' });
                        return;
                    }

                    const chunks: Buffer[] = [];
                    modelsRes.on('data', (chunk: Buffer) => chunks.push(chunk));
                    modelsRes.on('end', () => {
                        try {
                            const responseBody = Buffer.concat(chunks).toString('utf-8');
                            const jsonResponse = JSON.parse(responseBody);
                            const model = jsonResponse.data?.[0]?.id || 'llama.cpp';
                            resolve({ available: true, model });
                        } catch (e) {
                            resolve({ available: true, model: 'llama.cpp' });
                        }
                    });
                });

                modelsReq.on('error', () => resolve({ available: true, model: 'llama.cpp' }));
                modelsReq.on('timeout', () => {
                    modelsReq.destroy();
                    resolve({ available: true, model: 'llama.cpp' });
                });
                modelsReq.end();
            });

            healthReq.on('error', () => resolve({ available: false, model: '' }));
            healthReq.on('timeout', () => {
                healthReq.destroy();
                resolve({ available: false, model: '' });
            });
            healthReq.end();
        });
    }

    /**
     * Call llama.cpp server using OpenAI-compatible chat completions API.
     */
    private callLLM(prompt: string): Promise<string> {
        return new Promise((resolve, reject) => {
            if (!this.llmEndpoint) {
                reject(new Error('LLM endpoint not configured'));
                return;
            }
            const url = new URL(`${this.llmEndpoint}/chat/completions`);
            const postData = JSON.stringify({
                messages: [{ role: 'user', content: prompt }],
                temperature: 0.7,
                max_tokens: 1024,
                stream: false
            });

            const options = {
                hostname: url.hostname,
                port: url.port || 8080,
                path: url.pathname,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(postData)
                },
                timeout: 120000 // 2 minutes for AI response
            };

            const req = http.request(options, (res) => {
                const chunks: Buffer[] = [];
                res.on('data', (chunk: Buffer) => chunks.push(chunk));
                res.on('end', () => {
                    try {
                        const responseBody = Buffer.concat(chunks).toString('utf-8');
                        const jsonResponse = JSON.parse(responseBody);
                        // OpenAI format: choices[0].message.content
                        const content = jsonResponse.choices?.[0]?.message?.content || '';
                        resolve(content);
                    } catch (e) {
                        reject(new Error('Failed to parse LLM response'));
                    }
                });
            });

            req.on('error', (e) => reject(e));
            req.on('timeout', () => {
                req.destroy();
                reject(new Error('LLM request timed out'));
            });

            req.write(postData);
            req.end();
        });
    }

    /**
     * Get the HTML template with SSE client code injected.
     */
    private getHtmlWithSSE(): string {
        // Load base HTML template
        if (!this.htmlTemplate) {
            try {
                const htmlPath = path.join(this.resourcesPath, 'interactive_viz', 'interactive_flow_explorer.html');
                if (fs.existsSync(htmlPath)) {
                    this.htmlTemplate = fs.readFileSync(htmlPath, 'utf-8');
                } else {
                    this.htmlTemplate = this.getDefaultHtml();
                }
            } catch (error) {
                console.error('[ExplorerServer] Failed to load HTML template:', error);
                this.htmlTemplate = this.getDefaultHtml();
            }
        }

        // Inject SSE client code
        const sseClientScript = `
<script>
// TrueFlow Real-time SSE Client
(function() {
    const SSE_URL = '/events';
    let eventSource = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    const RECONNECT_DELAY = 2000;

    function showConnectionStatus(status, message) {
        let statusEl = document.getElementById('trueflow-connection-status');
        if (!statusEl) {
            statusEl = document.createElement('div');
            statusEl.id = 'trueflow-connection-status';
            statusEl.style.cssText = 'position:fixed;bottom:10px;right:10px;padding:8px 16px;border-radius:4px;font-size:12px;z-index:10000;transition:opacity 0.3s;';
            document.body.appendChild(statusEl);
        }

        if (status === 'connected') {
            statusEl.style.background = '#4CAF50';
            statusEl.style.color = 'white';
            statusEl.textContent = '● Live: ' + message;
            setTimeout(() => { statusEl.style.opacity = '0.6'; }, 3000);
        } else if (status === 'connecting') {
            statusEl.style.background = '#FF9800';
            statusEl.style.color = 'white';
            statusEl.style.opacity = '1';
            statusEl.textContent = '◌ ' + message;
        } else if (status === 'error') {
            statusEl.style.background = '#f44336';
            statusEl.style.color = 'white';
            statusEl.style.opacity = '1';
            statusEl.textContent = '✕ ' + message;
        }
    }

    function connect() {
        if (eventSource) {
            eventSource.close();
        }

        showConnectionStatus('connecting', 'Connecting to TrueFlow...');

        eventSource = new EventSource(SSE_URL);

        eventSource.onopen = function() {
            console.log('[TrueFlow] SSE connected');
            reconnectAttempts = 0;
            showConnectionStatus('connected', 'Real-time updates active');
        };

        eventSource.addEventListener('traceUpdate', function(e) {
            try {
                const data = JSON.parse(e.data);
                console.log('[TrueFlow] Received trace update:', Object.keys(data));

                // Update the visualization
                if (typeof loadVisualizationData === 'function') {
                    loadVisualizationData(data);
                } else if (window.explorer && typeof window.explorer.loadData === 'function') {
                    window.explorer.loadData(data);
                }

                // Flash status to show update received
                showConnectionStatus('connected', 'Updated ' + new Date().toLocaleTimeString());
            } catch (err) {
                console.error('[TrueFlow] Error processing update:', err);
            }
        });

        eventSource.addEventListener('cachedExplanation', function(e) {
            try {
                const data = JSON.parse(e.data);
                console.log('[TrueFlow] Cached explanation received for:', data.function);
                if (typeof handleCachedExplanation === 'function') {
                    handleCachedExplanation(data);
                }
            } catch (err) {
                console.error('[TrueFlow] Error processing cached explanation:', err);
            }
        });

        eventSource.onerror = function(e) {
            console.error('[TrueFlow] SSE error:', e);
            eventSource.close();

            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                showConnectionStatus('connecting', 'Reconnecting (' + reconnectAttempts + '/' + MAX_RECONNECT_ATTEMPTS + ')...');
                setTimeout(connect, RECONNECT_DELAY);
            } else {
                showConnectionStatus('error', 'Connection lost. Refresh to retry.');
            }
        };
    }

    // Start connection when page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', connect);
    } else {
        connect();
    }

    // Expose for debugging
    window.trueflowSSE = {
        reconnect: connect,
        getStatus: () => eventSource ? eventSource.readyState : -1
    };
})();
</script>
`;

        // Inject before </body>
        return this.htmlTemplate.replace('</body>', `${sseClientScript}</body>`);
    }

    private getDefaultHtml(): string {
        return `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TrueFlow Interactive Explorer</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .message {
            text-align: center;
            padding: 40px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            max-width: 500px;
        }
        h2 { color: #4CAF50; margin-bottom: 20px; }
        p { color: #aaa; line-height: 1.6; }
        .status {
            display: inline-block;
            padding: 4px 12px;
            background: #4CAF50;
            color: white;
            border-radius: 20px;
            font-size: 12px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="message">
        <h2>TrueFlow Interactive Explorer</h2>
        <p>Waiting for trace data...</p>
        <p>Run your Python/Java code with TrueFlow tracing enabled to see the visualization here in real-time.</p>
        <div class="status">● Server Active</div>
    </div>
    <script>
        function loadVisualizationData(data) {
            document.querySelector('.message').innerHTML =
                '<h2>✓ Data Received</h2>' +
                '<p>Trace data loaded with ' + (data.functions ? Object.keys(data.functions).length : 0) + ' functions.</p>' +
                '<pre style="text-align:left;background:#2a2a3e;padding:20px;border-radius:8px;overflow:auto;max-height:400px;">' +
                JSON.stringify(data, null, 2).substring(0, 2000) + '...</pre>';
        }
    </script>
</body>
</html>
        `.trim();
    }
}
