import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';
import * as crypto from 'crypto';

/**
 * Cached AI explanation for a function.
 * Keyed by function signature + content hash for invalidation.
 * Mirrors PyCharm's ExplanationCacheManager for feature parity.
 */
export interface CachedExplanation {
    functionName: string;
    filePath: string;
    line: number;
    contentHash: string;       // Hash of function source + context for cache invalidation
    whyNotCovered: string;     // Root cause type
    explanation: string;       // AI-generated explanation
    timestamp: number;         // When this was generated
    modelUsed: string;         // Which model generated this
}

/**
 * Visualization data structure (subset needed for caching).
 */
export interface VisualizationData {
    functions: Record<string, { name: string; line: number; file: string; call_count?: number; branches?: any[] }>;
    call_graph: Record<string, string[]>;
    covered_functions: string[];
    dead_functions: string[];
    why_not_covered: Record<string, {
        function: string;
        root_cause: string;
        root_cause_detail?: { type: string; caller: string; line: number; branch_type?: string; branch_condition?: string; branch_line?: number };
        reasons: any[];
    }>;
}

/**
 * Cache manager for auto-explain functionality.
 * Stores explanations persistently and manages background processing.
 *
 * Features (matching PyCharm plugin):
 * - Persistent file-based cache (explanation_cache.json)
 * - Smart invalidation (5-factor content hash)
 * - Priority queue (user-focused items processed first)
 * - Background idle-time worker
 * - Explorer notification of cached results via SSE
 */
export class ExplanationCacheManager {
    private cache: Map<string, CachedExplanation> = new Map();
    private cacheFilePath: string;
    private pendingQueue: string[] = [];
    private priorityFunctions: Map<string, number> = new Map(); // funcName -> priority timestamp
    private isProcessing = false;
    private lastUserRequestTime = Date.now();
    private readonly idleThresholdMs = 5000; // 5 seconds of idle before auto-processing
    private backgroundTimer: NodeJS.Timeout | null = null;
    private isShutdown = false;
    private llmEndpoint: string;
    private visualizationData: VisualizationData | null = null;

    // Callbacks
    private onCachedExplanation?: (explanation: CachedExplanation) => void;
    private onAIStatusCheck?: () => boolean; // Returns true if AI server is available
    private onAutoExplainStatus?: (active: boolean, funcName: string | null, cached: number, total: number) => void;

    constructor(
        cacheDir: string,
        llmEndpoint: string = 'http://127.0.0.1:8080/v1',
        onCachedExplanation?: (explanation: CachedExplanation) => void,
        onAIStatusCheck?: () => boolean,
        onAutoExplainStatus?: (active: boolean, funcName: string | null, cached: number, total: number) => void
    ) {
        this.cacheFilePath = path.join(cacheDir, 'explanation_cache.json');
        this.llmEndpoint = llmEndpoint;
        this.onCachedExplanation = onCachedExplanation;
        this.onAIStatusCheck = onAIStatusCheck;
        this.onAutoExplainStatus = onAutoExplainStatus;

        // Ensure cache directory exists
        const dir = path.dirname(this.cacheFilePath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }

        this.loadCache();
        this.startBackgroundWorker();
    }

    // ==================== Cache Key & Lookup ====================

    getCacheKey(funcName: string, filePath: string): string {
        return `${funcName}@${filePath}`;
    }

    getExplanation(funcName: string, filePath: string): CachedExplanation | undefined {
        const key = this.getCacheKey(funcName, filePath);
        return this.cache.get(key);
    }

    hasValidExplanation(funcName: string, filePath: string, contentHash: string): boolean {
        const cached = this.getExplanation(funcName, filePath);
        return cached !== undefined && cached.contentHash === contentHash;
    }

    storeExplanation(explanation: CachedExplanation): void {
        const key = this.getCacheKey(explanation.functionName, explanation.filePath);
        this.cache.set(key, explanation);
        this.saveCache();

        // Notify Interactive Explorer of the cached explanation
        this.onCachedExplanation?.(explanation);
    }

    // ==================== User Activity Tracking ====================

    markUserActivity(): void {
        this.lastUserRequestTime = Date.now();
    }

    isIdle(): boolean {
        return Date.now() - this.lastUserRequestTime > this.idleThresholdMs;
    }

    // ==================== Priority Queue ====================

    /**
     * Prioritize a function for explanation (user searched or focused on it).
     * These get processed before regular queue items.
     */
    prioritizeFunction(funcName: string, reason: string = 'user_interaction'): void {
        this.priorityFunctions.set(funcName, Date.now());
        if (!this.pendingQueue.includes(funcName)) {
            this.pendingQueue.push(funcName);
        }
        console.log(`[AutoExplain] Prioritized: ${funcName} (${reason})`);
    }

