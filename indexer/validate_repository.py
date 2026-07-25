import json
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(
    r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
)

OUTPUT_DIR = (
    PROJECT_ROOT /
    "output"
)

FILES = {

    "repository":
        OUTPUT_DIR / "repository_index.json",

    "dependency":
        OUTPUT_DIR / "dependency_graph.json",

    "hierarchy":
        OUTPUT_DIR / "class_hierarchy.json",

    "methods":
        OUTPUT_DIR / "method_index.json",

    "callgraph":
        OUTPUT_DIR / "call_graph_dedup.json"
}


class Validator:

    def __init__(self):

        self.errors = []

        self.warnings = []

        self.info = []

    def error(self, msg):

        self.errors.append(msg)

    def warning(self, msg):

        self.warnings.append(msg)

    def note(self, msg):

        self.info.append(msg)


validator = Validator()


##############################################################
# JSON
##############################################################

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as fp:

        return json.load(fp)


##############################################################
# Repository
##############################################################

def validate_repository_index(repo):

    units = set()

    files = set()

    classes = set()

    methods = set()

    for unit in repo:

        unit_name = unit["unit"]

        if unit_name in units:

            validator.error(
                f"Duplicate unit: {unit_name}"
            )

        units.add(unit_name)

        file_name = unit["file"]

        if file_name in files:

            validator.error(
                f"Duplicate file: {file_name}"
            )

        files.add(file_name)

        seen = set()

        for dep in unit["dependencies"]:

            if dep in seen:

                validator.warning(
                    f"{unit_name}: duplicate dependency {dep}"
                )

            seen.add(dep)

        seen = set()

        for cls in unit["classes"]:

            name = cls["name"]

            fq = (
                unit_name,
                name
            )

            if fq in seen:

                validator.error(
                    f"{unit_name}: duplicate class {name}"
                )

            seen.add(fq)

            classes.add(name)

        seen = set()

        for method in unit["methods"]:

            fq = (

                method["class"],

                method["name"],

                method["definition"]
            )

            if fq in seen:

                validator.error(
                    f"{unit_name}: duplicate method {fq}"
                )

            seen.add(fq)

            methods.add(fq)

    validator.note(
        f"Repository Units: {len(units)}"
    )

    validator.note(
        f"Repository Classes: {len(classes)}"
    )

    validator.note(
        f"Repository Methods: {len(methods)}"
    )


##############################################################
# Dependency Graph
##############################################################

def validate_dependency_graph(edges):

    seen = set()

    self_edges = 0

    for edge in edges:

        key = (
            edge["source"],
            edge["target"]
        )

        if key in seen:

            validator.error(
                f"Duplicate dependency edge {key}"
            )

        seen.add(key)

        if edge["source"] == edge["target"]:

            self_edges += 1

    validator.note(
        f"Dependency Edges: {len(edges)}"
    )

    validator.note(
        f"Self Dependency Edges: {self_edges}"
    )


##############################################################
# Class Hierarchy
##############################################################

def validate_class_hierarchy(edges):

    parent_map = {}

    for edge in edges:

        child = edge["child"]

        parent = edge["parent"]

        if child == parent:

            validator.error(
                f"Self inheritance: {child}"
            )

        if child in parent_map:

            validator.warning(
                f"{child} has multiple parents "
                f"({parent_map[child]}, {parent})"
            )

        parent_map[child] = parent

    validator.note(
        f"Hierarchy Classes: {len(parent_map)}"
    )


##############################################################
# Method Index
##############################################################

def validate_method_index(methods):

    seen = set()

    for m in methods:

        fq = (

            m["unit"],

            m["class"],

            m["method"]
        )

        if fq in seen:

            validator.error(
                f"Duplicate method definition {fq}"
            )

        seen.add(fq)

    validator.note(
        f"Indexed Methods: {len(methods)}"
    )


##############################################################
# Call Graph
##############################################################

def validate_call_graph(edges):

    seen = set()

    for edge in edges:

        key = (

            edge["caller"],

            edge["callee"]
        )

        if key in seen:

            validator.error(
                f"Duplicate call edge {key}"
            )

        seen.add(key)

    validator.note(
        f"Call Graph Edges: {len(edges)}"
    )


##############################################################
# Cross References
##############################################################

def validate_cross_refs(
    repo,
    methods,
    hierarchy,
    callgraph
):

    repo_units = {

        x["unit"]

        for x in repo
    }

    repo_classes = set()

    for unit in repo:

        for cls in unit["classes"]:

            repo_classes.add(
                cls["name"]
            )

    indexed_methods = set()

    for m in methods:

        if m["class"]:

            indexed_methods.add(
                f'{m["class"]}.{m["method"]}'
            )

        else:

            indexed_methods.add(
                m["method"]
            )

    #
    # hierarchy
    #

    for edge in hierarchy:

        if (
            edge["child"]
            not in repo_classes
        ):

            validator.warning(
                f'Hierarchy child missing: '
                f'{edge["child"]}'
            )

    #
    # call graph
    #

    for edge in callgraph:

        if (
            edge["caller"]
            not in indexed_methods
        ):

            validator.warning(
                f'Unknown caller: '
                f'{edge["caller"]}'
            )


##############################################################
# Summary
##############################################################

def print_summary():

    print()

    print("=" * 80)

    print("REPOSITORY VALIDATION")

    print("=" * 80)

    print()

    print(
        f"Errors   : {len(validator.errors)}"
    )

    print(
        f"Warnings : {len(validator.warnings)}"
    )

    print(
        f"Info      : {len(validator.info)}"
    )

    print()

    if validator.errors:

        print("ERRORS")

        print("-" * 40)

        for e in validator.errors:

            print(e)

        print()

    if validator.warnings:

        print("WARNINGS")

        print("-" * 40)

        for w in validator.warnings:

            print(w)

        print()

    print("STATISTICS")

    print("-" * 40)

    for x in validator.info:

        print(x)


##############################################################
# Main
##############################################################

def main():

    repository = load_json(
        FILES["repository"]
    )

    dependency = load_json(
        FILES["dependency"]
    )["edges"]

    hierarchy = load_json(
        FILES["hierarchy"]
    )

    methods = load_json(
        FILES["methods"]
    )

    callgraph = load_json(
        FILES["callgraph"]
    )["edges"]

    validate_repository_index(
        repository
    )

    validate_dependency_graph(
        dependency
    )

    validate_class_hierarchy(
        hierarchy
    )

    validate_method_index(
        methods
    )

    validate_call_graph(
        callgraph
    )

    validate_cross_refs(
        repository,
        methods,
        hierarchy,
        callgraph
    )

    print_summary()


if __name__ == "__main__":

    main()