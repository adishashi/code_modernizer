"""
symbol_table.py

Symbol lookup and disambiguation for repository intelligence.

This module does not perform graph traversal. It resolves names to repository
records owned by Repository.
"""

from difflib import SequenceMatcher


def _normalize(value):
    if value is None:
        return ""

    return str(value).casefold()


class SymbolTable:

    def __init__(self, repository):
        self.repository = repository

    ###########################################################################
    # Exact Lookup
    ###########################################################################

    def lookup_unit(self, name):
        unit = self.repository.find_unit(name)

        if not unit:
            return []

        return [self._unit_result(unit)]

    def lookup_file(self, path_or_unit):
        value = self.repository.find_file(path_or_unit)

        if isinstance(value, dict):
            return [self._unit_result(value)]

        if value:
            unit = self.repository.find_unit(path_or_unit)

            return [{
                "type": "file",
                "name": value,
                "unit": path_or_unit if unit else None,
                "file": value,
                "record": unit
            }]

        return []

    def lookup_class(self, name, unit_name=None):
        return [
            self._class_result(cls)
            for cls in self.repository.find_classes(
                name,
                unit_name=unit_name
            )
        ]

    def lookup_method(
        self,
        name,
        class_name=None,
        unit_name=None
    ):
        return [
            self._method_result(method)
            for method in self.repository.find_methods(
                name,
                class_name=class_name,
                unit_name=unit_name
            )
        ]

    def resolve_symbol(
        self,
        name,
        symbol_types=None,
        unit_name=None,
        class_name=None
    ):
        requested = self._requested_types(symbol_types)
        results = []

        if "unit" in requested:
            results.extend(self.lookup_unit(name))

        if "file" in requested:
            results.extend(self.lookup_file(name))

        if "class" in requested:
            results.extend(self.lookup_class(name, unit_name=unit_name))

        if "method" in requested:
            results.extend(
                self.lookup_method(
                    name,
                    class_name=class_name,
                    unit_name=unit_name
                )
            )

        return self._deduplicate(results)

    ###########################################################################
    # Disambiguation
    ###########################################################################

    def disambiguate_class(self, name):
        matches = self.lookup_class(name)

        return {
            "query": name,
            "ambiguous": len(matches) > 1,
            "matches": matches
        }

    def disambiguate_method(self, name):
        matches = self.lookup_method(name)

        return {
            "query": name,
            "ambiguous": len(matches) > 1,
            "matches": matches
        }

    ###########################################################################
    # Candidate Lookup
    ###########################################################################

    def candidate_symbols(
        self,
        query,
        symbol_types=None,
        limit=25
    ):
        requested = self._requested_types(symbol_types)
        query_key = _normalize(query)
        candidates = []

        if "unit" in requested:
            for unit_name, unit in self.repository.units.items():
                candidates.append(
                    self._score_result(
                        query_key,
                        unit_name,
                        self._unit_result(unit)
                    )
                )

        if "file" in requested:
            for unit_name, source_file in self.repository.files.items():
                if not source_file:
                    continue

                candidates.append(
                    self._score_result(
                        query_key,
                        source_file,
                        {
                            "type": "file",
                            "name": source_file,
                            "unit": unit_name,
                            "file": source_file,
                            "record": self.repository.find_unit(unit_name)
                        }
                    )
                )

        if "class" in requested:
            for class_matches in self.repository.classes_by_name.values():
                for cls in class_matches:
                    candidates.append(
                        self._score_result(
                            query_key,
                            cls.get("name"),
                            self._class_result(cls)
                        )
                    )

        if "method" in requested:
            for method in self.repository.methods:
                method_name = method.get("method")
                qualified = self._qualified_method_name(method)

                best_name = qualified if "." in query_key else method_name

                candidates.append(
                    self._score_result(
                        query_key,
                        best_name,
                        self._method_result(method)
                    )
                )

        ranked = [
            item for item in candidates
            if item["score"] > 0
        ]
        ranked.sort(
            key=lambda item: (
                item["score"],
                item["type"],
                item["name"]
            ),
            reverse=True
        )

        return self._deduplicate(ranked)[:limit]

    ###########################################################################
    # Result Helpers
    ###########################################################################

    def _requested_types(self, symbol_types):
        if symbol_types is None:
            return {"unit", "file", "class", "method"}

        if isinstance(symbol_types, str):
            return {_normalize(symbol_types)}

        return {
            _normalize(symbol_type)
            for symbol_type in symbol_types
        }

    def _unit_result(self, unit):
        return {
            "type": "unit",
            "name": unit.get("unit"),
            "unit": unit.get("unit"),
            "file": unit.get("file"),
            "record": unit
        }

    def _class_result(self, cls):
        return {
            "type": "class",
            "name": cls.get("name"),
            "unit": cls.get("unit"),
            "file": cls.get("file"),
            "record": cls
        }

    def _method_result(self, method):
        return {
            "type": "method",
            "name": self._qualified_method_name(method),
            "unit": method.get("unit"),
            "class": method.get("class"),
            "method": method.get("method"),
            "file": method.get("file"),
            "record": method
        }

    def _qualified_method_name(self, method):
        class_name = method.get("class")
        method_name = method.get("method")

        if class_name:
            return f"{class_name}.{method_name}"

        return method_name

    def _score_result(self, query_key, candidate_name, result):
        candidate_key = _normalize(candidate_name)

        if not query_key or not candidate_key:
            score = 0
        elif candidate_key == query_key:
            score = 100
        elif candidate_key.startswith(query_key):
            score = 90
        elif query_key in candidate_key:
            score = 75
        else:
            score = int(
                SequenceMatcher(
                    None,
                    query_key,
                    candidate_key
                ).ratio() * 60
            )

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