    /**
     * Prioritize multiple functions (e.g., search results).
     */
    prioritizeFunctions(funcNames: string[], reason: string = 'search'): void {
        const timestamp = Date.now();
        for (const funcName of funcNames) {
            this.priorityFunctions.set(funcName, timestamp);
            if (!this.pendingQueue.includes(funcName)) {
                this.pendingQueue.push(funcName);
            }
        }
        if (funcNames.length > 0) {
            console.log(`[AutoExplain] Prioritized ${funcNames.length} functions (${reason})`);
        }
    }

    queueForExplanation(funcName: string): void {
        if (!this.pendingQueue.includes(funcName)) {
            this.pendingQueue.push(funcName);
            console.log(`[AutoExplain] Queued: ${funcName} (queue size: ${this.pendingQueue.length})`);
        }
    }

    /**
     * Queue dead functions for auto-explanation.
     * Only queues functions not already cached with valid hash.
     */
    queueDeadFunctions(deadFunctions: string[]): void {
        for (const funcName of deadFunctions) {
            const funcInfo = this.visualizationData?.functions[funcName];
            const filePath = funcInfo?.file || '';
            const contentHash = this.computeContentHash(funcName, filePath, funcInfo?.line || 0);

            if (!this.hasValidExplanation(funcName, filePath, contentHash)) {
                this.queueForExplanation(funcName);
            }
        }
        console.log(`[AutoExplain] Queued ${this.pendingQueue.length} functions for auto-explanation`);
    }

    // ==================== Visualization Data ====================

    updateVisualizationData(data: VisualizationData): void {
        this.visualizationData = data;

        // Queue dead functions for background processing
        if (data.dead_functions && data.dead_functions.length > 0) {
            this.queueDeadFunctions(data.dead_functions);
        }
    }

    // ==================== Content Hash ====================

    /**
     * Compute a content hash that captures everything affecting the explanation:
     * 1. Source code of the function
     * 2. Coverage status (dead/alive)
     * 3. Callers (who calls this function)
     * 4. Callees (what this function calls)
     * 5. whyNotCovered reason
     */
    private computeContentHash(funcName: string, filePath: string, line: number): string {
        const data = this.visualizationData;
        if (!data) { return 'no_data'; }
        if (!filePath || line <= 0) { return 'unknown'; }

        try {
            const parts: string[] = [];

            // 1. Source code hash
            if (fs.existsSync(filePath)) {
                const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
                const startIdx = Math.max(0, line - 1);
                const endIdx = Math.min(lines.length, line + 50);
                const sourceCode = lines.slice(startIdx, endIdx).join('\n');
                parts.push(`src:${this.simpleHash(sourceCode)}`);
            }

            // 2. Coverage status
            const isAlive = (data.covered_functions || []).includes(funcName);
            parts.push(`alive:${isAlive}`);

            // 3. Callers (sorted for consistent hash)
            const callers = Object.entries(data.call_graph || {})
                .filter(([_, callees]) => callees.includes(funcName))
                .map(([caller]) => caller)
                .sort();
            const coveredSet = new Set(data.covered_functions || []);
            const aliveCallers = callers.filter(c => coveredSet.has(c));
            const deadCallers = callers.filter(c => !coveredSet.has(c));
            parts.push(`callers:${this.simpleHash(callers.join(','))}`);
            parts.push(`aliveCallers:${aliveCallers.length};deadCallers:${deadCallers.length}`);

            // 4. Callees
            const callees = (data.call_graph[funcName] || []).sort();
            parts.push(`callees:${this.simpleHash(callees.join(','))}`);

            // 5. whyNotCovered reason
            const whyInfo = (data.why_not_covered || {})[funcName];
            const whyReason = whyInfo?.root_cause || '';
            parts.push(`why:${whyReason}`);

            return this.simpleHash(parts.join(';'));
        } catch (e) {
            return 'error';
        }
    }

    private simpleHash(str: string): string {
        return crypto.createHash('md5').update(str).digest('hex').substring(0, 8);
    }

    // ==================== Background Worker ====================

    private startBackgroundWorker(): void {
        // Check every 3 seconds for idle processing (matches PyCharm)
        this.backgroundTimer = setInterval(() => {
            if (!this.isShutdown) {
                this.processQueueIfIdle();
            }
        }, 3000);
    }

