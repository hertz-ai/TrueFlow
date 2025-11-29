# Unit Tests for Python Runtime Instrumentor
# Tests all methods in python_runtime_instrumentor.py

import sys
import os
import json
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime_injector'))

from python_runtime_instrumentor import RuntimeInstrumentor, FunctionCall


class TestFunctionCall(unittest.TestCase):
    """Unit tests for FunctionCall class"""

    def test_function_call_initialization(self):
        """Test FunctionCall object creation"""
        call = FunctionCall(
            call_id='call_001',
            function_name='test_function',
            module='test_module',
            file_path='/path/to/file.py',
            line_number=42,
            start_time=1000.0,
            framework='FastAPI',
            invocation_type='async',
            is_ai_agent=True,
            parent_id='call_000',
            depth=2
        )

        self.assertEqual(call.call_id, 'call_001')
        self.assertEqual(call.function_name, 'test_function')
        self.assertEqual(call.module, 'test_module')
        self.assertEqual(call.file_path, '/path/to/file.py')
        self.assertEqual(call.line_number, 42)
        self.assertEqual(call.start_time, 1000.0)
        self.assertEqual(call.framework, 'FastAPI')
        self.assertEqual(call.invocation_type, 'async')
        self.assertTrue(call.is_ai_agent)
        self.assertEqual(call.parent_id, 'call_000')
        self.assertEqual(call.depth, 2)

    def test_function_call_default_values(self):
        """Test FunctionCall with default values"""
        call = FunctionCall(
            call_id='call_002',
            function_name='default_test',
            module='default_module',
            file_path='/default.py',
            line_number=1,
            start_time=2000.0
        )

        self.assertIsNone(call.framework)
        self.assertEqual(call.invocation_type, 'sync')
        self.assertFalse(call.is_ai_agent)
        self.assertIsNone(call.parent_id)
        self.assertEqual(call.depth, 0)
        self.assertIsNone(call.end_time)
        self.assertIsNone(call.duration_ms)

    def test_function_call_protocol_lists(self):
        """Test that all protocol lists are initialized"""
        call = FunctionCall(
            call_id='call_003',
            function_name='test',
            module='test',
            file_path='/test.py',
            line_number=1,
            start_time=3000.0
        )

        # Check all protocol lists exist and are empty
        self.assertEqual(call.sql_queries, [])
        self.assertEqual(call.websocket_events, [])
        self.assertEqual(call.webrtc_events, [])
        self.assertEqual(call.mcp_calls, [])
        self.assertEqual(call.agent_communications, [])
        self.assertEqual(call.process_spawns, [])
        self.assertEqual(call.grpc_calls, [])
        self.assertEqual(call.graphql_queries, [])
        self.assertEqual(call.mqtt_messages, [])
        self.assertEqual(call.amqp_messages, [])
        self.assertEqual(call.kafka_events, [])
        self.assertEqual(call.redis_commands, [])
        self.assertEqual(call.memcached_ops, [])
        self.assertEqual(call.elasticsearch_queries, [])
        self.assertEqual(call.sse_events, [])
        self.assertEqual(call.http2_frames, [])
        self.assertEqual(call.thrift_calls, [])
        self.assertEqual(call.zeromq_messages, [])
        self.assertEqual(call.nats_messages, [])


