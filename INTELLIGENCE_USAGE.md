# Repository Intelligence Usage

This guide covers the non-semantic intelligence layer: repository loading,
symbol lookup, graph traversal, search, context building, and LangChain tools.

The intelligence layer operates only on generated JSON artifacts in `output/`.
It does not parse Pascal source files.

Semantic, ChromaDB, and summary commands are organized into subpackages such as
`repository_intelligence.semantic`, `repository_intelligence.chroma`, and
`repository_intelligence.summaries`. Root-level CLI wrappers are retained for
backward compatibility.

---

## Load The Repository

```python
from repository_intelligence import Repository, load_repository

repository = Repository(
    load_repository("output")
)

print(repository.statistics())
```

Expected current statistics:

```text
files: 833
units: 804
classes: 2399
methods: 12093
dependency_edges: 5415
inheritance_edges: 1313
call_edges: 42309
```

`PROJECT_STATE.md` still lists 805 units from the latest validated parser
summary, while the current loaded artifact contains 804 unique unit keys.
Treat large deviations as parser or artifact regressions.

---

## Repository API

Use `Repository` for direct structural lookup.

```python
unit = repository.find_unit("uFileSource")
source_file = repository.find_file("uFileSource")
classes = repository.find_classes("TFileSource")
methods = repository.find_methods("CopyFile")

dependencies = repository.get_dependencies("uFileSource")
dependents = repository.get_dependents("uFileSource")

parent = repository.get_parent("TFileSystemFileSource")
children = repository.get_children("TFileSource")

callers = repository.get_callers("CopyFile")
callees = repository.get_callees("CopyFile")
```

Notes:

* `find_class()` returns the first match for backward compatibility.
* `find_classes()` returns all matching class records and should be preferred
  where namespace collisions matter.
* `find_method()` returns all matching method records.
* `find_methods()` accepts optional `class_name` and `unit_name` filters.

Example disambiguated method lookup:

```python
methods = repository.find_methods(
    "CopyFile",
    class_name="TFileSystemOperationHelper",
    unit_name="uFileSystemUtil"
)
```

---

## Symbol Table

Use `SymbolTable` for typed lookup and ambiguity handling.

```python
from repository_intelligence import SymbolTable

symbols = SymbolTable(repository)

unit_matches = symbols.resolve_symbol(
    "uFileSource",
    symbol_types="unit"
)

class_matches = symbols.resolve_symbol(
    "TFileSource",
    symbol_types="class"
)

method_matches = symbols.resolve_symbol(
    "CopyFile",
    symbol_types="method"
)

ambiguity = symbols.disambiguate_class("TFileSource")
```

`symbol_types` can be a string or a list containing `unit`, `file`, `class`,
or `method`.

---

## Graph API

Use `GraphAPI` for traversal. Traversals are bounded by depth to keep calls
predictable on large repositories.

```python
from repository_intelligence import GraphAPI

graph = GraphAPI(repository)

direct_dependencies = graph.dependencies("uFileSource")
transitive_dependencies = graph.transitive_dependencies(
    "uFileSource",
    max_depth=2
)

ancestors = graph.ancestors("TFileSystemFileSource")
descendants = graph.descendants(
    "TFileSource",
    max_depth=2
)

callees = graph.callees("CopyFile")
paths = graph.execution_paths(
    "CopyFile",
    "CopyFileExW",
    max_depth=2
)

impact = graph.impact_analysis(
    "TFileSource",
    max_depth=1
)
```

Current graph limitations:

* Class hierarchy uses simple class names, so namespace collisions are possible.
* Call graph data is static. Dynamic dispatch and unresolved framework calls may
  be incomplete.
* `impact_analysis()` combines available dependency, caller, and inheritance
  traversals for the provided symbol name. It does not infer symbol type.

---

## Search

Use `RepositorySearch` for ranked exact, substring, and fuzzy symbol search.

```python
from repository_intelligence import RepositorySearch

search = RepositorySearch(repository)

all_results = search.search_symbols(
    "checksum",
    limit=10
)

method_results = search.search_methods(
    "checksum",
    limit=5
)

class_results = search.search_classes(
    "TFileSource",
    limit=5
)
```

