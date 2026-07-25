"""
Tests for modernization prompt generation.
"""

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    FileMigrationPromptBuilder,
    FileMigrationPromptGenerator,
    ModernizationPromptBuilder,
    ModernizationPromptGenerator,
    Repository,
    create_repository_tools,
    load_repository
)


def sample_context():
    return {
        "task": {
            "description": "Modernize CopyFile to Java",
            "target_language": "Java",
            "purpose": "modernization_context"
        },
        "symbols": [
            {
                "document_type": "method",
                "name": "CopyFile",
                "unit": "uFileSystemUtil",
                "class_name": "TFileSystemOperationHelper",
                "method_name": "CopyFile",
                "file": "src/filesources/filesystem/ufilesystemutil.pas",
                "score": 0.9,
                "sources": ["hybrid", "semantic"]
            }
        ],
        "summaries": [
            {
                "summary_type": "method",
                "name": "CopyFile",
                "summary": "CopyFile copies one filesystem file to a target path."
            }
        ],
        "target_design": {
            "prompt_section": (
                "Java Target Design Templates\n"
                "Template: pascal_routine_to_java_method\n"
                "Rules:\n- Map Pascal functions to Java methods."
            ),
            "templates": [
                {
                    "template_id": "pascal_routine_to_java_method",
                    "title": "Pascal routine to Java method"
                }
            ]
        },
        "graph_context": [
            {
                "document_type": "method",
                "name": "CopyFile",
                "relationships": {
                    "callers": ["Execute"],
                    "callees": ["CopyFileExW"]
                }
            }
        ],
        "source_context": [
            {
                "document_type": "method",
                "symbol": "CopyFile",
                "file": "src/filesources/filesystem/ufilesystemutil.pas",
                "start_line": 523,
                "end_line": 540,
                "extraction_kind": "method_implementation",
                "truncated": False,
                "source": "function CopyFile: Boolean;\nbegin\n  Result := True;\nend;"
            }
        ],
        "modernization_guidance": {
            "touched_files": [
                "src/filesources/filesystem/ufilesystemutil.pas"
            ],
            "next_actions": [
                "Review top hybrid matches before selecting modernization scope."
            ],
            "risk_notes": [
                "Static call graph data can miss dynamic dispatch."
            ]
        }
    }


class ModernizationPromptBuilderTests(unittest.TestCase):

    def test_builds_messages_and_prompt_sections(self):
        builder = ModernizationPromptBuilder()
        result = builder.build_prompt(sample_context())

        self.assertEqual(2, len(result["messages"]))
        self.assertEqual("system", result["messages"][0]["role"])
        self.assertEqual("user", result["messages"][1]["role"])
        self.assertIn("Modernize CopyFile to Java", result["prompt"])
        self.assertIn("## Retrieved Symbols", result["prompt"])
        self.assertIn("## Java Target Design", result["prompt"])
        self.assertIn("```pascal", result["prompt"])
        self.assertGreater(result["statistics"]["prompt_chars"], 0)

    def test_source_budget_truncates_prompt_source(self):
        context = sample_context()
        context["source_context"][0]["source"] = "x" * 200
        builder = ModernizationPromptBuilder(max_source_chars=25)
        result = builder.build_prompt(context)

        self.assertTrue(result["statistics"]["source_truncated"])
        self.assertIn("Source budget exhausted", result["prompt"])


