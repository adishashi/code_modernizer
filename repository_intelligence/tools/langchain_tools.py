"""
langchain_tools.py

Thin LangChain wrappers around Repository APIs.

Business logic stays in repository_intelligence. These tools only adapt typed
tool arguments into calls on Repository, GraphAPI, RepositorySearch, and
ContextBuilder.
"""

from typing import List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

try:
    from ..context_builder import ContextBuilder
    from ..graph_api import GraphAPI
    from ..loader import load_repository
    from ..modernization import ModernizationAnalyzer
    from ..repository import Repository
    from ..search import RepositorySearch
except ImportError:
    from context_builder import ContextBuilder
    from graph_api import GraphAPI
    from loader import load_repository
    from repository_intelligence.modernization import ModernizationAnalyzer
    from repository import Repository
    from search import RepositorySearch


class UnitNameInput(BaseModel):
    unit_name: str = Field(
        ...,
        description="Pascal unit name."
    )


class FileInput(BaseModel):
    path_or_unit: str = Field(
        ...,
        description="Repository-relative source file path or Pascal unit name."
    )


class ClassNameInput(BaseModel):
    class_name: str = Field(
        ...,
        description="Pascal class name."
    )


class MethodNameInput(BaseModel):
    method_name: str = Field(
        ...,
        description="Method or procedure name. Qualified names are accepted."
    )


class FindMethodInput(BaseModel):
    method_name: str = Field(
        ...,
        description="Method or procedure name. Qualified names are accepted."
    )
    class_name: Optional[str] = Field(
        None,
        description="Optional class filter."
    )
    unit_name: Optional[str] = Field(
        None,
        description="Optional unit filter."
    )


class SearchSymbolsInput(BaseModel):
    query: str = Field(
        ...,
        description="Symbol search text."
    )
    symbol_types: Optional[List[str]] = Field(
        None,
        description="Optional list containing unit, file, class, or method."
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of results."
    )


class TraversalInput(BaseModel):
    name: str = Field(
        ...,
        description="Unit, class, or method name depending on the tool."
    )
    max_depth: int = Field(
        2,
        ge=1,
        le=10,
        description="Maximum graph traversal depth."
    )


class ExecutionPathInput(BaseModel):
    start_method: str = Field(
        ...,
        description="Starting caller method name."
    )
    target_method: str = Field(
        ...,
        description="Target callee method name."
    )
    max_depth: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum path length to explore."
    )
    limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum number of paths to return."
    )


class ContextInput(BaseModel):
    query: str = Field(
        ...,
        description="Repository question or symbol search text."
    )
    limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum search results to include."
    )
    max_graph_depth: int = Field(
        1,
        ge=1,
        le=5,
        description="Graph expansion depth."
    )


class ModernizationSymbolInput(BaseModel):
    symbol: str = Field(
        ...,
        description="Unit, class, method, or feature symbol to analyze."
    )
    max_depth: int = Field(
        2,
        ge=1,
        le=5,
        description="Maximum graph traversal depth."
    )
    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Maximum lexical matches to include."
    )


class ModernizationPatternInput(BaseModel):
    query: str = Field(
        ...,
        description="Pattern, API, class, method, or feature text to locate."
    )
    symbol_types: Optional[List[str]] = Field(
        None,
        description="Optional list containing unit, file, class, or method."
    )
    limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum candidate patterns to return."
    )


class MigrationContextInput(BaseModel):
    task: str = Field(
        ...,
        description="Modernization task or natural-language migration query."
    )
    target_language: str = Field(
        "Java",
        description="Target implementation language."
    )
    limit: int = Field(
        8,
        ge=1,
        le=25,
        description="Maximum retrieval results from each retrieval layer."
    )
    graph_depth: int = Field(
        1,
        ge=0,
        le=3,
        description="Graph expansion depth."
    )
    document_types: Optional[List[str]] = Field(
        None,
        description="Optional document types: unit, class, method, subsystem."
    )
    include_source: bool = Field(
        True,
        description="Whether to include bounded Pascal source snippets."
    )
    max_snippet_lines: int = Field(
        80,
        ge=1,
        le=200,
        description="Maximum source lines per snippet."
    )


