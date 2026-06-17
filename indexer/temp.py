# from pathlib import Path

# from parser import TreeSitterParser
# from visitors.repository_visitor import RepositoryVisitor

# TEST_FILE = Path(
#     r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
#     r"\doublecmd\src\fchecksumcalc.pas"
# )

# parser = TreeSitterParser()

# ast = parser.parse(TEST_FILE)

# visitor = RepositoryVisitor(ast)

# visitor.visit_root()

# print("\n=== RESULTS ===")
# print("Unit:")
# print(visitor.unit_name)

# print("\nDependencies:")
# print(visitor.dependencies)

# print("\nClasses:")
# print(visitor.classes)

# print("\nMethods:")
# print(visitor.methods)

from ctypes import cdll, c_void_p
from tree_sitter import Language, Parser
from pathlib import Path
from visitors.repository_visitor import RepositoryVisitor
from parser import TreeSitterParser

dll = cdll.LoadLibrary(r"build/pascal.dll")
dll.tree_sitter_pascal.restype = c_void_p

PASCAL = Language(dll.tree_sitter_pascal())

parser = TreeSitterParser()

tree, source = parser.parse(
    Path(
        r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
        r"\doublecmd\src\uglobs.pas"
    )
)

visitor = RepositoryVisitor(source)

visitor.visit(tree.root_node)

print(visitor.unit_name)
print(visitor.dependencies)
print(visitor.classes)
print(visitor.methods)
print(visitor.fields)