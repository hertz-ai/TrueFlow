//! Tracing subscriber layer for automatic instrumentation.
//!
//! Integrates with the `tracing` ecosystem to automatically capture
//! span enter/exit events and forward them to the IDE.

use parking_lot::Mutex;
use serde::Serialize;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;
use tracing::span::{Attributes, Id};
use tracing::{Event, Metadata, Subscriber};
use tracing_subscriber::layer::Context;
use tracing_subscriber::registry::LookupSpan;
use tracing_subscriber::Layer;

use crate::socket::SocketClient;

static CALL_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Trace event for the tracing subscriber
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
    language: &'static str,
    session_id: String,
    process_id: u32,
}

/// Span data stored in the registry
struct SpanData {
    call_id: String,
    start_time: Instant,
    module: String,
    function: String,
    file: Option<String>,
    line: Option<u32>,
}

/// TrueFlow layer for the tracing subscriber.
///
/// This layer captures span enter/exit events and sends them to the
/// TrueFlow IDE plugin.
///
/// # Example
///
/// ```rust
/// use tracing_subscriber::prelude::*;
/// use trueflow_runtime::TrueFlowLayer;
///
/// fn main() {
///     tracing_subscriber::registry()
///         .with(TrueFlowLayer::new(5681))
///         .init();
///
///     // Now all #[tracing::instrument] spans will be captured
///     my_traced_function();
/// }
///
/// #[tracing::instrument]
/// fn my_traced_function() {
///     tracing::info!("doing work");
/// }
/// ```
pub struct TrueFlowLayer {
    socket: Mutex<SocketClient>,
    spans: Mutex<HashMap<u64, SpanData>>,
    session_id: String,
    process_id: u32,
}

impl TrueFlowLayer {
    /// Create a new TrueFlow layer.
    pub fn new(port: u16) -> Self {
        let session_id = format!(
            "rust_{}_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis())
                .unwrap_or(0),
            rand_string(7)
        );

        let mut socket = SocketClient::new(port, 1000);
        socket.connect();

        TrueFlowLayer {
            socket: Mutex::new(socket),
            spans: Mutex::new(HashMap::new()),
            session_id,
            process_id: std::process::id(),
        }
    }

    fn emit(&self, event: TraceEvent) {
        if let Ok(json) = serde_json::to_string(&event) {
            let mut socket = self.socket.lock();
            socket.send(&json);
        }
    }

    fn get_depth<S>(&self, ctx: &Context<'_, S>) -> usize
    where
        S: Subscriber + for<'a> LookupSpan<'a>,
    {
        ctx.current_span()
            .id()
            .and_then(|id| ctx.span(id))
            .map(|span| {
                let mut depth = 0;
                let mut current = span.parent();
                while let Some(parent) = current {
                    depth += 1;
                    current = parent.parent();
                }
                depth
            })
            .unwrap_or(0)
    }
}

impl<S> Layer<S> for TrueFlowLayer
where
    S: Subscriber + for<'a> LookupSpan<'a>,
{
    fn on_new_span(&self, attrs: &Attributes<'_>, id: &Id, _ctx: Context<'_, S>) {
        let meta = attrs.metadata();
        let call_id = format!("call_{}", CALL_COUNTER.fetch_add(1, Ordering::SeqCst));

        let span_data = SpanData {
            call_id,
            start_time: Instant::now(),
            module: meta.module_path().unwrap_or("unknown").to_string(),
            function: meta.name().to_string(),
            file: meta.file().map(|s| s.to_string()),
            line: meta.line(),
        };

        let mut spans = self.spans.lock();
        spans.insert(id.into_u64(), span_data);
    }

    fn on_enter(&self, id: &Id, ctx: Context<'_, S>) {
        let spans = self.spans.lock();
        if let Some(span_data) = spans.get(&id.into_u64()) {
            let depth = self.get_depth(&ctx);

            // Get parent call ID
            let parent_id = ctx
                .current_span()
                .id()
                .and_then(|parent_id| {
                    if parent_id != id {
                        spans.get(&parent_id.into_u64()).map(|p| p.call_id.clone())
                    } else {
                        None
                    }
                });

            let event = TraceEvent {
                event_type: "call",
                timestamp: current_timestamp(),
                call_id: span_data.call_id.clone(),
                module: span_data.module.clone(),
                function: span_data.function.clone(),
                file: span_data.file.clone(),
                line: span_data.line,
                depth,
                parent_id,
                duration_ms: None,
                language: "rust",
                session_id: self.session_id.clone(),
                process_id: self.process_id,
            };

            drop(spans); // Release lock before emit
            self.emit(event);
        }
    }

    fn on_exit(&self, id: &Id, ctx: Context<'_, S>) {
        let spans = self.spans.lock();
        if let Some(span_data) = spans.get(&id.into_u64()) {
            let duration_ms = span_data.start_time.elapsed().as_secs_f64() * 1000.0;
            let depth = self.get_depth(&ctx);

            let parent_id = ctx
                .current_span()
                .id()
                .and_then(|parent_id| {
                    if parent_id != id {
                        spans.get(&parent_id.into_u64()).map(|p| p.call_id.clone())
                    } else {
                        None
                    }
                });

            let event = TraceEvent {
                event_type: "return",
                timestamp: current_timestamp(),
                call_id: span_data.call_id.clone(),
                module: span_data.module.clone(),
                function: span_data.function.clone(),
                file: None,
                line: None,
                depth,
                parent_id,
                duration_ms: Some(duration_ms),
                language: "rust",
                session_id: self.session_id.clone(),
                process_id: self.process_id,
            };

            drop(spans); // Release lock before emit
            self.emit(event);
        }
    }

    fn on_close(&self, id: Id, _ctx: Context<'_, S>) {
        let mut spans = self.spans.lock();
        spans.remove(&id.into_u64());
    }

    fn on_event(&self, _event: &Event<'_>, _ctx: Context<'_, S>) {
        // Could capture log events here if needed
    }
}

fn current_timestamp() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn rand_string(len: usize) -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};

    let hasher = RandomState::new();
    let mut h = hasher.build_hasher();
    h.write_usize(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos() as usize)
            .unwrap_or(0),
    );

    let hash = h.finish();
    format!("{:x}", hash)[..len.min(16)].to_string()
}
