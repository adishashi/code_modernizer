"""
Command line entry point for Stage 4.4 repository summaries.
"""

import argparse

try:
    from ..loader import load_repository
    from ..repository import Repository
    from .generator import generate_repository_summaries
except ImportError:
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository
    from repository_intelligence.summaries.generator import (
        generate_repository_summaries
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate deterministic repository summary artifacts."
    )
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing generated repository JSON artifacts."
    )
    parser.add_argument(
        "--output",
        default="output/summaries",
        help="Directory where summary artifacts will be written."
    )
    parser.add_argument(
        "--types",
        nargs="*",
        choices=["method", "class", "unit", "subsystem", "architecture"],
        default=None,
        help="Summary types to generate. Defaults to all summary types."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(
        load_repository(args.input)
    )
    manifest = generate_repository_summaries(
        repository,
        args.output,
        summary_types=args.types
    )

    print("Repository summaries generated")
    print("Output:", args.output)
    print("Summaries:", manifest["summary_count"])
    print("Counts:", manifest["summary_counts"])


if __name__ == "__main__":
    main()
