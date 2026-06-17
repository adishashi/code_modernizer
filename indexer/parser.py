from pathlib import Path
from ctypes import cdll, c_void_p

from tree_sitter import Language, Parser


class TreeSitterParser:

    def __init__(self):

        # Adjust if your DLL lives elsewhere
        dll_path = Path(
            r"C:\Users\Adity\OneDrive\Desktop\Persistent Project"
            r"\build\pascal.dll"
        )

        if not dll_path.exists():
            raise FileNotFoundError(
                f"Pascal DLL not found: {dll_path}"
            )

        self.dll = cdll.LoadLibrary(str(dll_path))

        self.dll.tree_sitter_pascal.restype = c_void_p

        language_ptr = self.dll.tree_sitter_pascal()

        # Works in tree-sitter 0.25.x
        self.language = Language(language_ptr)

        self.parser = Parser(self.language)

    def parse(self, file_path: Path):

        if not file_path.exists():
            raise FileNotFoundError(
                f"Source file not found: {file_path}"
            )

        source = file_path.read_bytes()

        tree = self.parser.parse(source)

        return tree, source