# ORIGIN.md extraction triage

**Status:** open — **27 of 50 rows `pending`** as of 2026-09-23 (17 `incorporated`, 5 `already-done`, 1 `dismissed`). `ORIGIN.md` cannot be
deleted until every row is non-`pending`. *(Recounted 2026-09-23 over table rows only. The earlier header read 35 of 51 with 4 `already-done`,
but the table had 33 of 50 with 5. `incorporated` (partial) counts as `incorporated`.)*

Update this count in the same edit that changes a disposition. A gate whose
progress has to be recounted by hand is a gate nobody checks.

**§9's settled decisions are now in the decision store** (2026-09-23): the six
`pending` ones were recorded; the other two were already `already-done`.
The operator recorded them before market research, which this ledger had advised
against because of churn. If research changes one, record a supersession.

**Largest remaining block: §4's build gaps.** Each is now stated as a requirement
in `docs/architecture/requirements.md` (DRAFT). Each stays `pending` until an
architecture or spec document carries its design, not just its requirement.

## Why this document exists

`ORIGIN.md` is bridging apparatus. It is the complete record of the design
conversation that created Auctor, it is **frozen** — never appended to, never
revised — it is gitignored and will never be committed, and it is **deleted** once
its contents have been extracted.

This table is the extraction ledger. It is checked in, so **it outlives
`ORIGIN.md`**: after deletion it is the only surviving record of what the project
believed at its founding and where each idea went. That is its real job. The
decision record `origin-md-is-bridging-apparatus` carries the rationale.

Granularity is **section-level**, matching `ORIGIN.md`'s own headings, because a
section anchor is exactly the anchor a `supersedes` entry would use:

```python
supersedes=[{"path": "ORIGIN.md#6. Infrastructure and adoption economics",
             "retraction_summary": "…"}]
```

Anchors are substring-matched against the chunker's `section_heading`, not a
markdown slug. Sections carrying several separable ideas are sub-rowed; nothing is
split finer than that. Claim-level rows would run past a hundred and drift within
a week.

**Out of scope:** `transcript/2026-09-20-origin-session.jsonl`. It is the raw
session log behind `ORIGIN.md` and exists as audit trail only. `ORIGIN.md` is the
authoritative record and was written by the operator; re-mining the JSONL would
extract the same ideas at lower fidelity.

## Dispositions

| Value | Meaning |
|---|---|
| `pending` | Not yet dealt with. Blocks deletion. |
| `incorporated` | Now asserted by a durable artifact named in *Destination*. |
| `dismissed` | Deliberately not carried forward. *Destination* names the decision recording why. |
| `already-done` | Was an action item; it has been performed. |

A row moves to `incorporated` only when a **named, committed artifact** asserts
it. "An agent read it once" is not extraction — that is precisely the failure mode
Auctor exists to prevent.

## §1 — What Auctor is

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#1. What Auctor is` | Three axes — scope, time, rank. Auctor answers "what should I believe?", not "what is similar?" | `incorporated` | `AGENTS.md` § Purpose |
| `#The two ideas that justify the project` (framing) | Retraction overlay and governing documents are the contribution; `search_docs` is table stakes | `incorporated` | `AGENTS.md` § Purpose |
| `#The two ideas that justify the project` (novelty claim) | No other documentation-RAG or memory MCP server models supersession — scoped "known to the authors of this document" | `pending` | **Market research.** Must not be restated unscoped until research has actually looked |
| `#Vocabulary` | *auctoritas* / *potestas* distinction; lögsögumaður metaphor; name rationale; rejected names | `pending` | Belongs in the public README / docs voice. Not yet written |
| `#Vocabulary` (repo description) | The 203-char GitHub description and the README opening line | `already-done` | `README.md` |
| `#Vocabulary` (repo topics) | Ten topics; withhold `claude-code`/`goose`/`codex` until each client is verified | `pending` | Applies at repo-publish time |

## §2 — Two forks already diverged

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#2. Why this project exists: two forks already diverged` (divergence evidence) | Nebulon sat five months behind; extraction is warranted independently of open-sourcing | `incorporated` | `AGENTS.md` § Bridging apparatus — it is the stated reason the bridge carries an expiry |
| `#2. …` (generality ranking = extraction plan) | `manifest.py` ship as-is; `chunkers/index/schema/server` are forked-not-different; `enrichment.py` is the one real seam | `pending` | **Architecture session.** This is the extraction plan and has no destination doc yet — see `docs/architecture/requirements.md` R-10, R-17, R-18 |
| `#2. …` (project identity is two strings) | Entire hardcoded identity in 3,315 LOC is `COLLECTION_NAME` + the FastMCP `instructions` sentence | `incorporated` | Verified against `config.py`; both retargeted in the bridge. Found a third — the ledger path — recorded in `docs-rag-is-bridging-apparatus` |

