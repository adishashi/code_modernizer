"""
Semantic intelligence APIs.
"""

from .embeddings import (
    EmbeddingDocument,
    LocalHashingEmbeddingProvider,
    RepositoryEmbeddingDocumentBuilder,
    RepositoryEmbeddingGenerator,
    generate_repository_embeddings
)
from .hybrid_retrieval import (
    EmbeddingMetadataIndex,
    HybridRetriever,
    HybridRetrievalWeights
)
from .semantic_search import SemanticSearchEngine, SummaryIndex

__all__ = [
    "EmbeddingDocument",
    "EmbeddingMetadataIndex",
    "HybridRetriever",
    "HybridRetrievalWeights",
    "LocalHashingEmbeddingProvider",
    "RepositoryEmbeddingDocumentBuilder",
    "RepositoryEmbeddingGenerator",
    "SemanticSearchEngine",
    "SummaryIndex",
    "generate_repository_embeddings"
]
