"""
File-by-file modernization planning.

This module does not call an LLM and does not write Java files. It turns the
indexed Pascal repository into deterministic migration jobs that later stages
can feed into full-unit prompts and batch generation.
"""

import argparse
import fnmatch
import json
import re
from pathlib import Path

try:
    from .source_extractor import PascalSourceExtractor
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.modernization.source_extractor import (
        PascalSourceExtractor
    )
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


JAVA_RESERVED_WORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch",
    "char", "class", "const", "continue", "default", "do", "double", "else",
    "enum", "extends", "final", "finally", "float", "for", "goto", "if",
    "implements", "import", "instanceof", "int", "interface", "long",
    "native", "new", "package", "private", "protected", "public", "return",
    "short", "static", "strictfp", "super", "switch", "synchronized",
    "this", "throw", "throws", "transient", "try", "void", "volatile",
    "while", "record", "sealed", "permits", "non-sealed", "var", "yield"
}


class FileMigrationPlanner:
    """
    Builds file-level Delphi/Object Pascal to Java migration jobs.

    A job represents one Pascal unit/source file and contains enough metadata
    for a later generator to build a file-oriented prompt: source location,
    target Java package, declared classes, method counts, and dependency edges.
    """

    def __init__(
        self,
        repository,
        source_root="doublecmd",
        target_base_package="org.doublecmd"
    ):
        self.repository = repository
        self.source_root = Path(source_root)
        self.target_base_package = target_base_package
        self.source_extractor = PascalSourceExtractor(source_root)

    def build_plan(
        self,
        include=None,
        exclude=None,
        units=None,
        limit=None,
        order="dependency",
        include_source=False
    ):
        """
        Return a structured migration plan.

        include/exclude are glob patterns matched against both unit names and
        normalized source paths. units is an exact unit-name allowlist.
        """

        selected_units = self._selected_units(
            include=include,
            exclude=exclude,
            units=units
        )
        ordering = self._ordering(selected_units, order=order)
        ordered_units = ordering["units"]

        if limit is not None:
            ordered_units = ordered_units[:limit]
            ordering = self._ordering(ordered_units, order=order)

        jobs = [
            self._job_for_unit(
                unit_name,
                index + 1,
                ordering=ordering,
                include_source=include_source
            )
            for index, unit_name in enumerate(ordered_units)
        ]

        return {
            "purpose": "file_migration_plan",
            "target_language": "Java",
            "source_root": str(self.source_root),
            "target_base_package": self.target_base_package,
            "order": order,
            "filters": {
                "include": list(include or []),
                "exclude": list(exclude or []),
                "units": list(units or []),
                "limit": limit,
                "include_source": include_source
            },
            "dependency_ordering": self._ordering_report(ordering),
            "statistics": self._statistics(jobs),
            "jobs": jobs
        }

    def _selected_units(self, include=None, exclude=None, units=None):
        include = list(include or [])
        exclude = list(exclude or [])
        unit_filter = set(units or [])
        selected = []

        for unit_name in self.repository.list_units():
            unit_record = self.repository.find_unit(unit_name)

            if not unit_record:
                continue

            source_file = unit_record.get("file") or ""

            if unit_filter and unit_name not in unit_filter:
                continue

            if include and not self._matches_any(unit_name, source_file, include):
                continue

            if exclude and self._matches_any(unit_name, source_file, exclude):
                continue

            selected.append(unit_name)

        return selected

    def _matches_any(self, unit_name, source_file, patterns):
        normalized_file = self._normalize_path(source_file)

        for pattern in patterns:
            normalized_pattern = self._normalize_path(pattern)

            if fnmatch.fnmatch(unit_name, pattern):
                return True

            if fnmatch.fnmatch(normalized_file, normalized_pattern):
                return True

        return False

    def _order_units(self, unit_names, order="dependency"):
        return self._ordering(unit_names, order=order)["units"]

    def _ordering(self, unit_names, order="dependency"):
        if order == "source":
            ordered_units = sorted(
                unit_names,
                key=lambda name: self._normalize_path(
                    self.repository.find_unit(name).get("file", name)
                )
            )
            return self._source_ordering(ordered_units)

        if order != "dependency":
            raise ValueError(f"Unsupported migration order: {order}")

        return self._dependency_ordering(unit_names)

    def _source_ordering(self, ordered_units):
        selected = set(ordered_units)
        internal_dependencies = self._internal_dependencies(selected)
        external_dependencies = self._external_dependencies(selected)
        position = {
            unit_name: index + 1
            for index, unit_name in enumerate(ordered_units)
        }

        return {
            "mode": "source",
            "units": ordered_units,
            "position": position,
            "waves": [
                {
                    "wave": index + 1,
                    "units": [unit_name]
                }
                for index, unit_name in enumerate(ordered_units)
            ],
            "internal_dependencies": internal_dependencies,
            "external_dependencies": external_dependencies,
            "internal_dependents": self._internal_dependents(
                internal_dependencies
            ),
            "cycles": [],
            "cycle_units": [],
            "remaining_units": [],
            "selected_units": sorted(selected)
        }

    def _dependency_ordering(self, unit_names):
        selected = set(unit_names)
        internal_dependencies = self._internal_dependencies(selected)
        external_dependencies = self._external_dependencies(selected)
        dependents = self._internal_dependents(internal_dependencies)
        incoming_counts = {
            unit_name: len(internal_dependencies[unit_name])
            for unit_name in selected
        }

        ready = sorted(
            unit_name
            for unit_name, count in incoming_counts.items()
            if count == 0
        )
        ordered = []
        waves = []

        while ready:
            current_wave = list(ready)
            waves.append({
                "wave": len(waves) + 1,
                "units": current_wave
            })
            ready = []

            for unit_name in current_wave:
                ordered.append(unit_name)

                for dependent in sorted(dependents[unit_name]):
                    incoming_counts[dependent] -= 1

                    if incoming_counts[dependent] == 0:
                        ready.append(dependent)

            ready = sorted(ready)

        remaining = sorted(selected - set(ordered))
        ordered.extend(remaining)
        position = {
            unit_name: index + 1
            for index, unit_name in enumerate(ordered)
        }

        return {
            "mode": "dependency",
            "units": ordered,
            "position": position,
            "waves": waves,
            "internal_dependencies": internal_dependencies,
            "external_dependencies": external_dependencies,
            "internal_dependents": dependents,
            "cycles": self._cycle_reports(remaining, internal_dependencies),
            "cycle_units": remaining,
            "remaining_units": remaining,
            "selected_units": sorted(selected)
        }

    def _internal_dependencies(self, selected):
        return {
            unit_name: sorted(
                dependency
                for dependency in self.repository.get_dependencies(unit_name)
                if dependency in selected
            )
            for unit_name in selected
        }

    def _external_dependencies(self, selected):
        return {
            unit_name: sorted(
                dependency
                for dependency in self.repository.get_dependencies(unit_name)
                if dependency not in selected
            )
            for unit_name in selected
        }

    def _internal_dependents(self, internal_dependencies):
        dependents = {
            unit_name: set()
            for unit_name in internal_dependencies
        }

        for unit_name, dependencies in internal_dependencies.items():
            for dependency in dependencies:
                dependents[dependency].add(unit_name)

        return {
            unit_name: sorted(unit_dependents)
            for unit_name, unit_dependents in dependents.items()
        }

    def _cycle_reports(self, remaining_units, internal_dependencies):
        remaining = set(remaining_units)

        if not remaining:
            return []

        return [
            {
                "unit": unit_name,
                "blocked_by": [
                    dependency
                    for dependency in internal_dependencies.get(unit_name, [])
                    if dependency in remaining
                ]
            }
            for unit_name in sorted(remaining)
        ]

    def _ordering_report(self, ordering):
        internal_dependencies = ordering["internal_dependencies"]
        external_dependencies = ordering["external_dependencies"]
        return {
            "mode": ordering["mode"],
            "ordered_units": ordering["units"],
            "waves": ordering["waves"],
            "internal_edge_count": sum(
                len(dependencies)
                for dependencies in internal_dependencies.values()
            ),
            "external_edge_count": sum(
                len(dependencies)
                for dependencies in external_dependencies.values()
            ),
            "cycle_count": len(ordering["cycles"]),
            "cycle_units": ordering["cycle_units"],
            "cycles": ordering["cycles"]
        }

    def _job_ordering(self, unit_name, ordering):
        position = ordering["position"].get(unit_name)
        internal_dependencies = ordering["internal_dependencies"].get(
            unit_name,
            []
        )
        external_dependencies = ordering["external_dependencies"].get(
            unit_name,
            []
        )
        prior = [
            dependency
            for dependency in internal_dependencies
            if ordering["position"].get(dependency, 0) < position
        ]
        later = [
            dependency
            for dependency in internal_dependencies
            if ordering["position"].get(dependency, 0) > position
        ]
        wave = None

        for wave_record in ordering["waves"]:
            if unit_name in wave_record["units"]:
                wave = wave_record["wave"]
                break

        return {
            "mode": ordering["mode"],
            "position": position,
            "wave": wave,
            "internal_dependencies": internal_dependencies,
            "prior_internal_dependencies": prior,
            "later_internal_dependencies": later,
            "external_dependencies": external_dependencies,
            "internal_dependents": ordering["internal_dependents"].get(
                unit_name,
                []
            ),
            "dependency_ready": not later,
            "cycle_participant": unit_name in set(ordering["cycle_units"])
        }

    def _job_for_unit(
        self,
        unit_name,
        sequence,
        ordering=None,
        include_source=False
    ):
        unit_record = self.repository.find_unit(unit_name)
        source_file = unit_record.get("file")
        classes = [
            class_record.get("name")
            for class_record in self.repository.classes_by_unit.get(unit_name, [])
            if class_record.get("name")
        ]
        methods = self.repository.methods_by_unit.get(unit_name, [])
        target_package = self._target_package(source_file)

        job = {
            "job_id": f"file:{unit_name}",
            "sequence": sequence,
            "status": "planned",
            "source": {
                "unit": unit_name,
                "file": source_file,
                "path": str(self.source_root / Path(source_file)),
                "dependencies": self.repository.get_dependencies(unit_name),
                "dependents": self.repository.get_dependents(unit_name)
            },
            "target": {
                "language": "Java",
                "package": target_package,
                "directory": target_package.replace(".", "/"),
                "file_hint": self._target_file_hint(target_package, unit_name)
            },
            "symbols": {
                "classes": classes,
                "methods": self._method_names(methods),
                "class_count": len(classes),
                "method_count": len(methods)
            },
            "ordering": (
                self._job_ordering(unit_name, ordering)
                if ordering
                else {}
            ),
            "planning_notes": self._planning_notes(unit_name, classes, methods)
        }

        if include_source:
            job["source_extraction"] = self._full_source_for_unit(unit_record)

        return job

    def _full_source_for_unit(self, unit_record):
        symbol = {
            "document_type": "unit",
            "name": unit_record.get("unit"),
            "unit": unit_record.get("unit"),
            "file": unit_record.get("file")
        }
        extraction = self.source_extractor.extract_unit(symbol)

        if not extraction:
            return {
                "available": False,
                "file": unit_record.get("file"),
                "source": "",
                "line_count": 0,
                "character_count": 0,
                "truncated": False,
                "extraction_kind": "unit"
            }

        return {
            "available": True,
            "file": extraction.get("file"),
            "path": extraction.get("path"),
            "start_line": extraction.get("start_line"),
            "end_line": extraction.get("end_line"),
            "line_count": extraction.get("line_count"),
            "character_count": len(extraction.get("source", "")),
            "truncated": extraction.get("truncated", False),
            "extraction_kind": "full_unit",
            "source": extraction.get("source", "")
        }

    def _method_names(self, methods):
        names = []

        for method in methods:
            class_name = method.get("class")
            method_name = method.get("method")

            if class_name and method_name:
                names.append(f"{class_name}.{method_name}")
            elif method_name:
                names.append(method_name)

        return names

    def _target_package(self, source_file):
        normalized = self._normalize_path(source_file)
        parts = normalized.split("/")[:-1]

        if parts and parts[0] == "src":
            parts = parts[1:]

        package_parts = [
            self._java_identifier(part)
            for part in parts
            if self._java_identifier(part)
        ]

        if not package_parts:
            return self.target_base_package

        return ".".join([self.target_base_package, *package_parts])

    def _target_file_hint(self, target_package, unit_name):
        class_name = self._java_type_name(unit_name)
        return f"{target_package.replace('.', '/')}/{class_name}.java"

    def _java_type_name(self, unit_name):
        cleaned = re.sub(r"[^A-Za-z0-9_]", "", unit_name or "")

        if cleaned.lower().startswith("u") and len(cleaned) > 1:
            cleaned = cleaned[1:]

        if not cleaned:
            return "MigrationUnit"

        return cleaned[:1].upper() + cleaned[1:]

    def _java_identifier(self, value):
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value).lower())
        cleaned = cleaned.strip("_")

        if not cleaned:
            return ""

        if cleaned[0].isdigit():
            cleaned = f"_{cleaned}"

        # Source folders can be named after Pascal concepts or ordinary words
        # that are Java keywords. Keep the mapping deterministic while avoiding
        # invalid package segments such as ".private".
        if cleaned in JAVA_RESERVED_WORDS:
            cleaned = f"{cleaned}_"

        return cleaned

    def _planning_notes(self, unit_name, classes, methods):
        notes = []

        if not classes:
            notes.append(
                "Unit has no indexed classes; generator may produce utility "
                "classes, package functions, constants, or only stubs."
            )

        if len(methods) > 100:
            notes.append(
                "Unit has many indexed methods; later generation should chunk "
                "or stage this file."
            )

        dependencies = self.repository.get_dependencies(unit_name)

        if len(dependencies) > 25:
            notes.append(
                "Unit has many dependencies; compile validation may require "
                "stub generation or dependency-first migration."
            )

        return notes

    def _statistics(self, jobs):
        return {
            "job_count": len(jobs),
            "source_file_count": len({
                job["source"]["file"]
                for job in jobs
                if job["source"].get("file")
            }),
            "class_count": sum(
                job["symbols"]["class_count"]
                for job in jobs
            ),
            "method_count": sum(
                job["symbols"]["method_count"]
                for job in jobs
            ),
            "source_included": any(
                "source_extraction" in job
                for job in jobs
            ),
            "source_available_count": sum(
                1
                for job in jobs
                if job.get("source_extraction", {}).get("available")
            ),
            "source_line_count": sum(
                job.get("source_extraction", {}).get("line_count", 0)
                for job in jobs
            ),
            "source_character_count": sum(
                job.get("source_extraction", {}).get("character_count", 0)
                for job in jobs
            )
        }

    def _normalize_path(self, value):
        return str(value or "").replace("\\", "/")


