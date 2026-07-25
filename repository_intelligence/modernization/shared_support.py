"""
Canonical Java support contracts for Delphi/Object Pascal migration.

Full-file migration prompts often need the same Pascal runtime abstractions
again and again. Without a canonical contract, model-backed jobs tend to
generate incompatible local copies of support types such as TStream. This module
defines shared Java files that batch generation can write once and prompts can
reference consistently.
"""

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path


@dataclass(frozen=True)
class JavaSharedSupportFile:
    support_id: str
    title: str
    pascal_symbols: tuple
    java_package: str
    java_type: str
    path: str
    content: str
    guidance: tuple

    def to_dict(self):
        return asdict(self)


class JavaSharedSupportCatalog:
    """
    Repository of canonical Java support files used across migration jobs.
    """

    def __init__(self, files=None):
        self.files = list(files or DEFAULT_SHARED_SUPPORT_FILES)
        self.by_id = {
            file.support_id: file
            for file in self.files
        }

    def list_files(self):
        return list(self.files)

    def get(self, support_id):
        return self.by_id.get(support_id)

    def require(self, support_id):
        support_file = self.get(support_id)

        if not support_file:
            raise KeyError(support_id)

        return support_file

    def protected_paths(self):
        return {
            support_file.path
            for support_file in self.files
        }

    def protected_type_names(self):
        return {
            support_file.java_type
            for support_file in self.files
        }

    def as_generation_payload(self):
        return {
            "structured_output": {
                "files": [
                    {
                        "path": support_file.path,
                        "language": "java",
                        "content": support_file.content
                    }
                    for support_file in self.files
                ],
                "classes": [
                    {
                        "name": support_file.java_type,
                        "source_symbol": ", ".join(
                            support_file.pascal_symbols
                        ),
                        "responsibility": support_file.title
                    }
                    for support_file in self.files
                ],
                "methods": [],
                "notes": [
                    "Canonical shared support files for migrated Java output."
                ],
                "unresolved_items": []
            }
        }

    def render(self):
        sections = [
            "Java Shared Support Contracts",
            (
                "Use these canonical support types instead of generating "
                "local replacements in each migrated unit."
            )
        ]

        for support_file in self.files:
            sections.extend([
                "",
                f"Support: {support_file.support_id}",
                f"Title: {support_file.title}",
                "Pascal symbols: " + ", ".join(support_file.pascal_symbols),
                (
                    "Java type: "
                    f"{support_file.java_package}.{support_file.java_type}"
                ),
                f"Path: {support_file.path}",
                "Rules:"
            ])
            sections.extend(
                f"- {rule}"
                for rule in support_file.guidance
            )

        return "\n".join(sections)

    def write_files(self, output_directory, overwrite=False):
        root = Path(output_directory).resolve()
        written = []
        skipped = []

        root.mkdir(parents=True, exist_ok=True)

        for support_file in self.files:
            target = root / support_file.path

            if target.exists() and not overwrite:
                skipped.append({
                    "path": support_file.path,
                    "support_id": support_file.support_id,
                    "reason": (
                        "Shared support file already exists and overwrite is "
                        "disabled."
                    )
                })
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(support_file.content, encoding="utf-8")
            written.append({
                "path": support_file.path,
                "absolute_path": str(target),
                "support_id": support_file.support_id,
                "bytes": target.stat().st_size
            })

        return {
            "output_directory": str(root),
            "written": written,
            "skipped": skipped,
            "summary": {
                "written": len(written),
                "skipped": len(skipped)
            }
        }


