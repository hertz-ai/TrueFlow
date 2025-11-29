from logging_config import setup_logger
logger = setup_logger(__name__)

"""
LLM-Powered Concept Explainer for Visualization

Uses locally hosted LLM (Qwen-VL via API) to:
1. Analyze code execution patterns from traces
2. Generate natural language explanations of what's happening
3. Identify key concepts that need visual explanation
4. Generate context-aware narration for visualizations
5. Explain WHY things are happening, not just WHAT

This makes visualizations INTELLIGENT TEACHING TOOLS, not just eye candy.
"""

import json
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ConceptExplanation:
    """An explanation of a concept with visual hints."""
    concept: str
    explanation: str
    why_it_matters: str
    visual_metaphor: str
    common_mistakes: List[str]
    related_concepts: List[str]


class LocalLLMExplainer:
    """
    Uses locally hosted LLM to generate intelligent explanations.

    Connects to: http://localhost:8000/v1/chat/completions
    Model: Qwen3-VL-2B-Instruct (or any OpenAI-compatible endpoint)
    """

    def __init__(self, api_base="http://localhost:8000/v1"):
        self.api_base = api_base
        self.model = "Qwen3-VL-2B-Instruct"

    def analyze_execution_pattern(self, trace_data: Dict) -> str:
        """
        Ask LLM: "What is this code trying to do?"

        Returns high-level explanation of execution pattern.
        """
        calls = trace_data.get('calls', [])

        # Build context from trace
        function_names = [c.get('function', '') for c in calls if c.get('type') == 'call']
        modules = list(set(c.get('module', '') for c in calls if c.get('module')))

        prompt = f"""Analyze this code execution pattern and explain what it's doing:

Functions called: {', '.join(function_names[:20])}
Modules involved: {', '.join(modules[:10])}

In 2-3 sentences, explain:
1. What is the high-level purpose of this code?
2. What pattern is it following (e.g., pipeline, recursion, state machine)?
3. Why would someone write code like this?

Be specific and technical. Focus on the WHY, not just the WHAT."""

        response = self._call_llm(prompt)
        return response

    def explain_concept(self, concept_name: str, context: Dict) -> ConceptExplanation:
        """
        Ask LLM: "Explain this concept in the context of this specific code."

        Returns detailed explanation with visual hints.
        """
        prompt = f"""Explain the concept of "{concept_name}" in the context of this code execution:

Context:
{json.dumps(context, indent=2)[:500]}

Provide:
1. EXPLANATION: What is {concept_name}? (2 sentences, technical)
2. WHY IT MATTERS: Why is this important here? (1 sentence)
3. VISUAL METAPHOR: How would you visualize this? (1 sentence, concrete visual description)
4. COMMON MISTAKES: What do developers get wrong? (2-3 bullet points)
5. RELATED CONCEPTS: What else should I know? (2-3 related terms)

Be specific to THIS CODE, not generic textbook definitions."""

        response = self._call_llm(prompt)

        # Parse response into structured format
        explanation = self._parse_concept_explanation(response, concept_name)
        return explanation

    def explain_bottleneck(self, function_name: str, duration: float, context: Dict) -> str:
        """
        Ask LLM: "Why is this function slow?"

        Returns explanation of performance issue with suggestions.
        """
        prompt = f"""This function is a performance bottleneck:

Function: {function_name}
Duration: {duration:.2f} seconds
Context: {json.dumps(context, indent=2)[:300]}

Explain:
1. Why is this function likely slow? (algorithmic complexity, I/O, etc.)
2. What should the developer check? (be specific)
3. What's a quick win optimization?

Be concise and actionable. 3-4 sentences max."""

        response = self._call_llm(prompt)
        return response

    def explain_error_propagation(self, error_path: List[str]) -> str:
        """
        Ask LLM: "How did this error propagate through the system?"

        Returns explanation of error flow.
        """
        prompt = f"""An error propagated through these functions:

Error path: {' → '.join(error_path)}

Explain:
1. Where did the error ORIGINATE?
2. Why did it propagate instead of being caught?
3. Where should error handling be added?

Be specific about the root cause. 3 sentences."""

        response = self._call_llm(prompt)
        return response

    def explain_architecture_pattern(self, layers: List[List[str]], dependencies: List[Tuple[str, str, int]]) -> str:
        """
        Ask LLM: "What architectural pattern does this follow?"

        Returns explanation of discovered architecture.
        """
        prompt = f"""This codebase has the following runtime architecture:

Layers (bottom to top): {[len(layer) for layer in layers]} modules per layer
Top dependencies: {[(src, dst, count) for src, dst, count in dependencies[:10]]}

Explain:
1. What architectural pattern is this? (layered, microservices, monolith, etc.)
2. Is this a good or bad architecture? Why?
3. What's the biggest architectural smell?

Be honest and direct. 3-4 sentences."""

        response = self._call_llm(prompt)
        return response

    def generate_narration_for_visualization(self, scene_type: str, key_points: List[str]) -> List[str]:
        """
        Ask LLM: "Generate narration for this visualization."

        Returns list of narration lines to display during animation.
        """
        prompt = f"""Generate narration for a {scene_type} visualization showing:

{chr(10).join(f'- {point}' for point in key_points)}

Create 3-5 narration lines that:
1. Explain what's happening (not just describing visuals)
2. Use analogies and metaphors
3. Connect to real-world programming experience
4. Focus on WHY, not just WHAT

Each line should be 10-15 words, clear and conversational."""

        response = self._call_llm(prompt)

        # Split into individual lines
        lines = [line.strip() for line in response.split('\n') if line.strip() and not line.strip().startswith('#')]
        return lines[:5]

    def explain_data_flow(self, from_func: str, to_func: str, data_type: str, value: Optional[str] = None) -> str:
        """
        Ask LLM: "What does this data represent and why is it flowing here?"

        Returns explanation of data semantics.
        """
        prompt = f"""Data is flowing from {from_func} to {to_func}:

Type: {data_type}
Value: {value if value else 'unknown'}

In 1-2 sentences, explain:
1. What does this data MEAN semantically?
2. WHY is it being passed to {to_func}?

Be specific, not generic."""

        response = self._call_llm(prompt)
        return response

    def explain_why_operation_exists(self, operation: str, context: Dict) -> str:
        """
        Ask LLM: "Why does this operation exist in the code?"

        Returns explanation of purpose/motivation.
        """
        prompt = f"""This operation appears in the code:

Operation: {operation}
Context: {json.dumps(context, indent=2)[:300]}

In 1-2 sentences, explain:
1. WHY does this operation exist?
2. What would break if it was removed?

Focus on the PURPOSE, not the mechanism."""

        response = self._call_llm(prompt)
        return response

    def suggest_visual_metaphor(self, concept: str, technical_details: str) -> str:
        """
        Ask LLM: "What's a good visual metaphor for this concept?"

        Returns concrete visual metaphor for animation.
        """
        prompt = f"""Suggest a visual metaphor for this concept:

Concept: {concept}
Technical: {technical_details}

Describe a concrete, visual metaphor that would help someone understand this.
Use real-world objects (e.g., "like water flowing through pipes").
1-2 sentences, very visual and concrete."""

        response = self._call_llm(prompt)
        return response

    def _call_llm(self, prompt: str, max_tokens: int = 256) -> str:
        """Call local LLM API."""
        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a programming expert who explains code clearly and concisely. Focus on WHY things happen, not just WHAT. Use analogies. Be direct."},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip()
            else:
                return f"[LLM Error: {response.status_code}]"

        except Exception as e:
            return f"[LLM Unavailable: {str(e)}]"

    def _parse_concept_explanation(self, response: str, concept_name: str) -> ConceptExplanation:
        """Parse LLM response into structured explanation."""
        lines = response.split('\n')

        explanation = ""
        why_it_matters = ""
        visual_metaphor = ""
        common_mistakes = []
        related_concepts = []

        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if 'EXPLANATION' in line.upper() or 'WHAT IS' in line.upper():
                current_section = 'explanation'
            elif 'WHY IT MATTERS' in line.upper() or 'IMPORTANT' in line.upper():
                current_section = 'why'
            elif 'VISUAL METAPHOR' in line.upper() or 'VISUALIZE' in line.upper():
                current_section = 'visual'
            elif 'COMMON MISTAKES' in line.upper() or 'WRONG' in line.upper():
                current_section = 'mistakes'
            elif 'RELATED CONCEPTS' in line.upper() or 'RELATED' in line.upper():
                current_section = 'related'
            elif current_section == 'explanation' and not line.startswith('-'):
                explanation += line + " "
            elif current_section == 'why' and not line.startswith('-'):
                why_it_matters += line + " "
            elif current_section == 'visual' and not line.startswith('-'):
                visual_metaphor += line + " "
            elif current_section == 'mistakes' and line.startswith('-'):
                common_mistakes.append(line[1:].strip())
            elif current_section == 'related' and line.startswith('-'):
                related_concepts.append(line[1:].strip())

        return ConceptExplanation(
            concept=concept_name,
            explanation=explanation.strip() or response[:200],
            why_it_matters=why_it_matters.strip() or "Context-specific importance",
            visual_metaphor=visual_metaphor.strip() or "Visual representation needed",
            common_mistakes=common_mistakes or ["Context-specific mistakes"],
            related_concepts=related_concepts or ["Context-specific concepts"]
        )


