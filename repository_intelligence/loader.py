"""
loader.py

Loads all repository indices into memory.

This module is intentionally lightweight. It performs:
    - JSON loading
    - Schema normalization
    - Basic sanity checks

All repository querying should be implemented elsewhere.
"""

from pathlib import Path
import json


class RepositoryData:

    def __init__(self):

        self.repository_index = []

        self.dependency_graph = []

        self.class_hierarchy = []

        self.method_index = []

        self.call_graph = []

        self.statistics = {}


class RepositoryLoader:

    def __init__(self, output_directory):

        self.output_directory = Path(output_directory)

    ###########################################################################
    # Helpers
    ###########################################################################

    def _load_json(self, filename):

        path = self.output_directory / filename

        if not path.exists():

            raise FileNotFoundError(path)

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as fp:

            return json.load(fp)

    def _extract_edges(self, data):

        """
        Some generated JSON files are stored as:

            {
                "statistics": ...,
                "edges": [...]
            }

        while others are simply lists.

        Normalize them here.
        """

        if isinstance(data, list):

            return data

        if isinstance(data, dict):

            if "edges" in data:

                return data["edges"]

        raise ValueError(
            "Unsupported graph schema."
        )

    ###########################################################################
    # Public API
    ###########################################################################

    def load(self):

        repo = RepositoryData()

        #
        # Repository index
        #

        repo.repository_index = self._load_json(
            "repository_index.json"
        )

        #
        # Dependency graph
        #

        dependency = self._load_json(
            "dependency_graph.json"
        )

        repo.dependency_graph = (
            self._extract_edges(
                dependency
            )
        )

        if isinstance(dependency, dict):

            repo.statistics[
                "dependency"
            ] = dependency.get(
                "statistics",
                {}
            )

        #
        # Class hierarchy
        #

        hierarchy = self._load_json(
            "class_hierarchy.json"
        )

        repo.class_hierarchy = (
            self._extract_edges(
                hierarchy
            )
            if isinstance(hierarchy, dict)
            else hierarchy
        )

        if isinstance(hierarchy, dict):

            repo.statistics[
                "hierarchy"
            ] = hierarchy.get(
                "statistics",
                {}
            )

        #
        # Method index
        #

        repo.method_index = self._load_json(
            "method_index.json"
        )

        #
        # Call graph
        #

        call_graph = self._load_json(
            "call_graph_dedup.json"
        )

        repo.call_graph = (
            self._extract_edges(
                call_graph
            )
        )

        if isinstance(call_graph, dict):

            repo.statistics[
                "call_graph"
            ] = call_graph.get(
                "statistics",
                {}
            )

        return repo


###########################################################################
# Convenience Function
###########################################################################

def load_repository(output_directory):

    loader = RepositoryLoader(
        output_directory
    )

    return loader.load()


###########################################################################
# Standalone Test
###########################################################################

if __name__ == "__main__":

    OUTPUT = (
        r"C:\Users\Adity\OneDrive\Desktop"
        r"\Persistent Project\output"
    )

    repository = load_repository(
        OUTPUT
    )

    print()

    print("=" * 70)

    print("Repository Loaded")

    print("=" * 70)

    print()

    print(
        "Units:",
        len(repository.repository_index)
    )

    print(
        "Dependency Edges:",
        len(repository.dependency_graph)
    )

    print(
        "Classes:",
        len(repository.class_hierarchy)
    )

    print(
        "Methods:",
        len(repository.method_index)
    )

    print(
        "Call Edges:",
        len(repository.call_graph)
    )