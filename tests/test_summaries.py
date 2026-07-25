"""
Tests for Stage 4.4 repository summaries.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    Repository,
    RepositorySummarizer,
    generate_repository_summaries,
    load_repository
)


class SummaryTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repository = Repository(
            load_repository(ROOT / "output")
        )
        cls.summarizer = RepositorySummarizer(cls.repository)


class RepositorySummaryTests(SummaryTestCase):

    def test_builds_expected_summary_counts(self):
        method_summaries = self.summarizer.build_summaries("method")
        class_summaries = self.summarizer.build_summaries("class")
        unit_summaries = self.summarizer.build_summaries("unit")
        subsystem_summaries = self.summarizer.build_summaries("subsystem")
        architecture_summaries = self.summarizer.build_summaries(
            "architecture"
        )

        self.assertEqual(12093, len(method_summaries))
        self.assertEqual(2508, len(class_summaries))
        self.assertEqual(804, len(unit_summaries))
        self.assertEqual(183, len(subsystem_summaries))
        self.assertEqual(1, len(architecture_summaries))

    def test_unit_summary_contains_metrics_and_related_symbols(self):
        unit_summary = [
            summary for summary in self.summarizer.build_summaries("unit")
            if summary.name == "uFileSource"
        ][0]

        self.assertEqual("unit", unit_summary.summary_type)
        self.assertIn("uFileSource is a Pascal unit", unit_summary.summary)
        self.assertGreater(unit_summary.metrics["dependency_count"], 0)
        self.assertIn("dependencies", unit_summary.related_symbols)

    def test_class_and_method_summaries_are_symbol_addressable(self):
        class_summary = [
            summary for summary in self.summarizer.build_summaries("class")
            if summary.name == "TFileSource"
            and summary.unit == "uFileSource"
        ][0]
        method_summary = [
            summary for summary in self.summarizer.build_summaries("method")
            if summary.method_name == "CopyFile"
            and summary.unit == "uFileSystemUtil"
        ][0]

        self.assertEqual("class", class_summary.summary_type)
        self.assertEqual("TFileSource", class_summary.class_name)
        self.assertEqual("method", method_summary.summary_type)
        self.assertEqual("CopyFile", method_summary.method_name)
        self.assertIn("static callees", method_summary.summary)

    def test_architecture_summary_captures_repository_scale(self):
        architecture = self.summarizer.build_summaries("architecture")[0]

        self.assertEqual("architecture", architecture.summary_type)
        self.assertEqual(12093, architecture.metrics["methods"])
        self.assertEqual(42309, architecture.metrics["call_edges"])
        self.assertIn("top_dependency_units", architecture.related_symbols)

    def test_summary_artifact_writer_outputs_manifest_and_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = generate_repository_summaries(
                self.repository,
                temp_dir,
                summary_types=["unit", "architecture"]
            )
            temp_path = Path(temp_dir)
            summaries_path = temp_path / "summaries.jsonl"
            manifest_path = temp_path / "manifest.json"

            self.assertTrue(summaries_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertEqual(805, manifest["summary_count"])
            self.assertEqual(804, manifest["summary_counts"]["unit"])
            self.assertEqual(
                1,
                manifest["summary_counts"]["architecture"]
            )

            with summaries_path.open("r", encoding="utf-8") as fp:
                first = json.loads(fp.readline())

            self.assertIn("summary_id", first)
            self.assertIn("summary", first)
            self.assertIn("metrics", first)


if __name__ == "__main__":
    unittest.main()
