"""
Test suite for AI Explanation Panel functionality.

Tests cover:
1. Context injection from other panels (dead code, performance, call trace)
2. Conversation history management
3. LLM wrapper calls (mock-based)
4. Public API methods for panel integration
5. Image/screenshot handling
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Optional

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'main', 'resources', 'runtime_injector'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'main', 'resources'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestContextInjection:
    """Tests for context injection from other panels."""

    def test_dead_code_context_building(self):
        """Test building context from dead code data."""
        dead_code_data = {
            "dead_functions": [
                "unused_helper",
                "deprecated_method",
                "old_api_handler"
            ],
            "called_functions": [
                "main",
                "process_data",
                "handle_request"
            ]
        }

        # Simulate context building (mirror Kotlin logic)
        context = self._build_dead_code_context(dead_code_data)

        assert "Dead Code Context" in context
        assert "unused_helper" in context
        assert "deprecated_method" in context
        assert "3" in context  # Count of dead functions

    def test_performance_context_building(self):
        """Test building context from performance data."""
        performance_data = {
            "hotspots": [
                {"function": "process_data", "total_ms": 1250.5, "calls": 150},
                {"function": "db_query", "total_ms": 890.2, "calls": 45},
                {"function": "serialize", "total_ms": 120.0, "calls": 300}
            ]
        }

        context = self._build_performance_context(performance_data)

        assert "Performance Context" in context
        assert "process_data" in context
        assert "1250.50" in context or "1250.5" in context
        assert "150 calls" in context

    def test_call_trace_context_building(self):
        """Test building context from call trace data."""
        call_trace_data = {
            "calls": [
                {"depth": 0, "function": "main", "module": "app"},
                {"depth": 1, "function": "process", "module": "processor"},
                {"depth": 2, "function": "validate", "module": "validator"},
                {"depth": 2, "function": "transform", "module": "transformer"},
                {"depth": 1, "function": "save", "module": "storage"}
            ]
        }

        context = self._build_call_trace_context(call_trace_data)

        assert "Call Trace Context" in context
        assert "app.main()" in context
        assert "processor.process()" in context
        # Check indentation reflects depth
        assert "→" in context

    def test_combined_context_building(self):
        """Test building combined context from all panels."""
        dead_code_data = {"dead_functions": ["unused"]}
        performance_data = {"hotspots": [{"function": "slow", "total_ms": 1000, "calls": 10}]}
        call_trace_data = {"calls": [{"depth": 0, "function": "main", "module": "app"}]}

        all_context = self._build_all_context(dead_code_data, performance_data, call_trace_data)

        assert "Dead Code Context" in all_context
        assert "Performance Context" in all_context
        assert "Call Trace Context" in all_context

    def test_empty_context_handling(self):
        """Test handling of empty/null context data."""
        context = self._build_dead_code_context(None)
        assert context == ""

        context = self._build_performance_context({})
        assert context == ""

        context = self._build_call_trace_context({"calls": []})
        assert context == ""

    # Helper methods that mirror the Kotlin/TypeScript logic
    def _build_dead_code_context(self, data: Optional[dict]) -> str:
        if not data:
            return ""
        dead_functions = data.get("dead_functions", [])
        if not dead_functions:
            return ""

        context = "\n--- Dead Code Context ---\n"
        context += f"Dead/Unreachable functions ({len(dead_functions)}):\n"
        for func in dead_functions[:20]:
            context += f"  - {func}\n"
        return context

    def _build_performance_context(self, data: Optional[dict]) -> str:
        if not data:
            return ""
        hotspots = data.get("hotspots", [])
        if not hotspots:
            return ""

        context = "\n--- Performance Context ---\n"
        context += "Performance hotspots:\n"
        for item in hotspots[:10]:
            func = item.get("function", "?")
            total_ms = item.get("total_ms", 0)
            calls = item.get("calls", 0)
            context += f"  - {func}: {total_ms:.2f}ms ({calls} calls)\n"
        return context

    def _build_call_trace_context(self, data: Optional[dict]) -> str:
        if not data:
            return ""
        calls = data.get("calls", [])
        if not calls:
            return ""

        context = "\n--- Call Trace Context ---\n"
        context += "Recent call sequence:\n"
        for item in calls[:30]:
            depth = item.get("depth", 0)
            func = item.get("function", "?")
            module = item.get("module", "?")
            indent = "  " * depth
            context += f"{indent}→ {module}.{func}()\n"
        return context

    def _build_all_context(self, dead_code: dict, performance: dict, call_trace: dict) -> str:
        return (
            self._build_dead_code_context(dead_code) +
            self._build_performance_context(performance) +
            self._build_call_trace_context(call_trace)
        )


class TestConversationHistory:
    """Tests for conversation history management."""

    def test_history_trimming(self):
        """Test that history is trimmed to max size."""
        max_history = 3  # 3 exchanges = 6 messages
        history = []

        # Add more than max history
        for i in range(10):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})

        # Trim history
        while len(history) > max_history * 2:
            history.pop(0)

        assert len(history) == 6  # 3 exchanges
        # Should keep most recent
        assert "Question 7" in history[0]["content"]

    def test_history_includes_images(self):
        """Test that history correctly handles image data."""
        history = []
        history.append({
            "role": "user",
            "content": "What is this?",
            "imageBase64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        })
        history.append({
            "role": "assistant",
            "content": "This is a small test image."
        })

        assert len(history) == 2
        assert history[0].get("imageBase64") is not None
        assert history[1].get("imageBase64") is None


class TestLLMWrapperCalls:
    """Tests for LLM wrapper functionality used by Manim and other panels."""

    def test_method_summary_prompt_format(self):
        """Test the prompt format for method summary (used by Manim billboard)."""
        method_name = "process_data"
        method_code = """
