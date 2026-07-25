import json
from pathlib import Path

from parser import TreeSitterParser
from visitors.base_visitor import PascalVisitor
from utils import node_text

from collections import Counter


PROJECT_ROOT = Path(
    r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
)

SOURCE_ROOT = (
    PROJECT_ROOT /
    "doublecmd"
)

OUTPUT_DIR = (
    PROJECT_ROOT /
    "output"
)

METHOD_INDEX_FILE = (
    OUTPUT_DIR /
    "method_index.json"
)

CALL_GRAPH_RAW_FILE = (
    OUTPUT_DIR /
    "call_graph_raw.json"
)

CALL_GRAPH_DEDUP_FILE = (
    OUTPUT_DIR /
    "call_graph_dedup.json"
)

CALL_GRAPH_WEIGHTED_FILE = (
    OUTPUT_DIR /
    "call_graph_weighted.json"
)

IGNORE_CALLS = {
    "TObject",
    "UIntPtr",
    "Integer",
    "String",
    "Boolean",
    "Pointer",
    "AnsiString",
    "WideString",
    "UnicodeString",
    "Cardinal",
    "LongInt",
    "Byte",
    "Word",
    "NativeUInt",
    "NativeInt"
}


class CallGraphVisitor(PascalVisitor):

    def __init__(self, source):

        super().__init__()

        self.source = source

        self.current_unit = None

        self.current_class = None

        self.current_method = None

        self.calls = []

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def visit_unit(self, node):

        module_node = None

        for child in node.children:

            if child.type == "moduleName":

                module_node = child
                break

        if module_node:

            self.current_unit = node_text(
                module_node,
                self.source
            )

        self.generic_visit(node)

    def extract_callee_name(
        self,
        node
    ):

        if node.type == "identifier":

            return node_text(
                node,
                self.source
            )

        if node.type == "exprDot":

            identifiers = []

            def collect(n):

                if n.type == "identifier":

                    identifiers.append(
                        node_text(
                            n,
                            self.source
                        )
                    )

                for child in n.children:

                    collect(child)

            collect(node)

            if identifiers:

                return identifiers[-1]

        return None

    # --------------------------------------------------
    # Method Tracking
    # --------------------------------------------------

    

    def visit_defProc(
        self,
        node
    ):

        old_method = (
            self.current_method
        )

        old_class = (
            self.current_class
        )

        header = (
            node.child_by_field_name(
                "header"
            )
        )

        if header:

            name_node = (
                header.child_by_field_name(
                    "name"
                )
            )

            if name_node:

            #
            # Class method
            #

                if (
                    name_node.type
                    ==
                    "genericDot"
                ):

                    lhs = (
                        name_node.child_by_field_name(
                            "lhs"
                        )
                    )

                    rhs = (
                        name_node.child_by_field_name(
                            "rhs"
                        )
                    )

                    if lhs and rhs:

                        self.current_class = (
                            node_text(
                                lhs,
                                self.source
                            )
                        )

                        method_name = (
                            node_text(
                                rhs,
                                self.source
                            )
                        )

                        self.current_method = (
                            f"{self.current_class}."
                            f"{method_name}"
                        )

            #
            # Global procedure
            #

                else:

                    self.current_class = None

                    self.current_method = (
                        node_text(
                            name_node,
                            self.source
                        )
                    )

        self.generic_visit(node)

        self.current_method = (
            old_method
        )

        self.current_class = (
            old_class
        )

    # --------------------------------------------------
    # Call Extraction
    # --------------------------------------------------

    def visit_exprCall(
        self,
        node
    ):

        if not self.current_method:

            self.generic_visit(node)
            return

        if not node.children:

            self.generic_visit(node)
            return

        target = node.children[0]

        callee = (
            self.extract_callee_name(
                target
            )
        )

        if (
            callee
            and
            callee
            not in IGNORE_CALLS
        ):

            self.calls.append(
                {
                    "caller":
                        self.current_method,

                    "caller_class":
                        self.current_class,

                    "caller_unit":
                        self.current_unit,

                    "callee":
                        callee
                }   
            )

        self.generic_visit(node)


# ======================================================
# Repository Processing
# ======================================================

def process_file(
    parser,
    pas_file
):

    try:

        tree, source = parser.parse(
            pas_file
        )

        visitor = (
            CallGraphVisitor(
                source
            )
        )

        visitor.visit(
            tree.root_node
        )

        return visitor.calls

    except Exception as ex:

        print(
            f"ERROR: {pas_file}"
        )

        print(ex)

        return []


# ======================================================
# Statistics
# ======================================================

def build_statistics(
    raw_edges,
    dedup_edges,
    weighted_edges
):

    callers = set()
    callees = set()

    for edge in dedup_edges:

        callers.add(
            edge["caller"]
        )

        callees.add(
            edge["callee"]
        )

    duplicate_count = (
        len(raw_edges)
        -
        len(dedup_edges)
    )

    return {

        "raw_call_edges":
            len(raw_edges),

        "unique_call_edges":
            len(dedup_edges),

        "duplicate_edges":
            duplicate_count,

        "duplicate_ratio":
            round(
                duplicate_count /
                max(
                    1,
                    len(raw_edges)
                ),
                4
            ),

        "unique_callers":
            len(callers),

        "unique_callees":
            len(callees)
    }

