"""
Modernization prompt generation.

This module converts structured modernization context into bounded LLM-ready
prompt messages. It does not call a model; generation backends can consume the
returned prompt package in the next modernization stage.
"""

import argparse
import json

try:
    from .context import ModernizationContextAssembler
    from .file_migration import FileMigrationPlanner
    from .java_templates import JavaTargetDesignTemplates
    from .shared_support import JavaSharedSupportCatalog
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.modernization.context import (
        ModernizationContextAssembler
    )
    from repository_intelligence.modernization.file_migration import (
        FileMigrationPlanner
    )
    from repository_intelligence.modernization.java_templates import (
        JavaTargetDesignTemplates
    )
    from repository_intelligence.modernization.shared_support import (
        JavaSharedSupportCatalog
    )
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


SYSTEM_PROMPT = """
You are a senior software modernization engineer converting legacy Delphi/Object
Pascal code to Java. Use only the supplied repository context as evidence. When
information is missing or ambiguous, state the gap instead of inventing details.
Preserve behavior before improving design.
""".strip()


USER_TASK_TEMPLATE = """
Modernization task:
{task}

Target language:
{target_language}

Expected response:
1. Summarize the source behavior and migration scope.
2. Propose the Java package/class/method design.
3. Map Pascal constructs to Java constructs using the target design templates.
4. Identify dependencies, callers, subclasses, and equivalent patterns that may affect the migration.
5. Provide Java-oriented implementation guidance.
6. List risks, assumptions, and validation steps.
""".strip()


FILE_MIGRATION_SYSTEM_PROMPT = """
You are a senior software modernization engineer converting complete
Delphi/Object Pascal units to Java. Convert the supplied source file as a
cohesive unit, preserving externally visible behavior before improving design.
Use only the supplied file, dependency metadata, and Java target templates as
evidence. If complete Java cannot be produced, generate compilable skeletons
and list unresolved items.
""".strip()


FILE_MIGRATION_RESPONSE_SCHEMA = """
Return only a JSON object with this shape:
{
  "files": [
    {
      "path": "relative Java source path",
      "language": "java",
      "content": "Java source code"
    }
  ],
  "classes": [
    {
      "name": "Java class or interface name",
      "source_symbol": "Pascal symbol",
      "responsibility": "short responsibility summary"
    }
  ],
  "methods": [
    {
      "name": "Java method name",
      "source_symbol": "Pascal method or routine",
      "notes": "mapping notes"
    }
  ],
  "notes": ["important migration notes"],
  "unresolved_items": ["missing information or manual follow-up"]
}
Do not wrap the JSON in markdown fences.
""".strip()


FILE_MIGRATION_USER_TEMPLATE = """
File migration task:
Convert the complete Pascal unit {unit} from {source_file} to Java.

Target package:
{target_package}

Target directory:
{target_directory}

File hint:
{file_hint}

Migration requirements:
1. Treat the supplied Pascal source as the primary migration scope.
2. Preserve all public interfaces, classes, records, enums, constants, and
   routines that are present in the unit when they are relevant to Java callers.
3. Split Java output into multiple files when Java visibility rules require it.
4. Prefer idiomatic Java packages, classes, interfaces, enums, and exceptions
   while keeping source-symbol traceability in classes/methods metadata.
5. Use stubs for unresolved repository dependencies only when needed for a
   coherent Java output, and list those stubs in unresolved_items.
6. Keep generated paths relative to the output root.
""".strip()


