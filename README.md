# Repository Intelligence and Delphi Modernization

This repository contains a Python-based repository intelligence system for understanding a large Pascal/Delphi codebase and supporting staged modernization work toward Java.

The current focus is the Double Commander Pascal source tree. The tooling builds code indexes, dependency views, retrieval context, modernization prompts, Java generation workflows, validation reports, and a lightweight dashboard for tracking migration runs.

## What It Does

- Builds repository indexes for Pascal units, symbols, classes, routines, dependencies, and call relationships.
- Provides semantic, lexical, and hybrid retrieval over repository context.
- Generates modernization context for Delphi-to-Java migration tasks.
- Runs file-oriented migration batches with resumable outputs and persistent artifacts.
- Produces validation and dashboard data for generated Java migration outputs.

## Repository Layout

```text
indexer/                    Pascal indexing and static analysis utilities
repository_intelligence/     Retrieval, summaries, modernization, CLI tools
tests/                       Focused regression tests for repository intelligence behavior
output/                      Local generated migration/index artifacts, ignored by Git
```

## Setup

Create a virtual environment and install the project dependencies used by your local workflow.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a local `.env` file for model-backed generation. The file is intentionally ignored by Git.

```text
GOOGLE_API_KEY=your_key_here
```

## Common Commands

Run the test suite:

```powershell
python -m unittest discover -s tests -v
```

Generate or inspect repository intelligence data through the module CLIs:

```powershell
python -m repository_intelligence.semantic.search --help
python -m repository_intelligence.modernization.generation --help
python -m repository_intelligence.modernization.batch_generation --help
python -m repository_intelligence.modernization.dashboard --help
```

Most generated artifacts are written under `output/`, including migration runs, generated Java files, validation reports, and dashboard files.

## Modernization Workflow

The modernization pipeline is designed to work file by file:

1. Plan Pascal source files for migration.
2. Extract full source and repository context for each file.
3. Build file-oriented modernization prompts.
4. Generate Java outputs through the configured LLM backend.
5. Persist generated files and metadata per migration run.
6. Validate outputs and review progress through reports or the dashboard.

The generated Java should be treated as migration artifacts, not final production code, until it has passed project-specific compilation and behavior validation.

## Git Hygiene

Local state, secrets, roadmap notes, generated indexes, migration outputs, and dashboard artifacts are ignored by default. The committed repository should contain source code, tests, and reusable project documentation only.
