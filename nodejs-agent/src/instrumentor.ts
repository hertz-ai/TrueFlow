/**
 * Core instrumentor that wraps functions and tracks calls.
 * Uses AsyncLocalStorage for maintaining call context across async boundaries.
 */

import { AsyncLocalStorage } from 'async_hooks';
import { performance } from 'perf_hooks';
import { TraceSocketServer } from './socket-server';
import { detectProtocol, detectInvocationType } from './protocol-detectors';
import * as path from 'path';
import * as fs from 'fs';

export interface InstrumentorConfig {
    host: string;
    port: number;
    includes: string[];
    excludes: string[];
    maxDepth: number;
    maxCalls: number;
    sampleRate: number;
}

interface CallContext {
    callId: string;
    depth: number;
    parentId: string | null;
}

interface MethodCall {
    callId: string;
    module: string;
    functionName: string;
    file: string;
    line: number;
    depth: number;
    parentId: string | null;
    startTime: number;
    endTime?: number;
    durationMs?: number;
    exception?: string;
    protocol?: string;
    invocationType?: string;
    threadId: number;
    threadName: string;
}

export class Instrumentor {
    private config: InstrumentorConfig;
    private asyncContext = new AsyncLocalStorage<CallContext>();
    private socketServer: TraceSocketServer;
    private sessionId: string;
    private callCounter = 0;
    private totalCalls = 0;
    private sampleCounter = 0;
    private enabled = true;
    private finalized = false;
    private completedCalls: MethodCall[] = [];
    private registeredFunctions = new Map<string, { file: string; line: number }>();

    constructor(config: InstrumentorConfig) {
        this.config = config;
        this.sessionId = `session_${new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 15)}`;
        this.socketServer = new TraceSocketServer(config.host, config.port, this);

        console.log(`[TrueFlow] Session ID: ${this.sessionId}`);
    }

    /**
     * Start the socket server for IDE communication.
     */
    start(): void {
        this.socketServer.start();
    }

