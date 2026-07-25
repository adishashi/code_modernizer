"""
summaries.py

Deterministic repository summary generation.

Stage 4.4 creates local summaries from the indexed repository metadata and
graph relationships. It deliberately does not call an LLM: these summaries are
stable artifacts that can later be used as context for an agent or as source
material for LLM-authored higher-level documentation.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json


@dataclass(frozen=True)
class SummaryRecord:
    """
    One summary artifact record.

    The fields mirror the repository's core symbol concepts so callers can
    filter summaries by type, unit, class, method, or file without parsing the
    summary text itself.
    """

    summary_id: str
    summary_type: str
    name: str
    summary: str
    unit: str = None
    class_name: str = None
    method_name: str = None
    file: str = None
    metrics: dict = field(default_factory=dict)
    related_symbols: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class RepositorySummarizer:
    """
    Builds summaries for methods, classes, units, subsystems, and architecture.

    The summarizer only reads Repository APIs and lookup tables. This keeps the
    implementation aligned with the project rule that downstream intelligence
    components must not reparse Pascal source files.
    """

    def __init__(self, repository):
        self.repository = repository

    def build_summaries(self, summary_types=None):
        requested = self._requested_types(summary_types)
        summaries = []

        if "method" in requested:
            summaries.extend(self.build_method_summaries())

        if "class" in requested:
            summaries.extend(self.build_class_summaries())

        if "unit" in requested:
            summaries.extend(self.build_unit_summaries())

        if "subsystem" in requested:
            summaries.extend(self.build_subsystem_summaries())

        if "architecture" in requested:
            summaries.append(self.build_architecture_summary())

        return summaries

    def build_method_summaries(self):
        summaries = []

        for index, method in enumerate(self.repository.methods):
            unit_name = method.get("unit")
            class_name = method.get("class")
            method_name = method.get("method")
            qualified_name = self._qualified_method_name(method)
            callers = self.repository.get_callers(method_name)
            callees = self.repository.get_callees(method_name)

            metrics = {
                "caller_count": len(callers),
                "callee_count": len(callees)
            }
            related = {
                "callers": callers[:20],
                "callees": callees[:20]
            }

            summary = self._sentence(
                f"{qualified_name} is a {method.get('kind') or 'method'}",
                f"defined in unit {unit_name}" if unit_name else None,
                f"on class {class_name}" if class_name else None,
                f"with {len(callers)} static callers",
                f"and {len(callees)} static callees"
            )

            summaries.append(
                SummaryRecord(
                    summary_id=(
                        f"summary:method:{unit_name or 'unknown'}:"
                        f"{class_name or 'global'}:{method_name}:{index}"
                    ),
                    summary_type="method",
                    name=qualified_name,
                    unit=unit_name,
                    class_name=class_name,
                    method_name=method_name,
                    file=method.get("file"),
                    summary=summary,
                    metrics=metrics,
                    related_symbols=related
                )
            )

        return summaries

    def build_class_summaries(self):
        summaries = []

        for class_name in sorted(self.repository.classes_by_name):
            for index, cls in enumerate(
                self.repository.classes_by_name[class_name]
            ):
                unit_name = cls.get("unit")
                parent = cls.get("parent")
                children = self.repository.get_children(class_name)
                methods = [
                    method for method in self.repository.methods_by_class.get(
                        class_name,
                        []
                    )
                    if not unit_name or method.get("unit") == unit_name
                ]

                metrics = {
                    "method_count": len(methods),
                    "child_count": len(children)
                }
                related = {
                    "parent": parent,
                    "children": children[:20],
                    "methods": [
                        self._qualified_method_name(method)
                        for method in methods[:30]
                    ]
                }

                summary = self._sentence(
                    f"{class_name} is a class",
                    f"in unit {unit_name}" if unit_name else None,
                    f"declared in {cls.get('file')}" if cls.get("file") else None,
                    f"that inherits from {parent}" if parent else None,
                    f"with {len(children)} indexed child classes",
                    f"and {len(methods)} indexed methods"
                )

                summaries.append(
                    SummaryRecord(
                        summary_id=(
                            f"summary:class:{unit_name or 'unknown'}:"
                            f"{class_name}:{index}"
                        ),
                        summary_type="class",
                        name=class_name,
                        unit=unit_name,
                        class_name=class_name,
                        file=cls.get("file"),
                        summary=summary,
                        metrics=metrics,
                        related_symbols=related
                    )
                )

        return summaries

    def build_unit_summaries(self):
        summaries = []

        for unit_name in sorted(self.repository.units):
            unit = self.repository.units[unit_name]
            dependencies = self.repository.get_dependencies(unit_name)
            dependents = self.repository.get_dependents(unit_name)
            classes = self.repository.classes_by_unit.get(unit_name, [])
            methods = self.repository.methods_by_unit.get(unit_name, [])
            fields = unit.get("fields", [])

            metrics = {
                "dependency_count": len(dependencies),
                "dependent_count": len(dependents),
                "class_count": len(classes),
                "method_count": len(methods),
                "field_count": len(fields)
            }
            related = {
                "dependencies": dependencies[:30],
                "dependents": dependents[:30],
                "classes": [
                    cls.get("name")
                    for cls in classes[:30]
                ],
                "methods": [
                    self._qualified_method_name(method)
                    for method in methods[:30]
                ]
            }

            summary = self._sentence(
                f"{unit_name} is a Pascal unit",
                f"stored at {unit.get('file')}" if unit.get("file") else None,
                f"with {len(dependencies)} direct dependencies",
                f"{len(dependents)} direct dependents",
                f"{len(classes)} classes",
                f"and {len(methods)} method definitions"
            )

            summaries.append(
                SummaryRecord(
                    summary_id=f"summary:unit:{unit_name}",
                    summary_type="unit",
                    name=unit_name,
                    unit=unit_name,
                    file=unit.get("file"),
                    summary=summary,
                    metrics=metrics,
                    related_symbols=related
                )
            )

        return summaries

    def build_subsystem_summaries(self):
        buckets = {}

        # A subsystem is derived from the first two path segments. This is a
        # pragmatic structural grouping until the project has explicit package
        # or module metadata.
        for unit_name, source_file in self.repository.files.items():
            subsystem = self._subsystem_name(source_file)

            if subsystem not in buckets:
                buckets[subsystem] = {
                    "units": [],
                    "files": [],
                    "classes": [],
                    "methods": []
                }

            bucket = buckets[subsystem]
            bucket["units"].append(unit_name)

            if source_file:
                bucket["files"].append(source_file)

            bucket["classes"].extend(
                cls.get("name")
                for cls in self.repository.classes_by_unit.get(unit_name, [])
            )
            bucket["methods"].extend(
                self._qualified_method_name(method)
                for method in self.repository.methods_by_unit.get(
                    unit_name,
                    []
                )
            )

        summaries = []

        for subsystem in sorted(buckets):
            bucket = buckets[subsystem]
            units = sorted(set(bucket["units"]))
            files = sorted(set(bucket["files"]))
            classes = sorted(set(bucket["classes"]))
            methods = sorted(set(bucket["methods"]))

            metrics = {
                "unit_count": len(units),
                "file_count": len(files),
                "class_count": len(classes),
                "method_count": len(methods)
            }
            related = {
                "units": units[:40],
                "classes": classes[:40],
                "methods": methods[:40]
            }

            summary = self._sentence(
                f"{subsystem} is a repository subsystem",
                f"covering {len(files)} files",
                f"{len(units)} units",
                f"{len(classes)} classes",
                f"and {len(methods)} methods"
            )

            summaries.append(
                SummaryRecord(
                    summary_id=f"summary:subsystem:{subsystem}",
                    summary_type="subsystem",
                    name=subsystem,
                    summary=summary,
                    metrics=metrics,
                    related_symbols=related
                )
            )

        return summaries

    def build_architecture_summary(self):
        stats = self.repository.statistics()
        top_dependency_units = self._top_items(
            self.repository.dependencies,
            limit=10
        )
        top_dependent_units = self._top_items(
            self.repository.reverse_dependencies,
            limit=10
        )
        root_classes = [
            class_name for class_name in sorted(self.repository.classes_by_name)
            if not self.repository.get_parent(class_name)
        ][:30]

        metrics = {
            "files": stats.get("files"),
            "units": stats.get("units"),
            "classes": stats.get("classes"),
            "methods": stats.get("methods"),
            "dependency_edges": stats.get("dependency_edges"),
            "inheritance_edges": stats.get("inheritance_edges"),
            "call_edges": stats.get("call_edges")
        }
        related = {
            "top_dependency_units": top_dependency_units,
            "top_dependent_units": top_dependent_units,
            "sample_root_classes": root_classes
        }

        summary = self._sentence(
            "The repository is indexed as a Pascal codebase",
            f"with {stats.get('files')} files",
            f"{stats.get('units')} units",
            f"{stats.get('classes')} unique class names",
            f"{stats.get('methods')} method definitions",
            f"{stats.get('dependency_edges')} dependency edges",
            f"{stats.get('inheritance_edges')} inheritance edges",
            f"and {stats.get('call_edges')} static call edges"
        )

        return SummaryRecord(
            summary_id="summary:architecture:repository",
            summary_type="architecture",
            name="repository",
            summary=summary,
            metrics=metrics,
            related_symbols=related
        )

    def _requested_types(self, summary_types):
        if summary_types is None:
            return {"method", "class", "unit", "subsystem", "architecture"}

        if isinstance(summary_types, str):
            return {summary_types.casefold()}

        return {
            summary_type.casefold()
            for summary_type in summary_types
        }

    def _qualified_method_name(self, method):
        class_name = method.get("class")
        method_name = method.get("method")

        if class_name:
            return f"{class_name}.{method_name}"

        return method_name

    def _subsystem_name(self, source_file):
        if not source_file:
            return "unknown"

        parts = Path(source_file).parts

        if len(parts) >= 2:
            return "/".join(parts[:2])

        return parts[0]

    def _top_items(self, mapping, limit):
        items = [
            {
                "name": key,
                "count": len(value)
            }
            for key, value in mapping.items()
        ]
        items.sort(
            key=lambda item: (
                item["count"],
                item["name"]
            ),
            reverse=True
        )

        return items[:limit]

    def _sentence(self, *parts):
        values = [
            part for part in parts
            if part
        ]

        return ", ".join(values) + "."


class SummaryArtifactWriter:
    """
    Writes summary artifacts to disk.
    """

    def __init__(self, output_directory):
        self.output_directory = Path(output_directory)

    def write(self, summaries):
        self.output_directory.mkdir(parents=True, exist_ok=True)
        summaries_path = self.output_directory / "summaries.jsonl"
        manifest_path = self.output_directory / "manifest.json"

        with summaries_path.open("w", encoding="utf-8") as fp:
            for summary in summaries:
                fp.write(json.dumps(summary.to_dict(), sort_keys=True))
                fp.write("\n")

        counts = {}

        for summary in summaries:
            counts[summary.summary_type] = counts.get(
                summary.summary_type,
                0
            ) + 1

        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "summary_count": len(summaries),
            "summary_counts": counts,
            "files": {
                "summaries": summaries_path.name
            }
        }

        with manifest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest, fp, indent=2, sort_keys=True)

        return manifest


def generate_repository_summaries(
    repository,
    output_directory,
    summary_types=None
):
    summarizer = RepositorySummarizer(repository)
    summaries = summarizer.build_summaries(summary_types=summary_types)
    writer = SummaryArtifactWriter(output_directory)

    return writer.write(summaries)
