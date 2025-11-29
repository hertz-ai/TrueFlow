"""
LLM-based Dynamic Operation Mapper

This module provides intelligent, language-agnostic operation detection using LLM reasoning.
When pattern matching fails to identify an operation type, this mapper uses semantic understanding
to classify operations across different programming languages and frameworks.
"""

import json
import re
import time
import requests
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from threading import Lock

# Import logging configuration
from logging_config import get_llm_mapper_logger

# Initialize logger
logger = get_llm_mapper_logger()


@dataclass
class OperationHint:
    """Semantic hints about an operation extracted from trace data."""
    function_name: str
    module_name: str
    parameters: List[str]
    return_type: Optional[str]
    context: str  # Surrounding code context if available

    def to_prompt(self) -> str:
        """Convert hints to LLM prompt."""
        return f"""Analyze this code operation and classify it into ONE of these categories:

CATEGORIES:
- neural_layer: Neural network layer forward pass (linear, conv, activation, etc.)
- attention: Attention mechanism (self-attention, cross-attention, multi-head)
- convolution: Convolution operation (1D, 2D, 3D)
- batch_norm: Batch normalization or layer normalization
- array_reshape: Tensor/array reshaping (reshape, view, transpose, permute)
- matrix_multiply: Matrix multiplication (matmul, dot product, @)
- broadcasting: Broadcasting operation (expand, broadcast_to)
- async_operation: Asynchronous operation (async/await, threading, multiprocessing)
- nested_call: Nested function call (recursion, deep call stack)
- memory_write: Memory write operation (cache write, store, set)
- memory_read: Memory read operation (cache read, load, get)
- memory_update: Memory update operation (update, modify)
- control_flow: Control flow (if/else, switch, loops)
- data_flow: Simple data passing between operations
- method_call: Generic method/function call

OPERATION DETAILS:
Function: {self.function_name}
Module: {self.module_name}
Parameters: {', '.join(self.parameters) if self.parameters else 'None'}
Return Type: {self.return_type or 'Unknown'}
Context: {self.context or 'Not available'}

INSTRUCTIONS:
1. Consider the semantic meaning, not just keywords
2. Be language-agnostic (works for Python, Java, C++, JavaScript, etc.)
3. Focus on WHAT the operation does, not HOW it's named
4. Return ONLY the category name, nothing else

CATEGORY:"""


