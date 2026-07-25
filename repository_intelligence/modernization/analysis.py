"""
Modernization-oriented repository analysis helpers.

These helpers are intentionally independent of LangChain. Tool wrappers should
delegate here so modernization behavior remains testable through normal Python
APIs and reusable by future agents.
"""

try:
    from ..graph_api import GraphAPI
    from ..search import RepositorySearch
    from .context import ModernizationContextAssembler
except ImportError:
    from repository_intelligence.graph_api import GraphAPI
    from repository_intelligence.search import RepositorySearch
    from repository_intelligence.modernization.context import (
        ModernizationContextAssembler
    )


class ModernizationAnalyzer:
    """
    Provides bounded modernization analyses over repository metadata.

    The methods favor compact, structured outputs because agents can decide how
    much detail to include in a final migration prompt or developer report.
    """

    def __init__(
        self,
        repository,
        artifacts_directory="output/embeddings",
        persist_directory="output/chroma",
        summary_directory="output/summaries",
        source_root="doublecmd",
        collection_name="repository_intelligence"
    ):
        self.repository = repository
        self.graph_api = GraphAPI(repository)
        self.search = RepositorySearch(repository)
        self.artifacts_directory = artifacts_directory
        self.persist_directory = persist_directory
        self.summary_directory = summary_directory
        self.source_root = source_root
        self.collection_name = collection_name

    def find_affected_code(self, symbol, max_depth=2, limit=25):
        matches = self.search.search_symbols(symbol, limit=limit)
        impact = self.graph_api.impact_analysis(
            symbol,
            max_depth=max_depth
        )

        affected = {
            "units": self._unit_records(
                item["node"]
                for item in impact.get("dependent_units", [])
            ),
            "classes": self._class_records(
                item["class"]
                for item in impact.get("children", [])
            ),
            "methods": self._method_records(
                item["node"]
                for item in impact.get("callers", [])
            )
        }

        return {
            "symbol": symbol,
            "matches": matches,
            "impact": impact,
            "affected_code": affected,
            "statistics": {
                "affected_units": len(affected["units"]),
                "affected_classes": len(affected["classes"]),
                "affected_methods": len(affected["methods"])
            }
        }

    def trace_dependencies(self, symbol, max_depth=2):
        return {
            "symbol": symbol,
            "unit": self._trace_unit(symbol, max_depth),
            "class": self._trace_class(symbol, max_depth),
            "method": self._trace_method(symbol, max_depth)
        }

    def locate_equivalent_patterns(
        self,
        query,
        limit=10,
        symbol_types=None
    ):
        results = self.search.search_symbols(
            query,
            symbol_types=symbol_types,
            limit=limit
        )
        groups = {
            "unit": [],
            "file": [],
            "class": [],
            "method": []
        }

        for result in results:
            result_type = result.get("type")

            if result_type in groups:
                groups[result_type].append(result)

        return {
            "query": query,
            "results": results,
            "groups": groups,
            "notes": [
                "Equivalent patterns are lexical candidates until semantic "
                "pattern mining is added.",
                "Prefer results with matching type and unit boundaries before "
                "using them as migration templates."
            ]
        }

    def estimate_change_impact(self, symbol, max_depth=2):
        affected = self.find_affected_code(
            symbol,
            max_depth=max_depth
        )
        stats = affected["statistics"]
        total = (
            stats["affected_units"]
            + stats["affected_classes"]
            + stats["affected_methods"]
        )
        severity = self._severity(total)

        return {
            "symbol": symbol,
            "severity": severity,
            "affected_counts": stats,
            "risk_notes": self._risk_notes(affected, total),
            "affected_code": affected["affected_code"]
        }

    def produce_migration_context(
        self,
        task,
        target_language="Java",
        limit=8,
        graph_depth=1,
        document_types=None,
        include_source=True,
        max_snippet_lines=80
    ):
        assembler = ModernizationContextAssembler(
            self.repository,
            artifacts_directory=self.artifacts_directory,
            persist_directory=self.persist_directory,
            summary_directory=self.summary_directory,
            source_root=self.source_root,
            collection_name=self.collection_name
        )

        try:
            return assembler.build_context(
                task,
                target_language=target_language,
                limit=limit,
                graph_depth=graph_depth,
                document_types=document_types,
                include_source=include_source,
                max_snippet_lines=max_snippet_lines
            )
        finally:
            assembler.close()

    def produce_migration_prompt(
        self,
        task,
        target_language="Java",
        limit=8,
        graph_depth=1,
        document_types=None,
        include_source=True,
        max_source_lines=160,
        max_source_chars=12000
    ):
        try:
            from .prompts import (
                ModernizationPromptBuilder,
                ModernizationPromptGenerator
            )
        except ImportError:
            from repository_intelligence.modernization.prompts import (
                ModernizationPromptBuilder,
                ModernizationPromptGenerator
            )

        generator = ModernizationPromptGenerator(
            self.repository,
            context_options={
                "artifacts_directory": self.artifacts_directory,
                "persist_directory": self.persist_directory,
                "summary_directory": self.summary_directory,
                "source_root": self.source_root,
                "collection_name": self.collection_name
            },
            prompt_builder=ModernizationPromptBuilder(
                max_source_chars=max_source_chars
            )
        )

        return generator.generate(
            task,
            target_language=target_language,
            limit=limit,
            graph_depth=graph_depth,
            document_types=document_types,
            include_source=include_source,
            max_source_lines=max_source_lines
        )

    def generate_migration_code(
        self,
        task,
        target_language="Java",
        limit=5,
        graph_depth=1,
        document_types=None,
        include_source=True,
        max_source_lines=160,
        backend=None,
        validate=False,
        compile_validation=False,
        output_directory=None,
        overwrite=True
    ):
        try:
            from .generation import (
                DryRunCodeGenerationBackend,
                ModernizationCodeGenerator
            )
        except ImportError:
            from repository_intelligence.modernization.generation import (
                DryRunCodeGenerationBackend,
                ModernizationCodeGenerator
            )

        generator = ModernizationCodeGenerator(
            self.repository,
            backend=backend or DryRunCodeGenerationBackend(),
            context_options={
                "artifacts_directory": self.artifacts_directory,
                "persist_directory": self.persist_directory,
                "summary_directory": self.summary_directory,
                "source_root": self.source_root,
                "collection_name": self.collection_name
            }
        )

        return generator.generate(
            task,
            target_language=target_language,
            limit=limit,
            graph_depth=graph_depth,
            document_types=document_types,
            include_source=include_source,
            max_source_lines=max_source_lines,
            validate=validate,
            compile_validation=compile_validation,
            output_directory=output_directory,
            overwrite=overwrite
        )

    def _trace_unit(self, symbol, max_depth):
        unit = self.repository.find_unit(symbol)

        if not unit:
            return None

        return {
            "record": unit,
            "dependencies": self.graph_api.dependencies(symbol),
            "dependents": self.graph_api.dependents(symbol),
            "transitive_dependencies": self.graph_api.transitive_dependencies(
                symbol,
                max_depth=max_depth
            ),
            "transitive_dependents": self.graph_api.transitive_dependents(
                symbol,
                max_depth=max_depth
            )
        }

    def _trace_class(self, symbol, max_depth):
        classes = self.repository.find_classes(symbol)

        if not classes:
            return None

        return {
            "records": classes,
            "parent": self.graph_api.parent(symbol),
            "children": self.graph_api.children(symbol),
            "ancestors": self.graph_api.ancestors(
                symbol,
                max_depth=max_depth
            ),
            "descendants": self.graph_api.descendants(
                symbol,
                max_depth=max_depth
            )
        }

    def _trace_method(self, symbol, max_depth):
        methods = self.repository.find_methods(symbol)

        if not methods:
            return None

        return {
            "records": methods,
            "callers": self.graph_api.callers(symbol),
            "callees": self.graph_api.callees(symbol),
            "transitive_callers": self.graph_api.transitive_callers(
                symbol,
                max_depth=max_depth
            ),
            "transitive_callees": self.graph_api.transitive_callees(
                symbol,
                max_depth=max_depth
            )
        }

    def _unit_records(self, unit_names):
        return [
            record
            for record in (
                self.repository.find_unit(unit_name)
                for unit_name in unit_names
            )
            if record
        ]

    def _class_records(self, class_names):
        records = []

        for class_name in class_names:
            records.extend(self.repository.find_classes(class_name))

        return records

    def _method_records(self, method_names):
        records = []

        for method_name in method_names:
            records.extend(self.repository.find_methods(method_name))

        return records

    def _severity(self, affected_count):
        if affected_count >= 50:
            return "high"

        if affected_count >= 10:
            return "medium"

        return "low"

    def _risk_notes(self, affected, affected_count):
        notes = []

        if affected_count == 0:
            notes.append(
                "No indexed dependents, callers, or subclasses were found."
            )

        if affected["statistics"]["affected_classes"]:
            notes.append(
                "Inheritance relationships are present; preserve polymorphic "
                "contracts during migration."
            )

        if affected["statistics"]["affected_methods"]:
            notes.append(
                "Callers are present; validate call sites after changing "
                "method signatures or behavior."
            )

        if affected["statistics"]["affected_units"]:
            notes.append(
                "Dependent units are present; check imports and initialization "
                "side effects."
            )

        notes.append(
            "Static analysis can miss dynamic dispatch and framework callbacks."
        )

        return notes