class FileMigrationPromptBuilderTests(unittest.TestCase):

    def sample_job(self):
        return {
            "job_id": "file:uExample",
            "sequence": 1,
            "source": {
                "unit": "uExample",
                "file": "src/example/uexample.pas",
                "path": "doublecmd/src/example/uexample.pas",
                "dependencies": ["Classes", "SysUtils"],
                "dependents": ["uExampleConsumer"]
            },
            "target": {
                "language": "Java",
                "package": "org.doublecmd.example",
                "directory": "org/doublecmd/example",
                "file_hint": "org/doublecmd/example/Example.java"
            },
            "symbols": {
                "classes": ["TExample"],
                "methods": ["TExample.Execute"],
                "class_count": 1,
                "method_count": 1
            },
            "ordering": {
                "mode": "dependency",
                "position": 2,
                "wave": 2,
                "internal_dependencies": ["uBase"],
                "prior_internal_dependencies": ["uBase"],
                "later_internal_dependencies": [],
                "external_dependencies": ["Classes", "SysUtils"],
                "internal_dependents": ["uExampleConsumer"],
                "dependency_ready": True,
                "cycle_participant": False
            },
            "planning_notes": [],
            "source_extraction": {
                "available": True,
                "file": "src/example/uexample.pas",
                "path": "doublecmd/src/example/uexample.pas",
                "line_count": 5,
                "character_count": 68,
                "truncated": False,
                "source": (
                    "unit uExample;\ninterface\n"
                    "type TExample = class end;\nimplementation\nend."
                )
            }
        }

    def test_file_prompt_uses_complete_unit_scope_and_json_schema(self):
        builder = FileMigrationPromptBuilder(max_source_chars=1000)
        result = builder.build_prompt(self.sample_job())

        self.assertEqual("file:uExample", result["job_id"])
        self.assertEqual(2, len(result["messages"]))
        self.assertIn("Convert the complete Pascal unit", result["prompt"])
        self.assertIn("Target package:", result["prompt"])
        self.assertIn("org.doublecmd.example", result["prompt"])
        self.assertIn("## Migration Dependency Ordering", result["prompt"])
        self.assertIn("Internal dependencies already scheduled earlier", result["prompt"])
        self.assertIn("- uBase", result["prompt"])
        self.assertIn("## Shared Java Support", result["prompt"])
        self.assertIn("org.doublecmd.runtime.io.TStream", result["prompt"])
        self.assertIn("Do not include these shared support files", result["prompt"])
        self.assertIn("## Complete Pascal Source", result["prompt"])
        self.assertIn("unit uExample;", result["prompt"])
        self.assertIn("Return only a JSON object", result["prompt"])
        self.assertIn("files", result["prompt"])
        self.assertFalse(result["statistics"]["source_truncated"])

    def test_file_prompt_source_budget_truncates_large_unit(self):
        job = self.sample_job()
        job["source_extraction"]["source"] = "unit uExample;\n" + ("x" * 200)
        builder = FileMigrationPromptBuilder(max_source_chars=20)
        result = builder.build_prompt(job)

        self.assertTrue(result["statistics"]["source_truncated"])
        self.assertIn("Source budget exhausted", result["prompt"])


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class ModernizationPromptGeneratorTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )

    def test_generates_prompt_from_repository_context(self):
        generator = ModernizationPromptGenerator(
            self.repository,
            context_options={
                "artifacts_directory": ROOT / "output" / "embeddings",
                "persist_directory": ROOT / "output" / "chroma",
                "summary_directory": ROOT / "output" / "summaries",
                "source_root": ROOT / "doublecmd"
            },
            prompt_builder=ModernizationPromptBuilder(
                max_source_chars=2000
            )
        )
        result = generator.generate(
            "Modernize TFileSource to Java",
            limit=3,
            graph_depth=1,
            document_types=["class"],
            max_source_lines=40
        )

        self.assertTrue(result["context"]["symbols"])
        self.assertTrue(result["context"]["target_design"]["templates"])
        self.assertIn(
            "Java Target Design Templates",
            result["prompt"]["prompt"]
        )
        self.assertIn("Source Context", result["prompt"]["prompt"])

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_migration_prompt_tool_produces_prompt_package(self):
        tools = {
            tool.name: tool
            for tool in create_repository_tools(
                self.repository,
                artifacts_directory=ROOT / "output" / "embeddings",
                persist_directory=ROOT / "output" / "chroma",
                summary_directory=ROOT / "output" / "summaries",
                source_root=ROOT / "doublecmd"
            )
        }
        result = tools["produce_migration_prompt"].invoke(
            {
                "task": "Modernize TFileSource to Java",
                "limit": 3,
                "graph_depth": 1,
                "document_types": ["class"],
                "include_source": False
            }
        )

        self.assertTrue(result["context"]["symbols"])
        self.assertIn("messages", result["prompt"])
        self.assertIn("Java Target Design", result["prompt"]["prompt"])

    def test_generates_file_migration_prompt_from_plan(self):
        generator = FileMigrationPromptGenerator(
            self.repository,
            source_root=ROOT / "doublecmd",
            prompt_builder=FileMigrationPromptBuilder(
                max_source_chars=5000
            )
        )
        result = generator.generate(
            units=["uFileSource"]
        )

        self.assertEqual(1, result["statistics"]["prompt_count"])
        self.assertEqual("file:uFileSource", result["prompts"][0]["job_id"])
        self.assertIn(
            "Convert the complete Pascal unit uFileSource",
            result["prompts"][0]["prompt"]
        )
        self.assertTrue(
            result["plan"]["jobs"][0]["source_extraction"]["available"]
        )

    def test_file_prompt_cli_outputs_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "repository_intelligence.modernization.file_prompts",
                "--input",
                str(ROOT / "output"),
                "--source-root",
                str(ROOT / "doublecmd"),
                "--units",
                "uFileSource",
                "--max-source-chars",
                "1000",
                "--json"
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT
        )
        result = json.loads(completed.stdout)

        self.assertEqual(1, result["statistics"]["prompt_count"])
        self.assertEqual("file:uFileSource", result["prompts"][0]["job_id"])


if __name__ == "__main__":
    unittest.main()