DEFAULT_SHARED_SUPPORT_FILES = (
    JavaSharedSupportFile(
        support_id="pascal_tseekorigin",
        title="Shared Delphi TSeekOrigin equivalent",
        pascal_symbols=("TSeekOrigin", "soFromBeginning", "soFromCurrent", "soFromEnd"),
        java_package="org.doublecmd.runtime.io",
        java_type="TSeekOrigin",
        path="org/doublecmd/runtime/io/TSeekOrigin.java",
        content="\n".join([
            "package org.doublecmd.runtime.io;",
            "",
            "/**",
            " * Canonical equivalent of Delphi/FPC stream seek origins.",
            " */",
            "public enum TSeekOrigin {",
            "    soFromBeginning,",
            "    soFromCurrent,",
            "    soFromEnd",
            "}"
        ]),
        guidance=(
            "Import org.doublecmd.runtime.io.TSeekOrigin when translating stream seek calls.",
            "Do not generate another TSeekOrigin enum in unit-local packages.",
            "Preserve Pascal names so translated switch statements remain traceable."
        )
    ),
    JavaSharedSupportFile(
        support_id="pascal_tstream",
        title="Shared Delphi TStream equivalent",
        pascal_symbols=("TStream", "Read", "Write", "Seek", "Position", "Size"),
        java_package="org.doublecmd.runtime.io",
        java_type="TStream",
        path="org/doublecmd/runtime/io/TStream.java",
        content="\n".join([
            "package org.doublecmd.runtime.io;",
            "",
            "import java.io.IOException;",
            "",
            "/**",
            " * Canonical base class for migrated Delphi/FPC TStream usages.",
            " */",
            "public abstract class TStream implements AutoCloseable {",
            "    public abstract int read(byte[] buffer, int offset, int count) throws IOException;",
            "    public abstract int write(byte[] buffer, int offset, int count) throws IOException;",
            "    public abstract long seek(long offset, TSeekOrigin origin) throws IOException;",
            "",
            "    public long getPosition() throws IOException {",
            "        return seek(0, TSeekOrigin.soFromCurrent);",
            "    }",
            "",
            "    public void setPosition(long position) throws IOException {",
            "        seek(position, TSeekOrigin.soFromBeginning);",
            "    }",
            "",
            "    public long getSize() throws IOException {",
            "        long current = getPosition();",
            "        long size = seek(0, TSeekOrigin.soFromEnd);",
            "        setPosition(current);",
            "        return size;",
            "    }",
            "",
            "    public void setSize(long size) throws IOException {",
            "        throw new UnsupportedOperationException(\"setSize is not supported by this stream\");",
            "    }",
            "",
            "    public void writeBuffer(byte[] buffer, int count) throws IOException {",
            "        int written = write(buffer, 0, count);",
            "        if (written != count) {",
            "            throw new IOException(\"Unable to write requested byte count\");",
            "        }",
            "    }",
            "",
            "    public long copyFrom(TStream source, long count) throws IOException {",
            "        byte[] buffer = new byte[8192];",
            "        long total = 0;",
            "        while (count < 0 || total < count) {",
            "            int requested = buffer.length;",
            "            if (count >= 0) {",
            "                requested = (int) Math.min(requested, count - total);",
            "            }",
            "            if (requested <= 0) {",
            "                break;",
            "            }",
            "            int read = source.read(buffer, 0, requested);",
            "            if (read <= 0) {",
            "                break;",
            "            }",
            "            writeBuffer(buffer, read);",
            "            total += read;",
            "        }",
            "        return total;",
            "    }",
            "",
            "    @Override",
            "    public void close() throws IOException {",
            "    }",
            "}"
        ]),
        guidance=(
            "Import org.doublecmd.runtime.io.TStream for Pascal TStream references.",
            "Do not generate another TStream class in unit-local packages.",
            "Subclasses should override only the operations they actually support.",
            "Use IOException for stream operation failures."
        )
    ),
    JavaSharedSupportFile(
        support_id="pascal_crc32",
        title="Shared CRC32 helper for DCCrc32-style routines",
        pascal_symbols=("DCCrc32", "crc32_16bytes"),
        java_package="org.doublecmd.runtime.checksum",
        java_type="DCCrc32",
        path="org/doublecmd/runtime/checksum/DCCrc32.java",
        content="\n".join([
            "package org.doublecmd.runtime.checksum;",
            "",
            "import java.util.zip.CRC32;",
            "",
            "/**",
            " * Shared CRC32 helper for migrated units that referenced DCCrc32.",
            " */",
            "public final class DCCrc32 {",
            "    private DCCrc32() {",
            "    }",
            "",
            "    public static int crc32_16bytes(byte[] buffer, int offset, int count, int seed) {",
            "        CRC32 crc32 = new CRC32();",
            "        if (seed != 0) {",
            "            crc32.update(new byte[] {",
            "                (byte) seed,",
            "                (byte) (seed >>> 8),",
            "                (byte) (seed >>> 16),",
            "                (byte) (seed >>> 24)",
            "            });",
            "        }",
            "        crc32.update(buffer, offset, count);",
            "        return (int) crc32.getValue();",
            "    }",
            "}"
        ]),
        guidance=(
            "Import org.doublecmd.runtime.checksum.DCCrc32 when a unit references DCCrc32.",
            "Do not generate local DCCrc32 helper classes per unit.",
            "Flag CRC seed semantics for review if exact Delphi compatibility matters."
        )
    )
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect or write canonical Java migration support files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("render", help="Render prompt guidance.")

    list_parser = subparsers.add_parser("list", help="List support files.")
    list_parser.add_argument("--json", action="store_true")

    write_parser = subparsers.add_parser("write", help="Write support files.")
    write_parser.add_argument(
        "--output-directory",
        default="output/generated_java",
        help="Directory where support Java files should be written."
    )
    write_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing support files."
    )
    write_parser.add_argument("--json", action="store_true")

    return parser.parse_args()


def main():
    args = parse_args()
    catalog = JavaSharedSupportCatalog()

    if args.command == "render":
        print(catalog.render())
        return

    if args.command == "list":
        records = [support_file.to_dict() for support_file in catalog.list_files()]

        if args.json:
            print(json.dumps(records, indent=2, sort_keys=True))
        else:
            for record in records:
                print(f"{record['support_id']}: {record['path']}")

        return

    result = catalog.write_files(
        args.output_directory,
        overwrite=args.overwrite
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Output directory: {result['output_directory']}")
        print(f"Written: {result['summary']['written']}")
        print(f"Skipped: {result['summary']['skipped']}")


if __name__ == "__main__":
    main()
