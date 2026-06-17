class PascalVisitor:

    def __init__(self):
        self.count = 0

    def visit(self, node):

        self.count += 1

        method_name = f"visit_{node.type}"

        visitor = getattr(
            self,
            method_name,
            self.generic_visit
        )

        return visitor(node)

    def generic_visit(self, node):

        for child in node.children:
            self.visit(child)