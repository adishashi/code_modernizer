"""
Command line entry point for modernization context assembly.
"""

import argparse
import json

try:
    from .context import ModernizationContextAssembler
    from ..loader import load_repository
    from ..repository import Repository
except ImportError:
    from repository_intelligence.modernization.context import ModernizationContextAssembler
    from repository_intelligence.loader import load_repository
    from repository_intelligence.repository import Repository


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build hybrid modernization context for a repository task."
    )
    parser.add_argument(
        "task",
        help="Modernization task or natural-language query."
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
        "--summaries",
        default="output/summaries",
        help="Directory containing generated summaries."
    )
    parser.add_argument(
        "--source-root",
        default="doublecmd",
        help="Root directory for source files referenced by repository metadata."
    )
    parser.add_argument(
        "--collection",
        default="repository_intelligence",
        help="ChromaDB collection name."
    )
    parser.add_argument(
        "--target-language",
        default="Java",
        help="Modernization target language label."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum retrieval results from each retrieval layer."
    )
    parser.add_argument(
        "--lexical-limit",
        type=int,
        default=25,
        help="Maximum lexical candidates to collect for hybrid retrieval."
    )
    parser.add_argument(
        "--vector-limit",
        type=int,
        default=25,
        help="Maximum vector candidates to collect for hybrid retrieval."
    )
    parser.add_argument(
        "--graph-depth",
        type=int,
        default=1,
        help="Graph expansion depth for retrieval and graph context."
    )
    parser.add_argument(
        "--types",
        nargs="*",
        choices=["unit", "class", "method", "subsystem"],
        default=None,
        help="Optional document types to include."
    )
    parser.add_argument(
        "--max-snippet-lines",
        type=int,
        default=80,
        help="Maximum lines per source snippet."
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Skip source snippet extraction."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON context."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    repository = Repository(
        load_repository(args.input)
    )
    assembler = ModernizationContextAssembler(
        repository,
        artifacts_directory=args.artifacts,
        persist_directory=args.chroma,
        summary_directory=args.summaries,
        source_root=args.source_root,
        collection_name=args.collection
    )

    try:
        context = assembler.build_context(
            args.task,
            target_language=args.target_language,
            limit=args.limit,
            lexical_limit=args.lexical_limit,
            vector_limit=args.vector_limit,
            graph_depth=args.graph_depth,
            document_types=args.types,
            include_source=not args.no_source,
            max_snippet_lines=args.max_snippet_lines
        )

        if args.json:
            print(json.dumps(context, indent=2, sort_keys=True))
        else:
            print(assembler.render_context(context))
    finally:
        assembler.close()


if __name__ == "__main__":
    main()
