# ARCHITECTURE.md

# Repository Intelligence System Architecture

> This document describes the complete software architecture of the Repository Intelligence System, including both the current implementation and the planned long-term architecture.

---

# 1. System Overview

The Repository Intelligence System is designed to transform a large software repository into a structured knowledge base that can be queried using natural language.

The project is intentionally divided into independent layers.

```text
                   Source Repository
                          │
                          ▼
                  Parsing Layer
                          │
                          ▼
                  Repository Index
                          │
                          ▼
                  Graph Generation
                          │
                          ▼
                 Validation Pipeline
                          │
                          ▼
              Repository Intelligence
                          │
                          ▼
                 Semantic Retrieval
                          │
                          ▼
                 LangChain Agent
                          │
                          ▼
                  Natural Language
```

Every layer has a single responsibility.

---

# 2. Architectural Principles

The following principles govern every design decision.

## Separation of Responsibilities

Each layer has exactly one responsibility.

Example:

* Parser → Parse Pascal
* Validator → Validate repository
* Repository → Store repository state
* Search → Search repository
* LangChain → Orchestrate reasoning

No layer should duplicate functionality from another.

---

## Single Source of Truth

Generated repository indices are the authoritative representation of the repository.

All future processing operates on these indices.

Source code should never be reparsed by downstream components.

---

## Static Analysis First

The project intentionally relies on static analysis.

No compilation or runtime execution is required.

This ensures portability and deterministic behaviour.

---

## Language Independence

Although the initial implementation targets Pascal, the overall architecture should support additional languages by replacing only the parser layer.

Future parsers may include:

* C++
* Java
* Python
* Go
* Rust

The intelligence layer should remain language-agnostic.

---

# 3. Layered Architecture

---

## Layer 1 — Parsing

Purpose:

Convert source code into Abstract Syntax Trees.

Current implementation:

* Tree-sitter
* Custom Pascal grammar
* Visitor-based extraction

Responsibilities:

* Parse source files
* Walk AST
* Extract repository entities

Outputs:

* Units
* Classes
* Fields
* Methods
* Dependencies

---

## Layer 2 — Repository Index

Purpose:

Convert AST information into structured JSON.

Artifacts:

* repository_index.json

This is the canonical repository database.

Every other graph is derived from this file.

---

## Layer 3 — Graph Generation

Purpose:

Generate structural relationships.

Graphs include:

### Dependency Graph

Unit imports.

### Class Hierarchy

Inheritance relationships.

### Method Index

Canonical method definitions.

### Call Graph

Static caller → callee relationships.

Future graphs:

* Composition graph
* Interface implementation graph
* Event graph
* Data flow graph
* Control flow graph

---

## Layer 4 — Validation

Purpose:

Guarantee correctness of generated indices.

Validation includes:

* duplicate detection
* missing references
* graph consistency
* inheritance validation
* schema validation
* repository statistics

Future validation:

* call graph correctness
* unreachable methods
* orphan classes
* dependency cycles
* AST integrity

Validation is mandatory before the intelligence layer executes.

---

## Layer 5 — Repository Intelligence

Purpose:

Provide a high-performance query interface over the repository.

Modules:

loader.py

repository.py

symbol_table.py

graph_api.py

search.py

context_builder.py

No module inside this layer should access raw JSON directly except loader.py.

---

## Layer 6 — Semantic Layer

Purpose:

Enable natural-language understanding.

Components:

Embeddings

Vector database

Method summaries

Class summaries

Unit summaries

Future:

Hybrid retrieval

Keyword + graph + semantic search

Current implementation:

Stage 4.1 generates embedding documents and local deterministic embedding
artifacts from repository metadata. The current artifacts are written to
output/embeddings and are intended for later vector database ingestion.

The semantic layer should keep embedding generation separate from vector
storage and semantic retrieval so providers and databases can be replaced
independently.

Stage 4.2 adds a persistent ChromaDB vector store under output/chroma. The
store ingests precomputed embedding artifacts and exposes count/query access to
the collection. Hybrid retrieval and repository-aware semantic search remain a
separate layer above the vector store.

Stage 4.3 adds hybrid retrieval above lexical search, ChromaDB vector search,
and graph traversal. The hybrid layer combines per-source scores and returns
ranked repository documents with score provenance for manual validation.

Stage 4.4 adds deterministic repository summaries for methods, classes, units,
subsystems, and repository architecture. These summaries are generated from the
existing repository indices and graphs, not from source reparsing or LLM calls,
so they are reproducible and suitable as stable agent context.

Stage 4.5 adds semantic search over the ChromaDB vector collection. Semantic
search is separate from hybrid retrieval: it returns direct vector matches with
optional summary enrichment, while hybrid retrieval blends vector, lexical, and
graph evidence.

Stage 4.6 adds modernization context assembly above retrieval and summaries.
It builds a structured task packet containing hybrid results, semantic
neighbours, summary records, graph relationships, and bounded source snippets.
This is the bridge between repository search and future code modernization
agents.

---

## Layer 7 — AI Agent

Purpose:

Reason over repository knowledge.

