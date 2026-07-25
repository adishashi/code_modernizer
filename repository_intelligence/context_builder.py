"""
context_builder.py

Assembles repository context for downstream LLM prompts.

The context builder uses repository indices, symbol lookup, search, and graph
traversal. It does not parse source files.
"""

try:
    from .graph_api import GraphAPI
    from .search import RepositorySearch
    from .symbol_table import SymbolTable
except ImportError:
    from graph_api import GraphAPI
    from search import RepositorySearch
    from symbol_table import SymbolTable


class ContextBuilder:

    def __init__(
        self,
        repository,
        symbol_table=None,
        graph_api=None,
        search=None
    ):
        self.repository = repository
        self.symbol_table = symbol_table or SymbolTable(repository)
        self.graph_api = graph_api or GraphAPI(repository)
        self.search = search or RepositorySearch(
            repository,
            symbol_table=self.symbol_table
        )

    ###########################################################################
    # Public API
    ###########################################################################

    def build_symbol_context(
        self,
        symbol,
        symbol_types=None,
        max_graph_depth=1,
        limit=10
    ):
        matches = self.symbol_table.resolve_symbol(
            symbol,
            symbol_types=symbol_types
        )

        if not matches:
            matches = self.search.search_symbols(
                symbol,
                symbol_types=symbol_types,
                limit=limit
            )

        context = {
            "query": symbol,
            "matches": matches[:limit],
            "units": [],
            "classes": [],
            "methods": [],
            "graphs": {}
        }

        for match in context["matches"]:
            self._add_match_context(
                context,
                match,
                max_graph_depth=max_graph_depth
            )

        context["units"] = self._deduplicate_records(
            context["units"],
            key_field="unit"
        )
        context["classes"] = self._deduplicate_records(
            context["classes"],
            key_field="name"
        )
        context["methods"] = self._deduplicate_records(
            context["methods"],
            key_field="method"
        )

        return context

    def build_query_context(
        self,
        query,
        limit=10,
        max_graph_depth=1
    ):
        results = self.search.search_symbols(
            query,
            limit=limit
        )

        context = {
            "query": query,
            "search_results": results,
            "units": [],
            "classes": [],
            "methods": [],
            "graphs": {}
        }

        for result in results:
            self._add_match_context(
                context,
                result,
                max_graph_depth=max_graph_depth
            )

        context["units"] = self._deduplicate_records(
            context["units"],
            key_field="unit"
        )
        context["classes"] = self._deduplicate_records(
            context["classes"],
            key_field="name"
        )
        context["methods"] = self._deduplicate_records(
            context["methods"],
            key_field="method"
        )

        return context

    def render_context(self, context):
        lines = [
            f"Repository context for: {context.get('query')}",
            "",
            "Units:"
        ]

        for unit in context.get("units", []):
            lines.append(
                f"- {unit.get('unit')} ({unit.get('file')})"
            )

        lines.append("")
        lines.append("Classes:")

        for cls in context.get("classes", []):
            parent = cls.get("parent")
            parent_text = f" < {parent}" if parent else ""
            lines.append(
                f"- {cls.get('name')}{parent_text} "
                f"[{cls.get('unit')}]"
            )

        lines.append("")
        lines.append("Methods:")

        for method in context.get("methods", []):
            class_name = method.get("class")
            prefix = f"{class_name}." if class_name else ""
            lines.append(
                f"- {prefix}{method.get('method')} "
                f"[{method.get('unit')}]"
            )

        lines.append("")
        lines.append("Graph Context:")

        for key, value in sorted(context.get("graphs", {}).items()):
            lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    ###########################################################################
    # Context Helpers
    ###########################################################################

    def _add_match_context(
        self,
        context,
        match,
        max_graph_depth=1
    ):
        match_type = match.get("type")
        record = match.get("record") or {}
        unit_name = match.get("unit")

        if unit_name:
            unit = self.repository.find_unit(unit_name)

            if unit:
                context["units"].append(unit)
                self._add_unit_graph_context(
                    context,
                    unit_name,
                    max_graph_depth=max_graph_depth
                )

        if match_type == "class":
            context["classes"].append(record)
            self._add_class_graph_context(
                context,
                match.get("name"),
                max_graph_depth=max_graph_depth
            )

        if match_type == "method":
            context["methods"].append(record)
            self._add_method_graph_context(
                context,
                match.get("method") or match.get("name"),
                max_graph_depth=max_graph_depth
            )

            if match.get("class"):
                for cls in self.repository.find_classes(match.get("class")):
                    context["classes"].append(cls)

        if match_type == "unit":
            for cls in self.repository.classes_by_unit.get(
                match.get("name"),
                []
            ):
                context["classes"].append(cls)

            context["methods"].extend(
                self.repository.methods_by_unit.get(
                    match.get("name"),
                    []
                )
            )

    def _add_unit_graph_context(
        self,
        context,
        unit_name,
        max_graph_depth
    ):
        context["graphs"][f"{unit_name}.dependencies"] = (
            self.graph_api.dependencies(unit_name)
        )
        context["graphs"][f"{unit_name}.dependents"] = (
            self.graph_api.dependents(unit_name)
        )

        if max_graph_depth > 1:
            context["graphs"][f"{unit_name}.transitive_dependencies"] = (
                self.graph_api.transitive_dependencies(
                    unit_name,
                    max_depth=max_graph_depth
                )
            )

    def _add_class_graph_context(
        self,
        context,
        class_name,
        max_graph_depth
    ):
        context["graphs"][f"{class_name}.parent"] = (
            self.graph_api.parent(class_name)
        )
        context["graphs"][f"{class_name}.children"] = (
            self.graph_api.children(class_name)
        )

        if max_graph_depth > 1:
            context["graphs"][f"{class_name}.ancestors"] = (
                self.graph_api.ancestors(
                    class_name,
                    max_depth=max_graph_depth
                )
            )
            context["graphs"][f"{class_name}.descendants"] = (
                self.graph_api.descendants(
                    class_name,
                    max_depth=max_graph_depth
                )
            )

    def _add_method_graph_context(
        self,
        context,
        method_name,
        max_graph_depth
    ):
        context["graphs"][f"{method_name}.callers"] = (
            self.graph_api.callers(method_name)
        )
        context["graphs"][f"{method_name}.callees"] = (
            self.graph_api.callees(method_name)
        )

        if max_graph_depth > 1:
            context["graphs"][f"{method_name}.transitive_callers"] = (
                self.graph_api.transitive_callers(
                    method_name,
                    max_depth=max_graph_depth
                )
            )
            context["graphs"][f"{method_name}.transitive_callees"] = (
                self.graph_api.transitive_callees(
                    method_name,
                    max_depth=max_graph_depth
                )
            )

    def _deduplicate_records(self, records, key_field):
        seen = set()
        unique = []

        for record in records:
            key = (
                record.get(key_field),
                record.get("unit"),
                record.get("file")
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(record)

        return unique
