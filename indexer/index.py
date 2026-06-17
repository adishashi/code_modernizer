from pathlib import Path

from parser import TreeSitterParser

parser = TreeSitterParser()

ast = parser.parse(
    Path(
        r"...\fchecksumcalc.pas"
    )
)

print(ast[:1000])