This is lexical search only. Semantic search and embeddings belong to the next
phase.

---

## Context Builder

Use `ContextBuilder` to assemble structured context for later LLM prompts.

```python
from repository_intelligence import ContextBuilder

builder = ContextBuilder(repository)

context = builder.build_query_context(
    "checksum",
    limit=5,
    max_graph_depth=1
)

text = builder.render_context(context)
print(text)
```

Returned context includes:

* ranked search results
* related units
* related classes
* related methods
* direct graph context

For exact symbol-first context:

```python
context = builder.build_symbol_context(
    "TFileSource",
    symbol_types="class",
    max_graph_depth=2
)
```

---

## LangChain Tools

LangChain wrappers are intentionally thin. They adapt typed tool input into
calls on `Repository`, `GraphAPI`, `RepositorySearch`, and `ContextBuilder`.

Create tools from an existing repository:

```python
from repository_intelligence import create_repository_tools

tools = create_repository_tools(repository)
tools_by_name = {
    tool.name: tool
    for tool in tools
}

result = tools_by_name["find_class"].invoke(
    {
        "class_name": "TFileSource"
    }
)
```

Or load artifacts and create tools in one call:

```python
from repository_intelligence import load_repository_tools

tools = load_repository_tools("output")
```

Available tools:

```text
find_unit
find_file
find_class
find_method
find_dependencies
find_dependents
find_parent
find_children
find_callers
find_callees
transitive_dependencies
transitive_dependents
transitive_callers
transitive_callees
execution_path
impact_analysis
search_symbols
build_context
render_context
repository_statistics
find_affected_code
trace_dependencies
locate_equivalent_patterns
estimate_change_impact
produce_migration_context
produce_migration_prompt
generate_migration_code
```

Example invocations:

```python
tools_by_name["find_unit"].invoke(
    {
        "unit_name": "uFileSource"
    }
)

tools_by_name["search_symbols"].invoke(
    {
        "query": "checksum",
        "symbol_types": ["unit", "class", "method"],
        "limit": 5
    }
)

tools_by_name["execution_path"].invoke(
    {
        "start_method": "CopyFile",
        "target_method": "CopyFileExW",
        "max_depth": 2,
        "limit": 5
    }
)

tools_by_name["render_context"].invoke(
    {
        "query": "checksum",
        "limit": 5,
        "max_graph_depth": 1
    }
)
```

---

## Modernization Tools

Modernization tools are thin LangChain wrappers around
`ModernizationAnalyzer` and `ModernizationContextAssembler`.

Available modernization-oriented tools:

```text
find_affected_code
trace_dependencies
locate_equivalent_patterns
estimate_change_impact
produce_migration_context
```

Example invocations:

```python
tools_by_name["find_affected_code"].invoke(
    {
        "symbol": "TFileSource",
        "max_depth": 1,
        "limit": 10
    }
)

tools_by_name["trace_dependencies"].invoke(
    {
        "symbol": "CopyFile",
        "max_depth": 2
    }
)

tools_by_name["locate_equivalent_patterns"].invoke(
    {
        "query": "checksum",
        "symbol_types": ["class", "method"],
        "limit": 5
    }
)

tools_by_name["estimate_change_impact"].invoke(
    {
        "symbol": "TFileSource",
        "max_depth": 2
    }
)

tools_by_name["produce_migration_context"].invoke(
    {
        "task": "modernize TFileSource to Java",
        "target_language": "Java",
        "limit": 5,
        "document_types": ["class"],
        "include_source": True
    }
)

tools_by_name["produce_migration_prompt"].invoke(
    {
        "task": "modernize TFileSource to Java",
        "target_language": "Java",
        "limit": 5,
        "document_types": ["class"],
        "include_source": True,
        "max_source_lines": 160,
        "max_source_chars": 12000
    }
)

tools_by_name["generate_migration_code"].invoke(
    {
        "task": "modernize TFileSource to Java",
        "target_language": "Java",
        "limit": 5,
        "document_types": ["class"],
        "include_source": True
    }
)
```

