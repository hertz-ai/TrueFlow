/**
 * TrueFlow Browser Runtime
 *
 * Injected into browser applications to track function calls and send traces
 * to the TrueFlow IDE plugin via WebSocket.
 *
 * Usage:
 *   1. Import at the top of your app: import '@trueflow/browser-agent'
 *   2. Or include via script tag: <script src="trueflow-runtime.js"></script>
 *   3. Connect: window.__trueflow__.connect(8765)
 */

interface TraceEvent {
    type: 'call' | 'return';
    timestamp: number;
    call_id: string;
    module: string;
    function: string;
    file?: string;
    line?: number;
    depth: number;
    parent_id: string | null;
    duration_ms?: number;
    exception?: string;
    language: 'javascript';
    session_id: string;
    process_id: number;
}

interface CallContext {
    callId: string;
    startTime: number;
    file: string;
    func: string;
    line: number;
}

class TrueFlowBrowser {
    private ws: WebSocket | null = null;
    private callStack: CallContext[] = [];
    private callCounter = 0;
    private sessionId: string;
    private connected = false;
    private buffer: TraceEvent[] = [];
    private maxBufferSize = 1000;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;
    private reconnectDelay = 1000;

    constructor() {
        this.sessionId = `browser_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        console.log('[TrueFlow] Browser agent initialized, session:', this.sessionId);
    }

    /**
     * Connect to the TrueFlow IDE server.
     */
    connect(port: number = 8765): void {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log('[TrueFlow] Already connected');
            return;
        }

        try {
            const url = `ws://localhost:${port}/trace`;
            console.log('[TrueFlow] Connecting to:', url);

            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                console.log('[TrueFlow] Connected to IDE');
                this.connected = true;
                this.reconnectAttempts = 0;
                this.flushBuffer();
            };

            this.ws.onclose = () => {
                console.log('[TrueFlow] Disconnected from IDE');
                this.connected = false;
                this.attemptReconnect(port);
            };

            this.ws.onerror = (error) => {
                console.log('[TrueFlow] Connection error:', error);
            };

            this.ws.onmessage = (event) => {
                this.handleMessage(event.data);
            };

        } catch (error) {
            console.log('[TrueFlow] Failed to connect:', error);
        }
    }

    /**
     * Attempt to reconnect after disconnection.
     */
    private attemptReconnect(port: number): void {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[TrueFlow] Max reconnection attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`[TrueFlow] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => {
            this.connect(port);
        }, delay);
    }

    /**
     * Handle incoming messages from the IDE.
     */
    private handleMessage(data: string): void {
        try {
            const message = JSON.parse(data);
            if (message.type === 'pause') {
                console.log('[TrueFlow] Tracing paused');
            } else if (message.type === 'resume') {
                console.log('[TrueFlow] Tracing resumed');
            }
        } catch (e) {
            // Ignore parse errors
        }
    }

    /**
     * Called when entering a function.
     */
    enter(file: string, func: string, line: number = 0): string {
        const callId = `call_${++this.callCounter}`;
        const parentId = this.callStack.length > 0
            ? this.callStack[this.callStack.length - 1].callId
            : null;

        const context: CallContext = {
            callId,
            startTime: performance.now(),
            file,
            func,
            line
        };
        this.callStack.push(context);

        const event: TraceEvent = {
            type: 'call',
            timestamp: Date.now() / 1000,
            call_id: callId,
            module: file,
            function: func,
            file,
            line,
            depth: this.callStack.length - 1,
            parent_id: parentId,
            language: 'javascript',
            session_id: this.sessionId,
            process_id: 0
        };

        this.emit(event);
        return callId;
    }

    /**
     * Called when exiting a function.
     */
    exit(error?: Error): void {
        const context = this.callStack.pop();
        if (!context) return;

        const durationMs = performance.now() - context.startTime;
        const parentId = this.callStack.length > 0
            ? this.callStack[this.callStack.length - 1].callId
            : null;

        const event: TraceEvent = {
            type: 'return',
            timestamp: Date.now() / 1000,
            call_id: context.callId,
            module: context.file,
            function: context.func,
            file: context.file,
            line: context.line,
            depth: this.callStack.length,
            parent_id: parentId,
            duration_ms: durationMs,
            language: 'javascript',
            session_id: this.sessionId,
            process_id: 0,
            exception: error ? `${error.name}: ${error.message}` : undefined
        };

        this.emit(event);
    }

    /**
     * Wrap a function with tracing.
     */
    wrap<T extends (...args: any[]) => any>(
        fn: T,
        file: string,
        name?: string
    ): T {
        const self = this;
        const funcName = name || fn.name || 'anonymous';

        const wrapped = function (this: any, ...args: any[]): any {
            self.enter(file, funcName);
            try {
                const result = fn.apply(this, args);

                // Handle promises
                if (result instanceof Promise) {
                    return result
                        .then((value) => {
                            self.exit();
                            return value;
                        })
                        .catch((error) => {
                            self.exit(error);
                            throw error;
                        });
                }

                self.exit();
                return result;
            } catch (error) {
                self.exit(error as Error);
                throw error;
            }
        } as T;

        // Preserve function properties
        Object.defineProperty(wrapped, 'name', { value: funcName });
        Object.defineProperty(wrapped, 'length', { value: fn.length });

        return wrapped;
    }

    /**
     * Emit a trace event.
     */
    private emit(event: TraceEvent): void {
        if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(event));
        } else {
            // Buffer events when disconnected
            this.buffer.push(event);
            if (this.buffer.length > this.maxBufferSize) {
                this.buffer.shift(); // Remove oldest
            }
        }
    }

    /**
     * Flush buffered events.
     */
    private flushBuffer(): void {
        if (!this.connected || !this.ws) return;

        while (this.buffer.length > 0) {
            const event = this.buffer.shift();
            if (event) {
                this.ws.send(JSON.stringify(event));
            }
        }
    }

    /**
     * Disconnect from the IDE.
     */
    disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.connected = false;
    }

    /**
     * Get current session ID.
     */
    getSessionId(): string {
        return this.sessionId;
    }

    /**
     * Check if connected.
     */
    isConnected(): boolean {
        return this.connected;
    }

    /**
     * Get current call depth.
     */
    getDepth(): number {
        return this.callStack.length;
    }
}

// Create global instance
const trueflow = new TrueFlowBrowser();

// Export for module usage
export { TrueFlowBrowser, trueflow };

// Attach to window for browser usage
if (typeof window !== 'undefined') {
    (window as any).__trueflow__ = trueflow;
}

// Auto-connect if environment variable is set
if (typeof process !== 'undefined' && process.env?.TRUEFLOW_BROWSER_PORT) {
    const port = parseInt(process.env.TRUEFLOW_BROWSER_PORT, 10);
    trueflow.connect(port);
}
