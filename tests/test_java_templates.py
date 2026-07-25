"""
Tests for Java target design templates.
"""

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from repository_intelligence import (  # noqa: E402
    JavaDesignTemplate,
    JavaSharedSupportCatalog,
    JavaTargetDesignTemplates
)


class JavaTargetDesignTemplateTests(unittest.TestCase):

    def test_default_templates_cover_core_pascal_constructs(self):
        templates = JavaTargetDesignTemplates()
        template_ids = {
            template.template_id
            for template in templates.list_templates()
        }

        expected = {
            "pascal_unit_to_java_package",
            "pascal_class_to_java_class",
            "pascal_interface_to_java_interface",
            "pascal_record_to_java_value_type",
            "pascal_property_to_accessors",
            "pascal_event_to_listener",
            "pascal_exception_to_java_exception",
            "pascal_file_operations_to_java_nio",
            "pascal_set_to_java_enumset",
            "pascal_constructor_destructor_to_lifecycle",
            "pascal_routine_to_java_method",
            "global_routine_to_utility_method"
        }

        self.assertTrue(expected.issubset(template_ids))

    def test_template_records_are_structured_and_serializable(self):
        templates = JavaTargetDesignTemplates()
        template = templates.require("pascal_class_to_java_class")

        self.assertIsInstance(template, JavaDesignTemplate)
        record = template.to_dict()
        self.assertEqual(
            "pascal_class_to_java_class",
            record["template_id"]
        )
        self.assertIn("extends", " ".join(record["rules"]))
        self.assertIn("TFileSource", record["example"])

    def test_selects_templates_for_repository_symbol_types(self):
        templates = JavaTargetDesignTemplates()

        unit_ids = [
            template.template_id
            for template in templates.select_for_symbol(
                {
                    "document_type": "unit",
                    "name": "uFileSource"
                }
            )
        ]
        class_ids = [
            template.template_id
            for template in templates.select_for_symbol(
                {
                    "document_type": "class",
                    "name": "TFileSource"
                }
            )
        ]
        method_ids = [
            template.template_id
            for template in templates.select_for_symbol(
                {
                    "document_type": "method",
                    "name": "CopyFile"
                }
            )
        ]

        self.assertIn("pascal_unit_to_java_package", unit_ids)
        self.assertIn("pascal_class_to_java_class", class_ids)
        self.assertIn("pascal_routine_to_java_method", method_ids)

    def test_renders_prompt_ready_template_section(self):
        templates = JavaTargetDesignTemplates()
        rendered = templates.as_prompt_section(
            template_ids=[
                "pascal_class_to_java_class",
                "pascal_property_to_accessors"
            ]
        )

        self.assertIn("Java Target Design Templates", rendered)
        self.assertIn("Template: pascal_class_to_java_class", rendered)
        self.assertIn("Template: pascal_property_to_accessors", rendered)
        self.assertNotIn("Template: pascal_unit_to_java_package", rendered)

    def test_single_risk_templates_render_as_one_bullet(self):
        templates = JavaTargetDesignTemplates()
        rendered = templates.render(
            template_ids=[
                "pascal_routine_to_java_method"
            ]
        )

        self.assertIn(
            "- var/out parameters and nested procedures require manual "
            "design decisions.",
            rendered
        )
        self.assertNotIn("- v\n- a\n- r", rendered)

    def test_shared_support_catalog_renders_canonical_contracts(self):
        catalog = JavaSharedSupportCatalog()
        rendered = catalog.render()
        paths = catalog.protected_paths()
        type_names = catalog.protected_type_names()

        self.assertIn("Java Shared Support Contracts", rendered)
        self.assertIn("org.doublecmd.runtime.io.TStream", rendered)
        self.assertIn("org/doublecmd/runtime/io/TStream.java", paths)
        self.assertIn("TStream", type_names)
        self.assertIn("DCCrc32", type_names)


if __name__ == "__main__":
    unittest.main()
