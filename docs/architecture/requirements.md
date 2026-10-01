# Auctor — High-Level Requirements

**Status:** DRAFT — first distillation, not yet approved by the operator.
**Source:** `ORIGIN.md` (the founding design record) and the decision store.
Every requirement cites the `ORIGIN.md` section it came from and, where one
exists, the decision record that settled it.

**Sequence note.** `AGENTS.md` sets the order as bridging apparatus → market
research → architecture → specification. The operator started this document **before** market
research, as a starting point ("extract and distill what we have discussed so far
as a starting point", 2026-09-23). So the document leaves out anything that
research is meant to establish. That covers prices and free-tier limits,
competitor positioning, and the claim that no other server models supersession.
Those items are listed under *Deferred to market research*. They are not
asserted here. When research moves a requirement, record a `supersedes` on that
requirement's heading. Do not edit the heading in place.

**Conventions.**

- Each requirement has its own heading, numbered `R-NN`. It is the `supersedes`
  anchor for that requirement, e.g.
  `docs/architecture/requirements.md#R-07`.
- **MUST** means release-blocking. **SHOULD** means expected, but it can be
  deferred with a recorded decision.
- *State* says where the requirement stands in the bridge code (`docs-rag/`).
  **Exists** means the bridge already does it and extraction must keep it.
  **Gap** means it still has to be built. **Partial** means only some of it
  exists.

---

## 1. Purpose

Auctor is an **authority layer over a document corpus**, exposed to coding
agents through MCP. Documentation RAG answers "what is similar?" Auctor answers
"what should I believe?"

A coding agent rarely fails because it couldn't find a related document. It
fails because it found five and believed the wrong one. Auctor answers that
along three axes:

| Axis | Question | Requirements |
|---|---|---|
| **Scope** | Which documents govern *this* module? | R-01 – R-05 |
| **Time** | Which documents are still true *now*? | R-06 – R-09 |
| **Rank** | Who wins when they disagree? | R-10 – R-11 |

Semantic search (R-12) is table stakes. It is not the contribution.

---

## 2. Scope — governing documents

### R-01 Declarative document–code mapping

Auctor MUST read a declarative manifest that binds governing documents to the
code they govern. A document's placement MUST be **declared**, never inferred
from its absence from other lists. An unplaced document has to be detectable
as unplaced.

*Why:* in the originating project, the top-of-ladder requirements document sat
misfiled for a long time because placement was inferred.
*Source:* §3 `sync-doc.yaml`, §4.3. *State:* **Partial.** `manifest.py` parses
`global`/`areas`, but it never reads `checks`, which hold the actual binding.

### R-02 `governing_docs(path)` query

Auctor MUST answer "which documents govern this path?" This covers the
documents themselves and the binding that ties each one to the path. The answer
MUST be available as an MCP tool and as a library call. It is computed from the
manifest, so no model ever parses the manifest by hand.

*Why:* this is the strongest idea in the project and today it has no API. Six
skills in the originating project do this lookup as prose that tells the model
to parse YAML by hand. That approach is untestable, costs context on every call,
and has to be rewritten for every CLI.
*Source:* §4.1. *State:* **Gap — highest-value.**

### R-03 Governance-coverage check

Auctor MUST detect holes in the mapping itself, not only code that disagrees
with its documents:

- a source path that no area covers
- a document that no area, global list or archival list places
- an indexed source file that no binding matches

It MUST run as pure computation, with no model involved and total recall. It MUST
be a portable command that exits non-zero when it finds holes, so a git hook or
CI can call it. Hook wiring comes after the command, not before.

*Why:* checks validate code against whatever the mapping says. When a module
has no governing documents, every check passes.
*Source:* §4.2. *State:* **Gap.**

### R-04 Manifest maintenance: detect → propose → confirm

Users MUST NOT have to maintain the mapping by hand, and a model MUST NOT
write authoritative bindings. Maintenance works in three steps:

1. Computation **detects** a gap.
2. A model **proposes** a fix into a candidates area.
3. A human **confirms** the fix by promoting the candidate.

The governing mapping MUST ignore unconfirmed candidates. Unconfirmed candidates
MUST appear at session start, the same way retractions do (R-08).

*Why:* a wrong binding fails nothing. It silently sends every future design
session for that module to the wrong spec.
*Source:* §4.3. *Decision:* `manifest-maintenance-detect-propose-confirm`.
*State:* **Gap.**

### R-05 Binding capture from the design workflow

When the design workflow writes a document for a module, it SHOULD emit a
candidate binding at that moment, while it knows the binding for certain. A
repo scanner that proposes bindings MAY exist, but only to bootstrap a
project's first manifest.

*Source:* §4.3. *Decision:* `capture-bindings-from-design-workflow`.
*State:* **Gap.** Auctor has no design-workflow skill yet.

---

## 3. Time — decisions and supersession

### R-06 Decision ledger

Auctor MUST keep a structured decision ledger. Each record has a topic, a
decision, the rationale, the alternatives considered, the session context,
tags, a status and its supersessions. The ledger MUST be an append-only file
that can be checked into the project's repository. It is the **source of
truth**. The vector store is a **derived cache** that Auctor MUST be able to
rebuild from the ledger alone.

A new decision MUST be searchable as soon as it is recorded.

*Known gap:* the bridge can only append to the ledger (`docs-rag/server.py:388`).
No tool can mark an earlier record `superseded`, so today a decision can retract
documents but cannot retire another decision. How a record's status changes
over its lifetime is an open question.

*Source:* §3 MCP surface, §3 Substrate. *State:* **Exists** (`store_decision`,
`decisions.jsonl`, `backfill_decisions.py`).

### R-07 Retraction overlay

A decision MUST be able to mark specific documents as no longer true, down to
single sections. Each retraction carries a short statement of what holds now.
Every retrieval result drawn from a retracted document or section MUST carry
that statement inline, along with the decision that retracted it and its date.
A retraction MUST NOT change the retracted document itself.

Retractions MUST name documents only. Code is kept correct by review and tests,
not by retraction.

*Source:* §1 *The two ideas*, §3 *The retraction mechanism*.
*State:* **Exists.** Section anchors are substring-matched against the heading
text, not slugs. That behaviour is part of the contract and must be kept.

### R-08 Session-start preamble

At the start of a session, Auctor MUST show the agent every active retraction,
before the agent reads any document. This is what closes the bypass: an agent
that reads a file directly never sees retrieval-time annotations. The preamble
MUST also show index freshness and unconfirmed manifest candidates (R-04). It
MUST NOT show ordinary decisions. It MUST stay within a size budget that a test
enforces (60 lines / 4 KB today). If it breaks, it MUST fail open, so the
session still starts without it.

The preamble MUST be available as plain command output, so any agent harness
that can prepend text can use it. Claude Code integration is one consumer of
that output, not the definition of it.

*Source:* §3, §5, §7. *State:* **Exists** (`bootstrap.py`, SessionStart hook).
Candidates are **Gap**.

### R-09 Corpus is fully re-embeddable on demand

Retractions are applied to chunks when the corpus is indexed. So a full reindex
MUST always be possible, and it MUST rebuild the collection from scratch rather
than update it in place. Nothing may make the corpus depend on incremental
history.

*Source:* §3 *Critical constraint*, §3 *Hard-won details*. *State:* **Exists.**

---

## 4. Rank — authority

### R-10 Authority ladder declared in the manifest

A project MUST be able to state its own documentation layout and authority
order in the manifest, without editing Auctor's code. Every retrieval result
MUST carry the authority level of the document it came from.

*Why:* today the ladder is hardcoded in `enrichment.py::_classify_authority`,
so a new project has to edit Python to describe its own layout. This is the
one real seam the extraction has to open.
*Source:* §2, §5 readiness check 1. *State:* **Gap.** This is a shipping
prerequisite.

### R-11 Conflicts are surfaced, not silently resolved

When two governing documents disagree, Auctor SHOULD show the conflict. Showing
it means naming both documents and their authority levels, not returning
whichever document ranked highest. Rank decides which document wins. It does
not hide that the two disagreed.

*Why:* an architecture document has *auctoritas* over a spec, but no
*potestas*. Nothing stops someone writing a contradictory spec, which is why a
cross-document conflict check has to exist.
*Source:* §1 *Vocabulary*. *State:* **Gap.** It needs design work: the
mechanism is not specified in `ORIGIN.md`.

---

## 5. Retrieval

### R-12 MCP retrieval surface

Auctor MUST keep the existing four MCP tools. It also adds R-02:

- `search_docs`: semantic search over documents, code and decisions, returning
  area, authority and retraction fields
- `search_decisions`: the same search restricted to decisions
- `store_decision`
- `list_indexed_files`

The decision-status filter SHOULD use the stored status property, not match
text inside the content.

*Source:* §3 MCP surface, §4.7. *State:* **Exists.** The status filter is
**Gap** (minor).

### R-13 Exact queries for absence

Any claim that something is missing MUST be answered by an exact property filter
with total recall. It MUST NOT be answered by vector search. A check that
depends on an exact query MUST NOT quietly fall back to another mode.

*Why:* ranked retrieval gives no completeness guarantee. A result below the
cutoff looks the same as one that doesn't exist.
*Source:* §3 `sync-doc.yaml` (index-mode checks), §8. *State:* **Exists** in
`symbols.py`. It is CLI-only, and whether it becomes an MCP tool is an open
architecture question.

---

## 6. Substrate and index integrity

### R-14 Weaviate, self-hosted and Cloud

Auctor MUST run against self-hosted Weaviate and Weaviate Cloud. Configuration
chooses between them. There MUST NOT be a vector-store abstraction layer.

*Source:* §4.5, §6. *Decision:* `keep-weaviate-support-weaviate-cloud`.
*State:* **Gap** (connection factory, ~15 lines).

### R-15 Embedding provider protocol

Embedding MUST go through one small provider interface that exposes
`embed(texts)`, `dims` and `model_id`. Auctor MUST ship at least an Ollama
implementation and an OpenAI-compatible implementation. Batching and truncation
MUST belong to the provider, not to the indexer. The default provider is not
fixed by this requirement. The retrieval-quality spike decides it (see *Open
questions*).

*Source:* §4.4. *Decision:* `abstract-embeddings-not-llm`. *State:* **Gap.**
Endpoints can already be set through environment variables, and that should
not be rebuilt.

### R-16 Model-identity guard

Auctor MUST refuse to query or extend an index built with a different embedding
model. The check compares the recorded model identity as well as the vector
dimensions. Comparing dimensions alone lets two models with the same dimension
count silently corrupt the index.

*Source:* §4.6. *State:* **Gap.** This is a real latent bug and cheap to fix
now.

### R-17 Preserve hard-won index behaviour

Extraction MUST keep these behaviours, each with its tests:

- exact-match tokenization on file paths
- full reindex recreates the collection
- schema drift on an incremental run raises an error instead of being silently
  repaired
- verified inserts
- stale-chunk deletion
- the binary-file guard

*Why:* each one fixed a data-loss or silent-corruption bug.
*Source:* §2, §3 *Hard-won details*. *State:* **Exists.** The parity test suite
(190 tests at bootstrap) is the gate.

### R-18 Project identity is configuration

Nothing about a project's identity MAY be hardcoded in Auctor's code. That
includes the collection name, the server's instructions text, the ledger path
and the documentation layout (R-10).

*Source:* §2. *State:* **Partial.** It was de-hardcoded in the bridge. See the
decision `docs-rag-is-bridging-apparatus`.

---

## 7. Adoption, portability and shipping

### R-19 Two deployment paths, same code

A solo developer MUST be able to run Auctor with **no local infrastructure**,
meaning a hosted embedding provider plus hosted Weaviate. An organisation that
needs data residency MUST be able to run it fully self-hosted. The two differ
only in configuration.

*Source:* §6. *State:* **Gap** until R-14 and R-15 are built. Whether the
no-infrastructure path is also **zero-cost** is a market-research question
(below).

### R-20 CLI-agnostic server

The MCP server MUST work over stdio with any MCP-capable agent CLI, and nothing
in it may be specific to one CLI. Auctor MUST NOT claim compatibility with a
CLI until someone has verified it.

*Source:* §1 *Vocabulary* (repo topics), §7. *Decision:*
`plan-for-no-community-maintainers`. *State:* **Exists** for the server.
Per-CLI verification is **Gap**.

### R-21 Ship the discipline, not just the server

A release MUST include these as first-class artifacts:

- the manifest format
- a skill pack
- the written retraction discipline
- a session-start integration

Documentation MUST state plainly that reading a file directly bypasses the
overlay. It MUST also cover session-start integration for each supported CLI.

*Why:* the governance loop is the novel part, and it lives in prose. Shipping
the server alone delivers ordinary semantic search.
*Source:* §5, §7. *Decision:* `ship-the-discipline-not-just-the-server`.
*State:* **Partial.** The discipline exists, but it is shaped around Auctor and
has not been shown to work for another project.

### R-22 Proven generic by a second consumer

Before the first public release, a second, unrelated project SHOULD run the
extracted package. Being generic only in principle is not proof.

*Source:* §5 readiness check 2, §10 (Nebulon). *State:* **Open.** See *Open
questions*.

### R-23 Single-maintainer scope

Auctor's scope MUST stay small enough for one maintainer to sustain. Prefer thin
seams to abstractions that need their own upkeep.

*Source:* §9. *Decision:* `plan-for-no-community-maintainers`.

---

## 8. Non-goals

These are deliberately out of scope. Each one points to the record that settled
it. Proposing one again needs new evidence.

| Non-goal | Settled by |
|---|---|
| Code navigation or editing (LSP symbols, reference graph, call sites, refactoring). Auctor is not a Serena replacement. | §8 |
| Generating text, or abstracting over LLM providers | `abstract-embeddings-not-llm` |
| An embedded or zero-infrastructure vector store, or any vector-store abstraction | `keep-weaviate-support-weaviate-cloud`; ledger row §6 *Rejected* is `dismissed` |
| A model writing authoritative manifest bindings without a human confirming them | `manifest-maintenance-detect-propose-confirm` |
| Publishing in order to hand maintenance to a community | `plan-for-no-community-maintainers` |

---

## 9. Open questions — not requirements

Each of these gates or shapes a requirement above. None is decided.

| Question | Affects | Owner |
|---|---|---|
| Retrieval quality of hosted embeddings vs `qwen3-embedding:4b` on this corpus shape. If materially worse, the default provider changes | R-15, R-19 | Spike (§10, §11.3) |
| Multi-project support: one collection name per deployment, and a hosted free tier that may allow only one collection | R-14, R-18, R-19 | Architecture, after research re-verifies tier limits |
| Candidates block inside the manifest, or in a sidecar file | R-04 | Architecture |
| Whether Nebulon becomes a consumer immediately (recommended: yes) | R-22 | Operator |
| Which CLI tools survive extraction, and which become MCP tools (notably exact symbol queries) | R-12, R-13 | Architecture |
| How cross-document conflicts are detected and surfaced | R-11 | Architecture |
| Distribution shape: PyPI, `uvx` from git, or both | R-21 | Architecture |
| How one decision retires another: the ledger is append-only and has no status-change path | R-06 | Architecture |

## 10. Deferred to market research

These are **not asserted** in this document. The facts behind them were verified
on 2026-09-20 and have to be checked again before anyone restates them (see
`AGENTS.md` § Research and external facts).

- Whether any other documentation-RAG or memory server models supersession.
  This is the differentiation claim, and today it holds only for what the
  authors of `ORIGIN.md` knew of.
- Provider pricing, free-tier limits, and whether the no-infrastructure path
  (R-19) also costs nothing.
- Positioning against Serena and other memory servers.
- Evidence for the dormancy of maintainer-less MCP projects.
