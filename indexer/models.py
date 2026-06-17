from dataclasses import dataclass, field

@dataclass
class Procedure:
    name: str
    implementation: bool = False

@dataclass
class Class:
    name: str

@dataclass
class PascalUnit:

    file_path: str
    unit_name: str | None = None

    dependencies: list[str] = field(default_factory=list)

    classes: list[Class] = field(default_factory=list)

    procedures: list[Procedure] = field(default_factory=list)