import json
from pathlib import Path


PROJECT_ROOT = Path(
    r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
)

OUTPUT_DIR = PROJECT_ROOT / "output"

REPOSITORY_INDEX_FILE = (
    OUTPUT_DIR / "repository_index.json"
)

CLASS_GRAPH_FILE = (
    OUTPUT_DIR / "class_hierarchy.json"
)


def load_repository():

    with open(
        REPOSITORY_INDEX_FILE,
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


def build_class_graph(
    repository
):

    edges = []

    seen = set()

    for unit in repository:

        for cls in unit.get(
            "classes",
            []
        ):

            child = cls.get(
                "name"
            )

            parent = cls.get(
                "parent"
            )

            if (
                not child
                or
                not parent
            ):
                continue

            edge = (
                parent,
                child
            )

            if edge in seen:
                continue

            seen.add(edge)

            edges.append(
                {
                    "parent": parent,
                    "child": child,
                    "unit": unit["unit"]
                }
            )

    return edges

def save_graph(edges):

    with open(
        CLASS_GRAPH_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            edges,
            fp,
            indent=4
        )

def print_stats(edges):

    parents = set()
    children = set()

    for edge in edges:

        parents.add(
            edge["parent"]
        )

        children.add(
            edge["child"]
        )

    print()

    print(
        f"Inheritance Edges: "
        f"{len(edges)}"
    )

    print(
        f"Parent Classes: "
        f"{len(parents)}"
    )

    print(
        f"Child Classes: "
        f"{len(children)}"
    )

def main():

    repository = load_repository()

    edges = build_class_graph(
        repository
    )

    save_graph(edges)

    print_stats(edges)

    print(
        f"Saved to "
        f"{CLASS_GRAPH_FILE}"
    )


if __name__ == "__main__":

    main()