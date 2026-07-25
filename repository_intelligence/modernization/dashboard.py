"""
Migration run dashboard generation.

The dashboard is deliberately read-only: it inspects durable migration run
artifacts, validation reports, prompts, and raw model outputs that already
exist on disk. This makes it safe to run while API token usage is constrained.
"""

import argparse
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


class MigrationDashboardBuilder:
    """
    Builds a compact status report for one file-by-file migration run.

    The run directory can be incomplete. Older or interrupted runs may be
    missing manifest files, embedded validation reports, or report backfills.
    The builder therefore treats per-file artifacts as the source of truth and
    supplements them with sibling validation report files when present.
    """

    def __init__(self, run_directory):
        self.run_directory = Path(run_directory)
        self.artifact_directory = self.run_directory / "artifacts"
        self.validation_directory = self.run_directory / "validation_reports"
        self.prompt_directory = self.run_directory / "prompts"
        self.raw_output_directory = self.run_directory / "raw_outputs"

    def build(self):
        artifacts = self._load_artifacts()
        jobs = [self._job_summary(artifact_path, artifact) for artifact_path, artifact in artifacts]
        jobs.sort(key=self._job_sort_key)

        summary = self._summary(jobs)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_directory": str(self.run_directory),
            "artifact_directory": str(self.artifact_directory),
            "validation_directory": str(self.validation_directory),
            "summary": summary,
            "sections": {
                "failed_jobs": self._failed_jobs(jobs),
                "jobs_with_warnings": self._jobs_with_warnings(jobs),
                "high_unresolved_jobs": self._top(
                    jobs,
                    "unresolved_count",
                    minimum=1
                ),
                "largest_prompts": self._top(jobs, "prompt_bytes"),
                "largest_sources": self._top(jobs, "source_chars"),
                "largest_estimated_token_jobs": self._top(
                    jobs,
                    "estimated_total_tokens"
                ),
                "not_written_jobs": [
                    job for job in jobs if job["status"] == "not_written"
                ],
                "missing_validation_reports": [
                    job for job in jobs if not job["validation_report_exists"]
                ]
            },
            "recommendations": self._recommendations(jobs, summary),
            "jobs": jobs
        }
        return report

    def write_json(self, output_path):
        report = self.build()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8"
        )
        return report

    def write_html(self, output_path):
        report = self.build()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_dashboard_html(report), encoding="utf-8")
        return report

    def _load_artifacts(self):
        if not self.artifact_directory.exists():
            return []

        artifacts = []
        for artifact_path in sorted(self.artifact_directory.glob("*.json")):
            try:
                artifact = json.loads(
                    artifact_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                artifact = {
                    "job_id": artifact_path.stem,
                    "status": "artifact_parse_failed",
                    "generation": {
                        "files": [],
                        "classes": [],
                        "methods": [],
                        "notes": [],
                        "unresolved_items": [
                            "Artifact JSON could not be parsed."
                        ]
                    }
                }

            artifacts.append((artifact_path, artifact))

        return artifacts

    def _job_summary(self, artifact_path, artifact):
        generation = artifact.get("generation", {}) or {}
        planning = artifact.get("planning", {}) or {}
        extraction = planning.get("source_extraction", {}) or {}
        persistence = artifact.get("persistence", {}) or {}
        persistence_summary = persistence.get("summary", {}) or {}
        validation_report = self._validation_report(artifact_path, artifact)
        prompt_path = self._artifact_prompt_path(artifact_path, artifact)
        raw_output_path = self._artifact_raw_output_path(artifact_path, artifact)
        validation_report_path = self.validation_directory / artifact_path.name
        findings = validation_report.get("findings", []) if validation_report else []
        error_count = sum(1 for finding in findings if finding.get("severity") == "error")
        warning_count = sum(1 for finding in findings if finding.get("severity") == "warning")

        return {
            "sequence": planning.get("sequence"),
            "job_id": artifact.get("job_id"),
            "unit": (artifact.get("source", {}) or {}).get("unit"),
            "source_file": (artifact.get("source", {}) or {}).get("file"),
            "target_file_hint": (artifact.get("target", {}) or {}).get("file_hint"),
            "status": artifact.get("status"),
            "backend": generation.get("backend"),
            "artifact_path": str(artifact_path),
            "prompt_path": str(prompt_path) if prompt_path else None,
            "raw_output_path": str(raw_output_path) if raw_output_path else None,
            "validation_report_path": str(validation_report_path),
            "validation_report_exists": validation_report_path.exists(),
            "validation_status": validation_report.get("status") if validation_report else None,
            "validation_errors": error_count,
            "validation_warnings": warning_count,
            "finding_codes": sorted({
                finding.get("code")
                for finding in findings
                if finding.get("code")
            }),
            "generated_files": len(generation.get("files", []) or []),
            "generated_classes": len(generation.get("classes", []) or []),
            "generated_methods": len(generation.get("methods", []) or []),
            "written_files": persistence_summary.get("written", 0),
            "skipped_files": persistence_summary.get("skipped", 0),
            "unresolved_count": len(generation.get("unresolved_items", []) or []),
            "source_chars": extraction.get("character_count", 0) or 0,
            "source_lines": extraction.get("line_count", 0) or 0,
            "source_truncated": bool(extraction.get("truncated")),
            "prompt_bytes": self._file_size(prompt_path),
            "raw_output_bytes": self._file_size(raw_output_path),
            "estimated_prompt_tokens": self._estimated_tokens(
                self._file_size(prompt_path)
            ),
            "estimated_output_tokens": self._estimated_tokens(
                self._file_size(raw_output_path)
            ),
            "estimated_total_tokens": (
                self._estimated_tokens(self._file_size(prompt_path))
                + self._estimated_tokens(self._file_size(raw_output_path))
            )
        }

    def _validation_report(self, artifact_path, artifact):
        embedded = (artifact.get("validation", {}) or {}).get("report")
        if embedded:
            return embedded

        report_path = self.validation_directory / artifact_path.name
        if not report_path.exists():
            return {}

        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "status": "report_parse_failed",
                "findings": [
                    {
                        "severity": "error",
                        "code": "validation_report_parse_failed",
                        "message": "Validation report JSON could not be parsed."
                    }
                ]
            }

    def _artifact_prompt_path(self, artifact_path, artifact):
        prompt_path = (artifact.get("prompt", {}) or {}).get("path")
        if prompt_path:
            return Path(prompt_path)

        candidate = self.prompt_directory / artifact_path.name
        return candidate if candidate.exists() else None

    def _artifact_raw_output_path(self, artifact_path, artifact):
        raw_output_path = (artifact.get("generation", {}) or {}).get(
            "raw_output_path"
        )
        if raw_output_path:
            return Path(raw_output_path)

        candidate = self.raw_output_directory / f"{artifact_path.stem}.txt"
        return candidate if candidate.exists() else None

    def _file_size(self, path):
        if not path:
            return 0

        path = Path(path)
        return path.stat().st_size if path.exists() else 0

    def _estimated_tokens(self, byte_count):
        # Local runs do not currently persist provider token metadata. The
        # dashboard uses a conservative byte-based estimate so token pressure
        # can still be tracked without calling the API.
        return int((byte_count + 3) // 4)

    def _summary(self, jobs):
        status_counts = Counter(job["status"] for job in jobs)
        validation_counts = Counter(
            job["validation_status"] or "missing"
            for job in jobs
        )

        return {
            "job_count": len(jobs),
            "status_counts": dict(sorted(status_counts.items())),
            "validation_status_counts": dict(sorted(validation_counts.items())),
            "completed_jobs": status_counts.get("completed", 0),
            "failed_or_incomplete_jobs": sum(
                1
                for job in jobs
                if job["status"] != "completed"
                or job["validation_status"] == "failed"
            ),
            "validation_reports": sum(
                1 for job in jobs if job["validation_report_exists"]
            ),
            "missing_validation_reports": sum(
                1 for job in jobs if not job["validation_report_exists"]
            ),
            "generated_java_files": sum(job["generated_files"] for job in jobs),
            "written_java_files": sum(job["written_files"] for job in jobs),
            "unresolved_items": sum(job["unresolved_count"] for job in jobs),
            "validation_errors": sum(job["validation_errors"] for job in jobs),
            "validation_warnings": sum(job["validation_warnings"] for job in jobs),
            "prompt_bytes": sum(job["prompt_bytes"] for job in jobs),
            "raw_output_bytes": sum(job["raw_output_bytes"] for job in jobs),
            "estimated_prompt_tokens": sum(
                job["estimated_prompt_tokens"] for job in jobs
            ),
            "estimated_output_tokens": sum(
                job["estimated_output_tokens"] for job in jobs
            ),
            "estimated_total_tokens": sum(
                job["estimated_total_tokens"] for job in jobs
            ),
            "source_chars": sum(job["source_chars"] for job in jobs),
            "largest_prompt_bytes": max(
                [job["prompt_bytes"] for job in jobs] or [0]
            ),
            "largest_source_chars": max(
                [job["source_chars"] for job in jobs] or [0]
            )
        }

    def _failed_jobs(self, jobs):
        return [
            job
            for job in jobs
            if job["status"] != "completed"
            or job["validation_status"] == "failed"
        ]

    def _jobs_with_warnings(self, jobs):
        return [
            job
            for job in jobs
            if job["validation_warnings"] > 0
        ][:25]

    def _top(self, jobs, key, minimum=0, limit=20):
        return [
            job
            for job in sorted(
                jobs,
                key=lambda item: item.get(key, 0),
                reverse=True
            )
            if job.get(key, 0) >= minimum
        ][:limit]

    def _recommendations(self, jobs, summary):
        recommendations = []

        if summary["missing_validation_reports"]:
            recommendations.append({
                "priority": "high",
                "title": "Backfill validation reports",
                "detail": (
                    f"{summary['missing_validation_reports']} artifacts do not "
                    "have validation report files. Generate these locally before "
                    "spending more API tokens."
                )
            })

        not_written = [
            job for job in jobs if job["status"] == "not_written"
        ]
        if not_written:
            units = ", ".join(job.get("unit") or job["job_id"] for job in not_written[:5])
            recommendations.append({
                "priority": "high",
                "title": "Skip or isolate not-written jobs",
                "detail": (
                    f"{len(not_written)} jobs produced no written Java files "
                    f"({units}). Exclude them during token-limited resumes or "
                    "retry them with smaller, specialized prompts."
                )
            })

        failed_validation = [
            job for job in jobs if job["validation_status"] == "failed"
        ]
        if failed_validation:
            recommendations.append({
                "priority": "high",
                "title": "Repair structurally failed generated files",
                "detail": (
                    f"{len(failed_validation)} jobs failed structural validation. "
                    "Prioritize local repairs for filename/package/declaration "
                    "issues before regenerating with the LLM."
                )
            })

        if any(
            "public_type_filename_mismatch" in job["finding_codes"]
            for job in jobs
        ):
            recommendations.append({
                "priority": "medium",
                "title": "Improve Java file naming",
                "detail": (
                    "At least one generated file declares a public type whose "
                    "name does not match the Java filename. Prefer public type "
                    "names over Pascal unit names when writing Java files."
                )
            })

        large_jobs = [
            job
            for job in jobs
            if job["prompt_bytes"] >= 100000
        ]
        if large_jobs:
            recommendations.append({
                "priority": "medium",
                "title": "Use token-aware batching",
                "detail": (
                    f"{len(large_jobs)} completed prompts were at least 100 KB. "
                    "Route constants, resource strings, and large lookup tables "
                    "through deterministic converters where possible."
                )
            })

        token_heavy_jobs = [
            job for job in jobs
            if job["estimated_total_tokens"] >= 50000
        ]
        if token_heavy_jobs:
            recommendations.append({
                "priority": "medium",
                "title": "Review estimated token-heavy jobs",
                "detail": (
                    f"{len(token_heavy_jobs)} jobs are estimated above 50k "
                    "prompt plus output tokens. These should be routed through "
                    "smaller prompts, deterministic converters, or manual review."
                )
            })

        if summary["unresolved_items"]:
            recommendations.append({
                "priority": "medium",
                "title": "Triage unresolved migration items",
                "detail": (
                    f"{summary['unresolved_items']} unresolved items were reported "
                    "across generated artifacts. Sort by subsystem and handle "
                    "shared runtime assumptions first."
                )
            })

        if not recommendations:
            recommendations.append({
                "priority": "low",
                "title": "Proceed to compile-level integration",
                "detail": (
                    "No structural blockers were detected in this run. The next "
                    "useful step is whole-project Java compilation."
                )
            })

        return recommendations

    def _job_sort_key(self, job):
        sequence = job.get("sequence")
        if sequence is None:
            sequence = 10**9
        return (sequence, job.get("job_id") or "")


def render_dashboard_html(report):
    summary = report["summary"]
    cards = [
        ("Jobs", summary["job_count"]),
        ("Completed", summary["completed_jobs"]),
        ("Failed/Incomplete", summary["failed_or_incomplete_jobs"]),
        ("Validation Reports", summary["validation_reports"]),
        ("Generated Java Files", summary["generated_java_files"]),
        ("Unresolved Items", summary["unresolved_items"]),
        ("Warnings", summary["validation_warnings"]),
        ("Prompt Bytes", summary["prompt_bytes"])
    ]
    data_json = json.dumps(report, sort_keys=True).replace("</", "<\\/")

    return "\n".join([
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Modernization Dashboard</title>",
        _style(),
        "</head>",
        "<body>",
        "<script id=\"dashboard-data\" type=\"application/json\">",
        data_json,
        "</script>",
        "<div class=\"app-shell\">",
        "<aside class=\"sidebar\">",
        "<div class=\"brand\">",
        "<div class=\"brand-mark\">M</div>",
        "<div>",
        "<h1>Modernization</h1>",
        "<p>Migration run dashboard</p>",
        "</div>",
        "</div>",
        "<nav class=\"nav\">",
        "<button class=\"nav-item active\" data-section=\"overview\">Overview</button>",
        "<button class=\"nav-item\" data-section=\"actions\">Actions</button>",
        "<button class=\"nav-item\" data-section=\"jobs\">Jobs</button>",
        "<button class=\"nav-item\" data-section=\"risk\">Risk</button>",
        "<button class=\"nav-item\" data-section=\"tokens\">Tokens</button>",
        "</nav>",
        "</aside>",
        "<main class=\"content\">",
        "<header class=\"topbar\">",
        "<div>",
        "<p class=\"eyebrow\">Current Run</p>",
        f"<h2>{escape(Path(report['run_directory']).name)}</h2>",
        f"<p class=\"path-line\">{escape(report['run_directory'])}</p>",
        "</div>",
        "<div class=\"generated-at\">",
        "<span>Generated</span>",
        f"<strong>{escape(report['generated_at'])}</strong>",
        "</div>",
        "</header>",
        "<section id=\"overview\" class=\"panel-section active\">",
        _cards(cards),
        _summary_panels(report),
        "</section>",
        "<section id=\"actions\" class=\"panel-section\">",
        _recommendations(report["recommendations"]),
        "</section>",
        "<section id=\"jobs\" class=\"panel-section\">",
        _job_controls(),
        _job_table_shell(),
        "</section>",
        "<section id=\"risk\" class=\"panel-section\">",
        _risk_shell(),
        "</section>",
        "<section id=\"tokens\" class=\"panel-section\">",
        _token_shell(report),
        "</section>",
        "</main>",
        "<aside id=\"job-detail\" class=\"detail-panel\" aria-hidden=\"true\">",
        "<button class=\"detail-close\" type=\"button\" aria-label=\"Close detail panel\">x</button>",
        "<div id=\"job-detail-content\"></div>",
        "</aside>",
        "</div>",
        _script(),
        "</body>",
        "</html>"
    ])


def _style():
    return """
<style>
:root {
  --bg: #eef3f8;
  --surface: #ffffff;
  --surface-2: #f7f9fc;
  --border: #d7dee8;
  --text: #17212f;
  --muted: #657282;
  --accent: #1f6feb;
  --danger: #c62828;
  --warn: #9a5b00;
  --ok: #1b7f3a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
}
button, input, select { font: inherit; }
.app-shell {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  min-height: 100vh;
}
.sidebar {
  background: #1f2937;
  color: #f8fafc;
  padding: 22px 18px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 28px;
}
.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: #dbeafe;
  color: #1e3a8a;
  font-weight: 700;
}
.brand h1 { margin: 0; font-size: 18px; }
.brand p { margin: 3px 0 0; color: #cbd5e1; font-size: 13px; }
.nav { display: grid; gap: 8px; }
.nav-item {
  border: 1px solid transparent;
  background: transparent;
  color: #dbe4ef;
  text-align: left;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
}
.nav-item:hover, .nav-item.active {
  background: #334155;
  border-color: #475569;
  color: #ffffff;
}
.content {
  padding: 24px;
  min-width: 0;
}
.topbar {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  margin-bottom: 18px;
}
.eyebrow {
  margin: 0 0 6px;
  text-transform: uppercase;
  font-size: 12px;
  color: var(--muted);
  font-weight: 700;
}
.topbar h2 {
  margin: 0;
  font-size: 28px;
}
.path-line {
  margin: 6px 0 0;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.generated-at {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  min-width: 260px;
}
.generated-at span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 4px;
}
.generated-at strong { overflow-wrap: anywhere; }
.panel-section { display: none; }
.panel-section.active { display: block; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}
.card .label {
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 700;
}
.card .value {
  font-size: 24px;
  margin-top: 7px;
  font-weight: 700;
}
.summary-grid, .risk-grid, .token-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.panel h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.meter {
  height: 12px;
  background: #e5eaf1;
  border-radius: 999px;
  overflow: hidden;
}
.meter-fill {
  height: 100%;
  background: var(--accent);
}
.stat-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.stat-list li { display: flex; justify-content: space-between; gap: 14px; }
.recommendations {
  display: grid;
  gap: 12px;
}
.recommendation {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  padding: 14px;
  border-radius: 8px;
}
.recommendation.high { border-left-color: var(--danger); }
.recommendation.medium { border-left-color: var(--warn); }
.recommendation strong { display: block; margin-bottom: 6px; }
.recommendation p { margin: 0; color: var(--muted); line-height: 1.45; }
.toolbar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(140px, 180px));
  gap: 10px;
  margin-bottom: 12px;
}
.toolbar input, .toolbar select {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  padding: 10px 11px;
  min-width: 0;
}
.table-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: auto;
  max-height: 620px;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1080px;
}
thead {
  position: sticky;
  top: 0;
  background: #edf2f7;
  z-index: 1;
}
th, td {
  border-bottom: 1px solid #e3e9f1;
  padding: 9px 10px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}
th {
  color: #536274;
  font-size: 12px;
  text-transform: uppercase;
  cursor: pointer;
  white-space: nowrap;
}
tbody tr { cursor: pointer; }
tbody tr:hover { background: #f7fafc; }
.pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  background: #e9eef5;
  color: #334155;
  white-space: nowrap;
}
.pill.passed, .pill.completed { background: #dcfce7; color: #166534; }
.pill.failed, .pill.not_written { background: #fee2e2; color: #991b1b; }
.pill.warning { background: #fef3c7; color: #92400e; }
.muted { color: var(--muted); }
.detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: min(520px, 100vw);
  height: 100vh;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -12px 0 30px rgba(15, 23, 42, .18);
  transform: translateX(100%);
  transition: transform .18s ease;
  padding: 22px;
  overflow: auto;
  z-index: 10;
}
.detail-panel.open { transform: translateX(0); }
.detail-close {
  float: right;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  cursor: pointer;
}
.detail-panel h3 { margin-top: 0; }
.detail-grid {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 8px 12px;
  margin-top: 14px;
}
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; overflow-wrap: anywhere; }
code { font-family: Consolas, monospace; font-size: 12px; }
@media (max-width: 900px) {
  .app-shell { grid-template-columns: 1fr; }
  .sidebar {
    position: static;
    height: auto;
  }
  .nav { grid-template-columns: repeat(5, 1fr); }
  .topbar { display: block; }
  .generated-at { margin-top: 12px; min-width: 0; }
  .toolbar { grid-template-columns: 1fr; }
}
</style>
"""


def _cards(cards):
    items = []
    for label, value in cards:
        items.append(
            "<div class=\"card\">"
            f"<div class=\"label\">{escape(label)}</div>"
            f"<div class=\"value\">{escape(str(value))}</div>"
            "</div>"
        )
    return "<section class=\"cards\">" + "\n".join(items) + "</section>"


def _recommendations(recommendations):
    items = []
    for recommendation in recommendations:
        priority = recommendation.get("priority", "low")
        items.append(
            f"<div class=\"recommendation {escape(priority)}\">"
            f"<strong>{escape(recommendation.get('title', ''))}</strong>"
            f"<p>{escape(recommendation.get('detail', ''))}</p>"
            "</div>"
        )
    return (
        "<h2>Recommended Next Actions</h2>"
        "<section class=\"recommendations\">"
        + "\n".join(items)
        + "</section>"
    )


def _summary_panels(report):
    summary = report["summary"]
    completed = summary["completed_jobs"]
    total = summary["job_count"] or 1
    completion_pct = round(completed * 100 / total, 1)
    validation_passed = summary["validation_status_counts"].get("passed", 0)
    validation_pct = round(validation_passed * 100 / total, 1)
    status_items = "".join(
        "<li>"
        f"<span>{escape(key)}</span>"
        f"<strong>{escape(value)}</strong>"
        "</li>"
        for key, value in summary["status_counts"].items()
    )
    validation_items = "".join(
        "<li>"
        f"<span>{escape(key)}</span>"
        f"<strong>{escape(value)}</strong>"
        "</li>"
        for key, value in summary["validation_status_counts"].items()
    )
    return "\n".join([
        "<div class=\"summary-grid\">",
        "<section class=\"panel\">",
        "<h3>Migration Completion</h3>",
        f"<div class=\"meter\"><div class=\"meter-fill\" style=\"width:{completion_pct}%\"></div></div>",
        f"<p>{completion_pct}% complete by job status.</p>",
        f"<ul class=\"stat-list\">{status_items}</ul>",
        "</section>",
        "<section class=\"panel\">",
        "<h3>Validation Coverage</h3>",
        f"<div class=\"meter\"><div class=\"meter-fill\" style=\"width:{validation_pct}%\"></div></div>",
        f"<p>{validation_pct}% passing validation reports.</p>",
        f"<ul class=\"stat-list\">{validation_items}</ul>",
        "</section>",
        "<section class=\"panel\">",
        "<h3>Token Pressure Signals</h3>",
        "<ul class=\"stat-list\">",
        f"<li><span>Total prompt bytes</span><strong>{escape(summary['prompt_bytes'])}</strong></li>",
        f"<li><span>Largest prompt bytes</span><strong>{escape(summary['largest_prompt_bytes'])}</strong></li>",
        f"<li><span>Estimated prompt tokens</span><strong>{escape(summary['estimated_prompt_tokens'])}</strong></li>",
        f"<li><span>Estimated output tokens</span><strong>{escape(summary['estimated_output_tokens'])}</strong></li>",
        f"<li><span>Total source chars</span><strong>{escape(summary['source_chars'])}</strong></li>",
        f"<li><span>Largest source chars</span><strong>{escape(summary['largest_source_chars'])}</strong></li>",
        "</ul>",
        "</section>",
        "</div>"
    ])


def _job_controls():
    return "\n".join([
        "<div class=\"toolbar\">",
        "<input id=\"job-search\" type=\"search\" placeholder=\"Search unit, job, path, finding code\">",
        "<select id=\"status-filter\" aria-label=\"Status filter\">",
        "<option value=\"all\">All statuses</option>",
        "</select>",
        "<select id=\"validation-filter\" aria-label=\"Validation filter\">",
        "<option value=\"all\">All validation</option>",
        "</select>",
        "<select id=\"risk-filter\" aria-label=\"Risk filter\">",
        "<option value=\"all\">All jobs</option>",
        "<option value=\"failed\">Failed/incomplete</option>",
        "<option value=\"warnings\">Warnings</option>",
        "<option value=\"unresolved\">Unresolved</option>",
        "<option value=\"large\">Large prompts</option>",
        "</select>",
        "</div>",
        "<p id=\"job-count\" class=\"muted\"></p>"
    ])


def _job_table_shell():
    columns = [
        ("sequence", "Seq"),
        ("unit", "Unit"),
        ("status", "Status"),
        ("validation_status", "Validation"),
        ("validation_errors", "Errors"),
        ("validation_warnings", "Warnings"),
        ("generated_files", "Generated"),
        ("written_files", "Written"),
        ("unresolved_count", "Unresolved"),
        ("prompt_bytes", "Prompt Bytes"),
        ("estimated_total_tokens", "Est Tokens"),
        ("source_chars", "Source Chars")
    ]
    header = "".join(
        f"<th data-sort=\"{escape(key)}\">{escape(label)}</th>"
        for key, label in columns
    )
    return "\n".join([
        "<div class=\"table-wrap\">",
        "<table>",
        f"<thead><tr>{header}</tr></thead>",
        "<tbody id=\"job-table-body\"></tbody>",
        "</table>",
        "</div>"
    ])


def _risk_shell():
    return "\n".join([
        "<div class=\"risk-grid\">",
        "<section class=\"panel\">",
        "<h3>Failed Or Incomplete</h3>",
        "<div id=\"risk-failed\"></div>",
        "</section>",
        "<section class=\"panel\">",
        "<h3>Largest Prompts</h3>",
        "<div id=\"risk-prompts\"></div>",
        "</section>",
        "<section class=\"panel\">",
        "<h3>Unresolved Items</h3>",
        "<div id=\"risk-unresolved\"></div>",
        "</section>",
        "</div>"
    ])


def _token_shell(report):
    summary = report["summary"]
    estimated_total = summary.get("estimated_total_tokens", 0)
    prompt_tokens = summary.get("estimated_prompt_tokens", 0)
    output_tokens = summary.get("estimated_output_tokens", 0)
    prompt_share = round((prompt_tokens / estimated_total) * 100, 1) if estimated_total else 0
    output_share = round((output_tokens / estimated_total) * 100, 1) if estimated_total else 0

    return "\n".join([
        "<div class=\"token-grid\">",
        "<section class=\"panel\">",
        "<h3>Estimated API Token Usage</h3>",
        "<p class=\"muted\">Actual provider token metadata is not present in the current artifacts. These values are local estimates using roughly 4 bytes per token.</p>",
        "<ul class=\"stat-list\">",
        f"<li><span>Estimated total tokens</span><strong>{escape(estimated_total)}</strong></li>",
        f"<li><span>Estimated prompt tokens</span><strong>{escape(prompt_tokens)}</strong></li>",
        f"<li><span>Estimated output tokens</span><strong>{escape(output_tokens)}</strong></li>",
        f"<li><span>Prompt/output split</span><strong>{escape(prompt_share)}% / {escape(output_share)}%</strong></li>",
        "</ul>",
        "</section>",
        "<section class=\"panel\">",
        "<h3>Largest Estimated Token Jobs</h3>",
        "<div id=\"token-largest\"></div>",
        "</section>",
        "<section class=\"panel\">",
        "<h3>Token Reduction Opportunities</h3>",
        "<ul class=\"stat-list\">",
        "<li><span>Large prompts</span><strong id=\"token-large-count\">0</strong></li>",
        "<li><span>Not written</span><strong id=\"token-not-written-count\">0</strong></li>",
        "<li><span>Validation failed</span><strong id=\"token-failed-count\">0</strong></li>",
        "</ul>",
        "</section>",
        "</div>"
    ])


def _script():
    return r"""
<script>
const dashboard = JSON.parse(document.getElementById("dashboard-data").textContent);
let currentSort = { key: "sequence", direction: "asc" };
let filteredJobs = [...dashboard.jobs];

function text(value) {
  return value === null || value === undefined ? "" : String(value);
}

function pill(value) {
  const normalized = text(value).toLowerCase();
  return `<span class="pill ${normalized}">${escapeHtml(text(value) || "missing")}</span>`;
}

function escapeHtml(value) {
  return text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function uniqueValues(key) {
  return [...new Set(dashboard.jobs.map(job => job[key] || "missing"))].sort();
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  values.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function applyFilters() {
  const query = document.getElementById("job-search").value.toLowerCase();
  const status = document.getElementById("status-filter").value;
  const validation = document.getElementById("validation-filter").value;
  const risk = document.getElementById("risk-filter").value;

  filteredJobs = dashboard.jobs.filter(job => {
    const haystack = [
      job.sequence,
      job.job_id,
      job.unit,
      job.source_file,
      job.target_file_hint,
      job.status,
      job.validation_status,
      (job.finding_codes || []).join(" ")
    ].map(text).join(" ").toLowerCase();

    if (query && !haystack.includes(query)) return false;
    if (status !== "all" && text(job.status || "missing") !== status) return false;
    if (validation !== "all" && text(job.validation_status || "missing") !== validation) return false;
    if (risk === "failed" && job.status === "completed" && job.validation_status !== "failed") return false;
    if (risk === "warnings" && Number(job.validation_warnings || 0) <= 0) return false;
    if (risk === "unresolved" && Number(job.unresolved_count || 0) <= 0) return false;
    if (risk === "large" && Number(job.prompt_bytes || 0) < 100000) return false;
    return true;
  });

  sortJobs();
  renderJobs();
}

function sortJobs() {
  const { key, direction } = currentSort;
  const factor = direction === "asc" ? 1 : -1;
  filteredJobs.sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (typeof av === "number" || typeof bv === "number") {
      return ((Number(av || 0)) - (Number(bv || 0))) * factor;
    }
    return text(av).localeCompare(text(bv)) * factor;
  });
}

function renderJobs() {
  const tbody = document.getElementById("job-table-body");
  tbody.innerHTML = filteredJobs.map((job, index) => `
    <tr data-index="${index}">
      <td>${escapeHtml(job.sequence)}</td>
      <td><strong>${escapeHtml(job.unit || job.job_id)}</strong><br><span class="muted">${escapeHtml(job.job_id)}</span></td>
      <td>${pill(job.status)}</td>
      <td>${pill(job.validation_status)}</td>
      <td>${escapeHtml(job.validation_errors)}</td>
      <td>${escapeHtml(job.validation_warnings)}</td>
      <td>${escapeHtml(job.generated_files)}</td>
      <td>${escapeHtml(job.written_files)}</td>
      <td>${escapeHtml(job.unresolved_count)}</td>
      <td>${escapeHtml(job.prompt_bytes)}</td>
      <td>${escapeHtml(job.estimated_total_tokens)}</td>
      <td>${escapeHtml(job.source_chars)}</td>
    </tr>
  `).join("");
  document.getElementById("job-count").textContent = `${filteredJobs.length} of ${dashboard.jobs.length} jobs shown`;
  [...tbody.querySelectorAll("tr")].forEach(row => {
    row.addEventListener("click", () => openJobDetail(filteredJobs[Number(row.dataset.index)]));
  });
}

function openJobDetail(job) {
  const panel = document.getElementById("job-detail");
  const content = document.getElementById("job-detail-content");
  content.innerHTML = `
    <h3>${escapeHtml(job.unit || job.job_id)}</h3>
    <p>${pill(job.status)} ${pill(job.validation_status)}</p>
    <dl class="detail-grid">
      <dt>Job</dt><dd><code>${escapeHtml(job.job_id)}</code></dd>
      <dt>Sequence</dt><dd>${escapeHtml(job.sequence)}</dd>
      <dt>Source</dt><dd><code>${escapeHtml(job.source_file)}</code></dd>
      <dt>Target</dt><dd><code>${escapeHtml(job.target_file_hint)}</code></dd>
      <dt>Artifact</dt><dd><code>${escapeHtml(job.artifact_path)}</code></dd>
      <dt>Validation</dt><dd><code>${escapeHtml(job.validation_report_path)}</code></dd>
      <dt>Prompt</dt><dd><code>${escapeHtml(job.prompt_path)}</code></dd>
      <dt>Raw output</dt><dd><code>${escapeHtml(job.raw_output_path)}</code></dd>
      <dt>Generated</dt><dd>${escapeHtml(job.generated_files)} files, ${escapeHtml(job.generated_classes)} classes, ${escapeHtml(job.generated_methods)} methods</dd>
      <dt>Findings</dt><dd>${escapeHtml((job.finding_codes || []).join(", ") || "none")}</dd>
    </dl>
  `;
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
}

function renderRiskList(id, jobs, key) {
  const element = document.getElementById(id);
  if (!jobs.length) {
    element.innerHTML = '<p class="muted">No matching jobs.</p>';
    return;
  }
  element.innerHTML = `<ul class="stat-list">${jobs.slice(0, 12).map(job => `
    <li><span>${escapeHtml(job.unit || job.job_id)}</span><strong>${escapeHtml(job[key])}</strong></li>
  `).join("")}</ul>`;
}

function initNavigation() {
  document.querySelectorAll(".nav-item").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
      document.querySelectorAll(".panel-section").forEach(section => section.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.section).classList.add("active");
    });
  });
}

function init() {
  fillSelect("status-filter", uniqueValues("status"));
  fillSelect("validation-filter", uniqueValues("validation_status"));
  ["job-search", "status-filter", "validation-filter", "risk-filter"].forEach(id => {
    document.getElementById(id).addEventListener("input", applyFilters);
    document.getElementById(id).addEventListener("change", applyFilters);
  });
  document.querySelectorAll("th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      currentSort = {
        key,
        direction: currentSort.key === key && currentSort.direction === "asc" ? "desc" : "asc"
      };
      applyFilters();
    });
  });
  document.querySelector(".detail-close").addEventListener("click", () => {
    const panel = document.getElementById("job-detail");
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
  });
  initNavigation();
  renderRiskList("risk-failed", dashboard.sections.failed_jobs, "validation_errors");
  renderRiskList("risk-prompts", dashboard.sections.largest_prompts, "prompt_bytes");
  renderRiskList("risk-unresolved", dashboard.sections.high_unresolved_jobs, "unresolved_count");
  renderRiskList("token-largest", dashboard.sections.largest_estimated_token_jobs, "estimated_total_tokens");
  document.getElementById("token-large-count").textContent = dashboard.jobs.filter(job => Number(job.prompt_bytes || 0) >= 100000).length;
  document.getElementById("token-not-written-count").textContent = dashboard.jobs.filter(job => job.status === "not_written").length;
  document.getElementById("token-failed-count").textContent = dashboard.jobs.filter(job => job.validation_status === "failed").length;
  applyFilters();
}

init();
</script>
"""


def escape(value):
    return html.escape(str(value), quote=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a dashboard for a modernization migration run."
    )
    parser.add_argument(
        "--run",
        required=True,
        help="Migration run directory, e.g. output/migration_runs/20260706T060336Z."
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path to write the structured dashboard JSON report."
    )
    parser.add_argument(
        "--html-output",
        default=None,
        help="Optional path to write the HTML dashboard."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the structured dashboard JSON to stdout."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    builder = MigrationDashboardBuilder(args.run)
    report = builder.build()

    if args.json_output:
        path = Path(args.json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8"
        )

    if args.html_output:
        path = Path(args.html_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_dashboard_html(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    print("Modernization Dashboard")
    print(f"Run: {report['run_directory']}")
    print(f"Jobs: {report['summary']['job_count']}")
    print(f"Completed: {report['summary']['completed_jobs']}")
    print(f"Failed/incomplete: {report['summary']['failed_or_incomplete_jobs']}")
    print(f"Validation reports: {report['summary']['validation_reports']}")
    print(f"Generated Java files: {report['summary']['generated_java_files']}")
    print(f"Unresolved items: {report['summary']['unresolved_items']}")

    if args.json_output:
        print(f"JSON report: {args.json_output}")

    if args.html_output:
        print(f"HTML dashboard: {args.html_output}")


if __name__ == "__main__":
    main()
