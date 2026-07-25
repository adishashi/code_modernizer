"""
graph_api.py

Graph traversal APIs for repository intelligence.

This module works from lookup tables owned by Repository. It does not perform
symbol search or semantic retrieval.
"""

from collections import deque


class GraphAPI:

    def __init__(self, repository):
        self.repository = repository

    ###########################################################################
    # Dependency Graph
    ###########################################################################

    def dependencies(self, unit_name):
        return self.repository.get_dependencies(unit_name)

    def dependents(self, unit_name):
        return self.repository.get_dependents(unit_name)

    def transitive_dependencies(self, unit_name, max_depth=3):
        return self._walk(
            unit_name,
            self.repository.dependencies,
            max_depth=max_depth
        )

    def transitive_dependents(self, unit_name, max_depth=3):
        return self._walk(
            unit_name,
            self.repository.reverse_dependencies,
            max_depth=max_depth
        )

    ###########################################################################
    # Inheritance Graph
    ###########################################################################

    def parent(self, class_name):
        return self.repository.get_parent(class_name)

    def children(self, class_name):
        return self.repository.get_children(class_name)

    def ancestors(self, class_name, max_depth=20):
        results = []
        current = class_name
        depth = 0
        seen = {class_name}

        while depth < max_depth:
            parent = self.repository.get_parent(current)

            if not parent or parent in seen:
                break

            depth += 1
            seen.add(parent)
            results.append({
                "class": parent,
                "depth": depth
            })
            current = parent

        return results

    def descendants(self, class_name, max_depth=5):
        return [
            {
                "class": item["node"],
                "depth": item["depth"]
            }
            for item in self._walk(
                class_name,
                self.repository.children_map,
                max_depth=max_depth
            )
        ]

    ###########################################################################
    # Call Graph
    ###########################################################################

    def callers(self, method_name):
        return self.repository.get_callers(method_name)

    def callees(self, method_name):
        return self.repository.get_callees(method_name)

    def transitive_callers(self, method_name, max_depth=3):
        return self._walk(
            method_name,
            self.repository.callers,
            max_depth=max_depth
        )

    def transitive_callees(self, method_name, max_depth=3):
        return self._walk(
            method_name,
            self.repository.callees,
            max_depth=max_depth
        )

    def execution_paths(
        self,
        start_method,
        target_method,
        max_depth=5,
        limit=10
    ):
        if start_method == target_method:
            return [[start_method]]

        paths = []
        queue = deque([(start_method, [start_method])])

        while queue and len(paths) < limit:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            for callee in sorted(self.repository.callees.get(current, [])):
                if callee in path:
                    continue

                next_path = path + [callee]

                if callee == target_method:
                    paths.append(next_path)
                else:
                    queue.append((callee, next_path))

        return paths

    ###########################################################################
    # Impact
    ###########################################################################

    def impact_analysis(
        self,
        symbol,
        max_depth=2
    ):
        return {
            "symbol": symbol,
            "dependent_units": self.transitive_dependents(
                symbol,
                max_depth=max_depth
            ),
            "callers": self.transitive_callers(
                symbol,
                max_depth=max_depth
            ),
            "children": self.descendants(
                symbol,
                max_depth=max_depth
            )
        }

    ###########################################################################
    # Helpers
    ###########################################################################

    def _walk(self, start, neighbour_map, max_depth=3):
        visited = {start}
        results = []
        queue = deque([(start, 0)])

        while queue:
            current, depth = queue.popleft()

            if depth >= max_depth:
                continue

            for neighbour in sorted(neighbour_map.get(current, [])):
                if neighbour in visited:
                    continue

                visited.add(neighbour)
                next_depth = depth + 1
                results.append({
                    "node": neighbour,
                    "depth": next_depth
                })
                queue.append((neighbour, next_depth))

        return results
