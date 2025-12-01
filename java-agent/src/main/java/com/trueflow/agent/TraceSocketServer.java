package com.trueflow.agent;

import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;
import java.util.logging.Logger;

/**
 * TCP socket server for streaming trace events to IDE.
 * Uses the same protocol as Python (newline-delimited JSON on port 5679).
 */
public class TraceSocketServer {
    private static final Logger LOGGER = Logger.getLogger(TraceSocketServer.class.getName());

    private final String host;
    private final int port;
    private final RuntimeInstrumentor instrumentor;

    private ServerSocket serverSocket;
    private ExecutorService executor;
    private volatile boolean running = false;
    private final List<ClientHandler> clients = new CopyOnWriteArrayList<>();

    public TraceSocketServer(String host, int port, RuntimeInstrumentor instrumentor) {
        this.host = host;
        this.port = port;
        this.instrumentor = instrumentor;
    }

    /**
     * Start the socket server in a background thread.
     */
    public void start() {
        if (running) return;

        executor = Executors.newCachedThreadPool(r -> {
            Thread t = new Thread(r, "TrueFlow-SocketServer");
            t.setDaemon(true);
            return t;
        });

        running = true;

        executor.submit(() -> {
            try {
                serverSocket = new ServerSocket(port, 50, InetAddress.getByName(host));
                LOGGER.info("[TrueFlow] Socket server listening on " + host + ":" + port);

                // Register event listener to broadcast to all clients
                Consumer<String> broadcaster = this::broadcast;
                instrumentor.addEventListener(broadcaster);

                while (running) {
                    try {
                        Socket clientSocket = serverSocket.accept();
                        LOGGER.info("[TrueFlow] Client connected: " + clientSocket.getRemoteSocketAddress());

                        ClientHandler handler = new ClientHandler(clientSocket);
                        clients.add(handler);
                        executor.submit(handler);

                    } catch (SocketException e) {
                        if (running) {
                            LOGGER.warning("[TrueFlow] Socket accept error: " + e.getMessage());
                        }
                    }
                }

            } catch (IOException e) {
                LOGGER.severe("[TrueFlow] Failed to start socket server: " + e.getMessage());
            }
        });
    }

    /**
     * Stop the socket server.
     */
    public void stop() {
        running = false;

        // Close all client connections
        for (ClientHandler client : clients) {
            client.close();
        }
        clients.clear();

        // Close server socket
        if (serverSocket != null) {
            try {
                serverSocket.close();
            } catch (IOException ignored) {}
        }

        // Shutdown executor
        if (executor != null) {
            executor.shutdownNow();
        }

        LOGGER.info("[TrueFlow] Socket server stopped");
    }

    /**
     * Broadcast a message to all connected clients.
     */
    public void broadcast(String message) {
        for (ClientHandler client : clients) {
            client.send(message);
        }
    }

    /**
     * Get the number of connected clients.
     */
    public int getClientCount() {
        return clients.size();
    }

    /**
     * Handler for individual client connections.
     */
    private class ClientHandler implements Runnable {
        private final Socket socket;
        private PrintWriter writer;
        private BufferedReader reader;
        private volatile boolean connected = true;

        public ClientHandler(Socket socket) {
            this.socket = socket;
            try {
                socket.setTcpNoDelay(true);  // Disable Nagle's algorithm for low latency
                socket.setKeepAlive(true);
                this.writer = new PrintWriter(new BufferedWriter(
                        new OutputStreamWriter(socket.getOutputStream())), false);
                this.reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            } catch (IOException e) {
                LOGGER.warning("[TrueFlow] Failed to initialize client handler: " + e.getMessage());
                connected = false;
            }
        }

        @Override
        public void run() {
            try {
                // Send function registry when client connects
                send(instrumentor.getFunctionRegistryJson());

                // Listen for commands from client
                while (connected && running) {
                    String line = reader.readLine();
                    if (line == null) {
                        // Client disconnected
                        break;
                    }

                    // Handle commands from IDE
                    handleCommand(line);
                }

            } catch (SocketException e) {
                // Client disconnected
            } catch (IOException e) {
                LOGGER.fine("[TrueFlow] Client error: " + e.getMessage());
            } finally {
                close();
            }
        }

        /**
         * Handle commands received from the IDE.
         */
        private void handleCommand(String command) {
            try {
                // Parse JSON command
                if (command.contains("\"type\"")) {
                    if (command.contains("\"pause\"")) {
                        instrumentor.setEnabled(false);
                        LOGGER.info("[TrueFlow] Tracing paused by client");
                    } else if (command.contains("\"resume\"")) {
                        instrumentor.setEnabled(true);
                        LOGGER.info("[TrueFlow] Tracing resumed by client");
                    } else if (command.contains("\"get_registry\"")) {
                        send(instrumentor.getFunctionRegistryJson());
                    } else if (command.contains("\"finalize\"")) {
                        instrumentor.finalize("./.trueflow/traces");
                    }
                }
            } catch (Exception e) {
                LOGGER.fine("[TrueFlow] Error handling command: " + e.getMessage());
            }
        }

        /**
         * Send a message to this client.
         */
        public void send(String message) {
            if (!connected || writer == null) return;

            try {
                synchronized (writer) {
                    writer.println(message);  // Newline-delimited
                    writer.flush();
                }
            } catch (Exception e) {
                LOGGER.fine("[TrueFlow] Failed to send to client: " + e.getMessage());
                close();
            }
        }

        /**
         * Close this client connection.
         */
        public void close() {
            connected = false;
            clients.remove(this);

            try {
                if (writer != null) writer.close();
                if (reader != null) reader.close();
                if (socket != null) socket.close();
            } catch (IOException ignored) {}

            LOGGER.info("[TrueFlow] Client disconnected");
        }
    }
}
