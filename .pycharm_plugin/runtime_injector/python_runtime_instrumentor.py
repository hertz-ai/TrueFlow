"""
Runtime Python Instrumentor - Injected by PyCharm Plugin

This file is INJECTED at runtime by the PyCharm plugin (like JRebel for Java).
It does NOT require any SDK installation or code changes.

Compatible with Python 2.7+ and Python 3.x

The plugin injects this via PYTHONPATH with sitecustomize.py.
Works for ALL Python executions (scripts, apps, batch files, etc.)
"""

from __future__ import print_function  # Python 2 compatibility
import sys
import os
import time
import inspect
import threading
import json
import socket
from datetime import datetime

# Python 2/3 compatibility
if sys.version_info[0] >= 3:
    from pathlib import Path
else:
    # Python 2 fallback
    class Path(object):
        def __init__(self, path):
            self.path = str(path)

        def mkdir(self, parents=False, exist_ok=False):
            if not os.path.exists(self.path):
                if parents:
                    os.makedirs(self.path)
                else:
                    os.mkdir(self.path)

        def write_text(self, content, encoding='utf-8'):
            with open(self.path, 'w') as f:
                f.write(content)

        def __truediv__(self, other):
            return Path(os.path.join(self.path, str(other)))

        def __str__(self):
            return self.path

# Logger integration - gracefully fallback if not available
try:
    sys.path.insert(0, str(Path(__file__).parent.parent) if sys.version_info[0] >= 3 else os.path.join(os.path.dirname(__file__), '..'))
    from logger import get_logger
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False
    # Fallback: create dummy logger for Python 2 compatibility
    class DummyLogger:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): print("[WARNING] " + str(msg))
        def error(self, msg, exc_info=False): print("[ERROR] " + str(msg))
    def get_logger(name): return DummyLogger()


# ============================================================================
# RUNTIME INJECTION MARKER
# ============================================================================
_INJECTED_BY_PYCHARM_PLUGIN = True
_INJECTION_TIME = datetime.now()


# ============================================================================
# SOCKET TRACE SERVER (Real-time streaming to PyCharm plugin)
# ============================================================================

