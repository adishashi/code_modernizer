import re

from models import (
    PascalUnit,
    Class,
    Procedure
)

def extract_unit_name(
    ast_text: str
):

    match = re.search(
        r"\(moduleName\s*\n\s*\(identifier\)",
        ast_text
    )

    if not match:
        return None

    return match.group(0)

def extract_dependencies(
    ast_text: str
):

    deps = []

    uses_blocks = re.finditer(
        r"\(declUses",
        ast_text
    )

    for block in uses_blocks:
        deps.append(
            block.group(0)
        )

    return deps

def extract_classes(
    ast_text: str
):

    classes = []

    matches = re.finditer(
        r"\(declType",
        ast_text
    )

    for m in matches:

        classes.append(
            Class(
                name=m.group(0)
            )
        )

    return classes

def extract_procedures(
    ast_text: str
):

    procedures = []

    declarations = re.finditer(
        r"\(declProc",
        ast_text
    )

    for _ in declarations:

        procedures.append(
            Procedure(
                name="unknown",
                implementation=False
            )
        )

    implementations = re.finditer(
        r"\(defProc",
        ast_text
    )

    for _ in implementations:

        procedures.append(
            Procedure(
                name="unknown",
                implementation=True
            )
        )

    return procedures

def build_unit(
    file_path,
    ast_text
):

    unit = PascalUnit(
        file_path=str(file_path)
    )

    unit.unit_name = (
        extract_unit_name(
            ast_text
        )
    )

    unit.dependencies = (
        extract_dependencies(
            ast_text
        )
    )

    unit.classes = (
        extract_classes(
            ast_text
        )
    )

    unit.procedures = (
        extract_procedures(
            ast_text
        )
    )

    return unit