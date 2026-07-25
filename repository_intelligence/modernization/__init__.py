"""
Modernization-specific repository context assembly.
"""

from importlib import import_module

from .context import (
    ModernizationContextAssembler,
    SourceSnippetExtractor,
    SummaryLookup,
    build_modernization_context
)
from .analysis import ModernizationAnalyzer
from .source_extractor import PascalSourceExtractor

__all__ = [
    "JavaDesignTemplate",
    "JavaSharedSupportCatalog",
    "JavaSharedSupportFile",
    "JavaTargetDesignTemplates",
    "FileMigrationPlanner",
    "FileMigrationArtifactWriter",
    "FileMigrationBatchGenerator",
    "DryRunFileGenerationBackend",
    "FileMigrationPromptBuilder",
    "FileMigrationPromptGenerator",
    "MigrationDashboardBuilder",
    "ModernizationAnalyzer",
    "ModernizationContextAssembler",
    "ModernizationPromptBuilder",
    "ModernizationPromptGenerator",
    "GeneratedJavaValidator",
    "GeneratedJavaFileWriter",
    "PascalSourceExtractor",
    "SourceSnippetExtractor",
    "SummaryLookup",
    "build_modernization_context",
    "build_file_migration_plan",
    "validate_generated_code",
    "write_generated_java_files"
]


def __getattr__(name):
    if name in {"JavaDesignTemplate", "JavaTargetDesignTemplates"}:
        module = import_module(".java_templates", __name__)
        return getattr(module, name)

    if name in {"JavaSharedSupportCatalog", "JavaSharedSupportFile"}:
        module = import_module(".shared_support", __name__)
        return getattr(module, name)

    if name in {
        "FileMigrationPromptBuilder",
        "FileMigrationPromptGenerator",
        "ModernizationPromptBuilder",
        "ModernizationPromptGenerator"
    }:
        module = import_module(".prompts", __name__)
        return getattr(module, name)

    file_migration_exports = {
        "FileMigrationPlanner",
        "build_file_migration_plan"
    }

    if name in file_migration_exports:
        module = import_module(".file_migration", __name__)
        return getattr(module, name)

    file_generation_exports = {
        "DryRunFileGenerationBackend",
        "FileMigrationArtifactWriter",
        "FileMigrationBatchGenerator"
    }

    if name in file_generation_exports:
        module = import_module(".file_generation", __name__)
        return getattr(module, name)

    dashboard_exports = {
        "MigrationDashboardBuilder"
    }

    if name in dashboard_exports:
        module = import_module(".dashboard", __name__)
        return getattr(module, name)

    generation_exports = {
        "DryRunCodeGenerationBackend",
        "GeneratedJavaFileWriter",
        "LangChainCodeGenerationBackend",
        "ModernizationCodeGenerator",
        "write_generated_java_files"
    }

    if name in generation_exports:
        module = import_module(".generation", __name__)
        return getattr(module, name)

    validation_exports = {
        "GeneratedJavaValidator",
        "validate_generated_code"
    }

    if name in validation_exports:
        module = import_module(".validation", __name__)
        return getattr(module, name)

    raise AttributeError(name)
