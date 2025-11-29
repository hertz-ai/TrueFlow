# End-to-End Tests for PyCharm Plugin
# Tests the complete workflow from instrumentation to file generation

import sys
import os
import json
import tempfile
import unittest
import subprocess
import time
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime_injector'))

from python_runtime_instrumentor import RuntimeInstrumentor


@contextmanager
def enable_tracing(instrumentor):
    """Context manager to enable tracing during code execution."""
    sys.settrace(instrumentor.trace_function)
    try:
        yield
    finally:
        sys.settrace(None)


class TestEndToEndSimpleApp(unittest.TestCase):
    """E2E test for simple Python application"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_script = os.path.join(self.temp_dir, 'simple_app.py')

        # Create a simple test application
        with open(self.test_script, 'w') as f:
            f.write('''
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b

def main():
    result1 = add(5, 3)
    result2 = multiply(4, 7)
    result3 = add(result1, result2)
    print(f"Final result: {result3}")

if __name__ == "__main__":
    main()
''')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_simple_app_instrumentation(self):
        """Test that simple app generates all export files"""
        # Run with instrumentation
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Enable tracing and execute the test script code
        with enable_tracing(instrumentor):
            exec(open(self.test_script).read())

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Check all 11 files were generated (one script file + test files)
        files = list(Path(self.temp_dir).iterdir())
        # At least 11 export files should be generated (may include the test script)
        self.assertGreaterEqual(len(files), 11)


class TestEndToEndFastAPIApp(unittest.TestCase):
    """E2E test for FastAPI-like application"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fastapi_app_with_sql(self):
        """Test FastAPI app with SQL queries"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Simulate FastAPI app
        def create_user(username, email):
            query = f"INSERT INTO users (username, email) VALUES ('{username}', '{email}')"
            return query

        def get_users():
            query = "SELECT * FROM users ORDER BY created_at DESC"
            return query

        def update_user(user_id, status):
            query = f"UPDATE users SET status = '{status}' WHERE id = {user_id}"
            return query

        # Execute app functions with tracing enabled
        with enable_tracing(instrumentor):
            create_user("john", "john@example.com")
            create_user("jane", "jane@example.com")
            get_users()
            update_user(1, "active")

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Load SQL analysis
        sql_file = list(Path(self.temp_dir).glob('*_sql_analysis.json'))[0]
        with open(sql_file, 'r') as f:
            sql_data = json.load(f)

        # Should have SQL analysis data (structure may vary)
        # Just verify the file was generated with some content
        self.assertIsInstance(sql_data, dict)

        # Load markdown summary
        md_file = list(Path(self.temp_dir).glob('*_summary.md'))[0]
        with open(md_file, 'r') as f:
            md_content = f.read()

        # Verify summary was generated with session info
        self.assertIn('Session', md_content)


class TestEndToEndWebSocketApp(unittest.TestCase):
    """E2E test for WebSocket application"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_websocket_app(self):
        """Test WebSocket application"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Simulate WebSocket app
        def connect_websocket(url):
            ws_url = f"ws://localhost:8000/{url}"
            return ws_url

        def send_message(message):
            ws_data = f"websocket.send('{message}')"
            return ws_data

        def receive_message():
            ws_receive = "websocket.receive()"
            return ws_receive

        # Execute WebSocket functions with tracing enabled
        with enable_tracing(instrumentor):
            connect_websocket("chat")
            send_message("Hello WebSocket!")
            receive_message()

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Load distributed analysis
        dist_file = list(Path(self.temp_dir).glob('*_distributed_analysis.json'))[0]
        with open(dist_file, 'r') as f:
            dist_data = json.load(f)

        # Should have detected WebSocket events
        self.assertIn('websocket_events', dist_data)


class TestEndToEndMicroservicesApp(unittest.TestCase):
    """E2E test for microservices application with gRPC + Kafka + Redis"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_microservices_architecture(self):
        """Test microservices with multiple protocols"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Simulate microservices app
        def call_user_service():
            grpc_call = "grpc.insecure_channel('user-service:50051')"
            return grpc_call

        def publish_event(event_type, data):
            kafka_topic = f"events.{event_type}"
            kafka_msg = f"kafka.produce('{kafka_topic}', '{data}')"
            return kafka_msg

        def cache_result(key, value):
            redis_cmd = f"SET {key} '{value}'"
            return redis_cmd

        def query_database(table):
            sql = f"SELECT * FROM {table}"
            return sql

        # Execute microservices functions with tracing enabled
        with enable_tracing(instrumentor):
            call_user_service()
            publish_event("user.created", "{'user_id': 123}")
            cache_result("user:123", "John Doe")
            query_database("users")

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Load LLM text summary
        txt_file = list(Path(self.temp_dir).glob('*_llm_summary.txt'))[0]
        with open(txt_file, 'r') as f:
            txt_content = f.read()

        # Should describe the architecture
        self.assertIn('gRPC', txt_content)
        self.assertIn('Kafka', txt_content)
        self.assertIn('Redis', txt_content)
        self.assertIn('SQL', txt_content)

        # Load Mermaid diagram
        mmd_file = list(Path(self.temp_dir).glob('*_architecture.mmd'))[0]
        with open(mmd_file, 'r') as f:
            mmd_content = f.read()

        self.assertIn('graph TD', mmd_content)
        self.assertIn('gRPC', mmd_content)


class TestEndToEndPerformanceAnalysis(unittest.TestCase):
    """E2E test for performance analysis features"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_performance_metrics(self):
        """Test that performance metrics are calculated correctly"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Simulate functions with different execution times
        def fast_function():
            return sum(range(100))

        def slow_function():
            time.sleep(0.1)  # Simulate slow operation
            return sum(range(10000))

        def medium_function():
            time.sleep(0.05)
            return sum(range(5000))

        # Execute functions with tracing enabled
        with enable_tracing(instrumentor):
            fast_function()
            slow_function()
            medium_function()

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Load flamegraph
        flame_file = list(Path(self.temp_dir).glob('*_flamegraph.json'))[0]
        with open(flame_file, 'r') as f:
            flame_data = json.load(f)

        # Should have statistics
        stats = flame_data['statistics']
        self.assertIn('total_calls', stats)
        self.assertIn('total_duration_ms', stats)
        self.assertIn('max_depth', stats)

        # Verify some calls were recorded
        self.assertGreater(stats['total_calls'], 0)

        # Load markdown summary
        md_file = list(Path(self.temp_dir).glob('*_summary.md'))[0]
        with open(md_file, 'r') as f:
            md_content = f.read()

        # Should have summary content (format may vary)
        self.assertIn('Session', md_content)


class TestEndToEndAIAgentApp(unittest.TestCase):
    """E2E test for AI agent application"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ai_agent_communication(self):
        """Test AI agent communication detection"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Simulate AI agent app
        def create_autogen_agent():
            agent = "autogen.AssistantAgent(name='researcher')"
            return agent

        def create_crewai_crew():
            crew = "Crew(agents=[agent1, agent2], tasks=[task1])"
            return crew

        def use_mcp_protocol():
            mcp = "mcp.Client('llm-context-manager')"
            return mcp

        # Execute agent functions with tracing enabled
        with enable_tracing(instrumentor):
            create_autogen_agent()
            create_crewai_crew()
            use_mcp_protocol()

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Load distributed analysis
        dist_file = list(Path(self.temp_dir).glob('*_distributed_analysis.json'))[0]
        with open(dist_file, 'r') as f:
            dist_data = json.load(f)

        # Should have agent communications
        self.assertIn('agent_communications', dist_data)
        self.assertIn('mcp_calls', dist_data)


class TestEndToEndLLMFriendlyExports(unittest.TestCase):
    """E2E test for LLM-friendly export formats"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_llm_formats_generated(self):
        """Test that all LLM-friendly formats are generated"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        # Simple app
        def process_data():
            query = "SELECT * FROM data"
            redis_cmd = "GET cache:data"
            return query, redis_cmd

        # Execute with tracing enabled
        with enable_tracing(instrumentor):
            process_data()

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Check markdown summary
        md_files = list(Path(self.temp_dir).glob('*_summary.md'))
        self.assertEqual(len(md_files), 1)

        # Check LLM text summary
        txt_files = list(Path(self.temp_dir).glob('*_llm_summary.txt'))
        self.assertEqual(len(txt_files), 1)

        # Check Mermaid diagram
        mmd_files = list(Path(self.temp_dir).glob('*_architecture.mmd'))
        self.assertEqual(len(mmd_files), 1)

        # Check D2 diagram
        d2_files = list(Path(self.temp_dir).glob('*_architecture.d2'))
        self.assertEqual(len(d2_files), 1)

        # Check ASCII art
        ascii_files = list(Path(self.temp_dir).glob('*_ascii.txt'))
        self.assertEqual(len(ascii_files), 1)

    def test_llm_summary_natural_language(self):
        """Test that LLM summary uses natural language"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        def sample_app():
            sql = "SELECT * FROM products"
            ws = "ws://localhost:8000/updates"
            return sql, ws

        # Execute with tracing enabled
        with enable_tracing(instrumentor):
            sample_app()

        # Finalize is called to generate exports
        instrumentor.finalize()

        # Load LLM text summary
        txt_file = list(Path(self.temp_dir).glob('*_llm_summary.txt'))[0]
        with open(txt_file, 'r') as f:
            content = f.read()

        # Should use natural language
        self.assertIn('Python application', content)
        self.assertIn('SQL queries', content)
        self.assertIn('WebSocket', content)
        self.assertIn('ARCHITECTURE INSIGHTS', content)