`produce_migration_context` and `produce_migration_prompt` use the
ChromaDB-backed modernization context assembler, so they require generated
embeddings, ChromaDB artifacts, and summary artifacts. The other modernization
tools use structural repository indices and lexical search.

`produce_migration_prompt` builds on the same context and returns a package
containing model-ready messages, a full prompt string, rendered context
sections, and prompt-size statistics.

---

## LangChain Agent Orchestration

The repository agent wraps the LangChain tools, prompt instructions, bounded
conversation memory, and tool routing behind one API. It supports two modes:

```text
deterministic - local rule-based tool routing for validation
langchain     - model-backed LangChain agent execution
```

Run the deterministic CLI:

```powershell
python -m repository_intelligence.agent "Estimate impact of TFileSource" --mode deterministic
```

Print the full structured result:

```powershell
python -m repository_intelligence.agent "Modernize TFileSource to Java" --mode deterministic --json
```

Use the API directly:

```python
from repository_intelligence import load_repository_agent

agent = load_repository_agent(
    "output",
    tool_options={
        "artifacts_directory": "output/embeddings",
        "persist_directory": "output/chroma",
        "summary_directory": "output/summaries",
        "source_root": "doublecmd"
    }
)

result = agent.ask(
    "Where is checksum calculation implemented?",
    mode="deterministic"
)

print(result["answer"])
```

Use a model-backed LangChain agent by passing a LangChain-compatible chat model
or model string:

```python
agent = load_repository_agent(
    "output",
    model=my_chat_model
)

result = agent.ask(
    "Explain how TFileSource should be migrated to Java.",
    mode="langchain"
)
```

The deterministic mode is intended for repeatable local validation. The
model-backed mode delegates tool selection and final wording to LangChain's
agent graph.

---

## Tests

The intelligence layer uses the standard library test runner.

```powershell
python -m unittest discover -s tests -v
```

The current integration suite covers:

* repository statistics and lookup
* method disambiguation
* symbol table lookup and ambiguity detection
* dependency, inheritance, and call graph traversal
* execution path and impact analysis
* lexical search
* context assembly and rendering
* LangChain tool creation and invocation

Run this suite before semantic search changes to ensure existing structural
behavior remains stable.

---

## Embedding Generation

Stage 4.1 generates embedding artifacts from repository metadata. It does not
create a vector database and does not expose semantic search yet.

Generate all embedding documents:

```powershell
python -m repository_intelligence.semantic.generate_embeddings --input output --output output\embeddings --dimensions 384
```

Generate selected document types:

```powershell
python -m repository_intelligence.semantic.generate_embeddings --input output --output output\embeddings_units --types unit subsystem --dimensions 384
```

Generated files:

```text
output/embeddings/metadata.jsonl
output/embeddings/embeddings.npy
output/embeddings/manifest.json
```

Current full-corpus manifest:

```text
documents: 15588
shape: 15588 x 384
provider: local_hashing
units: 804
classes: 2508
methods: 12093
subsystems: 183
```

`local_hashing` is deterministic and works without network access or external
model packages. It is suitable for validating the embedding pipeline and for
feeding Stage 4.2 vector database ingestion. Model-backed embeddings can be
added later behind the same provider interface.

---

## ChromaDB Vector Store

Stage 4.2 ingests Stage 4.1 embedding artifacts into a persistent ChromaDB
collection. This creates the vector database storage layer; semantic query
ranking is implemented in the next stage.

Ingest the full artifact set:

```powershell
python -m repository_intelligence.chroma.ingest_chroma --artifacts output\embeddings --persist output\chroma --collection repository_intelligence --batch-size 500
```

Current persistent collection:

```text
directory: output/chroma
collection: repository_intelligence
vectors: 15588
dimensions: 384
```

Use the vector store API directly:

```python
from repository_intelligence import ChromaRepositoryVectorStore

store = ChromaRepositoryVectorStore(
    "output/chroma",
    collection_name="repository_intelligence"
)

print(store.count())

result = store.query(
    [[1.0] + [0.0] * 383],
    n_results=3
)

store.close()
```

`close()` should be called when using a short-lived store on Windows so Chroma's
SQLite files are released before cleanup.

