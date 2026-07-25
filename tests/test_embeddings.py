"""
Tests for Stage 4.1 embedding generation.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    LocalHashingEmbeddingProvider,
    Repository,
    RepositoryEmbeddingDocumentBuilder,
    RepositoryEmbeddingGenerator,
    load_repository
)


class EmbeddingTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )


class EmbeddingDocumentBuilderTests(EmbeddingTestCase):

    def test_builds_unit_class_method_and_subsystem_documents(self):
        builder = RepositoryEmbeddingDocumentBuilder(self.repository)

        unit_documents = builder.build_documents("unit")
        class_documents = builder.build_documents("class")
        method_documents = builder.build_documents("method")
        subsystem_documents = builder.build_documents("subsystem")

        self.assertEqual(804, len(unit_documents))
        self.assertEqual(2508, len(class_documents))
        self.assertEqual(12093, len(method_documents))
        self.assertTrue(subsystem_documents)

        self.assertEqual("unit", unit_documents[0].document_type)
        self.assertIn("type: unit", unit_documents[0].text)
        self.assertEqual("class", class_documents[0].document_type)
        self.assertIn("type: class", class_documents[0].text)
        self.assertEqual("method", method_documents[0].document_type)
        self.assertIn("type: method", method_documents[0].text)
        self.assertEqual("subsystem", subsystem_documents[0].document_type)
        self.assertIn("type: subsystem", subsystem_documents[0].text)

    def test_document_ids_are_unique_for_default_corpus(self):
        builder = RepositoryEmbeddingDocumentBuilder(self.repository)
        documents = builder.build_documents()
        document_ids = [
            document.document_id
            for document in documents
        ]

        self.assertEqual(len(document_ids), len(set(document_ids)))


class EmbeddingGenerationTests(EmbeddingTestCase):

    def test_local_hashing_provider_generates_deterministic_shape(self):
        provider = LocalHashingEmbeddingProvider(dimensions=32)
        texts = [
            "unit uFileSource class TFileSource",
            "checksum calculation hash algorithm"
        ]

        first = provider.embed_documents(texts)
        second = provider.embed_documents(texts)

        self.assertEqual((2, 32), first.shape)
        np.testing.assert_array_equal(first, second)

    def test_generator_writes_manifest_metadata_and_embeddings(self):
        provider = LocalHashingEmbeddingProvider(dimensions=32)
        generator = RepositoryEmbeddingGenerator(
            self.repository,
            provider=provider
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = generator.generate(
                temp_dir,
                document_types=["unit", "subsystem"]
            )

            temp_path = Path(temp_dir)
            metadata_path = temp_path / "metadata.jsonl"
            embeddings_path = temp_path / "embeddings.npy"
            manifest_path = temp_path / "manifest.json"

            self.assertTrue(metadata_path.exists())
            self.assertTrue(embeddings_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertEqual(
                manifest["document_count"],
                manifest["embedding_shape"][0]
            )
            self.assertEqual(32, manifest["embedding_shape"][1])
            self.assertEqual("local_hashing", manifest["provider"]["provider"])
            self.assertEqual(804, manifest["document_counts"]["unit"])
            self.assertGreater(manifest["document_counts"]["subsystem"], 0)

            embeddings = np.load(embeddings_path)
            self.assertEqual(tuple(manifest["embedding_shape"]), embeddings.shape)

            with metadata_path.open("r", encoding="utf-8") as fp:
                first_metadata = json.loads(fp.readline())

            self.assertIn("document_id", first_metadata)
            self.assertIn("document_type", first_metadata)
            self.assertNotIn("text", first_metadata)


if __name__ == "__main__":
    unittest.main()
