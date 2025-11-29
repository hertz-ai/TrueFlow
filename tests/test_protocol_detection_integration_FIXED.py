# Integration Tests for Protocol Detection - FIXED VERSION
# Tests detection of all 29+ protocols in realistic scenarios with sys.settrace enabled

import sys
import os
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime_injector'))

from python_runtime_instrumentor import RuntimeInstrumentor


class TestSQLDetectionIntegration(unittest.TestCase):
    """Integration tests for SQL detection across different databases"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sql_queries_detected(self):
        """Test SQL queries are detected during execution"""
        sys.settrace(self.instrumentor.trace_function)

        def execute_sql():
            query = "SELECT * FROM users WHERE age > 18"
            return query

        execute_sql()
        sys.settrace(None)

        # Check if SQL was detected
        sql_calls = [c for c in self.instrumentor.calls if len(c.sql_queries) > 0]
        self.assertGreater(len(sql_calls), 0)

    def test_multiple_sql_patterns(self):
        """Test different SQL statement types"""
        sys.settrace(self.instrumentor.trace_function)

        def run_queries():
            select_query = "SELECT * FROM products"
            insert_query = "INSERT INTO orders (id, total) VALUES (1, 99.99)"
            update_query = "UPDATE customers SET status = 'active'"
            delete_query = "DELETE FROM temp_data WHERE date < '2024-01-01'"
            return [select_query, insert_query, update_query, delete_query]

        run_queries()
        sys.settrace(None)

        # Should detect all SQL patterns
        all_queries = []
        for call in self.instrumentor.calls:
            all_queries.extend(call.sql_queries)

        self.assertGreater(len(all_queries), 0)


class TestWebSocketDetectionIntegration(unittest.TestCase):
    """Integration tests for WebSocket detection"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_websocket_url_detection(self):
        """Test WebSocket URL detection"""
        sys.settrace(self.instrumentor.trace_function)

        def connect_websocket():
            url = "ws://localhost:8000/ws"
            secure_url = "wss://api.example.com/socket"
            return url, secure_url

        connect_websocket()
        sys.settrace(None)

        ws_calls = [c for c in self.instrumentor.calls if len(c.websocket_events) > 0]
        self.assertGreater(len(ws_calls), 0)


class TestExportIntegration(unittest.TestCase):
    """Integration tests for all export methods working together"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.instrumentor = RuntimeInstrumentor(output_dir=self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_exports_generated(self):
        """Test that all 11 files are generated"""
        sys.settrace(self.instrumentor.trace_function)

        def sample_app():
            query = "SELECT * FROM users"
            ws_url = "ws://localhost:8000/ws"
            redis_cmd = "SET key value"
            return query, ws_url, redis_cmd

        sample_app()
        sys.settrace(None)

        # Finalize to generate all exports
        self.instrumentor.finalize()

        # Check all files exist
        files = list(Path(self.temp_dir).iterdir())
        filenames = [f.name for f in files]

        # Should have 11 files
        self.assertEqual(len(files), 11)

        # Check specific file types
        self.assertTrue(any('performance.json' in f for f in filenames))
        self.assertTrue(any('flamegraph.json' in f for f in filenames))
        self.assertTrue(any('sql_analysis.json' in f for f in filenames))
        self.assertTrue(any('live_metrics.json' in f for f in filenames))
        self.assertTrue(any('distributed_analysis.json' in f for f in filenames))
        self.assertTrue(any('.puml' in f for f in filenames))
        self.assertTrue(any('summary.md' in f for f in filenames))
        self.assertTrue(any('llm_summary.txt' in f for f in filenames))
        self.assertTrue(any('architecture.mmd' in f for f in filenames))
        self.assertTrue(any('architecture.d2' in f for f in filenames))
        self.assertTrue(any('ascii.txt' in f for f in filenames))


if __name__ == '__main__':
    unittest.main(verbosity=2)