The Chroma store reads:

```text
output/embeddings/metadata.jsonl
output/embeddings/embeddings.npy
output/embeddings/manifest.json
```

and writes the persistent database under:

```text
output/chroma
```

---

## Hybrid Retrieval

Stage 4.3 combines:

* lexical symbol search
* ChromaDB vector search
* graph expansion
* repository and embedding statistics

Run a general hybrid query:

```powershell
python -m repository_intelligence.semantic.hybrid_search checksum --limit 10 --graph-depth 1
```

Run a type-filtered query:

```powershell
python -m repository_intelligence.semantic.hybrid_search TFileSource --types class --limit 10 --graph-depth 1
```

Print full JSON for manual validation:

```powershell
python -m repository_intelligence.semantic.hybrid_search checksum --limit 5 --json
```

Use the API directly:

```python
from repository_intelligence import HybridRetriever, Repository, load_repository

repository = Repository(
    load_repository("output")
)
retriever = HybridRetriever(
    repository,
    artifacts_directory="output/embeddings",
    persist_directory="output/chroma"
)

try:
    result = retriever.retrieve(
        "checksum",
        limit=10,
        lexical_limit=25,
        vector_limit=25,
        graph_depth=1
    )
finally:
    retriever.close()
```

Each result includes:

```text
document_id
document_type
name
file
combined score
lexical/vector/graph component scores
source list
vector distance
```

Hybrid retrieval is still based on local hashing embeddings. It validates the
retrieval architecture and ChromaDB integration; model-backed embeddings can be
plugged in behind the embedding provider interface later.

---

## Repository Summaries

Stage 4.4 generates deterministic summaries from repository metadata and graph
relationships. These summaries do not use an LLM; they are stable artifacts for
agent context, manual inspection, and later higher-level summarization.

Generate all summaries:

```powershell
python -m repository_intelligence.summaries.generate_summaries --input output --output output\summaries
```

Generate selected summary types:

```powershell
python -m repository_intelligence.summaries.generate_summaries --input output --output output\summaries_units --types unit architecture
```

Inspect generated summaries:

```powershell
python -m repository_intelligence.summaries.inspect_summaries TFileSource --type class --limit 5
```

Print matching summaries as JSON:

```powershell
python -m repository_intelligence.summaries.inspect_summaries CopyFile --type method --limit 3 --json
```

Generated files:

```text
output/summaries/summaries.jsonl
output/summaries/manifest.json
```

Current full-corpus manifest:

```text
summaries: 15589
methods: 12093
classes: 2508
units: 804
subsystems: 183
architecture: 1
```

Each summary record includes:

```text
summary_id
summary_type
name
summary
unit/class/method/file fields where applicable
metrics
related_symbols
```

---

## Semantic Search

Semantic search queries the ChromaDB vector collection directly and optionally
enriches matching embedding documents with generated summaries.

Run a semantic search:

```powershell
python -m repository_intelligence.semantic.semantic_search_cli "checksum calculation" --limit 5
```

Filter by document type:

```powershell
python -m repository_intelligence.semantic.semantic_search_cli TFileSource --types class --limit 5
```

Print full JSON:

```powershell
python -m repository_intelligence.semantic.semantic_search_cli checksum --limit 3 --json
```

Use the API directly:

```python
from repository_intelligence import SemanticSearchEngine

engine = SemanticSearchEngine(
    artifacts_directory="output/embeddings",
    persist_directory="output/chroma",
    summary_directory="output/summaries"
)

try:
    result = engine.search(
        "checksum calculation",
        limit=5,
        document_types=["unit", "class", "method"]
    )
finally:
    engine.close()
```

Each result includes:

```text
document_id
document_type
name
score
distance
document metadata
optional generated summary
optional summary metrics
```

The current semantic quality is limited by `local_hashing` embeddings. The
search API and CLI are designed so a model-backed embedding provider can replace
the local provider later without changing callers.

---

## Modernization Context Assembly

Modernization context assembly builds a single task packet for legacy-code
modernization work. It combines hybrid retrieval, direct semantic search,
summary enrichment, graph relationships, and bounded snippets from the Pascal
source tree.

