"""
Tests for modernization context assembly.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    ModernizationContextAssembler,
    PascalSourceExtractor,
    Repository,
    SourceSnippetExtractor,
    build_modernization_context,
    create_repository_tools,
    load_repository
)


class PascalSourceExtractorTests(unittest.TestCase):

    def test_extracts_full_class_declaration(self):
        extractor = PascalSourceExtractor(ROOT / "doublecmd")
        result = extractor.extract_symbol(
            {
                "document_type": "class",
                "name": "TFileSource",
                "class_name": "TFileSource",
                "unit": "uFileSource",
                "file": "src/filesources/ufilesource.pas"
            }
        )

        self.assertIsNotNone(result)
        self.assertEqual("class_declaration", result["extraction_kind"])
        self.assertIn(
            "TFileSource = class(TInterfacedObject, IFileSource)",
            result["source"]
        )
        self.assertIn("protected", result["source"])
        self.assertIn("public", result["source"])
        self.assertTrue(result["source"].rstrip().endswith("end;"))
        self.assertGreater(result["line_count"], 100)
        self.assertFalse(result["truncated"])

    def test_extracts_full_method_implementation_with_nested_procedures(self):
        extractor = PascalSourceExtractor(ROOT / "doublecmd")
        result = extractor.extract_symbol(
            {
                "document_type": "method",
                "name": "CopyFile",
                "method_name": "CopyFile",
                "class_name": "TFileSystemOperationHelper",
                "unit": "uFileSystemUtil",
                "file": "src/filesources/filesystem/ufilesystemutil.pas"
            }
        )

        self.assertIsNotNone(result)
        self.assertEqual("method_implementation", result["extraction_kind"])
        self.assertIn(
            "function TFileSystemOperationHelper.CopyFile(",
            result["source"]
        )
        self.assertIn("procedure OpenSourceFile;", result["source"])
        self.assertIn("procedure OpenTargetFile;", result["source"])
        self.assertTrue(result["source"].rstrip().endswith("end;"))
        self.assertGreater(result["line_count"], 200)
        self.assertFalse(result["truncated"])

    def test_source_snippet_extractor_keeps_compatibility_shape(self):
        extractor = SourceSnippetExtractor(ROOT / "doublecmd")
        snippet = extractor.extract(
            {
                "document_type": "class",
                "name": "TFileSource",
                "class_name": "TFileSource",
                "file": "src/filesources/ufilesource.pas"
            },
            max_lines=25
        )

        self.assertIsNotNone(snippet)
        self.assertIn("snippet", snippet)
        self.assertIn("source", snippet)
        self.assertLessEqual(snippet["line_count"], 25)


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class ModernizationContextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )

    def test_modernization_context_combines_retrieval_layers(self):
        assembler = ModernizationContextAssembler(
            self.repository,
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma",
            summary_directory=ROOT / "output" / "summaries",
            source_root=ROOT / "doublecmd"
        )

        try:
            context = assembler.build_context(
                "TFileSource modernization",
                limit=5,
                lexical_limit=10,
                vector_limit=10,
                graph_depth=1,
                document_types=["class"],
                max_snippet_lines=30
            )
        finally:
            assembler.close()

        self.assertEqual(
            "TFileSource modernization",
            context["task"]["description"]
        )
        self.assertEqual("Java", context["task"]["target_language"])
        self.assertTrue(context["symbols"])
        self.assertTrue(context["summaries"])
        self.assertTrue(context["graph_context"])
        self.assertTrue(context["target_design"]["templates"])
        self.assertTrue(context["source_context"])
        self.assertTrue(
            any(
                "hybrid" in symbol["sources"]
                for symbol in context["symbols"]
            )
        )
        self.assertTrue(
            any(
                "semantic" in symbol["sources"]
                for symbol in context["symbols"]
            )
        )

    def test_source_snippet_extractor_returns_bounded_source_window(self):
        extractor = SourceSnippetExtractor(ROOT / "doublecmd")
        snippet = extractor.extract(
            {
                "document_type": "class",
                "name": "TFileSource",
                "class_name": "TFileSource",
                "file": "src/filesources/ufilesource.pas"
            },
            max_lines=25
        )

        self.assertIsNotNone(snippet)
        self.assertIn("TFileSource", snippet["snippet"])
        self.assertLessEqual(
            len(snippet["snippet"].splitlines()),
            25
        )

    def test_convenience_helper_accepts_separate_options(self):
        context = build_modernization_context(
            self.repository,
            "TFileSource modernization",
            assembler_options={
                "artifacts_directory": ROOT / "output" / "embeddings",
                "persist_directory": ROOT / "output" / "chroma",
                "summary_directory": ROOT / "output" / "summaries",
                "source_root": ROOT / "doublecmd"
            },
            context_options={
                "target_language": "Java",
                "limit": 3,
                "lexical_limit": 5,
                "vector_limit": 5,
                "document_types": ["class"],
                "include_source": False
            }
        )

        self.assertEqual("Java", context["task"]["target_language"])
        self.assertEqual([], context["source_context"])
        self.assertTrue(context["symbols"])
        self.assertTrue(context["target_design"]["prompt_section"])

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_migration_context_tool_produces_context(self):
        tools = {
            tool.name: tool
            for tool in create_repository_tools(
                self.repository,
                artifacts_directory=ROOT / "output" / "embeddings",
                persist_directory=ROOT / "output" / "chroma",
                summary_directory=ROOT / "output" / "summaries",
                source_root=ROOT / "doublecmd"
            )
        }

        context = tools["produce_migration_context"].invoke(
            {
                "task": "TFileSource modernization",
                "limit": 3,
                "graph_depth": 1,
                "document_types": ["class"],
                "include_source": False
            }
        )

        self.assertEqual(
            "TFileSource modernization",
            context["task"]["description"]
        )
        self.assertTrue(context["symbols"])
        self.assertEqual([], context["source_context"])


if __name__ == "__main__":
    unittest.main()