class ModernizationPromptBuilder:
    """
    Renders structured modernization context into LLM prompt sections.

    Prompt generation is kept separate from context assembly so tests can verify
    prompt shape without requiring ChromaDB or a model backend.
    """

    def __init__(
        self,
        max_source_chars=12000,
        max_summary_items=10,
        max_graph_items=10,
        max_symbol_items=12
    ):
        self.max_source_chars = max_source_chars
        self.max_summary_items = max_summary_items
        self.max_graph_items = max_graph_items
        self.max_symbol_items = max_symbol_items

    def build_prompt(self, context):
        task = context.get("task", {})
        context_text = self.render_context_sections(context)
        system = SYSTEM_PROMPT
        user = USER_TASK_TEMPLATE.format(
            task=task.get("description"),
            target_language=task.get("target_language", "Java")
        )
        full_prompt = "\n\n".join([
            "SYSTEM:",
            system,
            "USER:",
            user,
            "REPOSITORY CONTEXT:",
            context_text
        ])

        return {
            "task": task,
            "messages": [
                {
                    "role": "system",
                    "content": system
                },
                {
                    "role": "user",
                    "content": user + "\n\n" + context_text
                }
            ],
            "sections": {
                "repository_context": context_text,
                "target_design": self._target_design_section(context),
                "source": self._source_section(context)
            },
            "prompt": full_prompt,
            "statistics": {
                "prompt_chars": len(full_prompt),
                "source_chars": len(self._source_section(context)),
                "source_truncated": self._source_truncated(context),
                "symbols": len(context.get("symbols", [])),
                "summaries": len(context.get("summaries", [])),
                "source_items": len(context.get("source_context", []))
            }
        }

    def render_context_sections(self, context):
        sections = [
            self._symbol_section(context),
            self._summary_section(context),
            self._target_design_section(context),
            self._graph_section(context),
            self._source_section(context),
            self._guidance_section(context)
        ]

        return "\n\n".join(
            section
            for section in sections
            if section
        )

    def _symbol_section(self, context):
        lines = ["## Retrieved Symbols"]

        for symbol in context.get("symbols", [])[:self.max_symbol_items]:
            lines.append(
                "- {type} {name} unit={unit} class={class_name} "
                "method={method_name} file={file} score={score} "
                "sources={sources}".format(
                    type=symbol.get("document_type"),
                    name=symbol.get("name"),
                    unit=symbol.get("unit"),
                    class_name=symbol.get("class_name"),
                    method_name=symbol.get("method_name"),
                    file=symbol.get("file"),
                    score=symbol.get("score"),
                    sources=",".join(symbol.get("sources", []))
                )
            )

        return "\n".join(lines)

    def _summary_section(self, context):
        summaries = context.get("summaries", [])[:self.max_summary_items]

        if not summaries:
            return ""

        lines = ["## Repository Summaries"]

        for summary in summaries:
            lines.append(
                "- {type} {name}: {text}".format(
                    type=summary.get("summary_type"),
                    name=summary.get("name"),
                    text=summary.get("summary")
                )
            )

        return "\n".join(lines)

    def _target_design_section(self, context):
        target_design = context.get("target_design", {})
        prompt_section = target_design.get("prompt_section")

        if prompt_section:
            return "## Java Target Design\n" + prompt_section

        templates = target_design.get("templates", [])

        if not templates:
            return ""

        lines = ["## Java Target Design"]

        for template in templates:
            lines.append(
                "- {template_id}: {title}".format(
                    template_id=template.get("template_id"),
                    title=template.get("title")
                )
            )

        return "\n".join(lines)

    def _graph_section(self, context):
        graph_items = context.get("graph_context", [])[:self.max_graph_items]

        if not graph_items:
            return ""

        lines = ["## Graph Context"]

        for item in graph_items:
            lines.append(
                "- {type} {name}: {relationships}".format(
                    type=item.get("document_type"),
                    name=item.get("name"),
                    relationships=json.dumps(
                        item.get("relationships", {}),
                        sort_keys=True
                    )
                )
            )

        return "\n".join(lines)

    def _source_section(self, context):
        source_items = context.get("source_context", [])

        if not source_items:
            return ""

        lines = ["## Source Context"]
        remaining = self.max_source_chars

        for item in source_items:
            source = item.get("source") or item.get("snippet") or ""

            if remaining <= 0:
                break

            clipped = source[:remaining]
            remaining -= len(clipped)
            truncated = item.get("truncated") or len(clipped) < len(source)
            lines.extend([
                "",
                "### {type} {symbol} ({file}:{start}-{end})".format(
                    type=item.get("document_type"),
                    symbol=item.get("symbol"),
                    file=item.get("file"),
                    start=item.get("start_line"),
                    end=item.get("end_line")
                ),
                f"Extraction: {item.get('extraction_kind')}",
                f"Truncated: {truncated}",
                "```pascal",
                clipped,
                "```"
            ])

        if remaining <= 0:
            lines.append(
                "Source budget exhausted; additional source context omitted."
            )

        return "\n".join(lines)

    def _guidance_section(self, context):
        guidance = context.get("modernization_guidance", {})
        lines = ["## Modernization Guidance"]

        if guidance.get("touched_files"):
            lines.append("Touched files:")
            lines.extend(
                f"- {file_name}"
                for file_name in guidance.get("touched_files", [])
            )

        if guidance.get("next_actions"):
            lines.append("Next actions:")
            lines.extend(
                f"- {item}"
                for item in guidance.get("next_actions", [])
            )

        if guidance.get("risk_notes"):
            lines.append("Risk notes:")
            lines.extend(
                f"- {item}"
                for item in guidance.get("risk_notes", [])
            )

        return "\n".join(lines)

    def _source_truncated(self, context):
        source_items = context.get("source_context", [])
        total = 0

        for item in source_items:
            source = item.get("source") or item.get("snippet") or ""
            total += len(source)

            if item.get("truncated"):
                return True

        return total > self.max_source_chars


