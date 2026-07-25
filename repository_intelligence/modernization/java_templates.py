"""
Java target design templates for Delphi/Object Pascal modernization.

The templates define repeatable mapping rules from Pascal constructs to Java
design patterns. They are intentionally structured so migration planning,
prompt generation, and tests can all consume the same rules.
"""

from dataclasses import asdict, dataclass, field
import argparse
import json


@dataclass(frozen=True)
class JavaDesignTemplate:
    """
    A single Pascal-to-Java design mapping.
    """

    template_id: str
    title: str
    pascal_construct: str
    java_target: str
    rules: tuple
    example: str
    risks: tuple = field(default_factory=tuple)

    def to_dict(self):
        return asdict(self)


class JavaTargetDesignTemplates:
    """
    Repository of Java target design templates.

    This class is deliberately dependency-free. It should remain usable from
    prompt builders, CLIs, tests, and future model-backed migration workflows.
    """

    def __init__(self, templates=None):
        self.templates = list(templates or DEFAULT_JAVA_TEMPLATES)
        self.by_id = {
            template.template_id: template
            for template in self.templates
        }

    def list_templates(self):
        return list(self.templates)

    def get(self, template_id):
        return self.by_id.get(template_id)

    def require(self, template_id):
        template = self.get(template_id)

        if not template:
            raise KeyError(template_id)

        return template

    def select_for_symbol(self, symbol):
        document_type = symbol.get("document_type") or symbol.get("type")

        if document_type == "unit":
            return [
                self.require("pascal_unit_to_java_package"),
                self.require("global_routine_to_utility_method")
            ]

        if document_type == "class":
            return [
                self.require("pascal_class_to_java_class"),
                self.require("pascal_property_to_accessors"),
                self.require("pascal_constructor_destructor_to_lifecycle")
            ]

        if document_type == "method":
            return [
                self.require("pascal_routine_to_java_method"),
                self.require("pascal_exception_to_java_exception")
            ]

        return [
            self.require("pascal_unit_to_java_package"),
            self.require("pascal_class_to_java_class"),
            self.require("pascal_routine_to_java_method")
        ]

    def render(self, template_ids=None):
        templates = (
            [self.require(template_id) for template_id in template_ids]
            if template_ids
            else self.templates
        )
        sections = [
            self.render_template(template)
            for template in templates
        ]

        return "\n\n".join(sections)

    def render_template(self, template):
        lines = [
            f"Template: {template.template_id}",
            f"Title: {template.title}",
            f"Pascal: {template.pascal_construct}",
            f"Java: {template.java_target}",
            "Rules:"
        ]
        lines.extend(
            f"- {rule}"
            for rule in self._list_items(template.rules)
        )
        lines.append("Example:")
        lines.append(template.example)

        if template.risks:
            lines.append("Risks:")
            lines.extend(
                f"- {risk}"
                for risk in self._list_items(template.risks)
            )

        return "\n".join(lines)

    def _list_items(self, value):
        if isinstance(value, str):
            return [value]

        return list(value)

    def as_prompt_section(self, template_ids=None):
        return (
            "Java Target Design Templates\n"
            "Use these mappings consistently when modernizing Pascal code.\n\n"
            + self.render(template_ids=template_ids)
        )


