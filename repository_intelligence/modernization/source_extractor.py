"""
Source extraction utilities for modernization.

Generated repository indices identify units, classes, methods, and files, but
they do not currently store exact source spans. This module fills that gap for
modernization by extracting full Pascal unit text, class declarations, and
method implementations from source files using conservative structural scans.
"""

from pathlib import Path
import re


PASCAL_METHOD_PREFIXES = (
    "function",
    "procedure",
    "constructor",
    "destructor",
    "operator"
)


class PascalSourceExtractor:
    """
    Extracts modernization-ready Pascal source bodies.

    The extractor is intentionally text-based because parsing remains owned by
    the indexing layer. It uses repository metadata to select a file and then
    applies Pascal-specific block heuristics that work well for declarations
    and implementation methods in the Double Commander codebase.
    """

    def __init__(self, source_root="doublecmd"):
        self.source_root = Path(source_root)

    def extract_symbol(self, symbol, max_lines=None):
        document_type = symbol.get("document_type") or symbol.get("type")

        if document_type == "unit":
            return self.extract_unit(symbol, max_lines=max_lines)

        if document_type == "class":
            return self.extract_class(symbol, max_lines=max_lines)

        if document_type == "method":
            return self.extract_method(symbol, max_lines=max_lines)

        return self.extract_nearest(symbol, max_lines=max_lines)

    def extract_unit(self, symbol, max_lines=None):
        lines, source_path = self._read_symbol_file(symbol)

        if lines is None:
            return None

        end = self._bounded_end(0, len(lines), max_lines)

        return self._record(
            symbol,
            source_path,
            0,
            end,
            lines,
            extraction_kind="unit",
            natural_end=len(lines)
        )

    def extract_class(self, symbol, max_lines=None):
        lines, source_path = self._read_symbol_file(symbol)

        if lines is None:
            return None

        class_name = symbol.get("class_name") or symbol.get("name")
        start = self._find_class_declaration(lines, class_name)

        if start is None:
            return None

        end = self._find_class_end(lines, start)

        bounded_end = self._bounded_end(start, end, max_lines)

        return self._record(
            symbol,
            source_path,
            start,
            bounded_end,
            lines,
            extraction_kind="class_declaration",
            natural_end=end
        )

    def extract_method(self, symbol, max_lines=None):
        lines, source_path = self._read_symbol_file(symbol)

        if lines is None:
            return None

        method_name = symbol.get("method_name") or symbol.get("method") or (
            symbol.get("name")
        )
        class_name = symbol.get("class_name") or symbol.get("class")
        start = self._find_method_implementation(
            lines,
            method_name,
            class_name=class_name
        )

        if start is None:
            return None

        end = self._find_method_end(lines, start)

        bounded_end = self._bounded_end(start, end, max_lines)

        return self._record(
            symbol,
            source_path,
            start,
            bounded_end,
            lines,
            extraction_kind="method_implementation",
            natural_end=end
        )

    def extract_nearest(self, symbol, max_lines=None, context_lines=12):
        lines, source_path = self._read_symbol_file(symbol)

        if lines is None:
            return None

        start = self._find_symbol_line(lines, symbol)

        if start is None:
            return None

        start = max(0, start - context_lines)
        end = self._bounded_end(start, len(lines), max_lines or 80)

        return self._record(
            symbol,
            source_path,
            start,
            end,
            lines,
            extraction_kind="nearest_context",
            natural_end=end
        )

    def _read_symbol_file(self, symbol):
        file_name = symbol.get("file")

        if not file_name:
            return None, None

        source_path = self.source_root / Path(str(file_name))

        if not source_path.exists():
            return None, source_path

        try:
            return (
                source_path.read_text(
                    encoding="utf-8",
                    errors="replace"
                ).splitlines(),
                source_path
            )
        except OSError:
            return None, source_path

    def _find_class_declaration(self, lines, class_name):
        if not class_name:
            return None

        pattern = re.compile(
            r"^\s*" + re.escape(class_name) + r"\s*=\s*class\b",
            re.IGNORECASE
        )

        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue

            # Skip forward declarations such as "TFoo = class;".
            if re.search(r"\bclass\s*;", line, re.IGNORECASE):
                continue

            return index

        return None

    def _find_class_end(self, lines, start):
        for index in range(start + 1, len(lines)):
            if re.match(r"^\s*end\s*;", lines[index], re.IGNORECASE):
                return index + 1

        return len(lines)

    def _find_method_implementation(self, lines, method_name, class_name=None):
        if not method_name:
            return None

        if class_name:
            owner = re.escape(class_name) + r"\s*\.\s*"
        else:
            owner = r"(?:[A-Za-z_][A-Za-z0-9_]*\s*\.\s*)?"

        pattern = re.compile(
            r"^(" + "|".join(PASCAL_METHOD_PREFIXES) + r")\s+"
            + owner
            + re.escape(method_name)
            + r"\b",
            re.IGNORECASE
        )

        for index, line in enumerate(lines):
            if pattern.search(line):
                return index

        return None

    def _find_method_end(self, lines, start):
        for index in range(start + 1, len(lines)):
            if self._is_top_level_method_start(lines[index]):
                return index

        return len(lines)

    def _is_top_level_method_start(self, line):
        return bool(
            re.match(
                r"^(" + "|".join(PASCAL_METHOD_PREFIXES) + r")\s+"
                r"(?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*\b",
                line,
                re.IGNORECASE
            )
        )

    def _find_symbol_line(self, lines, symbol):
        candidates = [
            symbol.get("method_name"),
            symbol.get("method"),
            symbol.get("class_name"),
            symbol.get("class"),
            symbol.get("name")
        ]
        patterns = [
            re.compile(r"\b" + re.escape(candidate) + r"\b", re.IGNORECASE)
            for candidate in candidates
            if candidate
        ]

        for index, line in enumerate(lines):
            if any(pattern.search(line) for pattern in patterns):
                return index

        return None

    def _bounded_end(self, start, natural_end, max_lines):
        if max_lines is None:
            return natural_end

        return min(natural_end, start + max_lines)

    def _record(
        self,
        symbol,
        source_path,
        start,
        end,
        lines,
        extraction_kind,
        natural_end
    ):
        source = "\n".join(lines[start:end])

        return {
            "symbol": symbol.get("name") or symbol.get("method"),
            "document_type": symbol.get("document_type") or symbol.get("type"),
            "unit": symbol.get("unit"),
            "class_name": symbol.get("class_name") or symbol.get("class"),
            "method_name": symbol.get("method_name") or symbol.get("method"),
            "file": symbol.get("file"),
            "path": str(source_path),
            "start_line": start + 1,
            "end_line": end,
            "line_count": end - start,
            "truncated": end < natural_end,
            "extraction_kind": extraction_kind,
            "source": source,
            "snippet": source
        }
