"""
Command line entry point for file-oriented migration prompts.
"""

import argparse
import json

try:
    from .prompts import FileMigrationPromptBuilder, FileMigrationPromptGenerator
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.modernization.prompts import (
        FileMigrationPromptBuilder,
        FileMigrationPromptGenerator
    )
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate file-oriented Delphi to Java migration prompts."
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
        help="Maximum number of file prompts to generate."
    )
    parser.add_argument(
        "--order",
        choices=["dependency", "source"],
        default="dependency",
        help="Migration job ordering."
    )
    parser.add_argument(
        "--max-source-chars",
        type=int,
        default=60000,
        help="Maximum Pascal source characters included per prompt."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured prompt packages as JSON."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(load_repository(args.input))
    generator = FileMigrationPromptGenerator(
        repository,
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
        order=args.order
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    for index, prompt in enumerate(result["prompts"]):
        if index:
            print("\n" + "=" * 80 + "\n")

        print(prompt["prompt"])


if __name__ == "__main__":
    main()
