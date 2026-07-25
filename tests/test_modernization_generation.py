"""
Tests for LLM code generation backend integration.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    DryRunCodeGenerationBackend,
    LangChainCodeGenerationBackend,
    ModernizationCodeGenerator,
    ModernizationPromptBuilder,
    ModernizationPromptGenerator,
    Repository,
    create_repository_tools,
    load_repository,
    write_generated_java_files
)
from repository_intelligence.modernization.generation import load_env_file  # noqa: E402
from repository_intelligence.modernization.generation import (  # noqa: E402
    DEFAULT_LANGCHAIN_GENERATION_MODEL
)


def prompt_package():
    return {
        "context": {
            "task": {
                "description": "Modernize TFileSource to Java",
                "target_language": "Java"
            },
            "symbols": [
                {
                    "document_type": "class",
                    "name": "TFileSource",
                    "file": "src/filesources/ufilesource.pas"
                }
            ]
        },
        "prompt": {
            "messages": [
                {
                    "role": "system",
                    "content": "system"
                },
                {
                    "role": "user",
                    "content": "user"
                }
            ],
            "prompt": "SYSTEM:\nsystem\nUSER:\nuser"
        }
    }


class FakeContentBlockModel:

    def __init__(self, content):
        self.content = content

    def invoke(self, _messages):
        class Response:
            pass

        response = Response()
        response.content = self.content
        return response


class ModernizationGenerationBackendTests(unittest.TestCase):

    def test_load_env_file_sets_key_without_overwriting_shell_value(self):
        previous = os.environ.get("OPENAI_API_KEY")
        previous_google = os.environ.get("GOOGLE_API_KEY")

        try:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)

            with tempfile.TemporaryDirectory() as directory:
                env_path = Path(directory) / ".env"
                env_path.write_text(
                    "OPENAI_API_KEY=from_file\n"
                    "GOOGLE_API_KEY=google_from_file\n",
                    encoding="utf-8"
                )

                self.assertTrue(load_env_file(env_path))
                self.assertEqual("from_file", os.environ["OPENAI_API_KEY"])
                self.assertEqual(
                    "google_from_file",
                    os.environ["GOOGLE_API_KEY"]
                )

                os.environ["OPENAI_API_KEY"] = "from_shell"
                os.environ["GOOGLE_API_KEY"] = "google_from_shell"
                self.assertTrue(load_env_file(env_path))
                self.assertEqual("from_shell", os.environ["OPENAI_API_KEY"])
                self.assertEqual(
                    "google_from_shell",
                    os.environ["GOOGLE_API_KEY"]
                )
        finally:
            if previous is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous

            if previous_google is None:
                os.environ.pop("GOOGLE_API_KEY", None)
            else:
                os.environ["GOOGLE_API_KEY"] = previous_google

    def test_default_langchain_generation_model_is_gemini(self):
        self.assertEqual(
            "google_genai:gemini-3.5-flash",
            DEFAULT_LANGCHAIN_GENERATION_MODEL
        )

    def test_dry_run_backend_returns_structured_java_skeleton(self):
        backend = DryRunCodeGenerationBackend()
        result = backend.generate(prompt_package())

        self.assertEqual("dry_run", result["backend"])
        structured = result["structured_output"]
        self.assertEqual(1, len(structured["files"]))
        self.assertEqual("java", structured["files"][0]["language"])
        self.assertIn("class FileSource", structured["files"][0]["content"])
        self.assertTrue(structured["unresolved_items"])

    def test_langchain_backend_unwraps_content_block_json(self):
        payload = {
            "files": [
                {
                    "path": "org/doublecmd/filesources/TURI.java",
                    "language": "java",
                    "content": "\n".join([
                        "package org.doublecmd.filesources;",
                        "public class TURI {}"
                    ])
                },
                {
                    "path": "org/doublecmd/filesources/FileSource.java",
                    "language": "java",
                    "content": "\n".join([
                        "package org.doublecmd.filesources;",
                        "public abstract class FileSource {}"
                    ])
                }
            ],
            "classes": [],
            "methods": [],
            "notes": [],
            "unresolved_items": []
        }
        backend = LangChainCodeGenerationBackend(
            FakeContentBlockModel([
                {
                    "type": "text",
                    "text": json.dumps(payload)
                }
            ])
        )
        result = backend.generate(prompt_package())

        self.assertEqual(2, len(result["structured_output"]["files"]))
        self.assertEqual(
            "org/doublecmd/filesources/TURI.java",
            result["structured_output"]["files"][0]["path"]
        )
        self.assertNotIn(
            "type",
            result["structured_output"]["files"][0]["content"]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_parses_json_model_output(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        payload = {
            "files": [
                {
                    "path": "org/doublecmd/FileSource.java",
                    "language": "java",
                    "content": "class FileSource {}"
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
            "notes": ["generated"],
            "unresolved_items": []
        }
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[json.dumps(payload)])
        )
        result = backend.generate(prompt_package())

        self.assertEqual("langchain", result["backend"])
        self.assertEqual(
            "org/doublecmd/FileSource.java",
            result["structured_output"]["files"][0]["path"]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_extracts_fenced_json_model_output(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        payload = {
            "files": [
                {
                    "path": "org/doublecmd/FileSource.java",
                    "language": "java",
                    "content": "public class FileSource {}"
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
        response = (
            "Here is the migration output:\n\n"
            "```json\n"
            f"{json.dumps(payload)}\n"
            "```"
        )
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[response])
        )
        result = backend.generate(prompt_package())

        self.assertEqual(1, len(result["structured_output"]["files"]))
        self.assertFalse(result["structured_output"]["unresolved_items"])

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_repairs_json_fence_with_apostrophe_escape(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        response = "\n".join([
            "```json",
            "{",
            '  "files": [',
            "    {",
            '      "path": "org/doublecmd/filesources/FileSource.java",',
            '      "language": "java",',
            '      "content": "package org.doublecmd.filesources;\\n'
            'public class FileSource {}"',
            "    }",
            "  ],",
            '  "classes": [],',
            '  "methods": [],',
            '  "notes": ["Pascal\\\'s reference counting was mapped."],',
            '  "unresolved_items": []',
            "}",
            "```"
        ])
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[response])
        )
        result = backend.generate(prompt_package())

        self.assertEqual(
            "org/doublecmd/filesources/FileSource.java",
            result["structured_output"]["files"][0]["path"]
        )
        self.assertEqual(
            "Pascal's reference counting was mapped.",
            result["structured_output"]["notes"][0]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_does_not_wrap_json_fence_as_java(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        response = "\n".join([
            "```json",
            "{",
            '  "summary": "public class FileSource appears only in text"',
            "}",
            "```"
        ])
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[response])
        )
        result = backend.generate(prompt_package())

        self.assertFalse(result["structured_output"]["files"])
        self.assertIn(
            "Parsed keys: summary",
            result["structured_output"]["notes"][0]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_extracts_embedded_json_model_output(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        payload = {
            "files": [
                {
                    "path": "org/doublecmd/FileSource.java",
                    "language": "java",
                    "content": "public class FileSource {}"
                }
            ],
            "classes": [],
            "methods": [],
            "notes": ["embedded"],
            "unresolved_items": []
        }
        response = f"Generated result follows:\n{json.dumps(payload)}\nDone."
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[response])
        )
        result = backend.generate(prompt_package())

        self.assertEqual(
            "embedded",
            result["structured_output"]["notes"][0]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_normalizes_common_file_schema_variants(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        payload = {
            "result": {
                "generated_files": [
                    {
                        "filename": "FileSource.java",
                        "code": "\n".join([
                            "package org.doublecmd.filesources;",
                            "public class FileSource {}"
                        ])
                    }
                ],
                "notes": "variant schema"
            }
        }
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[json.dumps(payload)])
        )
        result = backend.generate(prompt_package())

        self.assertEqual(
            "org/doublecmd/filesources/FileSource.java",
            result["structured_output"]["files"][0]["path"]
        )
        self.assertEqual(
            "variant schema",
            result["structured_output"]["notes"][0]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_wraps_raw_java_source_output(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        response = "\n".join([
            "```java",
            "package org.doublecmd.filesources;",
            "public class FileSource {}",
            "```"
        ])
        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(responses=[response])
        )
        result = backend.generate(prompt_package())

        self.assertEqual(1, len(result["structured_output"]["files"]))
        self.assertIn(
            "without the requested JSON schema",
            result["structured_output"]["notes"][0]
        )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_langchain_backend_reports_unrecognized_parsed_keys(self):
        from langchain_core.language_models.fake_chat_models import (
            FakeListChatModel
        )

        backend = LangChainCodeGenerationBackend(
            FakeListChatModel(
                responses=[json.dumps({"summary": "No files here"})]
            )
        )
        result = backend.generate(prompt_package())

        self.assertFalse(result["structured_output"]["files"])
        self.assertIn(
            "Parsed keys: summary",
            result["structured_output"]["notes"][0]
        )


@unittest.skipIf(
    importlib.util.find_spec("chromadb") is None,
    "chromadb is not installed"
)
class ModernizationCodeGeneratorTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )

    def test_code_generator_runs_dry_run_backend_end_to_end(self):
        prompt_generator = ModernizationPromptGenerator(
            self.repository,
            context_options={
                "artifacts_directory": ROOT / "output" / "embeddings",
                "persist_directory": ROOT / "output" / "chroma",
                "summary_directory": ROOT / "output" / "summaries",
                "source_root": ROOT / "doublecmd"
            },
            prompt_builder=ModernizationPromptBuilder(
                max_source_chars=1000
            )
        )
        generator = ModernizationCodeGenerator(
            self.repository,
            backend=DryRunCodeGenerationBackend(),
            prompt_generator=prompt_generator
        )
        result = generator.generate(
            "Modernize TFileSource to Java",
            limit=2,
            graph_depth=1,
            document_types=["class"],
            include_source=False
        )

        self.assertTrue(result["context"]["symbols"])
        self.assertEqual("dry_run", result["generation"]["backend"])
        self.assertTrue(result["generation"]["structured_output"]["files"])

    def test_code_generator_can_persist_generated_java_files(self):
        prompt_generator = ModernizationPromptGenerator(
            self.repository,
            context_options={
                "artifacts_directory": ROOT / "output" / "embeddings",
                "persist_directory": ROOT / "output" / "chroma",
                "summary_directory": ROOT / "output" / "summaries",
                "source_root": ROOT / "doublecmd"
            },
            prompt_builder=ModernizationPromptBuilder(
                max_source_chars=1000
            )
        )
        generator = ModernizationCodeGenerator(
            self.repository,
            backend=DryRunCodeGenerationBackend(),
            prompt_generator=prompt_generator
        )

        with tempfile.TemporaryDirectory() as directory:
            result = generator.generate(
                "Modernize TFileSource to Java",
                limit=2,
                graph_depth=1,
                document_types=["class"],
                include_source=False,
                output_directory=directory
            )
            written = result["generation"]["written_files"]
            file_record = written["written"][0]
            output_path = Path(file_record["absolute_path"])

            self.assertEqual(1, written["summary"]["written"])
            self.assertTrue(output_path.exists())
            self.assertIn("class FileSource", output_path.read_text())

    def test_generated_java_writer_rejects_unsafe_paths(self):
        payload = {
            "structured_output": {
                "files": [
                    {
                        "path": "../Bad.java",
                        "language": "java",
                        "content": "public class Bad {}"
                    },
                    {
                        "path": "org/example/Good.java",
                        "language": "java",
                        "content": "package org.example; public class Good {}"
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            report = write_generated_java_files(payload, directory)

            self.assertEqual(1, report["summary"]["written"])
            self.assertEqual(1, report["summary"]["skipped"])
            self.assertTrue(
                (Path(directory) / "org" / "example" / "Good.java").exists()
            )
            self.assertFalse((Path(directory).parent / "Bad.java").exists())

    def test_generated_java_writer_can_skip_existing_files(self):
        payload = {
            "structured_output": {
                "files": [
                    {
                        "path": "org/example/Good.java",
                        "language": "java",
                        "content": "package org.example; public class Good {}"
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            first = write_generated_java_files(payload, directory)
            second = write_generated_java_files(
                payload,
                directory,
                overwrite=False
            )

            self.assertEqual(1, first["summary"]["written"])
            self.assertEqual(0, second["summary"]["written"])
            self.assertEqual(1, second["summary"]["skipped"])

    def test_generated_java_writer_protects_batch_paths(self):
        payload = {
            "structured_output": {
                "files": [
                    {
                        "path": "org/example/Shared.java",
                        "language": "java",
                        "content": "package org.example; public class Shared {}"
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            report = write_generated_java_files(
                payload,
                directory,
                protected_paths={"org/example/Shared.java"}
            )

            self.assertEqual(0, report["summary"]["written"])
            self.assertEqual(1, report["summary"]["skipped"])
            self.assertEqual(
                "batch_output_collision",
                report["skipped"][0]["code"]
            )
            self.assertFalse(
                (Path(directory) / "org" / "example" / "Shared.java").exists()
            )

    def test_generated_java_writer_protects_shared_support_types(self):
        payload = {
            "structured_output": {
                "files": [
                    {
                        "path": "org/example/TStream.java",
                        "language": "java",
                        "content": "package org.example; public class TStream {}"
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            report = write_generated_java_files(
                payload,
                directory,
                protected_type_names={"TStream"}
            )

            self.assertEqual(0, report["summary"]["written"])
            self.assertEqual(1, report["summary"]["skipped"])
            self.assertEqual(
                "shared_support_type",
                report["skipped"][0]["code"]
            )

    @unittest.skipIf(
        importlib.util.find_spec("langchain_core") is None,
        "langchain_core is not installed"
    )
    def test_generation_tool_returns_structured_output(self):
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
        result = tools["generate_migration_code"].invoke(
            {
                "task": "Modernize TFileSource to Java",
                "limit": 2,
                "graph_depth": 1,
                "document_types": ["class"],
                "include_source": False
            }
        )

        self.assertEqual("dry_run", result["generation"]["backend"])
        self.assertTrue(result["generation"]["structured_output"]["files"])


if __name__ == "__main__":
    unittest.main()
