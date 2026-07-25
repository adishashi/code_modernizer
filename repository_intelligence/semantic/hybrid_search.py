"""
Command line entry point for Stage 4.3 hybrid retrieval.
"""

"""
Score meanings:
lexical - Accuracy based on keyword/symbol match from RepositorySearch
vector - Similarity from ChromaDB database
graph - structural relevance from repository relationships
"""

import argparse
import json

try:
    from .hybrid_retrieval import HybridRetriever
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.semantic.hybrid_retrieval import HybridRetriever
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run hybrid repository retrieval."
    )
    parser.add_argument(
        "query",
        help="Natural-language or symbol query."
    )
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing generated repository JSON artifacts."
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
        "--collection",
        default="repository_intelligence",
        help="ChromaDB collection name."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum combined results to print."
    )
    parser.add_argument(
        "--lexical-limit",
        type=int,
        default=25,
        help="Maximum lexical candidates to collect."
    )
    parser.add_argument(
        "--vector-limit",
        type=int,
        default=25,
        help="Maximum vector candidates to collect."
    )
    parser.add_argument(
        "--graph-depth",
        type=int,
        default=1,
        help="Graph expansion depth."
    )
    parser.add_argument(
        "--types",
        nargs="*",
        choices=["unit", "class", "method", "subsystem"],
        default=None,
        help="Optional document types to search."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON output."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(
        load_repository(args.input)
    )
    retriever = HybridRetriever(
        repository,
        artifacts_directory=args.artifacts,
        persist_directory=args.chroma,
        collection_name=args.collection
    )

    try:
        result = retriever.retrieve(
            args.query,
            limit=args.limit,
            lexical_limit=args.lexical_limit,
            vector_limit=args.vector_limit,
            graph_depth=args.graph_depth,
            document_types=args.types
        )

        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
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
                print(f"   sources: {', '.join(item['sources'])}")
                print(f"   scores: {item['scores']}")

                if item.get("file"):
                    print(f"   file: {item['file']}")

                print()
    finally:
        retriever.close()


if __name__ == "__main__":
    main()
