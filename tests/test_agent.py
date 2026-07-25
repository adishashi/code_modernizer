"""
Tests for the LangChain repository orchestration layer.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    Repository,
    RepositoryAgentMemory,
    RepositoryIntelligenceAgent,
    create_repository_langchain_agent,
    create_repository_tools,
    load_repository
)


class RepositoryAgentTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )

    def test_memory_keeps_bounded_history(self):
        memory = RepositoryAgentMemory(max_messages=2)
        memory.add_user_message("one")
        memory.add_ai_message("two")
        memory.add_user_message("three")

        self.assertEqual(2, len(memory.snapshot()))

    def test_deterministic_agent_routes_impact_questions_to_tool(self):
        agent = RepositoryIntelligenceAgent(self.repository)
        result = agent.ask(
            "Estimate impact of `TFileSource`",
            mode="deterministic"
        )

        self.assertEqual("deterministic", result["mode"])
        self.assertEqual(
            "estimate_change_impact",
            result["tool_calls"][0]["tool"]
        )
        self.assertIn(
            result["result"]["severity"],
            {"low", "medium", "high"}
        )

    def test_deterministic_agent_routes_search_questions_to_tool(self):
        agent = RepositoryIntelligenceAgent(self.repository)
        result = agent.ask(
            "Where is checksum implemented?",
            mode="deterministic"
        )

        self.assertEqual("search_symbols", result["tool_calls"][0]["tool"])
        self.assertTrue(result["result"])

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_agent_graph_can_be_constructed(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        tools = create_repository_tools(self.repository)
        graph = create_repository_langchain_agent(
            FakeListChatModel(responses=["ok"]),
            tools
        )

        self.assertIsNotNone(graph)


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class RepositoryAgentModernizationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )

    def test_deterministic_agent_routes_modernization_to_context_tool(self):
        agent = RepositoryIntelligenceAgent(
            self.repository,
            tool_options={
                "artifacts_directory": ROOT / "output" / "embeddings",
                "persist_directory": ROOT / "output" / "chroma",
                "summary_directory": ROOT / "output" / "summaries",
                "source_root": ROOT / "doublecmd"
            }
        )
        result = agent.ask(
            "Modernize TFileSource to Java",
            mode="deterministic"
        )

        self.assertEqual(
            "produce_migration_prompt",
            result["tool_calls"][0]["tool"]
        )
        self.assertTrue(result["result"]["context"]["symbols"])
        self.assertIn("prompt", result["result"]["prompt"])


if __name__ == "__main__":
    unittest.main()
