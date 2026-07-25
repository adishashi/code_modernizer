"""
hybrid_retrieval.py

Hybrid retrieval over repository intelligence data.

This layer combines lexical search, Chroma vector search, and graph expansion.
It does not mutate repository indices or vector database artifacts.
"""

from dataclasses import dataclass
from pathlib import Path

try:
    from .embeddings import LocalHashingEmbeddingProvider
    from ..graph_api import GraphAPI
    from ..search import RepositorySearch
    from ..chroma.vector_store import (
        DEFAULT_COLLECTION_NAME,
        ChromaRepositoryVectorStore,
        EmbeddingArtifactReader
    )
except ImportError:
    from embeddings import LocalHashingEmbeddingProvider
    from repository_intelligence.graph_api import GraphAPI
    from repository_intelligence.search import RepositorySearch
    from repository_intelligence.chroma.vector_store import (
        DEFAULT_COLLECTION_NAME,
        ChromaRepositoryVectorStore,
        EmbeddingArtifactReader
    )


@dataclass
class HybridRetrievalWeights:
    lexical: float = 0.35
    vector: float = 0.45
    graph: float = 0.20


class EmbeddingMetadataIndex:
    """
    Lookup helper for embedding metadata records.
    """

    def __init__(self, metadata_records):
        self.records = metadata_records
        self.by_id = {}
        self.by_type_name = {}
        self.by_unit = {}
        self.by_class_name = {}
        self.by_method_name = {}

        for record in metadata_records:
            document_id = record.get("document_id")
            document_type = record.get("document_type")
            name = record.get("name")
            unit = record.get("unit")
            class_name = record.get("class_name")
            method_name = record.get("method_name")

            if document_id:
                self.by_id[document_id] = record

            self._append(self.by_type_name, (document_type, name), record)

            if unit:
                self._append(self.by_unit, unit, record)

            if class_name:
                self._append(self.by_class_name, class_name, record)

            if method_name:
                self._append(self.by_method_name, method_name, record)

    def find_for_symbol(self, symbol):
        symbol_type = symbol.get("type")
        name = symbol.get("name")
        unit = symbol.get("unit")
        class_name = symbol.get("class")
        method_name = symbol.get("method")

        if symbol_type == "unit":
            return self.by_type_name.get(("unit", name), [])

        if symbol_type == "class":
            matches = self.by_type_name.get(("class", name), [])

            if unit:
                matches = [
                    record for record in matches
                    if record.get("unit") == unit
                ]

            return matches

        if symbol_type == "method":
            matches = []

            if method_name:
                matches = list(self.by_method_name.get(method_name, []))
            else:
                matches = list(self.by_type_name.get(("method", name), []))

            if unit:
                matches = [
                    record for record in matches
                    if record.get("unit") == unit
                ]

            if class_name:
                matches = [
                    record for record in matches
                    if record.get("class_name") == class_name
                ]

            return matches

        if symbol_type == "file":
            return [
                record for record in self.records
                if record.get("file") == name
            ]

        return []

    def unit_documents(self, unit_name):
        return [
            record for record in self.by_unit.get(unit_name, [])
            if record.get("document_type") == "unit"
        ]

    def class_documents(self, class_name):
        return [
            record for record in self.by_class_name.get(class_name, [])
            if record.get("document_type") == "class"
        ]

    def method_documents(self, method_name):
        return [
            record for record in self.by_method_name.get(method_name, [])
            if record.get("document_type") == "method"
        ]

    def _append(self, index, key, record):
        if key not in index:
            index[key] = []

        index[key].append(record)


