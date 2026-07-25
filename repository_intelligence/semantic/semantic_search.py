"""
semantic_search.py

Repository-aware semantic search over the ChromaDB vector store.

This module is intentionally layered above embedding generation and vector
storage. Embeddings are produced by embeddings.py, persisted by vector_store.py,
and queried here with repository-friendly result formatting and optional summary
enrichment.
"""

from pathlib import Path
import json

try:
    from .embeddings import LocalHashingEmbeddingProvider
    from ..chroma.vector_store import (
        DEFAULT_COLLECTION_NAME,
        ChromaRepositoryVectorStore,
        EmbeddingArtifactReader
    )
except ImportError:
    from embeddings import LocalHashingEmbeddingProvider
    from repository_intelligence.chroma.vector_store import (
        DEFAULT_COLLECTION_NAME,
        ChromaRepositoryVectorStore,
        EmbeddingArtifactReader
    )


class SummaryIndex:
    """
    Lookup index for summary artifacts.

    Semantic search results reference embedding document identifiers, while
    summaries use their own summary identifiers. This index bridges that gap by
    matching records through type/name/unit/class/method metadata.
    """

    def __init__(self, summary_directory=None):
        self.summary_directory = Path(summary_directory) if summary_directory else None
        self.by_key = {}

        if self.summary_directory:
            self._load()

    def find(self, metadata):
        if not self.by_key:
            return None

        key = self._key(
            metadata.get("document_type"),
            metadata.get("name"),
            metadata.get("unit"),
            metadata.get("class_name"),
            metadata.get("method_name")
        )

        return self.by_key.get(key)

    def _load(self):
        path = self.summary_directory / "summaries.jsonl"

        if not path.exists():
            return

        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()

                if not line:
                    continue

                record = json.loads(line)
                key = self._key(
                    record.get("summary_type"),
                    record.get("name"),
                    record.get("unit"),
                    record.get("class_name"),
                    record.get("method_name")
                )
                self.by_key[key] = record

    def _key(
        self,
        record_type,
        name,
        unit,
        class_name,
        method_name
    ):
        return (
            record_type,
            name,
            unit,
            class_name,
            method_name
        )


class SemanticSearchEngine:
    """
    Semantic search API backed by ChromaDB.

    Current embeddings use the deterministic local hashing provider. The class
    accepts an embedding_provider argument so model-backed embeddings can later
    be plugged in without changing the search API.
    """

    def __init__(
        self,
        artifacts_directory="output/embeddings",
        persist_directory="output/chroma",
        collection_name=DEFAULT_COLLECTION_NAME,
        summary_directory="output/summaries",
        embedding_provider=None
    ):
        self.artifacts_directory = Path(artifacts_directory)
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self.summary_index = SummaryIndex(summary_directory)

        reader = EmbeddingArtifactReader(self.artifacts_directory)
        self.manifest = reader.read_manifest()
        dimensions = (
            self.manifest.get("provider", {}).get("dimensions")
            or self.manifest.get("embedding_shape", [None, 384])[1]
        )
        self.embedding_provider = (
            embedding_provider
            or LocalHashingEmbeddingProvider(dimensions=dimensions)
        )
        self.vector_store = ChromaRepositoryVectorStore(
            self.persist_directory,
            collection_name=self.collection_name
        )

    def close(self):
        self.vector_store.close()

    def search(
        self,
        query,
        limit=10,
        document_types=None,
        include_summaries=True
    ):
        # The same provider used to build the Chroma collection must be used
        # for query embeddings. With local_hashing this is deterministic because
        # the hashing projection has no learned state.
        query_embedding = self.embedding_provider.embed_documents([query])
        where = self._document_type_filter(document_types)
        raw = self.vector_store.query(
            query_embedding,
            n_results=limit,
            where=where
        )

        results = self._format_results(
            raw,
            include_summaries=include_summaries
        )

        return {
            "query": query,
            "results": results,
            "statistics": {
                "vector_collection_count": self.vector_store.count(),
                "embedding_manifest": {
                    "document_count": self.manifest.get("document_count"),
                    "document_counts": self.manifest.get("document_counts"),
                    "embedding_shape": self.manifest.get("embedding_shape"),
                    "provider": self.manifest.get("provider")
                }
            }
        }

    def _format_results(
        self,
        raw,
        include_summaries
    ):
        ids = raw.get("ids", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        results = []

        for document_id, metadata, document, distance in zip(
            ids,
            metadatas,
            documents,
            distances
        ):
            # Chroma returns a distance where lower is better. Convert it into
            # a bounded similarity-style score for display and downstream
            # ranking explanations.
            score = 1 / (1 + max(distance, 0))
            result = {
                "document_id": document_id,
                "document_type": metadata.get("document_type"),
                "name": metadata.get("name"),
                "unit": metadata.get("unit"),
                "class_name": metadata.get("class_name"),
                "method_name": metadata.get("method_name"),
                "file": metadata.get("file"),
                "score": round(score, 6),
                "distance": distance,
                "document": document
            }

            if include_summaries:
                # Summaries are optional enrichment. Search should still work
                # when output/summaries has not been generated yet.
                summary = self.summary_index.find(metadata)

                if summary:
                    result["summary"] = summary.get("summary")
                    result["summary_id"] = summary.get("summary_id")
                    result["metrics"] = summary.get("metrics")

            results.append(result)

        return results

    def _document_type_filter(self, document_types):
        if document_types is None:
            return None

        if isinstance(document_types, str):
            requested = [document_types.casefold()]
        else:
            requested = [
                document_type.casefold()
                for document_type in document_types
            ]

        if len(requested) == 1:
            return {
                "document_type": requested[0]
            }

        return {
            "document_type": {
                "$in": requested
            }
        }
