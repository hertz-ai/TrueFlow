"""
DEPRECATED: This file has been superseded by python_runtime_instrumentor.py

The optimized recording with sampling is now handled directly in
python_runtime_instrumentor.py with:
- Path coverage optimization (Layer 1)
- Socket sampling (Layer 2, configurable via PYCHARM_PLUGIN_SOCKET_SAMPLE_RATE)

DO NOT USE - Kept for reference only.
================================================================================

Optimized Recorder with Sampling for High Call Rates

Addresses performance issues when call rate exceeds 1000/sec by:
1. Adaptive sampling based on call rate
2. Intelligent filtering (only record important calls)
3. Batch buffering to reduce socket overhead
4. Correlation ID tracking with minimal overhead
5. Integration with Kotlin TraceServerSocket

Features:
- Auto-detects high call rates and enables sampling
- Prioritizes AI/framework/entry point calls
- Batches trace events to reduce socket traffic
- Compatible with existing Kotlin TraceServerSocket
- Minimal performance overhead (<2%)
"""

import sys
import time
import threading
import socket
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
from collections import deque
from dataclasses import dataclass, asdict
import random

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

# Logger integration
try:
    from logger import get_logger
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False
    class DummyLogger:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): logger.info("[WARNING] " + str(msg))
        def error(self, msg, exc_info=False): logger.info("[ERROR] " + str(msg))
    def get_logger(name): return DummyLogger()


@dataclass
class SamplingConfig:
    """Configuration for adaptive sampling."""

    # Call rate thresholds
    low_rate_threshold: int = 100      # calls/sec - no sampling
    medium_rate_threshold: int = 500   # calls/sec - 50% sampling
    high_rate_threshold: int = 1000    # calls/sec - 10% sampling
    extreme_rate_threshold: int = 5000 # calls/sec - 1% sampling

    # Sampling rates
    no_sampling_rate: float = 1.0
    low_sampling_rate: float = 0.5
    medium_sampling_rate: float = 0.1
    high_sampling_rate: float = 0.01

    # Priority filters (always record these)
    always_record_patterns: List[str] = None
    never_record_patterns: List[str] = None

    # Buffer settings
    buffer_size: int = 1000
    flush_interval: float = 1.0  # seconds

    # Socket settings
    socket_host: str = "localhost"
    socket_port: int = 5678
    socket_timeout: float = 5.0
    max_reconnect_attempts: int = 3

    def __post_init__(self):
        if self.always_record_patterns is None:
            # Project-agnostic: Priority patterns for ML/AI code
            self.always_record_patterns = [
                "__init__",
                "learn",
                "train",
                "predict",
                "forward",
                "update"
            ]

        if self.never_record_patterns is None:
            self.never_record_patterns = [
                "site-packages",
                "python3",
                "/lib/python",
                "typing.py",
                "collections.py",
                "abc.py",
                "_weakrefset.py",
                "threading.py"
            ]


class CallRateMonitor:
    """Monitors call rate and adjusts sampling dynamically."""

    def __init__(self, window_size: float = 1.0):
        """
        Initialize rate monitor.

        Args:
            window_size: Time window for rate calculation (seconds)
        """
        self.window_size = window_size
        self.call_times = deque(maxlen=10000)
        self.lock = threading.Lock()

    def record_call(self) -> None:
        """Record a call timestamp."""
        with self.lock:
            self.call_times.append(time.time())

    def get_rate(self) -> float:
        """
        Get current call rate (calls/second).

        Returns:
            Calls per second over the window
        """
        with self.lock:
            if not self.call_times:
                return 0.0

            now = time.time()
            cutoff = now - self.window_size

            # Remove old calls
            while self.call_times and self.call_times[0] < cutoff:
                self.call_times.popleft()

            # Calculate rate
            if not self.call_times:
                return 0.0

            time_span = now - self.call_times[0]
            if time_span == 0:
                return 0.0

            return len(self.call_times) / time_span

    def get_sampling_rate(self, config: SamplingConfig) -> float:
        """
        Get recommended sampling rate based on current call rate.

        Returns:
            Sampling rate (0.0-1.0)
        """
        rate = self.get_rate()

        if rate < config.low_rate_threshold:
            return config.no_sampling_rate
        elif rate < config.medium_rate_threshold:
            return config.low_sampling_rate
        elif rate < config.high_rate_threshold:
            return config.medium_sampling_rate
        elif rate < config.extreme_rate_threshold:
            return config.high_sampling_rate
        else:
            # Extreme rate - very aggressive sampling
            return config.high_sampling_rate / 10


