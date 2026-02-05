//! TrueFlow Runtime Library
//!
//! Provides runtime support for TrueFlow instrumentation in Rust applications.
//!
//! # Quick Start
//!
//! ```rust
//! use trueflow_runtime::init;
//! use trueflow_macros::trace;
//!
//! fn main() {
//!     // Initialize TrueFlow (connects to IDE on port 5681)
//!     init();
//!
//!     // Your application code
//!     my_function();
//! }
//!
//! #[trace]
//! fn my_function() {
//!     println!("Hello from traced function!");
//! }
//! ```

mod instrumentor;
mod socket;
mod subscriber;

pub use instrumentor::{enter, CallGuard};
pub use subscriber::TrueFlowLayer;

use once_cell::sync::OnceCell;
use std::sync::atomic::{AtomicBool, Ordering};

static INITIALIZED: AtomicBool = AtomicBool::new(false);
static INSTRUMENTOR: OnceCell<instrumentor::Instrumentor> = OnceCell::new();

/// Initialize TrueFlow with default settings.
///
/// Connects to the IDE on port 5681 (default Rust port).
///
/// # Example
///
/// ```rust
/// fn main() {
///     trueflow_runtime::init();
///     // ... your app
/// }
/// ```
pub fn init() {
    init_with_config(Config::default());
}

/// Initialize TrueFlow with custom configuration.
///
/// # Example
///
/// ```rust
/// use trueflow_runtime::{init_with_config, Config};
///
/// fn main() {
///     init_with_config(Config {
///         port: 5681,
///         enabled: true,
///         buffer_size: 1000,
///     });
/// }
/// ```
pub fn init_with_config(config: Config) {
    if INITIALIZED.swap(true, Ordering::SeqCst) {
        return; // Already initialized
    }

    if !config.enabled {
        eprintln!("[TrueFlow] Disabled by configuration");
        return;
    }

    let instrumentor = instrumentor::Instrumentor::new(config.port, config.buffer_size);

    if let Err(_) = INSTRUMENTOR.set(instrumentor) {
        eprintln!("[TrueFlow] Already initialized");
        return;
    }

    // Start the socket connection
    if let Some(inst) = INSTRUMENTOR.get() {
        inst.start();
    }

    eprintln!("[TrueFlow] Rust agent initialized on port {}", config.port);
}

/// Configuration for TrueFlow runtime.
#[derive(Debug, Clone)]
pub struct Config {
    /// Port to connect to IDE (default: 5681)
    pub port: u16,
    /// Whether tracing is enabled (default: true, or TRUEFLOW_ENABLED env var)
    pub enabled: bool,
    /// Maximum events to buffer when disconnected (default: 1000)
    pub buffer_size: usize,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            port: std::env::var("TRUEFLOW_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(5681),
            enabled: std::env::var("TRUEFLOW_ENABLED")
                .map(|v| v == "1" || v.to_lowercase() == "true")
                .unwrap_or(true),
            buffer_size: 1000,
        }
    }
}

/// Get the global instrumentor instance.
pub(crate) fn get_instrumentor() -> Option<&'static instrumentor::Instrumentor> {
    INSTRUMENTOR.get()
}

/// Setup TrueFlow as a tracing subscriber layer.
///
/// This integrates with the `tracing` ecosystem for automatic instrumentation.
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
/// }
/// ```
pub fn setup_tracing_subscriber(port: u16) {
    use tracing_subscriber::prelude::*;

    let layer = TrueFlowLayer::new(port);

    tracing_subscriber::registry()
        .with(layer)
        .init();
}

// Re-export macros for convenience
pub use trueflow_macros::{trace, trace_impl, trace_module, no_trace};
