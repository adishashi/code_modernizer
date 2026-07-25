"""
Command line entry point for Stage 4.2 ChromaDB ingestion.
"""

import argparse

try:
    from .vector_store import (
        DEFAULT_COLLECTION_NAME,
        ingest_chroma_artifacts
    )
except ImportError:
    from vector_store import (
        DEFAULT_COLLECTION_NAME,
        ingest_chroma_artifacts
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ingest repository embedding artifacts into ChromaDB."
    )
    parser.add_argument(
        "--artifacts",
        default="output/embeddings",
        help="Directory containing metadata.jsonl, embeddings.npy, manifest.json."
    )
    parser.add_argument(
        "--persist",
        default="output/chroma",
        help="Persistent ChromaDB directory."
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help="ChromaDB collection name."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of records to insert per ChromaDB add call."
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the existing collection instead of resetting it."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    result = ingest_chroma_artifacts(
        args.artifacts,
        args.persist,
        collection_name=args.collection,
        batch_size=args.batch_size,
        reset=not args.append
    )

    print("ChromaDB ingestion complete")
    print("Collection:", result["collection"])
    print("Persist Directory:", result["persist_directory"])
    print("Ingested:", result["ingested"])
    print("Collection Count:", result["count"])
    print("Embedding Shape:", result["embedding_shape"])


if __name__ == "__main__":
    main()
