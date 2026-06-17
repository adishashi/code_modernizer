from visitors.base_visitor import PascalVisitor

def node_text(node, source):

        return source[
            node.start_byte:
            node.end_byte
        ].decode("utf-8")

class RepositoryVisitor(PascalVisitor):

    def __init__(self, source):

        super().__init__()

        self.source = source

        self.unit_name = None

        self.dependencies = []

        self.classes = []

        self.fields = []

        self.methods = []

        self.count = 1
    
    def visit_moduleName(self, node):

        if self.unit_name:
            return

        identifier = None

        for child in node.children:

            if child.type == "identifier":
                identifier = child
                break

        if identifier:

            self.unit_name = node_text(
                identifier,
                self.source
            )

    def visit_declUses(self, node):

        for child in node.children:
        
            if child.type == "moduleName":

                for grandchild in child.children:

                    if grandchild.type == "identifier":

                        self.dependencies.append(
                            node_text(
                                grandchild,
                                self.source
                            )
                        )

    def visit_declProc(self, node):

        name_node = node.child_by_field_name(
            "name"
        )

        if name_node:

            method_name = node_text(
                name_node,
                self.source
            )

            kind = "procedure"

            for child in node.children:

                if child.type == "kConstructor":
                    kind = "constructor"

                elif child.type == "kFunction":
                    kind = "function"

            self.methods.append(
                {
                    "class": None,
                    "name": method_name,
                    "kind": kind,
                    "definition": False
                }
            )

        self.generic_visit(node)

    def visit_declType(self, node):

        name_node = node.child_by_field_name(
            "name"
        )

        type_node = node.child_by_field_name(
            "type"
        )

        if (
            name_node and
            type_node and
            type_node.type == "declClass"
        ):

            class_name = node_text(
                name_node,
                self.source
            )

            parent_name = None

            for child in type_node.children:

                if child.type == "typeref":

                    for grandchild in child.children:

                        if grandchild.type == "identifier":

                            parent_name = node_text(
                                grandchild,
                                self.source
                            )

                            break

                    break

            self.classes.append(
                {
                    "name": class_name,
                    "parent": parent_name
                }
            )

        self.generic_visit(node)

    def visit_defProc(self, node):

        header = node.child_by_field_name(
            "header"
        )

        if not header:
            return

        name = header.child_by_field_name(
            "name"
        )

        if not name:
            return

        if name.type == "genericDot":

            lhs = name.child_by_field_name(
                "lhs"
            )

            rhs = name.child_by_field_name(
                "rhs"
            )

            self.methods.append(
                {
                    "class": node_text(
                        lhs,
                        self.source
                    ),

                    "name": node_text(
                        rhs,
                        self.source
                    ),

                    "kind": "procedure",

                    "definition": True
                }
            )

    def visit_declField(self, node):

        name_node = node.child_by_field_name(
            "name"
        )

        type_node = node.child_by_field_name(
            "type"
        )

        if not name_node:
            return

        field_name = node_text(
            name_node,
            self.source
        )

        field_type = None

        if type_node:

            field_type = node_text(
                type_node,
                self.source
            )

        self.fields.append(
            {
                "name": field_name,
                "type": field_type
            }
        )

        self.generic_visit(node)
    