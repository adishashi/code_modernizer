import json
from pathlib import Path


PROJECT_ROOT = Path(
    r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
)

OUTPUT_DIR = PROJECT_ROOT / "output"

REPOSITORY_INDEX_FILE = (
    OUTPUT_DIR / "repository_index.json"
)

METHOD_INDEX_FILE = (
    OUTPUT_DIR / "method_index.json"
)


def load_repository():

    with open(
        REPOSITORY_INDEX_FILE,
        "r",
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


def build_method_index(
    repository
):

    method_index = []

    for unit_info in repository:

        unit_name = unit_info.get(
            "unit"
        )

        file_path = unit_info.get(
            "file"
        )

        methods = unit_info.get(
            "methods",
            []
        )

        for method in methods:

            if not method.get(
                "definition",
                False
            ):
                continue

            method_index.append(
                {
                    "unit": unit_name,

                    "class": method.get(
                        "class"
                    ),

                    "method": method.get(
                        "name"
                    ),

                    "kind": method.get(
                        "kind"
                    ),

                    "file": file_path
                }
            )

    return method_index


def save_index(
    method_index
):

    with open(
        METHOD_INDEX_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            method_index,
            fp,
            indent=4
        )


def print_stats(
    method_index
):

    print()

    print(
        f"Method Definitions: "
        f"{len(method_index)}"
    )

    classes = set()

    for entry in method_index:

        if entry["class"]:

            classes.add(
                entry["class"]
            )

    print(
        f"Classes With Definitions: "
        f"{len(classes)}"
    )


def main():

    repository = load_repository()

    method_index = build_method_index(
        repository
    )

    save_index(
        method_index
    )

    print_stats(
        method_index
    )

    print()

    print(
        f"Saved to:\n"
        f"{METHOD_INDEX_FILE}"
    )


if __name__ == "__main__":

    main()