"""
Hybrid context assembly for modernization tasks.

Modernization needs a richer packet than normal search results. This module
combines hybrid retrieval, direct semantic neighbours, deterministic summaries,
structural graph context, and bounded source snippets into one prompt-ready
object. It still treats the generated JSON artifacts as the source of truth and
only reads source files for display snippets.
"""

from pathlib import Path
import json

try:
    from ..graph_api import GraphAPI
    from ..semantic.hybrid_retrieval import HybridRetriever
    from ..semantic.semantic_search import SemanticSearchEngine
    from .source_extractor import PascalSourceExtractor
except ImportError:
    from repository_intelligence.graph_api import GraphAPI
    from repository_intelligence.semantic.hybrid_retrieval import HybridRetriever
    from repository_intelligence.semantic.semantic_search import SemanticSearchEngine
    from repository_intelligence.modernization.source_extractor import (
        PascalSourceExtractor
    )


class SummaryLookup:
    """
    Loads generated summaries and matches them to retrieval metadata.

    Summary artifacts and embedding metadata use the same symbol fields, but
    they are stored in different files. This small index gives the context
    assembler a deterministic way to attach human-readable summaries.
    """

    def __init__(self, summary_directory="output/summaries"):
        self.summary_directory = Path(summary_directory)
        self.by_key = {}
        self.records = []
        self._load()

    def find(self, metadata):
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
                self.records.append(record)
                self.by_key[self._key(
                    record.get("summary_type"),
                    record.get("name"),
                    record.get("unit"),
                    record.get("class_name"),
                    record.get("method_name")
                )] = record

    def _key(self, document_type, name, unit, class_name, method_name):
        return (
            document_type,
            name,
            unit,
            class_name,
            method_name
        )


class SourceSnippetExtractor(PascalSourceExtractor):
    """
    Compatibility wrapper for bounded display snippets.

    New modernization code should use PascalSourceExtractor directly when it
    needs complete class declarations or method implementations.
    """

    def extract(self, symbol, max_lines=80, context_lines=12):
        return self.extract_nearest(
            symbol,
            max_lines=max_lines,
            context_lines=context_lines
        )