Run a modernization context query:

```powershell
python -m repository_intelligence.modernization.build_context "modernize TFileSource to Java" --types class --limit 5
```

Print full JSON for validation:

```powershell
python -m repository_intelligence.modernization.build_context "checksum calculation modernization" --limit 5 --json
```

Skip source snippets when only metadata context is needed:

```powershell
python -m repository_intelligence.modernization.build_context "archive extraction modernization" --no-source
```

Use the API directly:

```python
from repository_intelligence import (
    ModernizationContextAssembler,
    Repository,
    load_repository
)

repository = Repository(
    load_repository("output")
)
assembler = ModernizationContextAssembler(
    repository,
    artifacts_directory="output/embeddings",
    persist_directory="output/chroma",
    summary_directory="output/summaries",
    source_root="doublecmd"
)

try:
    context = assembler.build_context(
        "modernize TFileSource to Java",
        target_language="Java",
        limit=5,
        document_types=["class"],
        graph_depth=1
    )
finally:
    assembler.close()
```

Returned context includes:

```text
task
retrieval.hybrid
retrieval.semantic
symbols
summaries
graph_context
target_design
source_context
modernization_guidance
statistics
```

Source context is extracted from files referenced by repository metadata. For
units, classes, and methods, the modernization layer now attempts to return the
full source body instead of only a display window.

---

## Pascal Source Extraction

Modernization source extraction returns source bodies for selected repository
symbols. It supports:

```text
unit   - full Pascal source file
class  - class declaration block
method - method implementation body
```

Extract a class declaration:

```powershell
python -m repository_intelligence.modernization.extract_source TFileSource --type class
```

Extract a disambiguated method implementation:

```powershell
python -m repository_intelligence.modernization.extract_source CopyFile --type method --class-name TFileSystemOperationHelper --unit-name uFileSystemUtil
```

Print the structured extraction record:

```powershell
python -m repository_intelligence.modernization.extract_source TFileSource --type class --json
```

Use the API directly:

```python
from repository_intelligence import PascalSourceExtractor

extractor = PascalSourceExtractor("doublecmd")
record = extractor.extract_symbol(
    {
        "document_type": "method",
        "name": "CopyFile",
        "method_name": "CopyFile",
        "class_name": "TFileSystemOperationHelper",
        "unit": "uFileSystemUtil",
        "file": "src/filesources/filesystem/ufilesystemutil.pas"
    }
)

print(record["source"])
```

Each extraction record includes:

```text
symbol
document_type
unit
class_name
method_name
file
path
start_line
end_line
line_count
truncated
extraction_kind
source
```

The extractor is structural text scanning, not a second parser. It is designed
to provide complete source bodies for migration prompts while keeping generated
repository indices as the source of truth for symbol identity.

---

## Java Target Design Templates

Java target design templates define consistent Delphi/Object Pascal to Java
mapping rules for modernization prompts and planning.

List available templates:

```powershell
python -m repository_intelligence.modernization.java_templates list
```

Show selected templates:

```powershell
python -m repository_intelligence.modernization.java_templates show pascal_class_to_java_class pascal_property_to_accessors
```

Render a prompt-ready section:

```powershell
python -m repository_intelligence.modernization.java_templates render pascal_class_to_java_class pascal_routine_to_java_method
```

Use the API directly:

```python
from repository_intelligence import JavaTargetDesignTemplates

templates = JavaTargetDesignTemplates()
selected = templates.select_for_symbol(
    {
        "document_type": "class",
        "name": "TFileSource"
    }
)

prompt_text = templates.as_prompt_section(
    template_ids=[
        template.template_id
        for template in selected
    ]
)
```

Current templates cover:

```text
Pascal units to Java packages
Pascal classes to Java classes
Pascal interfaces to Java interfaces
Pascal records to Java value types
Pascal properties to Java accessors
Pascal events to Java listeners
Pascal exceptions to Java exceptions
Pascal file operations to Java NIO
Pascal sets to Java EnumSet
Pascal constructors/destructors to Java lifecycle patterns
Pascal routines to Java methods
Global routines to utility or service methods
```