    /**
     * Check if a module path should be instrumented.
     */
    shouldInstrument(modulePath: string): boolean {
        if (!this.enabled || this.finalized) return false;

        // Normalize path
        const normalizedPath = modulePath.replace(/\\/g, '/');

        // Check excludes first
        for (const exclude of this.config.excludes) {
            if (normalizedPath.includes(exclude)) {
                return false;
            }
        }

        // If includes is empty, instrument everything not excluded
        if (this.config.includes.length === 0) {
            return true;
        }

        // Check includes
        for (const include of this.config.includes) {
            if (normalizedPath.includes(include)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Wrap a function with tracing.
     */
    wrapFunction(fn: Function, modulePath: string, functionName: string, line = 0): Function {
        const self = this;

        // Skip if already wrapped
        if ((fn as any).__trueflow_wrapped__) {
            return fn;
        }

        const wrapped = function (this: any, ...args: any[]): any {
            // Check limits
            if (!self.enabled || self.finalized) {
                return fn.apply(this, args);
            }

            if (self.totalCalls >= self.config.maxCalls) {
                if (self.enabled) {
                    console.log(`[TrueFlow] Max calls reached (${self.config.maxCalls}), disabling tracing`);
                    self.enabled = false;
                }
                return fn.apply(this, args);
            }

            // Sampling
            if (self.config.sampleRate > 1) {
                self.sampleCounter++;
                if (self.sampleCounter % self.config.sampleRate !== 0) {
                    return fn.apply(this, args);
                }
            }

            // Get parent context
            const parent = self.asyncContext.getStore();
            const depth = parent ? parent.depth + 1 : 0;

            // Check depth limit
            if (depth >= self.config.maxDepth) {
                return fn.apply(this, args);
            }

            // Generate call ID
            const callId = `call_${++self.callCounter}`;
            self.totalCalls++;

            // Create call record
            const call: MethodCall = {
                callId,
                module: modulePath,
                functionName,
                file: modulePath,
                line,
                depth,
                parentId: parent?.callId || null,
                startTime: performance.now(),
                threadId: process.pid,
                threadName: `node-${process.pid}`,
                protocol: detectProtocol(modulePath, functionName),
                invocationType: detectInvocationType(modulePath, functionName)
            };

            // Register function
            const funcKey = `${modulePath}.${functionName}`;
            if (!self.registeredFunctions.has(funcKey)) {
                self.registeredFunctions.set(funcKey, { file: modulePath, line });
            }

            // Emit call event
            self.emitCall(call);

            // Create new context for this call
            const newContext: CallContext = {
                callId,
                depth,
                parentId: parent?.callId || null
            };

            try {
                // Execute function within async context
                const result = self.asyncContext.run(newContext, () => {
                    return fn.apply(this, args);
                });

                // Handle promises (async functions)
                if (result instanceof Promise) {
                    return result.then(
                        (value) => {
                            self.completeCall(call);
                            return value;
                        },
                        (error) => {
                            self.completeCall(call, error);
                            throw error;
                        }
                    );
                }

                // Sync function
                self.completeCall(call);
                return result;

            } catch (error) {
                self.completeCall(call, error);
                throw error;
            }
        };

        // Mark as wrapped and preserve original properties
        (wrapped as any).__trueflow_wrapped__ = true;
        (wrapped as any).__trueflow_original__ = fn;

        // Preserve function name and length
        Object.defineProperty(wrapped, 'name', { value: functionName });
        Object.defineProperty(wrapped, 'length', { value: fn.length });

        return wrapped;
    }

    /**
     * Complete a call and emit return event.
     */
    private completeCall(call: MethodCall, error?: any): void {
        call.endTime = performance.now();
        call.durationMs = call.endTime - call.startTime;

        if (error) {
            call.exception = error instanceof Error
                ? `${error.name}: ${error.message}`
                : String(error);
        }

        this.completedCalls.push(call);
        this.emitReturn(call);
    }

    /**
     * Emit a call event to connected clients.
     */
    private emitCall(call: MethodCall): void {
        const event = {
            type: 'call',
            timestamp: Date.now() / 1000,
            call_id: call.callId,
            module: call.module,
            function: call.functionName,
            file: call.file,
            line: call.line,
            depth: call.depth,
            parent_id: call.parentId,
            thread_id: call.threadId,
            thread_name: call.threadName,
            session_id: this.sessionId,
            process_id: process.pid,
            language: 'nodejs',
            protocol: call.protocol,
            invocation_type: call.invocationType
        };

        this.socketServer.broadcast(JSON.stringify(event));
    }

    /**
     * Emit a return event to connected clients.
     */
    private emitReturn(call: MethodCall): void {
        const event = {
            type: 'return',
            timestamp: Date.now() / 1000,
            call_id: call.callId,
            module: call.module,
            function: call.functionName,
            file: call.file,
            line: call.line,
            depth: call.depth,
            parent_id: call.parentId,
            duration_ms: call.durationMs,
            thread_id: call.threadId,
            session_id: this.sessionId,
            process_id: process.pid,
            language: 'nodejs',
            exception: call.exception
        };

        this.socketServer.broadcast(JSON.stringify(event));
    }

    /**
     * Get function registry JSON for new clients.
     */
    getFunctionRegistryJson(): string {
        const functions = Array.from(this.registeredFunctions.entries()).map(([key, info]) => {
            const [module, func] = key.split('.');
            return {
                module: module || '',
                function: func || key,
                file: info.file,
                line: info.line
            };
        });

        return JSON.stringify({
            type: 'function_registry',
            timestamp: Date.now() / 1000,
            session_id: this.sessionId,
            language: 'nodejs',
            trace_data: {
                total_functions: functions.length,
                functions
            }
        });
    }

    /**
     * Finalize tracing and export reports.
     */
    finalize(): void {
        if (this.finalized) return;
        this.finalized = true;
        this.enabled = false;

        console.log(`[TrueFlow] Finalizing trace with ${this.completedCalls.length} calls`);

        // Export trace data
        const traceDir = process.env.TRUEFLOW_TRACE_DIR || './.trueflow/traces';
        this.exportTraces(traceDir);

        // Stop socket server
        this.socketServer.stop();
    }

    /**
     * Export trace data to files.
     */
    private exportTraces(outputDir: string): void {
        try {
            if (!fs.existsSync(outputDir)) {
                fs.mkdirSync(outputDir, { recursive: true });
            }

            const timestamp = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 15);

            // JSON trace
            const jsonPath = path.join(outputDir, `nodejs_trace_${timestamp}.json`);
            const traceData = {
                session_id: this.sessionId,
                timestamp,
                language: 'nodejs',
                total_calls: this.completedCalls.length,
                total_functions: this.registeredFunctions.size,
                calls: this.completedCalls.map(call => ({
                    call_id: call.callId,
                    module: call.module,
                    function: call.functionName,
                    file: call.file,
                    line: call.line,
                    depth: call.depth,
                    parent_id: call.parentId,
                    duration_ms: call.durationMs,
                    exception: call.exception,
                    protocol: call.protocol,
                    invocation_type: call.invocationType
                }))
            };
            fs.writeFileSync(jsonPath, JSON.stringify(traceData, null, 2));
            console.log(`[TrueFlow] JSON trace exported to: ${jsonPath}`);

            // Performance metrics
            const perfPath = path.join(outputDir, `${this.sessionId}_performance.json`);
            const methodMetrics = new Map<string, { count: number; totalTime: number; protocol?: string }>();

            for (const call of this.completedCalls) {
                const key = `${call.module}.${call.functionName}`;
                const existing = methodMetrics.get(key) || { count: 0, totalTime: 0, protocol: call.protocol };
                existing.count++;
                existing.totalTime += call.durationMs || 0;
                methodMetrics.set(key, existing);
            }

            const sortedMetrics = Array.from(methodMetrics.entries())
                .map(([key, stats]) => ({
                    method: key,
                    call_count: stats.count,
                    total_time_ms: stats.totalTime,
                    avg_time_ms: stats.totalTime / stats.count,
                    protocol: stats.protocol
                }))
                .sort((a, b) => b.total_time_ms - a.total_time_ms);

            fs.writeFileSync(perfPath, JSON.stringify({
                session_id: this.sessionId,
                language: 'nodejs',
                statistics: {
                    total_calls: this.completedCalls.length,
                    total_functions: this.registeredFunctions.size,
                    total_duration_ms: this.completedCalls.reduce((sum, c) => sum + (c.durationMs || 0), 0)
                },
                function_metrics: sortedMetrics
            }, null, 2));
            console.log(`[TrueFlow] Performance metrics exported to: ${perfPath}`);

        } catch (error) {
            console.error('[TrueFlow] Failed to export traces:', error);
        }
    }

    /**
     * Get current session ID.
     */
    getSessionId(): string {
        return this.sessionId;
    }

    /**
     * Check if tracing is enabled.
     */
    isEnabled(): boolean {
        return this.enabled && !this.finalized;
    }

    /**
     * Get total call count.
     */
    getTotalCalls(): number {
        return this.totalCalls;
    }
}
