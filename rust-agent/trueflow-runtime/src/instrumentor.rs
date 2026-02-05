//! Core instrumentation logic for TrueFlow Rust agent.

use parking_lot::Mutex;
use serde::Serialize;
use std::cell::RefCell;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use crate::socket::SocketClient;

/// Global call counter for unique call IDs
static CALL_COUNTER: AtomicU64 = AtomicU64::new(0);

thread_local! {
    /// Thread-local call stack for tracking parent-child relationships
    static CALL_STACK: RefCell<Vec<CallContext>> = RefCell::new(Vec::new());
}

/// Context for an active function call
#[derive(Debug, Clone)]
struct CallContext {
    call_id: String,
    module: &'static str,
    function: &'static str,
    file: &'static str,
    line: u32,
    start_time: Instant,
}

/// Trace event sent to the IDE
#[derive(Debug, Serialize)]
struct TraceEvent {
    #[serde(rename = "type")]
    event_type: &'static str,
    timestamp: f64,
    call_id: String,
    module: String,
    function: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    line: Option<u32>,
    depth: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    parent_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    duration_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    exception: Option<String>,
    language: &'static str,
    session_id: String,
    process_id: u32,
}

/// Main instrumentor that manages tracing state
pub struct Instrumentor {
    socket: Mutex<SocketClient>,
    session_id: String,
    process_id: u32,
}

impl Instrumentor {
    /// Create a new instrumentor
    pub fn new(port: u16, buffer_size: usize) -> Self {
        let session_id = format!(
            "rust_{}_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis())
                .unwrap_or(0),
            rand_string(7)
        );

        Instrumentor {
            socket: Mutex::new(SocketClient::new(port, buffer_size)),
            session_id,
            process_id: std::process::id(),
        }
    }

    /// Start the socket connection
    pub fn start(&self) {
        let mut socket = self.socket.lock();
        socket.connect();
    }

    /// Emit a call event
    pub fn emit_call(
        &self,
        call_id: &str,
        module: &str,
        function: &str,
        file: &str,
        line: u32,
        depth: usize,
        parent_id: Option<&str>,
    ) {
        let event = TraceEvent {
            event_type: "call",
            timestamp: current_timestamp(),
            call_id: call_id.to_string(),
            module: module.to_string(),
            function: function.to_string(),
            file: Some(file.to_string()),
            line: Some(line),
            depth,
            parent_id: parent_id.map(|s| s.to_string()),
            duration_ms: None,
            exception: None,
            language: "rust",
            session_id: self.session_id.clone(),
            process_id: self.process_id,
        };

        self.emit(event);
    }

    /// Emit a return event
    pub fn emit_return(
        &self,
        call_id: &str,
        module: &str,
        function: &str,
        depth: usize,
        parent_id: Option<&str>,
        duration_ms: f64,
        exception: Option<&str>,
    ) {
        let event = TraceEvent {
            event_type: "return",
            timestamp: current_timestamp(),
            call_id: call_id.to_string(),
            module: module.to_string(),
            function: function.to_string(),
            file: None,
            line: None,
            depth,
            parent_id: parent_id.map(|s| s.to_string()),
            duration_ms: Some(duration_ms),
            exception: exception.map(|s| s.to_string()),
            language: "rust",
            session_id: self.session_id.clone(),
            process_id: self.process_id,
        };

        self.emit(event);
    }

    fn emit(&self, event: TraceEvent) {
        if let Ok(json) = serde_json::to_string(&event) {
            let mut socket = self.socket.lock();
            socket.send(&json);
        }
    }
}

/// RAII guard for function call tracking
///
/// Automatically emits the return event when dropped.
pub struct CallGuard {
    call_id: String,
    module: &'static str,
    function: &'static str,
    start_time: Instant,
}

impl Drop for CallGuard {
    fn drop(&mut self) {
        let duration_ms = self.start_time.elapsed().as_secs_f64() * 1000.0;

        // Pop from call stack
        let (depth, parent_id) = CALL_STACK.with(|stack| {
            let mut stack = stack.borrow_mut();
            stack.pop();
            let depth = stack.len();
            let parent_id = stack.last().map(|ctx| ctx.call_id.clone());
            (depth, parent_id)
        });

        // Check if panicking (exception)
        let exception = if std::thread::panicking() {
            Some("panic")
        } else {
            None
        };

        // Emit return event
        if let Some(inst) = crate::get_instrumentor() {
            inst.emit_return(
                &self.call_id,
                self.module,
                self.function,
                depth,
                parent_id.as_deref(),
                duration_ms,
                exception,
            );
        }
    }
}

/// Enter a function and return a guard that tracks the call.
///
/// This is called by the `#[trace]` macro. You generally don't need
/// to call this directly.
pub fn enter(
    module: &'static str,
    function: &'static str,
    line: u32,
    file: &'static str,
) -> CallGuard {
    let call_id = format!("call_{}", CALL_COUNTER.fetch_add(1, Ordering::SeqCst));

    // Get parent from call stack and push new context
    let (depth, parent_id) = CALL_STACK.with(|stack| {
        let mut stack = stack.borrow_mut();
        let depth = stack.len();
        let parent_id = stack.last().map(|ctx| ctx.call_id.clone());

        stack.push(CallContext {
            call_id: call_id.clone(),
            module,
            function,
            file,
            line,
            start_time: Instant::now(),
        });

        (depth, parent_id)
    });

    // Emit call event
    if let Some(inst) = crate::get_instrumentor() {
        inst.emit_call(
            &call_id,
            module,
            function,
            file,
            line,
            depth,
            parent_id.as_deref(),
        );
    }

    CallGuard {
        call_id,
        module,
        function,
        start_time: Instant::now(),
    }
}

/// Get current timestamp as seconds since epoch
fn current_timestamp() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Generate a random alphanumeric string
fn rand_string(len: usize) -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};

    let hasher = RandomState::new();
    let mut h = hasher.build_hasher();
    h.write_usize(std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as usize)
        .unwrap_or(0));

    let hash = h.finish();
    format!("{:x}", hash)[..len.min(16)].to_string()
}