class FileMigrationPromptBuilder:
    """
    Renders one planned Pascal unit migration job into an LLM-ready prompt.

    This prompt is intentionally file-oriented. Unlike retrieval prompts, it
    treats the complete source unit as the migration scope and uses repository
    metadata as supporting context.
    """

    def __init__(
        self,
        max_source_chars=60000,
        java_templates=None,
        shared_support=None
    ):
        self.max_source_chars = max_source_chars
        self.java_templates = java_templates or JavaTargetDesignTemplates()
        self.shared_support = shared_support or JavaSharedSupportCatalog()

    def build_prompt(self, job, plan=None):
        source_section = self._source_section(job)
        context_text = "\n\n".join([
            self._job_section(job),
            self._ordering_section(job),
            self._dependency_section(job),
            self._symbol_section(job),
            self._target_design_section(),
            self._shared_support_section(),
            source_section,
            self._response_schema_section()
        ])
        user = FILE_MIGRATION_USER_TEMPLATE.format(
            unit=job["source"].get("unit"),
            source_file=job["source"].get("file"),
            target_package=job["target"].get("package"),
            target_directory=job["target"].get("directory"),
            file_hint=job["target"].get("file_hint")
        )
        full_prompt = "\n\n".join([
            "SYSTEM:",
            FILE_MIGRATION_SYSTEM_PROMPT,
            "USER:",
            user,
            "FILE MIGRATION CONTEXT:",
            context_text
        ])

        return {
            "job_id": job.get("job_id"),
            "source": job.get("source", {}),
            "target": job.get("target", {}),
            "messages": [
                {
                    "role": "system",
                    "content": FILE_MIGRATION_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user + "\n\n" + context_text
                }
            ],
            "sections": {
                "job": self._job_section(job),
                "ordering": self._ordering_section(job),
                "dependencies": self._dependency_section(job),
                "symbols": self._symbol_section(job),
                "target_design": self._target_design_section(),
                "source": source_section,
                "response_schema": self._response_schema_section()
            },
            "prompt": full_prompt,
            "statistics": {
                "prompt_chars": len(full_prompt),
                "source_chars": self._source_chars(job),
                "source_prompt_chars": len(source_section),
                "source_truncated": self._source_truncated(job),
                "class_count": job.get("symbols", {}).get("class_count", 0),
                "method_count": job.get("symbols", {}).get("method_count", 0),
                "dependency_count": len(
                    job.get("source", {}).get("dependencies", [])
                )
            },
            "plan_statistics": (plan or {}).get("statistics", {})
        }

    def _job_section(self, job):
        source = job.get("source", {})
        target = job.get("target", {})
        lines = [
            "## File Migration Job",
            f"Job id: {job.get('job_id')}",
            f"Sequence: {job.get('sequence')}",
            f"Pascal unit: {source.get('unit')}",
            f"Pascal file: {source.get('file')}",
            f"Source path: {source.get('path')}",
            f"Target package: {target.get('package')}",
            f"Target directory: {target.get('directory')}",
            f"Target file hint: {target.get('file_hint')}"
        ]

        if job.get("planning_notes"):
            lines.append("Planning notes:")
            lines.extend(
                f"- {note}"
                for note in job.get("planning_notes", [])
            )

        return "\n".join(lines)

    def _dependency_section(self, job):
        source = job.get("source", {})
        lines = ["## Unit Dependencies"]
        dependencies = source.get("dependencies", [])
        dependents = source.get("dependents", [])

        lines.append("Direct dependencies:")
        lines.extend(
            f"- {dependency}"
            for dependency in dependencies[:50]
        )

        if len(dependencies) > 50:
            lines.append(
                f"- ... {len(dependencies) - 50} additional dependencies omitted"
            )

        lines.append("Direct dependents:")
        lines.extend(
            f"- {dependent}"
            for dependent in dependents[:50]
        )

        if len(dependents) > 50:
            lines.append(
                f"- ... {len(dependents) - 50} additional dependents omitted"
            )

        return "\n".join(lines)

    def _ordering_section(self, job):
        ordering = job.get("ordering") or {}

        if not ordering:
            return ""

        lines = [
            "## Migration Dependency Ordering",
            f"Order mode: {ordering.get('mode')}",
            f"Position: {ordering.get('position')}",
            f"Wave: {ordering.get('wave')}",
            f"Dependency ready: {ordering.get('dependency_ready')}",
            f"Cycle participant: {ordering.get('cycle_participant')}"
        ]

        lines.append("Internal dependencies already scheduled earlier:")
        lines.extend(
            f"- {dependency}"
            for dependency in ordering.get("prior_internal_dependencies", [])
        )

        lines.append("Internal dependencies not yet scheduled:")
        lines.extend(
            f"- {dependency}"
            for dependency in ordering.get("later_internal_dependencies", [])
        )

        lines.append("External dependencies outside this batch:")
        lines.extend(
            f"- {dependency}"
            for dependency in ordering.get("external_dependencies", [])[:50]
        )

        if len(ordering.get("external_dependencies", [])) > 50:
            lines.append(
                "- ... {count} additional external dependencies omitted".format(
                    count=len(ordering["external_dependencies"]) - 50
                )
            )

        return "\n".join(lines)

    def _symbol_section(self, job):
        symbols = job.get("symbols", {})
        classes = symbols.get("classes", [])
        methods = symbols.get("methods", [])
        lines = ["## Indexed Symbols"]
        lines.append(f"Class count: {symbols.get('class_count', 0)}")
        lines.extend(
            f"- class {class_name}"
            for class_name in classes[:60]
        )

        if len(classes) > 60:
            lines.append(f"- ... {len(classes) - 60} additional classes omitted")

        lines.append(f"Method count: {symbols.get('method_count', 0)}")
        lines.extend(
            f"- method {method_name}"
            for method_name in methods[:120]
        )

        if len(methods) > 120:
            lines.append(f"- ... {len(methods) - 120} additional methods omitted")

        return "\n".join(lines)

    def _target_design_section(self):
        return (
            "## Java Target Design\n"
            + self.java_templates.as_prompt_section(
                template_ids=[
                    "pascal_unit_to_java_package",
                    "pascal_class_to_java_class",
                    "pascal_routine_to_java_method",
                    "pascal_property_to_accessors",
                    "pascal_constructor_destructor_to_lifecycle",
                    "pascal_exception_to_java_exception",
                    "global_routine_to_utility_method"
                ]
            )
        )

    def _shared_support_section(self):
        return (
            "## Shared Java Support\n"
            + self.shared_support.render()
            + "\n\nDo not include these shared support files in the response "
            "files array. Reference them with imports from their canonical "
            "packages instead."
        )

    def _source_section(self, job):
        extraction = job.get("source_extraction") or {}

        if not extraction.get("available"):
            return (
                "## Complete Pascal Source\n"
                "Source was not available. Generate skeletons and list the "
                "missing source file as an unresolved item."
            )

        source = extraction.get("source", "")
        clipped = source[:self.max_source_chars]
        truncated = len(clipped) < len(source) or extraction.get("truncated")

        lines = [
            "## Complete Pascal Source",
            f"File: {extraction.get('file')}",
            f"Path: {extraction.get('path')}",
            f"Lines: {extraction.get('line_count')}",
            f"Characters: {extraction.get('character_count')}",
            f"Truncated: {truncated}",
            "```pascal",
            clipped,
            "```"
        ]

        if truncated:
            lines.append(
                "Source budget exhausted; prompt does not contain the full unit."
            )

        return "\n".join(lines)

    def _response_schema_section(self):
        return "## Required Response Schema\n" + FILE_MIGRATION_RESPONSE_SCHEMA

    def _source_chars(self, job):
        extraction = job.get("source_extraction") or {}
        return len(extraction.get("source", ""))

    def _source_truncated(self, job):
        extraction = job.get("source_extraction") or {}
        source = extraction.get("source", "")
        return bool(
            extraction.get("truncated")
            or len(source) > self.max_source_chars
        )