Current target:

LangChain

Future alternatives:

* LangGraph
* LlamaIndex
* Custom orchestration

The agent should remain replaceable.

Repository APIs must not depend on the agent framework.

Current implementation:

repository_intelligence.agent provides a LangChain-backed agent wrapper,
bounded conversation memory, prompt instructions, deterministic local tool
routing for validation, and optional model-backed execution through
LangChain's create_agent API.

---

# 4. Repository Intelligence Architecture

```text
Repository

│

├── Loader

│

├── Repository

│

├── Symbol Table

│

├── Graph API

│

├── Search

│

├── Context Builder

│

├── Chroma

│

├── Semantic

│

├── Summaries

│

└── LangChain Tools
```

The Repository object owns all repository state.

Every tool interacts only with Repository.

---

# 5. Planned Repository API

The Repository object should expose functionality including:

find_unit()

find_class()

find_method()

find_file()

get_dependencies()

get_dependents()

get_parent()

get_children()

get_callers()

get_callees()

search_symbols()

statistics()

Future APIs:

execution_path()

impact_analysis()

semantic_search()

architecture_summary()

dead_code()

---

# 6. LangChain Architecture

LangChain should function purely as an orchestration layer.

Each tool should wrap exactly one Repository API.

Example:

```text
find_class()

↓

Repository.find_class()

↓

Repository indices

↓

Result
```

Business logic belongs inside Repository.

---

# 7. Context Construction

The Context Builder is responsible for assembling relevant repository context before invoking the LLM.

Input:

Natural-language query

Output:

Repository context

Example:

User:

Explain checksum calculation.

Context Builder collects:

* relevant methods
* related classes
* dependency graph
* call graph
* inheritance
* semantic neighbours

Only then is the LLM invoked.

---

# 8. Planned Repository Tools

Core tools:

Find Unit

Find Class

Find Method

Find File

Find Callers

Find Callees

Find Dependencies

Find Dependents

Find Parent

Find Children

Search Symbols

Semantic Search

Execution Path

Impact Analysis

Repository Statistics

Architecture Summary

---

# 9. Future Development Phases

## Phase A

Repository Intelligence

(Current)

---

## Phase B

Semantic Search

ChromaDB

Embeddings

Hybrid retrieval

---

## Phase C

Repository Summarization

Generate summaries for:

Units

Classes

Methods

Subsystems

Architecture

---

## Phase D

Natural Language Assistant

Explain repository behaviour.

Locate implementations.

Trace execution.

Recommend modifications.

Analyse impact.

---

## Phase E

Code Modernization

Assist developers in modernising legacy Pascal code.

Examples:

Replace deprecated APIs

Refactor duplicated logic

Identify long methods

Suggest design improvements

Improve naming consistency

Recommend modularisation

Support migration to newer language versions

Future:

Automatic refactoring suggestions.

---

## Phase F

Testing and Validation Intelligence

Future capabilities:

Generate unit tests

Generate integration tests

Generate regression tests

Identify untested methods

Estimate change risk

Predict affected modules

Generate repository health reports

Static verification of generated code.

---

## Phase G

Developer Assistance

Repository chat.

Architecture explanations.

Onboarding support.

Feature localisation.

Implementation guidance.

Pull request review assistance.

Documentation generation.

---

# 10. Quality Assurance

Future quality pipeline:

```text
Parse Repository

↓

Generate Indices

↓

Validate Repository

↓

Run Repository Tests

↓

Run Graph Validation

↓

Run Intelligence Tests

↓

Run Agent Tests

↓

Publish
```

Every stage should be independently testable.

---

# 11. Testing Strategy

Testing will eventually be divided into several layers.

Parser Tests

Visitor Tests

Repository Tests

Graph Tests

Validation Tests

Search Tests

Context Builder Tests

Tool Tests

Agent Tests

End-to-End Tests

Regression Tests

Performance Tests

Benchmark Suite

Every major component should have an independent test suite.

---

# 12. Continuous Integration

Planned CI pipeline:

Repository validation

Unit testing

Graph validation

Coverage reporting

Performance benchmarks

Documentation generation

Packaging

Future:

GitHub Actions

Automated releases

Artifact generation

---

# 13. Performance Goals

Repository loading:

< 5 seconds

Repository queries:

< 10 ms

Graph traversal:

< 50 ms

Semantic retrieval:

< 500 ms

LLM context generation:

< 2 seconds

---

# 14. Extensibility

Future support:

Additional programming languages

Additional graph types

Alternative LLM providers

Alternative embedding models

Alternative vector databases

Plugin architecture

Distributed indexing

Incremental repository updates

---

# 15. Long-Term Vision

The completed Repository Intelligence System should function as an AI software engineer capable of understanding, navigating, analysing and reasoning over an entire software repository.

The system should be able to answer architectural questions, explain execution flow, assist with development, recommend improvements, generate documentation, support testing, and guide code modernization while remaining modular, language-independent and extensible.

This document serves as the architectural blueprint for all future development. New features should extend the existing layered architecture rather than bypassing or replacing it.
