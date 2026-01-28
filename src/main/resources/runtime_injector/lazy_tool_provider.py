#!/usr/bin/env python3
"""
Lazy Tool Provider - Tiered tool loading for low-throughput LLMs

Instead of sending all 31 tools upfront (2000+ tokens), this provides:
1. A minimal bootstrap (3 tools, ~150 tokens)
2. Category-based tool discovery
3. Full tool coverage without upfront cost

Usage:
    provider = LazyToolProvider(hub_state)

    # Get minimal bootstrap for llama.cpp
    bootstrap_prompt = provider.get_bootstrap_prompt()

    # When LLM requests tools for a category
    tools = provider.get_tools_for_category("analysis")

    # Execute any tool
    result = await provider.execute("analyze_dead_code", {"source_dir": "src"})
"""

import json
from typing import Dict, List, Any, Optional

# Tool categories with descriptions (for classification)
TOOL_CATEGORIES = {
    "greeting": {
        "description": "Simple greetings, chitchat, or questions not needing code analysis",
        "keywords": ["hi", "hello", "hey", "thanks", "bye", "help", "what can you do"],
        "tools": []  # No tools needed
    },
    "trace": {
        "description": "Connecting to trace server, viewing trace events, clearing traces",
        "keywords": ["trace", "connect", "events", "socket", "streaming"],
        "tools": ["trace_connect", "trace_disconnect", "trace_status", "trace_get_events", "trace_clear"]
    },
    "analysis": {
        "description": "Dead code detection, performance analysis, SQL query analysis",
        "keywords": ["dead", "unused", "performance", "slow", "bottleneck", "sql", "n+1", "hotspot"],
        "tools": ["analyze_dead_code", "analyze_performance", "analyze_call_tree", "analyze_sql_queries"]
    },
    "explorer": {
        "description": "Finding callers/callees, searching functions, call chains, code coverage",
        "keywords": ["who calls", "what calls", "callers", "callees", "find", "search", "path", "chain", "coverage"],
        "tools": ["explorer_get_callers", "explorer_get_callees", "explorer_search",
                  "explorer_get_call_chain", "explorer_get_coverage_summary", "explorer_find_path",
                  "explorer_get_function_details", "explorer_get_hot_paths", "explorer_get_call_graph",
                  "explorer_explain_function"]
    },
    "export": {
        "description": "Exporting diagrams (PlantUML, Mermaid), flamegraphs",
        "keywords": ["diagram", "plantuml", "mermaid", "export", "flamegraph", "visualize"],
        "tools": ["export_diagram", "export_flamegraph"]
    },
    "video": {
        "description": "Generating Manim videos, listing videos",
        "keywords": ["video", "manim", "animation", "visualize", "movie"],
        "tools": ["manim_generate_video", "manim_list_videos"]
    },
    "ai": {
        "description": "Starting/stopping AI server, downloading models, AI explanations",
        "keywords": ["ai server", "llama", "model", "download", "explain code", "start server"],
        "tools": ["ai_server_start", "ai_server_stop", "ai_server_status", "ai_download_model", "ai_explain_code"]
    },
    "project": {
        "description": "Project configuration, listing connected IDEs",
        "keywords": ["project", "directory", "config", "ide", "connected"],
        "tools": ["set_project_dir", "get_project_info", "list_projects"]
    }
}