class MigrationPromptInput(BaseModel):
    task: str = Field(
        ...,
        description="Modernization task or natural-language migration query."
    )
    target_language: str = Field(
        "Java",
        description="Target implementation language."
    )
    limit: int = Field(
        5,
        ge=1,
        le=25,
        description="Maximum retrieval results from each retrieval layer."
    )
    graph_depth: int = Field(
        1,
        ge=0,
        le=3,
        description="Graph expansion depth."
    )
    document_types: Optional[List[str]] = Field(
        None,
        description="Optional document types: unit, class, method, subsystem."
    )
    include_source: bool = Field(
        True,
        description="Whether to include Pascal source in the prompt."
    )
    max_source_lines: int = Field(
        160,
        ge=1,
        le=500,
        description="Maximum source lines per extracted source item."
    )
    max_source_chars: int = Field(
        12000,
        ge=500,
        le=100000,
        description="Maximum source characters included in prompt text."
    )


class MigrationCodeGenerationInput(BaseModel):
    task: str = Field(
        ...,
        description="Modernization task or natural-language migration query."
    )
    target_language: str = Field(
        "Java",
        description="Target implementation language."
    )
    limit: int = Field(
        5,
        ge=1,
        le=25,
        description="Maximum retrieval results from each retrieval layer."
    )
    graph_depth: int = Field(
        1,
        ge=0,
        le=3,
        description="Graph expansion depth."
    )
    document_types: Optional[List[str]] = Field(
        None,
        description="Optional document types: unit, class, method, subsystem."
    )
    include_source: bool = Field(
        True,
        description="Whether to include Pascal source in the prompt."
    )
    max_source_lines: int = Field(
        160,
        ge=1,
        le=500,
        description="Maximum source lines per extracted source item."
    )
    validation_enabled: bool = Field(
        False,
        description="Whether to validate generated Java output."
    )
    compile_validation: bool = Field(
        False,
        description="Whether to compile generated Java with javac when available."
    )
    output_directory: Optional[str] = Field(
        None,
        description="Optional directory where generated Java files are persisted."
    )
    overwrite_files: bool = Field(
        True,
        description="Whether persisted generated Java files may overwrite existing files."
    )


class NoInput(BaseModel):
    pass