    /**
     * Select the next function to process, prioritizing user-interacted items.
     */
    private selectNextFunction(): string | null {
        if (this.pendingQueue.length === 0) { return null; }

        // Find highest priority item (most recently user-interacted)
        const prioritized = this.pendingQueue.filter(f => this.priorityFunctions.has(f));
        if (prioritized.length > 0) {
            let best = prioritized[0];
            let bestTime = this.priorityFunctions.get(best) || 0;
            for (const f of prioritized) {
                const t = this.priorityFunctions.get(f) || 0;
                if (t > bestTime) {
                    best = f;
                    bestTime = t;
                }
            }
            // Remove from queue
            const idx = this.pendingQueue.indexOf(best);
            if (idx !== -1) { this.pendingQueue.splice(idx, 1); }
            return best;
        }

        // No priority items, take from front (FIFO)
        return this.pendingQueue.shift() || null;
    }

    private async processQueueIfIdle(): Promise<void> {
        if (this.isProcessing || this.pendingQueue.length === 0) { return; }
        if (!this.isIdle()) { return; }

        // Check if AI server is running
        if (this.onAIStatusCheck && !this.onAIStatusCheck()) { return; }

        const funcName = this.selectNextFunction();
        if (!funcName) { return; }

        this.isProcessing = true;
        const isPriority = this.priorityFunctions.has(funcName);
        this.priorityFunctions.delete(funcName);
        console.log(`[AutoExplain] Processing${isPriority ? ' (PRIORITY)' : ''}: ${funcName} (remaining: ${this.pendingQueue.length})`);

        const totalDead = this.visualizationData?.dead_functions?.length || 0;
        this.onAutoExplainStatus?.(true, funcName, this.cache.size, totalDead);

        try {
            await this.processAutoExplain(funcName);
        } catch (e) {
            console.error(`[AutoExplain] Error processing ${funcName}:`, e);
        } finally {
            this.isProcessing = false;
            this.onAutoExplainStatus?.(false, null, this.cache.size, totalDead);
        }
    }

    private async processAutoExplain(funcName: string): Promise<void> {
        const data = this.visualizationData;
        if (!data) { return; }

        const funcInfo = data.functions[funcName];
        const whyInfo = (data.why_not_covered || {})[funcName];

        if (!funcInfo || !whyInfo) { return; }

        const filePath = funcInfo.file || '';
        const line = funcInfo.line;
        const contentHash = this.computeContentHash(funcName, filePath, line);

        // Check cache again (might have been filled by user request)
        if (this.hasValidExplanation(funcName, filePath, contentHash)) {
            console.log(`[AutoExplain] Already cached: ${funcName}`);
            return;
        }

        // Build rich context for auto-explain with call chain and root cause branch
        const sourceCode = this.readFunctionSource(filePath, line);
        const rootCause = whyInfo.root_cause;
        const callerInfo = whyInfo.root_cause_detail;
        const reasons = whyInfo.reasons || [];

        // Trace call chain from root caller to dead function
        const callChain = this.traceCallChainToFunction(funcName, data);

        // Read root caller source (where the branch decision happens)
        let rootCallerSource = '';
        if (callerInfo?.caller) {
            const callerFunc = data.functions[callerInfo.caller];
            if (callerFunc?.file) {
                rootCallerSource = this.readFunctionSource(callerFunc.file, callerFunc.line);
            }
        }

        const prompt = this.buildAutoExplainPrompt(funcName, rootCause, sourceCode, callerInfo, callChain, rootCallerSource, reasons);

        try {
            const response = await this.callLLM(prompt);
            const explanation: CachedExplanation = {
                functionName: funcName,
                filePath,
                line,
                contentHash,
                whyNotCovered: rootCause,
                explanation: response,
                timestamp: Date.now(),
                modelUsed: 'auto'
            };
            this.storeExplanation(explanation);
            console.log(`[AutoExplain] Cached explanation for: ${funcName}`);
        } catch (e) {
            console.error(`[AutoExplain] Failed to get explanation for ${funcName}:`, e);
        }
    }

    private readFunctionSource(filePath: string, line: number): string {
        if (!filePath || line <= 0) { return ''; }
        try {
            if (!fs.existsSync(filePath)) { return ''; }
            const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
            const startIdx = Math.max(0, line - 1);
            const endIdx = Math.min(lines.length, line + 30);
            return lines.slice(startIdx, endIdx).join('\n');
        } catch (e) {
            return '';
        }
    }

