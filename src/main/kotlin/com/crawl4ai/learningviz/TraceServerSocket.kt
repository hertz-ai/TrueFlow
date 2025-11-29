package com.crawl4ai.learningviz

import com.google.gson.Gson
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.concurrent.thread

/**
 * Trace server that RUNS IN PYCHARM and accepts connections from Python processes.
 * This is the REVERSE of TraceSocketClient - PyCharm is the server, Python is the client.
 *
 * Usage:
 * 1. PyCharm starts this server on port 5678
 * 2. Python process connects to localhost:5678
 * 3. Python sends JSON trace events
 * 4. PyCharm receives and displays them
 */
class TraceServerSocket(
    private val port: Int = 5678,
    private val onTraceReceived: (TraceEvent) -> Unit,
    private val onClientConnected: (clientId: String) -> Unit = {},
    private val onClientDisconnected: (clientId: String) -> Unit = {},
    private val onError: (Exception) -> Unit = {}
) {
    private var serverSocket: ServerSocket? = null
    private var running = false
    private val clients = CopyOnWriteArrayList<ClientHandler>()
    private val gson = Gson()

    fun start() {
        if (running) {
            throw IllegalStateException("Server already running")
        }

        try {
            serverSocket = ServerSocket(port)
            serverSocket?.soTimeout = 10000 // 10 second timeout for accept()
            running = true

            println("[TraceServer] Started on port $port")

            // Accept client connections in background thread
            thread(name = "TraceServerAcceptor") {
                acceptClients()
            }

        } catch (e: Exception) {
            onError(e)
            throw e
        }
    }

    private fun acceptClients() {
        while (running) {
            try {
                val clientSocket = serverSocket?.accept()
                if (clientSocket != null) {
                    val handler = ClientHandler(clientSocket)
                    clients.add(handler)
                    handler.start()
                }
            } catch (e: SocketTimeoutException) {
                // Normal timeout, continue loop
            } catch (e: Exception) {
                if (running) {
                    onError(e)
                }
            }
        }
    }

    fun stop() {
        running = false
        clients.forEach { it.stop() }
        clients.clear()
        serverSocket?.close()
        serverSocket = null
        println("[TraceServer] Stopped")
    }

    fun isRunning() = running

    fun getClientCount() = clients.size

    private inner class ClientHandler(private val socket: Socket) {
        private val clientId = "${socket.inetAddress.hostAddress}:${socket.port}"
        private var running = false

        fun start() {
            running = true
            onClientConnected(clientId)

            thread(name = "TraceServerClient-$clientId") {
                try {
                    val reader = BufferedReader(InputStreamReader(socket.getInputStream()))

                    while (running) {
                        val line = reader.readLine() ?: break

                        if (line.isNotBlank()) {
                            try {
                                // Parse JSON trace event
                                val event = gson.fromJson(line, TraceEvent::class.java)
                                onTraceReceived(event)
                            } catch (e: Exception) {
                                println("[TraceServer] Failed to parse trace event: ${e.message}")
                            }
                        }
                    }
                } catch (e: Exception) {
                    if (running) {
                        println("[TraceServer] Client $clientId error: ${e.message}")
                    }
                } finally {
                    stop()
                }
            }
        }

        fun stop() {
            running = false
            clients.remove(this)
            socket.close()
            onClientDisconnected(clientId)
        }
    }
}