class LLMOperationMapper:
    """
    Intelligent operation mapper using LLM reasoning.

    This mapper provides a fallback when pattern matching fails, using semantic
    understanding to classify operations across different languages and frameworks.
    """

    # Static knowledge base for common patterns (language-agnostic)
    SEMANTIC_PATTERNS = {
        'neural_layer': [
            r'(?i)(forward|backward|layer|activation|relu|sigmoid|tanh|softmax)',
            r'(?i)(dense|linear|fullyconnected|fc\d+)',
        ],
        'attention': [
            r'(?i)(attention|attn|self_attn|cross_attn|multihead|mha)',
            r'(?i)(query|key|value|q_proj|k_proj|v_proj)',
        ],
        'convolution': [
            r'(?i)(conv\d*d|convolution|convolve)',
            r'(?i)(kernel|filter|stride|padding)',
        ],
        'batch_norm': [
            r'(?i)(batch.*norm|layer.*norm|group.*norm|instance.*norm)',
            r'(?i)(bn\d*d|normalize|standardize)',
        ],
        'array_reshape': [
            r'(?i)(reshape|view|resize|transpose|permute|expand_dims)',
            r'(?i)(flatten|squeeze|unsqueeze|ravel)',
        ],
        'matrix_multiply': [
            r'(?i)(matmul|dot|mm|bmm|einsum)',
            r'(?i)(multiply|product).*(?i)(matrix|tensor)',
        ],
        'broadcasting': [
            r'(?i)(broadcast|expand|repeat|tile)',
        ],
        'async_operation': [
            r'(?i)(async|await|promise|future|thread|pool|parallel)',
            r'(?i)(executor|worker|task|coroutine)',
        ],
        'memory_write': [
            r'(?i)(write|store|save|cache|put|set|insert|__setitem__)',
        ],
        'memory_read': [
            r'(?i)(read|load|fetch|get|retrieve|__getitem__)',
        ],
        'memory_update': [
            r'(?i)(update|modify|change|mutate)',
        ],
    }

    def __init__(self, use_llm: bool = False, llm_client = None, llm_backend: str = "local"):
        """
        Initialize the mapper.

        Args:
            use_llm: Whether to use LLM for classification (requires API access)
            llm_client: Optional LLM client (OpenAI, Anthropic, etc.)
            llm_backend: LLM backend to use ("local", "openai", "anthropic")
        """
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.llm_backend = llm_backend
        self.cache = {}  # Cache LLM responses to avoid repeated calls

        # Rate limiting for local model (10 tokens/s, estimate ~100 tokens per request = 1 request per 10s)
        self.rate_limit_lock = Lock()
        self.last_llm_call_time = 0
        self.min_call_interval = 10.0  # seconds (conservative, assuming ~100 tokens per call at 10 tok/s)

        # Local model configuration
        self.local_model_url = "http://localhost:8000/v1/chat/completions"
        self.local_model_name = "Qwen3-VL-2B-Instruct"

    def extract_hints(self, call_data: Dict[str, Any]) -> OperationHint:
        """Extract semantic hints from call data."""
        function = call_data.get('function', '')
        module = call_data.get('module', '')

        # Extract parameter names (if available)
        parameters = []
        if 'args' in call_data:
            parameters.extend([str(arg) for arg in call_data['args']])
        if 'kwargs' in call_data:
            parameters.extend([f"{k}={v}" for k, v in call_data['kwargs'].items()])

        # Extract return type (if available)
        return_type = call_data.get('return_type')

        # Build context
        context_parts = []
        if 'file' in call_data:
            context_parts.append(f"File: {call_data['file']}")
        if 'line' in call_data:
            context_parts.append(f"Line: {call_data['line']}")

        context = ', '.join(context_parts) if context_parts else ''

        return OperationHint(
            function_name=function,
            module_name=module,
            parameters=parameters,
            return_type=return_type,
            context=context
        )

    def classify_with_patterns(self, hints: OperationHint) -> Optional[str]:
        """Classify operation using semantic pattern matching."""
        # Combine all searchable text
        search_text = f"{hints.function_name} {hints.module_name} {' '.join(hints.parameters)}"

        # Score each category
        scores = {}
        for category, patterns in self.SEMANTIC_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, search_text):
                    score += 1
            if score > 0:
                scores[category] = score

        # Return highest scoring category
        if scores:
            return max(scores, key=scores.get)

        return None

    def _call_local_llm(self, prompt: str) -> Optional[str]:
        """Call local Qwen model with rate limiting."""
        with self.rate_limit_lock:
            # Rate limiting: Wait if needed
            current_time = time.time()
            time_since_last_call = current_time - self.last_llm_call_time

            if time_since_last_call < self.min_call_interval:
                wait_time = self.min_call_interval - time_since_last_call
                logger.debug(f"Rate limiting: waiting {wait_time:.1f}s before LLM call...")
                time.sleep(wait_time)

            try:
                response = requests.post(
                    self.local_model_url,
                    json={
                        "model": self.local_model_name,
                        "messages": [
                            {"role": "system", "content": "You are an expert code analyzer. Classify operations accurately. Reply with ONLY the category name."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.0,
                        "max_tokens": 20  # Very short response (just category name)
                    },
                    timeout=30  # 30s timeout (conservative for slow model)
                )

                self.last_llm_call_time = time.time()

                if response.status_code == 200:
                    result = response.json()
                    category = result['choices'][0]['message']['content'].strip().lower()
                    return category
                else:
                    logger.warning(f"Local LLM returned status {response.status_code}")
                    return None

            except Exception as e:
                logger.error(f"Local LLM call failed: {e}")
                return None

    def classify_with_llm(self, hints: OperationHint) -> Optional[str]:
        """Classify operation using LLM reasoning."""
        if not self.use_llm:
            return None

        # Check cache
        cache_key = f"{hints.function_name}:{hints.module_name}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # Generate prompt
            prompt = hints.to_prompt()

            # Call appropriate backend
            if self.llm_backend == "local":
                category = self._call_local_llm(prompt)
            elif self.llm_client:
                # Use provided client (OpenAI, Anthropic, etc.)
                response = self.llm_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an expert code analyzer. Classify operations accurately and concisely."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=20
                )
                category = response.choices[0].message.content.strip().lower()
            else:
                return None

            # Validate category
            valid_categories = set(self.SEMANTIC_PATTERNS.keys()) | {
                'control_flow', 'data_flow', 'method_call'
            }

            if category and category in valid_categories:
                self.cache[cache_key] = category
                return category

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")

        return None

    def classify(self, call_data: Dict[str, Any]) -> str:
        """
        Classify operation type using intelligent mapping.

        Falls back through multiple strategies:
        1. Semantic pattern matching (fast, no API calls)
        2. LLM reasoning (if enabled, slower but accurate)
        3. Default to 'method_call'

        Args:
            call_data: Trace data for the operation

        Returns:
            Operation category name
        """
        # Extract hints
        hints = self.extract_hints(call_data)

        # Try pattern matching first (fast)
        category = self.classify_with_patterns(hints)
        if category:
            return category

        # Try LLM if enabled (slower but more accurate)
        if self.use_llm:
            category = self.classify_with_llm(hints)
            if category:
                return category

        # Default fallback
        return 'method_call'

    def explain_classification(self, call_data: Dict[str, Any], category: str) -> str:
        """Generate human-readable explanation of why operation was classified this way."""
        hints = self.extract_hints(call_data)

        explanation = f"Operation '{hints.function_name}' classified as '{category}'\n"
        explanation += f"Module: {hints.module_name}\n"

        # Find matching patterns
        if category in self.SEMANTIC_PATTERNS:
            search_text = f"{hints.function_name} {hints.module_name}"
            matches = []
            for pattern in self.SEMANTIC_PATTERNS[category]:
                if re.search(pattern, search_text):
                    matches.append(pattern)
            if matches:
                explanation += f"Matched patterns: {', '.join(matches)}\n"

        return explanation


# Example usage and testing
if __name__ == "__main__":
    mapper = LLMOperationMapper(use_llm=False)  # Use pattern matching only

    # Test cases (language-agnostic examples)
    test_cases = [
        # Python
        {"function": "forward", "module": "torch.nn.Linear"},
        {"function": "self_attention", "module": "transformers.modeling"},
        {"function": "conv2d", "module": "tensorflow.nn"},
        {"function": "reshape", "module": "numpy"},
        {"function": "matmul", "module": "torch"},

        # Java
        {"function": "computeAttention", "module": "ai.neural.AttentionLayer"},
        {"function": "forwardPass", "module": "ml.DenseLayer"},

        # JavaScript
        {"function": "convolution", "module": "tfjs.layers"},

        # C++
        {"function": "matrix_multiply", "module": "eigen"},

        # Unknown
        {"function": "process_data", "module": "utils"},
    ]

    logger.info("=== LLM Operation Mapper Test ===")
    for i, test in enumerate(test_cases, 1):
        category = mapper.classify(test)
        logger.info(f"{i}. {test['function']} ({test['module']}) -> {category}")

    logger.info("=== Detailed Explanation Example ===")
    explanation = mapper.explain_classification(test_cases[1], mapper.classify(test_cases[1]))
    logger.info(explanation)