Modernization context assembly now includes a `target_design` section with the
templates selected for the retrieved symbols.

---

## Modernization Prompt Generation

Modernization prompt generation turns repository context into an LLM-ready
prompt package. It combines:

```text
task instructions
retrieved symbols
repository summaries
Java target design templates
graph relationships
bounded Pascal source context
modernization guidance and risks
```

Generate a prompt:

```powershell
python -m repository_intelligence.modernization.prompts "Modernize TFileSource to Java" --types class --limit 5
```

Generate a prompt without source bodies:

```powershell
python -m repository_intelligence.modernization.prompts "Modernize TFileSource to Java" --types class --no-source
```

Print the structured package:

```powershell
python -m repository_intelligence.modernization.prompts "Modernize CopyFile to Java" --types method --json
```

Use the API directly:

```python
from repository_intelligence import (
    ModernizationPromptGenerator,
    Repository,
    load_repository
)

repository = Repository(
    load_repository("output")
)
generator = ModernizationPromptGenerator(
    repository,
    context_options={
        "artifacts_directory": "output/embeddings",
        "persist_directory": "output/chroma",
        "summary_directory": "output/summaries",
        "source_root": "doublecmd"
    }
)

package = generator.generate(
    "Modernize TFileSource to Java",
    document_types=["class"],
    limit=5
)

print(package["prompt"]["prompt"])
```

The prompt package includes:

```text
context
prompt.messages
prompt.sections
prompt.prompt
prompt.statistics
```

This stage does not call an LLM. It prepares bounded, evidence-grounded prompt
input for the model-backed generation stage.

---

## LLM Code Generation Backend

The code generation backend consumes modernization prompt packages and returns
structured Java migration output.

Run a local dry-run generation:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --types class --limit 5
```

The dry-run backend does not call an LLM. It validates the end-to-end pipeline
and returns a Java skeleton.

Run a LangChain-backed generation:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --backend langchain --types class --limit 5
```

Persist generated Java files to disk:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --backend langchain --types class --limit 5 --output-directory output\generated_java
```

Prevent overwriting previously generated files:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --backend langchain --types class --limit 5 --output-directory output\generated_java --no-overwrite
```

The generation CLI loads `.env` from the current working directory before
initializing the model. For Gemini models, the file should contain:

```text
GOOGLE_API_KEY=...
```

The default LangChain generation model is:

```text
google_genai:gemini-3.5-flash
```

Gemini generation requires the LangChain Google integration package:

```powershell
pip install langchain-google-genai
```

Use a custom environment file path when needed:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --backend langchain --env-file .env.local --types class
```

Override the model explicitly when needed:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --backend langchain --model "google_genai:gemini-3.1-flash-lite" --types class
```

Existing shell environment variables are not overwritten by `.env` values.
The repository `.gitignore` excludes `.env` and `.env.*`.

Use the API directly:

```python
from repository_intelligence import (
    LangChainCodeGenerationBackend,
    ModernizationCodeGenerator,
    Repository,
    load_repository
)

repository = Repository(
    load_repository("output")
)
backend = LangChainCodeGenerationBackend(my_chat_model)
generator = ModernizationCodeGenerator(
    repository,
    backend=backend,
    context_options={
        "artifacts_directory": "output/embeddings",
        "persist_directory": "output/chroma",
        "summary_directory": "output/summaries",
        "source_root": "doublecmd"
    }
)

result = generator.generate(
    "Modernize TFileSource to Java",
    document_types=["class"],
    output_directory="output/generated_java"
)
```

Generation results include:

```text
context
prompt
generation.backend
generation.raw_output
generation.structured_output.files
generation.structured_output.classes
generation.structured_output.methods
generation.structured_output.notes
generation.structured_output.unresolved_items
generation.written_files
```

The LangChain backend asks the model for JSON. If the model returns plain text,
the raw text is preserved and the structured output records a parsing follow-up.
Persistent writing uses generated file paths under the selected output
directory. Unsafe paths, absolute paths, and parent-directory traversal are
skipped.

---

## File-by-File Migration Planning