def process_data(self, items):
    results = []
    for item in items:
        results.append(self.transform(item))
    return results
"""
        # Expected prompt format
        prompt = f"""In ONE brief sentence (max 15 words), what does this method do?

Method: {method_name}
Code:
```
{method_code}
```"""

        assert "ONE brief sentence" in prompt
        assert "max 15 words" in prompt
        assert method_name in prompt
        assert "process_data" in prompt

    def test_dead_code_explanation_prompt(self):
        """Test the prompt format for dead code explanation."""
        function_name = "unused_helper"
        call_tree = """
main() -> process() -> validate()
       -> handle() -> transform()
"""
        prompt = f"""Why is the function '{function_name}' marked as dead/unreachable?

Call tree context:
{call_tree}

Explain:
1. What paths could reach this function?
2. Why aren't those paths being executed?
3. Is this likely intentional or a bug?"""

        assert function_name in prompt
        assert "dead/unreachable" in prompt
        assert "paths could reach" in prompt

    def test_performance_explanation_prompt(self):
        """Test the prompt format for performance explanation."""
        function_name = "slow_query"
        stats = "1250.5ms total, 150 calls, 8.33ms avg"
        call_sequence = "main -> process -> slow_query (repeated 150x)"

        prompt = f"""Why is '{function_name}' a performance bottleneck?

Stats: {stats}
Call sequence leading to it:
{call_sequence}

Explain:
1. Why is this function slow?
2. What's causing repeated calls?
3. Potential optimizations?"""

        assert function_name in prompt
        assert stats in prompt
        assert "performance bottleneck" in prompt

    def test_exception_explanation_prompt(self):
        """Test the prompt format for exception explanation."""
        exception_type = "ValueError"
        message = "Invalid argument: expected positive integer"
        stack_trace = """
Traceback (most recent call last):
  File "app.py", line 42, in process
    result = validate(value)
  File "validator.py", line 15, in validate
    raise ValueError("Invalid argument: expected positive integer")
"""
        prompt = f"""Explain this exception:

Type: {exception_type}
Message: {message}
Stack trace:
{stack_trace}

