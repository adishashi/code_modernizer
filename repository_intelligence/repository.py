"""
repository.py

Central repository object.

This class owns every lookup table used by the intelligence layer.
No module outside loader.py should access generated JSON files directly.
"""

from collections import defaultdict, deque

try:
    from .loader import RepositoryData
except ImportError:
    from loader import RepositoryData


def _normalize(value):
    if value is None:
        return ""

    return str(value).casefold()


class Repository:

    ###########################################################################
    # Construction
    ###########################################################################

    def __init__(
        self,
        repository_data: RepositoryData
    ):

        self.data = repository_data

        #
        # Units and files
        #

        self.units = {}
        self.units_by_lower_name = {}

        self.files = {}
        self.units_by_file = {}
        self.files_by_lower_path = {}

        #
        # Classes
        #

        self.classes = {}
        self.classes_by_name = defaultdict(list)
        self.classes_by_lower_name = defaultdict(list)
        self.classes_by_unit = defaultdict(list)

        #
        # Fields
        #

        self.fields = []
        self.fields_by_name = defaultdict(list)
        self.fields_by_class = defaultdict(list)
        self.fields_by_unit = defaultdict(list)

        #
        # Methods
        #

        self.methods = []
        self.methods_by_name = defaultdict(list)
        self.methods_by_lower_name = defaultdict(list)
        self.methods_by_class = defaultdict(list)
        self.methods_by_unit = defaultdict(list)
        self.methods_by_qualified_name = defaultdict(list)

        #
        # Dependency Graph
        #

        self.dependencies = defaultdict(set)
        self.reverse_dependencies = defaultdict(set)

        #
        # Inheritance
        #

        self.parent_map = {}
        self.children_map = defaultdict(list)
        self.inheritance_units = defaultdict(set)

        #
        # Call Graph
        #

        self.callers = defaultdict(set)
        self.callees = defaultdict(set)
        self.call_edges_by_caller = defaultdict(list)
        self.call_edges_by_callee = defaultdict(list)

        self._build_units()
        self._build_classes()
        self._build_fields()
        self._build_methods()
        self._build_dependency_graph()
        self._build_inheritance()
        self._build_call_graph()

    ###########################################################################
    # Build Helpers
    ###########################################################################

    def _build_units(self):

        for unit in self.data.repository_index:

            unit_name = unit.get("unit")

            if not unit_name:
                continue

            source_file = unit.get("file")

            self.units[unit_name] = unit
            self.units_by_lower_name[_normalize(unit_name)] = unit_name
            self.files[unit_name] = source_file

            if source_file:
                self.units_by_file[source_file] = unit_name
                self.files_by_lower_path[_normalize(source_file)] = unit_name

    def _build_classes(self):

        for unit in self.data.repository_index:

            unit_name = unit.get("unit")

            for cls in unit.get("classes", []):

                class_name = cls.get("name")

                if not class_name:
                    continue

                class_record = dict(cls)
                class_record.setdefault("unit", unit_name)
                class_record.setdefault("file", unit.get("file"))

                self.classes.setdefault(class_name, class_record)
                self.classes_by_name[class_name].append(class_record)
                self.classes_by_lower_name[_normalize(class_name)].append(
                    class_record
                )
                self.classes_by_unit[unit_name].append(class_record)

    def _build_fields(self):

        for unit in self.data.repository_index:

            unit_name = unit.get("unit")

            for field in unit.get("fields", []):

                field_record = dict(field)
                field_record.setdefault("unit", unit_name)
                field_record.setdefault("file", unit.get("file"))

                self.fields.append(field_record)

                field_name = field_record.get("name")
                class_name = field_record.get("class")

                if field_name:
                    self.fields_by_name[field_name].append(field_record)

                if class_name:
                    self.fields_by_class[class_name].append(field_record)

                if unit_name:
                    self.fields_by_unit[unit_name].append(field_record)

    def _build_methods(self):

        for method in self.data.method_index:

            method_record = dict(method)
            self.methods.append(method_record)

            method_name = method_record.get("method")
            class_name = method_record.get("class")
            unit_name = method_record.get("unit")

            if method_name:
                self.methods_by_name[method_name].append(method_record)
                self.methods_by_lower_name[_normalize(method_name)].append(
                    method_record
                )

            if class_name:
                self.methods_by_class[class_name].append(method_record)
                qualified_name = f"{class_name}.{method_name}"
                self.methods_by_qualified_name[qualified_name].append(
                    method_record
                )
                self.methods_by_qualified_name[
                    _normalize(qualified_name)
                ].append(method_record)

            if unit_name:
                self.methods_by_unit[unit_name].append(method_record)

    def _build_dependency_graph(self):

        for edge in self.data.dependency_graph:

            source = edge.get("source")
            target = edge.get("target")

            if not source or not target:
                continue

            self.dependencies[source].add(target)
            self.reverse_dependencies[target].add(source)

    def _build_inheritance(self):

        for edge in self.data.class_hierarchy:

            child = edge.get("child")
            parent = edge.get("parent")
            unit_name = edge.get("unit")

            if not child or not parent:
                continue

            self.parent_map[child] = parent
            self.children_map[parent].append(child)

            if unit_name:
                self.inheritance_units[(child, parent)].add(unit_name)

    def _build_call_graph(self):

        for edge in self.data.call_graph:

            caller = edge.get("caller")
            callee = edge.get("callee")

            if not caller or not callee:
                continue

            self.callers[callee].add(caller)
            self.callees[caller].add(callee)
            self.call_edges_by_caller[caller].append(edge)
            self.call_edges_by_callee[callee].append(edge)

    ###########################################################################
    # Lookup API
    ###########################################################################

    def list_units(self):
        return sorted(self.units)

    def list_classes(self):
        return sorted(self.classes_by_name)

    def list_methods(self):
        return list(self.methods)

    def find_unit(
        self,
        unit_name
    ):

        exact = self.units.get(unit_name)

        if exact:
            return exact

        canonical = self.units_by_lower_name.get(_normalize(unit_name))

        if canonical:
            return self.units.get(canonical)

        return None

    def find_file(
        self,
        path_or_unit
    ):

        if path_or_unit in self.files:
            return self.files[path_or_unit]

        unit_name = self.units_by_file.get(path_or_unit)

        if unit_name:
            return self.units.get(unit_name)

        unit_name = self.files_by_lower_path.get(_normalize(path_or_unit))

        if unit_name:
            return self.units.get(unit_name)

        unit = self.find_unit(path_or_unit)

        if unit:
            return unit.get("file")

        return None

    def find_class(
        self,
        class_name
    ):

        matches = self.find_classes(class_name)

        if matches:
            return matches[0]

        return None

    def find_classes(
        self,
        class_name,
        unit_name=None
    ):

        matches = list(
            self.classes_by_name.get(class_name)
            or self.classes_by_lower_name.get(_normalize(class_name), [])
        )

        if unit_name:
            matches = [
                cls for cls in matches
                if cls.get("unit") == unit_name
            ]

        return matches

    def find_method(
        self,
        method_name
    ):

        return self.find_methods(method_name)

    def find_methods(
        self,
        method_name,
        class_name=None,
        unit_name=None
    ):

        matches = []

        if "." in str(method_name):
            matches = list(
                self.methods_by_qualified_name.get(method_name)
                or self.methods_by_qualified_name.get(
                    _normalize(method_name),
                    []
                )
            )
        else:
            matches = list(
                self.methods_by_name.get(method_name)
                or self.methods_by_lower_name.get(_normalize(method_name), [])
            )

        if class_name:
            matches = [
                method for method in matches
                if method.get("class") == class_name
            ]

        if unit_name:
            matches = [
                method for method in matches
                if method.get("unit") == unit_name
            ]

        return matches

    ###########################################################################
    # Dependency API
    ###########################################################################

    def get_dependencies(
        self,
        unit_name
    ):

        return sorted(self.dependencies.get(unit_name, set()))

    def get_dependents(
        self,
        unit_name
    ):

        return sorted(self.reverse_dependencies.get(unit_name, set()))

    ###########################################################################
    # Inheritance API
    ###########################################################################

    def get_parent(
        self,
        class_name
    ):

        return self.parent_map.get(class_name)

    def get_children(
        self,
        class_name
    ):

        return sorted(self.children_map.get(class_name, []))

    ###########################################################################
    # Call Graph API
    ###########################################################################

    def get_callers(
        self,
        method
    ):

        return sorted(self.callers.get(method, set()))

    def get_callees(
        self,
        method
    ):

        return sorted(self.callees.get(method, set()))

    ###########################################################################
    # Search API
    ###########################################################################

    def search_symbols(
        self,
        query,
        symbol_types=None,
        limit=25
    ):

        try:
            from .search import RepositorySearch
        except ImportError:
            from search import RepositorySearch

        return RepositorySearch(self).search_symbols(
            query,
            symbol_types=symbol_types,
            limit=limit
        )

    ###########################################################################
    # Traversal Helpers
    ###########################################################################

    def breadth_first_walk(
        self,
        start,
        neighbour_map,
        max_depth=2
    ):

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
                results.append({
                    "node": neighbour,
                    "depth": depth + 1
                })
                queue.append((neighbour, depth + 1))

        return results

    ###########################################################################
    # Statistics
    ###########################################################################

    def statistics(self):

        return {
            "files": len(self.data.repository_index),
            "units": len(self.units),
            "classes": len(self.classes),
            "class_records": sum(
                len(matches)
                for matches in self.classes_by_name.values()
            ),
            "unique_class_names": len(self.classes_by_name),
            "fields": len(self.fields),
            "methods": len(self.methods),
            "dependency_edges": len(self.data.dependency_graph),
            "inheritance_edges": len(self.data.class_hierarchy),
            "call_edges": len(self.data.call_graph)
        }


###########################################################################
# Standalone Test
###########################################################################

if __name__ == "__main__":

    try:
        from .loader import load_repository
    except ImportError:
        from loader import load_repository

    repository = Repository(
        load_repository(
            r"C:\Users\Adity\OneDrive\Desktop\Persistent Project\output"
        )
    )

    print()
    print("=" * 70)
    print("Repository")
    print("=" * 70)
    print()

    for key, value in repository.statistics().items():
        print(f"{key:20}", value)

    print()
    print("Example Class:", repository.find_class("TFileSource"))
    print()
    print("CopyFile Methods:", len(repository.find_method("CopyFile")))