class HybridRetriever:
    """
    Combines lexical search, vector search, and graph expansion.
    """

    def __init__(
        self,
        repository,
        artifacts_directory="output/embeddings",
        persist_directory="output/chroma",
        collection_name=DEFAULT_COLLECTION_NAME,
        embedding_provider=None,
        weights=None
    ):
        self.repository = repository
        self.artifacts_directory = Path(artifacts_directory)
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self.search = RepositorySearch(repository)
        self.graph_api = GraphAPI(repository)
        self.weights = weights or HybridRetrievalWeights()

        reader = EmbeddingArtifactReader(self.artifacts_directory)
        self.manifest = reader.read_manifest()
        self.metadata_index = EmbeddingMetadataIndex(
            reader.read_metadata(
                self.manifest.get("files", {}).get(
                    "metadata",
                    "metadata.jsonl"
                )
            )
        )

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

    def retrieve(
        self,
        query,
        limit=10,
        lexical_limit=25,
        vector_limit=25,
        graph_depth=1,
        document_types=None
    ):
        candidates = {}

        lexical_results = self._lexical_results(
            query,
            lexical_limit=lexical_limit,
            document_types=document_types
        )
        self._merge_lexical(candidates, lexical_results)

        vector_results = self._vector_results(
            query,
            vector_limit=vector_limit,
            document_types=document_types
        )
        self._merge_vector(candidates, vector_results)

        if graph_depth > 0:
            self._merge_graph(candidates, graph_depth=graph_depth)

        results = [
            self._finalize_candidate(candidate)
            for candidate in candidates.values()
        ]
        results.sort(
            key=lambda result: (
                result["score"],
                result["name"]
            ),
            reverse=True
        )

        return {
            "query": query,
            "results": results[:limit],
            "statistics": {
                "repository": self.repository.statistics(),
                "vector_collection_count": self.vector_store.count(),
                "embedding_manifest": {
                    "document_count": self.manifest.get("document_count"),
                    "document_counts": self.manifest.get("document_counts"),
                    "embedding_shape": self.manifest.get("embedding_shape"),
                    "provider": self.manifest.get("provider")
                }
            },
            "weights": {
                "lexical": self.weights.lexical,
                "vector": self.weights.vector,
                "graph": self.weights.graph
            }
        }

    def _lexical_results(
        self,
        query,
        lexical_limit,
        document_types
    ):
        symbol_types = self._document_types_to_symbol_types(document_types)

        return self.search.search_symbols(
            query,
            symbol_types=symbol_types,
            limit=lexical_limit
        )

    def _vector_results(
        self,
        query,
        vector_limit,
        document_types
    ):
        query_embedding = self.embedding_provider.embed_documents([query])
        where = self._document_type_filter(document_types)

        return self.vector_store.query(
            query_embedding,
            n_results=vector_limit,
            where=where
        )

    def _merge_lexical(self, candidates, lexical_results):
        for result in lexical_results:
            records = self.metadata_index.find_for_symbol(result)

            for record in records:
                candidate = self._candidate(candidates, record)
                score = min(1.0, result.get("score", 0) / 100)

                candidate["lexical_score"] = max(
                    candidate["lexical_score"],
                    score
                )
                candidate["sources"].add("lexical")

    def _merge_vector(self, candidates, vector_results):
        ids = vector_results.get("ids", [[]])[0]
        metadatas = vector_results.get("metadatas", [[]])[0]
        distances = vector_results.get("distances", [[]])[0]

        for document_id, metadata, distance in zip(ids, metadatas, distances):
            record = self.metadata_index.by_id.get(document_id, metadata)
            candidate = self._candidate(candidates, record)

            score = 1 / (1 + max(distance, 0))

            candidate["vector_score"] = max(
                candidate["vector_score"],
                score
            )
            candidate["vector_distance"] = min(
                candidate["vector_distance"],
                distance
            )
            candidate["sources"].add("vector")

    def _merge_graph(self, candidates, graph_depth):
        seed_records = [
            candidate["metadata"]
            for candidate in list(candidates.values())
            if candidate["lexical_score"] > 0 or candidate["vector_score"] > 0
        ]

        for record in seed_records:
            for related_record, score in self._related_records(
                record,
                graph_depth=graph_depth
            ):
                candidate = self._candidate(candidates, related_record)
                candidate["graph_score"] = max(
                    candidate["graph_score"],
                    score
                )
                candidate["sources"].add("graph")

    def _related_records(self, record, graph_depth):
        document_type = record.get("document_type")
        related = []

        if document_type == "unit":
            unit_name = record.get("unit") or record.get("name")
            neighbours = (
                self.graph_api.dependencies(unit_name)
                + self.graph_api.dependents(unit_name)
            )

            for neighbour in neighbours:
                for item in self.metadata_index.unit_documents(neighbour):
                    related.append((item, 0.75))

            if graph_depth > 1:
                for item in self.graph_api.transitive_dependencies(
                    unit_name,
                    max_depth=graph_depth
                ):
                    score = 0.5 / item["depth"]

                    for document in self.metadata_index.unit_documents(
                        item["node"]
                    ):
                        related.append((document, score))

        if document_type == "class":
            class_name = record.get("class_name") or record.get("name")
            neighbours = list(self.graph_api.children(class_name))
            parent = self.graph_api.parent(class_name)

            if parent:
                neighbours.append(parent)

            for neighbour in neighbours:
                for item in self.metadata_index.class_documents(neighbour):
                    related.append((item, 0.75))

        if document_type == "method":
            method_name = record.get("method_name") or record.get("name")
            neighbours = (
                self.graph_api.callers(method_name)
                + self.graph_api.callees(method_name)
            )

            for neighbour in neighbours:
                for item in self.metadata_index.method_documents(neighbour):
                    related.append((item, 0.65))

        return related

    def _candidate(self, candidates, record):
        document_id = record.get("document_id")

        if document_id not in candidates:
            candidates[document_id] = {
                "metadata": record,
                "lexical_score": 0.0,
                "vector_score": 0.0,
                "graph_score": 0.0,
                "vector_distance": float("inf"),
                "sources": set()
            }

        return candidates[document_id]

    def _finalize_candidate(self, candidate):
        metadata = candidate["metadata"]
        lexical_score = candidate["lexical_score"]
        vector_score = candidate["vector_score"]
        graph_score = candidate["graph_score"]
        score = (
            lexical_score * self.weights.lexical
            + vector_score * self.weights.vector
            + graph_score * self.weights.graph
        )

        vector_distance = candidate["vector_distance"]

        if vector_distance == float("inf"):
            vector_distance = None

        return {
            "document_id": metadata.get("document_id"),
            "document_type": metadata.get("document_type"),
            "name": metadata.get("name"),
            "unit": metadata.get("unit"),
            "class_name": metadata.get("class_name"),
            "method_name": metadata.get("method_name"),
            "file": metadata.get("file"),
            "score": round(score, 6),
            "scores": {
                "lexical": round(lexical_score, 6),
                "vector": round(vector_score, 6),
                "graph": round(graph_score, 6)
            },
            "vector_distance": vector_distance,
            "sources": sorted(candidate["sources"])
        }

    def _document_types_to_symbol_types(self, document_types):
        if document_types is None:
            return None

        requested = self._normalize_document_types(document_types)
        symbol_types = {
            document_type
            for document_type in requested
            if document_type in {"unit", "class", "method"}
        }

        if not symbol_types:
            return None

        return symbol_types

    def _document_type_filter(self, document_types):
        if document_types is None:
            return None

        requested = sorted(self._normalize_document_types(document_types))

        if len(requested) == 1:
            return {
                "document_type": requested[0]
            }

        return {
            "document_type": {
                "$in": requested
            }
        }

    def _normalize_document_types(self, document_types):
        if isinstance(document_types, str):
            return {document_types.casefold()}

        return {
            document_type.casefold()
            for document_type in document_types
        }
