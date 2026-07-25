"""
Validation utilities for generated Java modernization output.

The validator works on the structured generation payload rather than raw model
text. It performs deterministic checks that are useful before a developer or a
later automation step spends time reviewing or compiling generated Java.
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


DECLARATION_PATTERN = re.compile(
    r"\b(public\s+)?(class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
PACKAGE_PATTERN = re.compile(
    r"^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;",
    re.MULTILINE
)
JAVA_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EMBEDDED_GENERATION_JSON_PATTERN = re.compile(
    r"^\s*(?:json\s*)?\{[\s\S]{0,200}?\"files\"\s*:",
    re.IGNORECASE
)
PLACEHOLDER_PATTERN = re.compile(
    "|".join([
        r"\bTODO\b",
        r"\bFIXME\b",
        r"\bXXX\b",
        r"implementation\s+(?:omitted|pending|required)",
        r"not\s+implemented",
        r"placeholder",
        r"throw\s+new\s+UnsupportedOperationException"
    ]),
    re.IGNORECASE
)
JAVA_RESERVED_WORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch",
    "char", "class", "const", "continue", "default", "do", "double", "else",
    "enum", "extends", "final", "finally", "float", "for", "goto", "if",
    "implements", "import", "instanceof", "int", "interface", "long",
    "native", "new", "package", "private", "protected", "public", "return",
    "short", "static", "strictfp", "super", "switch", "synchronized",
    "this", "throw", "throws", "transient", "try", "void", "volatile",
    "while", "record", "sealed", "permits", "non-sealed", "var", "yield"
}


class GeneratedJavaValidator:
    """
    Performs lightweight validation over generated Java file records.

    These checks intentionally stop short of full semantic validation. They are
    designed to catch common LLM output defects: missing files, markdown fences,
    invalid paths, unbalanced delimiters, package/path mismatches, and public
    class names that do not match their file names.
    """

    def validate(self, generation_result, compile_sources=False):
        structured = self._structured_output(generation_result)
        findings = []

        if not isinstance(structured, dict):
            findings.append(self._finding(
                "error",
                "missing_structured_output",
                "Generation result does not contain a structured output object."
            ))
            return self._report([], findings)

        files = structured.get("files", [])

        if not isinstance(files, list) or not files:
            findings.append(self._finding(
                "error",
                "missing_files",
                "Structured output must include at least one generated file."
            ))
            files = []

        file_reports = []

        for index, file_record in enumerate(files):
            report = self._validate_file_record(file_record, index)
            file_reports.append(report)
            findings.extend(report["findings"])

        findings.extend(self._validate_file_set(file_reports))
        findings.extend(self._validate_class_metadata(structured, file_reports))

        unresolved = structured.get("unresolved_items", [])

        if unresolved:
            findings.append(self._finding(
                "warning",
                "unresolved_items_present",
                "Generated output still contains unresolved migration items."
            ))

        if compile_sources and file_reports:
            findings.extend(self._compile(file_reports))

        return self._report(file_reports, findings)

    def _structured_output(self, generation_result):
        """
        Accept a full generation package, a generation object, or the structured
        output itself so CLI pipelines can pass whichever JSON level they have.
        """

        if not isinstance(generation_result, dict):
            return None

        if "generation" in generation_result:
            return generation_result["generation"].get("structured_output")

        if "structured_output" in generation_result:
            return generation_result.get("structured_output")

        return generation_result

    def _validate_file_record(self, file_record, index):
        findings = []

        if not isinstance(file_record, dict):
            return {
                "index": index,
                "path": None,
                "language": None,
                "package": None,
                "declarations": [],
                "findings": [
                    self._finding(
                        "error",
                        "invalid_file_record",
                        "Generated file entry must be an object."
                    )
                ]
            }

        path = file_record.get("path")
        language = file_record.get("language")
        content = file_record.get("content")

        if not path or not isinstance(path, str):
            findings.append(self._finding(
                "error",
                "missing_path",
                "Generated file is missing a relative path."
            ))
        else:
            findings.extend(self._validate_path(path))

        if language != "java":
            findings.append(self._finding(
                "error",
                "invalid_language",
                "Generated file language must be 'java'.",
                path
            ))

        if not content or not isinstance(content, str):
            findings.append(self._finding(
                "error",
                "missing_content",
                "Generated file content is empty or missing.",
                path
            ))
            content = ""

        findings.extend(self._validate_source_text(path, content))

        package_name = self._package_name(content)
        declarations = self._declarations(content)
        findings.extend(self._validate_package_name(path, package_name))
        findings.extend(self._validate_package_path(path, package_name))
        findings.extend(self._validate_declarations(path, declarations))

        return {
            "index": index,
            "path": path,
            "language": language,
            "content": content,
            "package": package_name,
            "declarations": declarations,
            "findings": findings
        }

    def _validate_path(self, path):
        findings = []
        normalized = path.replace("\\", "/")
        parsed = PurePosixPath(normalized)

        if parsed.is_absolute() or ".." in parsed.parts:
            findings.append(self._finding(
                "error",
                "unsafe_path",
                "Generated file path must be a safe relative path.",
                path
            ))

        if not normalized.endswith(".java"):
            findings.append(self._finding(
                "error",
                "non_java_path",
                "Generated Java file path must end with .java.",
                path
            ))

        return findings

    def _validate_source_text(self, path, content):
        findings = []

        if "```" in content:
            findings.append(self._finding(
                "error",
                "markdown_fence_in_source",
                "Generated source content must not include markdown fences.",
                path
            ))

        if EMBEDDED_GENERATION_JSON_PATTERN.search(content):
            findings.append(self._finding(
                "error",
                "embedded_generation_json",
                (
                    "Generated source appears to contain the structured JSON "
                    "response instead of Java source code."
                ),
                path
            ))

        if PLACEHOLDER_PATTERN.search(content):
            findings.append(self._finding(
                "warning",
                "placeholder_source_text",
                (
                    "Generated source still contains placeholder or unresolved "
                    "implementation text."
                ),
                path
            ))

        balance_findings = self._delimiter_findings(path, content)
        findings.extend(balance_findings)

        if not DECLARATION_PATTERN.search(self._code_view(content)):
            findings.append(self._finding(
                "warning",
                "missing_type_declaration",
                "Generated source does not declare a Java type.",
                path
            ))

        return findings

    def _delimiter_findings(self, path, content):
        counts = self._delimiter_counts(content)
        findings = []

        for opening, closing in [("{", "}"), ("(", ")"), ("[", "]")]:
            if counts[opening] != counts[closing]:
                findings.append(self._finding(
                    "error",
                    "unbalanced_delimiters",
                    (
                        f"Generated source has unbalanced {opening}{closing} "
                        "delimiters."
                    ),
                    path
                ))

        return findings

    def _delimiter_counts(self, content):
        """
        Count delimiters outside comments and string/character literals.

        This is a small lexical scanner, not a Java parser. It is enough to keep
        braces inside comments or string literals from producing false failures.
        """

        counts = {"{": 0, "}": 0, "(": 0, ")": 0, "[": 0, "]": 0}
        state = "code"
        index = 0

        while index < len(content):
            character = content[index]
            next_character = (
                content[index + 1]
                if index + 1 < len(content)
                else ""
            )

            if state == "code":
                if character == "/" and next_character == "/":
                    state = "line_comment"
                    index += 2
                    continue

                if character == "/" and next_character == "*":
                    state = "block_comment"
                    index += 2
                    continue

                if character == '"':
                    state = "string"
                    index += 1
                    continue

                if character == "'":
                    state = "char"
                    index += 1
                    continue

                if character in counts:
                    counts[character] += 1

            elif state == "line_comment":
                if character == "\n":
                    state = "code"

            elif state == "block_comment":
                if character == "*" and next_character == "/":
                    state = "code"
                    index += 2
                    continue

            elif state == "string":
                if character == "\\":
                    index += 2
                    continue

                if character == '"':
                    state = "code"

            elif state == "char":
                if character == "\\":
                    index += 2
                    continue

                if character == "'":
                    state = "code"

            index += 1

        return counts

    def _package_name(self, content):
        match = PACKAGE_PATTERN.search(content)
        return match.group(1) if match else None

    def _declarations(self, content):
        code_view = self._code_view(content)
        return [
            {
                "visibility": "public" if match.group(1) else "package",
                "kind": match.group(2),
                "name": match.group(3),
                "depth": self._brace_depth_at(content, match.start())
            }
            for match in DECLARATION_PATTERN.finditer(code_view)
        ]

    def _code_view(self, content):
        """
        Return a same-length view with comments and literals blanked out.

        Declaration regexes are intentionally lightweight. Masking comments and
        literals keeps phrases like "class to provide" in Javadocs from being
        interpreted as real Java declarations while preserving character
        offsets for brace-depth calculation.
        """

        characters = list(content)
        state = "code"
        index = 0

        while index < len(characters):
            character = characters[index]
            next_character = (
                characters[index + 1]
                if index + 1 < len(characters)
                else ""
            )

            if state == "code":
                if character == "/" and next_character == "/":
                    characters[index] = " "
                    characters[index + 1] = " "
                    state = "line_comment"
                    index += 2
                    continue

                if character == "/" and next_character == "*":
                    characters[index] = " "
                    characters[index + 1] = " "
                    state = "block_comment"
                    index += 2
                    continue

                if character == '"':
                    characters[index] = " "
                    state = "string"
                    index += 1
                    continue

                if character == "'":
                    characters[index] = " "
                    state = "char"
                    index += 1
                    continue

            elif state == "line_comment":
                if character == "\n":
                    state = "code"
                else:
                    characters[index] = " "

            elif state == "block_comment":
                if character == "*" and next_character == "/":
                    characters[index] = " "
                    characters[index + 1] = " "
                    state = "code"
                    index += 2
                    continue

                if character != "\n":
                    characters[index] = " "

            elif state == "string":
                if character == "\\":
                    characters[index] = " "

                    if index + 1 < len(characters):
                        characters[index + 1] = " "

                    index += 2
                    continue

                characters[index] = " " if character != "\n" else "\n"

                if character == '"':
                    state = "code"

            elif state == "char":
                if character == "\\":
                    characters[index] = " "

                    if index + 1 < len(characters):
                        characters[index + 1] = " "

                    index += 2
                    continue

                characters[index] = " " if character != "\n" else "\n"

                if character == "'":
                    state = "code"

            index += 1

        return "".join(characters)

    def _brace_depth_at(self, content, stop_index):
        """
        Return Java brace depth before a declaration.

        The validator only enforces filename matching for top-level public
        declarations. Nested public types are legal Java, so they should not be
        counted as additional public top-level classes.
        """

        depth = 0
        state = "code"
        index = 0

        while index < min(stop_index, len(content)):
            character = content[index]
            next_character = (
                content[index + 1]
                if index + 1 < len(content)
                else ""
            )

            if state == "code":
                if character == "/" and next_character == "/":
                    state = "line_comment"
                    index += 2
                    continue

                if character == "/" and next_character == "*":
                    state = "block_comment"
                    index += 2
                    continue

                if character == '"':
                    state = "string"
                    index += 1
                    continue

                if character == "'":
                    state = "char"
                    index += 1
                    continue

                if character == "{":
                    depth += 1
                elif character == "}":
                    depth = max(0, depth - 1)

            elif state == "line_comment":
                if character == "\n":
                    state = "code"

            elif state == "block_comment":
                if character == "*" and next_character == "/":
                    state = "code"
                    index += 2
                    continue

            elif state == "string":
                if character == "\\":
                    index += 2
                    continue

                if character == '"':
                    state = "code"

            elif state == "char":
                if character == "\\":
                    index += 2
                    continue

                if character == "'":
                    state = "code"

            index += 1

        return depth

    def _validate_package_path(self, path, package_name):
        if not path or not package_name:
            return []

        normalized = path.replace("\\", "/")
        package_path = package_name.replace(".", "/")

        if not normalized.startswith(f"{package_path}/"):
            return [
                self._finding(
                    "warning",
                    "package_path_mismatch",
                    (
                        "Generated file path does not match the declared Java "
                        "package."
                    ),
                    path
                )
            ]

        return []

    def _validate_package_name(self, path, package_name):
        if not path:
            return []

        if not package_name:
            return [
                self._finding(
                    "error",
                    "missing_package_declaration",
                    "Generated Java source must declare a package.",
                    path
                )
            ]

        for segment in package_name.split("."):
            if (
                not JAVA_IDENTIFIER_PATTERN.match(segment)
                or segment in JAVA_RESERVED_WORDS
            ):
                return [
                    self._finding(
                        "error",
                        "invalid_package_declaration",
                        (
                            "Generated Java package contains an invalid "
                            "identifier segment."
                        ),
                        path
                    )
                ]

        return []

    def _validate_declarations(self, path, declarations):
        if not path:
            return []

        findings = []
        file_stem = PurePosixPath(path.replace("\\", "/")).stem
        public_declarations = [
            declaration
            for declaration in declarations
            if (
                declaration["visibility"] == "public"
                and declaration.get("depth", 0) == 0
            )
        ]

        for declaration in public_declarations:
            if declaration["name"] != file_stem:
                findings.append(self._finding(
                    "error",
                    "public_type_filename_mismatch",
                    (
                        "Public Java type name must match the generated file "
                        "name."
                    ),
                    path
                ))

        if len(public_declarations) > 1:
            findings.append(self._finding(
                "error",
                "multiple_public_types",
                "A Java source file may not declare multiple public types.",
                path
            ))

        return findings

    def _validate_file_set(self, file_reports):
        """
        Validate relationships across generated files.

        Single-file checks cannot catch two common batch defects: multiple
        outputs targeting the same path, and separate files declaring the same
        package/type name. Those defects make persisted migration output
        ambiguous even when each source file looks superficially valid.
        """

        findings = []
        seen_paths = {}
        seen_types = {}

        for report in file_reports:
            path = report.get("path")

            if path:
                normalized_path = path.replace("\\", "/")

                if normalized_path in seen_paths:
                    findings.append(self._finding(
                        "error",
                        "duplicate_file_path",
                        (
                            "Multiple generated file records target the same "
                            "Java path."
                        ),
                        path
                    ))
                else:
                    seen_paths[normalized_path] = report

            package_name = report.get("package")

            for declaration in report.get("declarations", []):
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

                if qualified_name in seen_types:
                    findings.append(self._finding(
                        "error",
                        "duplicate_type_declaration",
                        (
                            "Multiple generated files declare the same Java "
                            "type."
                        ),
                        path
                    ))
                else:
                    seen_types[qualified_name] = report

        return findings

    def _validate_class_metadata(self, structured, file_reports):
        classes = structured.get("classes", [])

        if not classes:
            return []

        declared_names = {
            declaration["name"]
            for report in file_reports
            for declaration in report.get("declarations", [])
        }
        findings = []

        for class_record in classes:
            class_name = (
                class_record.get("name")
                if isinstance(class_record, dict)
                else None
            )

            metadata_name = class_name.split(".")[-1] if class_name else None

            if metadata_name and metadata_name not in declared_names:
                findings.append(self._finding(
                    "warning",
                    "class_metadata_without_declaration",
                    (
                        f"Class metadata references {class_name}, but no "
                        "generated Java declaration with that name was found."
                    )
                ))

        return findings

    def _compile(self, file_reports):
        javac = shutil.which("javac")

        if not javac:
            return [
                self._finding(
                    "warning",
                    "javac_unavailable",
                    "Compilation validation was requested, but javac was not found."
                )
            ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_paths = []

            for report in file_reports:
                path = report.get("path")

                if not path:
                    continue

                target = root / path.replace("\\", "/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    report.get("content", ""),
                    encoding="utf-8"
                )
                source_paths.append(str(target))

            if not source_paths:
                return []

            completed = subprocess.run(
                [javac, "-d", str(root / "classes"), *source_paths],
                capture_output=True,
                text=True,
                check=False
            )

            if completed.returncode == 0:
                return []

            return [
                self._finding(
                    "error",
                    "javac_failed",
                    self._compact_compiler_output(
                        completed.stderr or completed.stdout
                    )
                )
            ]

    def _compact_compiler_output(self, output):
        lines = [line.rstrip() for line in output.splitlines() if line.strip()]
        return "\n".join(lines[:20]) if lines else "javac failed."

    def _report(self, file_reports, findings):
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
                "files": len(file_reports),
                "errors": len(errors),
                "warnings": len(warnings)
            },
            "findings": findings,
            "files": [
                {
                    "path": report.get("path"),
                    "package": report.get("package"),
                    "declarations": report.get("declarations", [])
                }
                for report in file_reports
            ]
        }

    def _finding(self, severity, code, message, file=None):
        finding = {
            "severity": severity,
            "code": code,
            "message": message
        }

        if file:
            finding["file"] = file

        return finding


def validate_generated_code(generation_result, compile_sources=False):
    """
    Convenience wrapper for API callers and LangChain tools.
    """

    return GeneratedJavaValidator().validate(
        generation_result,
        compile_sources=compile_sources
    )


def _load_input(path):
    if path == "-":
        import sys

        return json.loads(sys.stdin.read())

    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate generated Java modernization output."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="JSON generation result file, or '-' for stdin."
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Also compile generated Java with javac when available."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full validation report as JSON."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    payload = _load_input(args.input)
    report = validate_generated_code(
        payload,
        compile_sources=args.compile
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    print(f"Status: {report['status']}")
    print(f"Files: {report['summary']['files']}")
    print(f"Errors: {report['summary']['errors']}")
    print(f"Warnings: {report['summary']['warnings']}")

    for finding in report["findings"]:
        location = f" [{finding['file']}]" if "file" in finding else ""
        print(
            f"- {finding['severity'].upper()} {finding['code']}"
            f"{location}: {finding['message']}"
        )


if __name__ == "__main__":
    main()