## §3 — What exists today

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#MCP surface — four tools, FastMCP over stdio` | The four tools and their return fields | `incorporated` | Verified live at bootstrap; `session-bootstrap` § Retrieval playbook |
| `#CLI tooling — not exposed over MCP` | Seven CLI modules and what each does | `pending` | Architecture session decides which survive extraction and which become MCP tools — see `docs/architecture/requirements.md` §9 open questions |
| `#Substrate` | Weaviate 8081 / Ollama qwen3-embedding:4b 2560d; **JSONL is source of truth, Weaviate a derived cache** | `incorporated` | `AGENTS.md` § Bridging apparatus; it is why the ledger moved to the project root |
| `#The retraction mechanism, end to end` | Five-step flow; anchors are substring-matched not slugs; **retractions apply at index time** so the corpus must stay re-embeddable | `incorporated` | `session-bootstrap`, `reindex-docs` § `--full` is required |
| `` #`sync-doc.yaml` — 624 lines, three sections, two consumers `` | Areas are dispatch units not the mapping; two different glob engines; declared-not-inferred; index-mode checks need total recall | `incorporated` | `sync-doc.yaml` header comments; `reindex-docs` troubleshooting |
| `#Hard-won details worth preserving` | `FIELD` tokenization on `file_path`; `--full` recreates rather than reusing; schema drift raises; dimension probe | `incorporated` | Inherited in the bridge code and asserted by its tests; `--full` semantics in `reindex-docs` |

## §4 — Gaps found, the work to do

Every row here is **build work** and belongs to the architecture/specification
phase. None can be `incorporated` before there is a design document to
incorporate it into.

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#4.1` | `governing_docs(path)` does not exist — the strongest idea has no API. Six skills hand-parse YAML. ~60 lines | `pending` | Architecture session. **Highest-value gap** — see `docs/architecture/requirements.md` R-02 |
| `#4.2` | No governance-coverage check. Orphaned *code* is undetectable. Pure computation, no LLM. Build as a portable command first | `pending` | Architecture session — see `docs/architecture/requirements.md` R-03 |
| `#4.3` | Manifest maintenance is detect → propose → confirm. Auto-population **rejected**. Capture bindings as a byproduct of the design workflow | `pending` | Architecture session. Carries the operator's stated intent that users must not hand-maintain the mapping — see `docs/architecture/requirements.md` R-04, R-05 |
| `#4.4` | Embedding provider seam — `Protocol{embed, dims, model_id}`, Ollama + OpenAI-compatible. ~80 lines. Endpoints are *already* env-configurable | `pending` | Architecture session; gated on the §10 quality spike — see `docs/architecture/requirements.md` R-15 |
| `#4.5` | Weaviate connection factory — two call sites, ~15 lines. Not an abstraction over Weaviate, just its own two modes | `pending` | Architecture session — see `docs/architecture/requirements.md` R-14 |
| `#4.6` | Model-identity guard — a real latent bug. Dimension probe misses two models sharing a dimension count. Persist `model_id` | `pending` | Architecture session. Cheap now, painful after an index is poisoned — see `docs/architecture/requirements.md` R-16 |
| `#4.7` | `search_decisions` status filter substring-matches content although `decision_status` is filterable. Low priority | `pending` | Architecture session — see `docs/architecture/requirements.md` R-12 |

## §5 — What does not ship (the biggest risk)

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#5. What does *not* ship, and why it is the biggest risk` (thesis) | The overlay needs code + hook + prose discipline. Shipping code alone gets a crowded semantic-search repo. The novel part lives in prose | `incorporated` | Decision `docs-rag-is-bridging-apparatus` (its rejected-alternatives list states the reasoning); `AGENTS.md` § Bridging apparatus |
| `#5. …` (readiness check 1) | The authority ladder must move out of Python and into the manifest | `pending` | Architecture session. Still hardcoded in `enrichment.py::_classify_authority` — see `docs/architecture/requirements.md` R-10 |
| `#5. …` (readiness check 2) | A SKILL pack plus written retraction discipline a stranger on another project and another CLI can follow | `pending` | **Started, not done.** `AGENTS.md` Gate + `session-bootstrap` + `reindex-docs` exist but are Auctor-shaped, not portable. Portability needs a second consumer to prove — see `docs/architecture/requirements.md` R-21 |

## §6 — Infrastructure and adoption economics

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#6. Infrastructure and adoption economics` (costs) | Provider pricing; a solo developer runs Auctor at zero cost with zero local infra; Voyage's grant is token-denominated, Cohere's is call-denominated and does not fit | `pending` | **Market research.** Every figure was verified 2026-09-20 and must be re-verified before quoting — `AGENTS.md` § Research and external facts |
| `#6. …` (corpus measurement) | 5,157 chunks / ~1.0M tokens measured; ~1.2M with enrichment headers is an **estimate** and must be measured before publishing | `pending` | Market research / architecture |
| `#6. …` (Weaviate free tier) | Permanent free tier; **binding constraint is "1 collection", not size** | `pending` | Market research. Directly constrains the multi-project question in §10 |
| `#Rejected: embedded / zero-infrastructure vector store` | LanceDB satisfies the capability list and is **rejected anyway** — the interface would mean reimplementing Weaviate. Operator's own judgement | `dismissed` | Settled by the operator in the originating conversation. Re-raising needs new evidence, not a new opinion |

