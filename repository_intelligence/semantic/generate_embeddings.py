"""
Command line entry point for Stage 4.1 embedding generation.
"""

import argparse

try:
    from .embeddings import (
        LocalHashingEmbeddingProvider,
        generate_repository_embeddings
    )
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from embeddings import (
        LocalHashingEmbeddingProvider,
        generate_repository_embeddings
    )
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate repository embedding artifacts."
    )
    parser.add_argument(
        "--input",
        default="output",
        help="Directory containing generated repository JSON artifacts."
    )
    parser.add_argument(
        "--output",
        default="output/embeddings",
        help="Directory where embedding artifacts will be written."
    )
    parser.add_argument(
        "--types",
        nargs="*",
        default=None,
        choices=["unit", "class", "method", "subsystem"],
        help="Document types to embed. Defaults to all types."
    )
    parser.add_argument(
        "--dimensions",
        type=int,
        default=384,
        help="Hashing embedding dimension count."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(
        load_repository(args.input)
    )
    provider = LocalHashingEmbeddingProvider(
        dimensions=args.dimensions
    )

    manifest = generate_repository_embeddings(
        repository,
        args.output,
        document_types=args.types,
        provider=provider
    )

    print("Embedding artifacts generated")
    print("Output:", args.output)
    print("Documents:", manifest["document_count"])
    print("Shape:", manifest["embedding_shape"])
    print("Provider:", manifest["provider"]["provider"])


if __name__ == "__main__":
    main()
