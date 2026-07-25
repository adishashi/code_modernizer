"""
Tests for batch file-by-file Java generation.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    DryRunFileGenerationBackend,
    FileMigrationArtifactWriter,
    FileMigrationBatchGenerator,
    Repository,
    load_repository
)


class CountingDryRunFileGenerationBackend(DryRunFileGenerationBackend):

    def __init__(self):
        self.calls = 0

    def generate(self, prompt_package):
        self.calls += 1
        return super().generate(prompt_package)


class DuplicatePathFileGenerationBackend:

    backend_name = "duplicate_path"

    def generate(self, prompt_package):
        content = "\n".join([
            "package org.doublecmd.shared;",
            "",
            "public class SharedSupport {",
            "}"
        ])

        return {
            "backend": self.backend_name,
            "raw_output": content,
            "structured_output": {
                "files": [
                    {
                        "path": "org/doublecmd/shared/SharedSupport.java",
                        "language": "java",
                        "content": content
                    }
                ],
                "classes": [
                    {
                        "name": "SharedSupport",
                        "source_symbol": (
                            prompt_package
                            .get("prompt", {})
                            .get("source", {})
                            .get("unit")
                        ),
                        "responsibility": "Intentional collision test output."
                    }
                ],
                "methods": [],
                "notes": [],
                "unresolved_items": []
            }
        }


class SharedSupportCollisionBackend:

    backend_name = "shared_support_collision"

    def generate(self, prompt_package):
        content = "\n".join([
            "package org.doublecmd.plugins.wcx.zip.src.fparchive;",
            "",
            "public class TStream {",
            "}"
        ])

        return {
            "backend": self.backend_name,
            "raw_output": content,
            "structured_output": {
                "files": [
                    {
                        "path": (
                            "org/doublecmd/plugins/wcx/zip/src/fparchive/"
                            "TStream.java"
                        ),
                        "language": "java",
                        "content": content
                    }
                ],
                "classes": [
                    {
                        "name": "TStream",
                        "source_symbol": "TStream",
                        "responsibility": "Intentional shared support collision."
                    }
                ],
                "methods": [],
                "notes": [],
                "unresolved_items": []
            }
        }


class FileMigrationBatchGenerationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(load_repository(ROOT / "output"))

    def test_dry_run_batch_generates_writes_and_records_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=DryRunFileGenerationBackend(),
                source_root=ROOT / "doublecmd"
            )
            result = generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                validate=True
            )

            self.assertEqual(1, result["statistics"]["job_count"])
            self.assertEqual(1, result["statistics"]["completed"])
            self.assertEqual(1, result["statistics"]["written_files"])
            self.assertEqual("completed", result["jobs"][0]["status"])
            self.assertTrue(result["shared_support"]["enabled"])
            self.assertEqual(
                3,
                result["shared_support"]["persistence"]["summary"]["written"]
            )
            self.assertTrue(Path(result["run_directory"], "manifest.json").exists())
            self.assertTrue(Path(result["run_directory"], "jobs.jsonl").exists())
            self.assertTrue(Path(result["run_directory"], "artifacts.jsonl").exists())
            self.assertTrue(Path(result["jobs"][0]["raw_output"]).exists())
            self.assertTrue(Path(result["jobs"][0]["prompt"]).exists())
            self.assertTrue(Path(result["jobs"][0]["artifact"]).exists())
            self.assertTrue(
                (
                    root
                    / "generated"
                    / "org"
                    / "doublecmd"
                    / "filesources"
                    / "FileSource.java"
                ).exists()
            )
            self.assertEqual(
                "passed",
                result["jobs"][0]["validation"]["status"]
            )
            artifact = json.loads(Path(result["jobs"][0]["artifact"]).read_text())
            self.assertEqual("file_migration", artifact["artifact_type"])
            self.assertEqual("file:uFileSource", artifact["job_id"])
            self.assertEqual("completed", artifact["status"])
            self.assertEqual(
                "src/filesources/ufilesource.pas",
                artifact["source"]["file"].replace("\\", "/").lower()
            )
            self.assertNotIn(
                "source",
                artifact["planning"]["source_extraction"]
            )
            self.assertEqual(
                1,
                artifact["persistence"]["summary"]["written"]
            )
            self.assertEqual(
                "passed",
                artifact["validation"]["report"]["status"]
            )
            self.assertTrue(
                (
                    root
                    / "generated"
                    / "org"
                    / "doublecmd"
                    / "runtime"
                    / "io"
                    / "TStream.java"
                ).exists()
            )

            artifact_index = Path(
                result["run_directory"],
                "artifacts.jsonl"
            ).read_text().splitlines()
            self.assertEqual(1, len(artifact_index))
            self.assertEqual(
                result["jobs"][0]["artifact"],
                json.loads(artifact_index[0])["path"]
            )

    def test_batch_respects_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=DryRunFileGenerationBackend(),
                source_root=ROOT / "doublecmd"
            )
            first = generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs"
            )
            second = generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                overwrite=False
            )

            self.assertEqual(1, first["statistics"]["written_files"])
            self.assertEqual(0, second["statistics"]["written_files"])
            self.assertEqual(1, second["statistics"]["skipped_files"])
            self.assertEqual("not_written", second["jobs"][0]["status"])

    def test_resume_reuses_completed_jobs_without_backend_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_backend = CountingDryRunFileGenerationBackend()
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=first_backend,
                source_root=ROOT / "doublecmd"
            )
            first = generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                validate=True
            )
            resume_backend = CountingDryRunFileGenerationBackend()
            resume_generator = FileMigrationBatchGenerator(
                self.repository,
                backend=resume_backend,
                source_root=ROOT / "doublecmd"
            )
            resumed = resume_generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                validate=True,
                resume_run=first["run_directory"]
            )

            self.assertEqual(1, first_backend.calls)
            self.assertEqual(0, resume_backend.calls)
            self.assertEqual(1, resumed["resume"]["reused_jobs"])
            self.assertEqual(0, resumed["resume"]["generated_jobs"])
            self.assertEqual("reused", resumed["jobs"][0]["resume_status"])
            self.assertEqual("completed", resumed["jobs"][0]["status"])
            self.assertEqual(
                first["jobs"][0]["artifact"],
                resumed["jobs"][0]["artifact"]
            )

    def test_resume_recovers_completed_jobs_from_artifacts_without_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_backend = CountingDryRunFileGenerationBackend()
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=first_backend,
                source_root=ROOT / "doublecmd"
            )
            first = generator.generate(
                units=["AbResString"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                validate=True
            )
            run_root = Path(first["run_directory"])

            for index_path in [
                run_root / "manifest.json",
                run_root / "jobs.jsonl",
                run_root / "artifacts.jsonl"
            ]:
                index_path.unlink()

            resume_backend = CountingDryRunFileGenerationBackend()
            resume_generator = FileMigrationBatchGenerator(
                self.repository,
                backend=resume_backend,
                source_root=ROOT / "doublecmd"
            )
            resumed = resume_generator.generate(
                units=["AbResString", "AbSWStm"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                validate=True,
                resume_run=run_root
            )
            statuses = {
                job["job_id"]: job["resume_status"]
                for job in resumed["jobs"]
            }

            self.assertEqual(1, first_backend.calls)
            self.assertEqual(1, resume_backend.calls)
            self.assertEqual(1, resumed["resume"]["reused_jobs"])
            self.assertEqual(1, resumed["resume"]["generated_jobs"])
            self.assertEqual("reused", statuses["file:AbResString"])
            self.assertEqual("generated", statuses["file:AbSWStm"])
            self.assertTrue((run_root / "manifest.json").exists())
            self.assertTrue((run_root / "jobs.jsonl").exists())
            self.assertTrue((run_root / "artifacts.jsonl").exists())

    def test_force_rerun_ignores_resume_completed_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=DryRunFileGenerationBackend(),
                source_root=ROOT / "doublecmd"
            )
            first = generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs"
            )
            rerun_backend = CountingDryRunFileGenerationBackend()
            rerun_generator = FileMigrationBatchGenerator(
                self.repository,
                backend=rerun_backend,
                source_root=ROOT / "doublecmd"
            )
            rerun = rerun_generator.generate(
                units=["uFileSource"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                resume_run=first["run_directory"],
                force_rerun=True
            )

            self.assertEqual(1, rerun_backend.calls)
            self.assertEqual(0, rerun["resume"]["reused_jobs"])
            self.assertEqual(1, rerun["resume"]["rerun_jobs"])
            self.assertEqual("rerun", rerun["jobs"][0]["resume_status"])

    def test_batch_detects_and_protects_cross_job_output_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=DuplicatePathFileGenerationBackend(),
                source_root=ROOT / "doublecmd"
            )
            result = generator.generate(
                units=["AbResString", "AbSWStm"],
                output_directory=root / "generated",
                run_directory=root / "runs"
            )
            statuses = {
                job["status"]
                for job in result["jobs"]
            }
            batch_codes = {
                finding["code"]
                for finding in result["batch_validation"]["findings"]
            }

            self.assertEqual(2, result["statistics"]["job_count"])
            self.assertEqual(1, result["statistics"]["written_files"])
            self.assertEqual(1, result["statistics"]["skipped_files"])
            self.assertEqual(1, result["statistics"]["write_conflict"])
            self.assertIn("write_conflict", statuses)
            self.assertFalse(result["batch_validation"]["passed"])
            self.assertIn("batch_duplicate_file_path", batch_codes)
            self.assertIn("batch_duplicate_type_declaration", batch_codes)

            skipped = [
                skipped_file
                for job in result["jobs"]
                for skipped_file in job["written_files"]["skipped"]
            ]
            self.assertEqual("batch_output_collision", skipped[0]["code"])

    def test_batch_skips_generated_shared_support_types(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = FileMigrationBatchGenerator(
                self.repository,
                backend=SharedSupportCollisionBackend(),
                source_root=ROOT / "doublecmd"
            )
            result = generator.generate(
                units=["AbSWStm"],
                output_directory=root / "generated",
                run_directory=root / "runs",
                validate=True
            )

            self.assertEqual("write_conflict", result["jobs"][0]["status"])
            self.assertEqual(0, result["statistics"]["written_files"])
            self.assertEqual(1, result["statistics"]["write_conflict"])
            skipped = result["jobs"][0]["written_files"]["skipped"][0]
            self.assertEqual("shared_support_type", skipped["code"])
            self.assertTrue(
                (
                    root
                    / "generated"
                    / "org"
                    / "doublecmd"
                    / "runtime"
                    / "io"
                    / "TStream.java"
                ).exists()
            )

    def test_file_generation_cli_outputs_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "repository_intelligence.modernization.file_generation",
                    "--input",
                    str(ROOT / "output"),
                    "--source-root",
                    str(ROOT / "doublecmd"),
                    "--units",
                    "uFileSource",
                    "--output-directory",
                    str(root / "generated"),
                    "--run-directory",
                    str(root / "runs"),
                    "--validate",
                    "--json"
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=ROOT
            )
            result = json.loads(completed.stdout)

            self.assertEqual(1, result["statistics"]["job_count"])
            self.assertEqual(1, result["statistics"]["written_files"])
            self.assertTrue(Path(result["run_directory"], "manifest.json").exists())
            self.assertTrue(Path(result["jobs"][0]["artifact"]).exists())

    def test_file_migration_artifact_writer_is_exported(self):
        self.assertTrue(FileMigrationArtifactWriter)


if __name__ == "__main__":
    unittest.main()