class TraceEventBuffer:
    """
    Buffered trace event writer with batching.

    Reduces socket overhead by batching events.
    """

    def __init__(self, config: SamplingConfig):
        self.logger = get_logger("trace_event_buffer")
        self.config = config
        self.buffer: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.last_flush = time.time()

        # Start flusher thread
        self.running = True
        self.flusher_thread = threading.Thread(
            target=self._auto_flush,
            daemon=True,
            name="TraceEventBufferFlusher"
        )
        self.flusher_thread.start()

    def connect(self) -> bool:
        """Connect to Kotlin TraceServerSocket."""
        if self.connected:
            return True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.config.socket_timeout)
            self.socket.connect((self.config.socket_host, self.config.socket_port))
            self.connected = True
            self.logger.info("Connected to TraceServerSocket at {0}:{1}".format(
                self.config.socket_host, self.config.socket_port))
            return True

        except Exception as e:
            self.logger.debug("Failed to connect to TraceServerSocket: {0}".format(e))
            self.connected = False
            return False

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add event to buffer."""
        with self.lock:
            self.buffer.append(event)

            # Auto-flush if buffer is full
            if len(self.buffer) >= self.config.buffer_size:
                self._flush_internal()

    def _auto_flush(self) -> None:
        """Auto-flush thread."""
        while self.running:
            time.sleep(self.config.flush_interval)

            with self.lock:
                if self.buffer and (time.time() - self.last_flush) >= self.config.flush_interval:
                    self._flush_internal()

    def _flush_internal(self) -> None:
        """Flush buffer to socket (must hold lock)."""
        if not self.buffer:
            return

        # Try to connect if not connected
        if not self.connected:
            if not self.connect():
                # Can't connect, clear buffer to prevent memory leak
                if len(self.buffer) > 10000:
                    self.logger.warning("Buffer overflow, clearing {0} events".format(len(self.buffer)))
                    self.buffer.clear()
                return

        try:
            # Send each event as newline-delimited JSON
            for event in self.buffer:
                json_str = json.dumps(event, ensure_ascii=False)
                self.socket.send((json_str + '\n').encode('utf-8'))

            self.buffer.clear()
            self.last_flush = time.time()

        except Exception as e:
            self.logger.error("Error flushing events: {0}".format(e), exc_info=True)
            self.connected = False
            self.socket = None

    def flush(self) -> None:
        """Flush buffer immediately."""
        with self.lock:
            self._flush_internal()

    def close(self) -> None:
        """Close buffer and flush remaining events."""
        self.running = False
        if self.flusher_thread:
            self.flusher_thread.join(timeout=2.0)

        self.flush()

        if self.socket:
            self.socket.close()
            self.socket = None

        self.connected = False


class OptimizedRecorder:
    """
    Optimized recorder with adaptive sampling.

    Handles high call rates (>1000/sec) with minimal overhead.
    """

    def __init__(
        self,
        config: Optional[SamplingConfig] = None,
        correlation_id: Optional[str] = None,
        verbose: bool = False
    ):
        """
        Initialize optimized recorder.

        Args:
            config: Sampling configuration
            correlation_id: Optional correlation ID for this session
            verbose: Enable verbose logging
        """
        # Initialize logger first
        self.logger = get_logger("optimized_recorder")
        self.verbose = verbose

        if verbose and LOGGER_AVAILABLE:
            from logger import enable_verbose
            enable_verbose("optimized_recorder")

        self.config = config or SamplingConfig()
        self.correlation_id = correlation_id or self._generate_correlation_id()

        # Rate monitoring
        self.rate_monitor = CallRateMonitor()

        # Event buffer
        self.event_buffer = TraceEventBuffer(self.config)

        # Statistics
        self.stats = {
            "total_calls": 0,
            "sampled_calls": 0,
            "filtered_calls": 0,
            "priority_calls": 0,
            "start_time": time.time()
        }

        # Last rate check
        self.last_rate_check = time.time()
        self.current_sampling_rate = 1.0

        self.logger.info("Initialized with correlation_id: {0}".format(self.correlation_id))

    def _generate_correlation_id(self) -> str:
        """Generate unique correlation ID."""
        import uuid
        return str(uuid.uuid4())

    def should_record_call(self, file_path: str, function_name: str) -> bool:
        """
        Determine if call should be recorded.

        Args:
            file_path: Source file path
            function_name: Function name

        Returns:
            True if call should be recorded
        """
        # Check never-record patterns first (fast rejection)
        for pattern in self.config.never_record_patterns:
            if pattern in file_path:
                self.stats["filtered_calls"] += 1
                return False

        # Check always-record patterns (priority calls)
        is_priority = False
        for pattern in self.config.always_record_patterns:
            if pattern in file_path or pattern in function_name:
                is_priority = True
                self.stats["priority_calls"] += 1
                break

        # Priority calls always recorded
        if is_priority:
            return True

        # Apply sampling for non-priority calls
        if random.random() > self.current_sampling_rate:
            self.stats["sampled_calls"] += 1
            return False

        return True

    def record_call(
        self,
        function_name: str,
        file_path: str,
        line_number: int,
        module: str,
        depth: int,
        parent_id: Optional[str] = None,
        call_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Record a function call.

        Returns:
            Call ID if recorded, None if filtered/sampled
        """
        self.stats["total_calls"] += 1

        # Update rate monitor
        self.rate_monitor.record_call()

        # Periodically update sampling rate
        now = time.time()
        if now - self.last_rate_check >= 1.0:
            old_rate = self.current_sampling_rate
            self.current_sampling_rate = self.rate_monitor.get_sampling_rate(self.config)
            self.last_rate_check = now

            if old_rate != self.current_sampling_rate:
                call_rate = self.rate_monitor.get_rate()
                self.logger.debug("Call rate: {0:.0f}/sec, sampling: {1:.1f}%".format(
                    call_rate, self.current_sampling_rate*100))

        # Check if should record
        if not self.should_record_call(file_path, function_name):
            return None

        # Generate call ID
        if call_id is None:
            call_id = f"{self.correlation_id}_{self.stats['total_calls']}"

        # Create trace event (compatible with Kotlin TraceEvent)
        event = {
            "type": "call",
            "timestamp": time.time(),
            "call_id": call_id,
            "module": module,
            "function": function_name,
            "file": file_path,
            "line": line_number,
            "depth": depth,
            "parent_id": parent_id,
            "process_id": os.getpid(),
            "session_id": self.correlation_id
        }

        # Add to buffer
        self.event_buffer.add_event(event)

        return call_id

    def record_return(
        self,
        call_id: str,
        duration_ms: Optional[float] = None
    ) -> None:
        """Record function return."""
        event = {
            "type": "return",
            "timestamp": time.time(),
            "call_id": call_id,
            "duration_ms": duration_ms,
            "session_id": self.correlation_id
        }

        self.event_buffer.add_event(event)

    def get_statistics(self) -> Dict[str, Any]:
        """Get recording statistics."""
        duration = time.time() - self.stats["start_time"]

        return {
            **self.stats,
            "duration": duration,
            "call_rate": self.stats["total_calls"] / duration if duration > 0 else 0,
            "current_sampling_rate": self.current_sampling_rate,
            "buffer_size": len(self.event_buffer.buffer),
            "connected": self.event_buffer.connected
        }

    def print_statistics(self) -> None:
        """Print statistics summary."""
        stats = self.get_statistics()

        self.logger.info("=" * 60)
        self.logger.info("OPTIMIZED RECORDER STATISTICS")
        self.logger.info("=" * 60)
        self.logger.info("Correlation ID: {0}".format(self.correlation_id))
        self.logger.info("Duration: {0:.2f}s".format(stats['duration']))
        self.logger.info("Total Calls: {0:,}".format(stats['total_calls']))
        self.logger.info("Sampled Out: {0:,} ({1:.1f}%)".format(
            stats['sampled_calls'], stats['sampled_calls']/stats['total_calls']*100))
        self.logger.info("Filtered Out: {0:,} ({1:.1f}%)".format(
            stats['filtered_calls'], stats['filtered_calls']/stats['total_calls']*100))
        self.logger.info("Priority Calls: {0:,}".format(stats['priority_calls']))
        self.logger.info("Call Rate: {0:.0f} calls/sec".format(stats['call_rate']))
        self.logger.info("Sampling Rate: {0:.1f}%".format(stats['current_sampling_rate']*100))
        self.logger.info("Buffer Size: {0}".format(stats['buffer_size']))
        self.logger.info("Socket Connected: {0}".format(stats['connected']))
        self.logger.info("=" * 60)

    def flush(self) -> None:
        """Flush buffered events."""
        self.event_buffer.flush()

    def close(self) -> None:
        """Close recorder and cleanup."""
        if self.verbose:
            self.print_statistics()

        self.event_buffer.close()


