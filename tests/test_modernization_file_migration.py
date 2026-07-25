"""
Tests for file-by-file modernization planning.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    FileMigrationPlanner,
    Repository,
    build_file_migration_plan,
    load_repository
)


class FileMigrationPlannerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(load_repository(ROOT / "output"))

    def test_plans_single_pascal_unit_as_file_migration_job(self):
        planner = FileMigrationPlanner(
            self.repository,
            source_root=ROOT / "doublecmd"
        )
        plan = planner.build_plan(
            units=["uFileSource"]
        )

        self.assertEqual(1, plan["statistics"]["job_count"])
        job = plan["jobs"][0]
        self.assertEqual("uFileSource", job["source"]["unit"])
        self.assertEqual(
            "src\\filesources\\ufilesource.pas",
            job["source"]["file"]
        )
        self.assertEqual(
            "org.doublecmd.filesources",
            job["target"]["package"]
        )
        self.assertEqual(
            "org/doublecmd/filesources/FileSource.java",
            job["target"]["file_hint"]
        )
        self.assertIn("TFileSource", job["symbols"]["classes"])
        self.assertGreater(job["symbols"]["method_count"], 0)
        self.assertEqual("dependency", job["ordering"]["mode"])
        self.assertEqual(1, job["ordering"]["position"])
        self.assertTrue(job["ordering"]["dependency_ready"])
        self.assertGreater(
            len(job["ordering"]["external_dependencies"]),
            0
        )
        self.assertNotIn("source_extraction", job)

    def test_full_source_extraction_mode_includes_complete_unit_source(self):
        planner = FileMigrationPlanner(
            self.repository,
            source_root=ROOT / "doublecmd"
        )
        plan = planner.build_plan(
            units=["uFileSource"],
            include_source=True
        )
        job = plan["jobs"][0]
        source = job["source_extraction"]

        self.assertTrue(source["available"])
        self.assertEqual("full_unit", source["extraction_kind"])
        self.assertFalse(source["truncated"])
        self.assertGreater(source["line_count"], 500)
        self.assertEqual(source["character_count"], len(source["source"]))
        self.assertIn("unit uFileSource;", source["source"])
        self.assertIn("implementation", source["source"])
        self.assertTrue(plan["statistics"]["source_included"])
        self.assertEqual(1, plan["statistics"]["source_available_count"])

    def test_include_and_exclude_filters_match_source_paths(self):
        planner = FileMigrationPlanner(self.repository)
        plan = planner.build_plan(
            include=["src/filesources/*.pas"],
            exclude=["*/wfxplugin/*"],
            limit=10,
            order="source"
        )

        self.assertGreater(plan["statistics"]["job_count"], 0)

        for job in plan["jobs"]:
            source_file = job["source"]["file"].replace("\\", "/")
            self.assertTrue(source_file.startswith("src/filesources/"))
            self.assertNotIn("/wfxplugin/", source_file)

    def test_reserved_source_path_segments_are_safe_java_packages(self):
        planner = FileMigrationPlanner(self.repository)
        plan = planner.build_plan(units=["BTypes"])
        job = plan["jobs"][0]

        self.assertEqual(
            "org.doublecmd.components.kascrypt.hashes.private_",
            job["target"]["package"]
        )
        self.assertEqual(
            "org/doublecmd/components/kascrypt/hashes/private_/BTypes.java",
            job["target"]["file_hint"]
        )

    def test_dependency_order_places_dependencies_before_dependents(self):
        planner = FileMigrationPlanner(self.repository)
        plan = planner.build_plan(
            units=["uFileSource", "uWfxPluginFileSource"]
        )
        units = [
            job["source"]["unit"]
            for job in plan["jobs"]
        ]

        self.assertLess(
            units.index("uFileSource"),
            units.index("uWfxPluginFileSource")
        )
        self.assertEqual(
            ["uFileSource", "uWfxPluginFileSource"],
            plan["dependency_ordering"]["ordered_units"]
        )
        self.assertEqual(1, plan["dependency_ordering"]["internal_edge_count"])
        self.assertEqual(0, plan["dependency_ordering"]["cycle_count"])
        self.assertEqual(
            ["uFileSource"],
            plan["jobs"][1]["ordering"]["prior_internal_dependencies"]
        )
        self.assertTrue(plan["jobs"][1]["ordering"]["dependency_ready"])

    def test_source_order_reports_later_internal_dependencies(self):
        planner = FileMigrationPlanner(self.repository)
        plan = planner.build_plan(
            units=["uWfxPluginFileSource", "uFileSource"],
            order="source"
        )
        units = [
            job["source"]["unit"]
            for job in plan["jobs"]
        ]

        self.assertEqual("source", plan["dependency_ordering"]["mode"])
        self.assertEqual(1, plan["dependency_ordering"]["internal_edge_count"])

        dependent_job = next(
            job
            for job in plan["jobs"]
            if job["source"]["unit"] == "uWfxPluginFileSource"
        )

        if units.index("uWfxPluginFileSource") < units.index("uFileSource"):
            self.assertEqual(
                ["uFileSource"],
                dependent_job["ordering"]["later_internal_dependencies"]
            )
            self.assertFalse(dependent_job["ordering"]["dependency_ready"])

    def test_convenience_helper_builds_plan(self):
        plan = build_file_migration_plan(
            self.repository,
            units=["uFileSource"]
        )

        self.assertEqual("file_migration_plan", plan["purpose"])
        self.assertEqual(1, len(plan["jobs"]))

    def test_cli_outputs_json_plan(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "repository_intelligence.modernization.file_migration",
                "--input",
                str(ROOT / "output"),
                "--units",
                "uFileSource",
                "--include-source",
                "--json"
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT
        )
        plan = json.loads(completed.stdout)

        self.assertEqual(1, plan["statistics"]["job_count"])
        self.assertEqual("uFileSource", plan["jobs"][0]["source"]["unit"])
        self.assertTrue(plan["jobs"][0]["source_extraction"]["available"])


if __name__ == "__main__":
    unittest.main()
