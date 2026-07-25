"""
LangChain orchestration for repository intelligence.

The agent layer owns orchestration only. Repository lookup, graph traversal,
semantic retrieval, and modernization analysis continue to live in the
intelligence modules and are exposed here through thin LangChain tools.
"""

import argparse
import json
import re

try:
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage, HumanMessage
except ImportError:  # pragma: no cover - exercised only without LangChain.
    create_agent = None
    AIMessage = None
    HumanMessage = None

try:
    from .loader import load_repository
    from .repository import Repository
    from .tools import create_repository_tools
except ImportError:
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository
    from repository_intelligence.tools import create_repository_tools


REPOSITORY_AGENT_SYSTEM_PROMPT = """
You are a repository intelligence agent for the Double Commander Pascal
codebase. Use repository tools before answering structural, semantic, or
modernization questions. Prefer exact repository evidence over general software
knowledge. When discussing modernization, identify affected code, dependencies,
impact, equivalent patterns, and migration context before recommending changes.
Keep answers grounded in tool results and call out static-analysis limits.
""".strip()


class RepositoryAgentMemory:
    """
    Minimal message memory for the agent wrapper.

    LangChain's high-level memory APIs vary across versions. Keeping the memory
    object small makes the orchestration layer stable while still allowing the
    compiled LangChain graph to receive prior messages.
    """

    def __init__(self, max_messages=20):
        self.max_messages = max_messages
        self.messages = []

    def add_user_message(self, content):
        if HumanMessage is not None:
            self.messages.append(HumanMessage(content=content))
        else:
            self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_ai_message(self, content):
        if AIMessage is not None:
            self.messages.append(AIMessage(content=content))
        else:
            self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def snapshot(self):
        return list(self.messages)

    def clear(self):
        self.messages = []

    def _trim(self):
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]