# Full tool definitions (loaded on demand)
TOOL_DEFINITIONS = {
    # Trace tools
    "trace_connect": {"description": "Connect to trace server", "params": {"host": "string", "port": "integer"}},
    "trace_disconnect": {"description": "Disconnect from trace server", "params": {}},
    "trace_status": {"description": "Get trace collection status", "params": {}},
    "trace_get_events": {"description": "Get trace events", "params": {"limit": "integer", "filter_module": "string", "filter_function": "string"}},
    "trace_clear": {"description": "Clear all trace data", "params": {}},

    # Analysis tools
    "analyze_dead_code": {"description": "Find dead/unreachable code", "params": {"source_dir": "string"}},
    "analyze_performance": {"description": "Find performance hotspots", "params": {"sort_by": "string", "limit": "integer"}},
    "analyze_call_tree": {"description": "Generate call tree", "params": {"root_function": "string", "max_depth": "integer"}},
    "analyze_sql_queries": {"description": "Detect SQL N+1 problems", "params": {}},

    # Explorer tools
    "explorer_get_callers": {"description": "Get all callers of a function", "params": {"function_name": "string", "max_depth": "integer"}},
    "explorer_get_callees": {"description": "Get all callees of a function", "params": {"function_name": "string", "max_depth": "integer"}},
    "explorer_search": {"description": "Search functions by name", "params": {"query": "string", "search_type": "string"}},
    "explorer_get_call_chain": {"description": "Get full upstream/downstream call chain", "params": {"function_name": "string"}},
    "explorer_get_coverage_summary": {"description": "Get code coverage summary", "params": {}},
    "explorer_find_path": {"description": "Find call path between two functions", "params": {"source": "string", "target": "string"}},
    "explorer_get_function_details": {"description": "Get detailed function info with metrics", "params": {"function_name": "string"}},
    "explorer_get_hot_paths": {"description": "Get most frequently executed paths", "params": {"limit": "integer"}},
    "explorer_get_call_graph": {"description": "Get full call graph", "params": {"module_filter": "string"}},
    "explorer_explain_function": {"description": "AI explanation of a function", "params": {"function_name": "string"}},

    # Export tools
    "export_diagram": {"description": "Export PlantUML/Mermaid diagram", "params": {"format": "string", "output_file": "string"}},
    "export_flamegraph": {"description": "Export flamegraph JSON for speedscope", "params": {"output_file": "string"}},

    # Video tools
    "manim_generate_video": {"description": "Generate Manim animation", "params": {"trace_file": "string", "quality": "string"}},
    "manim_list_videos": {"description": "List generated videos", "params": {}},

    # AI tools
    "ai_server_start": {"description": "Start llama.cpp server", "params": {"model_path": "string", "port": "integer"}},
    "ai_server_stop": {"description": "Stop AI server", "params": {}},
    "ai_server_status": {"description": "Get AI server status", "params": {}},
    "ai_download_model": {"description": "Download model from HuggingFace", "params": {"model_name": "string"}},
    "ai_explain_code": {"description": "AI explanation with trace context", "params": {"question": "string", "context_type": "string"}},

    # Project tools
    "set_project_dir": {"description": "Set project directory", "params": {"directory": "string"}},
    "get_project_info": {"description": "Get project info", "params": {}},
    "list_projects": {"description": "List connected IDE projects", "params": {}},
}


