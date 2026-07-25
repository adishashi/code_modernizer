"""
Command line entry point for semantic search over ChromaDB.
"""

import argparse
import json

try:
    from .semantic_search import SemanticSearchEngine
except ImportError:
    from repository_intelligence.semantic.semantic_search import SemanticSearchEngine


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run semantic repository search over ChromaDB."
    )
    parser.add_argument(
        "query",
        help="Natural-language or symbol query."
    )
    parser.add_argument(
        "--artifacts",
        default="output/embeddings",
        help="Directory containing embedding artifacts."
    )
    parser.add_argument(
        "--chroma",
        default="output/chroma",
        help="Persistent ChromaDB directory."
    )
    parser.add_argument(
        "--summaries",
        default="output/summaries",
        help="Directory containing generated summary artifacts."
    )
    parser.add_argument(
        "--collection",
        default="repository_intelligence",
        help="ChromaDB collection name."
    )
    parser.add_argument(
        "--types",
        nargs="*",
        choices=["unit", "class", "method", "subsystem"],
        default=None,
        help="Optional document types to search."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum results to return."
    )
    parser.add_argument(
        "--no-summaries",
        action="store_true",
        help="Do not enrich results with generated summaries."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON output."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    engine = SemanticSearchEngine(
        artifacts_directory=args.artifacts,
        persist_directory=args.chroma,
        collection_name=args.collection,
        summary_directory=args.summaries
    )

    try:
        result = engine.search(
            args.query,
            limit=args.limit,
            document_types=args.types,
            include_summaries=not args.no_summaries
        )

        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
            return

        print(f"Query: {result['query']}")
        print(
            "Vector Collection Count:",
            result["statistics"]["vector_collection_count"]
        )
        print()

        for index, item in enumerate(result["results"], start=1):
            print(
                f"{index}. {item['document_type']} "
                f"{item['name']} score={item['score']}"
            )
            print(f"   id: {item['document_id']}")
            print(f"   distance: {item['distance']}")

            if item.get("file"):
                print(f"   file: {item['file']}")

            if item.get("summary"):
                print(f"   summary: {item['summary']}")

            print()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
