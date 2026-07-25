"""
search.py

Repository search over indexed units, files, classes, and methods.

Search combines SymbolTable lookup with lightweight ranking. It does not use
embeddings or semantic retrieval; those belong to a later phase.
"""

try:
    from .symbol_table import SymbolTable
except ImportError:
    from symbol_table import SymbolTable


class RepositorySearch:

    def __init__(self, repository, symbol_table=None):
        self.repository = repository
        self.symbol_table = symbol_table or SymbolTable(repository)

    def search_units(self, query, limit=25):
        return self.search_symbols(
            query,
            symbol_types={"unit"},
            limit=limit
        )

    def search_files(self, query, limit=25):
        return self.search_symbols(
            query,
            symbol_types={"file"},
            limit=limit
        )

    def search_classes(self, query, limit=25):
        return self.search_symbols(
            query,
            symbol_types={"class"},
            limit=limit
        )

    def search_methods(self, query, limit=25):
        return self.search_symbols(
            query,
            symbol_types={"method"},
            limit=limit
        )

    def search_symbols(
        self,
        query,
        symbol_types=None,
        limit=25
    ):
        exact = self.symbol_table.resolve_symbol(
            query,
            symbol_types=symbol_types
        )

        exact_results = [
            self._with_score(result, 100)
            for result in exact
        ]

        candidates = self.symbol_table.candidate_symbols(
            query,
            symbol_types=symbol_types,
            limit=limit * 4
        )

        results = self._deduplicate(exact_results + candidates)
        results.sort(
            key=lambda item: (
                item.get("score", 0),
                item.get("type", ""),
                item.get("name", "")
            ),
            reverse=True
        )

        return results[:limit]

    def _with_score(self, result, score):
        scored = dict(result)
        scored["score"] = score

        return scored

    def _deduplicate(self, results):
        seen = set()
        unique = []

        for result in results:
            key = (
                result.get("type"),
                result.get("name"),
                result.get("unit"),
                result.get("file")
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(result)

        return unique