def build_file_migration_plan(repository, **options):
    """
    Convenience wrapper for API callers and tests.
    """

    return FileMigrationPlanner(repository).build_plan(**options)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plan file-by-file Delphi to Java migration jobs."
    )
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing generated repository JSON artifacts."
    )
    parser.add_argument(
        "--source-root",
        default="doublecmd",
        help="Root directory for source files referenced by metadata."
    )
    parser.add_argument(
        "--target-base-package",
        default="org.doublecmd",
        help="Base Java package for generated files."
    )
    parser.add_argument(
        "--include",
        nargs="*",
        default=None,
        help="Glob patterns matched against source paths or unit names."
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Glob patterns to exclude by source path or unit name."
    )
    parser.add_argument(
        "--units",
        nargs="*",
        default=None,
        help="Exact Pascal unit names to include."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of migration jobs to include."
    )
    parser.add_argument(
        "--order",
        choices=["dependency", "source"],
        default="dependency",
        help="Migration job ordering."
    )
    parser.add_argument(
        "--include-source",
        action="store_true",
        help="Include complete Pascal unit source text in each migration job."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full migration plan as JSON."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(load_repository(args.input))
    planner = FileMigrationPlanner(
        repository,
        source_root=args.source_root,
        target_base_package=args.target_base_package
    )
    plan = planner.build_plan(
        include=args.include,
        exclude=args.exclude,
        units=args.units,
        limit=args.limit,
        order=args.order,
        include_source=args.include_source
    )

    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return

    print("File Migration Plan")
    print(f"Jobs: {plan['statistics']['job_count']}")
    print(f"Classes: {plan['statistics']['class_count']}")
    print(f"Methods: {plan['statistics']['method_count']}")
    print(f"Source included: {plan['statistics']['source_included']}")

    for job in plan["jobs"]:
        print(
            f"- {job['sequence']:04d} {job['source']['unit']} "
            f"({job['source']['file']}) -> {job['target']['package']}"
        )


if __name__ == "__main__":
    main()
