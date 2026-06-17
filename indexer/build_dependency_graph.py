import json
from pathlib import Path


PROJECT_ROOT = Path(
    r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
)

OUTPUT_DIR = PROJECT_ROOT / "output"

REPOSITORY_INDEX_FILE = (
    OUTPUT_DIR / "repository_index.json"
)

DEPENDENCY_GRAPH_FILE = (
    OUTPUT_DIR / "dependency_graph.json"
)


def load_repository_index():

    with open(
        REPOSITORY_INDEX_FILE,
        "r",
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


def build_unit_lookup(repository):

    units = {}

    for entry in repository:

        unit_name = entry.get("unit")

        if unit_name:

            units[
                unit_name.lower()
            ] = unit_name

    return units


def build_dependency_graph(
    repository,
    known_units
):

    edges = []

    seen = set()

    for entry in repository:

        source = entry.get("unit")

        if not source:
            continue

        for dependency in entry.get(
            "dependencies",
            []
        ):

            dependency_lower = (
                dependency.lower()
            )

            # Only keep dependencies
            # that exist inside the repo

            if (
                dependency_lower
                not in known_units
            ):
                continue

            target = known_units[
                dependency_lower
            ]

            edge_key = (
                source,
                target
            )

            if edge_key in seen:
                continue

            seen.add(edge_key)

            edges.append(
                {
                    "source": source,
                    "target": target
                }
            )

    incoming = set()
    outgoing = set()

    for edge in edges:

        incoming.add(
            edge["target"].lower()
        )

        outgoing.add(
            edge["source"].lower()
        )

    orphans = []

    for unit in known_units:
        if unit not in incoming and unit not in outgoing:
            orphans.append(unit)

    print(orphans)

    return edges


def compute_statistics(
    repository,
    edges
):

    stats = {}

    stats["units"] = len(
        {
            entry["unit"]
            for entry in repository
            if entry.get("unit")
        }
    )

    stats["dependency_edges"] = len(
        edges
    )

    outgoing = {}

    incoming = {}

    for edge in edges:

        source = edge["source"]
        target = edge["target"]

        outgoing[source] = (
            outgoing.get(
                source,
                0
            )
            + 1
        )

        incoming[target] = (
            incoming.get(
                target,
                0
            )
            + 1
        )

    stats["most_dependent_units"] = sorted(
        outgoing.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    stats["most_referenced_units"] = sorted(
        incoming.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    return stats


def save_graph(
    edges,
    stats
):

    output = {
        "statistics": stats,
        "edges": edges
    }

    with open(
        DEPENDENCY_GRAPH_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            output,
            fp,
            indent=4
        )


def print_summary(
    stats
):

    print("\n")
    print("=" * 80)

    print(
        f"Units: {stats['units']}"
    )

    print(
        f"Dependency Edges: "
        f"{stats['dependency_edges']}"
    )

    print("\nMost Dependent Units")

    for unit, count in stats[
        "most_dependent_units"
    ]:

        print(
            f"  {unit}: {count}"
        )

    print("\nMost Referenced Units")

    for unit, count in stats[
        "most_referenced_units"
    ]:

        print(
            f"  {unit}: {count}"
        )

    print("=" * 80)


def main():

    print(
        "Loading repository index..."
    )

    repository = (
        load_repository_index()
    )

    print(
        f"Loaded "
        f"{len(repository)} units"
    )

    known_units = (
        build_unit_lookup(
            repository
        )
    )

    print(
        f"Found "
        f"{len(known_units)} "
        f"repository units"
    )

    edges = build_dependency_graph(
        repository,
        known_units
    )

    stats = compute_statistics(
        repository,
        edges
    )

    save_graph(
        edges,
        stats
    )

    print_summary(
        stats
    )

    print(
        f"\nSaved graph to:"
    )

    print(
        DEPENDENCY_GRAPH_FILE
    )


if __name__ == "__main__":

    main()