DEFAULT_JAVA_TEMPLATES = (
    JavaDesignTemplate(
        template_id="pascal_unit_to_java_package",
        title="Pascal unit to Java package",
        pascal_construct="unit uExample with interface and implementation sections",
        java_target="Java package with one primary class plus support classes as needed",
        rules=(
            "Map the Pascal unit name to a stable Java package segment.",
            "Move public interface declarations to public Java types.",
            "Move implementation-only helpers to package-private classes or private static methods.",
            "Preserve initialization/finalization behavior as explicit lifecycle methods."
        ),
        example=(
            "unit uFileSource -> package org.doublecmd.filesources;\n"
            "TFileSource -> public abstract class FileSource"
        ),
        risks=(
            "Pascal units can mix many responsibilities that should not always become one Java class.",
            "Initialization sections can hide side effects that Java static initializers should avoid."
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_class_to_java_class",
        title="Pascal class to Java class",
        pascal_construct="TExample = class(TParent, IInterface)",
        java_target="Java class or abstract class with extends/implements",
        rules=(
            "Drop the leading T only when it improves Java naming consistency.",
            "Map single class inheritance to extends.",
            "Map implemented Pascal interfaces to implements.",
            "Use abstract classes when Pascal methods are intentionally unsupported or virtual placeholders.",
            "Prefer composition when Pascal inheritance is used only for shared utility state."
        ),
        example=(
            "TFileSource = class(TInterfacedObject, IFileSource)\n"
            "-> public abstract class FileSource implements IFileSource"
        ),
        risks=(
            "Pascal class names are currently simple names and can collide across units.",
            "Dynamic dispatch and interface reference-counting semantics need explicit review."
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_interface_to_java_interface",
        title="Pascal interface to Java interface",
        pascal_construct="IExample = interface ... end",
        java_target="Java interface with method contracts",
        rules=(
            "Map interface methods directly to Java interface methods.",
            "Remove COM-style reference counting methods unless explicitly used by repository logic.",
            "Represent optional capabilities with smaller interfaces instead of marker booleans where practical."
        ),
        example=(
            "IFileSource -> public interface FileSourceContract"
        ),
        risks=(
            "Pascal interfaces can imply lifetime semantics that Java garbage collection does not model.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_record_to_java_value_type",
        title="Pascal record to Java value type",
        pascal_construct="record with fields",
        java_target="Java record or immutable value class",
        rules=(
            "Use Java record when the Pascal record is a plain data carrier.",
            "Use a normal class when mutation, default values, or methods are required.",
            "Preserve field units and path semantics in type names where Pascal used aliases."
        ),
        example=(
            "TURI record -> public record UriParts(String protocol, String host, String path)"
        ),
        risks=(
            "Pascal records can be stack-allocated and mutable; Java records are immutable.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_property_to_accessors",
        title="Pascal property to Java accessors",
        pascal_construct="property Name: Type read GetName write SetName",
        java_target="Java getter/setter or immutable constructor parameter",
        rules=(
            "Map read-only properties to getters.",
            "Map writable properties to getter/setter pairs only when mutability is required.",
            "Prefer constructor injection for values that should not change after construction.",
            "Preserve boolean naming as isX or hasX when it reads naturally."
        ),
        example=(
            "property CurrentAddress: String read FCurrentAddress;\n"
            "-> public String getCurrentAddress()"
        ),
        risks=(
            "Blind setter generation can preserve unnecessary mutable state.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_event_to_listener",
        title="Pascal event to Java listener",
        pascal_construct="event callback, method list, observer field",
        java_target="Listener interface, observer list, or functional callback",
        rules=(
            "Use listener interfaces for multi-method event contracts.",
            "Use java.util.function callbacks for simple one-method events.",
            "Represent listener registration with add/remove methods.",
            "Avoid exposing mutable listener collections."
        ),
        example=(
            "TMethodList event listeners -> List<FileSourceListener> with addListener/removeListener"
        ),
        risks=(
            "Threading expectations around UI callbacks must be reviewed before migration.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_exception_to_java_exception",
        title="Pascal exception to Java exception",
        pascal_construct="raise Exception.Create(...)",
        java_target="Checked or unchecked Java exception",
        rules=(
            "Use unchecked exceptions for programming errors and unsupported operations.",
            "Use checked exceptions for recoverable IO and repository operations.",
            "Preserve user-facing error messages separately from diagnostic details."
        ),
        example=(
            "raise Exception.Create('Cannot construct abstract class')\n"
            "-> throw new IllegalStateException(\"Cannot construct abstract class\")"
        ),
        risks=(
            "Java checked exceptions can spread through APIs and should be designed deliberately.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_file_operations_to_java_nio",
        title="Pascal file operations to Java NIO",
        pascal_construct="TFile, streams, filesystem helpers",
        java_target="java.nio.file.Path, Files, FileChannel, InputStream/OutputStream",
        rules=(
            "Map file paths to Path rather than String where operations touch the filesystem.",
            "Use try-with-resources for stream lifetime.",
            "Use Files.copy, Files.move, and FileChannel for common file operations.",
            "Preserve retry, overwrite, timestamp, permission, and progress semantics explicitly."
        ),
        example=(
            "TFileStreamUAC.Create(...) -> try (InputStream in = Files.newInputStream(path)) { ... }"
        ),
        risks=(
            "Double Commander file-source abstractions may not always map to local filesystem APIs.",
            "Platform-specific behavior must remain behind adapters."
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_set_to_java_enumset",
        title="Pascal set to Java EnumSet",
        pascal_construct="set of enum values",
        java_target="EnumSet<EnumType>",
        rules=(
            "Map Pascal enum members to Java enum constants.",
            "Use EnumSet.noneOf for empty sets and EnumSet.of for literals.",
            "Prefer immutable wrappers when exposing sets from public APIs."
        ),
        example=(
            "TFileSourceOperationTypes -> EnumSet<FileSourceOperationType>"
        ),
        risks=(
            "Pascal set ordering and serialization may not match Java EnumSet behavior.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_constructor_destructor_to_lifecycle",
        title="Pascal constructor/destructor to Java lifecycle",
        pascal_construct="constructor Create; destructor Destroy",
        java_target="Java constructor, AutoCloseable, or explicit close/dispose method",
        rules=(
            "Map constructor initialization to Java constructors or static factories.",
            "Map destructor resource cleanup to AutoCloseable when deterministic cleanup is required.",
            "Avoid relying on finalizers.",
            "Use dependency injection for collaborators that Pascal constructors allocated globally."
        ),
        example=(
            "destructor Destroy; override -> public void close()"
        ),
        risks=(
            "Pascal destructors run deterministically; Java garbage collection does not.",
        )
    ),
    JavaDesignTemplate(
        template_id="pascal_routine_to_java_method",
        title="Pascal routine to Java method",
        pascal_construct="procedure/function with parameters and Result",
        java_target="Java method with return value or void",
        rules=(
            "Map Pascal functions to Java methods returning the function result type.",
            "Map procedures to void methods.",
            "Replace Result assignments with explicit return statements.",
            "Model var/out parameters as return objects or mutable holder types only when necessary.",
            "Preserve nested helper routines as private methods or local lambdas when readable."
        ),
        example=(
            "function CopyFile(...): Boolean -> public boolean copyFile(...)"
        ),
        risks=(
            "var/out parameters and nested procedures require manual design decisions.",
        )
    ),
    JavaDesignTemplate(
        template_id="global_routine_to_utility_method",
        title="Global routine to utility/service method",
        pascal_construct="unit-level function or procedure",
        java_target="static utility method or injectable service",
        rules=(
            "Use static utility methods for stateless pure helpers.",
            "Use services when the routine depends on filesystem, UI, configuration, or shared state.",
            "Avoid creating one large utility class for an entire Pascal unit."
        ),
        example=(
            "function mbCompareText(...) -> TextComparison.compare(...)"
        ),
        risks=(
            "Global routines often hide dependencies that should become explicit collaborators.",
        )
    )
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect Java target design templates."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    list_parser = subparsers.add_parser(
        "list",
        help="List available template identifiers."
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Print template summaries as JSON."
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Show one or more templates."
    )
    show_parser.add_argument(
        "template_ids",
        nargs="+",
        help="Template identifiers to show."
    )
    show_parser.add_argument(
        "--json",
        action="store_true",
        help="Print full templates as JSON."
    )

    render_parser = subparsers.add_parser(
        "render",
        help="Render a prompt-ready template section."
    )
    render_parser.add_argument(
        "template_ids",
        nargs="*",
        help="Optional template identifiers to render."
    )

    return parser.parse_args()


def main():
    args = parse_args()
    templates = JavaTargetDesignTemplates()

    if args.command == "list":
        records = [
            {
                "template_id": template.template_id,
                "title": template.title,
                "pascal_construct": template.pascal_construct,
                "java_target": template.java_target
            }
            for template in templates.list_templates()
        ]

        if args.json:
            print(json.dumps(records, indent=2, sort_keys=True))
        else:
            for record in records:
                print(f"{record['template_id']}: {record['title']}")

        return

    if args.command == "show":
        selected = [
            templates.require(template_id)
            for template_id in args.template_ids
        ]

        if args.json:
            print(json.dumps(
                [template.to_dict() for template in selected],
                indent=2,
                sort_keys=True
            ))
        else:
            print(templates.render(args.template_ids))

        return

    print(templates.as_prompt_section(
        template_ids=args.template_ids or None
    ))


if __name__ == "__main__":
    main()
