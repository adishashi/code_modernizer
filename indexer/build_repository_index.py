import json
from pathlib import Path

from parser import TreeSitterParser
from visitors.repository_visitor import RepositoryVisitor


PROJECT_ROOT = Path(
    r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
)

SOURCE_ROOT = PROJECT_ROOT / "doublecmd"

OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR /
    "repository_index.json"
)


def process_file(
    parser,
    pas_file
):

    try:

        tree, source = parser.parse(
            pas_file
        )

        visitor = RepositoryVisitor(
            source
        )

        visitor.visit(
            tree.root_node
        )

        print("=" * 80)
        print("FILE:", pas_file.name)

        print("UNIT:")
        print(visitor.unit_name)

        print("DEPENDENCIES:")
        print(visitor.dependencies[:5])

        print("CLASSES:")
        print(visitor.classes[:5])

        print("FIELDS:")
        print(visitor.fields[:5])

        print("METHODS:")
        print(visitor.methods[:5])

        print("=" * 80)

        return {
            "unit": visitor.unit_name,

            "file": str(
                pas_file.relative_to(
                    SOURCE_ROOT
                )
            ),

            "dependencies":
                visitor.dependencies,

            "classes":
                visitor.classes,

            "fields":
                visitor.fields,

            "methods":
                visitor.methods
        }

    except Exception as ex:

        print(
            f"ERROR: {pas_file}"
        )

        print(ex)

        return None


def main():

    parser = TreeSitterParser()

    repository_index = []

    pas_files = list(
        SOURCE_ROOT.rglob(
            "*.pas"
        )
    )

    print(
        f"Found {len(pas_files)} Pascal files"
    )

    for i, pas_file in enumerate(
        pas_files,
        start=1
    ):

        print(
            f"[{i}/{len(pas_files)}] "
            f"{pas_file.name}"
        )

        result = process_file(
            parser,
            pas_file
        )

        if result:

            repository_index.append(
                result
            )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            repository_index,
            fp,
            indent=4
        )

    print()
    print(
        f"Indexed "
        f"{len(repository_index)} units"
    )

    print(
        f"Saved: {OUTPUT_FILE}"
    )


if __name__ == "__main__":

    main()