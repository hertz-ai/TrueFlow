/**
 * TCP socket server for streaming trace events to IDE.
 * Uses the same protocol as Python/Java (newline-delimited JSON on port 5680).
 */

import * as net from 'net';
import type { Instrumentor } from './instrumentor';

export class TraceSocketServer {
    private host: string;
    private port: number;
    private instrumentor: Instrumentor;
    private server: net.Server | null = null;
    private clients: net.Socket[] = [];
    private running = false;

    constructor(host: string, port: number, instrumentor: Instrumentor) {
        this.host = host;
        this.port = port;
        this.instrumentor = instrumentor;
    }

    /**
     * Start the socket server.
     */
    start(): void {
        if (this.running) return;

        this.server = net.createServer((socket) => {
            this.handleClient(socket);
        });

        this.server.on('error', (err: NodeJS.ErrnoException) => {
            if (err.code === 'EADDRINUSE') {
                console.error(`[TrueFlow] Port ${this.port} is already in use`);
            } else {
                console.error('[TrueFlow] Socket server error:', err.message);
            }
        });

        this.server.listen(this.port, this.host, () => {
            this.running = true;
            console.log(`[TrueFlow] Socket server listening on ${this.host}:${this.port}`);
        });
    }

    /**
     * Handle a new client connection.
     */
    private handleClient(socket: net.Socket): void {
        console.log(`[TrueFlow] Client connected from ${socket.remoteAddress}:${socket.remotePort}`);

        // Configure socket
        socket.setNoDelay(true);
        socket.setKeepAlive(true);

        // Add to clients list
        this.clients.push(socket);

        // Send function registry to new client
        try {
            const registry = this.instrumentor.getFunctionRegistryJson();
            socket.write(registry + '\n');
        } catch (error) {
            console.error('[TrueFlow] Failed to send registry:', error);
        }

        // Handle incoming commands from client
        let buffer = '';
        socket.on('data', (data) => {
            buffer += data.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.trim()) {
                    this.handleCommand(line.trim(), socket);
                }
            }
        });

        // Handle client disconnect
        socket.on('close', () => {
            console.log('[TrueFlow] Client disconnected');
            this.removeClient(socket);
        });

        socket.on('error', (err) => {
            console.log('[TrueFlow] Client error:', err.message);
            this.removeClient(socket);
        });
    }

    /**
     * Handle a command from the client.
     */
    private handleCommand(command: string, socket: net.Socket): void {
        try {
            const parsed = JSON.parse(command);

            switch (parsed.type) {
                case 'pause':
                    console.log('[TrueFlow] Tracing paused by client');
                    // Would need to expose setEnabled on instrumentor
                    break;

                case 'resume':
                    console.log('[TrueFlow] Tracing resumed by client');
                    break;

                case 'get_registry':
                    socket.write(this.instrumentor.getFunctionRegistryJson() + '\n');
                    break;

                case 'finalize':
                    this.instrumentor.finalize();
                    break;

                default:
                    console.log('[TrueFlow] Unknown command:', parsed.type);
            }
        } catch (error) {
            console.log('[TrueFlow] Invalid command:', command);
        }
    }

    /**
     * Remove a client from the list.
     */
    private removeClient(socket: net.Socket): void {
        const index = this.clients.indexOf(socket);
        if (index !== -1) {
            this.clients.splice(index, 1);
        }
    }

    /**
     * Broadcast a message to all connected clients.
     */
    broadcast(message: string): void {
        if (!this.running || this.clients.length === 0) return;

        const data = message + '\n';

        // Send to all clients, removing dead ones
        this.clients = this.clients.filter((socket) => {
            try {
                if (!socket.destroyed) {
                    socket.write(data);
                    return true;
                }
            } catch (error) {
                // Client disconnected
            }
            return false;
        });
    }

    /**
     * Stop the socket server.
     */
    stop(): void {
        this.running = false;

        // Close all client connections
        for (const socket of this.clients) {
            try {
                socket.destroy();
            } catch (e) {
                // Ignore
            }
        }
        this.clients = [];

        // Close server
        if (this.server) {
            this.server.close();
            this.server = null;
        }

        console.log('[TrueFlow] Socket server stopped');
    }

    /**
     * Get number of connected clients.
     */
    getClientCount(): number {
        return this.clients.length;
    }
}
