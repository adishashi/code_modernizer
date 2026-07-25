"""
vector_store.py

ChromaDB integration for repository embedding artifacts.

This module ingests Stage 4.1 artifacts into a persistent vector database. It
does not generate embeddings and does not implement hybrid semantic search.
"""

from pathlib import Path
import json


DEFAULT_COLLECTION_NAME = "repository_intelligence"


class EmbeddingArtifactReader:
    """
    Reads metadata and vectors produced by embeddings.py.
    """

    def __init__(self, artifact_directory):
        self.artifact_directory = Path(artifact_directory)

    def read_manifest(self):
        path = self.artifact_directory / "manifest.json"

        if not path.exists():
            raise FileNotFoundError(path)

        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def read_metadata(self, filename="metadata.jsonl"):
        path = self.artifact_directory / filename

        if not path.exists():
            raise FileNotFoundError(path)

        records = []

        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()

                if not line:
                    continue

                records.append(json.loads(line))

        return records

    def read_embeddings(self, filename="embeddings.npy"):
        import numpy as np

        path = self.artifact_directory / filename

        if not path.exists():
            raise FileNotFoundError(path)

        return np.load(path)

    def read(self):
        manifest = self.read_manifest()
        files = manifest.get("files", {})
        metadata = self.read_metadata(
            files.get("metadata", "metadata.jsonl")
        )
        embeddings = self.read_embeddings(
            files.get("embeddings", "embeddings.npy")
        )

        if len(metadata) != embeddings.shape[0]:
            raise ValueError(
                "Metadata and embedding counts do not match: "
                f"{len(metadata)} != {embeddings.shape[0]}"
            )

        return manifest, metadata, embeddings


class ChromaRepositoryVectorStore:
    """
    Persistent ChromaDB store for repository embeddings.
    """

    def __init__(
        self,
        persist_directory,
        collection_name=DEFAULT_COLLECTION_NAME
    ):
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    @property
    def client(self):
        if self._client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise RuntimeError(
                    "chromadb is required for ChromaRepositoryVectorStore"
                ) from exc

            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory)
            )

        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "description": "Repository intelligence embeddings"
                }
            )

        return self._collection

    def reset_collection(self):
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass

        self._collection = None

        return self.collection

    def count(self):
        return self.collection.count()

    def close(self):
        self._collection = None
        self._client = None

    def ingest_artifacts(
        self,
        artifact_directory,
        batch_size=500,
        reset=True
    ):
        reader = EmbeddingArtifactReader(artifact_directory)
        manifest, metadata, embeddings = reader.read()

        if reset:
            collection = self.reset_collection()
        else:
            collection = self.collection

        ids = [
            record["document_id"]
            for record in metadata
        ]
        documents = [
            self._metadata_to_document(record)
            for record in metadata
        ]
        clean_metadata = [
            self._clean_metadata(record)
            for record in metadata
        ]

        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            collection.add(
                ids=ids[start:end],
                embeddings=embeddings[start:end].tolist(),
                metadatas=clean_metadata[start:end],
                documents=documents[start:end]
            )

        return {
            "collection": self.collection_name,
            "persist_directory": str(self.persist_directory),
            "ingested": len(ids),
            "count": collection.count(),
            "embedding_shape": manifest.get("embedding_shape"),
            "document_counts": manifest.get("document_counts", {})
        }

    def query(
        self,
        query_embeddings,
        n_results=10,
        where=None
    ):
        embeddings = query_embeddings

        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()

        if embeddings and isinstance(embeddings[0], (int, float)):
            embeddings = [embeddings]

        return self.collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            where=where,
            include=[
                "metadatas",
                "documents",
                "distances"
            ]
        )

    def _metadata_to_document(self, record):
        parts = [
            f"type: {record.get('document_type')}",
            f"name: {record.get('name')}"
        ]

        for key in ("unit", "class_name", "method_name", "file"):
            value = record.get(key)

            if value is not None:
                parts.append(f"{key}: {value}")

        return "\n".join(parts)

    def _clean_metadata(self, record):
        cleaned = {}

        for key, value in record.items():
            if value is None:
                continue

            cleaned[key] = value

        return cleaned


def ingest_chroma_artifacts(
    artifact_directory,
    persist_directory,
    collection_name=DEFAULT_COLLECTION_NAME,
    batch_size=500,
    reset=True
):
    """
    Ingest embedding artifacts into a persistent ChromaDB collection.
    """

    store = ChromaRepositoryVectorStore(
        persist_directory,
        collection_name=collection_name
    )

    return store.ingest_artifacts(
        artifact_directory,
        batch_size=batch_size,
        reset=reset
    )
