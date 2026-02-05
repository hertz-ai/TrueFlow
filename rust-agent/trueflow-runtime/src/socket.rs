//! Socket client for communicating with TrueFlow IDE plugin.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

/// TCP socket client for sending trace events to the IDE
pub struct SocketClient {
    port: u16,
    buffer_size: usize,
    stream: Option<TcpStream>,
    buffer: VecDeque<String>,
    connected: Arc<AtomicBool>,
    reconnect_attempts: u32,
    max_reconnect_attempts: u32,
}

impl SocketClient {
    /// Create a new socket client
    pub fn new(port: u16, buffer_size: usize) -> Self {
        SocketClient {
            port,
            buffer_size,
            stream: None,
            buffer: VecDeque::new(),
            connected: Arc::new(AtomicBool::new(false)),
            reconnect_attempts: 0,
            max_reconnect_attempts: 5,
        }
    }

    /// Connect to the IDE server
    pub fn connect(&mut self) {
        if self.connected.load(Ordering::SeqCst) {
            return;
        }

        let addr = format!("127.0.0.1:{}", self.port);
        eprintln!("[TrueFlow] Connecting to {}...", addr);

        match TcpStream::connect_timeout(
            &addr.parse().unwrap(),
            Duration::from_secs(5),
        ) {
            Ok(stream) => {
                stream.set_nodelay(true).ok();
                stream.set_write_timeout(Some(Duration::from_millis(100))).ok();
                stream.set_read_timeout(Some(Duration::from_millis(100))).ok();

                self.stream = Some(stream);
                self.connected.store(true, Ordering::SeqCst);
                self.reconnect_attempts = 0;
                eprintln!("[TrueFlow] Connected to IDE");

                // Flush any buffered events
                self.flush_buffer();

                // Start reader thread for IDE commands
                self.start_reader();
            }
            Err(e) => {
                eprintln!("[TrueFlow] Connection failed: {}", e);
                self.schedule_reconnect();
            }
        }
    }

    /// Send a JSON event to the IDE
    pub fn send(&mut self, json: &str) {
        if self.connected.load(Ordering::SeqCst) {
            if let Some(ref mut stream) = self.stream {
                let message = format!("{}\n", json);
                if let Err(e) = stream.write_all(message.as_bytes()) {
                    eprintln!("[TrueFlow] Send failed: {}", e);
                    self.connected.store(false, Ordering::SeqCst);
                    self.buffer_event(json.to_string());
                    self.schedule_reconnect();
                }
            }
        } else {
            self.buffer_event(json.to_string());
        }
    }

    /// Buffer an event for later sending
    fn buffer_event(&mut self, event: String) {
        self.buffer.push_back(event);
        while self.buffer.len() > self.buffer_size {
            self.buffer.pop_front();
        }
    }

    /// Flush buffered events
    fn flush_buffer(&mut self) {
        if !self.connected.load(Ordering::SeqCst) {
            return;
        }

        while let Some(event) = self.buffer.pop_front() {
            if let Some(ref mut stream) = self.stream {
                let message = format!("{}\n", event);
                if let Err(_) = stream.write_all(message.as_bytes()) {
                    // Put it back and stop flushing
                    self.buffer.push_front(event);
                    break;
                }
            }
        }
    }

    /// Schedule a reconnection attempt
    fn schedule_reconnect(&mut self) {
        if self.reconnect_attempts >= self.max_reconnect_attempts {
            eprintln!("[TrueFlow] Max reconnection attempts reached");
            return;
        }

        self.reconnect_attempts += 1;
        let delay = Duration::from_millis(1000 * self.reconnect_attempts as u64);
        let port = self.port;
        let connected = Arc::clone(&self.connected);

        eprintln!(
            "[TrueFlow] Reconnecting in {:?} (attempt {})",
            delay, self.reconnect_attempts
        );

        thread::spawn(move || {
            thread::sleep(delay);

            if connected.load(Ordering::SeqCst) {
                return; // Already reconnected
            }

            let addr = format!("127.0.0.1:{}", port);
            if TcpStream::connect_timeout(&addr.parse().unwrap(), Duration::from_secs(5)).is_ok() {
                // Signal that reconnection should be attempted
                // The actual reconnection will happen on the next send
            }
        });
    }

    /// Start a reader thread for IDE commands
    fn start_reader(&mut self) {
        if let Some(ref stream) = self.stream {
            let stream = match stream.try_clone() {
                Ok(s) => s,
                Err(_) => return,
            };
            let connected = Arc::clone(&self.connected);

            thread::spawn(move || {
                let reader = BufReader::new(stream);
                for line in reader.lines() {
                    match line {
                        Ok(msg) => {
                            // Handle IDE commands
                            if let Ok(cmd) = serde_json::from_str::<serde_json::Value>(&msg) {
                                match cmd.get("type").and_then(|t| t.as_str()) {
                                    Some("pause") => {
                                        eprintln!("[TrueFlow] Tracing paused");
                                    }
                                    Some("resume") => {
                                        eprintln!("[TrueFlow] Tracing resumed");
                                    }
                                    _ => {}
                                }
                            }
                        }
                        Err(_) => {
                            connected.store(false, Ordering::SeqCst);
                            break;
                        }
                    }
                }
            });
        }
    }

    /// Disconnect from the IDE
    pub fn disconnect(&mut self) {
        self.connected.store(false, Ordering::SeqCst);
        self.stream = None;
    }

    /// Check if connected
    pub fn is_connected(&self) -> bool {
        self.connected.load(Ordering::SeqCst)
    }
}

impl Drop for SocketClient {
    fn drop(&mut self) {
        self.disconnect();
    }
}
