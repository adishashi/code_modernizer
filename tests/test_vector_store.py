"""
Tests for Stage 4.2 ChromaDB vector database integration.
"""

import importlib.util
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
    ChromaRepositoryVectorStore,
    EmbeddingArtifactReader
)


ARTIFACTS = ROOT / "output" / "embeddings"


class EmbeddingArtifactReaderTests(unittest.TestCase):

    def test_reader_loads_manifest_metadata_and_embeddings(self):
        reader = EmbeddingArtifactReader(ARTIFACTS)
        manifest, metadata, embeddings = reader.read()

        self.assertEqual(15588, manifest["document_count"])
        self.assertEqual(15588, len(metadata))
        self.assertEqual((15588, 384), embeddings.shape)
        self.assertIn("document_id", metadata[0])


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class ChromaVectorStoreTests(unittest.TestCase):

    def test_ingests_subset_artifacts_and_queries_collection(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            with tempfile.TemporaryDirectory(
                ignore_cleanup_errors=True
            ) as chroma_dir:
                artifact_path = Path(artifact_dir)
                chroma_path = Path(chroma_dir)
                self._write_subset_artifacts(artifact_path)

                store = ChromaRepositoryVectorStore(
                    chroma_path,
                    collection_name="test_repository_intelligence"
                )

                try:
                    result = store.ingest_artifacts(
                        artifact_path,
                        batch_size=2
                    )
                    query = store.query(
                        [[1.0, 0.0, 0.0, 0.0]],
                        n_results=2
                    )
                finally:
                    store.close()

                self.assertEqual(3, result["ingested"])
                self.assertEqual(3, result["count"])
                self.assertEqual(2, len(query["ids"][0]))
                self.assertEqual("unit:uFileSource", query["ids"][0][0])

    def _write_subset_artifacts(self, artifact_path):
        metadata = [
            {
                "document_id": "unit:uFileSource",
                "document_type": "unit",
                "name": "uFileSource",
                "unit": "uFileSource"
            },
            {
                "document_id": "class:uFileSource:TFileSource:0",
                "document_type": "class",
                "name": "TFileSource",
                "unit": "uFileSource",
                "class_name": "TFileSource"
            },
            {
                "document_id": "method:uFileSystemUtil:helper:CopyFile:0",
                "document_type": "method",
                "name": "TFileSystemOperationHelper.CopyFile",
                "unit": "uFileSystemUtil",
                "class_name": "TFileSystemOperationHelper",
                "method_name": "CopyFile"
            }
        ]
        embeddings = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.9, 0.1, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0]
            ],
            dtype="float32"
        )
        manifest = {
            "schema_version": 1,
            "document_count": len(metadata),
            "document_counts": {
                "unit": 1,
                "class": 1,
                "method": 1
            },
            "embedding_shape": list(embeddings.shape),
            "files": {
                "metadata": "metadata.jsonl",
                "embeddings": "embeddings.npy"
            },
            "provider": {
                "provider": "test"
            }
        }

        with (artifact_path / "metadata.jsonl").open(
            "w",
            encoding="utf-8"
        ) as fp:
            for record in metadata:
                fp.write(json.dumps(record))
                fp.write("\n")

        np.save(artifact_path / "embeddings.npy", embeddings)

        with (artifact_path / "manifest.json").open(
            "w",
            encoding="utf-8"
        ) as fp:
            json.dump(manifest, fp)


if __name__ == "__main__":
    unittest.main()