    /**
     * Trace the call chain from root caller down to a dead function using the call graph.
     */
    private traceCallChainToFunction(funcName: string, data: any): string[] {
        const chain: string[] = [funcName];
        const visited = new Set<string>();

        // Build reverse graph (callee -> callers)
        const reverseGraph: Record<string, string[]> = {};
        for (const [caller, callees] of Object.entries(data.call_graph || {})) {
            for (const callee of (callees as string[])) {
                if (!reverseGraph[callee]) { reverseGraph[callee] = []; }
                reverseGraph[callee].push(caller);
            }
        }
        for (const [caller, callees] of Object.entries(data.resolved_call_graph || {})) {
            for (const callee of (callees as string[])) {
                if (!reverseGraph[callee]) { reverseGraph[callee] = []; }
                reverseGraph[callee].push(caller);
            }
        }

        // Walk up to root (max 20 levels)
        let current = funcName;
        const coveredSet = new Set(data.covered_functions || []);
        for (let i = 0; i < 20; i++) {
            if (visited.has(current)) { break; }
            visited.add(current);
            const callers = reverseGraph[current];
            if (!callers || callers.length === 0) { break; }
            const nextCaller = callers.find(c => coveredSet.has(c)) || callers[0];
            chain.unshift(nextCaller);
            current = nextCaller;
        }
        return chain;
    }

    private buildAutoExplainPrompt(
        funcName: string,
        rootCause: string,
        sourceCode: string,
        callerInfo?: { type: string; caller: string; line: number; branch_type?: string; branch_condition?: string; branch_line?: number } | null,
        callChain: string[] = [],
        rootCallerSource: string = '',
        reasons: Array<{ explanation?: string }> = []
    ): string {
        let prompt = `Explain why this function is not executed:\n\n`;
        prompt += `Function: ${funcName}\n`;
        prompt += `Root cause: ${rootCause}\n`;

        if (callerInfo) {
            if (callerInfo.caller) {
                prompt += `\nRoot caller (where the decision happens): ${callerInfo.caller}\n`;
            }
            if (callerInfo.branch_condition) {
                prompt += `Branch not taken: ${callerInfo.branch_type || 'if'} ${callerInfo.branch_condition}`;
                if (callerInfo.branch_line) { prompt += ` (line ${callerInfo.branch_line})`; }
                prompt += '\n';
            }
        }

        if (callChain.length > 1) {
            prompt += `\nCall chain (root → dead):\n  ${callChain.join(' → ')}\n`;
        }

        for (const reason of reasons) {
            if (reason.explanation && reason.explanation.includes('Chain:')) {
                prompt += `\n${reason.explanation}\n`;
                break;
            }
        }

        if (rootCallerSource) {
            prompt += `\nRoot caller source:\n\`\`\`python\n${rootCallerSource}\n\`\`\`\n`;
        }

        if (sourceCode) {
            prompt += `\nDead function source:\n\`\`\`python\n${sourceCode}\n\`\`\`\n`;
        }

        prompt += `\nProvide a concise 2-3 sentence explanation of why this function is dead and what condition would need to change to make it execute.`;
        return prompt;
    }

    // ==================== LLM Integration ====================

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
                max_tokens: 512, // Shorter for auto-explain (tooltip-sized)
                stream: false
            });

            const options = {
                hostname: url.hostname,
                port: url.port || '8080',
                path: url.pathname,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(postData)
                },
                timeout: 60000 // 1 minute for auto-explain
            };

            const req = http.request(options, (res) => {
                const chunks: Buffer[] = [];
                res.on('data', (chunk: Buffer) => chunks.push(chunk));
                res.on('end', () => {
                    try {
                        const responseBody = Buffer.concat(chunks).toString('utf-8');
                        const jsonResponse = JSON.parse(responseBody);
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

    // ==================== Persistence ====================

    private loadCache(): void {
        try {
            if (fs.existsSync(this.cacheFilePath)) {
                const json = fs.readFileSync(this.cacheFilePath, 'utf-8');
                const loaded: Record<string, CachedExplanation> = JSON.parse(json);
                this.cache.clear();
                for (const [key, value] of Object.entries(loaded)) {
                    this.cache.set(key, value);
                }
                console.log(`[AutoExplain] Loaded ${this.cache.size} cached explanations`);
            }
        } catch (e) {
            console.warn(`[AutoExplain] Failed to load cache: ${e}`);
        }
    }

    private saveCache(): void {
        try {
            const dir = path.dirname(this.cacheFilePath);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
            const obj: Record<string, CachedExplanation> = {};
            this.cache.forEach((value, key) => { obj[key] = value; });
            fs.writeFileSync(this.cacheFilePath, JSON.stringify(obj, null, 2));
        } catch (e) {
            console.warn(`[AutoExplain] Failed to save cache: ${e}`);
        }
    }

    // ==================== Public API ====================

    getCacheStats(): { totalCached: number; pendingQueue: number; isProcessing: boolean; isIdle: boolean } {
        return {
            totalCached: this.cache.size,
            pendingQueue: this.pendingQueue.length,
            isProcessing: this.isProcessing,
            isIdle: this.isIdle()
        };
    }

    shutdown(): void {
        this.isShutdown = true;
        if (this.backgroundTimer) {
            clearInterval(this.backgroundTimer);
            this.backgroundTimer = null;
        }
        this.saveCache();
    }
}
