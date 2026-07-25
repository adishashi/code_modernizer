"""
Batch file-by-file Java generation for modernization.

This module is the first executable batch layer for full-file migration. It
combines file-oriented prompts, a pluggable generation backend, persistent Java
file writing, optional validation, and run manifests for resumable inspection.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from .generation import (
        DEFAULT_LANGCHAIN_GENERATION_MODEL,
        LangChainCodeGenerationBackend,
        load_env_file,
        write_generated_java_files
    )
    from .prompts import FileMigrationPromptBuilder, FileMigrationPromptGenerator
    from .shared_support import JavaSharedSupportCatalog
    from .validation import validate_generated_code
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.modernization.generation import (
        DEFAULT_LANGCHAIN_GENERATION_MODEL,
        LangChainCodeGenerationBackend,
        load_env_file,
        write_generated_java_files
    )
    from repository_intelligence.modernization.prompts import (
        FileMigrationPromptBuilder,
        FileMigrationPromptGenerator
    )
    from repository_intelligence.modernization.shared_support import (
        JavaSharedSupportCatalog
    )
    from repository_intelligence.modernization.validation import (
        validate_generated_code
    )
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


class DryRunFileGenerationBackend:
    """
    Deterministic backend for validating the batch migration workflow.

    It uses the file prompt metadata to produce a small Java skeleton. This is
    intentionally separate from DryRunCodeGenerationBackend because full-file
    jobs are unit-scoped and already provide target package/file hints.
    """

    backend_name = "dry_run_file"

    def generate(self, prompt_package):
        prompt = prompt_package.get("prompt", {})
        source = prompt.get("source", {})
        target = prompt.get("target", {})
        unit_name = source.get("unit") or "MigrationUnit"
        package_name = target.get("package") or "org.doublecmd.migration"
        file_hint = target.get("file_hint")
        class_name = self._class_name(file_hint, unit_name)
        content = "\n".join([
            f"package {package_name};",
            "",
            "/**",
            " * Dry-run file migration skeleton.",
            f" * Source unit: {unit_name}",
            f" * Source file: {source.get('file')}",
            " */",
            f"public final class {class_name} {{",
            f"    private {class_name}() {{",
            "    }",
            "}"
        ])
        path = file_hint or (
            package_name.replace(".", "/") + f"/{class_name}.java"
        )

        return {
            "backend": self.backend_name,
            "raw_output": content,
            "structured_output": {
                "files": [
                    {
                        "path": path,
                        "language": "java",
                        "content": content
                    }
                ],
                "classes": [
                    {
                        "name": class_name,
                        "source_symbol": unit_name,
                        "responsibility": "Dry-run full-file migration skeleton."
                    }
                ],
                "methods": [],
                "notes": [
                    "Dry-run backend did not call an LLM.",
                    "Use --backend langchain for model-backed file migration."
                ],
                "unresolved_items": [
                    "Implementation requires model-backed generation."
                ]
            }
        }

    def _class_name(self, file_hint, unit_name):
        if file_hint:
            return Path(file_hint).stem

        cleaned = "".join(
            character
            for character in str(unit_name)
            if character.isalnum()
        )

        if cleaned.lower().startswith("u") and len(cleaned) > 1:
            cleaned = cleaned[1:]

        return cleaned[:1].upper() + cleaned[1:] if cleaned else "MigrationUnit"


class FileMigrationBatchGenerator:
    """
    Orchestrates batch generation from planned file migration prompts.
    """

    def __init__(
        self,
        repository,
        backend=None,
        source_root="doublecmd",
        target_base_package="org.doublecmd",
        prompt_builder=None,
        shared_support=None
    ):
        self.repository = repository
        self.backend = backend or DryRunFileGenerationBackend()
        self.shared_support = shared_support or JavaSharedSupportCatalog()
        self.prompt_generator = FileMigrationPromptGenerator(
            repository,
            source_root=source_root,
            target_base_package=target_base_package,
            prompt_builder=prompt_builder or FileMigrationPromptBuilder()
        )

    def generate(
        self,
        include=None,
        exclude=None,
        units=None,
        limit=None,
        order="dependency",
        output_directory="output/generated_java",
        run_directory="output/migration_runs",
        overwrite=True,
        validate=False,
        compile_validation=False,
        resume_run=None,
        force_rerun=False,
        include_shared_support=True,
        overwrite_shared_support=False
    ):
        prompt_package = self.prompt_generator.generate(
            include=include,
            exclude=exclude,
            units=units,
            limit=limit,
            order=order
        )
        run_root = (
            Path(resume_run)
            if resume_run
            else self._run_root(run_directory)
        )
        raw_dir = run_root / "raw_outputs"
        prompt_dir = run_root / "prompts"
        validation_dir = run_root / "validation_reports"
        artifact_dir = run_root / "artifacts"

        for directory in [raw_dir, prompt_dir, validation_dir, artifact_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        planned_jobs = {
            job.get("job_id"): job
            for job in prompt_package["plan"].get("jobs", [])
        }
        previous_jobs = self._load_previous_jobs(run_root) if resume_run else {}
        job_results = []
        shared_support_report = (
            self.shared_support.write_files(
                output_directory,
                overwrite=overwrite_shared_support
            )
            if include_shared_support
            else self._empty_shared_support_report(output_directory)
        )
        claimed_output_paths = set(
            self.shared_support.protected_paths()
            if include_shared_support
            else set()
        )
        protected_type_names = (
            self.shared_support.protected_type_names()
            if include_shared_support
            else set()
        )
        artifact_writer = FileMigrationArtifactWriter(run_root, artifact_dir)

        for prompt in prompt_package["prompts"]:
            job_id = prompt["job_id"]
            previous_job = previous_jobs.get(job_id)

            if (
                previous_job
                and not force_rerun
                and self._can_resume_job(previous_job)
            ):
                previous_job = dict(previous_job)
                previous_job["resume_status"] = "reused"
                job_results.append(previous_job)
                claimed_output_paths.update(
                    self._written_output_paths(previous_job)
                )
                continue

            safe_job_id = self._safe_name(job_id)
            generation = self.backend.generate({"prompt": prompt})
            generation["written_files"] = write_generated_java_files(
                generation,
                output_directory,
                overwrite=overwrite,
                protected_paths=claimed_output_paths,
                protected_type_names=protected_type_names
            )
            claimed_output_paths.update(self._written_output_paths({
                "written_files": generation.get("written_files", {})
            }))

            if validate or compile_validation:
                generation["validation"] = validate_generated_code(
                    generation,
                    compile_sources=compile_validation
                )
                self._write_json(
                    validation_dir / f"{safe_job_id}.json",
                    generation["validation"]
                )

            raw_path = raw_dir / f"{safe_job_id}.txt"
            prompt_path = prompt_dir / f"{safe_job_id}.json"
            raw_path.write_text(
                generation.get("raw_output", ""),
                encoding="utf-8"
            )
            self._write_json(prompt_path, prompt)
            artifact = artifact_writer.write(
                prompt=prompt,
                planned_job=planned_jobs.get(job_id, {}),
                generation=generation,
                raw_output_path=raw_path,
                prompt_path=prompt_path,
                validation_path=(
                    validation_dir / f"{safe_job_id}.json"
                    if generation.get("validation")
                    else None
                ),
                status=self._status(generation)
            )

            job_results.append({
                "job_id": job_id,
                "source": prompt.get("source", {}),
                "target": prompt.get("target", {}),
                "backend": generation.get("backend"),
                "status": self._status(generation),
                "resume_status": (
                    "rerun"
                    if previous_job
                    else "generated"
                ),
                "raw_output": str(raw_path),
                "prompt": str(prompt_path),
                "artifact": artifact["path"],
                "written_files": generation.get("written_files", {}),
                "validation": generation.get("validation"),
                "structured_output": generation.get("structured_output", {})
            })

        batch_validation = self._batch_validation(job_results)
        result = {
            "purpose": "file_migration_batch_generation",
            "run_directory": str(run_root),
            "output_directory": str(Path(output_directory)),
            "backend": getattr(self.backend, "backend_name", type(self.backend).__name__),
            "artifact_directory": str(artifact_dir),
            "shared_support": {
                "enabled": include_shared_support,
                "files": [
                    support_file.to_dict()
                    for support_file in self.shared_support.list_files()
                ] if include_shared_support else [],
                "persistence": shared_support_report
            },
            "batch_validation": batch_validation,
            "resume": {
                "enabled": bool(resume_run),
                "source_run": str(run_root) if resume_run else None,
                "force_rerun": force_rerun,
                "reused_jobs": sum(
                    1
                    for job in job_results
                    if job.get("resume_status") == "reused"
                ),
                "generated_jobs": sum(
                    1
                    for job in job_results
                    if job.get("resume_status") == "generated"
                ),
                "rerun_jobs": sum(
                    1
                    for job in job_results
                    if job.get("resume_status") == "rerun"
                )
            },
            "plan": prompt_package["plan"],
            "statistics": self._statistics(job_results),
            "jobs": job_results
        }
        self._write_json(run_root / "manifest.json", result)
        self._write_jsonl(run_root / "jobs.jsonl", job_results)
        self._write_jsonl(
            run_root / "artifacts.jsonl",
            self._artifact_summaries(job_results)
        )

        return result

    def _written_output_paths(self, job):
        return {
            file_record.get("path", "").replace("\\", "/")
            for file_record in (
                job.get("written_files", {}).get("written", [])
            )
            if file_record.get("path")
        }

    def _empty_shared_support_report(self, output_directory):
        return {
            "output_directory": str(Path(output_directory).resolve()),
            "written": [],
            "skipped": [],
            "summary": {
                "written": 0,
                "skipped": 0
            }
        }

    def _batch_validation(self, jobs):
        """
        Validate relationships that span multiple migration jobs.

        Per-job validation cannot see whether two independently generated units
        target the same Java file or top-level type. The batch report keeps
        those collisions visible before a full migration overwrites output or
        produces an impossible Java source set.
        """

        findings = []
        paths = {}
        types = {}

        for job in jobs:
            job_id = job.get("job_id")

            for file_record in (
                job.get("structured_output", {}).get("files", [])
            ):
                path = file_record.get("path")

                if path:
                    normalized_path = path.replace("\\", "/")
                    previous_job = paths.get(normalized_path)

                    if previous_job and previous_job != job_id:
                        findings.append({
                            "severity": "error",
                            "code": "batch_duplicate_file_path",
                            "message": (
                                "Multiple migration jobs generated the same "
                                "Java file path."
                            ),
                            "file": normalized_path,
                            "jobs": [previous_job, job_id]
                        })
                    else:
                        paths[normalized_path] = job_id

            validation_files = self._validation_files_for_job(job)

            for file_report in validation_files:
                package_name = file_report.get("package")
                path = file_report.get("path")

                for declaration in file_report.get("declarations", []):
                    if declaration.get("depth", 0) != 0:
                        continue

                    type_name = declaration.get("name")

                    if not type_name:
                        continue

                    qualified_name = (
                        f"{package_name}.{type_name}"
                        if package_name
                        else type_name
                    )
                    previous = types.get(qualified_name)

                    if previous and previous["job_id"] != job_id:
                        findings.append({
                            "severity": "error",
                            "code": "batch_duplicate_type_declaration",
                            "message": (
                                "Multiple migration jobs generated the same "
                                "top-level Java type."
                            ),
                            "file": path,
                            "type": qualified_name,
                            "jobs": [previous["job_id"], job_id]
                        })
                    else:
                        types[qualified_name] = {
                            "job_id": job_id,
                            "path": path
                        }

        errors = [
            finding
            for finding in findings
            if finding["severity"] == "error"
        ]
        warnings = [
            finding
            for finding in findings
            if finding["severity"] == "warning"
        ]

        return {
            "passed": not errors,
            "status": "passed" if not errors else "failed",
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "findings": len(findings)
            },
            "findings": findings
        }

    def _validation_files_for_job(self, job):
        validation_files = (
            job.get("validation", {}) or {}
        ).get("files", [])

        if validation_files:
            return validation_files

        # Batch validation is useful even when users skip per-job validation.
        # Run the deterministic validator in memory and use only the normalized
        # file/declaration summaries for cross-job duplicate detection.
        report = validate_generated_code({
            "structured_output": job.get("structured_output", {})
        })
        return report.get("files", [])

    def _load_previous_jobs(self, run_root):
        manifest_path = Path(run_root) / "manifest.json"

        if manifest_path.exists():
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                manifest = None

            if manifest:
                return {
                    job.get("job_id"): job
                    for job in manifest.get("jobs", [])
                    if job.get("job_id")
                }

        return self._load_previous_jobs_from_artifacts(run_root)

    def _load_previous_jobs_from_artifacts(self, run_root):
        artifact_dir = Path(run_root) / "artifacts"

        if not artifact_dir.exists():
            return {}

        jobs = {}

        for artifact_path in sorted(artifact_dir.glob("*.json")):
            try:
                artifact = json.loads(
                    artifact_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                continue

            job = self._job_from_artifact(artifact, artifact_path)

            if job.get("job_id"):
                jobs[job["job_id"]] = job

        return jobs

    def _job_from_artifact(self, artifact, artifact_path):
        generation = artifact.get("generation", {})
        validation = artifact.get("validation", {}) or {}
        prompt = artifact.get("prompt", {}) or {}

        return {
            "job_id": artifact.get("job_id"),
            "source": artifact.get("source", {}),
            "target": artifact.get("target", {}),
            "backend": generation.get("backend"),
            "status": artifact.get("status"),
            "raw_output": generation.get("raw_output_path"),
            "prompt": prompt.get("path"),
            "artifact": str(artifact_path),
            "written_files": artifact.get("persistence", {}),
            "validation": validation.get("report"),
            "structured_output": {
                "files": generation.get("files", []),
                "classes": generation.get("classes", []),
                "methods": generation.get("methods", []),
                "notes": generation.get("notes", []),
                "unresolved_items": generation.get("unresolved_items", [])
            }
        }

    def _can_resume_job(self, job):
        if job.get("status") != "completed":
            return False

        for key in ["raw_output", "prompt", "artifact"]:
            path = job.get(key)

            if not path or not Path(path).exists():
                return False

        written = job.get("written_files", {}).get("summary", {})
        return written.get("written", 0) > 0

    def _artifact_summaries(self, jobs):
        summaries = []

        for job in jobs:
            artifact_path = job.get("artifact")

            if artifact_path and Path(artifact_path).exists():
                try:
                    artifact = json.loads(
                        Path(artifact_path).read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    artifact = None

                if artifact:
                    summaries.append(
                        FileMigrationArtifactWriter.summary_for_artifact(
                            artifact,
                            artifact_path
                        )
                    )
                    continue

            summaries.append({
                "job_id": job.get("job_id"),
                "status": job.get("status"),
                "path": artifact_path,
                "source_file": job.get("source", {}).get("file"),
                "target_file_hint": job.get("target", {}).get("file_hint"),
                "generated_files": len(
                    job.get("structured_output", {}).get("files", [])
                ),
                "written_files": (
                    job.get("written_files", {})
                    .get("summary", {})
                    .get("written", 0)
                ),
                "skipped_files": (
                    job.get("written_files", {})
                    .get("summary", {})
                    .get("skipped", 0)
                ),
                "validation_status": (
                    job.get("validation", {}) or {}
                ).get("status")
            })

        return summaries

    def _run_root(self, run_directory):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        root = Path(run_directory) / timestamp
        suffix = 1

        while root.exists():
            root = Path(run_directory) / f"{timestamp}-{suffix}"
            suffix += 1

        root.mkdir(parents=True, exist_ok=True)
        return root

    def _status(self, generation):
        validation = generation.get("validation")

        if validation and not validation.get("passed"):
            return "validation_failed"

        written = generation.get("written_files", {}).get("summary", {})
        skipped = generation.get("written_files", {}).get("skipped", [])

        if any(
            file_record.get("code") in {
                "batch_output_collision",
                "shared_support_type"
            }
            for file_record in skipped
        ):
            return "write_conflict"

        if written.get("written", 0) == 0:
            return "not_written"

        return "completed"

    def _statistics(self, jobs):
        return {
            "job_count": len(jobs),
            "completed": sum(1 for job in jobs if job["status"] == "completed"),
            "validation_failed": sum(
                1
                for job in jobs
                if job["status"] == "validation_failed"
            ),
            "write_conflict": sum(
                1
                for job in jobs
                if job["status"] == "write_conflict"
            ),
            "not_written": sum(1 for job in jobs if job["status"] == "not_written"),
            "written_files": sum(
                job.get("written_files", {})
                .get("summary", {})
                .get("written", 0)
                for job in jobs
            ),
            "skipped_files": sum(
                job.get("written_files", {})
                .get("summary", {})
                .get("skipped", 0)
                for job in jobs
            )
        }

    def _safe_name(self, value):
        return "".join(
            character if character.isalnum() or character in "-_." else "_"
            for character in str(value)
        )

    def _write_json(self, path, payload):
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8"
        )

    def _write_jsonl(self, path, rows):
        path.write_text(
            "".join(
                json.dumps(row, sort_keys=True) + "\n"
                for row in rows
            ),
            encoding="utf-8"
        )


class FileMigrationArtifactWriter:
    """
    Writes one durable review artifact per source file migration job.

    Batch runs already keep raw outputs and prompts in separate folders. The
    per-file artifact ties those files together with the planned source unit,
    generated Java file records, validation result, and write status so an
    external tool or developer can inspect one migration without reconstructing
    the whole batch manifest.
    """

    schema_version = 1

    def __init__(self, run_root, artifact_dir):
        self.run_root = Path(run_root)
        self.artifact_dir = Path(artifact_dir)
        self.artifact_summaries = []

    def write(
        self,
        prompt,
        planned_job,
        generation,
        raw_output_path,
        prompt_path,
        validation_path=None,
        status="completed"
    ):
        job_id = prompt.get("job_id")
        artifact_path = self.artifact_dir / f"{self._safe_name(job_id)}.json"
        structured_output = generation.get("structured_output", {})
        written_files = generation.get("written_files", {})
        validation = generation.get("validation")

        artifact = {
            "schema_version": self.schema_version,
            "artifact_type": "file_migration",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "status": status,
            "source": prompt.get("source", {}),
            "target": prompt.get("target", {}),
            "planning": {
                "sequence": planned_job.get("sequence"),
                "ordering": planned_job.get("ordering", {}),
                "symbols": planned_job.get("symbols", {}),
                "planning_notes": planned_job.get("planning_notes", []),
                "source_extraction": self._source_extraction_summary(
                    planned_job.get("source_extraction", {})
                )
            },
            "prompt": {
                "path": str(prompt_path),
                "statistics": prompt.get("statistics", {}),
                "plan_statistics": prompt.get("plan_statistics", {})
            },
            "generation": {
                "backend": generation.get("backend"),
                "raw_output_path": str(raw_output_path),
                "files": structured_output.get("files", []),
                "classes": structured_output.get("classes", []),
                "methods": structured_output.get("methods", []),
                "notes": structured_output.get("notes", []),
                "unresolved_items": structured_output.get(
                    "unresolved_items",
                    []
                )
            },
            "persistence": written_files,
            "validation": {
                "path": str(validation_path) if validation_path else None,
                "report": validation
            }
        }

        artifact_path.write_text(
            json.dumps(artifact, indent=2, sort_keys=True),
            encoding="utf-8"
        )
        summary = self._summary(artifact, artifact_path)
        self.artifact_summaries.append(summary)
        return summary

    def _source_extraction_summary(self, extraction):
        if not extraction:
            return {}

        # The full Pascal source can be large and already exists in the prompt
        # package. Store metadata here so artifact indexes stay reviewable.
        return {
            key: value
            for key, value in extraction.items()
            if key != "source"
        }

    def _summary(self, artifact, artifact_path):
        return self.summary_for_artifact(artifact, artifact_path)

    @staticmethod
    def summary_for_artifact(artifact, artifact_path):
        persistence = artifact.get("persistence", {})
        validation = artifact.get("validation", {}).get("report") or {}

        return {
            "job_id": artifact.get("job_id"),
            "status": artifact.get("status"),
            "path": str(artifact_path),
            "source_file": artifact.get("source", {}).get("file"),
            "target_file_hint": artifact.get("target", {}).get("file_hint"),
            "generated_files": len(
                artifact.get("generation", {}).get("files", [])
            ),
            "written_files": persistence.get("summary", {}).get("written", 0),
            "skipped_files": persistence.get("summary", {}).get("skipped", 0),
            "validation_status": validation.get("status")
        }

    def _safe_name(self, value):
        return "".join(
            character if character.isalnum() or character in "-_." else "_"
            for character in str(value)
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run batch file-by-file Delphi to Java generation."
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
        help="Maximum number of files to generate."
    )
    parser.add_argument(
        "--order",
        choices=["dependency", "source"],
        default="dependency",
        help="Migration job ordering."
    )
    parser.add_argument(
        "--backend",
        choices=["dry-run", "langchain"],
        default="dry-run",
        help="Generation backend."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_LANGCHAIN_GENERATION_MODEL,
        help=f"LangChain model string. Default: {DEFAULT_LANGCHAIN_GENERATION_MODEL}"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional .env file to load before initializing the model."
    )
    parser.add_argument(
        "--max-source-chars",
        type=int,
        default=60000,
        help="Maximum Pascal source characters included per file prompt."
    )
    parser.add_argument(
        "--output-directory",
        default="output/generated_java",
        help="Directory where generated Java files are persisted."
    )
    parser.add_argument(
        "--run-directory",
        default="output/migration_runs",
        help="Directory where batch run manifests and raw outputs are stored."
    )
    parser.add_argument(
        "--resume-run",
        default=None,
        help=(
            "Existing migration run directory to resume. Completed jobs are "
            "reused unless --force-rerun is set."
        )
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Regenerate jobs even when --resume-run contains completed jobs."
    )
    parser.add_argument(
        "--no-shared-support",
        action="store_true",
        help="Do not write or protect canonical shared Java support files."
    )
    parser.add_argument(
        "--overwrite-shared-support",
        action="store_true",
        help="Overwrite canonical shared Java support files if they already exist."
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Do not overwrite existing generated Java files."
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate each generated Java result."
    )
    parser.add_argument(
        "--compile-validation",
        action="store_true",
        help="Also compile generated Java with javac during validation."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full batch result as JSON."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    load_env_file(args.env_file)
    repository = Repository(load_repository(args.input))
    backend = (
        LangChainCodeGenerationBackend(args.model)
        if args.backend == "langchain"
        else DryRunFileGenerationBackend()
    )
    generator = FileMigrationBatchGenerator(
        repository,
        backend=backend,
        source_root=args.source_root,
        target_base_package=args.target_base_package,
        prompt_builder=FileMigrationPromptBuilder(
            max_source_chars=args.max_source_chars
        )
    )
    result = generator.generate(
        include=args.include,
        exclude=args.exclude,
        units=args.units,
        limit=args.limit,
        order=args.order,
        output_directory=args.output_directory,
        run_directory=args.run_directory,
        overwrite=not args.no_overwrite,
        validate=args.validate or args.compile_validation,
        compile_validation=args.compile_validation,
        resume_run=args.resume_run,
        force_rerun=args.force_rerun,
        include_shared_support=not args.no_shared_support,
        overwrite_shared_support=args.overwrite_shared_support
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print("File Migration Batch Generation")
    print(f"Run directory: {result['run_directory']}")
    print(f"Output directory: {result['output_directory']}")
    print(f"Artifact directory: {result['artifact_directory']}")
    print(f"Shared support: {result['shared_support']['enabled']}")
    print(
        "Shared support written: "
        f"{result['shared_support']['persistence']['summary']['written']}"
    )
    print(f"Jobs: {result['statistics']['job_count']}")
    print(f"Completed: {result['statistics']['completed']}")
    print(f"Validation failed: {result['statistics']['validation_failed']}")
    print(f"Write conflicts: {result['statistics']['write_conflict']}")
    print(f"Files written: {result['statistics']['written_files']}")
    print(f"Batch validation: {result['batch_validation']['status']}")
    if result.get("resume", {}).get("enabled"):
        print(f"Reused jobs: {result['resume']['reused_jobs']}")
        print(f"Generated jobs: {result['resume']['generated_jobs']}")
        print(f"Rerun jobs: {result['resume']['rerun_jobs']}")

    for job in result["jobs"]:
        print(
            f"- {job['job_id']} status={job['status']} "
            f"resume={job.get('resume_status', 'n/a')} "
            f"written={job['written_files'].get('summary', {}).get('written', 0)} "
            f"artifact={job['artifact']}"
        )


if __name__ == "__main__":
    main()
