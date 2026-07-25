"""
Tests for semantic search over the ChromaDB vector store.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import SemanticSearchEngine  # noqa: E402


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class SemanticSearchTests(unittest.TestCase):

    def test_semantic_search_returns_vector_results_with_statistics(self):
        engine = SemanticSearchEngine(
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma",
            summary_directory=ROOT / "output" / "summaries"
        )

        try:
            result = engine.search(
                "checksum calculation",
                limit=5
            )
        finally:
            engine.close()

        self.assertEqual("checksum calculation", result["query"])
        self.assertEqual(
            15588,
            result["statistics"]["vector_collection_count"]
        )
        self.assertEqual(5, len(result["results"]))
        self.assertIn("score", result["results"][0])
        self.assertIn("distance", result["results"][0])

    def test_semantic_search_filters_document_types(self):
        engine = SemanticSearchEngine(
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma",
            summary_directory=ROOT / "output" / "summaries"
        )

        try:
            result = engine.search(
                "TFileSource",
                limit=5,
                document_types=["class"]
            )
        finally:
            engine.close()

        self.assertTrue(result["results"])
        self.assertTrue(
            all(
                item["document_type"] == "class"
                for item in result["results"]
            )
        )

    def test_semantic_search_enriches_results_with_summaries(self):
        engine = SemanticSearchEngine(
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma",
            summary_directory=ROOT / "output" / "summaries"
        )

        try:
            result = engine.search(
                "TFileSource",
                limit=10,
                document_types=["class"],
                include_summaries=True
            )
        finally:
            engine.close()

        self.assertTrue(
            any(
                item.get("summary")
                for item in result["results"]
            )
        )


if __name__ == "__main__":
    unittest.main()
