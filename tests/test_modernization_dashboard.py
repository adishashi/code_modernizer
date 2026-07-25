"""
Tests for migration run dashboard reporting.
"""

import json
import tempfile
import unittest
from pathlib import Path

from repository_intelligence.modernization.dashboard import (
    MigrationDashboardBuilder,
    render_dashboard_html
)


class MigrationDashboardTests(unittest.TestCase):

    def test_dashboard_summarizes_artifacts_and_validation_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir)
            artifact_dir = run / "artifacts"
            prompt_dir = run / "prompts"
            raw_dir = run / "raw_outputs"
            validation_dir = run / "validation_reports"

            for directory in [
                artifact_dir,
                prompt_dir,
                raw_dir,
                validation_dir
            ]:
                directory.mkdir()

            self._write_artifact(
                artifact_dir / "file_Good.json",
                job_id="file:Good",
                unit="Good",
                status="completed",
                sequence=1,
                files=["org/example/Good.java"],
                written=1,
                unresolved=[]
            )
            self._write_report(
                validation_dir / "file_Good.json",
                status="passed",
                findings=[]
            )
            (prompt_dir / "file_Good.json").write_text("prompt", encoding="utf-8")
            (raw_dir / "file_Good.txt").write_text("raw", encoding="utf-8")

            self._write_artifact(
                artifact_dir / "file_Bad.json",
                job_id="file:Bad",
                unit="Bad",
                status="not_written",
                sequence=2,
                files=[],
                written=0,
                unresolved=["No output."]
            )
            self._write_report(
                validation_dir / "file_Bad.json",
                status="failed",
                findings=[
                    {
                        "severity": "error",
                        "code": "missing_files",
                        "message": "No files."
                    }
                ]
            )

            report = MigrationDashboardBuilder(run).build()

            self.assertEqual(2, report["summary"]["job_count"])
            self.assertEqual(1, report["summary"]["completed_jobs"])
            self.assertEqual(1, report["summary"]["failed_or_incomplete_jobs"])
            self.assertEqual(2, report["summary"]["validation_reports"])
            self.assertEqual(1, report["summary"]["generated_java_files"])
            self.assertEqual(1, report["summary"]["unresolved_items"])
            self.assertGreater(report["summary"]["estimated_total_tokens"], 0)
            self.assertGreater(report["jobs"][0]["estimated_total_tokens"], 0)
            self.assertEqual(["file:Bad"], [
                job["job_id"]
                for job in report["sections"]["failed_jobs"]
            ])
            recommendation_titles = {
                recommendation["title"]
                for recommendation in report["recommendations"]
            }
            self.assertIn("Skip or isolate not-written jobs", recommendation_titles)

    def test_dashboard_html_contains_summary_and_actions(self):
        report = {
            "generated_at": "2026-07-21T00:00:00+00:00",
            "run_directory": "output/migration_runs/example",
            "summary": {
                "job_count": 1,
                "status_counts": {
                    "completed": 1
                },
                "validation_status_counts": {
                    "passed": 1
                },
                "completed_jobs": 1,
                "failed_or_incomplete_jobs": 0,
                "validation_reports": 1,
                "generated_java_files": 1,
                "unresolved_items": 0,
                "validation_warnings": 0,
                "prompt_bytes": 100,
                "estimated_prompt_tokens": 25,
                "estimated_output_tokens": 10,
                "estimated_total_tokens": 35,
                "source_chars": 20,
                "largest_prompt_bytes": 100,
                "largest_source_chars": 20,
                "estimated_prompt_tokens": 25,
                "estimated_output_tokens": 10,
                "estimated_total_tokens": 35
            },
            "recommendations": [
                {
                    "priority": "low",
                    "title": "Proceed",
                    "detail": "Next step."
                }
            ],
            "sections": {
                "failed_jobs": [],
                "high_unresolved_jobs": [],
                "largest_prompts": [],
                "largest_estimated_token_jobs": [],
                "jobs_with_warnings": []
            },
            "jobs": [
                {
                    "sequence": 1,
                    "unit": "Good",
                    "status": "completed",
                    "validation_status": "passed",
                    "validation_errors": 0,
                    "validation_warnings": 0,
                    "generated_files": 1,
                    "written_files": 1,
                    "unresolved_count": 0,
                    "prompt_bytes": 100,
                    "estimated_total_tokens": 35,
                    "source_chars": 20,
                    "finding_codes": []
                }
            ]
        }

        html = render_dashboard_html(report)

        self.assertIn("Modernization Dashboard", html)
        self.assertIn("Recommended Next Actions", html)
        self.assertIn("job-search", html)
        self.assertIn("risk-filter", html)
        self.assertIn("Estimated API Token Usage", html)
        self.assertIn("token-largest", html)
        self.assertIn("job-detail", html)
        self.assertIn("Good", html)

    def _write_artifact(
        self,
        path,
        job_id,
        unit,
        status,
        sequence,
        files,
        written,
        unresolved
    ):
        file_records = [
            {
                "path": file_path,
                "language": "java",
                "content": (
                    "package org.example;\n\n"
                    f"public class {Path(file_path).stem} {{}}\n"
                )
            }
            for file_path in files
        ]
        artifact = {
            "artifact_type": "file_migration",
            "job_id": job_id,
            "status": status,
            "source": {
                "unit": unit,
                "file": f"{unit}.pas"
            },
            "target": {
                "file_hint": f"org/example/{unit}.java"
            },
            "planning": {
                "sequence": sequence,
                "source_extraction": {
                    "character_count": 20,
                    "line_count": 2,
                    "truncated": False
                }
            },
            "generation": {
                "backend": "test",
                "files": file_records,
                "classes": [],
                "methods": [],
                "notes": [],
                "unresolved_items": unresolved
            },
            "persistence": {
                "summary": {
                    "written": written,
                    "skipped": 0
                }
            },
            "validation": {
                "report": None
            }
        }
        path.write_text(json.dumps(artifact), encoding="utf-8")

    def _write_report(self, path, status, findings):
        report = {
            "status": status,
            "passed": status == "passed",
            "findings": findings,
            "summary": {
                "errors": sum(
                    1 for finding in findings
                    if finding.get("severity") == "error"
                ),
                "warnings": sum(
                    1 for finding in findings
                    if finding.get("severity") == "warning"
                ),
                "files": 1
            }
        }
        path.write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
