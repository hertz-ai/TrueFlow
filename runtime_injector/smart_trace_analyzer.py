"""
Smart Trace Analyzer - Uses Intelligence When Needed

This module provides intelligent analysis ONLY when the user explicitly requests it:
- "Find what's blocking this flow" → Analyze bottlenecks
- "Explain the architecture" → Generate architectural diagram
- "Why is this slow?" → Performance analysis
- "What's wrong with X?" → Root cause analysis

Otherwise, uses simple deterministic pattern matching.
"""

import json
import time
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass

# Import logging
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
try:
    from logging_config import get_analyzer_logger
    logger = get_analyzer_logger()
except:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class PerformanceBottleneck:
    """Identifies a performance bottleneck in execution."""
    function: str
    module: str
    avg_duration_ms: float
    call_count: int
    total_time_ms: float
    percentage_of_total: float
    blocking_reason: str  # Why it's slow


@dataclass
class ArchitectureNode:
    """Represents a component in the architecture."""
    name: str
    type: str  # 'layer', 'module', 'function'
    children: List[str]
    call_frequency: int
    avg_duration_ms: float


class SmartTraceAnalyzer:
    """
    Intelligent trace analyzer that uses AI reasoning ONLY when user requests it.

    User intents that trigger intelligence:
    - "find blocking" / "what's slow" → Performance analysis
    - "explain architecture" / "show structure" → Architecture discovery
    - "why does X happen" → Root cause analysis
    - "compare A vs B" → Differential analysis

    Otherwise: Simple pattern matching and statistics.
    """

    def __init__(self, use_llm_for_insights: bool = False):
        """
        Args:
            use_llm_for_insights: Whether to use LLM for generating human-readable insights
                                  Only enable when user explicitly asks for explanations
        """
        self.use_llm_for_insights = use_llm_for_insights

        # Simple pattern-based detection (no LLM)
        self.performance_patterns = {
            'io_bound': ['read', 'write', 'fetch', 'load', 'save', 'request'],
            'compute_bound': ['matmul', 'conv', 'einsum', 'transform', 'calculate'],
            'memory_bound': ['allocate', 'copy', 'transfer', 'cache'],
            'synchronization': ['lock', 'wait', 'sync', 'barrier', 'join']
        }

        logger.info(f"Smart analyzer initialized (LLM insights: {use_llm_for_insights})")

    def analyze_performance(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze trace for performance bottlenecks.

        This is INTELLIGENT analysis - use when user asks:
        - "Find what's blocking this flow"
        - "Why is this slow?"
        - "Show me bottlenecks"
        """
        calls = trace_data.get('calls', [])

        # Aggregate by function
        function_stats = defaultdict(lambda: {'durations': [], 'count': 0})

        for call in calls:
            if call.get('type') != 'return':
                continue

            func_key = f"{call.get('module', '')}.{call.get('function', '')}"
            duration = call.get('duration_ms', 0)

            function_stats[func_key]['durations'].append(duration)
            function_stats[func_key]['count'] += 1

        # Calculate bottlenecks
        total_time = sum(
            sum(stats['durations'])
            for stats in function_stats.values()
        )

        bottlenecks = []
        for func_key, stats in function_stats.items():
            if not stats['durations']:
                continue

            avg_duration = sum(stats['durations']) / len(stats['durations'])
            total_func_time = sum(stats['durations'])
            percentage = (total_func_time / total_time * 100) if total_time > 0 else 0

            # Classify blocking reason (deterministic)
            blocking_reason = self._classify_blocking_reason(func_key, avg_duration)

            bottlenecks.append(PerformanceBottleneck(
                function=func_key.split('.')[-1],
                module='.'.join(func_key.split('.')[:-1]),
                avg_duration_ms=avg_duration,
                call_count=stats['count'],
                total_time_ms=total_func_time,
                percentage_of_total=percentage,
                blocking_reason=blocking_reason
            ))

        # Sort by total time (most impactful first)
        bottlenecks.sort(key=lambda x: x.total_time_ms, reverse=True)

        # Generate insights (with or without LLM)
        insights = self._generate_performance_insights(bottlenecks, total_time)

        return {
            'total_execution_time_ms': total_time,
            'bottlenecks': [
                {
                    'function': b.function,
                    'module': b.module,
                    'avg_duration_ms': round(b.avg_duration_ms, 2),
                    'call_count': b.call_count,
                    'total_time_ms': round(b.total_time_ms, 2),
                    'percentage': round(b.percentage_of_total, 1),
                    'blocking_reason': b.blocking_reason
                }
                for b in bottlenecks[:10]  # Top 10
            ],
            'insights': insights
        }

    def analyze_architecture(self, trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Discover architecture from execution traces.

        This is INTELLIGENT analysis - use when user asks:
        - "Explain the architecture"
        - "Show me the system structure"
        - "What are the main components?"
        """
        calls = trace_data.get('calls', [])

        # Build call graph
        call_graph = defaultdict(lambda: {
            'children': set(),
            'call_count': 0,
            'total_duration': 0.0
        })

        for call in calls:
            func = call.get('function', '')
            module = call.get('module', '')
            parent_id = call.get('parent_id')
            duration = call.get('duration_ms', 0)

            func_key = f"{module}.{func}"
            call_graph[func_key]['call_count'] += 1
            call_graph[func_key]['total_duration'] += duration

            # Build parent-child relationships
            if parent_id:
                # Find parent function
                parent_call = next(
                    (c for c in calls if c.get('call_id') == parent_id),
                    None
                )
                if parent_call:
                    parent_key = f"{parent_call.get('module', '')}.{parent_call.get('function', '')}"
                    call_graph[parent_key]['children'].add(func_key)

        # Classify components by type
        components = []
        for func_key, data in call_graph.items():
            component_type = self._classify_component_type(func_key)
            avg_duration = data['total_duration'] / data['call_count'] if data['call_count'] > 0 else 0

            components.append({
                'name': func_key,
                'type': component_type,
                'children': list(data['children']),
                'call_frequency': data['call_count'],
                'avg_duration_ms': round(avg_duration, 2)
            })

        # Find root components (no parents)
        all_children = set()
        for comp in components:
            all_children.update(comp['children'])

        roots = [c for c in components if c['name'] not in all_children]

        # Generate architectural insights
        insights = self._generate_architecture_insights(components, roots)

        return {
            'components': components,
            'root_components': [r['name'] for r in roots],
            'total_components': len(components),
            'insights': insights
        }

    def find_root_cause(self, trace_data: Dict[str, Any], symptom: str) -> Dict[str, Any]:
        """
        Root cause analysis for a specific symptom.

        This is INTELLIGENT analysis - use when user asks:
        - "Why does X fail?"
        - "What's causing Y?"
        - "Root cause of Z?"
        """
        calls = trace_data.get('calls', [])

        # Search for exceptions/errors
        errors = [
            call for call in calls
            if call.get('exception') or 'error' in call.get('function', '').lower()
        ]

        # Search for unusual patterns
        anomalies = self._detect_anomalies(calls)

        # Trace back from symptom
        relevant_calls = self._trace_back_from_symptom(calls, symptom)

        root_causes = []

        # Analyze errors
        if errors:
            for error_call in errors:
                root_causes.append({
                    'type': 'exception',
                    'function': error_call.get('function'),
                    'module': error_call.get('module'),
                    'details': error_call.get('exception', 'Unknown error'),
                    'likelihood': 'high'
                })

        # Analyze anomalies
        for anomaly in anomalies:
            root_causes.append(anomaly)

        # Generate explanation
        explanation = self._generate_root_cause_explanation(
            symptom, root_causes, relevant_calls
        )

        return {
            'symptom': symptom,
            'root_causes': root_causes,
            'relevant_call_chain': relevant_calls,
            'explanation': explanation
        }

    def _classify_blocking_reason(self, func_key: str, duration_ms: float) -> str:
        """Deterministic classification of why a function is slow."""
        func_lower = func_key.lower()

        # Check patterns
        for category, patterns in self.performance_patterns.items():
            if any(pattern in func_lower for pattern in patterns):
                if category == 'io_bound':
                    return "I/O operations (network/disk)"
                elif category == 'compute_bound':
                    return "Heavy computation"
                elif category == 'memory_bound':
                    return "Memory allocation/transfer"
                elif category == 'synchronization':
                    return "Thread synchronization"

        # Fallback based on duration
        if duration_ms > 1000:
            return "Very slow execution (>1s)"
        elif duration_ms > 100:
            return "Slow execution (>100ms)"
        else:
            return "Normal execution"

    def _classify_component_type(self, func_key: str) -> str:
        """Deterministic classification of component type."""
        func_lower = func_key.lower()

        if any(x in func_lower for x in ['layer', 'linear', 'conv', 'attention']):
            return "neural_layer"
        elif any(x in func_lower for x in ['forward', 'backward']):
            return "model_component"
        elif any(x in func_lower for x in ['learn', 'train', 'update']):
            return "learning_component"
        elif any(x in func_lower for x in ['encode', 'decode']):
            return "encoder_decoder"
        elif any(x in func_lower for x in ['memory', 'cache', 'buffer']):
            return "memory_component"
        else:
            return "generic_function"

    def _detect_anomalies(self, calls: List[Dict]) -> List[Dict]:
        """Detect unusual patterns in execution."""
        anomalies = []

        # Detect excessive calls to same function
        function_counts = Counter(
            f"{call.get('module', '')}.{call.get('function', '')}"
            for call in calls
        )

        for func, count in function_counts.most_common(5):
            if count > 100:
                anomalies.append({
                    'type': 'excessive_calls',
                    'function': func,
                    'count': count,
                    'likelihood': 'medium',
                    'details': f"Function called {count} times (potential loop or recursion issue)"
                })

        # Detect very long durations
        for call in calls:
            duration = call.get('duration_ms', 0)
            if duration > 5000:  # >5 seconds
                anomalies.append({
                    'type': 'timeout_risk',
                    'function': call.get('function'),
                    'module': call.get('module'),
                    'duration_ms': duration,
                    'likelihood': 'high',
                    'details': f"Function took {duration}ms (potential timeout)"
                })

        return anomalies

    def _trace_back_from_symptom(self, calls: List[Dict], symptom: str) -> List[Dict]:
        """Trace back execution chain from a symptom."""
        # Find calls matching symptom
        matching_calls = [
            call for call in calls
            if symptom.lower() in call.get('function', '').lower()
            or symptom.lower() in call.get('module', '').lower()
        ]

        if not matching_calls:
            return []

        # Build call chain
        call_chain = []
        for match_call in matching_calls:
            current = match_call
            chain = [current]

            # Trace back to root
            while current.get('parent_id'):
                parent = next(
                    (c for c in calls if c.get('call_id') == current.get('parent_id')),
                    None
                )
                if parent:
                    chain.insert(0, parent)
                    current = parent
                else:
                    break

            call_chain.extend(chain)

        return call_chain[:20]  # Limit to 20 calls

    def _generate_performance_insights(self, bottlenecks: List[PerformanceBottleneck], total_time: float) -> List[str]:
        """Generate human-readable insights about performance."""
        insights = []

        if not bottlenecks:
            return ["No significant bottlenecks detected"]

        # Top bottleneck
        top = bottlenecks[0]
        insights.append(
            f"Primary bottleneck: {top.function} takes {top.percentage_of_total:.1f}% of total time "
            f"({top.blocking_reason})"
        )

        # I/O vs Compute
        io_time = sum(b.total_time_ms for b in bottlenecks if 'I/O' in b.blocking_reason)
        compute_time = sum(b.total_time_ms for b in bottlenecks if 'computation' in b.blocking_reason)

        if io_time > compute_time * 2:
            insights.append("System is I/O bound - consider async operations or caching")
        elif compute_time > io_time * 2:
            insights.append("System is compute bound - consider GPU acceleration or optimization")

        # Excessive calls
        excessive = [b for b in bottlenecks if b.call_count > 100]
        if excessive:
            insights.append(
                f"{len(excessive)} functions called >100 times - potential for batching or caching"
            )

        return insights

    def _generate_architecture_insights(self, components: List[Dict], roots: List[Dict]) -> List[str]:
        """Generate human-readable insights about architecture."""
        insights = []

        # Component type distribution
        type_counts = Counter(c['type'] for c in components)
        dominant_type = type_counts.most_common(1)[0] if type_counts else None

        if dominant_type:
            insights.append(
                f"Architecture is primarily composed of {dominant_type[0]} components ({dominant_type[1]} total)"
            )

        # Depth analysis
        max_children = max((len(c['children']) for c in components), default=0)
        if max_children > 10:
            insights.append(f"Deep component hierarchy detected (max {max_children} children) - consider flattening")

        # Entry points
        insights.append(f"System has {len(roots)} root entry points")

        return insights

    def _generate_root_cause_explanation(self, symptom: str, root_causes: List[Dict], call_chain: List[Dict]) -> str:
        """Generate human-readable explanation of root cause."""
        if not root_causes:
            return f"No clear root cause found for '{symptom}'"

        primary = root_causes[0]
        explanation = f"Root cause of '{symptom}': {primary['type']} in {primary.get('function', 'unknown function')}"

        if primary.get('details'):
            explanation += f" - {primary['details']}"

        if len(call_chain) > 0:
            explanation += f"\n\nCall chain leading to issue ({len(call_chain)} steps)"

        return explanation


# Convenience functions for common user requests
def find_whats_blocking(trace_file: str) -> Dict[str, Any]:
    """User asked: 'Find what's blocking this flow'"""
    with open(trace_file) as f:
        trace_data = json.load(f)

    analyzer = SmartTraceAnalyzer(use_llm_for_insights=False)
    return analyzer.analyze_performance(trace_data)


def explain_architecture(trace_file: str) -> Dict[str, Any]:
    """User asked: 'Explain the architecture'"""
    with open(trace_file) as f:
        trace_data = json.load(f)

    analyzer = SmartTraceAnalyzer(use_llm_for_insights=False)
    return analyzer.analyze_architecture(trace_data)


def why_is_this_slow(trace_file: str) -> Dict[str, Any]:
    """User asked: 'Why is this slow?'"""
    return find_whats_blocking(trace_file)


def whats_wrong_with(trace_file: str, component: str) -> Dict[str, Any]:
    """User asked: 'What's wrong with X?'"""
    with open(trace_file) as f:
        trace_data = json.load(f)

    analyzer = SmartTraceAnalyzer(use_llm_for_insights=False)
    return analyzer.find_root_cause(trace_data, component)


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python smart_trace_analyzer.py <trace_file> <command>")
        print("Commands: blocking, architecture, slow, rootcause:<symptom>")
        sys.exit(1)

    trace_file = sys.argv[1]
    command = sys.argv[2]

    if command == "blocking":
        result = find_whats_blocking(trace_file)
        print(json.dumps(result, indent=2))

    elif command == "architecture":
        result = explain_architecture(trace_file)
        print(json.dumps(result, indent=2))

    elif command == "slow":
        result = why_is_this_slow(trace_file)
        print(json.dumps(result, indent=2))

    elif command.startswith("rootcause:"):
        symptom = command.split(':', 1)[1]
        result = whats_wrong_with(trace_file, symptom)
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