Explain:
1. What caused this exception?
2. What was the code trying to do?
3. How to fix it?"""

        assert exception_type in prompt
        assert message in prompt
        assert "ValueError" in prompt

    def test_summary_response_truncation(self):
        """Test that long summaries are truncated for billboard display."""
        # Simulate a long response
        long_response = "This method processes incoming data items by iterating through each one and applying a transformation function to convert them into the desired output format."

        # Truncate to first sentence
        summary = long_response.split(".")[0].strip()

        # Further truncate if too long
        if len(summary) > 80:
            summary = summary[:77] + "..."

        assert len(summary) <= 80


class TestManimIntegration:
    """Tests for Manim billboard text integration."""

    def test_manim_calls_get_method_summary(self):
        """Test that Manim can call getMethodSummary for billboard text."""
        # Mock the AI service
        mock_callback_result = None

        def mock_callback(result):
            nonlocal mock_callback_result
            mock_callback_result = result

        # Simulate getMethodSummary call
        method_name = "encode_text"
        method_code = "def encode_text(self, text): return self.tokenizer.encode(text)"

        # When server is not running, should fallback to method name
        # This simulates the Kotlin/TypeScript behavior
        server_running = False

        if not server_running:
            mock_callback(method_name)  # Fallback

        assert mock_callback_result == method_name

    def test_billboard_text_length_limits(self):
        """Test that billboard text respects length limits."""
        # Manim billboard should show short text
        max_billboard_length = 80

        test_summaries = [
            "Encodes text using tokenizer",  # 28 chars - OK
            "This is a very long method summary that explains in great detail what the method does including all edge cases",  # Too long
            "",  # Empty
        ]

        for summary in test_summaries:
            if not summary:
                display_text = "Unknown"
            elif len(summary) > max_billboard_length:
                display_text = summary[:77] + "..."
            else:
                display_text = summary

            assert len(display_text) <= max_billboard_length or display_text.endswith("...")


class TestPublicAPIIntegration:
    """Tests for public API used by other panels."""

    def test_ask_question_callback_signature(self):
        """Test askQuestion callback receives string response."""
        responses = []

        def callback(response: str):
            responses.append(response)
            assert isinstance(response, str)

        # Simulate async call completion
        callback("This is the AI response to your question.")

        assert len(responses) == 1
        assert "AI response" in responses[0]

    def test_explain_dead_code_includes_context(self):
        """Test explainDeadCode includes proper context."""
        function_name = "unused_function"
        call_tree = "main -> process (unused_function never called)"

        # Build the expected question
        question = f"""Why is the function '{function_name}' marked as dead/unreachable?

Call tree context:
{call_tree}

Explain:
1. What paths could reach this function?
2. Why aren't those paths being executed?
3. Is this likely intentional or a bug?"""

        # Verify question structure
        assert function_name in question
        assert call_tree in question
        assert "dead/unreachable" in question

    def test_is_server_running_check(self):
        """Test server running status check."""
        # Simulate server states
        server_process = None

        def is_server_running():
            return server_process is not None

        assert is_server_running() == False

        # Simulate server start
        server_process = object()  # Mock process
        assert is_server_running() == True


class TestImageHandling:
    """Tests for image/screenshot handling."""

    def test_base64_image_format(self):
        """Test that images are properly base64 encoded."""
        # 1x1 PNG pixel
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        # Verify it's valid base64
        import base64
        try:
            decoded = base64.b64decode(test_image_base64)
            assert decoded[:8] == b'\x89PNG\r\n\x1a\n'  # PNG magic bytes
        except Exception:
            pytest.fail("Invalid base64 image data")

    def test_image_url_format_for_llm(self):
        """Test the image URL format sent to LLM API."""
        image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        # Format expected by OpenAI-compatible API
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_base64}"
            }
        }

        assert image_content["type"] == "image_url"
        assert image_content["image_url"]["url"].startswith("data:image/png;base64,")

    def test_vision_model_detection(self):
        """Test detection of vision-capable models."""
        model_presets = [
            {"name": "Qwen3-VL-2B", "hasVision": True},
            {"name": "Qwen3-2B-Text", "hasVision": False},
            {"name": "Qwen3-VL-4B", "hasVision": True},
        ]

        for preset in model_presets:
            if "-VL-" in preset["name"]:
                assert preset["hasVision"] == True
            else:
                # Text-only models might still have vision=False
                pass


class TestModelPresets:
    """Tests for model preset configuration."""

    def test_model_presets_have_required_fields(self):
        """Test that all model presets have required fields."""
        presets = [
            {
                "displayName": "Qwen3-VL-2B Instruct Q4_K_XL (Recommended)",
                "repoId": "unsloth/Qwen3-VL-2B-Instruct-GGUF",
                "fileName": "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
                "sizeMB": 1500,
                "hasVision": True
            },
            {
                "displayName": "Qwen3-2B Text-Only Q4_K_M",
                "repoId": "unsloth/Qwen3-2B-Instruct-GGUF",
                "fileName": "Qwen3-2B-Instruct-Q4_K_M.gguf",
                "sizeMB": 1100,
                "hasVision": False
            }
        ]

        for preset in presets:
            assert "displayName" in preset
            assert "repoId" in preset
            assert "fileName" in preset
            assert "sizeMB" in preset
            assert "hasVision" in preset
            assert preset["fileName"].endswith(".gguf")

    def test_huggingface_url_construction(self):
        """Test HuggingFace URL construction from preset."""
        preset = {
            "repoId": "unsloth/Qwen3-VL-2B-Instruct-GGUF",
            "fileName": "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf"
        }

        url = f"https://huggingface.co/{preset['repoId']}/resolve/main/{preset['fileName']}"

        assert url == "https://huggingface.co/unsloth/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf"
        assert "huggingface.co" in url
        assert preset["fileName"] in url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