class FileMigrationPromptGenerator:
    """
    Plans file migrations and renders one prompt package per planned unit.
    """

    def __init__(
        self,
        repository,
        source_root="doublecmd",
        target_base_package="org.doublecmd",
        prompt_builder=None
    ):
        self.repository = repository
        self.planner = FileMigrationPlanner(
            repository,
            source_root=source_root,
            target_base_package=target_base_package
        )
        self.prompt_builder = prompt_builder or FileMigrationPromptBuilder()

    def generate(
        self,
        include=None,
        exclude=None,
        units=None,
        limit=None,
        order="dependency"
    ):
        plan = self.planner.build_plan(
            include=include,
            exclude=exclude,
            units=units,
            limit=limit,
            order=order,
            include_source=True
        )
        prompts = [
            self.prompt_builder.build_prompt(job, plan=plan)
            for job in plan.get("jobs", [])
        ]

        return {
            "plan": plan,
            "prompts": prompts,
            "statistics": {
                "job_count": len(plan.get("jobs", [])),
                "prompt_count": len(prompts),
                "prompt_chars": sum(
                    prompt["statistics"]["prompt_chars"]
                    for prompt in prompts
                ),
                "source_truncated_count": sum(
                    1
                    for prompt in prompts
                    if prompt["statistics"]["source_truncated"]
                )
            }
        }