class RepositoryIntelligenceAgent:
    """
    Orchestrates repository tools with optional LangChain model execution.

    If a model is supplied, calls are delegated to LangChain's `create_agent`.
    If no model is supplied, `ask()` uses a deterministic tool-selection path
    that is suitable for local validation, tests, and offline development.
    """

    def __init__(
        self,
        repository,
        model=None,
        tools=None,
        system_prompt=REPOSITORY_AGENT_SYSTEM_PROMPT,
        memory=None,
        tool_options=None
    ):
        self.repository = repository
        self.model = model
        self.system_prompt = system_prompt
        self.memory = memory or RepositoryAgentMemory()
        self.tools = tools or create_repository_tools(
            repository,
            **(tool_options or {})
        )
        self.tools_by_name = {
            tool.name: tool
            for tool in self.tools
        }
        self.langchain_agent = None

        if model is not None:
            self.langchain_agent = create_repository_langchain_agent(
                model,
                self.tools,
                system_prompt=system_prompt
            )

    def ask(self, question, mode="auto"):
        """
        Answer a repository question.

        mode:
            auto - use LangChain when a model exists, otherwise deterministic
            langchain - require a model-backed LangChain agent
            deterministic - use local rule-based tool orchestration
        """

        if mode not in {"auto", "langchain", "deterministic"}:
            raise ValueError(f"Unsupported agent mode: {mode}")

        if mode == "langchain" or (
            mode == "auto" and self.langchain_agent is not None
        ):
            return self._ask_langchain(question)

        return self._ask_deterministic(question)

    def _ask_langchain(self, question):
        if self.langchain_agent is None:
            raise RuntimeError("A LangChain model is required for this mode.")

        messages = self.memory.snapshot()
        messages.append(HumanMessage(content=question))
        result = self.langchain_agent.invoke({
            "messages": messages
        })
        answer = self._extract_langchain_answer(result)
        self.memory.add_user_message(question)
        self.memory.add_ai_message(answer)

        return {
            "question": question,
            "mode": "langchain",
            "answer": answer,
            "raw": result
        }

    def _ask_deterministic(self, question):
        tool_name, arguments = self._select_tool(question)
        result = self.tools_by_name[tool_name].invoke(arguments)
        answer = self._summarize_tool_result(tool_name, result)
        self.memory.add_user_message(question)
        self.memory.add_ai_message(answer)

        return {
            "question": question,
            "mode": "deterministic",
            "answer": answer,
            "tool_calls": [
                {
                    "tool": tool_name,
                    "arguments": arguments
                }
            ],
            "result": result
        }

    def _select_tool(self, question):
        lowered = question.casefold()
        symbol = self._extract_symbol(question)

        if any(
            word in lowered
            for word in (
                "modernize",
                "modernise",
                "migration",
                "migrate",
                "convert",
                "java"
            )
        ):
            return "produce_migration_prompt", {
                "task": question,
                "target_language": "Java",
                "limit": 5,
                "graph_depth": 1,
                "include_source": True,
                "max_source_lines": 160,
                "max_source_chars": 12000
            }

        if any(
            word in lowered
            for word in ("impact", "affected", "risk", "blast radius")
        ):
            return "estimate_change_impact", {
                "symbol": symbol,
                "max_depth": 2,
                "limit": 25
            }

        if any(
            word in lowered
            for word in ("dependency", "dependencies", "dependents", "trace")
        ):
            return "trace_dependencies", {
                "symbol": symbol,
                "max_depth": 2,
                "limit": 25
            }

        if any(
            word in lowered
            for word in ("equivalent", "similar", "pattern", "where else")
        ):
            return "locate_equivalent_patterns", {
                "query": symbol,
                "limit": 10
            }

        if any(
            word in lowered
            for word in ("find", "where", "locate", "search")
        ):
            return "search_symbols", {
                "query": symbol,
                "limit": 10
            }

        return "render_context", {
            "query": question,
            "limit": 5,
            "max_graph_depth": 1
        }

    def _extract_symbol(self, question):
        backtick = re.search(r"`([^`]+)`", question)

        if backtick:
            return backtick.group(1).strip()

        candidates = re.findall(
            r"\b(?:T[A-Z][A-Za-z0-9_]+|u[A-Z][A-Za-z0-9_]+|[A-Z][A-Za-z0-9_]{3,})\b",
            question
        )

        if candidates:
            return candidates[-1]

        words = [
            word.strip(".,:?;()[]{}")
            for word in question.split()
            if len(word.strip(".,:?;()[]{}")) > 2
        ]

        return " ".join(words[:6]) if words else question

    def _summarize_tool_result(self, tool_name, result):
        if tool_name == "produce_migration_context":
            stats = result.get("statistics", {})
            return (
                "Built migration context with "
                f"{stats.get('symbol_count', 0)} symbols, "
                f"{stats.get('summary_count', 0)} summaries, and "
                f"{stats.get('source_snippet_count', 0)} source snippets."
            )

        if tool_name == "produce_migration_prompt":
            stats = result.get("prompt", {}).get("statistics", {})
            return (
                "Built migration prompt with "
                f"{stats.get('symbols', 0)} symbols, "
                f"{stats.get('summaries', 0)} summaries, "
                f"{stats.get('source_items', 0)} source items, and "
                f"{stats.get('prompt_chars', 0)} characters."
            )

        if tool_name == "estimate_change_impact":
            counts = result.get("affected_counts", {})
            return (
                f"Estimated {result.get('severity')} impact for "
                f"{result.get('symbol')}: "
                f"{counts.get('affected_units', 0)} units, "
                f"{counts.get('affected_classes', 0)} classes, "
                f"{counts.get('affected_methods', 0)} methods affected."
            )

        if tool_name == "trace_dependencies":
            sections = [
                name
                for name in ("unit", "class", "method")
                if result.get(name)
            ]
            return (
                f"Traced {result.get('symbol')} as "
                f"{', '.join(sections) if sections else 'no indexed symbol'}."
            )

        if tool_name == "locate_equivalent_patterns":
            return (
                f"Located {len(result.get('results', []))} candidate "
                f"patterns for {result.get('query')}."
            )

        if tool_name == "search_symbols":
            return f"Found {len(result)} repository symbols."

        if isinstance(result, str):
            return result

        return f"Tool {tool_name} returned structured repository context."

    def _extract_langchain_answer(self, result):
        messages = result.get("messages", []) if isinstance(result, dict) else []

        if messages:
            last = messages[-1]
            return getattr(last, "content", str(last))

        return str(result)


def create_repository_langchain_agent(
    model,
    tools,
    system_prompt=REPOSITORY_AGENT_SYSTEM_PROMPT
):
    if create_agent is None:
        raise ImportError("langchain is required to create the agent.")

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt
    )


def create_repository_agent(repository, model=None, **kwargs):
    return RepositoryIntelligenceAgent(
        repository,
        model=model,
        **kwargs
    )


def load_repository_agent(output_directory="output", model=None, **kwargs):
    repository = Repository(
        load_repository(output_directory)
    )

    return create_repository_agent(
        repository,
        model=model,
        **kwargs
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the repository intelligence LangChain orchestrator."
    )
    parser.add_argument(
        "question",
        help="Repository question or modernization request."
    )
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing generated repository JSON artifacts."
    )
    parser.add_argument(
        "--artifacts",
        default="output/embeddings",
        help="Directory containing embedding artifacts."
    )
    parser.add_argument(
        "--chroma",
        default="output/chroma",
        help="Persistent ChromaDB directory."
    )
    parser.add_argument(
        "--summaries",
        default="output/summaries",
        help="Directory containing generated summaries."
    )
    parser.add_argument(
        "--source-root",
        default="doublecmd",
        help="Root directory for source files referenced by metadata."
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional LangChain model string or model object identifier."
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "langchain", "deterministic"],
        default="deterministic",
        help="Agent execution mode."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full structured output."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    agent = load_repository_agent(
        args.input,
        model=args.model,
        tool_options={
            "artifacts_directory": args.artifacts,
            "persist_directory": args.chroma,
            "summary_directory": args.summaries,
            "source_root": args.source_root
        }
    )
    result = agent.ask(
        args.question,
        mode=args.mode
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(result["answer"])


if __name__ == "__main__":
    main()
