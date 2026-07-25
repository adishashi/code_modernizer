"""
embeddings.py

Embedding document generation for the semantic intelligence layer.

Stage 4.1 intentionally stops at artifact generation. It does not introduce a
vector database or semantic search API; those belong to later roadmap stages.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

@dataclass(frozen=True)
class EmbeddingDocument:
    """
    Text and metadata prepared for embedding.
    """

    document_id: str
    document_type: str
    name: str
    text: str
    unit: str = None
    class_name: str = None
    method_name: str = None
    file: str = None

    def metadata(self):
        data = asdict(self)
        data.pop("text")

        return data


class RepositoryEmbeddingDocumentBuilder:
    """
    Builds embedding documents from Repository lookup tables.
    """

    def __init__(self, repository):
        self.repository = repository

    def build_documents(self, document_types=None):
        requested = self._requested_types(document_types)
        documents = []

        if "unit" in requested:
            documents.extend(self.build_unit_documents())

        if "class" in requested:
            documents.extend(self.build_class_documents())

        if "method" in requested:
            documents.extend(self.build_method_documents())

        if "subsystem" in requested:
            documents.extend(self.build_subsystem_documents())

        return documents

    def build_unit_documents(self):
        documents = []

        for unit_name in sorted(self.repository.units):
            unit = self.repository.units[unit_name]
            dependencies = self.repository.get_dependencies(unit_name)
            dependents = self.repository.get_dependents(unit_name)
            classes = [
                cls.get("name")
                for cls in self.repository.classes_by_unit.get(unit_name, [])
            ]
            methods = [
                self._qualified_method_name(method)
                for method in self.repository.methods_by_unit.get(
                    unit_name,
                    []
                )
            ]

            text = self._join_sections(
                ("type", "unit"),
                ("name", unit_name),
                ("file", unit.get("file")),
                ("dependencies", dependencies),
                ("dependents", dependents),
                ("classes", classes),
                ("methods", methods),
                ("fields", self._field_names(unit.get("fields", [])))
            )

            documents.append(
                EmbeddingDocument(
                    document_id=f"unit:{unit_name}",
                    document_type="unit",
                    name=unit_name,
                    unit=unit_name,
                    file=unit.get("file"),
                    text=text
                )
            )

        return documents

    def build_class_documents(self):
        documents = []

        for class_name in sorted(self.repository.classes_by_name):
            for index, cls in enumerate(
                self.repository.classes_by_name[class_name]
            ):
                unit_name = cls.get("unit")
                children = self.repository.get_children(class_name)
                methods = [
                    self._qualified_method_name(method)
                    for method in self.repository.methods_by_class.get(
                        class_name,
                        []
                    )
                    if not unit_name or method.get("unit") == unit_name
                ]

                text = self._join_sections(
                    ("type", "class"),
                    ("name", class_name),
                    ("unit", unit_name),
                    ("file", cls.get("file")),
                    ("parent", cls.get("parent")),
                    ("children", children),
                    ("methods", methods)
                )

                suffix = unit_name or "unknown"

                documents.append(
                    EmbeddingDocument(
                        document_id=f"class:{suffix}:{class_name}:{index}",
                        document_type="class",
                        name=class_name,
                        unit=unit_name,
                        class_name=class_name,
                        file=cls.get("file"),
                        text=text
                    )
                )

        return documents

    def build_method_documents(self):
        documents = []

        for index, method in enumerate(self.repository.methods):
            unit_name = method.get("unit")
            class_name = method.get("class")
            method_name = method.get("method")
            qualified_name = self._qualified_method_name(method)
            callers = self.repository.get_callers(method_name)
            callees = self.repository.get_callees(method_name)

            text = self._join_sections(
                ("type", "method"),
                ("name", qualified_name),
                ("method", method_name),
                ("class", class_name),
                ("unit", unit_name),
                ("file", method.get("file")),
                ("kind", method.get("kind")),
                ("callers", callers),
                ("callees", callees)
            )

            document_id = (
                f"method:{unit_name or 'unknown'}:"
                f"{class_name or 'global'}:{method_name}:{index}"
            )

            documents.append(
                EmbeddingDocument(
                    document_id=document_id,
                    document_type="method",
                    name=qualified_name,
                    unit=unit_name,
                    class_name=class_name,
                    method_name=method_name,
                    file=method.get("file"),
                    text=text
                )
            )

        return documents

    def build_subsystem_documents(self):
        subsystems = {}

        for unit_name, source_file in self.repository.files.items():
            subsystem = self._subsystem_name(source_file)

            if subsystem not in subsystems:
                subsystems[subsystem] = {
                    "units": [],
                    "classes": [],
                    "methods": [],
                    "files": []
                }

            bucket = subsystems[subsystem]
            bucket["units"].append(unit_name)

            if source_file:
                bucket["files"].append(source_file)

            bucket["classes"].extend(
                cls.get("name")
                for cls in self.repository.classes_by_unit.get(unit_name, [])
            )
            bucket["methods"].extend(
                self._qualified_method_name(method)
                for method in self.repository.methods_by_unit.get(
                    unit_name,
                    []
                )
            )

        documents = []

        for subsystem in sorted(subsystems):
            bucket = subsystems[subsystem]
            text = self._join_sections(
                ("type", "subsystem"),
                ("name", subsystem),
                ("files", sorted(set(bucket["files"]))),
                ("units", sorted(set(bucket["units"]))),
                ("classes", sorted(set(bucket["classes"]))),
                ("methods", sorted(set(bucket["methods"])))
            )

            documents.append(
                EmbeddingDocument(
                    document_id=f"subsystem:{subsystem}",
                    document_type="subsystem",
                    name=subsystem,
                    text=text
                )
            )

        return documents

    def _requested_types(self, document_types):
        if document_types is None:
            return {"unit", "class", "method", "subsystem"}

        if isinstance(document_types, str):
            return {document_types.casefold()}

        return {
            document_type.casefold()
            for document_type in document_types
        }

    def _qualified_method_name(self, method):
        class_name = method.get("class")
        method_name = method.get("method")

        if class_name:
            return f"{class_name}.{method_name}"

        return method_name

    def _field_names(self, fields):
        names = []

        for field in fields:
            field_name = field.get("name")
            field_type = field.get("type")

            if field_name and field_type:
                names.append(f"{field_name}: {field_type}")
            elif field_name:
                names.append(field_name)

        return names

    def _subsystem_name(self, source_file):
        if not source_file:
            return "unknown"

        parts = Path(source_file).parts

        if len(parts) >= 2:
            return "/".join(parts[:2])

        return parts[0]

    def _join_sections(self, *sections):
        lines = []

        for key, value in sections:
            if value is None:
                continue

            if isinstance(value, (list, tuple, set)):
                values = [
                    str(item)
                    for item in value
                    if item is not None
                ]

                if not values:
                    continue

                lines.append(f"{key}: {', '.join(values)}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)


class LocalHashingEmbeddingProvider:
    """
    Deterministic local embedding provider.

    Hashing vectors are not a replacement for model embeddings, but they allow
    the pipeline, metadata, storage contract, and tests to be built without
    network access or external model packages.
    """

    provider_name = "local_hashing"

    def __init__(
        self,
        dimensions=384,
        ngram_range=(1, 2),
        norm="l2"
    ):
        self.dimensions = dimensions
        self.ngram_range = ngram_range
        self.norm = norm

    def embed_documents(self, texts):
        try:
            from sklearn.feature_extraction.text import HashingVectorizer
        except ImportError as exc:
            raise RuntimeError(
                "scikit-learn is required for LocalHashingEmbeddingProvider"
            ) from exc

        vectorizer = HashingVectorizer(
            n_features=self.dimensions,
            alternate_sign=False,
            norm=self.norm,
            ngram_range=self.ngram_range,
            lowercase=True
        )

        matrix = vectorizer.transform(texts)

        return matrix.astype("float32").toarray()

    def metadata(self):
        return {
            "provider": self.provider_name,
            "dimensions": self.dimensions,
            "ngram_range": list(self.ngram_range),
            "norm": self.norm
        }


class EmbeddingArtifactWriter:
    """
    Writes embedding artifacts for later vector database ingestion.
    """

    def __init__(self, output_directory):
        self.output_directory = Path(output_directory)

    def write(self, documents, embeddings, provider_metadata):
        import numpy as np

        self.output_directory.mkdir(parents=True, exist_ok=True)

        metadata_path = self.output_directory / "metadata.jsonl"
        embeddings_path = self.output_directory / "embeddings.npy"
        manifest_path = self.output_directory / "manifest.json"

        with metadata_path.open("w", encoding="utf-8") as fp:
            for document in documents:
                fp.write(json.dumps(document.metadata(), sort_keys=True))
                fp.write("\n")

        np.save(embeddings_path, embeddings)

        counts = {}

        for document in documents:
            counts[document.document_type] = (
                counts.get(document.document_type, 0) + 1
            )

        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "document_count": len(documents),
            "document_counts": counts,
            "embedding_shape": list(embeddings.shape),
            "provider": provider_metadata,
            "files": {
                "metadata": metadata_path.name,
                "embeddings": embeddings_path.name
            }
        }

        with manifest_path.open("w", encoding="utf-8") as fp:
            json.dump(manifest, fp, indent=2, sort_keys=True)

        return manifest


class RepositoryEmbeddingGenerator:
    """
    Coordinates document construction, embedding, and artifact writing.
    """

    def __init__(
        self,
        repository,
        provider=None
    ):
        self.repository = repository
        self.provider = provider or LocalHashingEmbeddingProvider()
        self.document_builder = RepositoryEmbeddingDocumentBuilder(repository)

    def build_documents(self, document_types=None):
        return self.document_builder.build_documents(
            document_types=document_types
        )

    def generate(
        self,
        output_directory,
        document_types=None
    ):
        documents = self.build_documents(document_types=document_types)
        texts = [
            document.text
            for document in documents
        ]
        embeddings = self.provider.embed_documents(texts)
        writer = EmbeddingArtifactWriter(output_directory)

        return writer.write(
            documents,
            embeddings,
            self.provider.metadata()
        )


def generate_repository_embeddings(
    repository,
    output_directory,
    document_types=None,
    provider=None
):
    """
    Generate embedding artifacts for a Repository.
    """

    generator = RepositoryEmbeddingGenerator(
        repository,
        provider=provider
    )

    return generator.generate(
        output_directory,
        document_types=document_types
    )
