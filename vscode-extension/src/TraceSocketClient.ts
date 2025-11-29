import * as net from 'net';
import { EventEmitter } from 'events';

/**
 * TraceSocketClient - Connects to the Python trace server for real-time tracing.
 *
 * Protocol: Newline-delimited JSON on port 5678
 *
 * Example trace event:
 * {"type":"call","timestamp":123.45,"call_id":"abc","module":"foo","function":"bar",
 *  "file":"/path","line":10,"depth":2,"correlation_id":"cycle_001"}
 */
export interface TraceEvent {
    type: 'call' | 'return' | 'exception';
    timestamp: number;
    call_id: string;
    module: string;
    function: string;
    file: string;
    line: number;
    depth: number;
    correlation_id?: string;
    args?: any;
    return_value?: any;
    exception?: string;
    duration_ms?: number;
}

export interface PerformanceData {
    module: string;
    function: string;
    calls: number;
    total: number;
    avg: number;
    min: number;
    max: number;
}

export class TraceSocketClient extends EventEmitter {
    private socket: net.Socket | null = null;
    private buffer = '';
    private connected = false;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;
    private reconnectDelay = 2000;

    // Performance tracking
    private callStats = new Map<string, { count: number; total: number; min: number; max: number }>();
    private callStack = new Map<string, { start: number; depth: number }>();

    // Event buffer for UI updates (circular buffer)
    private eventBuffer: TraceEvent[] = [];
    private maxBufferSize = 10000;

    // Sampling for high-frequency events
    private eventCounter = 0;
    private sampleRate = 1; // Process every event by default

    constructor() {
        super();
    }

    /**
     * Connect to the trace server
     */
    connect(host: string = 'localhost', port: number = 5678): Promise<void> {
        return new Promise((resolve, reject) => {
            if (this.connected) {
                resolve();
                return;
            }

            this.socket = new net.Socket();

            this.socket.on('connect', () => {
                this.connected = true;
                this.reconnectAttempts = 0;
                console.log(`[TraceSocketClient] Connected to ${host}:${port}`);
                this.emit('connected');
                resolve();
            });

            this.socket.on('data', (data: Buffer) => {
                this.processData(data);
            });

            this.socket.on('error', (err: Error) => {
                console.error('[TraceSocketClient] Socket error:', err.message);
                this.emit('error', err);

                if (!this.connected) {
                    reject(err);
                }
            });

            this.socket.on('close', () => {
                const wasConnected = this.connected;
                this.connected = false;
                console.log('[TraceSocketClient] Connection closed');
                this.emit('disconnected');

                if (wasConnected) {
                    this.attemptReconnect(host, port);
                }
            });

            this.socket.connect(port, host);
        });
    }

    /**
     * Attempt to reconnect after connection loss
     */
    private attemptReconnect(host: string, port: number): void {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[TraceSocketClient] Max reconnect attempts reached');
            this.emit('maxReconnectAttemptsReached');
            return;
        }

        this.reconnectAttempts++;
        console.log(`[TraceSocketClient] Attempting reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);

        setTimeout(() => {
            this.connect(host, port).catch(() => {
                // Reconnect failed, will try again
            });
        }, this.reconnectDelay);
    }

    /**
     * Process incoming data from socket
     */
    private processData(data: Buffer): void {
        this.buffer += data.toString();
        const lines = this.buffer.split('\n');
        this.buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.trim()) {
                try {
                    const event = JSON.parse(line) as TraceEvent;
                    this.handleEvent(event);
                } catch (e) {
                    console.error('[TraceSocketClient] Failed to parse event:', line);
                }
            }
        }
    }

    /**
     * Handle a single trace event
     */
    private handleEvent(event: TraceEvent): void {
        // Apply sampling for high-frequency events
        this.eventCounter++;
        if (this.eventCounter % this.sampleRate !== 0) {
            return;
        }

        // Add to circular buffer
        this.eventBuffer.push(event);
        if (this.eventBuffer.length > this.maxBufferSize) {
            this.eventBuffer.shift();
        }

        // Track performance
        const key = `${event.module}.${event.function}`;

        if (event.type === 'call') {
            this.callStack.set(event.call_id, {
                start: event.timestamp,
                depth: event.depth
            });
        } else if (event.type === 'return' && event.duration_ms !== undefined) {
            const stats = this.callStats.get(key) || { count: 0, total: 0, min: Infinity, max: 0 };
            stats.count++;
            stats.total += event.duration_ms;
            stats.min = Math.min(stats.min, event.duration_ms);
            stats.max = Math.max(stats.max, event.duration_ms);
            this.callStats.set(key, stats);
        }

        // Emit event for real-time updates
        this.emit('event', event);

        // Emit batch update periodically for efficiency
        if (this.eventCounter % 100 === 0) {
            this.emit('batch', this.eventBuffer.slice(-100));
        }
    }

    /**
     * Get performance data for all tracked functions
     */
    getPerformanceData(): PerformanceData[] {
        const data: PerformanceData[] = [];

        this.callStats.forEach((stats, key) => {
            const [module, func] = key.split('.');
            data.push({
                module,
                function: func,
                calls: stats.count,
                total: stats.total,
                avg: stats.count > 0 ? stats.total / stats.count : 0,
                min: stats.min === Infinity ? 0 : stats.min,
                max: stats.max
            });
        });

        // Sort by total time descending
        data.sort((a, b) => b.total - a.total);

        return data;
    }

    /**
     * Get recent events
     */
    getRecentEvents(count: number = 100): TraceEvent[] {
        return this.eventBuffer.slice(-count);
    }

    /**
     * Get event count
     */
    getEventCount(): number {
        return this.eventCounter;
    }

    /**
     * Set sampling rate (1 = process all, 10 = process 1 in 10)
     */
    setSampleRate(rate: number): void {
        this.sampleRate = Math.max(1, rate);
    }

    /**
     * Check if connected
     */
    isConnected(): boolean {
        return this.connected;
    }

    /**
     * Reset statistics
     */
    reset(): void {
        this.callStats.clear();
        this.callStack.clear();
        this.eventBuffer = [];
        this.eventCounter = 0;
    }

    /**
     * Disconnect from server
     */
    disconnect(): void {
        if (this.socket) {
            this.socket.destroy();
            this.socket = null;
        }
        this.connected = false;
        this.emit('disconnected');
    }
}