class LazyToolProvider:
    """Provides tools lazily based on query classification."""

    def __init__(self, tool_executor=None):
        """
        Args:
            tool_executor: Async function that executes tools: executor(name, args) -> result
        """
        self.tool_executor = tool_executor
        self.loaded_categories = set()

    def get_bootstrap_prompt(self) -> str:
        """Get minimal bootstrap prompt for LLM (~200 tokens)."""
        categories_desc = "\n".join(
            f"  - {cat}: {info['description']}"
            for cat, info in TOOL_CATEGORIES.items()
        )

        return f"""You are TrueFlow AI, a code analysis assistant. You have access to tools organized by category.

AVAILABLE CATEGORIES:
{categories_desc}

INSTRUCTIONS:
1. For simple greetings/questions, respond directly without tools
2. For code analysis questions, first determine the category needed
3. Call get_tools(category) to see available tools for that category
4. Then call execute(tool_name, args) to run the tool

FUNCTIONS:
- get_tools(category: string) -> Returns list of tools for that category
- execute(tool_name: string, args: object) -> Runs the tool and returns result
- respond(message: string) -> Send a direct response without tools

Example:
User: "hi" -> respond("Hello! How can I help with code analysis?")
User: "find dead code" -> get_tools("analysis") -> execute("analyze_dead_code", {{}})
User: "who calls step()" -> get_tools("explorer") -> execute("explorer_get_callers", {{"function_name": "step"}})
"""

    def classify_query(self, query: str) -> str:
        """Classify query into a category based on keywords."""
        query_lower = query.lower()

        # Check each category's keywords
        scores = {}
        for cat, info in TOOL_CATEGORIES.items():
            score = sum(1 for kw in info["keywords"] if kw in query_lower)
            if score > 0:
                scores[cat] = score

        if not scores:
            return "greeting"  # Default to greeting if no match

        return max(scores, key=scores.get)

    def get_tools_for_category(self, category: str) -> List[Dict]:
        """Get tool definitions for a category."""
        if category not in TOOL_CATEGORIES:
            return []

        self.loaded_categories.add(category)
        tool_names = TOOL_CATEGORIES[category]["tools"]

        tools = []
        for name in tool_names:
            if name in TOOL_DEFINITIONS:
                defn = TOOL_DEFINITIONS[name]
                tools.append({
                    "name": name,
                    "description": defn["description"],
                    "parameters": defn["params"]
                })

        return tools

    def get_tools_prompt(self, category: str) -> str:
        """Get a prompt describing tools for a category."""
        tools = self.get_tools_for_category(category)
        if not tools:
            return f"No tools needed for '{category}'. Respond directly."

        tools_desc = "\n".join(
            f"  - {t['name']}: {t['description']}\n    Parameters: {json.dumps(t['parameters'])}"
            for t in tools
        )

        return f"""TOOLS FOR '{category.upper()}':
{tools_desc}

Call execute(tool_name, args) to use a tool."""

    def get_all_categories(self) -> Dict[str, str]:
        """Get all category names and descriptions."""
        return {cat: info["description"] for cat, info in TOOL_CATEGORIES.items()}

    def get_token_estimate(self, category: str = None) -> int:
        """Estimate tokens for bootstrap or category tools."""
        if category is None:
            # Bootstrap only
            return 200

        tools = self.get_tools_for_category(category)
        # Rough estimate: 30 tokens per tool definition
        return 200 + len(tools) * 30

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool."""
        if self.tool_executor:
            return await self.tool_executor(tool_name, args)
        return {"error": "No tool executor configured"}


def create_openai_functions_format(category: str) -> List[Dict]:
    """Create OpenAI functions format for a category (for llama.cpp function calling)."""
    tools = []

    if category not in TOOL_CATEGORIES:
        return tools

    for tool_name in TOOL_CATEGORIES[category]["tools"]:
        if tool_name not in TOOL_DEFINITIONS:
            continue

        defn = TOOL_DEFINITIONS[tool_name]

        # Convert to OpenAI function format
        properties = {}
        required = []
        for param_name, param_type in defn["params"].items():
            properties[param_name] = {"type": param_type}
            # Simple heuristic: if no default implied, it's required
            if param_name in ["function_name", "query", "source", "target", "question", "directory"]:
                required.append(param_name)

        tools.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": defn["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })

    return tools


# Convenience function for quick classification
def classify_and_get_tools(query: str) -> tuple:
    """Classify query and return (category, tools_prompt)."""
    provider = LazyToolProvider()
    category = provider.classify_query(query)

    if category == "greeting":
        return category, "Respond directly without tools."

    return category, provider.get_tools_prompt(category)


if __name__ == "__main__":
    # Demo
    provider = LazyToolProvider()

    print("=== Bootstrap Prompt ===")
    print(provider.get_bootstrap_prompt())
    print(f"\nEstimated tokens: {provider.get_token_estimate()}")

    print("\n=== Query Classification ===")
    queries = [
        "hi",
        "find dead code",
        "who calls step()",
        "why is learn_from_reality slow?",
        "export diagram",
        "generate video"
    ]

    for q in queries:
        cat = provider.classify_query(q)
        tokens = provider.get_token_estimate(cat)
        print(f"  '{q}' -> {cat} (~{tokens} tokens)")

    print("\n=== Analysis Tools ===")
    print(provider.get_tools_prompt("analysis"))
