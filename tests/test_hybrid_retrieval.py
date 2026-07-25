"""
Tests for Stage 4.3 hybrid retrieval.
"""

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    HybridRetriever,
    Repository,
    load_repository
)


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class HybridRetrievalTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )

    def test_hybrid_retrieval_combines_lexical_vector_and_statistics(self):
        retriever = HybridRetriever(
            self.repository,
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma"
        )

        try:
            result = retriever.retrieve(
                "checksum",
                limit=20,
                lexical_limit=10,
                vector_limit=10,
                graph_depth=1
            )
        finally:
            retriever.close()

        self.assertEqual("checksum", result["query"])
        self.assertEqual(
            15588,
            result["statistics"]["vector_collection_count"]
        )
        self.assertTrue(result["results"])
        self.assertTrue(
            any(
                "checksum" in item["name"].casefold()
                for item in result["results"]
            )
        )
        self.assertTrue(
            any(
                "lexical" in item["sources"]
                for item in result["results"]
            )
        )
        self.assertTrue(
            any(
                "vector" in item["sources"]
                for item in result["results"]
            )
        )

    def test_hybrid_retrieval_filters_document_types(self):
        retriever = HybridRetriever(
            self.repository,
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma"
        )

        try:
            result = retriever.retrieve(
                "TFileSource",
                limit=5,
                lexical_limit=10,
                vector_limit=10,
                graph_depth=0,
                document_types=["class"]
            )
        finally:
            retriever.close()

        self.assertTrue(result["results"])
        self.assertTrue(
            all(
                item["document_type"] == "class"
                for item in result["results"]
            )
        )
        self.assertTrue(
            any(
                item["name"] == "TFileSource"
                for item in result["results"]
            )
        )

    def test_graph_expansion_adds_graph_source(self):
        retriever = HybridRetriever(
            self.repository,
            artifacts_directory=ROOT / "output" / "embeddings",
            persist_directory=ROOT / "output" / "chroma"
        )

        try:
            result = retriever.retrieve(
                "TFileSource",
                limit=20,
                lexical_limit=5,
                vector_limit=5,
                graph_depth=1,
                document_types=["class"]
            )
        finally:
            retriever.close()

        self.assertTrue(
            any(
                "graph" in item["sources"]
                for item in result["results"]
            )
        )


if __name__ == "__main__":
    unittest.main()