def load_defined_methods():

    with open(
        METHOD_INDEX_FILE,
        "r",
        encoding="utf-8"
    ) as fp:

        data = json.load(fp)

    methods = set()

    for entry in data:

        name = entry.get(
            "method"
        )

        if name:

            methods.add(name)

    return methods

def build_graph_variants(raw_edges):

    unique_edges = set()

    edge_counter = Counter()

    for edge in raw_edges:

        key = (
            edge["caller"],
            edge["caller_class"],
            edge["caller_unit"],
            edge["callee"]
        )

        unique_edges.add(key)

        edge_counter[key] += 1

    dedup_edges = [
        {
            "caller":
                caller,

            "caller_class":
                caller_class,

            "caller_unit":
                caller_unit,

            "callee":
                callee
        }

        for (
            caller,
            caller_class,
            caller_unit,
            callee
        )
        in sorted(unique_edges, key=lambda x: (
            x[0] or "",
            x[1] or "",
            x[2] or "",
            x[3] or ""
        ))
    ]

    weighted_edges = [
        {
            "caller": caller,
            "caller_class": caller_class,
            "caller_unit": caller_unit,
            "callee": callee,
            "count": count
        }
        for (caller, caller_class, caller_unit, callee), count
        in edge_counter.items()
    ]

    return (
        dedup_edges,
        weighted_edges
    )

# ======================================================
# Main
# ======================================================

def main():

    parser = TreeSitterParser()

    pas_files = list(
        SOURCE_ROOT.rglob(
            "*.pas"
        )
    )

    print(
        f"Found "
        f"{len(pas_files)} "
        f"Pascal files"
    )

    all_calls = []

    for index, pas_file in enumerate(
        pas_files,
        start=1
    ):

        print(
            f"[{index}/{len(pas_files)}] "
            f"{pas_file.name}"
        )

        calls = process_file(
            parser,
            pas_file
        )

        all_calls.extend(
            calls
        )

    dedup_edges, weighted_edges = (
        build_graph_variants(
            all_calls
        )
    )

    defined_methods = (
    load_defined_methods()
)

    resolvable = 0

    unresolvable = 0

    unresolved_counter = Counter()

    for edge in dedup_edges:

        if (
            edge["callee"]
            in
            defined_methods
        ):

            resolvable += 1

        else:

            unresolvable += 1
            unresolved_counter[edge["callee"]] += 1

    print()

    print("TOP UNRESOLVED")

    for name, count in (
        unresolved_counter
        .most_common(100)
    ):

        print(
            count,
            name
        )

    print()
    print("=" * 80)

    print(
        f"Resolvable Edges: "
        f"{resolvable}"
    )

    print(
        f"Unresolvable Edges: "
        f"{unresolvable}"
    )

    print(
        f"Resolution Rate: "
        f"{resolvable / max(1, len(dedup_edges)):.2%}"
    )

    print("=" * 80)

    print()
    print("=" * 80)

    callee_counter = Counter()

    for edge in dedup_edges:
        callee_counter[
            edge["callee"]
        ] += 1

    for name, count in (
        callee_counter.most_common(100)
    ):
        print(
            count,
            name
        )

    caller_counter = Counter()

    for edge in dedup_edges:
        caller_counter[edge["caller"]] += 1

    print(caller_counter.most_common(50))


    stats = build_statistics(
        all_calls,
        dedup_edges,
        weighted_edges
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        CALL_GRAPH_RAW_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            {
                "statistics": stats,
                "edges": all_calls
            },
            fp,
            indent=4
        )


    with open(
        CALL_GRAPH_DEDUP_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            {
                "statistics": stats,
                "edges": dedup_edges
            },
            fp,
            indent=4
        )


    with open(
        CALL_GRAPH_WEIGHTED_FILE,
        "w",
        encoding="utf-8"
    ) as fp:

        json.dump(
            {
                "statistics": stats,
                "edges": weighted_edges
            },
            fp,
            indent=4
        )

    print()
    print("=" * 80)

    print(
        f"Raw Call Edges: "
        f"{stats['raw_call_edges']}"
    )

    print(
        f"Unique Call Edges: "
        f"{stats['unique_call_edges']}"
    )

    print(
        f"Duplicate Edges: "
        f"{stats['duplicate_edges']}"
    )

    print(
        f"Duplicate Ratio: "
        f"{stats['duplicate_ratio']:.2%}"
    )

    print(
        f"Unique Callers: "
        f"{stats['unique_callers']}"
    )

    print(
        f"Unique Callees: "
        f"{stats['unique_callees']}"
    )

    print("=" * 80)

    print()

if __name__ == "__main__":

    main()