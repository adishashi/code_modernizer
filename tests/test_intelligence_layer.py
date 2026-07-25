"""
Integration tests for the repository intelligence layer.

These tests use the generated artifacts in output/ as the fixture. They verify
that the intelligence API is stable before adding semantic search.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    ContextBuilder,
    GraphAPI,
    ModernizationAnalyzer,
    Repository,
    RepositorySearch,
    SymbolTable,
    create_repository_tools,
    load_repository
)


class IntelligenceLayerTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        output_directory = ROOT / "output"
        cls.repository = Repository(
            load_repository(output_directory)
        )
        cls.symbol_table = SymbolTable(cls.repository)
        cls.graph_api = GraphAPI(cls.repository)
        cls.search = RepositorySearch(cls.repository)
        cls.context_builder = ContextBuilder(cls.repository)


class RepositoryAPITests(IntelligenceLayerTestCase):

    def test_repository_statistics_match_generated_artifacts(self):
        stats = self.repository.statistics()

        self.assertEqual(833, stats["files"])
        self.assertEqual(804, stats["units"])
        self.assertEqual(2399, stats["classes"])
        self.assertEqual(12093, stats["methods"])
        self.assertEqual(5415, stats["dependency_edges"])
        self.assertEqual(1313, stats["inheritance_edges"])
        self.assertEqual(42309, stats["call_edges"])

    def test_repository_lookup_apis_return_expected_records(self):
        unit = self.repository.find_unit("uFileSource")
        classes = self.repository.find_classes("TFileSource")
        methods = self.repository.find_methods("CopyFile")

        self.assertIsNotNone(unit)
        self.assertEqual("uFileSource", unit["unit"])
        self.assertTrue(
            self.repository.find_file("uFileSource").endswith(
                "ufilesource.pas"
            )
        )
        self.assertGreaterEqual(len(classes), 1)
        self.assertEqual("uFileSource", classes[0]["unit"])
        self.assertGreaterEqual(len(methods), 1)

    def test_repository_method_filters_disambiguate_results(self):
        methods = self.repository.find_methods(
            "CopyFile",
            class_name="TFileSystemOperationHelper",
            unit_name="uFileSystemUtil"
        )

        self.assertEqual(1, len(methods))
        self.assertEqual("TFileSystemOperationHelper", methods[0]["class"])
        self.assertEqual("uFileSystemUtil", methods[0]["unit"])


class SymbolTableTests(IntelligenceLayerTestCase):

    def test_symbol_table_resolves_units_classes_and_methods(self):
        unit_results = self.symbol_table.resolve_symbol(
            "uFileSource",
            symbol_types="unit"
        )
        class_results = self.symbol_table.resolve_symbol(
            "TFileSource",
            symbol_types="class"
        )
        method_results = self.symbol_table.resolve_symbol(
            "CopyFile",
            symbol_types="method"
        )

        self.assertEqual("unit", unit_results[0]["type"])
        self.assertEqual("class", class_results[0]["type"])
        self.assertEqual("method", method_results[0]["type"])

    def test_symbol_table_reports_ambiguous_class_names(self):
        result = self.symbol_table.disambiguate_class("TFileSource")

        self.assertTrue(result["ambiguous"])
        self.assertGreater(len(result["matches"]), 1)

    def test_symbol_table_ranks_keyword_candidates(self):
        results = self.symbol_table.candidate_symbols(
            "checksum",
            limit=10
        )

        self.assertTrue(results)
        self.assertTrue(
            any("checksum" in item["name"].casefold() for item in results)
        )
        self.assertGreaterEqual(results[0]["score"], results[-1]["score"])


class GraphAPITests(IntelligenceLayerTestCase):

    def test_dependency_and_reverse_dependency_traversal(self):
        dependencies = self.graph_api.dependencies("uFileSource")
        dependents = self.graph_api.dependents("uFileSource")
        transitive = self.graph_api.transitive_dependencies(
            "uFileSource",
            max_depth=2
        )

        self.assertIn("uFile", dependencies)
        self.assertIn("uFileSystemFileSource", dependents)
        self.assertTrue(transitive)
        self.assertTrue(all(item["depth"] <= 2 for item in transitive))

    def test_inheritance_traversal(self):
        children = self.graph_api.children("TFileSource")
        ancestors = self.graph_api.ancestors("TFileSystemFileSource")

        self.assertIn("TRealFileSource", children)
        self.assertTrue(
            any(item["class"] == "TFileSource" for item in ancestors)
        )

    def test_call_graph_traversal(self):
        callees = self.graph_api.callees("CopyFile")
        transitive = self.graph_api.transitive_callees(
            "CopyFile",
            max_depth=2
        )

        self.assertIn("CopyFileExW", callees)
        self.assertTrue(all(item["depth"] <= 2 for item in transitive))

    def test_execution_paths_and_impact_analysis_are_bounded(self):
        paths = self.graph_api.execution_paths(
            "CopyFile",
            "CopyFileExW",
            max_depth=2
        )
        impact = self.graph_api.impact_analysis(
            "TFileSource",
            max_depth=1
        )

        self.assertIn(["CopyFile", "CopyFileExW"], paths)
        self.assertIn("children", impact)
        self.assertTrue(
            any(item["class"] == "TRealFileSource" for item in impact["children"])
        )


class SearchAndContextTests(IntelligenceLayerTestCase):

    def test_search_returns_ranked_symbol_results(self):
        results = self.search.search_symbols(
            "checksum",
            limit=5
        )

        self.assertTrue(results)
        self.assertLessEqual(len(results), 5)
        self.assertTrue(
            any("checksum" in item["name"].casefold() for item in results)
        )

    def test_context_builder_collects_records_and_graphs(self):
        context = self.context_builder.build_query_context(
            "checksum",
            limit=3,
            max_graph_depth=1
        )
        rendered = self.context_builder.render_context(context)

        self.assertTrue(context["units"])
        self.assertTrue(context["classes"])
        self.assertTrue(context["methods"])
        self.assertTrue(context["graphs"])
        self.assertIn("Repository context for: checksum", rendered)
        self.assertIn("Graph Context:", rendered)

    def test_symbol_context_falls_back_to_search(self):
        context = self.context_builder.build_symbol_context(
            "checksum",
            limit=3
        )

        self.assertTrue(context["matches"])
        self.assertTrue(context["units"])


class ModernizationAnalyzerTests(IntelligenceLayerTestCase):

    def test_finds_affected_code_for_class_symbols(self):
        analyzer = ModernizationAnalyzer(self.repository)
        result = analyzer.find_affected_code(
            "TFileSource",
            max_depth=1,
            limit=5
        )

        self.assertEqual("TFileSource", result["symbol"])
        self.assertTrue(result["matches"])
        self.assertTrue(result["affected_code"]["classes"])
        self.assertGreater(
            result["statistics"]["affected_classes"],
            0
        )

    def test_traces_dependencies_for_units_classes_and_methods(self):
        analyzer = ModernizationAnalyzer(self.repository)

        unit_trace = analyzer.trace_dependencies(
            "uFileSource",
            max_depth=1
        )
        class_trace = analyzer.trace_dependencies(
            "TFileSource",
            max_depth=1
        )
        method_trace = analyzer.trace_dependencies(
            "CopyFile",
            max_depth=1
        )

        self.assertIsNotNone(unit_trace["unit"])
        self.assertIsNotNone(class_trace["class"])
        self.assertIsNotNone(method_trace["method"])

    def test_locates_equivalent_patterns_and_estimates_impact(self):
        analyzer = ModernizationAnalyzer(self.repository)
        patterns = analyzer.locate_equivalent_patterns(
            "checksum",
            limit=5
        )
        impact = analyzer.estimate_change_impact(
            "TFileSource",
            max_depth=1
        )

        self.assertTrue(patterns["results"])
        self.assertIn(
            impact["severity"],
            {"low", "medium", "high"}
        )
        self.assertTrue(impact["risk_notes"])


@unittest.skipIf(
    importlib.util.find_spec("langchain_core") is None,
    "langchain_core is not installed"
)
class LangChainToolTests(IntelligenceLayerTestCase):

    def test_langchain_tool_factory_exposes_expected_tools(self):
        tools = create_repository_tools(self.repository)
        names = {tool.name for tool in tools}
        expected = {
            "find_unit",
            "find_file",
            "find_class",
            "find_method",
            "find_dependencies",
            "find_dependents",
            "find_parent",
            "find_children",
            "find_callers",
            "find_callees",
            "transitive_dependencies",
            "transitive_dependents",
            "transitive_callers",
            "transitive_callees",
            "execution_path",
            "impact_analysis",
            "search_symbols",
            "build_context",
            "render_context",
            "repository_statistics",
            "find_affected_code",
            "trace_dependencies",
            "locate_equivalent_patterns",
            "estimate_change_impact",
            "produce_migration_context",
            "produce_migration_prompt",
            "generate_migration_code"
        }

        self.assertEqual(expected, names)

    def test_langchain_tools_invoke_repository_apis(self):
        tools = {
            tool.name: tool
            for tool in create_repository_tools(self.repository)
        }

        self.assertEqual(
            "uFileSource",
            tools["find_unit"].invoke(
                {"unit_name": "uFileSource"}
            )["unit"]
        )
        self.assertTrue(
            tools["find_class"].invoke(
                {"class_name": "TFileSource"}
            )
        )
        self.assertTrue(
            tools["search_symbols"].invoke(
                {
                    "query": "checksum",
                    "limit": 3
                }
            )
        )
        self.assertEqual(
            12093,
            tools["repository_statistics"].invoke({})["methods"]
        )
        self.assertTrue(
            tools["find_affected_code"].invoke(
                {
                    "symbol": "TFileSource",
                    "max_depth": 1,
                    "limit": 5
                }
            )["affected_code"]["classes"]
        )
        self.assertIsNotNone(
            tools["trace_dependencies"].invoke(
                {
                    "symbol": "CopyFile",
                    "max_depth": 1,
                    "limit": 5
                }
            )["method"]
        )
        self.assertTrue(
            tools["locate_equivalent_patterns"].invoke(
                {
                    "query": "checksum",
                    "limit": 3
                }
            )["results"]
        )
        self.assertIn(
            tools["estimate_change_impact"].invoke(
                {
                    "symbol": "TFileSource",
                    "max_depth": 1,
                    "limit": 5
                }
            )["severity"],
            {"low", "medium", "high"}
        )


if __name__ == "__main__":
    unittest.main()
