import json


class RepositoryGraph:

    def __init__(self):

        self.units = []

    def add(
        self,
        unit
    ):

        self.units.append(unit)

    def export(
        self,
        path
    ):

        output = []

        for unit in self.units:

            output.append(
                {
                    "file":
                        unit.file_path,

                    "unit":
                        unit.unit_name,

                    "dependencies":
                        unit.dependencies,

                    "classes":
                        [
                            c.name
                            for c
                            in unit.classes
                        ],

                    "procedures":
                        [
                            p.name
                            for p
                            in unit.procedures
                        ]
                }
            )

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                output,
                f,
                indent=2
            )