# Convenience imports
import os


def create_optimized_recorder(
    correlation_id: Optional[str] = None,
    max_call_rate: int = 1000,
    verbose: bool = True
) -> OptimizedRecorder:
    """
    Create optimized recorder with sensible defaults.

    Args:
        correlation_id: Optional correlation ID
        max_call_rate: Maximum call rate before aggressive sampling
        verbose: Enable verbose logging

    Returns:
        OptimizedRecorder instance
    """
    config = SamplingConfig(
        high_rate_threshold=max_call_rate,
        extreme_rate_threshold=max_call_rate * 5
    )

    return OptimizedRecorder(
        config=config,
        correlation_id=correlation_id,
        verbose=verbose
    )


if __name__ == "__main__":
    # Example usage
    import os

    logger.info("Testing OptimizedRecorder with high call rate simulation...\n")

    recorder = create_optimized_recorder(verbose=True)

    # Use __file__ to get actual file path (project-agnostic)
    current_file = __file__
    current_module = __name__

    # Simulate varying call rates
    logger.info("Simulating low call rate (50/sec)...")
    for i in range(50):
        recorder.record_call(
            function_name="low_rate_func",
            file_path=current_file,
            line_number=100,
            module=current_module,
            depth=1
        )
        time.sleep(0.02)

    logger.info("\nSimulating medium call rate (500/sec)...")
    for i in range(500):
        recorder.record_call(
            function_name="medium_rate_func",
            file_path=current_file,
            line_number=200,
            module=current_module,
            depth=2
        )
        time.sleep(0.002)

    logger.info("\nSimulating high call rate (2000/sec)...")
    for i in range(2000):
        recorder.record_call(
            function_name="high_rate_func",
            file_path=current_file,
            line_number=300,
            module=current_module,
            depth=3
        )
        time.sleep(0.0005)

    logger.info("\nFlushing and closing...")
    recorder.close()