class ModernizationPromptGenerator:
    """
    Combines context assembly and prompt rendering.
    """

    def __init__(
        self,
        repository,
        context_options=None,
        prompt_builder=None
    ):
        self.repository = repository
        self.context_options = context_options or {}
        self.prompt_builder = prompt_builder or ModernizationPromptBuilder()

    def generate(
        self,
        task,
        target_language="Java",
        limit=8,
        lexical_limit=25,
        vector_limit=25,
        graph_depth=1,
        document_types=None,
        include_source=True,
        max_source_lines=160
    ):
        assembler = ModernizationContextAssembler(
            self.repository,
            **self.context_options
        )

        try:
            context = assembler.build_context(
                task,
                target_language=target_language,
                limit=limit,
                lexical_limit=lexical_limit,
                vector_limit=vector_limit,
                graph_depth=graph_depth,
                document_types=document_types,
                include_source=include_source,
                max_snippet_lines=max_source_lines
            )
        finally:
            assembler.close()

        prompt = self.prompt_builder.build_prompt(context)

        return {
            "context": context,
            "prompt": prompt
        }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate an LLM-ready modernization prompt."
    )
    parser.add_argument(
        "task",
        help="Modernization task or natural-language query."
    )
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing generated repository JSON artifacts."
    )
    parser.add_argument(
        "--artifacts",
        default="output/embeddings",
        help="Directory containing embedding artifacts."
    )
    parser.add_argument(
        "--chroma",
        default="output/chroma",
        help="Persistent ChromaDB directory."
    )
    parser.add_argument(
        "--summaries",
        default="output/summaries",
        help="Directory containing generated summaries."
    )
    parser.add_argument(
        "--source-root",
        default="doublecmd",
        help="Root directory for source files referenced by metadata."
    )
    parser.add_argument(
        "--target-language",
        default="Java",
        help="Modernization target language label."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum retrieval results from each retrieval layer."
    )
    parser.add_argument(
        "--types",
        nargs="*",
        choices=["unit", "class", "method", "subsystem"],
        default=None,
        help="Optional document types to include."
    )
    parser.add_argument(
        "--graph-depth",
        type=int,
        default=1,
        help="Graph expansion depth."
    )
    parser.add_argument(
        "--max-source-lines",
        type=int,
        default=160,
        help="Maximum source lines per extracted source item."
    )
    parser.add_argument(
        "--max-source-chars",
        type=int,
        default=12000,
        help="Maximum source characters included in prompt text."
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Skip source extraction."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured prompt package as JSON."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(
        load_repository(args.input)
    )
    generator = ModernizationPromptGenerator(
        repository,
        context_options={
            "artifacts_directory": args.artifacts,
            "persist_directory": args.chroma,
            "summary_directory": args.summaries,
            "source_root": args.source_root
        },
        prompt_builder=ModernizationPromptBuilder(
            max_source_chars=args.max_source_chars
        )
    )
    result = generator.generate(
        args.task,
        target_language=args.target_language,
        limit=args.limit,
        graph_depth=args.graph_depth,
        document_types=args.types,
        include_source=not args.no_source,
        max_source_lines=args.max_source_lines
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["prompt"]["prompt"])


if __name__ == "__main__":
    main()