The file migration planner prepares full Pascal unit migration jobs. It does
not call an LLM and does not write Java files. It enumerates source files,
derives target Java package paths, records symbols, and orders jobs for later
batch generation.

Plan a single unit:

```powershell
python -m repository_intelligence.modernization.file_migration --units uFileSource --json
```

Include complete Pascal unit source in each job:

```powershell
python -m repository_intelligence.modernization.file_migration --units uFileSource --include-source --json
```

Plan a source subtree:

```powershell
python -m repository_intelligence.modernization.file_migration --include "src/filesources/*.pas" --exclude "*/wfxplugin/*" --limit 25 --json
```

Print a compact human-readable plan:

```powershell
python -m repository_intelligence.modernization.file_migration --include "src/filesources/*.pas" --limit 10
```

Each job contains:

```text
job_id
sequence
source.unit
source.file
source.path
source.dependencies
source.dependents
source_extraction.available
source_extraction.extraction_kind
source_extraction.path
source_extraction.line_count
source_extraction.character_count
source_extraction.source
target.package
target.directory
target.file_hint
symbols.classes
symbols.methods
ordering.mode
ordering.position
ordering.wave
ordering.internal_dependencies
ordering.prior_internal_dependencies
ordering.later_internal_dependencies
ordering.external_dependencies
ordering.internal_dependents
ordering.dependency_ready
ordering.cycle_participant
planning_notes
```

The plan also contains `dependency_ordering`, which summarizes the selected
unit graph:

```text
dependency_ordering.ordered_units
dependency_ordering.waves
dependency_ordering.internal_edge_count
dependency_ordering.external_edge_count
dependency_ordering.cycle_count
dependency_ordering.cycles
```

The default order is dependency-first. It places selected dependency units
before selected dependent units and groups ready units into migration waves.
Source order can be requested with:

```powershell
python -m repository_intelligence.modernization.file_migration --include "src/filesources/*.pas" --order source
```

---

## File-Oriented Migration Prompts

File-oriented prompts consume file migration jobs with complete Pascal source
and prepare one LLM prompt per Pascal unit. This is the prompt path intended for
full file-by-file Delphi to Java migration.

Generate a prompt for one unit:

```powershell
python -m repository_intelligence.modernization.file_prompts --units uFileSource --json
```

Generate prompts for a source subtree:

```powershell
python -m repository_intelligence.modernization.file_prompts --include "src/filesources/*.pas" --limit 5 --json
```

Limit source included per prompt:

```powershell
python -m repository_intelligence.modernization.file_prompts --units uFileSource --max-source-chars 60000 --json
```

Each prompt package includes:

```text
plan
prompts[].job_id
prompts[].source
prompts[].target
prompts[].messages
prompts[].sections.job
prompts[].sections.dependencies
prompts[].sections.symbols
prompts[].sections.target_design
prompts[].sections.source
prompts[].sections.response_schema
prompts[].prompt
prompts[].statistics
```

The prompt asks the model to return only the standard generation JSON shape:

```text
files[]
classes[]
methods[]
notes[]
unresolved_items[]
```

---

## Batch File Generation

Batch file generation executes the file-oriented migration prompt flow for one
or more Pascal units. It writes generated Java files, stores raw model output,
stores prompt packages, writes per-file migration artifacts, and writes a run
manifest for later inspection.

Run a dry-run batch for one unit:

```powershell
python -m repository_intelligence.modernization.file_generation --units uFileSource --output-directory output\generated_java --run-directory output\migration_runs
```

Run a model-backed batch:

```powershell
python -m repository_intelligence.modernization.file_generation --backend langchain --units uFileSource --output-directory output\generated_java --run-directory output\migration_runs --validate
```

Run a limited source subtree:

```powershell
python -m repository_intelligence.modernization.file_generation --backend langchain --include "src/filesources/*.pas" --limit 5 --output-directory output\generated_java --run-directory output\migration_runs --validate
```

Prevent overwrites:

```powershell
python -m repository_intelligence.modernization.file_generation --units uFileSource --output-directory output\generated_java --no-overwrite
```

Inspect canonical shared support contracts:

```powershell
python -m repository_intelligence.modernization.shared_support list
python -m repository_intelligence.modernization.shared_support render
```

Write only the canonical shared support files:

```powershell
python -m repository_intelligence.modernization.shared_support write --output-directory output\generated_java
```

Resume an interrupted or partially failed batch run:

```powershell
python -m repository_intelligence.modernization.file_generation --resume-run output\migration_runs\<timestamp> --backend langchain --output-directory output\generated_java --validate
```

When `--resume-run` is used, completed jobs with their prompt, raw output,
artifact, and written-file metadata are reused without calling the backend.
Missing, failed, or incomplete jobs are generated again. Use `--force-rerun`
with `--resume-run` to regenerate completed jobs intentionally.

If a run stops before `manifest.json`, `jobs.jsonl`, or `artifacts.jsonl` are
written, resume falls back to the durable per-file artifacts in
`artifacts/*.json`. This allows interrupted runs to continue from completed
artifact-backed jobs instead of starting again from the first planned unit.

Each run creates:

```text
output/migration_runs/<timestamp>/manifest.json
output/migration_runs/<timestamp>/jobs.jsonl
output/migration_runs/<timestamp>/artifacts.jsonl
output/migration_runs/<timestamp>/artifacts/*.json
output/migration_runs/<timestamp>/prompts/*.json
output/migration_runs/<timestamp>/raw_outputs/*.txt
output/migration_runs/<timestamp>/validation_reports/*.json
```

Each `artifacts/*.json` file is the durable review record for one Pascal unit.
It links the source file, target Java hint, prompt package, raw model output,
generated Java file records, write/skipped status, validation report, notes,
and unresolved migration items. The artifact stores source extraction metadata,
but not the full Pascal source text, because the full source already exists in
the corresponding prompt package.

The generated Java files are written under `--output-directory` using the paths
returned by the model. Batch generation writes canonical shared support files
for common Pascal runtime abstractions before file jobs run. Current shared
support files include:

```text
org/doublecmd/runtime/io/TSeekOrigin.java
org/doublecmd/runtime/io/TStream.java
org/doublecmd/runtime/checksum/DCCrc32.java
```

File prompts instruct the model to import these contracts instead of generating
local copies. During batch generation, paths written by earlier jobs in the same
run and canonical shared support type names are protected. If a later job
generates the same Java path or a local copy of a shared support type, that file
is skipped and the job is marked with a `write_conflict` status instead of
silently overwriting or duplicating support output.

Use `--no-shared-support` to disable shared support writing/protection for a
diagnostic run. Use `--overwrite-shared-support` to refresh the canonical
support files in the output directory.

Batch manifests also include:

```text
batch_validation.status
batch_validation.summary
batch_validation.findings
```

Batch validation reports duplicate generated file paths and duplicate top-level
Java type declarations across jobs. These checks run even when per-job
`--validate` is not enabled.

---

## Generated Code Validation

Generated Java validation checks the structured generation payload before a
developer reviews or applies the output. The base validation does not require a
JDK. It checks for:

* missing generated files
* unsafe or non-Java output paths
* non-Java language markers
* markdown fences inside source content
* structured JSON accidentally stored as Java source
* unbalanced Java delimiters
* missing or invalid Java package declarations
* package-to-path mismatches
* public type names that do not match file names
* duplicate generated file paths
* duplicate top-level Java type declarations
* declaration-like words inside comments ignored during type detection
* placeholder implementation text
* unresolved migration items

Validate as part of generation:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --types class --limit 5 --validate
```

Print the generation package with the attached validation report:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --types class --limit 5 --validate --json
```

Also compile generated Java with `javac` when a JDK is installed:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --types class --limit 5 --compile-validation
```

Validate a saved generation JSON file:

```powershell
python -m repository_intelligence.modernization.validation generation-result.json --json
```

Validate piped generation JSON:

```powershell
python -m repository_intelligence.modernization.generation "Modernize TFileSource to Java" --types class --limit 5 --json |
  python -m repository_intelligence.modernization.validation --json
```

Validation results include:

```text
generation.validation.status
generation.validation.passed
generation.validation.summary
generation.validation.findings
generation.validation.files
```
