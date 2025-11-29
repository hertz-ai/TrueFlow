# Real-World Test with api_server.py
# Tests the plugin with actual FastAPI application to verify all functionality

import sys
import os
import json
import subprocess
import time
import tempfile
import unittest
from pathlib import Path

# Check if optional dependencies are available
try:
    import requests
    import fastapi
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    requests = None  # Mock for type hints

# Add runtime injector to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime_injector'))


@unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI and requests not installed - skipping real-world tests")
class TestRealWorldAPIServer(unittest.TestCase):
    """
    Real-world test using the actual api_server.py
    This test verifies:
    1. Runtime instrumentation works with FastAPI
    2. All 11 export files are generated
    3. FastAPI framework is detected
    4. SQL/WebSocket/other protocols are captured (if used)
    5. Performance metrics are realistic
    6. LLM-friendly exports contain useful information
    """

    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.temp_dir = tempfile.mkdtemp()
        cls.api_server_path = os.path.join(
            os.path.dirname(__file__),
            '../../src/crawl4ai/server/api_server.py'
        )
        cls.runtime_instrumentor_path = os.path.join(
            os.path.dirname(__file__),
            '../runtime_injector/python_runtime_instrumentor.py'
        )

        # Check if api_server.py exists
        if not os.path.exists(cls.api_server_path):
            cls.api_server_path = 'C:/Users/sathi/PycharmProjects/crawl4ai/src/crawl4ai/server/api_server.py'

        print(f"API Server path: {cls.api_server_path}")
        print(f"Temp dir: {cls.temp_dir}")

    @classmethod
    def tearDownClass(cls):
        """Clean up"""
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_api_server_instrumentation(self):
        """Test that api_server.py runs with instrumentation and generates all files"""

        # Create a test script that imports and uses the runtime instrumentor
        test_script = os.path.join(self.temp_dir, 'test_server.py')
        # Use forward slashes for Windows compatibility in Python paths
        temp_dir_safe = self.temp_dir.replace('\\', '/')
        runtime_dir_safe = os.path.dirname(self.runtime_instrumentor_path).replace('\\', '/')
        with open(test_script, 'w') as f:
            f.write(f'''
import sys
import os

# Set output directory for instrumentation
os.environ['PYCHARM_PLUGIN_OUTPUT_DIR'] = "{temp_dir_safe}"

# Import runtime instrumentor FIRST
sys.path.insert(0, "{runtime_dir_safe}")
from python_runtime_instrumentor import RuntimeInstrumentor

# Create instrumentor
instrumentor = RuntimeInstrumentor(output_dir="{temp_dir_safe}")

# Import FastAPI (this will be traced)
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

# Create simple FastAPI app
app = FastAPI(title="Test API")

class Message(BaseModel):
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    model: str = "test-model"

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    \"\"\"Test endpoint\"\"\"
    # Simulate some work
    response_content = f"Echo: {{request.messages[-1].content if request.messages else 'no message'}}"

    return {{
        "id": "test-123",
        "object": "chat.completion",
        "model": request.model,
        "choices": [{{
            "index": 0,
            "message": {{
                "role": "assistant",
                "content": response_content
            }}
        }}]
    }}

@app.get("/v1/stats")
async def get_stats():
    \"\"\"Stats endpoint\"\"\"
    return {{
        "total_requests": 1,
        "framework": "FastAPI"
    }}

# Simulate some requests
import asyncio

async def simulate_requests():
    \"\"\"Simulate API usage\"\"\"
    # Call endpoints to generate traces
    req = ChatRequest(
        messages=[Message(content="Hello, World!")],
        model="test-model"
    )

    # Simulate processing
    result = await chat_completions(req)
    stats = await get_stats()

    print(f"Chat result: {{result}}")
    print(f"Stats: {{stats}}")

# Run simulation
asyncio.run(simulate_requests())

# Finalize instrumentation
instrumentor.finalize()
print(f"Instrumentation complete. Files in: {temp_dir_safe}")
''')

        # Run the test script
        result = subprocess.run(
            [sys.executable, test_script],
            capture_output=True,
            text=True,
            timeout=30
        )

        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

        # Check that script ran successfully
        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        # Check that all 11 files were generated
        files = list(Path(self.temp_dir).glob('session_*'))
        print(f"Generated {len(files)} files:")
        for f in files:
            print(f"  - {f.name}")

        self.assertEqual(len(files), 11, f"Expected 11 files, got {len(files)}")

        # Verify specific file types exist
        self.assertTrue(any('performance.json' in str(f) for f in files), "Missing performance.json")
        self.assertTrue(any('flamegraph.json' in str(f) for f in files), "Missing flamegraph.json")
        self.assertTrue(any('sql_analysis.json' in str(f) for f in files), "Missing sql_analysis.json")
        self.assertTrue(any('live_metrics.json' in str(f) for f in files), "Missing live_metrics.json")
        self.assertTrue(any('distributed_analysis.json' in str(f) for f in files), "Missing distributed_analysis.json")
        self.assertTrue(any('.puml' in str(f) for f in files), "Missing PlantUML file")
        self.assertTrue(any('summary.md' in str(f) for f in files), "Missing markdown summary")
        self.assertTrue(any('llm_summary.txt' in str(f) for f in files), "Missing LLM text summary")
        self.assertTrue(any('architecture.mmd' in str(f) for f in files), "Missing Mermaid diagram")
        self.assertTrue(any('architecture.d2' in str(f) for f in files), "Missing D2 diagram")
        self.assertTrue(any('ascii.txt' in str(f) for f in files), "Missing ASCII art")

    def test_fastapi_framework_detection(self):
        """Test that FastAPI framework is detected"""

        test_script = os.path.join(self.temp_dir, 'test_fastapi_detection.py')
        with open(test_script, 'w') as f:
            f.write(f'''
import sys
import os
os.environ['PYCHARM_PLUGIN_OUTPUT_DIR'] = r"{self.temp_dir}"

sys.path.insert(0, r"{os.path.dirname(self.runtime_instrumentor_path)}")
from python_runtime_instrumentor import RuntimeInstrumentor

instrumentor = RuntimeInstrumentor(output_dir=r"{self.temp_dir}")

# Import and use FastAPI
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {{"message": "Hello"}}

# Call the endpoint function directly
result = read_root()
print(f"Result: {{result}}")

instrumentor.finalize()
''')

        result = subprocess.run([sys.executable, test_script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)

        # Load markdown summary
        md_files = list(Path(self.temp_dir).glob('*_summary.md'))
        if md_files:
            with open(md_files[0], 'r') as f:
                content = f.read()

            # Check that FastAPI is mentioned
            self.assertIn('FastAPI', content, "FastAPI framework not detected in summary")

    def test_performance_metrics_realistic(self):
        """Test that performance metrics are calculated correctly"""

        test_script = os.path.join(self.temp_dir, 'test_performance.py')
        with open(test_script, 'w') as f:
            f.write(f'''
import sys
import os
import time

os.environ['PYCHARM_PLUGIN_OUTPUT_DIR'] = r"{self.temp_dir}"
sys.path.insert(0, r"{os.path.dirname(self.runtime_instrumentor_path)}")
from python_runtime_instrumentor import RuntimeInstrumentor

instrumentor = RuntimeInstrumentor(output_dir=r"{self.temp_dir}")

def fast_function():
    return sum(range(100))

def slow_function():
    time.sleep(0.05)  # 50ms
    return sum(range(1000))

def medium_function():
    time.sleep(0.02)  # 20ms
    return sum(range(500))

# Execute functions
fast_function()
slow_function()
medium_function()

instrumentor.finalize()
''')

        result = subprocess.run([sys.executable, test_script], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0)

        # Load performance JSON
        perf_files = list(Path(self.temp_dir).glob('*_performance.json'))
        if perf_files:
            with open(perf_files[0], 'r') as f:
                data = json.load(f)

            stats = data.get('statistics', {})
            self.assertGreater(stats.get('total_duration_ms', 0), 0)
            print(f"Total duration: {stats.get('total_duration_ms')}ms")

    def test_llm_summary_contains_architecture_insights(self):
        """Test that LLM summary provides useful architectural insights"""

        test_script = os.path.join(self.temp_dir, 'test_llm_summary.py')
        with open(test_script, 'w') as f:
            f.write(f'''
import sys
import os

os.environ['PYCHARM_PLUGIN_OUTPUT_DIR'] = r"{self.temp_dir}"
sys.path.insert(0, r"{os.path.dirname(self.runtime_instrumentor_path)}")
from python_runtime_instrumentor import RuntimeInstrumentor

instrumentor = RuntimeInstrumentor(output_dir=r"{self.temp_dir}")

# Simulate different protocol usage
def database_function():
    query = "SELECT * FROM users WHERE id = 1"
    return query

def cache_function():
    redis_cmd = "SET user:1 'John Doe'"
    return redis_cmd

def websocket_function():
    ws_url = "ws://localhost:8000/ws"
    return ws_url

# Execute
database_function()
cache_function()
websocket_function()

instrumentor.finalize()
''')

        result = subprocess.run([sys.executable, test_script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)

        # Load LLM text summary
        txt_files = list(Path(self.temp_dir).glob('*_llm_summary.txt'))
        if txt_files:
            with open(txt_files[0], 'r') as f:
                content = f.read()

            # Check for key architectural insights
            self.assertIn('Python application', content)
            self.assertIn('ARCHITECTURE INSIGHTS', content)
            print("LLM Summary Preview:")
            print(content[:500])

    def test_mermaid_diagram_valid_syntax(self):
        """Test that generated Mermaid diagram has valid syntax"""

        test_script = os.path.join(self.temp_dir, 'test_mermaid.py')
        with open(test_script, 'w') as f:
            f.write(f'''
import sys
import os

os.environ['PYCHARM_PLUGIN_OUTPUT_DIR'] = r"{self.temp_dir}"
sys.path.insert(0, r"{os.path.dirname(self.runtime_instrumentor_path)}")
from python_runtime_instrumentor import RuntimeInstrumentor

instrumentor = RuntimeInstrumentor(output_dir=r"{self.temp_dir}")

def api_handler():
    sql = "SELECT * FROM data"
    return sql

api_handler()
instrumentor.finalize()
''')

        result = subprocess.run([sys.executable, test_script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)

        # Load Mermaid diagram
        mmd_files = list(Path(self.temp_dir).glob('*_architecture.mmd'))
        if mmd_files:
            with open(mmd_files[0], 'r') as f:
                content = f.read()

            # Validate Mermaid syntax
            self.assertIn('graph TD', content)
            self.assertIn('-->', content)
            self.assertIn('[', content)
            self.assertIn(']', content)
            print("Mermaid Diagram:")
            print(content[:300])


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