class TestRuntimeInstrumentorInitialization(unittest.TestCase):
    """Unit tests for RuntimeInstrumentor initialization"""

    def setUp(self):
        """Create temporary directory for each test"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_instrumentor_initialization(self):
        """Test RuntimeInstrumentor initialization"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        self.assertIsNotNone(instrumentor.session_id)
        self.assertTrue(len(instrumentor.session_id) > 0)
        self.assertEqual(instrumentor.calls, [])
        self.assertEqual(instrumentor.call_stack, [])
        self.assertEqual(instrumentor.active_calls, {})
        self.assertEqual(instrumentor.call_counter, 0)
        self.assertIsInstance(instrumentor.process_id, int)
        self.assertIsInstance(instrumentor.parent_process_id, int)

    def test_pattern_lists_initialized(self):
        """Test all pattern detection lists are initialized"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # SQL patterns
        self.assertIn('SELECT ', instrumentor.sql_patterns)
        self.assertIn('INSERT ', instrumentor.sql_patterns)

        # WebSocket patterns
        self.assertIn('ws://', instrumentor.websocket_patterns)
        self.assertIn('websocket', instrumentor.websocket_patterns)

        # gRPC patterns
        self.assertIn('grpc', instrumentor.grpc_patterns)

        # GraphQL patterns
        self.assertIn('graphql', instrumentor.graphql_patterns)

        # Kafka patterns
        self.assertIn('kafka', instrumentor.kafka_patterns)

        # Redis patterns
        self.assertIn('redis', instrumentor.redis_patterns)


class TestExportMethods(unittest.TestCase):
    """Unit tests for all export methods"""

    def setUp(self):
        """Create instrumentor with sample data"""
        self.temp_dir = tempfile.mkdtemp()
        self.instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Add sample function calls
        call1 = FunctionCall(
            call_id='call_001',
            function_name='fetch_users',
            module='myapp.database',
            file_path='/app/database.py',
            line_number=45,
            start_time=1000.0,
            framework='FastAPI',
            parent_id=None,
            depth=0
        )
        call1.end_time = 1000.5
        call1.duration_ms = 500.0
        call1.sql_queries.append({
            'query': 'SELECT * FROM users',
            'timestamp': 1000.1,
            'variable': 'query'
        })

        call2 = FunctionCall(
            call_id='call_002',
            function_name='send_message',
            module='myapp.websocket',
            file_path='/app/websocket.py',
            line_number=78,
            start_time=1001.0,
            parent_id='call_001',
            depth=1
        )
        call2.end_time = 1001.2
        call2.duration_ms = 200.0
        call2.websocket_events.append({
            'type': 'send',
            'url': 'ws://localhost:8000/ws',
            'data': 'message_data',
            'timestamp': 1001.1
        })

        call3 = FunctionCall(
            call_id='call_003',
            function_name='publish_event',
            module='myapp.kafka',
            file_path='/app/kafka.py',
            line_number=23,
            start_time=1002.0,
            parent_id='call_001',
            depth=1
        )
        call3.end_time = 1002.1
        call3.duration_ms = 100.0
        call3.kafka_events.append({
            'type': 'produce',
            'data': 'user-events',
            'timestamp': 1002.05
        })

        self.instrumentor.calls = [call1, call2, call3]

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_performance_json(self):
        """Test export_performance_json creates valid JSON"""
        self.instrumentor.export_performance_json()

        # Find the performance JSON file
        files = list(Path(self.temp_dir).glob('*_performance.json'))
        self.assertEqual(len(files), 1)

        # Load and validate JSON
        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('session_id', data)
        self.assertIn('function_metrics', data)
        self.assertEqual(len(data['function_metrics']), 3)

        # Check first call
        call = data['function_metrics'][0]
        self.assertEqual(call['function'], 'fetch_users')
        self.assertEqual(call['module'], 'myapp.database')
        self.assertEqual(call['total_time_ms'], 500.0)

    def test_export_flamegraph_json(self):
        """Test export_flamegraph_json creates hierarchical structure"""
        self.instrumentor.export_flamegraph_json()

        files = list(Path(self.temp_dir).glob('*_flamegraph.json'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('session_id', data)
        self.assertIn('frames', data)
        self.assertIn('statistics', data)

        # Check frames have parent_id and depth
        frames = data['frames']
        self.assertTrue(any(f['parent_id'] is None for f in frames))  # Root calls
        self.assertTrue(any(f['parent_id'] is not None for f in frames))  # Child calls

        # Check statistics
        stats = data['statistics']
        self.assertEqual(stats['total_calls'], 3)
        # Only the first call has duration since others don't propagate up
        self.assertGreater(stats['total_duration_ms'], 0)

    def test_export_sql_analysis_json(self):
        """Test export_sql_analysis_json analyzes SQL queries"""
        self.instrumentor.export_sql_analysis_json()

        files = list(Path(self.temp_dir).glob('*_sql_analysis.json'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('session_id', data)
        self.assertIn('statistics', data)
        self.assertIn('all_queries', data)
        self.assertEqual(data['statistics']['total_queries'], 1)

    def test_export_live_metrics_json(self):
        """Test export_live_metrics_json calculates metrics"""
        self.instrumentor.export_live_metrics_json()

        files = list(Path(self.temp_dir).glob('*_live_metrics.json'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('session_id', data)
        self.assertIn('metrics', data)

        metrics = data['metrics']
        self.assertIn('requests_per_sec', metrics)
        self.assertIn('avg_latency_ms', metrics)
        self.assertIn('error_rate_percent', metrics)

    def test_export_distributed_analysis_json(self):
        """Test export_distributed_analysis_json captures protocols"""
        self.instrumentor.export_distributed_analysis_json()

        files = list(Path(self.temp_dir).glob('*_distributed_analysis.json'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('websocket_events', data)
        self.assertIn('architecture_map', data)

        # Check websocket events
        self.assertEqual(len(data['websocket_events']), 1)
        ws_event = data['websocket_events'][0]
        self.assertEqual(ws_event['type'], 'send')

        # Note: Kafka events are tracked separately in the runtime instrumentor
        # but not exported in the distributed_analysis.json file

    def test_export_markdown_summary(self):
        """Test export_markdown_summary creates markdown file"""
        self.instrumentor.export_markdown_summary()

        files = list(Path(self.temp_dir).glob('*_summary.md'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            content = f.read()

        # Check markdown structure
        self.assertIn('# Runtime Analysis Summary', content)
        self.assertIn('## Architecture Overview', content)
        self.assertIn('## Performance Metrics', content)
        self.assertIn('## Top 10 Slowest Functions', content)
        self.assertIn('FastAPI', content)

    def test_export_llm_text_summary(self):
        """Test export_llm_text_summary creates natural language summary"""
        self.instrumentor.export_llm_text_summary()

        files = list(Path(self.temp_dir).glob('*_llm_summary.txt'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            content = f.read()

        # Check natural language
        self.assertIn('RUNTIME ANALYSIS SUMMARY', content)
        self.assertIn('Python application', content)
        self.assertIn('SQL queries', content)
        self.assertIn('WebSocket', content)

    def test_export_mermaid_diagrams(self):
        """Test export_mermaid_diagrams creates Mermaid syntax"""
        self.instrumentor.export_mermaid_diagrams()

        files = list(Path(self.temp_dir).glob('*_architecture.mmd'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            content = f.read()

        # Check Mermaid syntax
        self.assertIn('graph TD', content)
        self.assertIn('myapp_database', content)
        self.assertIn('Database', content)
        self.assertIn('-->', content)

    def test_export_d2_diagram(self):
        """Test export_d2_diagram creates D2 syntax"""
        self.instrumentor.export_d2_diagram()

        files = list(Path(self.temp_dir).glob('*_architecture.d2'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            content = f.read()

        # Check D2 syntax
        self.assertIn('direction: right', content)
        self.assertIn('myapp_database:', content)
        self.assertIn('shape: rectangle', content)
        self.assertIn('->', content)

    def test_export_ascii_art(self):
        """Test export_ascii_art creates ASCII visualization"""
        self.instrumentor.export_ascii_art()

        files = list(Path(self.temp_dir).glob('*_ascii.txt'))
        self.assertEqual(len(files), 1)

        with open(files[0], 'r', encoding='utf-8') as f:
            content = f.read()

        # Check ASCII art
        self.assertIn('RUNTIME ARCHITECTURE MAP', content)
        self.assertIn('YOUR APPLICATION', content)
        self.assertIn('Python Process', content)
        self.assertIn('SQL', content)


class TestPatternDetection(unittest.TestCase):
    """Unit tests for protocol pattern detection"""

    def setUp(self):
        """Create instrumentor"""
        self.temp_dir = tempfile.mkdtemp()
        self.instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

    def tearDown(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sql_pattern_detection(self):
        """Test SQL query detection"""
        call = FunctionCall(
            call_id='test',
            function_name='test',
            module='test',
            file_path='/test.py',
            line_number=1,
            start_time=1000.0
        )

        # Create mock frame
        class MockFrame:
            f_locals = {'query': 'SELECT * FROM users WHERE id = 1'}
            f_code = type('obj', (object,), {'co_name': 'test'})()
            f_lineno = 1

        frame = MockFrame()
        self.instrumentor._detect_patterns_in_frame(frame, call)

        # Check SQL query was detected
        self.assertEqual(len(call.sql_queries), 1)
        self.assertIn('SELECT', call.sql_queries[0]['query'])

    def test_websocket_pattern_detection(self):
        """Test WebSocket detection"""
        call = FunctionCall(
            call_id='test',
            function_name='test',
            module='test',
            file_path='/test.py',
            line_number=1,
            start_time=1000.0
        )

        class MockFrame:
            f_locals = {'url': 'ws://localhost:8000/ws'}
            f_code = type('obj', (object,), {'co_name': 'test'})()
            f_lineno = 1

        frame = MockFrame()
        self.instrumentor._detect_patterns_in_frame(frame, call)

        self.assertEqual(len(call.websocket_events), 1)

    def test_grpc_pattern_detection(self):
        """Test gRPC detection"""
        call = FunctionCall(
            call_id='test',
            function_name='test',
            module='test',
            file_path='/test.py',
            line_number=1,
            start_time=1000.0
        )

        class MockFrame:
            f_locals = {'channel': 'grpc.insecure_channel(localhost:50051)'}
            f_code = type('obj', (object,), {'co_name': 'test'})()
            f_lineno = 1

        frame = MockFrame()
        self.instrumentor._detect_patterns_in_frame(frame, call)

        self.assertEqual(len(call.grpc_calls), 1)


if __name__ == '__main__':
    unittest.main()