class ModernizationContextAssembler:
    """
    Builds modernization-ready context from all intelligence layers.

    The result is intentionally structured instead of prompt-only text so a
    future agent can choose which sections to include, compress, or validate.
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
        self.hybrid_retriever = HybridRetriever(
            repository,
            artifacts_directory=artifacts_directory,
            persist_directory=persist_directory,
            collection_name=collection_name
        )
        self.semantic_engine = SemanticSearchEngine(
            artifacts_directory=artifacts_directory,
            persist_directory=persist_directory,
            collection_name=collection_name,
            summary_directory=summary_directory
        )
        self.summary_lookup = SummaryLookup(summary_directory)
        self.source_extractor = PascalSourceExtractor(source_root)
        try:
            from .java_templates import JavaTargetDesignTemplates
        except ImportError:
            from repository_intelligence.modernization.java_templates import (
                JavaTargetDesignTemplates
            )

        self.java_templates = JavaTargetDesignTemplates()

    def close(self):
        self.hybrid_retriever.close()
        self.semantic_engine.close()

    def build_context(
        self,
        task,
        target_language="Java",
        limit=8,
        lexical_limit=25,
        vector_limit=25,
        graph_depth=1,
        document_types=None,
        include_source=True,
        max_snippet_lines=80
    ):
        hybrid = self.hybrid_retriever.retrieve(
            task,
            limit=limit,
            lexical_limit=lexical_limit,
            vector_limit=vector_limit,
            graph_depth=graph_depth,
            document_types=document_types
        )
        semantic = self.semantic_engine.search(
            task,
            limit=limit,
            document_types=document_types,
            include_summaries=True
        )
        symbols = self._merge_symbols(
            hybrid.get("results", []),
            semantic.get("results", [])
        )
        summaries = self._summaries_for(symbols)
        graph_context = self._graph_context(symbols, graph_depth)
        target_design = self._target_design(symbols)
        source_context = (
            self._source_context(symbols, max_snippet_lines)
            if include_source
            else []
        )

        return {
            "task": {
                "description": task,
                "target_language": target_language,
                "purpose": "modernization_context"
            },
            "retrieval": {
                "hybrid": hybrid,
                "semantic": semantic
            },
            "symbols": symbols,
            "summaries": summaries,
            "graph_context": graph_context,
            "target_design": target_design,
            "source_context": source_context,
            "modernization_guidance": self._guidance(symbols),
            "statistics": {
                "symbol_count": len(symbols),
                "summary_count": len(summaries),
                "source_snippet_count": len(source_context),
                "repository": self.repository.statistics()
            }
        }

    def render_context(self, context):
        lines = [
            "Modernization Context",
            f"Task: {context['task']['description']}",
            f"Target language: {context['task']['target_language']}",
            "",
            "Top Symbols:"
        ]

        for symbol in context.get("symbols", []):
            lines.append(
                f"- {symbol.get('document_type')} {symbol.get('name')} "
                f"score={symbol.get('score')} file={symbol.get('file')}"
            )

        lines.append("")
        lines.append("Summaries:")

        for summary in context.get("summaries", []):
            lines.append(
                f"- {summary.get('summary_type')} {summary.get('name')}: "
                f"{summary.get('summary')}"
            )

        lines.append("")
        lines.append("Graph Context:")

        for item in context.get("graph_context", []):
            lines.append(
                f"- {item.get('document_type')} {item.get('name')}: "
                f"{item.get('relationships')}"
            )

        lines.append("")
        lines.append("Target Design:")

        for template in context.get("target_design", {}).get(
            "templates",
            []
        ):
            lines.append(
                f"- {template.get('template_id')}: "
                f"{template.get('title')}"
            )

        lines.append("")
        lines.append("Source Snippets:")

        for snippet in context.get("source_context", []):
            lines.append(
                f"- {snippet.get('document_type')} {snippet.get('symbol')} "
                f"{snippet.get('file')}:{snippet.get('start_line')} "
                f"({snippet.get('extraction_kind')})"
            )

        lines.append("")
        lines.append("Modernization Guidance:")

        for item in context.get("modernization_guidance", {}).get(
            "next_actions",
            []
        ):
            lines.append(f"- {item}")

        return "\n".join(lines)

    def _merge_symbols(self, hybrid_results, semantic_results):
        merged = {}

        for source_name, results in (
            ("hybrid", hybrid_results),
            ("semantic", semantic_results)
        ):
            for result in results:
                key = self._symbol_key(result)

                if key not in merged:
                    merged[key] = {
                        "document_id": result.get("document_id"),
                        "document_type": result.get("document_type"),
                        "name": result.get("name"),
                        "unit": result.get("unit"),
                        "class_name": result.get("class_name"),
                        "method_name": result.get("method_name"),
                        "file": result.get("file"),
                        "score": 0.0,
                        "sources": []
                    }

                merged[key]["score"] = max(
                    merged[key]["score"],
                    result.get("score", 0.0)
                )

                if source_name not in merged[key]["sources"]:
                    merged[key]["sources"].append(source_name)

        return sorted(
            merged.values(),
            key=lambda item: (item["score"], item["name"]),
            reverse=True
        )

    def _summaries_for(self, symbols):
        summaries = []
        seen = set()

        for symbol in symbols:
            summary = self.summary_lookup.find(symbol)

            if not summary:
                continue

            summary_id = summary.get("summary_id")

            if summary_id in seen:
                continue

            seen.add(summary_id)
            summaries.append(summary)

        return summaries

    def _graph_context(self, symbols, graph_depth):
        context = []

        for symbol in symbols:
            document_type = symbol.get("document_type")
            relationships = {}

            if document_type == "unit":
                unit_name = symbol.get("unit") or symbol.get("name")
                relationships["dependencies"] = self.graph_api.dependencies(
                    unit_name
                )
                relationships["dependents"] = self.graph_api.dependents(
                    unit_name
                )

                if graph_depth > 1:
                    relationships["transitive_dependencies"] = (
                        self.graph_api.transitive_dependencies(
                            unit_name,
                            max_depth=graph_depth
                        )
                    )

            if document_type == "class":
                class_name = symbol.get("class_name") or symbol.get("name")
                relationships["parent"] = self.graph_api.parent(class_name)
                relationships["children"] = self.graph_api.children(
                    class_name
                )

                if graph_depth > 1:
                    relationships["ancestors"] = self.graph_api.ancestors(
                        class_name,
                        max_depth=graph_depth
                    )
                    relationships["descendants"] = (
                        self.graph_api.descendants(
                            class_name,
                            max_depth=graph_depth
                        )
                    )

            if document_type == "method":
                method_name = symbol.get("method_name") or symbol.get("name")
                relationships["callers"] = self.graph_api.callers(
                    method_name
                )
                relationships["callees"] = self.graph_api.callees(
                    method_name
                )

                if graph_depth > 1:
                    relationships["transitive_callers"] = (
                        self.graph_api.transitive_callers(
                            method_name,
                            max_depth=graph_depth
                        )
                    )
                    relationships["transitive_callees"] = (
                        self.graph_api.transitive_callees(
                            method_name,
                            max_depth=graph_depth
                        )
                    )

            context.append({
                "document_type": document_type,
                "name": symbol.get("name"),
                "unit": symbol.get("unit"),
                "relationships": relationships
            })

        return context

    def _target_design(self, symbols):
        selected = {}

        for symbol in symbols:
            for template in self.java_templates.select_for_symbol(symbol):
                selected[template.template_id] = template

        template_ids = sorted(selected)

        return {
            "target_language": "Java",
            "templates": [
                selected[template_id].to_dict()
                for template_id in template_ids
            ],
            "prompt_section": self.java_templates.as_prompt_section(
                template_ids=template_ids
            ) if template_ids else ""
        }

    def _source_context(self, symbols, max_snippet_lines):
        snippets = []
        seen = set()

        for symbol in symbols:
            snippet = self.source_extractor.extract_symbol(
                symbol,
                max_lines=max_snippet_lines
            )

            if not snippet:
                continue

            key = (
                snippet.get("file"),
                snippet.get("start_line"),
                snippet.get("symbol")
            )

            if key in seen:
                continue

            seen.add(key)
            snippets.append(snippet)

        return snippets

    def _guidance(self, symbols):
        touched_files = sorted({
            symbol.get("file")
            for symbol in symbols
            if symbol.get("file")
        })
        next_actions = [
            "Review top hybrid matches before selecting modernization scope.",
            "Use summaries to identify symbol responsibilities and boundaries.",
            "Inspect graph context for dependencies, callers, and subclasses.",
            "Compare source snippets against generated Java design before coding."
        ]

        risk_notes = [
            "Static call graph data can miss dynamic dispatch.",
            "Simple class names can collide across units.",
            "Source snippets are display aids and are not a parser substitute."
        ]

        return {
            "touched_files": touched_files,
            "next_actions": next_actions,
            "risk_notes": risk_notes
        }

    def _symbol_key(self, result):
        return (
            result.get("document_type"),
            result.get("name"),
            result.get("unit"),
            result.get("class_name"),
            result.get("method_name"),
            result.get("file")
        )


def build_modernization_context(
    repository,
    task,
    assembler_options=None,
    context_options=None
):
    assembler = ModernizationContextAssembler(
        repository,
        **(assembler_options or {})
    )

    try:
        return assembler.build_context(task, **(context_options or {}))
    finally:
        assembler.close()