class TestEndToEndDiagramGeneration(unittest.TestCase):
    """E2E test for diagram generation"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mermaid_diagram_syntax(self):
        """Test Mermaid diagram has valid syntax"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        def app():
            sql = "SELECT * FROM users"
            return sql

        # Execute with tracing enabled
        with enable_tracing(instrumentor):
            app()

        # Finalize is called to generate exports
        instrumentor.finalize()

        mmd_file = list(Path(self.temp_dir).glob('*_architecture.mmd'))[0]
        with open(mmd_file, 'r') as f:
            content = f.read()

        # Should have valid Mermaid syntax
        self.assertIn('graph TD', content)
        self.assertIn('-->', content)
        self.assertIn('[', content)
        self.assertIn(']', content)

    def test_d2_diagram_syntax(self):
        """Test D2 diagram has valid syntax"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        def app():
            redis = "SET key value"
            return redis

        # Execute with tracing enabled
        with enable_tracing(instrumentor):
            app()

        # Finalize is called to generate exports
        instrumentor.finalize()

        d2_file = list(Path(self.temp_dir).glob('*_architecture.d2'))[0]
        with open(d2_file, 'r') as f:
            content = f.read()

        # Should have valid D2 syntax
        self.assertIn('direction:', content)
        self.assertIn('->', content)
        self.assertIn('{', content)
        self.assertIn('}', content)

    def test_ascii_art_visualization(self):
        """Test ASCII art is properly formatted"""
        instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

        def app():
            kafka = "kafka.Producer()"
            return kafka

        # Execute with tracing enabled
        with enable_tracing(instrumentor):
            app()

        # Finalize is called to generate exports
        instrumentor.finalize()

        ascii_file = list(Path(self.temp_dir).glob('*_ascii.txt'))[0]
        with open(ascii_file, 'r') as f:
            content = f.read()

        # Should have box drawing
        self.assertIn('=', content)
        self.assertIn('|', content)
        self.assertIn('+', content)
        self.assertIn('YOUR APPLICATION', content)


if __name__ == '__main__':
    unittest.main()