def create_repository_tools(
    repository,
    artifacts_directory="output/embeddings",
    persist_directory="output/chroma",
    summary_directory="output/summaries",
    source_root="doublecmd",
    collection_name="repository_intelligence"
):
    """
    Create LangChain StructuredTool instances for a Repository.
    """

    graph_api = GraphAPI(repository)
    search = RepositorySearch(repository)
    context_builder = ContextBuilder(
        repository,
        graph_api=graph_api,
        search=search
    )
    modernization = ModernizationAnalyzer(
        repository,
        artifacts_directory=artifacts_directory,
        persist_directory=persist_directory,
        summary_directory=summary_directory,
        source_root=source_root,
        collection_name=collection_name
    )

    def find_unit(unit_name: str):
        return repository.find_unit(unit_name)

    def find_file(path_or_unit: str):
        return {
            "query": path_or_unit,
            "result": repository.find_file(path_or_unit)
        }

    def find_class(class_name: str):
        return repository.find_classes(class_name)

    def find_method(
        method_name: str,
        class_name: Optional[str] = None,
        unit_name: Optional[str] = None
    ):
        return repository.find_methods(
            method_name,
            class_name=class_name,
            unit_name=unit_name
        )

    def find_dependencies(unit_name: str):
        return repository.get_dependencies(unit_name)

    def find_dependents(unit_name: str):
        return repository.get_dependents(unit_name)

    def find_parent(class_name: str):
        return {
            "class": class_name,
            "parent": repository.get_parent(class_name)
        }

    def find_children(class_name: str):
        return repository.get_children(class_name)

    def find_callers(method_name: str):
        return repository.get_callers(method_name)

    def find_callees(method_name: str):
        return repository.get_callees(method_name)

    def transitive_dependencies(name: str, max_depth: int = 2):
        return graph_api.transitive_dependencies(
            name,
            max_depth=max_depth
        )

    def transitive_dependents(name: str, max_depth: int = 2):
        return graph_api.transitive_dependents(
            name,
            max_depth=max_depth
        )

    def transitive_callers(name: str, max_depth: int = 2):
        return graph_api.transitive_callers(
            name,
            max_depth=max_depth
        )

    def transitive_callees(name: str, max_depth: int = 2):
        return graph_api.transitive_callees(
            name,
            max_depth=max_depth
        )

    def execution_path(
        start_method: str,
        target_method: str,
        max_depth: int = 5,
        limit: int = 10
    ):
        return graph_api.execution_paths(
            start_method,
            target_method,
            max_depth=max_depth,
            limit=limit
        )

    def impact_analysis(name: str, max_depth: int = 2):
        return graph_api.impact_analysis(
            name,
            max_depth=max_depth
        )

    def search_symbols(
        query: str,
        symbol_types: Optional[List[str]] = None,
        limit: int = 10
    ):
        return search.search_symbols(
            query,
            symbol_types=symbol_types,
            limit=limit
        )

    def build_context(
        query: str,
        limit: int = 10,
        max_graph_depth: int = 1
    ):
        return context_builder.build_query_context(
            query,
            limit=limit,
            max_graph_depth=max_graph_depth
        )

    def render_context(
        query: str,
        limit: int = 10,
        max_graph_depth: int = 1
    ):
        context = context_builder.build_query_context(
            query,
            limit=limit,
            max_graph_depth=max_graph_depth
        )

        return context_builder.render_context(context)

    def repository_statistics():
        return repository.statistics()

    def find_affected_code(
        symbol: str,
        max_depth: int = 2,
        limit: int = 25
    ):
        return modernization.find_affected_code(
            symbol,
            max_depth=max_depth,
            limit=limit
        )

    def trace_dependencies(
        symbol: str,
        max_depth: int = 2,
        limit: int = 25
    ):
        return modernization.trace_dependencies(
            symbol,
            max_depth=max_depth
        )

    def locate_equivalent_patterns(
        query: str,
        symbol_types: Optional[List[str]] = None,
        limit: int = 10
    ):
        return modernization.locate_equivalent_patterns(
            query,
            symbol_types=symbol_types,
            limit=limit
        )

    def estimate_change_impact(
        symbol: str,
        max_depth: int = 2,
        limit: int = 25
    ):
        return modernization.estimate_change_impact(
            symbol,
            max_depth=max_depth
        )

    def produce_migration_context(
        task: str,
        target_language: str = "Java",
        limit: int = 8,
        graph_depth: int = 1,
        document_types: Optional[List[str]] = None,
        include_source: bool = True,
        max_snippet_lines: int = 80
    ):
        return modernization.produce_migration_context(
            task,
            target_language=target_language,
            limit=limit,
            graph_depth=graph_depth,
            document_types=document_types,
            include_source=include_source,
            max_snippet_lines=max_snippet_lines
        )

    def produce_migration_prompt(
        task: str,
        target_language: str = "Java",
        limit: int = 5,
        graph_depth: int = 1,
        document_types: Optional[List[str]] = None,
        include_source: bool = True,
        max_source_lines: int = 160,
        max_source_chars: int = 12000
    ):
        return modernization.produce_migration_prompt(
            task,
            target_language=target_language,
            limit=limit,
            graph_depth=graph_depth,
            document_types=document_types,
            include_source=include_source,
            max_source_lines=max_source_lines,
            max_source_chars=max_source_chars
        )

    def generate_migration_code(
        task: str,
        target_language: str = "Java",
        limit: int = 5,
        graph_depth: int = 1,
        document_types: Optional[List[str]] = None,
        include_source: bool = True,
        max_source_lines: int = 160,
        validation_enabled: bool = False,
        compile_validation: bool = False,
        output_directory: Optional[str] = None,
        overwrite_files: bool = True
    ):
        return modernization.generate_migration_code(
            task,
            target_language=target_language,
            limit=limit,
            graph_depth=graph_depth,
            document_types=document_types,
            include_source=include_source,
            max_source_lines=max_source_lines,
            validate=validation_enabled,
            compile_validation=compile_validation,
            output_directory=output_directory,
            overwrite=overwrite_files
        )

    return [
        StructuredTool.from_function(
            func=find_unit,
            name="find_unit",
            description="Find a Pascal unit by name.",
            args_schema=UnitNameInput
        ),
        StructuredTool.from_function(
            func=find_file,
            name="find_file",
            description="Find a source file by path or unit name.",
            args_schema=FileInput
        ),
        StructuredTool.from_function(
            func=find_class,
            name="find_class",
            description="Find class declarations by class name.",
            args_schema=ClassNameInput
        ),
        StructuredTool.from_function(
            func=find_method,
            name="find_method",
            description="Find method definitions by method name.",
            args_schema=FindMethodInput
        ),
        StructuredTool.from_function(
            func=find_dependencies,
            name="find_dependencies",
            description="List direct unit dependencies.",
            args_schema=UnitNameInput
        ),
        StructuredTool.from_function(
            func=find_dependents,
            name="find_dependents",
            description="List units that directly depend on a unit.",
            args_schema=UnitNameInput
        ),
        StructuredTool.from_function(
            func=find_parent,
            name="find_parent",
            description="Find the direct parent class of a class.",
            args_schema=ClassNameInput
        ),
        StructuredTool.from_function(
            func=find_children,
            name="find_children",
            description="Find direct child classes of a class.",
            args_schema=ClassNameInput
        ),
        StructuredTool.from_function(
            func=find_callers,
            name="find_callers",
            description="Find direct callers of a method.",
            args_schema=MethodNameInput
        ),
        StructuredTool.from_function(
            func=find_callees,
            name="find_callees",
            description="Find direct callees of a method.",
            args_schema=MethodNameInput
        ),
        StructuredTool.from_function(
            func=transitive_dependencies,
            name="transitive_dependencies",
            description="Traverse unit dependencies to a bounded depth.",
            args_schema=TraversalInput
        ),
        StructuredTool.from_function(
            func=transitive_dependents,
            name="transitive_dependents",
            description="Traverse reverse unit dependencies to a bounded depth.",
            args_schema=TraversalInput
        ),
        StructuredTool.from_function(
            func=transitive_callers,
            name="transitive_callers",
            description="Traverse method callers to a bounded depth.",
            args_schema=TraversalInput
        ),
        StructuredTool.from_function(
            func=transitive_callees,
            name="transitive_callees",
            description="Traverse method callees to a bounded depth.",
            args_schema=TraversalInput
        ),
        StructuredTool.from_function(
            func=execution_path,
            name="execution_path",
            description="Find bounded static call paths between two methods.",
            args_schema=ExecutionPathInput
        ),
        StructuredTool.from_function(
            func=impact_analysis,
            name="impact_analysis",
            description="Return structural impact context for a symbol.",
            args_schema=TraversalInput
        ),
        StructuredTool.from_function(
            func=search_symbols,
            name="search_symbols",
            description="Search units, files, classes, and methods.",
            args_schema=SearchSymbolsInput
        ),
        StructuredTool.from_function(
            func=build_context,
            name="build_context",
            description="Build structured repository context for a query.",
            args_schema=ContextInput
        ),
        StructuredTool.from_function(
            func=render_context,
            name="render_context",
            description="Build and render repository context as text.",
            args_schema=ContextInput
        ),
        StructuredTool.from_function(
            func=repository_statistics,
            name="repository_statistics",
            description="Return repository index statistics.",
            args_schema=NoInput
        ),
        StructuredTool.from_function(
            func=find_affected_code,
            name="find_affected_code",
            description="Find indexed code affected by changing a symbol.",
            args_schema=ModernizationSymbolInput
        ),
        StructuredTool.from_function(
            func=trace_dependencies,
            name="trace_dependencies",
            description="Trace dependency, inheritance, and call relationships for a symbol.",
            args_schema=ModernizationSymbolInput
        ),
        StructuredTool.from_function(
            func=locate_equivalent_patterns,
            name="locate_equivalent_patterns",
            description="Locate similar indexed symbols that may serve as migration patterns.",
            args_schema=ModernizationPatternInput
        ),
        StructuredTool.from_function(
            func=estimate_change_impact,
            name="estimate_change_impact",
            description="Estimate change impact and migration risk for a symbol.",
            args_schema=ModernizationSymbolInput
        ),
        StructuredTool.from_function(
            func=produce_migration_context,
            name="produce_migration_context",
            description="Produce hybrid modernization context for a migration task.",
            args_schema=MigrationContextInput
        ),
        StructuredTool.from_function(
            func=produce_migration_prompt,
            name="produce_migration_prompt",
            description="Produce an LLM-ready modernization prompt package.",
            args_schema=MigrationPromptInput
        ),
        StructuredTool.from_function(
            func=generate_migration_code,
            name="generate_migration_code",
            description="Generate Java migration output using the configured code generation backend.",
            args_schema=MigrationCodeGenerationInput
        )
    ]


def load_repository_tools(output_directory, **tool_options):
    """
    Load repository artifacts and create LangChain tools.
    """

    repository = Repository(
        load_repository(output_directory)
    )

    return create_repository_tools(repository, **tool_options)
