"""
Tests for generated Java modernization validation.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    DryRunCodeGenerationBackend,
    ModernizationCodeGenerator,
    ModernizationPromptBuilder,
    ModernizationPromptGenerator,
    Repository,
    create_repository_tools,
    load_repository,
    validate_generated_code
)


VALID_GENERATION = {
    "generation": {
        "structured_output": {
            "files": [
                {
                    "path": "org/doublecmd/filesources/FileSource.java",
                    "language": "java",
                    "content": "\n".join([
                        "package org.doublecmd.filesources;",
                        "",
                        "public class FileSource {",
                        "    public String name() {",
                        "        return \"source\";",
                        "    }",
                        "}"
                    ])
                }
            ],
            "classes": [
                {
                    "name": "FileSource",
                    "source_symbol": "TFileSource",
                    "responsibility": "File source abstraction"
                }
            ],
            "methods": [],
            "notes": [],
            "unresolved_items": []
        }
    }
}


class GeneratedJavaValidationTests(unittest.TestCase):

    def test_valid_generated_java_passes_basic_validation(self):
        report = validate_generated_code(VALID_GENERATION)

        self.assertTrue(report["passed"])
        self.assertEqual("passed", report["status"])
        self.assertEqual(0, report["summary"]["errors"])
        self.assertEqual(
            "FileSource",
            report["files"][0]["declarations"][0]["name"]
        )

    def test_validator_reports_common_llm_output_defects(self):
        report = validate_generated_code({
            "structured_output": {
                "files": [
                    {
                        "path": "../Bad.txt",
                        "language": "text",
                        "content": "```java\npublic class Good {\n"
                    },
                    {
                        "path": "org/example/WrongName.java",
                        "language": "java",
                        "content": "public class OtherName {}"
                    }
                ],
                "classes": [
                    {
                        "name": "MissingClass"
                    }
                ],
                "unresolved_items": ["Need real implementation"]
            }
        })

        codes = {finding["code"] for finding in report["findings"]}

        self.assertFalse(report["passed"])
        self.assertIn("unsafe_path", codes)
        self.assertIn("non_java_path", codes)
        self.assertIn("invalid_language", codes)
        self.assertIn("markdown_fence_in_source", codes)
        self.assertIn("public_type_filename_mismatch", codes)
        self.assertIn("class_metadata_without_declaration", codes)
        self.assertIn("unresolved_items_present", codes)

    def test_validator_allows_public_nested_types(self):
        report = validate_generated_code({
            "structured_output": {
                "files": [
                    {
                        "path": "org/doublecmd/filesources/FileSourceField.java",
                        "language": "java",
                        "content": "\n".join([
                            "package org.doublecmd.filesources;",
                            "",
                            "public class FileSourceField {",
                            "    public enum Alignment {",
                            "        LEFT, CENTER, RIGHT",
                            "    }",
                            "}"
                        ])
                    }
                ],
                "classes": [],
                "methods": [],
                "notes": [],
                "unresolved_items": []
            }
        })
        codes = {finding["code"] for finding in report["findings"]}

        self.assertTrue(report["passed"])
        self.assertNotIn("public_type_filename_mismatch", codes)
        self.assertNotIn("multiple_public_types", codes)

    def test_validator_ignores_declaration_words_in_comments(self):
        report = validate_generated_code({
            "structured_output": {
                "files": [
                    {
                        "path": "org/doublecmd/TStream.java",
                        "language": "java",
                        "content": "\n".join([
                            "package org.doublecmd;",
                            "",
                            "/**",
                            " * Abstraction of the Delphi TStream class to provide stream behavior.",
                            " */",
                            "public abstract class TStream {",
                            "}"
                        ])
                    },
                    {
                        "path": "org/doublecmd/AbZstd.java",
                        "language": "java",
                        "content": "\n".join([
                            "package org.doublecmd;",
                            "",
                            "/** Simple interface to zstd library. */",
                            "public class AbZstd {",
                            "}"
                        ])
                    }
                ],
                "classes": [],
                "methods": [],
                "notes": [],
                "unresolved_items": []
            }
        })
        declarations = [
            declaration["name"]
            for file_report in report["files"]
            for declaration in file_report["declarations"]
        ]
        codes = {finding["code"] for finding in report["findings"]}

        self.assertTrue(report["passed"])
        self.assertEqual(["TStream", "AbZstd"], declarations)
        self.assertNotIn("duplicate_type_declaration", codes)

    def test_validator_matches_nested_class_metadata(self):
        report = validate_generated_code({
            "structured_output": {
                "files": [
                    {
                        "path": "org/doublecmd/AbSWStm.java",
                        "language": "java",
                        "content": "\n".join([
                            "package org.doublecmd;",
                            "",
                            "public class AbSWStm {",
                            "    public static class TabSlidingWindowStream {",
                            "    }",
                            "}"
                        ])
                    }
                ],
                "classes": [
                    {
                        "name": "AbSWStm.TabSlidingWindowStream"
                    }
                ],
                "methods": [],
                "notes": [],
                "unresolved_items": []
            }
        })
        codes = {finding["code"] for finding in report["findings"]}

        self.assertTrue(report["passed"])
        self.assertNotIn("class_metadata_without_declaration", codes)

    def test_validator_reports_stronger_batch_defects(self):
        content = "\n".join([
            "package org.doublecmd.filesources;",
            "",
            "public class FileSource {",
            "    // TODO: replace placeholder behavior.",
            "}"
        ])
        report = validate_generated_code({
            "structured_output": {
                "files": [
                    {
                        "path": "org/doublecmd/filesources/FileSource.java",
                        "language": "java",
                        "content": content
                    },
                    {
                        "path": "org/doublecmd/filesources/FileSource.java",
                        "language": "java",
                        "content": content
                    },
                    {
                        "path": "org/doublecmd/other/FileSource.java",
                        "language": "java",
                        "content": content
                    },
                    {
                        "path": "org/doublecmd/migration/RawPayload.java",
                        "language": "java",
                        "content": (
                            "json\n"
                            "{\"files\": [{\"path\": \"A.java\"}]}"
                        )
                    },
                    {
                        "path": "org/doublecmd/bad/NoPackage.java",
                        "language": "java",
                        "content": "public class NoPackage {}"
                    },
                    {
                        "path": "org/doublecmd/class/BadPackage.java",
                        "language": "java",
                        "content": "\n".join([
                            "package org.doublecmd.class;",
                            "public class BadPackage {}"
                        ])
                    }
                ],
                "classes": [],
                "methods": [],
                "notes": [],
                "unresolved_items": []
            }
        })
        codes = {finding["code"] for finding in report["findings"]}

        self.assertFalse(report["passed"])
        self.assertIn("duplicate_file_path", codes)
        self.assertIn("duplicate_type_declaration", codes)
        self.assertIn("embedded_generation_json", codes)
        self.assertIn("missing_package_declaration", codes)
        self.assertIn("invalid_package_declaration", codes)
        self.assertIn("placeholder_source_text", codes)

    def test_generation_can_attach_validation_report(self):
        repository = Repository(load_repository(ROOT / "output"))
        prompt_generator = ModernizationPromptGenerator(
            repository,
            context_options={
                "artifacts_directory": ROOT / "output" / "embeddings",
                "persist_directory": ROOT / "output" / "chroma",
                "summary_directory": ROOT / "output" / "summaries",
                "source_root": ROOT / "doublecmd"
            },
            prompt_builder=ModernizationPromptBuilder(max_source_chars=1000)
        )
        generator = ModernizationCodeGenerator(
            repository,
            backend=DryRunCodeGenerationBackend(),
            prompt_generator=prompt_generator
        )
        result = generator.generate(
            "Modernize TFileSource to Java",
            document_types=["class"],
            include_source=False,
            validate=True
        )

        self.assertIn("validation", result["generation"])
        self.assertEqual("passed", result["generation"]["validation"]["status"])

    def test_generation_tool_accepts_validation_flag(self):
        repository = Repository(load_repository(ROOT / "output"))
        tools = {
            tool.name: tool
            for tool in create_repository_tools(
                repository,
                artifacts_directory=ROOT / "output" / "embeddings",
                persist_directory=ROOT / "output" / "chroma",
                summary_directory=ROOT / "output" / "summaries",
                source_root=ROOT / "doublecmd"
            )
        }
        result = tools["generate_migration_code"].invoke(
            {
                "task": "Modernize TFileSource to Java",
                "limit": 2,
                "document_types": ["class"],
                "include_source": False,
                "validation_enabled": True
            }
        )

        self.assertEqual("passed", result["generation"]["validation"]["status"])

    def test_validation_cli_reads_generation_json_from_stdin(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "repository_intelligence.modernization.validation",
                "--json"
            ],
            input=json.dumps(VALID_GENERATION),
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT
        )
        report = json.loads(completed.stdout)

        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
