"""
Repository intelligence public API.
"""

from importlib import import_module

from .context_builder import ContextBuilder
from .semantic.embeddings import (
    EmbeddingDocument,
    LocalHashingEmbeddingProvider,
    RepositoryEmbeddingDocumentBuilder,
    RepositoryEmbeddingGenerator,
    generate_repository_embeddings
)
from .graph_api import GraphAPI
from .semantic.hybrid_retrieval import (
    EmbeddingMetadataIndex,
    HybridRetriever,
    HybridRetrievalWeights
)
from .loader import RepositoryLoader, load_repository
from .modernization import (
    ModernizationAnalyzer,
    ModernizationContextAssembler,
    PascalSourceExtractor,
    SourceSnippetExtractor,
    SummaryLookup as ModernizationSummaryLookup,
    build_modernization_context
)
from .repository import Repository
from .search import RepositorySearch
from .semantic.semantic_search import SemanticSearchEngine, SummaryIndex
from .symbol_table import SymbolTable
from .summaries import (
    RepositorySummarizer,
    SummaryArtifactWriter,
    SummaryRecord,
    generate_repository_summaries
)
from .chroma.vector_store import (
    ChromaRepositoryVectorStore,
    EmbeddingArtifactReader,
    ingest_chroma_artifacts
)

__all__ = [
    "ContextBuilder",
    "EmbeddingDocument",
    "GraphAPI",
    "ChromaRepositoryVectorStore",
    "EmbeddingArtifactReader",
    "EmbeddingMetadataIndex",
    "DryRunFileGenerationBackend",
    "FileMigrationArtifactWriter",
    "FileMigrationBatchGenerator",
    "FileMigrationPlanner",
    "FileMigrationPromptBuilder",
    "FileMigrationPromptGenerator",
    "HybridRetriever",
    "HybridRetrievalWeights",
    "LocalHashingEmbeddingProvider",
    "JavaDesignTemplate",
    "JavaSharedSupportCatalog",
    "JavaSharedSupportFile",
    "JavaTargetDesignTemplates",
    "GeneratedJavaValidator",
    "GeneratedJavaFileWriter",
    "ModernizationAnalyzer",
    "ModernizationContextAssembler",
    "ModernizationSummaryLookup",
    "ModernizationPromptBuilder",
    "ModernizationPromptGenerator",
    "PascalSourceExtractor",
    "Repository",
    "REPOSITORY_AGENT_SYSTEM_PROMPT",
    "RepositoryAgentMemory",
    "RepositoryEmbeddingDocumentBuilder",
    "RepositoryEmbeddingGenerator",
    "RepositoryIntelligenceAgent",
    "RepositoryLoader",
    "RepositorySearch",
    "RepositorySummarizer",
    "SemanticSearchEngine",
    "SourceSnippetExtractor",
    "SymbolTable",
    "SummaryArtifactWriter",
    "SummaryIndex",
    "SummaryRecord",
    "build_modernization_context",
    "build_file_migration_plan",
    "create_repository_agent",
    "create_repository_langchain_agent",
    "create_repository_tools",
    "generate_repository_embeddings",
    "generate_repository_summaries",
    "ingest_chroma_artifacts",
    "load_repository_tools",
    "load_repository_agent",
    "load_repository",
    "validate_generated_code",
    "write_generated_java_files",
]


def __getattr__(name):
    agent_exports = {
        "DryRunCodeGenerationBackend",
        "DryRunFileGenerationBackend",
        "FileMigrationArtifactWriter",
        "FileMigrationBatchGenerator",
        "FileMigrationPlanner",
        "FileMigrationPromptBuilder",
        "FileMigrationPromptGenerator",
        "GeneratedJavaFileWriter",
        "GeneratedJavaValidator",
        "JavaDesignTemplate",
        "JavaSharedSupportCatalog",
        "JavaSharedSupportFile",
        "JavaTargetDesignTemplates",
        "LangChainCodeGenerationBackend",
        "ModernizationCodeGenerator",
        "ModernizationPromptBuilder",
        "ModernizationPromptGenerator",
        "REPOSITORY_AGENT_SYSTEM_PROMPT",
        "RepositoryAgentMemory",
        "RepositoryIntelligenceAgent",
        "create_repository_agent",
        "create_repository_langchain_agent",
        "create_repository_tools",
        "build_file_migration_plan",
        "load_repository_agent",
        "load_repository_tools",
        "validate_generated_code",
        "write_generated_java_files"
    }

    if name in agent_exports:
        if name in {"JavaDesignTemplate", "JavaTargetDesignTemplates"}:
            module = import_module(".modernization.java_templates", __name__)
            return getattr(module, name)

        if name in {"JavaSharedSupportCatalog", "JavaSharedSupportFile"}:
            module = import_module(".modernization.shared_support", __name__)
            return getattr(module, name)

        if name in {
            "FileMigrationPromptBuilder",
            "FileMigrationPromptGenerator",
            "ModernizationPromptBuilder",
            "ModernizationPromptGenerator"
        }:
            module = import_module(".modernization.prompts", __name__)
            return getattr(module, name)

        file_migration_exports = {
            "FileMigrationPlanner",
            "build_file_migration_plan"
        }

        if name in file_migration_exports:
            module = import_module(".modernization.file_migration", __name__)
            return getattr(module, name)

        file_generation_exports = {
            "DryRunFileGenerationBackend",
            "FileMigrationArtifactWriter",
            "FileMigrationBatchGenerator"
        }

        if name in file_generation_exports:
            module = import_module(".modernization.file_generation", __name__)
            return getattr(module, name)

        generation_exports = {
            "DryRunCodeGenerationBackend",
            "GeneratedJavaFileWriter",
            "LangChainCodeGenerationBackend",
            "ModernizationCodeGenerator",
            "write_generated_java_files"
        }

        if name in generation_exports:
            module = import_module(".modernization.generation", __name__)
            return getattr(module, name)

        validation_exports = {
            "GeneratedJavaValidator",
            "validate_generated_code"
        }

        if name in validation_exports:
            module = import_module(".modernization.validation", __name__)
            return getattr(module, name)

        if name in {"create_repository_tools", "load_repository_tools"}:
            module = import_module(".tools", __name__)
            return getattr(module, name)

        module = import_module(".agent", __name__)
        return getattr(module, name)

    raise AttributeError(name)
