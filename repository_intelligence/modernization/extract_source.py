"""
Command line entry point for Pascal source extraction.
"""

import argparse
import json

try:
    from .source_extractor import PascalSourceExtractor
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.modernization.source_extractor import (
        PascalSourceExtractor
    )
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract Pascal source for a unit, class, or method."
    )
    parser.add_argument(
        "name",
        help="Unit, class, or method name."
    )
    parser.add_argument(
        "--type",
        choices=["unit", "class", "method"],
        required=True,
        help="Symbol type to extract."
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
        "--class-name",
        default=None,
        help="Optional class filter for method extraction."
    )
    parser.add_argument(
        "--unit-name",
        default=None,
        help="Optional unit filter for class or method extraction."
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=None,
        help="Optional maximum lines to return."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full extraction record as JSON."
    )

    return parser.parse_args()


def resolve_symbol(repository, args):
    if args.type == "unit":
        unit = repository.find_unit(args.name)

        if not unit:
            return None

        return {
            "document_type": "unit",
            "name": unit.get("unit"),
            "unit": unit.get("unit"),
            "file": unit.get("file")
        }

    if args.type == "class":
        matches = repository.find_classes(
            args.name,
            unit_name=args.unit_name
        )

        if not matches:
            return None

        record = matches[0]
        return {
            "document_type": "class",
            "name": record.get("name"),
            "class_name": record.get("name"),
            "unit": record.get("unit"),
            "file": record.get("file")
        }

    matches = repository.find_methods(
        args.name,
        class_name=args.class_name,
        unit_name=args.unit_name
    )

    if not matches:
        return None

    record = matches[0]
    return {
        "document_type": "method",
        "name": record.get("method"),
        "method_name": record.get("method"),
        "class_name": record.get("class"),
        "unit": record.get("unit"),
        "file": record.get("file")
    }


def main():
    args = parse_args()
    repository = Repository(
        load_repository(args.input)
    )
    symbol = resolve_symbol(repository, args)

    if not symbol:
        raise SystemExit(f"No {args.type} found for {args.name}")

    extractor = PascalSourceExtractor(args.source_root)
    result = extractor.extract_symbol(
        symbol,
        max_lines=args.max_lines
    )

    if not result:
        raise SystemExit(f"No source extracted for {args.name}")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(
        f"{result['document_type']} {result['symbol']} "
        f"{result['file']}:{result['start_line']}-{result['end_line']}"
    )
    print()
    print(result["source"])


if __name__ == "__main__":
    main()