# Singleton instance
_explainer = None

def get_llm_explainer() -> LocalLLMExplainer:
    """Get singleton LLM explainer instance."""
    global _explainer
    if _explainer is None:
        _explainer = LocalLLMExplainer()
    return _explainer


if __name__ == "__main__":
    # Test LLM explainer
    explainer = LocalLLMExplainer()

    # Test execution pattern analysis
    test_trace = {
        'calls': [
            {'type': 'call', 'function': 'forward', 'module': 'neural_network'},
            {'type': 'call', 'function': 'attention', 'module': 'transformer'},
            {'type': 'call', 'function': 'softmax', 'module': 'ops'},
        ]
    }

    logger.info("=== Execution Pattern Analysis ===")
    pattern = explainer.analyze_execution_pattern(test_trace)
    logger.info(pattern)

    logger.info("\n=== Concept Explanation ===")
    concept = explainer.explain_concept("attention mechanism", {"model": "transformer", "layer": "encoder"})
    logger.info(f"Concept: {concept.concept}")
    logger.info(f"Explanation: {concept.explanation}")
    logger.info(f"Why: {concept.why_it_matters}")
    logger.info(f"Visual: {concept.visual_metaphor}")

    logger.info("\n=== Bottleneck Explanation ===")
    bottleneck = explainer.explain_bottleneck("attention_forward", 2.5, {"batch_size": 32, "seq_len": 1024})
    logger.info(bottleneck)

    logger.info("\n=== Narration Generation ===")
    narration = explainer.generate_narration_for_visualization(
        "neural_network_forward_pass",
        ["Data enters input layer", "Attention weights computed", "Output generated"]
    )
    for line in narration:
        logger.info(f"- {line}")