class TraceSocketServer(object):
    """
    Socket server that streams traces to connected PyCharm plugin clients.
    Similar to debugpy/pydevd remote debugging protocol.
    """

    def __init__(self, host='127.0.0.1', port=5678):
        self.logger = get_logger("trace_server")
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = []  # List of connected client sockets
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        """Start trace server in background thread."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True

            # Accept connections in background thread
            accept_thread = threading.Thread(target=self._accept_connections)
            accept_thread.daemon = True
            accept_thread.start()

            self.logger.info("Trace socket server started on {0}:{1}".format(self.host, self.port))
            self.logger.info("Connect from PyCharm: Tools -> Attach to Trace Server")
            return True

        except Exception as e:
            self.logger.error("Failed to start trace server: {0}".format(str(e)), exc_info=True)
            return False

    def _accept_connections(self):
        """Accept client connections in background."""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                with self.lock:
                    self.clients.append(client_socket)
                self.logger.info("Client connected from {0}".format(addr))

                # Notify parent instrumentor about new client
                if hasattr(self, 'on_client_connected'):
                    self.on_client_connected()
            except:
                if self.running:
                    self.logger.warning("Error accepting connection")
                break

    def stream_trace(self, trace_data):
        """Stream trace event to all connected clients."""
        if not self.clients:
            return

        try:
            # Serialize to JSON with newline delimiter (MUST NOT contain embedded newlines!)
            message = json.dumps(trace_data, separators=(',', ':')) + '\n'  # Compact JSON, no spaces
            message_bytes = message.encode('utf-8')

            # Debug: Log first few events to verify JSON format
            if not hasattr(self, '_debug_event_count'):
                self._debug_event_count = 0
            if self._debug_event_count < 5:
                # Check for embedded newlines
                if '\n' in message[:-1]:  # Exclude the trailing newline we added
                    self.logger.error("CRITICAL: JSON contains embedded newlines! This will break readLine() parsing!")
                self.logger.debug("Streaming trace event #{0} ({1} bytes): {2}".format(
                    self._debug_event_count, len(message_bytes), message.strip()[:200]))
                self._debug_event_count += 1

            # Send to all clients
            with self.lock:
                disconnected = []
                for client in self.clients:
                    try:
                        client.sendall(message_bytes)
                    except:
                        disconnected.append(client)

                # Remove disconnected clients
                for client in disconnected:
                    self.clients.remove(client)
                    try:
                        client.close()
                    except:
                        pass

        except Exception as e:
            self.logger.error("Error streaming trace: {0}".format(str(e)), exc_info=True)

    def stop(self):
        """Stop server and close all connections."""
        self.running = False

        with self.lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients = []

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        self.logger.info("Trace socket server stopped")


# ============================================================================
# DATA STRUCTURES (Python 2/3 compatible - no dataclasses)
# ============================================================================

class FunctionCall(object):
    """Record of a single function call."""

    def __init__(self, call_id, function_name, module, file_path, line_number,
                 start_time, framework=None, invocation_type="sync", is_ai_agent=False,
                 parent_id=None, depth=0):
        self.call_id = call_id
        self.function_name = function_name
        self.module = module
        self.file_path = file_path
        self.line_number = line_number
        self.start_time = start_time
        self.end_time = None
        self.duration_ms = None
        self.exception = None
        self.framework = framework
        self.invocation_type = invocation_type
        self.is_ai_agent = is_ai_agent
        self.parent_id = parent_id  # For flamegraph hierarchy
        self.depth = depth  # Call stack depth
        self.sql_queries = []  # SQL queries executed
        self.http_requests = []  # HTTP requests made
        self.websocket_events = []  # WebSocket send/receive
        self.webrtc_events = []  # WebRTC peer connections, data channels
        self.mcp_calls = []  # Model Context Protocol interactions
        self.agent_communications = []  # A2A (agent-to-agent) messages
        self.process_spawns = []  # Cross-process communication
        self.distributed_trace_id = None  # For cross-process tracing

        # Additional protocols
        self.grpc_calls = []  # gRPC RPC calls
        self.graphql_queries = []  # GraphQL queries/mutations
        self.mqtt_messages = []  # MQTT pub/sub
        self.amqp_messages = []  # RabbitMQ/AMQP messages
        self.kafka_events = []  # Kafka produce/consume
        self.redis_commands = []  # Redis commands
        self.memcached_ops = []  # Memcached operations
        self.elasticsearch_queries = []  # Elasticsearch queries
        self.sse_events = []  # Server-Sent Events
        self.http2_frames = []  # HTTP/2 frames
        self.thrift_calls = []  # Apache Thrift calls
        self.zeromq_messages = []  # ZeroMQ messages
        self.nats_messages = []  # NATS messages


# ============================================================================
# RUNTIME INSTRUMENTOR (Auto-injected by plugin)
# ============================================================================

class RuntimeInstrumentor(object):
    """
    Runtime instrumentor injected by PyCharm plugin.

    NO SDK REQUIRED - Pure runtime injection like JRebel.
    Compatible with Python 2.7+ and Python 3.x
    """

    def __init__(self, output_dir=None):
        # Initialize logger FIRST
        self.logger = get_logger("runtime_instrumentor")

        try:
            self.output_dir = Path(output_dir or os.getenv('CRAWL4AI_TRACE_DIR', './traces'))
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # Fallback to temp directory if output_dir creation fails
            try:
                import tempfile
                self.output_dir = Path(tempfile.mkdtemp(prefix='pycharm_plugin_'))
                self.logger.warning("Using temp directory due to error: {0}".format(str(e)))
            except Exception:
                # Last resort - use current directory
                self.output_dir = Path('./traces_fallback')
                try:
                    self.output_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass

        self.session_id = "session_{0}".format(datetime.now().strftime('%Y%m%d_%H%M%S'))
        self.calls = []
        self.call_counter = 0
        self.enabled = True
        self.call_stack = []  # Track call hierarchy for flamegraph
        self.active_calls = {}  # Track in-flight calls by frame id

        # Safety limits to prevent memory exhaustion
        self.max_calls = int(os.getenv('PYCHARM_PLUGIN_MAX_CALLS', '10000'))  # Max calls to track (reduced for performance)
        self.call_rate_window = []  # Track recent call timestamps for rate limiting
        self.max_calls_per_second = int(os.getenv('PYCHARM_PLUGIN_MAX_CALLS_PER_SEC', '10000'))  # Auto-disable if exceeding this rate
        self.max_call_depth = int(os.getenv('PYCHARM_PLUGIN_MAX_DEPTH', '1000'))  # Max call stack depth
        self.auto_finalize_threshold = int(os.getenv('PYCHARM_PLUGIN_AUTO_FINALIZE', '50000'))  # Auto-finalize at N calls

        # Periodic flush for long-running processes
        self.flush_interval = int(os.getenv('PYCHARM_PLUGIN_FLUSH_INTERVAL', '10'))  # Flush every N seconds
        self.last_flush_time = time.time()
        self.flush_lock = False  # Simple flag to prevent concurrent flushes

        # Detection patterns
        self.sql_patterns = [  # SQL detection patterns
            'SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ',
            'CREATE ', 'DROP ', 'ALTER ', 'TRUNCATE '
        ]

        # Database library patterns - detect execute() calls and connection objects
        self.db_library_patterns = [
            '.execute(', '.executemany(', '.query(',  # DB-API 2.0 methods
            'sqlite3.', 'psycopg2.', 'pymysql.', 'mysql.connector',  # Database drivers
            'SQLAlchemy', 'session.query', 'Session.query',  # SQLAlchemy
            'django.db', 'cursor.execute', 'connection.cursor'  # Django, cursors
        ]

        self.websocket_patterns = [  # WebSocket detection
            'ws://', 'wss://', 'websocket', 'socket.io'
        ]

        self.webrtc_patterns = [  # WebRTC detection
            'RTCPeerConnection', 'RTCDataChannel', 'getUserMedia',
            'createOffer', 'createAnswer', 'addIceCandidate'
        ]

        self.mcp_patterns = [  # Model Context Protocol detection
            'mcp://', 'model_context_protocol', 'mcp_server', 'mcp_client'
        ]

        self.agent_patterns = [  # Agent-to-Agent detection
            'autogen', 'crewai', 'langgraph', 'agentops',
            'send_message', 'receive_message', 'agent_chat'
        ]

        self.process_patterns = [  # Cross-process detection
            'multiprocessing', 'subprocess', 'Process', 'Pool',
            'spawn', 'fork', 'Pipe', 'Queue'
        ]

        # Additional protocol patterns
        self.grpc_patterns = [  # gRPC detection
            'grpc', 'grpc.aio', 'grpc_channel', 'stub', 'servicer'
        ]

        self.graphql_patterns = [  # GraphQL detection
            'graphql', 'graphene', 'strawberry', 'ariadne', 'query', 'mutation'
        ]

        self.mqtt_patterns = [  # MQTT detection
            'mqtt', 'paho', 'publish', 'subscribe', 'broker'
        ]

        self.amqp_patterns = [  # AMQP/RabbitMQ detection
            'amqp', 'rabbitmq', 'pika', 'kombu', 'celery.app'
        ]

        self.kafka_patterns = [  # Kafka detection
            'kafka', 'confluent_kafka', 'producer', 'consumer', 'topic'
        ]

        self.redis_patterns = [  # Redis detection
            'redis', 'aioredis', 'SET ', 'GET ', 'HSET', 'LPUSH', 'PUBLISH'
        ]

        self.memcached_patterns = [  # Memcached detection
            'memcached', 'pymemcache', 'pylibmc'
        ]

        self.elasticsearch_patterns = [  # Elasticsearch detection
            'elasticsearch', 'es.search', 'es.index', 'query_dsl'
        ]

        self.sse_patterns = [  # Server-Sent Events detection
            'text/event-stream', 'EventSource', 'sse'
        ]

        self.http2_patterns = [  # HTTP/2 detection
            'http2', 'h2', 'hpack', 'SETTINGS', 'HEADERS'
        ]

        self.thrift_patterns = [  # Apache Thrift detection
            'thrift', 'TBinaryProtocol', 'TSocket'
        ]

        self.zeromq_patterns = [  # ZeroMQ detection
            'zmq', 'zeromq', 'PUB', 'SUB', 'PUSH', 'PULL'
        ]

        self.nats_patterns = [  # NATS messaging detection
            'nats', 'nats.aio', 'nc.publish', 'nc.subscribe'
        ]

        # Learning cycle tracking (for correlation ID injection)
        self.learning_cycles = {}  # Tracks active learning cycles by correlation ID
        self.current_correlation_id = None
        self.correlation_counter = 0
        self.cycle_execution_trees = {}  # One execution tree per correlation ID
        self.streamed_cycles = set()  # Track which cycles have been streamed to avoid duplicates
        self.cycle_call_stack_depth = {}  # Track call stack depth per correlation ID (for auto-end detection)

        # Learning cycle entry points (where reality/sensor data enters the system)
        # ACTUAL function names from embodied_ai codebase
        self.cycle_entry_patterns = [
            # Sensor input sources (reality enters here)
            '_capture_loop',  # Webcam/screen capture loop
            'encode_video_frame',  # Video frame encoding
            'encode_image',  # Image encoding (Qwen-VL)
            'encode_text',  # Text encoding
            'encode_multimodal',  # Multimodal encoding (unified stream)
            'encode_numpy',  # Audio encoding from numpy
            'process_video_frame_pair',  # Video frame processing
            # API entry points (external requests)
            'chat',  # OpenAI chat API (qwen_inference_only.py)
            'create_chat_completion',  # FastAPI endpoint (learning_llm_provider.py)
            '_encode_message',  # Message encoding entry point
            # Explicit learning entry
            '_learn_from_experience',
            'learn_from_feedback',
        ]

        # Learning cycle exit points (where learning completes - error processed, params updated)
        # ACTUAL function names from embodied_ai codebase
        self.cycle_exit_patterns = [
            # Parameter updates
            'step',  # Agent step / optimizer step (realtime_agent.py, integrated_realtime_agent.py)
            '_learning_step',  # Internal learning step (realtime_agent.py:822, integrated_realtime_agent.py:285)
            'train_step',  # Training step (truth_grounded_learning.py)
            'update',  # Generic update (attention_gated_updater.py)
            'forward_mode_update',  # Forward mode learning (hybrid_forward_mode.py)
            '_update_lora_params',  # LoRA parameter update (attention_gated_updater.py)
            'record_lora_update',  # Record LoRA update (hybrid_weight_strategy.py)
            # Neuron growth / architecture adaptation
            'grow',  # Self-organizing capacity growth (self_organizing_capacity.py:408)
            'check_and_expand',  # Zero-cost expansion check (zero_cost_expansion.py:115)
            '_expand_network',  # Network expansion (zero_cost_expansion.py:220)
            'expand_capacity',  # Capacity expansion (unified_lora_manager.py:260)
            'expand_slots',  # Slot expansion (orthogonal_lora.py:390, temporal_coherence.py)
            '_expand_embeddings',  # Embedding expansion (meta_learning_router.py:961)
            # Memory operations (experience stored = learning complete)
            'buffer',  # Experience buffering (EpisodicMemory)
            'store',  # Experience storage
            '_maybe_update_compressions',  # Temporal compression (hierarchical_temporal_compression.py:250)
            '_update_recent_summary',  # Recent tier update
            '_update_hourly_summary',  # Hourly tier update
            '_update_daily_summary',  # Daily tier update
            # Reasoning / consolidation
            'reasoning_step',  # Recursive memory reasoning (recursive_memory_reasoning.py:165)
            'meta_train_step',  # Meta-learning step (meta_learning_router.py:589)
        ]

        # Phase detection patterns
        self.phase_patterns = {
            'forward': ['forward', 'predict', '__call__'],
            'loss': ['loss', 'error', 'compute_loss', 'criterion'],
            'backward': ['backward', 'grad'],
            'update': ['step', 'update', 'optimizer']
        }

        # Cross-process tracing
        self.distributed_trace_id = os.getenv('DISTRIBUTED_TRACE_ID', self.session_id)
        self.process_id = os.getpid()
        self.parent_process_id = os.getppid()
        self.start_time = time.time()

        # Socket trace server for real-time streaming to PyCharm plugin
        # Python acts as SERVER, PyCharm is CLIENT
        self.trace_server = None
        self.trace_connected = False

        # Start socket server if socket tracing is enabled
        if os.getenv('PYCHARM_PLUGIN_SOCKET_TRACE', '0') == '1':
            port = int(os.getenv('PYCHARM_PLUGIN_TRACE_PORT', '5678'))
            host = os.getenv('PYCHARM_PLUGIN_TRACE_HOST', '127.0.0.1')

            try:
                self.trace_server = TraceSocketServer(host=host, port=port)
                # Register callback for when client connects
                self.trace_server.on_client_connected = self._on_client_connected
                if self.trace_server.start():
                    self.trace_connected = True
                    self.logger.info("Trace socket server started on {0}:{1}".format(host, port))
                else:
                    self.logger.warning("Failed to start trace socket server")
                    self.trace_server = None
            except Exception as e:
                self.logger.warning("Could not start trace socket server: {0}".format(str(e)))
                import traceback
                self.logger.debug(traceback.format_exc())
                self.trace_server = None
        else:
            self.logger.info("Socket tracing disabled (set PYCHARM_PLUGIN_SOCKET_TRACE=1 to enable)")

        # Project scanner - intelligently filter to only project functions
        # Run in background thread to avoid blocking startup
        self.project_scanner = None
        self.scanned_paths = set()  # Track which paths we've already scanned
        self.scanner_ready = False

        # Path coverage tracking - skip rendering for already-covered execution paths
        # Key: (file_path, line_number) tuple
        # Only emit trace events when code execution branches to a new line
        self.covered_paths = set()
        self.enable_path_coverage = os.getenv('PYCHARM_PLUGIN_PATH_COVERAGE', 'true').lower() == 'true'

        # Socket streaming sampling - prevent overwhelming the client
        # Even after path coverage, we may have thousands of events per second
        # Sample N out of M events for socket streaming (e.g., 1 in 10)
        self.socket_sample_rate = int(os.getenv('PYCHARM_PLUGIN_SOCKET_SAMPLE_RATE', '10'))  # Stream 1 in N
        self.socket_event_counter = 0

        def scan_in_background():
            try:
                from project_scanner import ProjectScanner
                scanner = ProjectScanner(os.getcwd())
                self.logger.info("Scanning project for functions (background)...")
                scanner.scan()
                stats = scanner.get_stats()
                self.logger.info("Project scan complete: {0} files, {1} functions".format(
                    stats['files'], stats['functions']))
                self.project_scanner = scanner
                self.scanner_ready = True

                # Send function registry to plugin for dead code detection
                # Note: This will only send if a client is already connected
                # If no client yet, it will be sent when client connects
                self._send_function_registry(scanner)
            except Exception as e:
                self.logger.warning("Project scan failed: {0}".format(str(e)))
                self.logger.info("Falling back to pattern-based filtering")
                self.scanner_ready = True  # Mark as ready anyway

        # Start scanner in background thread
        scan_thread = threading.Thread(target=scan_in_background, daemon=True)
        scan_thread.start()

        self.logger.info("RuntimeInstrumentor initialized (session: {0}, pid: {1})".format(
            self.session_id, self.process_id))
        self.logger.warning("Tracing adds overhead. For performance-critical code, disable tracing or use sampling.")

    def _on_client_connected(self):
        """Called when a new client connects to trace server."""
        # Send function registry if scanner is ready
        if self.scanner_ready and self.project_scanner:
            self.logger.info("Client connected, sending function registry...")
            self._send_function_registry(self.project_scanner)

    def _send_function_registry(self, scanner):
        """Send function registry to plugin for dead code detection."""
        if not self.trace_server or not self.trace_server.clients:
            self.logger.debug("No clients connected, function registry not sent")
            return

        try:
            # Build function registry event
            all_functions = []
            for filepath, functions in scanner.functions.items():
                for func_name in functions:
                    # Extract module name from filepath
                    module = self._filepath_to_module(filepath)
                    all_functions.append({
                        'module': module,
                        'function': func_name,
                        'file': filepath,
                        'line': 0  # Line number not available from AST scan
                    })

            # Send registry event
            # Note: traceData expects trace_data field in JSON
            registry_event = {
                'type': 'function_registry',
                'timestamp': time.time(),
                'call_id': 'registry_event',
                'module': '__registry__',
                'function': '__registry__',
                'file': '',
                'line': 0,
                'depth': 0,
                'parent_id': None,
                'session_id': self.session_id,
                'process_id': self.process_id,
                'correlation_id': None,
                'learning_phase': None,
                'trace_data': {
                    'total_functions': len(all_functions),
                    'functions': all_functions
                }
            }

            self.trace_server.stream_trace(registry_event)
            self.logger.info("Sent function registry: {0} functions".format(len(all_functions)))

        except Exception as e:
            self.logger.warning("Failed to send function registry: {0}".format(str(e)))

    def _filepath_to_module(self, filepath):
        """Convert file path to module name.

        Converts absolute path to relative module path to match Python's __name__.
        e.g., C:/project/src/crawl4ai/foo.py -> src.crawl4ai.foo
        """
        # Get absolute path and normalize
        abs_path = os.path.abspath(filepath)

        # Get project root (cwd) to make path relative
        project_root = os.getcwd()

        # Make path relative to project root
        try:
            if abs_path.startswith(project_root):
                rel_path = os.path.relpath(abs_path, project_root)
            else:
                rel_path = abs_path
        except ValueError:
            # Different drive on Windows
            rel_path = abs_path

        # Remove .py extension
        module_path = rel_path.replace('.py', '')
        # Convert path separators to dots
        module_path = module_path.replace(os.sep, '.')
        module_path = module_path.replace('/', '.')
        # Remove leading dots
        module_path = module_path.lstrip('.')
        return module_path

    def pause_tracing(self):
        """Temporarily pause tracing (useful for performance-critical sections)."""
        self.enabled = False
        sys.settrace(None)
        self.logger.info("Tracing paused")

    def resume_tracing(self):
        """Resume tracing after pause."""
        self.enabled = True
        sys.settrace(self.trace_function)
        self.logger.info("Tracing resumed")

    def trace_function(self, frame, event, arg):
        """sys.settrace callback - intercepts all function calls and returns."""
        try:
            if not self.enabled:
                return

            code = frame.f_code
            func_name = code.co_name
            module = frame.f_globals.get('__name__', '') or ''  # Handle None case

            # Skip Python-generated internal functions (comprehensions, lambdas, etc.)
            # These clutter the visualization without providing useful information
            if func_name in ('<genexpr>', '<lambda>', '<listcomp>', '<setcomp>', '<dictcomp>'):
                return

            # Skip internal Python modules (but allow __main__ for testing and database libraries)
            # Allow database libraries even if in site-packages
            db_modules = ['sqlite3', 'psycopg2', 'pymysql', 'mysql', 'sqlalchemy', 'django.db']
            is_db_module = any(module.startswith(db_mod) for db_mod in db_modules)

            # Filter out Python bootstrap and standard library noise
            bootstrap_modules = [
                'importlib', 'enum', 'signal', 'types', 'encodings', 'zipimport',
                'site', 'abc', 'functools', 'collections', 'reprlib', 'weakref',
                'operator', 'keyword', 're', 'sre_', 'copyreg', 'locale', 'codecs',
                'io', 'posixpath', 'ntpath', 'genericpath', 'stat', 'os.path',
                'nt', 'posix', '_collections_abc', '_weakrefset', '_bootlocale',
                'json.encoder', 'json.decoder', 'json.scanner', 'decimal', 'heapq',
                'bisect', 'threading', 'traceback', 'linecache', 'tokenize', 'token',
                'warnings', 'string', 'copy', 'pickle', 'struct', 'socket', 'select',
                'selectors', 'ssl', 'hashlib', 'random', 'datetime', 'calendar'
            ]
            is_bootstrap = any(module.startswith(bs_mod) for bs_mod in bootstrap_modules)

            # Intelligent filtering using project scanner
            filename = code.co_filename

            # Use project scanner if available (much more accurate)
            # If scanner not ready yet, allow all project code (fail open)
            if self.scanner_ready and self.project_scanner:
                # Skip tracing the instrumentor itself to reduce noise
                if 'python_runtime_instrumentor' in filename or 'sitecustomize' in filename:
                    return

                # Skip performance-critical library internals (PyTorch, transformers, etc.)
                # These add massive overhead and aren't useful for debugging user code
                performance_sensitive_modules = [
                    'torch', 'transformers', 'numpy', 'pandas',
                    'cv2', 'PIL', 'sklearn', 'scipy'
                ]
                if any(module.startswith(mod) for mod in performance_sensitive_modules):
                    # Allow top-level user calls INTO these libraries, but not their internals
                    if not self.project_scanner.is_project_file(filename):
                        return

                # Skip PyTorch/model hooks (called thousands of times, huge overhead)
                if func_name.endswith('_hook') or func_name.startswith('hook_'):
                    return

                # Check if this function is in the project
                should_trace = self.project_scanner.should_trace(filename, func_name)

                # For socket streaming: If file is in project but function not found statically,
                # still trace it (covers decorators, properties, lambdas, dynamic methods)
                if not should_trace and self.trace_server and self.trace_server.clients:
                    if self.project_scanner.is_project_file(filename):
                        should_trace = True  # File is in project, trace all its functions

                if not should_trace:
                    return  # Not in project, skip it

                # Track unique scanned paths for statistics
                abs_path = os.path.abspath(filename)
                if abs_path not in self.scanned_paths:
                    self.scanned_paths.add(abs_path)

            else:
                # Fallback to pattern-based filtering (used before scanner is ready)
                cwd = os.getcwd()
                is_user_code = filename.startswith(cwd) or module == '__main__'

                # Skip standard library modules (asyncio, collections, etc.)
                stdlib_indicators = [
                    '/lib/python',  # Unix: /usr/lib/python3.10/
                    '\\lib\\',      # Windows: C:\Python310\lib\
                    '/asyncio/',
                    '\\asyncio\\',
                ]
                if any(indicator in filename for indicator in stdlib_indicators):
                    if not is_user_code:  # Unless it's in project directory
                        return

                # Filter logic: Skip bootstrap/stdlib, skip site-packages (except DB libs and user's project)
                if not is_db_module and not is_user_code:
                    if is_bootstrap or (module.startswith('_') and module != '__main__') or 'site-packages' in filename:
                        return

            frame_id = id(frame)

            if event == 'call':
                current_time = time.time()

                # Rate limiting: Auto-disable if call rate too high (prevents infinite loops/ML overhead)
                self.call_rate_window.append(current_time)
                # Keep only last second of timestamps
                self.call_rate_window = [t for t in self.call_rate_window if current_time - t < 1.0]

                if len(self.call_rate_window) > self.max_calls_per_second:
                    if self.enabled:
                        self.logger.warning("Call rate exceeds {0}/sec, disabling tracing to prevent performance degradation".format(self.max_calls_per_second))
                        self.enabled = False
                        sys.settrace(None)
                    return

                # Periodic flush check for long-running processes
                if current_time - self.last_flush_time >= self.flush_interval and not self.flush_lock:
                    self.flush_lock = True
                    try:
                        self.finalize()
                        self.last_flush_time = current_time
                        self.logger.debug("Periodic flush completed ({0} calls tracked)".format(len(self.calls)))
                    except Exception as e:
                        self.logger.error("Periodic flush failed: {0}".format(str(e)), exc_info=True)
                    finally:
                        self.flush_lock = False

                # Safety check: prevent memory exhaustion
                # Only enforce total limit if socket streaming is NOT active
                # Socket streaming needs continuous operation, uses periodic flush instead
                if len(self.calls) >= self.max_calls:
                    if self.trace_server and self.trace_server.clients:
                        # Socket streaming active - just flush and clear instead of disabling
                        self.logger.debug("Max calls limit ({0}) reached with socket client, flushing and clearing".format(self.max_calls))
                        try:
                            self.finalize()
                            self.calls = []  # Clear to prevent memory exhaustion
                            self.logger.info("Cleared {0} calls to continue socket streaming".format(self.max_calls))
                        except Exception as e:
                            self.logger.error("Emergency flush failed: {0}".format(str(e)), exc_info=True)
                    else:
                        # No socket client - disable as before
                        if self.enabled:
                            self.logger.warning("Max calls limit ({0}) reached, disabling instrumentation".format(self.max_calls))
                            self.enabled = False
                        return

                # Safety check: prevent stack overflow tracking
                if len(self.call_stack) >= self.max_call_depth:
                    # Silently skip deep calls but continue tracking
                    return

                # Path coverage optimization: skip already-covered execution paths
                # Only emit trace events when code execution branches to a new line
                # This reduces file-based traces and provides baseline filtering for socket streaming
                # IMPORTANT: Socket streaming needs ALL events, not just unique paths
                # So we skip path coverage check when socket client is connected
                if self.enable_path_coverage and not (self.trace_server and self.trace_server.clients):
                    path_key = (filename, code.co_firstlineno)
                    if path_key in self.covered_paths:
                        # This exact code path was already executed
                        # Skip recording to avoid redundant visualization
                        return  # Skip for file-based traces only
                    else:
                        # Mark this path as covered (only on first occurrence)
                        self.covered_paths.add(path_key)

                # Record call
                call_id = "call_{0}".format(self.call_counter)
                self.call_counter += 1

                # Detect learning cycle start
                cycle_id = self._detect_learning_cycle_start(func_name, frame)

                # Detect phase within current cycle
                phase = self._detect_phase(func_name)

                # Update cycle call count and depth tracking
                if self.current_correlation_id:
                    cycle = self.learning_cycles[self.current_correlation_id]
                    cycle['call_count'] += 1
                    if phase and phase in cycle['phases']:
                        cycle['phases'][phase]['call_count'] += 1

                    # Increment call stack depth for this correlation ID
                    if self.current_correlation_id in self.cycle_call_stack_depth:
                        self.cycle_call_stack_depth[self.current_correlation_id] += 1

                # Determine parent for flamegraph hierarchy
                parent_id = self.call_stack[-1] if self.call_stack else None
                depth = len(self.call_stack)

                call_record = FunctionCall(
                    call_id=call_id,
                    function_name=func_name,
                    module=module,
                    file_path=code.co_filename,
                    line_number=code.co_firstlineno,
                    start_time=time.time(),
                    framework=self._detect_framework(module),
                    invocation_type=self._detect_invocation_type(func_name),
                    is_ai_agent=self._is_ai_agent(func_name, module),
                    parent_id=parent_id,
                    depth=depth
                )

                self.calls.append(call_record)
                self.call_stack.append(call_id)
                self.active_calls[frame_id] = call_record

                # Add to cycle execution tree if we're in a learning cycle
                if self.current_correlation_id and self.current_correlation_id in self.cycle_execution_trees:
                    # Extract parameters with type and shape info
                    parameters = self._extract_function_parameters(frame, code)

                    call_dict = {
                        'call_id': call_id,
                        'function_name': func_name,
                        'module': module,
                        'file_path': code.co_filename,
                        'line_number': code.co_firstlineno,
                        'start_time': call_record.start_time,
                        'end_time': None,  # Will be filled on return
                        'duration_ms': None,
                        'parent_id': parent_id,
                        'depth': depth,
                        'correlation_id': self.current_correlation_id,
                        'learning_phase': phase if phase else None,
                        'thread_id': str(threading.current_thread().ident),
                        'framework': call_record.framework,
                        'invocation_type': call_record.invocation_type,
                        'parameters': parameters  # Exact params with type/shape
                    }
                    self.cycle_execution_trees[self.current_correlation_id].append(call_dict)

                # Stream to PyCharm if connected
                # IMPORTANT: Don't sample - send ALL events to maintain call/return coherence
                # The plugin needs matching pairs for proper visualization
                # Socket will handle backpressure via TCP flow control
                if self.trace_server and self.trace_server.clients:
                    trace_event = {
                        'type': 'call',
                        'timestamp': call_record.start_time,
                        'call_id': call_id,
                        'module': module,
                        'function': func_name,
                        'file': code.co_filename,
                        'line': code.co_firstlineno,
                        'depth': depth,
                        'parent_id': parent_id,
                        'process_id': self.process_id,
                        'session_id': self.session_id,
                        'correlation_id': self.current_correlation_id,
                        'learning_phase': phase if phase else None
                    }
                    # Stream all call events to maintain coherence
                    self.trace_server.stream_trace(trace_event)

                # Auto-finalize if threshold reached (prevent memory growth)
                if len(self.calls) >= self.auto_finalize_threshold and len(self.calls) % 1000 == 0:
                    try:
                        self.logger.debug("Auto-finalizing at {0} calls to prevent memory growth".format(len(self.calls)))
                        # Don't call full finalize, just clear old data
                        self._cleanup_old_calls()
                    except Exception:
                        pass

                # Detect various patterns in local variables
                try:
                    self._detect_patterns_in_frame(frame, call_record)
                except Exception:
                    # Pattern detection failed, continue without it
                    pass

            elif event == 'return':
                # Mark call as complete
                if frame_id in self.active_calls:
                    call_record = self.active_calls[frame_id]
                    call_record.end_time = time.time()
                    call_record.duration_ms = (call_record.end_time - call_record.start_time) * 1000

                    # Update end_time in cycle execution tree
                    if self.current_correlation_id and self.current_correlation_id in self.cycle_execution_trees:
                        tree = self.cycle_execution_trees[self.current_correlation_id]
                        for call_dict in reversed(tree):  # Search from end (most recent)
                            if call_dict['call_id'] == call_record.call_id:
                                call_dict['end_time'] = call_record.end_time
                                call_dict['duration_ms'] = call_record.duration_ms
                                break

                    # Decrement call stack depth for correlation ID
                    if self.current_correlation_id and self.current_correlation_id in self.cycle_call_stack_depth:
                        self.cycle_call_stack_depth[self.current_correlation_id] -= 1

                        # Auto-end cycle when depth reaches 0 (all calls with this correlation_id completed)
                        if self.cycle_call_stack_depth[self.current_correlation_id] <= 0:
                            self._auto_end_cycle_by_depth(self.current_correlation_id)

                    # Also check traditional exit points
                    code = frame.f_code
                    func_name = code.co_name
                    self._detect_learning_cycle_end(func_name)

                    # Detect patterns again on return (all variables are now available)
                    try:
                        self._detect_patterns_in_frame(frame, call_record)
                    except Exception:
                        # Pattern detection failed, continue without it
                        pass

                    # Stream return event to PyCharm if connected
                    # Send ALL return events to match with call events
                    if self.trace_server and self.trace_server.clients:
                        trace_event = {
                            'type': 'return',
                            'timestamp': call_record.end_time,
                            'call_id': call_record.call_id,
                            'duration_ms': call_record.duration_ms,
                            # Copy context from call_record so return events have full information
                            'module': call_record.module,
                            'function': call_record.function_name,
                            'file': call_record.file_path,
                            'line': call_record.line_number,
                            'depth': call_record.depth,
                            'parent_id': call_record.parent_id,
                            'process_id': self.process_id,
                            'session_id': self.session_id,
                            'correlation_id': self.current_correlation_id
                        }
                        self.trace_server.stream_trace(trace_event)

                    try:
                        del self.active_calls[frame_id]
                    except KeyError:
                        pass

                    # Pop from stack
                    try:
                        if self.call_stack and self.call_stack[-1] == call_record.call_id:
                            self.call_stack.pop()
                    except (IndexError, KeyError):
                        pass

            elif event == 'exception':
                # Record exception
                if frame_id in self.active_calls:
                    call_record = self.active_calls[frame_id]
                    if arg:
                        try:
                            exc_type, exc_value, exc_tb = arg
                            call_record.exception = "{0}: {1}".format(exc_type.__name__, str(exc_value))
                        except Exception:
                            call_record.exception = "Exception (details unavailable)"

            return self.trace_function

        except Exception as e:
            # CRITICAL: Never crash the traced application
            # Silently disable tracing if something goes wrong
            try:
                self.logger.error("Instrumentation error, disabling: {0}".format(str(e)), exc_info=True)
                self.enabled = False
            except Exception:
                pass
            return None

    def _detect_learning_cycle_start(self, func_name, frame):
        """
        Detect if this function call starts a new learning cycle.
        Returns correlation_id if cycle started, None otherwise.
        """
        # Check if this is a cycle entry point
        is_entry_point = any(pattern in func_name for pattern in self.cycle_entry_patterns)

        if is_entry_point:
            # Create new correlation ID
            self.correlation_counter += 1
            correlation_id = "cycle_{0:06d}_{1}".format(
                self.correlation_counter,
                hex(id(frame))[2:10]  # Use frame ID for uniqueness
            )

            # Initialize cycle tracking
            self.learning_cycles[correlation_id] = {
                'start_time': time.time(),
                'end_time': None,
                'entry_point': func_name,
                'current_phase': None,
                'phases': {},
                'call_count': 0
            }

            # Initialize execution tree for this correlation ID
            self.cycle_execution_trees[correlation_id] = []

            # Initialize call stack depth tracking (starts at 0, incremented on each call)
            self.cycle_call_stack_depth[correlation_id] = 0

            self.current_correlation_id = correlation_id

            # Optionally reset covered paths for each new cycle
            # This ensures each learning cycle gets full visibility
            # Set PYCHARM_PLUGIN_RESET_COVERAGE_PER_CYCLE=false to accumulate coverage across cycles
            if os.getenv('PYCHARM_PLUGIN_RESET_COVERAGE_PER_CYCLE', 'true').lower() == 'true':
                self.covered_paths.clear()

            self.logger.info("Learning cycle started: {0} (entry: {1})".format(
                correlation_id, func_name
            ))

            # Send cycle_start event to PyCharm
            if self.trace_server:
                event = {
                    'type': 'cycle_start',
                    'correlation_id': correlation_id,
                    'entry_point': func_name,
                    'timestamp': time.time()
                }
                self.trace_server.stream_trace(event)

            return correlation_id

        return None

    def _detect_learning_cycle_end(self, func_name):
        """
        Detect if this function return ends the current learning cycle.
        Cycle ends when either:
        1. An explicit exit point is reached (parameter update, error processed)
        2. The entry point function returns (fallback)
        """
        if not self.current_correlation_id:
            return

        cycle = self.learning_cycles.get(self.current_correlation_id)
        if not cycle:
            return

        # Check if this is an explicit exit point (learning completed)
        is_exit_point = any(pattern in func_name for pattern in self.cycle_exit_patterns)

        # Cycle ends when either exit point reached OR entry point returns
        if is_exit_point or func_name == cycle['entry_point']:
            cycle['end_time'] = time.time()
            duration = cycle['end_time'] - cycle['start_time']

            # Log why cycle ended
            end_reason = "exit_point({})".format(func_name) if is_exit_point else "entry_return({})".format(func_name)

            # Export execution tree for this correlation ID
            self.logger.info("BEFORE _export_cycle_execution_tree for {0} [reason: {1}]".format(
                self.current_correlation_id, end_reason))
            self._export_cycle_execution_tree(self.current_correlation_id)
            self.logger.info("AFTER _export_cycle_execution_tree for {0}".format(self.current_correlation_id))

            self.logger.info("Learning cycle completed: {0} (duration: {1:.3f}s, calls: {2}, end: {3})".format(
                self.current_correlation_id, duration, cycle['call_count'], end_reason
            ))

            # Send cycle_end event to PyCharm
            if self.trace_server:
                event = {
                    'type': 'cycle_end',
                    'correlation_id': self.current_correlation_id,
                    'duration': duration,
                    'call_count': cycle['call_count'],
                    'timestamp': time.time()
                }
                self.trace_server.stream_trace(event)

            # Clear current cycle
            self.current_correlation_id = None

    def _auto_end_cycle_by_depth(self, correlation_id):
        """
        Auto-end cycle when call stack depth reaches 0.
        This means all calls with this correlation_id have completed (last return received).
        """
        if correlation_id not in self.learning_cycles:
            return

        cycle = self.learning_cycles[correlation_id]
        cycle['end_time'] = time.time()
        duration = cycle['end_time'] - cycle['start_time']

        # Log that cycle ended by depth tracking
        self.logger.info("BEFORE _export_cycle_execution_tree for {0} [reason: depth_zero (all calls completed)]".format(
            correlation_id))
        self._export_cycle_execution_tree(correlation_id)
        self.logger.info("AFTER _export_cycle_execution_tree for {0}".format(correlation_id))

        self.logger.info("Learning cycle completed: {0} (duration: {1:.3f}s, calls: {2}, end: depth_zero)".format(
            correlation_id, duration, cycle['call_count']
        ))

        # Send cycle_end event to PyCharm
        if self.trace_server:
            event = {
                'type': 'cycle_end',
                'correlation_id': correlation_id,
                'duration': duration,
                'call_count': cycle['call_count'],
                'timestamp': time.time()
            }
            self.trace_server.stream_trace(event)

        # Clean up depth tracking
        if correlation_id in self.cycle_call_stack_depth:
            del self.cycle_call_stack_depth[correlation_id]

        # Clear current cycle only if this is the current one
        if self.current_correlation_id == correlation_id:
            self.current_correlation_id = None

    def _detect_phase(self, func_name):
        """Detect current learning phase from function name."""
        if not self.current_correlation_id:
            return None

        func_lower = func_name.lower()

        for phase_name, patterns in self.phase_patterns.items():
            if any(pattern in func_lower for pattern in patterns):
                cycle = self.learning_cycles[self.current_correlation_id]

                # Only set phase if it changed
                if cycle['current_phase'] != phase_name:
                    # End previous phase
                    if cycle['current_phase']:
                        prev_phase = cycle['current_phase']
                        if prev_phase in cycle['phases']:
                            cycle['phases'][prev_phase]['end_time'] = time.time()

                    # Start new phase
                    cycle['current_phase'] = phase_name
                    cycle['phases'][phase_name] = {
                        'start_time': time.time(),
                        'end_time': None,
                        'call_count': 0
                    }

                    self.logger.debug("Phase: {0}".format(phase_name.upper()))

                return phase_name

        return None

    def _extract_function_parameters(self, frame, code):
        """
        Extract function parameters with type and shape information.
        Returns dict of {param_name: {value, type, shape, dtype}}
        """
        parameters = {}

        try:
            # Get argument names
            arg_count = code.co_argcount
            arg_names = code.co_varnames[:arg_count]

            # Extract parameter values from frame locals
            for arg_name in arg_names:
                if arg_name in frame.f_locals:
                    param_value = frame.f_locals[arg_name]
                    param_info = self._get_param_info(param_value)
                    parameters[arg_name] = param_info

        except Exception as e:
            # If parameter extraction fails, continue without it
            parameters['_extraction_error'] = str(e)

        return parameters

    def _get_param_info(self, value):
        """Get type, shape, and dtype info for a parameter value."""
        info = {
            'type': type(value).__name__,
            'value_repr': None,
            'shape': None,
            'dtype': None,
            'device': None
        }

        try:
            # Check if it's a torch.Tensor
            if hasattr(value, 'shape') and hasattr(value, 'dtype'):
                # Likely a tensor (PyTorch, NumPy, etc.)
                info['shape'] = list(value.shape) if hasattr(value.shape, '__iter__') else str(value.shape)
                info['dtype'] = str(value.dtype)

                # Check for device (PyTorch specific)
                if hasattr(value, 'device'):
                    info['device'] = str(value.device)

                # Don't include full tensor value (too large)
                info['value_repr'] = f"Tensor{tuple(info['shape'])}"

            # Check if it's a numpy array
            elif hasattr(value, '__array__'):
                import numpy as np
                if isinstance(value, np.ndarray):
                    info['shape'] = list(value.shape)
                    info['dtype'] = str(value.dtype)
                    info['value_repr'] = f"ndarray{tuple(info['shape'])}"

            # For simple types, store the value
            elif isinstance(value, (int, float, str, bool, type(None))):
                info['value_repr'] = repr(value)

            # For lists/tuples, store length and first few elements
            elif isinstance(value, (list, tuple)):
                info['shape'] = [len(value)]
                if len(value) > 0 and len(value) <= 3:
                    info['value_repr'] = repr(value)
                else:
                    info['value_repr'] = f"{type(value).__name__}(len={len(value)})"

            # For dicts, store number of keys
            elif isinstance(value, dict):
                info['shape'] = [len(value)]
                info['value_repr'] = f"dict(keys={len(value)})"

            else:
                # For other objects, just store type
                info['value_repr'] = f"<{type(value).__name__}>"

        except Exception:
            # If info extraction fails, just use type name
            pass

        return info

    def _export_cycle_execution_tree(self, correlation_id):
        """
        Export execution tree for a completed learning cycle.
        One tree per correlation ID containing all calls with parameters.
        """
        self.logger.info("_export_cycle_execution_tree CALLED for {0}".format(correlation_id))

        if correlation_id not in self.cycle_execution_trees:
            self.logger.info("  SKIPPED: {0} not in cycle_execution_trees".format(correlation_id))
            return

        cycle = self.learning_cycles.get(correlation_id)
        if not cycle:
            self.logger.info("  SKIPPED: {0} not in learning_cycles".format(correlation_id))
            return

        tree = self.cycle_execution_trees[correlation_id]
        self.logger.info("  PROCEEDING: tree has {0} calls".format(len(tree)))

        # Build complete trace data
        trace_data = {
            'correlation_id': correlation_id,
            'start_time': cycle['start_time'],
            'end_time': cycle['end_time'],
            'duration': cycle['end_time'] - cycle['start_time'] if cycle['end_time'] else 0,
            'entry_point': cycle['entry_point'],
            'total_calls': len(tree),

            # Phase information
            'phases': {
                name: {
                    'start_time': phase['start_time'],
                    'end_time': phase['end_time'],
                    'duration': (phase['end_time'] - phase['start_time']) if phase['end_time'] else 0,
                    'call_count': phase['call_count']
                }
                for name, phase in cycle['phases'].items()
            },

            # Complete execution tree with all calls and parameters
            'calls': tree
        }

        # Export to JSON file
        try:
            filename = "{0}_trace_{1}.json".format(
                correlation_id,
                datetime.now().strftime('%Y%m%d_%H%M%S')
            )
            filepath = self.output_dir / filename

            with open(str(filepath), 'w') as f:
                json.dump(trace_data, f, indent=2, default=str)

            self.logger.debug("Execution tree exported: {0}".format(filename))
            self.logger.debug("  Calls: {0}, Phases: {1}".format(
                len(tree), ', '.join(cycle['phases'].keys())
            ))

        except Exception as e:
            self.logger.error("Failed to export execution tree: {0}".format(str(e)), exc_info=True)

        # ALSO stream the complete trace data to PyCharm plugin for Manim video generation
        # Only stream if not already sent (avoid duplicates)
        self.logger.info("  STREAMING CHECK: trace_server={0}, clients={1}, already_streamed={2}".format(
            self.trace_server is not None,
            len(self.trace_server.clients) if self.trace_server else 0,
            correlation_id in self.streamed_cycles
        ))

        if self.trace_server and self.trace_server.clients and correlation_id not in self.streamed_cycles:
            try:
                # Stream complete trace as cycle_complete event (includes all call details)
                cycle_complete_event = {
                    'type': 'cycle_complete',
                    'trace_data': trace_data  # Complete trace with all calls
                }
                self.trace_server.stream_trace(cycle_complete_event)
                self.streamed_cycles.add(correlation_id)  # Mark as streamed
                self.logger.info("  STREAMED cycle_complete for {0} to plugin".format(correlation_id))
            except Exception as e:
                self.logger.error("  FAILED to stream trace to plugin: {0}".format(str(e)))

    def _detect_patterns_in_frame(self, frame, call_record):
        """Detect SQL, WebSocket, WebRTC, MCP, A2A, and cross-process patterns."""

        # Check if this function call itself is a database operation
        func_name = call_record.function_name
        if func_name in ['execute', 'executemany', 'query', 'fetchone', 'fetchall', 'fetchmany']:
            # This is a database cursor method - capture the SQL from arguments
            if 'self' in frame.f_locals:
                # Check for SQL in args
                for arg_name in ['args', 'sql', 'query', 'operation']:
                    if arg_name in frame.f_locals:
                        arg_value = frame.f_locals[arg_name]
                        if isinstance(arg_value, str):
                            # Extract SQL query
                            call_record.sql_queries.append({
                                'query': arg_value[:500],
                                'variable': arg_name,
                                'timestamp': time.time(),
                                'method': func_name
                            })
                        elif isinstance(arg_value, (tuple, list)) and len(arg_value) > 0:
                            # First argument might be the query
                            if isinstance(arg_value[0], str):
                                call_record.sql_queries.append({
                                    'query': arg_value[0][:500],
                                    'variable': arg_name + '[0]',
                                    'timestamp': time.time(),
                                    'method': func_name
                                })

        for var_name, var_value in frame.f_locals.items():
            if isinstance(var_value, str):
                var_upper = var_value.strip().upper()
                var_lower = var_value.lower()

                # SQL detection
                for pattern in self.sql_patterns:
                    if var_upper.startswith(pattern):
                        call_record.sql_queries.append({
                            'query': var_value[:500],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Database library detection
                for pattern in self.db_library_patterns:
                    if pattern.lower() in var_lower:
                        # Detected database library usage
                        call_record.sql_queries.append({
                            'query': var_value[:500],
                            'variable': var_name,
                            'timestamp': time.time(),
                            'library': pattern
                        })
                        break

                # WebSocket detection
                for pattern in self.websocket_patterns:
                    if pattern.lower() in var_lower:
                        call_record.websocket_events.append({
                            'type': 'connection' if 'ws://' in var_lower or 'wss://' in var_lower else 'message',
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # WebRTC detection
                for pattern in self.webrtc_patterns:
                    if pattern in var_value:
                        call_record.webrtc_events.append({
                            'type': pattern,
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # MCP (Model Context Protocol) detection
                for pattern in self.mcp_patterns:
                    if pattern.lower() in var_lower:
                        call_record.mcp_calls.append({
                            'protocol': 'mcp',
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Agent-to-Agent communication detection
                for pattern in self.agent_patterns:
                    if pattern.lower() in var_lower:
                        call_record.agent_communications.append({
                            'type': 'agent_message',
                            'framework': pattern,
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # gRPC detection
                for pattern in self.grpc_patterns:
                    if pattern.lower() in var_lower:
                        call_record.grpc_calls.append({
                            'type': 'grpc_call',
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # GraphQL detection
                for pattern in self.graphql_patterns:
                    if pattern.lower() in var_lower:
                        call_record.graphql_queries.append({
                            'type': 'mutation' if 'mutation' in var_lower else 'query',
                            'data': var_value[:500],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # MQTT detection
                for pattern in self.mqtt_patterns:
                    if pattern.lower() in var_lower:
                        call_record.mqtt_messages.append({
                            'type': 'publish' if 'publish' in var_lower else 'subscribe',
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # AMQP detection
                for pattern in self.amqp_patterns:
                    if pattern.lower() in var_lower:
                        call_record.amqp_messages.append({
                            'type': 'amqp_message',
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Kafka detection
                for pattern in self.kafka_patterns:
                    if pattern.lower() in var_lower:
                        call_record.kafka_events.append({
                            'type': 'produce' if 'producer' in var_lower else 'consume',
                            'data': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Redis detection
                for pattern in self.redis_patterns:
                    if pattern in var_upper or pattern.lower() in var_lower:
                        call_record.redis_commands.append({
                            'command': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Memcached detection
                for pattern in self.memcached_patterns:
                    if pattern.lower() in var_lower:
                        call_record.memcached_ops.append({
                            'operation': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Elasticsearch detection
                for pattern in self.elasticsearch_patterns:
                    if pattern.lower() in var_lower:
                        call_record.elasticsearch_queries.append({
                            'query': var_value[:500],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # SSE detection
                for pattern in self.sse_patterns:
                    if pattern.lower() in var_lower:
                        call_record.sse_events.append({
                            'event': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # HTTP/2 detection
                for pattern in self.http2_patterns:
                    if pattern.lower() in var_lower:
                        call_record.http2_frames.append({
                            'frame': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # Thrift detection
                for pattern in self.thrift_patterns:
                    if pattern in var_value:
                        call_record.thrift_calls.append({
                            'call': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # ZeroMQ detection
                for pattern in self.zeromq_patterns:
                    if pattern in var_upper or pattern.lower() in var_lower:
                        call_record.zeromq_messages.append({
                            'message': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

                # NATS detection
                for pattern in self.nats_patterns:
                    if pattern.lower() in var_lower:
                        call_record.nats_messages.append({
                            'message': var_value[:200],
                            'variable': var_name,
                            'timestamp': time.time()
                        })
                        break

            # Cross-process detection (check for Process/Pool objects)
            if var_name in ['process', 'pool', 'pipe', 'queue', 'manager']:
                var_type = type(var_value).__name__
                for pattern in self.process_patterns:
                    if pattern in var_type:
                        call_record.process_spawns.append({
                            'type': var_type,
                            'variable': var_name,
                            'timestamp': time.time(),
                            'process_id': self.process_id,
                            'distributed_trace_id': self.distributed_trace_id
                        })
                        break

    def _detect_framework(self, module):
        """Detect framework from module name."""
        if 'fastapi' in module:
            return 'fastapi'
        elif 'flask' in module:
            return 'flask'
        elif 'django' in module:
            return 'django'
        elif 'torch' in module:
            return 'pytorch'
        return None

    def _detect_invocation_type(self, func_name: str) -> str:
        """Detect invocation type."""
        if func_name.startswith('async_'):
            return 'async'
        elif 'schedule' in func_name.lower():
            return 'scheduled'
        return 'sync'

    def _is_ai_agent(self, func_name: str, module: str) -> bool:
        """Detect if AI agent function."""
        ai_keywords = ['learn', 'train', 'infer', 'reason', 'plan']
        return any(kw in func_name.lower() or kw in module.lower() for kw in ai_keywords)

    def _cleanup_old_calls(self):
        """Cleanup old call records to prevent memory growth."""
        try:
            # Keep only the last 10000 calls
            if len(self.calls) > 10000:
                # Export current batch before clearing
                old_calls = self.calls
                self.calls = self.calls[-10000:]
                self.logger.debug("Cleaned up {0} old call records".format(len(old_calls) - len(self.calls)))
        except Exception:
            pass

    def export_plantuml(self):
        """Export traces as PlantUML diagram."""
        output_file = self.output_dir / "{0}.puml".format(self.session_id)

        lines = [
            "@startuml",
            "autonumber",
            "skinparam backgroundColor #FEFEFE",
            "",
        ]

        # Add participants
        modules = set(call.module for call in self.calls)
        for module in sorted(modules):
            clean_name = module.replace(".", "_")

            # Determine icon
            icon = "entity"
            if any(c.framework == 'fastapi' and c.module == module for c in self.calls):
                icon = "control"
            elif any(c.is_ai_agent and c.module == module for c in self.calls):
                lines.append('participant "{0}\\n<<AI Agent>>" as {1} #LightBlue'.format(module, clean_name))
                continue

            lines.append('{0} "{1}" as {2}'.format(icon, module, clean_name))

        lines.append("")

        # Add calls
        for call in self.calls:
            if call.duration_ms is None:
                continue

            src = call.module.replace(".", "_")
            label = call.function_name

            if call.invocation_type == 'async':
                label = "<<async>> {0}".format(label)

            if call.is_ai_agent:
                label = "AI {0}".format(label)  # Removed emoji for Python 2 compatibility

            lines.append("{0} -> {0}: {1}".format(src, label))
            lines.append("note right: {0:.1f}ms".format(call.duration_ms))

            if call.exception:
                lines.append("note over {0} #FF6B6B: {1}".format(src, call.exception))

            lines.append("")

        lines.append("@enduml")

        output_file.write_text("\n".join(lines), encoding='utf-8')
        self.logger.debug("Exported PlantUML: {0}".format(str(output_file)))

    def export_performance_json(self):
        """Export performance metrics as JSON."""
        output_file = self.output_dir / "{0}_performance.json".format(self.session_id)

        # Calculate metrics per function
        function_metrics = {}
        for call in self.calls:
            key = "{0}.{1}".format(call.module, call.function_name)
            if key not in function_metrics:
                function_metrics[key] = {
                    "module": call.module,
                    "function": call.function_name,
                    "call_count": 0,
                    "total_time_ms": 0.0,
                    "framework": call.framework,
                    "is_ai_agent": call.is_ai_agent
                }

            function_metrics[key]["call_count"] += 1
            if call.duration_ms:
                function_metrics[key]["total_time_ms"] += call.duration_ms

        # Sort by total time
        metrics_list = sorted(
            function_metrics.values(),
            key=lambda x: x["total_time_ms"],
            reverse=True
        )

        report = {
            "session_id": self.session_id,
            "process_id": self.process_id,
            "start_time": self.start_time,
            "statistics": {
                "total_calls": len(self.calls),
                "total_duration_ms": sum(c.duration_ms or 0 for c in self.calls)
            },
            "function_metrics": metrics_list
        }

        output_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
        self.logger.debug("Exported performance: {0}".format(str(output_file)))

    def export_flamegraph_json(self):
        """Export flamegraph data in speedscope.app compatible format."""
        output_file = self.output_dir / "{0}_flamegraph.json".format(self.session_id)

        # Build call tree hierarchy
        frames = []
        for call in self.calls:
            if call.duration_ms is None:
                continue

            frames.append({
                "name": "{0}.{1}".format(call.module, call.function_name),
                "value": call.duration_ms,
                "file": call.file_path,
                "line": call.line_number,
                "parent_id": call.parent_id,
                "call_id": call.call_id,
                "depth": call.depth,
                "framework": call.framework,
                "is_ai_agent": call.is_ai_agent
            })

        flamegraph_data = {
            "session_id": self.session_id,
            "type": "flamegraph",
            "frames": frames,
            "statistics": {
                "total_duration_ms": sum(c.duration_ms or 0 for c in self.calls if c.parent_id is None),
                "max_depth": max((c.depth for c in self.calls), default=0),
                "total_calls": len(self.calls)
            }
        }

        output_file.write_text(json.dumps(flamegraph_data, indent=2), encoding='utf-8')
        self.logger.debug("Exported flamegraph: {0}".format(str(output_file)))

    def export_sql_analysis_json(self):
        """Export SQL query analysis with N+1 detection."""
        output_file = self.output_dir / "{0}_sql_analysis.json".format(self.session_id)

        # Collect all SQL queries
        all_queries = []
        query_patterns = {}  # Track similar queries for N+1 detection

        for call in self.calls:
            for sql in call.sql_queries:
                query_text = sql['query']

                # Normalize query for pattern matching (remove literals)
                normalized = query_text.upper()
                for i in range(100):
                    normalized = normalized.replace(" {0} ".format(i), " ? ")
                    normalized = normalized.replace("'{0}'".format(i), "?")

                # Track query pattern
                if normalized not in query_patterns:
                    query_patterns[normalized] = {
                        "pattern": normalized,
                        "count": 0,
                        "examples": [],
                        "locations": []
                    }

                query_patterns[normalized]["count"] += 1
                query_patterns[normalized]["examples"].append(query_text[:200])
                query_patterns[normalized]["locations"].append({
                    "module": call.module,
                    "function": call.function_name,
                    "line": call.line_number
                })

                all_queries.append({
                    "query": query_text,
                    "module": call.module,
                    "function": call.function_name,
                    "timestamp": sql['timestamp'],
                    "variable": sql['variable']
                })

        # Detect N+1 queries (same pattern executed many times)
        n_plus_1_issues = []
        for pattern, data in query_patterns.items():
            if data["count"] > 10:  # Threshold for N+1 detection
                n_plus_1_issues.append({
                    "severity": "high" if data["count"] > 50 else "medium",
                    "pattern": pattern,
                    "count": data["count"],
                    "example": data["examples"][0] if data["examples"] else "",
                    "locations": data["locations"][:5],  # First 5 locations
                    "suggestion": "Consider using JOIN or eager loading to reduce query count"
                })

        sql_report = {
            "session_id": self.session_id,
            "statistics": {
                "total_queries": len(all_queries),
                "unique_patterns": len(query_patterns),
                "n_plus_1_issues": len(n_plus_1_issues)
            },
            "n_plus_1_issues": sorted(n_plus_1_issues, key=lambda x: x["count"], reverse=True),
            "all_queries": all_queries[:100]  # Limit to first 100
        }

        output_file.write_text(json.dumps(sql_report, indent=2), encoding='utf-8')
        self.logger.debug("Exported SQL analysis: {0}".format(str(output_file)))

    def export_live_metrics_json(self):
        """Export real-time metrics snapshot."""
        output_file = self.output_dir / "{0}_live_metrics.json".format(self.session_id)

        # Calculate current metrics
        current_time = time.time()
        recent_calls = [c for c in self.calls if c.start_time > current_time - 60]  # Last 60 seconds

        # Top slowest functions
        slowest = sorted(
            [c for c in self.calls if c.duration_ms],
            key=lambda x: x.duration_ms,
            reverse=True
        )[:10]

        # Error rate
        errors = [c for c in self.calls if c.exception]
        error_rate = (len(errors) / len(self.calls) * 100) if self.calls else 0

        metrics = {
            "session_id": self.session_id,
            "timestamp": current_time,
            "metrics": {
                "requests_per_sec": len(recent_calls) / 60.0 if recent_calls else 0,
                "avg_latency_ms": sum(c.duration_ms or 0 for c in recent_calls) / len(recent_calls) if recent_calls else 0,
                "error_rate_percent": error_rate,
                "total_calls": len(self.calls),
                "active_calls": len(self.active_calls)
            },
            "top_slowest": [
                {
                    "function": "{0}.{1}".format(c.module, c.function_name),
                    "duration_ms": c.duration_ms,
                    "file": c.file_path,
                    "line": c.line_number
                }
                for c in slowest
            ],
            "recent_errors": [
                {
                    "function": "{0}.{1}".format(c.module, c.function_name),
                    "exception": c.exception,
                    "timestamp": c.start_time
                }
                for c in errors[-10:]  # Last 10 errors
            ]
        }

        output_file.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
        self.logger.debug("Exported live metrics: {0}".format(str(output_file)))

    def export_distributed_analysis_json(self):
        """Export WebSocket, WebRTC, MCP, A2A, and cross-process analysis."""
        output_file = self.output_dir / "{0}_distributed_analysis.json".format(self.session_id)

        # Collect all distributed/streaming events
        websocket_events = []
        webrtc_events = []
        mcp_calls = []
        agent_communications = []
        process_spawns = []

        for call in self.calls:
            for ws in call.websocket_events:
                websocket_events.append({
                    'module': call.module,
                    'function': call.function_name,
                    'type': ws['type'],
                    'data': ws['data'],
                    'timestamp': ws['timestamp']
                })

            for rtc in call.webrtc_events:
                webrtc_events.append({
                    'module': call.module,
                    'function': call.function_name,
                    'type': rtc['type'],
                    'data': rtc['data'],
                    'timestamp': rtc['timestamp']
                })

            for mcp in call.mcp_calls:
                mcp_calls.append({
                    'module': call.module,
                    'function': call.function_name,
                    'protocol': mcp['protocol'],
                    'data': mcp['data'],
                    'timestamp': mcp['timestamp']
                })

            for agent in call.agent_communications:
                agent_communications.append({
                    'module': call.module,
                    'function': call.function_name,
                    'type': agent['type'],
                    'framework': agent['framework'],
                    'data': agent['data'],
                    'timestamp': agent['timestamp']
                })

            for proc in call.process_spawns:
                process_spawns.append({
                    'module': call.module,
                    'function': call.function_name,
                    'type': proc['type'],
                    'process_id': proc['process_id'],
                    'distributed_trace_id': proc['distributed_trace_id'],
                    'timestamp': proc['timestamp']
                })

        # Build architecture map (cross-process stitching)
        architecture_map = {
            'current_process': {
                'pid': self.process_id,
                'parent_pid': self.parent_process_id,
                'distributed_trace_id': self.distributed_trace_id,
                'session_id': self.session_id
            },
            'spawned_processes': process_spawns,
            'websocket_connections': len(websocket_events),
            'webrtc_connections': len(webrtc_events),
            'mcp_calls': len(mcp_calls),
            'agent_communications': len(agent_communications)
        }

        distributed_report = {
            "session_id": self.session_id,
            "distributed_trace_id": self.distributed_trace_id,
            "process_info": {
                "pid": self.process_id,
                "parent_pid": self.parent_process_id
            },
            "statistics": {
                "websocket_events": len(websocket_events),
                "webrtc_events": len(webrtc_events),
                "mcp_calls": len(mcp_calls),
                "agent_communications": len(agent_communications),
                "process_spawns": len(process_spawns)
            },
            "architecture_map": architecture_map,
            "websocket_events": websocket_events[:100],  # Limit
            "webrtc_events": webrtc_events[:100],
            "mcp_calls": mcp_calls[:100],
            "agent_communications": agent_communications[:100],
            "process_spawns": process_spawns
        }

        output_file.write_text(json.dumps(distributed_report, indent=2), encoding='utf-8')
        self.logger.debug("Exported distributed analysis: {0}".format(str(output_file)))

    def export_markdown_summary(self):
        """Export comprehensive markdown summary for human + LLM consumption."""
        output_file = self.output_dir / "session_{0}_summary.md".format(self.session_id)

        # Collect protocol statistics
        total_sql = sum(len(c.sql_queries) for c in self.calls)
        total_websocket = sum(len(c.websocket_events) for c in self.calls)
        total_webrtc = sum(len(c.webrtc_events) for c in self.calls)
        total_mcp = sum(len(c.mcp_calls) for c in self.calls)
        total_grpc = sum(len(c.grpc_calls) for c in self.calls)
        total_graphql = sum(len(c.graphql_queries) for c in self.calls)
        total_mqtt = sum(len(c.mqtt_messages) for c in self.calls)
        total_kafka = sum(len(c.kafka_events) for c in self.calls)
        total_redis = sum(len(c.redis_commands) for c in self.calls)
        total_amqp = sum(len(c.amqp_messages) for c in self.calls)

        # Detect frameworks
        frameworks = set()
        for call in self.calls:
            if call.framework:
                frameworks.add(call.framework)

        # Calculate performance metrics
        if self.calls:
            durations = [c.duration_ms for c in self.calls if c.duration_ms and c.duration_ms > 0]
            avg_duration = sum(durations) / len(durations) if durations else 0
            max_duration = max(durations) if durations else 0
            total_duration = sum(durations)
        else:
            avg_duration = max_duration = total_duration = 0

        # Build markdown content
        lines = [
            "# Runtime Analysis Summary",
            "",
            "**Session ID:** {0}".format(self.session_id),
            "**Process ID:** {0}".format(self.process_id),
            "**Total Functions Called:** {0}".format(len(self.calls)),
            "**Total Execution Time:** {0:.2f}ms".format(total_duration),
            "",
            "## Architecture Overview",
            "",
            "This application uses the following technologies:",
            ""
        ]

        # Add detected frameworks
        if frameworks:
            lines.append("### Web Frameworks")
            for fw in sorted(frameworks):
                lines.append("- {0}".format(fw))
            lines.append("")

        # Add protocols
        protocols_found = []
        if total_sql > 0:
            protocols_found.append(("SQL Database", total_sql, "queries"))
        if total_websocket > 0:
            protocols_found.append(("WebSocket", total_websocket, "events"))
        if total_webrtc > 0:
            protocols_found.append(("WebRTC", total_webrtc, "events"))
        if total_mcp > 0:
            protocols_found.append(("MCP (Model Context Protocol)", total_mcp, "calls"))
        if total_grpc > 0:
            protocols_found.append(("gRPC", total_grpc, "calls"))
        if total_graphql > 0:
            protocols_found.append(("GraphQL", total_graphql, "queries"))
        if total_mqtt > 0:
            protocols_found.append(("MQTT", total_mqtt, "messages"))
        if total_kafka > 0:
            protocols_found.append(("Kafka", total_kafka, "events"))
        if total_redis > 0:
            protocols_found.append(("Redis", total_redis, "commands"))
        if total_amqp > 0:
            protocols_found.append(("AMQP/RabbitMQ", total_amqp, "messages"))

        if protocols_found:
            lines.append("### Protocols Detected")
            for protocol, count, unit in protocols_found:
                lines.append("- **{0}**: {1} {2}".format(protocol, count, unit))
            lines.append("")

        # Performance metrics
        lines.extend([
            "## Performance Metrics",
            "",
            "- **Average Function Duration:** {0:.2f}ms".format(avg_duration),
            "- **Slowest Function:** {0:.2f}ms".format(max_duration),
            "- **Total Runtime:** {0:.2f}ms".format(total_duration),
            "",
            "## Top 10 Slowest Functions",
            ""
        ])

        # List slowest functions
        sorted_calls = sorted(self.calls, key=lambda c: c.duration_ms or 0, reverse=True)[:10]
        for i, call in enumerate(sorted_calls, 1):
            lines.append("{0}. **{1}.{2}** - {3:.2f}ms ({4}:{5})".format(
                i, call.module, call.function_name, call.duration_ms or 0,
                call.file_path, call.line_number
            ))

        lines.append("")
        lines.append("## Recommendations")
        lines.append("")

        # Add recommendations based on detected patterns
        if total_sql > 100:
            lines.append("- Consider implementing SQL query caching or connection pooling")
        if total_websocket > 0:
            lines.append("- WebSocket connections detected - ensure proper connection lifecycle management")
        if total_grpc > 0:
            lines.append("- gRPC detected - consider using connection pooling and keepalive settings")
        if total_kafka > 0:
            lines.append("- Kafka events detected - ensure batch processing for better throughput")
        if max_duration > 1000:
            lines.append("- Functions taking >1 second detected - consider async processing or optimization")

        lines.append("")
        lines.append("---")
        lines.append("*Generated by PyCharm Learning Flow Visualizer Plugin*")

        output_file.write_text('\n'.join(lines), encoding='utf-8')
        self.logger.debug("Exported markdown summary: {0}".format(str(output_file)))

    def export_llm_text_summary(self):
        """Export natural language summary optimized for LLM understanding."""
        output_file = self.output_dir / "session_{0}_llm_summary.txt".format(self.session_id)

        # Collect comprehensive statistics
        total_calls = len(self.calls)
        frameworks = set(c.framework for c in self.calls if c.framework)

        protocol_counts = {
            'sql': sum(len(c.sql_queries) for c in self.calls),
            'websocket': sum(len(c.websocket_events) for c in self.calls),
            'webrtc': sum(len(c.webrtc_events) for c in self.calls),
            'mcp': sum(len(c.mcp_calls) for c in self.calls),
            'grpc': sum(len(c.grpc_calls) for c in self.calls),
            'graphql': sum(len(c.graphql_queries) for c in self.calls),
            'mqtt': sum(len(c.mqtt_messages) for c in self.calls),
            'kafka': sum(len(c.kafka_events) for c in self.calls),
            'redis': sum(len(c.redis_commands) for c in self.calls),
            'amqp': sum(len(c.amqp_messages) for c in self.calls),
            'elasticsearch': sum(len(c.elasticsearch_queries) for c in self.calls),
            'memcached': sum(len(c.memcached_ops) for c in self.calls)
        }

        # Build natural language summary
        lines = []

        # Opening statement
        lines.append("RUNTIME ANALYSIS SUMMARY")
        lines.append("=" * 80)
        lines.append("")

        # Architecture description
        if frameworks:
            fw_list = ', '.join(sorted(frameworks))
            lines.append("This is a Python application using {0}. ".format(fw_list))
        else:
            lines.append("This is a Python application. ")

        lines.append("During execution, the application called {0} functions. ".format(total_calls))
        lines.append("")

        # Protocol usage description
        active_protocols = [(name, count) for name, count in protocol_counts.items() if count > 0]
        if active_protocols:
            lines.append("The application communicates using the following protocols:")
            lines.append("")
            for protocol, count in active_protocols:
                if protocol == 'sql':
                    lines.append("- SQL DATABASE: The app executed {0} SQL queries, indicating database interaction.".format(count))
                elif protocol == 'websocket':
                    lines.append("- WEBSOCKET: The app used {0} WebSocket events for real-time bidirectional communication.".format(count))
                elif protocol == 'webrtc':
                    lines.append("- WEBRTC: The app used {0} WebRTC events for peer-to-peer media streaming.".format(count))
                elif protocol == 'mcp':
                    lines.append("- MCP: The app made {0} Model Context Protocol calls for AI model interaction.".format(count))
                elif protocol == 'grpc':
                    lines.append("- gRPC: The app made {0} gRPC calls for high-performance RPC communication.".format(count))
                elif protocol == 'graphql':
                    lines.append("- GRAPHQL: The app executed {0} GraphQL queries for flexible API data fetching.".format(count))
                elif protocol == 'mqtt':
                    lines.append("- MQTT: The app sent/received {0} MQTT messages for IoT or pub/sub messaging.".format(count))
                elif protocol == 'kafka':
                    lines.append("- KAFKA: The app produced/consumed {0} Kafka events for distributed event streaming.".format(count))
                elif protocol == 'redis':
                    lines.append("- REDIS: The app executed {0} Redis commands for caching or message brokering.".format(count))
                elif protocol == 'amqp':
                    lines.append("- AMQP/RABBITMQ: The app sent {0} AMQP messages for message queue communication.".format(count))
                elif protocol == 'elasticsearch':
                    lines.append("- ELASTICSEARCH: The app executed {0} search queries for full-text search.".format(count))
                elif protocol == 'memcached':
                    lines.append("- MEMCACHED: The app performed {0} memcached operations for distributed caching.".format(count))
            lines.append("")

        # Performance analysis
        durations = [c.duration_ms for c in self.calls if c.duration_ms and c.duration_ms > 0]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            total_duration = sum(durations)

            lines.append("PERFORMANCE ANALYSIS:")
            lines.append("")
            lines.append("The application's total execution time was {0:.2f} milliseconds. ".format(total_duration))
            lines.append("On average, each function took {0:.2f}ms to execute. ".format(avg_duration))
            lines.append("The slowest function took {0:.2f}ms. ".format(max_duration))
            lines.append("")

            if max_duration > 1000:
                lines.append("WARNING: Some functions are taking over 1 second to complete. Consider optimization.")
                lines.append("")

        # Architecture recommendations
        lines.append("ARCHITECTURE INSIGHTS:")
        lines.append("")

        if protocol_counts['websocket'] > 0 and protocol_counts['sql'] > 0:
            lines.append("- This appears to be a real-time application (WebSocket) with database persistence (SQL).")
        if protocol_counts['kafka'] > 0 or protocol_counts['amqp'] > 0:
            lines.append("- This is a distributed system using message queues for inter-service communication.")
        if protocol_counts['grpc'] > 0:
            lines.append("- This application uses gRPC for microservice communication.")
        if protocol_counts['mcp'] > 0:
            lines.append("- This application integrates AI models using the Model Context Protocol.")
        if protocol_counts['redis'] > 0 or protocol_counts['memcached'] > 0:
            lines.append("- The application uses caching to improve performance.")

        lines.append("")
        lines.append("=" * 80)
        lines.append("End of analysis")

        output_file.write_text('\n'.join(lines), encoding='utf-8')
        self.logger.debug("Exported LLM text summary: {0}".format(str(output_file)))

    def export_mermaid_diagrams(self):
        """Export Mermaid diagram (text-based, LLM-friendly)."""
        output_file = self.output_dir / "session_{0}_architecture.mmd".format(self.session_id)

        # Collect unique modules and their relationships
        modules = {}
        for call in self.calls:
            if call.module not in modules:
                modules[call.module] = {
                    'calls': 0,
                    'protocols': set(),
                    'dependencies': set()
                }
            modules[call.module]['calls'] += 1

            # Track protocol usage per module
            if len(call.sql_queries) > 0:
                modules[call.module]['protocols'].add('SQL')
            if len(call.websocket_events) > 0:
                modules[call.module]['protocols'].add('WebSocket')
            if len(call.grpc_calls) > 0:
                modules[call.module]['protocols'].add('gRPC')
            if len(call.graphql_queries) > 0:
                modules[call.module]['protocols'].add('GraphQL')
            if len(call.kafka_events) > 0:
                modules[call.module]['protocols'].add('Kafka')
            if len(call.redis_commands) > 0:
                modules[call.module]['protocols'].add('Redis')

        # Build Mermaid graph
        lines = [
            "graph TD",
            "    %% Architecture Diagram - Session {0}".format(self.session_id),
            ""
        ]

        # Add nodes for each module
        for i, (module, data) in enumerate(sorted(modules.items())):
            module_safe = module.replace('.', '_').replace('-', '_')
            protocols_str = ', '.join(sorted(data['protocols'])) if data['protocols'] else 'No Protocols'
            lines.append("    {0}[{1}<br/>{2} calls<br/>{3}]".format(
                module_safe, module, data['calls'], protocols_str
            ))

        lines.append("")

        # Add external system nodes
        external_systems = set()
        for call in self.calls:
            if len(call.sql_queries) > 0:
                external_systems.add('Database')
            if len(call.websocket_events) > 0:
                external_systems.add('WebSocket_Server')
            if len(call.kafka_events) > 0:
                external_systems.add('Kafka_Cluster')
            if len(call.redis_commands) > 0:
                external_systems.add('Redis_Cache')
            if len(call.grpc_calls) > 0:
                external_systems.add('gRPC_Service')

        for system in sorted(external_systems):
            lines.append("    {0}[(({0}))]".format(system))

        lines.append("")

        # Add connections from modules to external systems
        for module, data in modules.items():
            module_safe = module.replace('.', '_').replace('-', '_')
            if 'SQL' in data['protocols']:
                lines.append("    {0} -->|SQL Queries| Database".format(module_safe))
            if 'WebSocket' in data['protocols']:
                lines.append("    {0} -->|WebSocket| WebSocket_Server".format(module_safe))
            if 'Kafka' in data['protocols']:
                lines.append("    {0} -->|Kafka Events| Kafka_Cluster".format(module_safe))
            if 'Redis' in data['protocols']:
                lines.append("    {0} -->|Redis Commands| Redis_Cache".format(module_safe))
            if 'gRPC' in data['protocols']:
                lines.append("    {0} -->|gRPC Calls| gRPC_Service".format(module_safe))

        lines.append("")
        lines.append("    %% Style definitions")
        lines.append("    classDef moduleClass fill:#e1f5ff,stroke:#01579b,stroke-width:2px")
        lines.append("    classDef externalClass fill:#fff3e0,stroke:#e65100,stroke-width:2px")

        output_file.write_text('\n'.join(lines), encoding='utf-8')
        self.logger.debug("Exported Mermaid diagram: {0}".format(str(output_file)))

    def export_d2_diagram(self):
        """Export D2 diagram (modern declarative diagram format)."""
        output_file = self.output_dir / "session_{0}_architecture.d2".format(self.session_id)

        # Collect modules and protocols
        modules = {}
        for call in self.calls:
            if call.module not in modules:
                modules[call.module] = {'protocols': set(), 'calls': 0}
            modules[call.module]['calls'] += 1

            if len(call.sql_queries) > 0:
                modules[call.module]['protocols'].add('SQL')
            if len(call.websocket_events) > 0:
                modules[call.module]['protocols'].add('WebSocket')
            if len(call.grpc_calls) > 0:
                modules[call.module]['protocols'].add('gRPC')
            if len(call.kafka_events) > 0:
                modules[call.module]['protocols'].add('Kafka')
            if len(call.redis_commands) > 0:
                modules[call.module]['protocols'].add('Redis')

        # Build D2 content
        lines = [
            "# Runtime Architecture - Session {0}".format(self.session_id),
            "",
            "direction: right",
            ""
        ]

        # Add modules
        for module, data in sorted(modules.items()):
            module_safe = module.replace('.', '_').replace('-', '_')
            protocols = ', '.join(sorted(data['protocols'])) if data['protocols'] else 'None'
            lines.append("{0}: {{".format(module_safe))
            lines.append("  shape: rectangle")
            lines.append("  label: {0}".format(module))
            lines.append("  calls: {0}".format(data['calls']))
            lines.append("  protocols: {0}".format(protocols))
            lines.append("}")
            lines.append("")

        # Add external systems
        external = set()
        for call in self.calls:
            if len(call.sql_queries) > 0:
                external.add('database')
            if len(call.websocket_events) > 0:
                external.add('websocket_server')
            if len(call.kafka_events) > 0:
                external.add('kafka_cluster')
            if len(call.redis_commands) > 0:
                external.add('redis_cache')
            if len(call.grpc_calls) > 0:
                external.add('grpc_service')

        for ext in sorted(external):
            lines.append("{0}: {{".format(ext))
            lines.append("  shape: cylinder")
            lines.append("  style.fill: \"#fff3e0\"")
            lines.append("}")
            lines.append("")

        # Add connections
        for module, data in modules.items():
            module_safe = module.replace('.', '_').replace('-', '_')
            if 'SQL' in data['protocols']:
                lines.append("{0} -> database: SQL Queries".format(module_safe))
            if 'WebSocket' in data['protocols']:
                lines.append("{0} -> websocket_server: WebSocket".format(module_safe))
            if 'Kafka' in data['protocols']:
                lines.append("{0} -> kafka_cluster: Kafka Events".format(module_safe))
            if 'Redis' in data['protocols']:
                lines.append("{0} -> redis_cache: Redis Commands".format(module_safe))
            if 'gRPC' in data['protocols']:
                lines.append("{0} -> grpc_service: gRPC Calls".format(module_safe))

        output_file.write_text('\n'.join(lines), encoding='utf-8')
        self.logger.debug("Exported D2 diagram: {0}".format(str(output_file)))

    def export_ascii_art(self):
        """Export ASCII art architecture visualization."""
        output_file = self.output_dir / "session_{0}_ascii.txt".format(self.session_id)

        # Collect protocol usage
        protocols = {
            'SQL': sum(len(c.sql_queries) for c in self.calls),
            'WebSocket': sum(len(c.websocket_events) for c in self.calls),
            'WebRTC': sum(len(c.webrtc_events) for c in self.calls),
            'gRPC': sum(len(c.grpc_calls) for c in self.calls),
            'GraphQL': sum(len(c.graphql_queries) for c in self.calls),
            'Kafka': sum(len(c.kafka_events) for c in self.calls),
            'Redis': sum(len(c.redis_commands) for c in self.calls),
            'MQTT': sum(len(c.mqtt_messages) for c in self.calls),
            'AMQP': sum(len(c.amqp_messages) for c in self.calls)
        }

        active_protocols = [(name, count) for name, count in protocols.items() if count > 0]

        # Build ASCII art
        lines = [
            "=" * 80,
            "  RUNTIME ARCHITECTURE MAP - Session {0}".format(self.session_id),
            "=" * 80,
            "",
            "                            YOUR APPLICATION",
            "                          +------------------+",
            "                          |  Python Process  |",
            "                          |  PID: {0:6}      |".format(self.process_id),
            "                          |  Calls: {0:6}    |".format(len(self.calls)),
            "                          +------------------+",
            "                                   |"
        ]

        if active_protocols:
            lines.append("                                   | Communicates via:")
            lines.append("                                   |")

            # Draw connections to external systems
            for i, (protocol, count) in enumerate(active_protocols):
                is_last = (i == len(active_protocols) - 1)
                connector = "                                   +--" if not is_last else "                                   +--"

                if protocol == 'SQL':
                    lines.append("{0}> SQL ({1} queries)".format(connector, count))
                    lines.append("                                   |      |")
                    lines.append("                                   |      v")
                    lines.append("                                   |   [DATABASE]")
                elif protocol == 'WebSocket':
                    lines.append("{0}> WebSocket ({1} events)".format(connector, count))
                    lines.append("                                   |      |")
                    lines.append("                                   |      v")
                    lines.append("                                   |   [WS SERVER]")
                elif protocol == 'gRPC':
                    lines.append("{0}> gRPC ({1} calls)".format(connector, count))
                    lines.append("                                   |      |")
                    lines.append("                                   |      v")
                    lines.append("                                   |   [gRPC SERVICE]")
                elif protocol == 'Kafka':
                    lines.append("{0}> Kafka ({1} events)".format(connector, count))
                    lines.append("                                   |      |")
                    lines.append("                                   |      v")
                    lines.append("                                   |   [KAFKA CLUSTER]")
                elif protocol == 'Redis':
                    lines.append("{0}> Redis ({1} commands)".format(connector, count))
                    lines.append("                                   |      |")
                    lines.append("                                   |      v")
                    lines.append("                                   |   [REDIS CACHE]")
                else:
                    lines.append("{0}> {1} ({2} ops)".format(connector, protocol, count))

                if not is_last:
                    lines.append("                                   |")
        else:
            lines.append("                                   |")
            lines.append("                          (No external protocols detected)")

        lines.append("")
        lines.append("=" * 80)

        output_file.write_text('\n'.join(lines), encoding='utf-8')
        self.logger.debug("Exported ASCII art: {0}".format(str(output_file)))

    def finalize(self):
        """Finalize and export all reports."""
        try:
            # Update durations for any remaining active calls
            for call in self.calls:
                try:
                    if call.end_time:
                        call.duration_ms = (call.end_time - call.start_time) * 1000
                    elif call.start_time:
                        # Call didn't complete - estimate duration
                        call.end_time = time.time()
                        call.duration_ms = (call.end_time - call.start_time) * 1000
                except Exception:
                    # Skip this call if duration calculation fails
                    continue

            # Export all report types - each wrapped in try-except for graceful degradation
            export_methods = [
                ('PlantUML', self.export_plantuml),
                ('Performance JSON', self.export_performance_json),
                ('Flamegraph JSON', self.export_flamegraph_json),
                ('SQL Analysis', self.export_sql_analysis_json),
                ('Live Metrics', self.export_live_metrics_json),
                ('Distributed Analysis', self.export_distributed_analysis_json),
                ('Markdown Summary', self.export_markdown_summary),
                ('LLM Text Summary', self.export_llm_text_summary),
                ('Mermaid Diagram', self.export_mermaid_diagrams),
                ('D2 Diagram', self.export_d2_diagram),
                ('ASCII Art', self.export_ascii_art)
            ]

            failed_exports = []
            for export_name, export_func in export_methods:
                try:
                    export_func()
                except Exception as e:
                    failed_exports.append((export_name, str(e)))

            # Log summary
            successful_count = len(export_methods) - len(failed_exports)
            self.logger.info("Instrumentation session complete: {0} calls recorded (pid: {1})".format(
                len(self.calls), self.process_id))
            self.logger.info("Exported {0}/{1} report formats successfully".format(
                successful_count, len(export_methods)))

            if failed_exports:
                self.logger.warning("Some exports failed:")
                for export_name, error in failed_exports:
                    self.logger.warning("  - {0}: {1}".format(export_name, error[:100]))

        except Exception as e:
            # Even finalize should not crash
            self.logger.error("Error during finalization: {0}".format(str(e)), exc_info=True)


# ============================================================================
# AUTO-ENABLE INSTRUMENTATION (Runtime injection by plugin)
# ============================================================================

_instrumentor = None

def _enable_instrumentation():
    """Enable instrumentation (called automatically by plugin)."""
    global _instrumentor

    try:
        if _instrumentor is not None:
            return  # Already enabled

        trace_dir = os.getenv('CRAWL4AI_TRACE_DIR', './traces')
        _instrumentor = RuntimeInstrumentor(output_dir=trace_dir)

        # Hook into sys.settrace
        sys.settrace(_instrumentor.trace_function)

        # Register cleanup on exit
        import atexit
        atexit.register(_safe_finalize)

        # Register signal handlers to catch crashes
        import signal
        def _signal_handler(signum, frame):
            if _instrumentor:
                _instrumentor.logger.info("Caught signal {0}, finalizing traces...".format(signum))
            _safe_finalize()
            # Re-raise to allow normal signal handling
            if signum == signal.SIGINT:
                raise KeyboardInterrupt
            elif signum == signal.SIGTERM:
                sys.exit(1)

        try:
            signal.signal(signal.SIGINT, _signal_handler)   # Ctrl+C
            signal.signal(signal.SIGTERM, _signal_handler)  # kill command
            if hasattr(signal, 'SIGBREAK'):
                signal.signal(signal.SIGBREAK, _signal_handler)  # Windows Ctrl+Break
        except (ValueError, OSError):
            # Signal handlers can only be set in main thread
            pass

        _instrumentor.logger.info("Runtime instrumentation active (output: {0})".format(trace_dir))

    except Exception as e:
        # CRITICAL: Never crash on initialization
        # Use basic print since logger may not be available
        print("[PyCharm Plugin] Failed to enable instrumentation: {0}".format(str(e)))
        print("[PyCharm Plugin] Application will continue without instrumentation")


def _safe_finalize():
    """Safe finalize that never crashes."""
    global _instrumentor
    try:
        if _instrumentor is not None:
            _instrumentor.finalize()
    except Exception as e:
        # Use basic print since logger may not be available
        print("[PyCharm Plugin] Error during cleanup: {0}".format(str(e)))


# Auto-enable if environment variable is set (plugin sets this)
if os.getenv('PYCHARM_PLUGIN_TRACE_ENABLED') == '1':
    try:
        _enable_instrumentation()
    except Exception as e:
        # Never crash the application during auto-enable
        # Use basic print since logger may not be available
        print("[PyCharm Plugin] Auto-enable failed: {0}".format(str(e)))
