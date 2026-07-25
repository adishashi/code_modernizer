"""
Command line entry point for inspecting generated summary artifacts.
"""

import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect repository summary artifacts."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Optional case-insensitive text to search in summary names."
    )
    parser.add_argument(
        "--summaries",
        default="output/summaries",
        help="Directory containing summaries.jsonl and manifest.json."
    )
    parser.add_argument(
        "--type",
        choices=["method", "class", "unit", "subsystem", "architecture"],
        default=None,
        help="Optional summary type filter."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum matching summaries to print."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print matching records as JSON."
    )

    return parser.parse_args()


def load_records(summary_directory):
    path = Path(summary_directory) / "summaries.jsonl"

    if not path.exists():
        raise FileNotFoundError(path)

    records = []

    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()

            if not line:
                continue

            records.append(json.loads(line))

    return records


def main():
    args = parse_args()
    records = load_records(args.summaries)
    query = args.query.casefold() if args.query else None
    matches = []

    for record in records:
        if args.type and record.get("summary_type") != args.type:
            continue

        if query and query not in record.get("name", "").casefold():
            continue

        matches.append(record)

        if len(matches) >= args.limit:
            break

    if args.json:
        print(json.dumps(matches, indent=2, sort_keys=True))
        return

    print("Matches:", len(matches))
    print()

    for index, record in enumerate(matches, start=1):
        print(
            f"{index}. {record['summary_type']} "
            f"{record['name']}"
        )
        print(f"   id: {record['summary_id']}")
        print(f"   summary: {record['summary']}")

        if record.get("file"):
            print(f"   file: {record['file']}")

        print()


if __name__ == "__main__":
    main()