## §7 — Portability across model CLIs

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#7. Portability across model CLIs — three layers` | The stdio server is portable today; the hook and skills are Claude Code-bound and **load-bearing**; reading a file with Read or grep bypasses the overlay entirely | `incorporated` (partial) | The bypass gap is in `session-bootstrap`. The per-CLI porting work Auctor "owes its users" is `pending` — architecture session — see `docs/architecture/requirements.md` R-08, R-20, R-21 |

## §8 — Relationship to Serena

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#8. Relationship to Serena` | Serena is two things; Auctor overlaps only project memories and is strictly richer there. **Auctor is not a Serena replacement** — no reference graph, no edit capability | `pending` | **Market research.** The comparison table is the seed of the competitive analysis and the honest-positioning statement the README needs |

## §9 — Decisions settled, with what was rejected

Eight rows. These are the originating conversation's conclusions. The six not
already done were backfilled into the decision store on 2026-09-23.

| Decision | Disposition | Destination |
|---|---|---|
| Extract `docs-rag` into its own repo | `already-done` | This repository exists |
| Name it **Auctor** | `already-done` | `README.md`, `LICENSE`, PyPI claim still `pending` (§11.1) |
| Keep Weaviate; support Weaviate Cloud | `incorporated` | Decision `keep-weaviate-support-weaviate-cloud`; requirement R-14. Cloud support is still build work |
| Abstract **embeddings**, not "the LLM" | `incorporated` | Decision `abstract-embeddings-not-llm`; requirement R-15. Implementation is §4.4 |
| Manifest maintenance is detect → propose → confirm | `incorporated` | Decision `manifest-maintenance-detect-propose-confirm`; requirement R-04. Implementation is §4.3 |
| Capture bindings as a byproduct of the design workflow | `incorporated` | Decision `capture-bindings-from-design-workflow`; requirement R-05 |
| Ship the discipline, not just the server | `incorporated` | Decision `ship-the-discipline-not-just-the-server`; requirement R-21 |
| Plan for no community maintainers | `incorporated` | Decision `plan-for-no-community-maintainers`; requirement R-23. PAL MCP evidence is still to be re-verified in market research |

Backfilled 2026-09-23. `search_decisions("why did we choose Weaviate")` now
answers from Auctor's own store.

## §10 — Open questions

| Question | Disposition | Destination |
|---|---|---|
| Retrieval quality of hosted embeddings vs `qwen3-embedding:4b` on a corpus of this shape. ~1 hour, ~3 cents. **If quality is materially worse the default provider changes** | `pending` | The §11.3 spike. Gates §4.4 — see `docs/architecture/requirements.md` R-15 and §9 open questions |
| Candidates block inside `sync-doc.yaml` or a sidecar file | `pending` | Architecture session — see `docs/architecture/requirements.md` R-04 and §9 open questions |
| Whether Nebulon becomes a consumer immediately (recommended: yes — forces the seam to be genuinely generic) | `pending` | Architecture session. Also the only way to prove §5's portability claim — see `docs/architecture/requirements.md` R-22 and §9 open questions |
| Multi-project support. `COLLECTION_NAME` is one string; Weaviate Cloud free tier allows one collection. Serena has `activate_project` | `pending` | Architecture session — see `docs/architecture/requirements.md` §9 open questions |
| Licence | `already-done` | MIT, committed `dac4676` |
| Distribution shape — PyPI, `uvx`-from-git, or both | `pending` | Architecture session — see `docs/architecture/requirements.md` §9 open questions |

## §11 — Immediate action items

| Item | Disposition | Destination |
|---|---|---|
| 1. Claim `auctor` on PyPI before the repo goes public | `pending` | **Operator action. Has a clock on it** — verified free 2026-09-20; free names do not stay free |
| 2. Choose a licence | `already-done` | MIT, `dac4676` |
| 3. Run the embedding-quality spike before fixing a default provider | `pending` | Gates §4.4 |
| 4. Record the extraction as a decision in **Ariadne's** store | `pending` | Triggered when the bridge was copied. To be recorded **without** `supersedes` — `docs-rag/` still lives and runs there |
| 5. Begin the architecture/design workflow proper | `pending` (in progress) | Sequence: bridging apparatus ✓ → market research → architecture → specification |

## Provenance

| Section | Asserts | Disposition | Destination |
|---|---|---|---|
| `#Provenance` | Produced 2026-09-20 from Ariadne at `build/container-stack`, commit `8c5c451`. Measurements and prices verified that date; re-check before quoting | `incorporated` | This document's header and `AGENTS.md` § Research and external facts |
