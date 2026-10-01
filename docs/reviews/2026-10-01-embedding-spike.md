# Embedding-quality spike

| | |
|---|---|
| Date | 2026-10-01 |
| Question | Which embedding model should ReasonHold default to, and how much retrieval quality does a smaller model lose against today's `qwen3-embedding:4b`? |
| Status | Throwaway probe; the code is not kept. Feeds decision `default-embedding-qwen3-0.6b`. |

## Method

- Corpus: all 5,157 chunks of Ariadne's live `AriadneDoc` collection, exported read-only, rendered with docs-rag's `render_embedding_text` (metadata headers plus body, truncated to 12,000 characters). Queries embedded raw, as `server.py` does.
- 40 questions written by Claude against a fixed-seed sample of target chunks: 14 architecture/spec sections, 10 other markdown (plans, skills, deployment), 8 decisions, 5 Python, 3 SQL functions. One target per question.
- Each model embedded corpus and questions through Ollama; cosine similarity ranked in memory. Metrics: hit@1, hit@5, hit@10, mean reciprocal rank (MRR).
- Hosted providers were not tested (no new paid services).

## Results

| Model | Dims | hit@1 | hit@5 | hit@10 | MRR | Embed 5,157 chunks |
|---|---|---|---|---|---|---|
| `qwen3-embedding:4b` | 2,560 | 45.0% | 77.5% | 85% | 0.59 | 176 s |
| `qwen3-embedding:0.6b` | 1,024 | 55.0% | 75.0% | 80% | 0.64 | 92 s |
| `nomic-embed-text:latest` | 768 | 42.5% | 75.0% | 80% | 0.56 | 25 s |

By question category (hit@5 / MRR):

| Category | `qwen3-embedding:4b` | `qwen3-embedding:0.6b` | `nomic-embed-text` |
|---|---|---|---|
| Architecture/spec | 11/14 / 0.71 | 12/14 / 0.83 | 11/14 / 0.74 |
| Other markdown | 8/10 / 0.50 | 6/10 / 0.50 | 6/10 / 0.30 |
| Decisions | 8/8 / 0.72 | 8/8 / 0.70 | 8/8 / 0.84 |
| Python | 4/5 / 0.55 | 4/5 / 0.70 | 4/5 / 0.42 |
| SQL functions | 0/3 / 0.03 | 0/3 / 0.01 | 1/3 / 0.09 |

## Reading

- The three models are statistically indistinguishable at this sample size: one question is 2.5 points, and the hit@5 gap between `4b` and the others is a single question.
- `qwen3-embedding:0.6b` has the best hit@1 and MRR, the best architecture/spec scores, vectors 2.5x smaller and half the embedding time. The 4B model buys nothing measurable on this corpus.
- SQL-function questions fail on every model: the documentation that describes a function outranks its SQL. This supports R-13 (exact symbol queries for code) and the later Serena seam.
- Four questions missed the top 10 on every model (two vague plan or justfile fragments, two SQL).

## Caveats

- Single-target scoring undercounts: other chunks that also answer a question count as misses. The comparison between models is fair; absolute levels are low.
- Questions were written by Claude, not by users.
- `nomic-embed-text` query latency (333 ms) is probably an Ollama model-swap artifact; the Qwen models measured 9 to 12 ms.

## Questions and target ranks

| # | Question | Target | qwen3-embedding:4b | qwen3-embedding:0.6b | nomic-embed-text:latest |
|---|---|---|---|---|---|
| 0 | Which database functions does the CLI use to manage the processing queue and clean up a project? | `docs/architecture/database-schema.md` markdown_section | 1 | 1 | 1 |
| 1 | Why should acquisition metadata like crawl batch info not be copied onto every artifact row? | `docs/specs/2026-03-03-ingest-manager-design.md` markdown_section | 1 | 1 | 2 |
| 2 | Where in the UI does a user configure named entity extraction rules for a project? | `docs/specs/2026-03-09-ui-project-management-design.md` markdown_section | 1 | 1 | 1 |
| 3 | Which documentation hygiene checks always run regardless of which code changed? | `docs/specs/2026-08-19-doc-code-mapping-design.md` markdown_section | 19 | 22 | 13 |
| 4 | Why was the document viewer in the corpus browser postponed? | `docs/specs/2026-03-10-ui-corpus-browser-design.md` markdown_section | 9 | 1 | 1 |
| 5 | What tables support multiple projects and user accounts? | `docs/architecture/database-schema.md` markdown_section | 2 | 1 | 6 |
| 6 | How does a user switch between projects in the web interface? | `docs/specs/2026-03-09-ui-project-management-design.md` markdown_section | 1 | 1 | 1 |
| 7 | Why did we choose Scrapy with Playwright for downloading government websites? | `docs/architecture/design-decisions.md` markdown_section | 1 | 1 | 1 |
| 8 | What gets logged when entities are dropped during cleaning after NER? | `docs/specs/2026-03-17-post-ner-entity-cleaning-design.md` markdown_section | 9 | 2 | 2 |
| 9 | Which stored procedures let analysts group entities into named views? | `docs/architecture/database-schema.md` markdown_section | 1 | 1 | 1 |
| 10 | What is the scope of the web UI design for listing and creating projects? | `docs/specs/2026-03-09-ui-project-management-design.md` markdown_section | 1 | 1 | 1 |
| 11 | Where does aggregation happen for the salience signal validation report? | `docs/specs/2026-09-18-salience-signal-validation-design.md` markdown_section | 5 | 14 | 1 |
| 12 | What commands does the ariadne command line offer for crawling and indexing? | `docs/architecture/pipeline-architecture.md` markdown_section | 1 | 1 | 11 |
| 13 | Are file paths on source documents stored as absolute or relative paths? | `docs/specs/2026-03-03-ingest-manager-design.md` markdown_section | 1 | 1 | 1 |
| 14 | How do we validate that the schema deploys with the new indexing queue? | `docs/plans/2026-03-16-pipeline-phase-realignment-plan.md` markdown_section | 1 | 1 | 5 |
| 15 | How were the structure-aware chunkers for docs-rag planned? | `docs/plans/2026-03-09-docs-rag-plan.md` markdown_section | 60 | 5 | 1 |
| 16 | How are the container images built and tagged? | `justfile` markdown_section | 5 | 6 | 5 |
| 17 | Which pipeline phase boundaries must implementation respect, such as which phase writes to Postgres? | `.claude/skills/implement-from-plan/SKILL.md` markdown_section | 1 | 1 | 118 |
| 18 | What happens if store_decision fails after writing to the decision log? | `docs/bugs/2026-08-20-store-decision-persists-before-indexing.md` markdown_section | 2 | 14 | 3 |
| 19 | How does the documentation audit verify that every queue has a consumer? | `.claude/skills/sync-docs/SKILL.md` markdown_section | 2 | 1 | 12 |
| 20 | How do I restore the postgres database from a dump on the host? | `docs/plans/2026-08-07-host-provisioning-plan.md` markdown_section | 13 | 24 | 124 |
| 21 | How does the docs audit compare documented stored function signatures with what is actually deployed? | `.claude/skills/sync-docs/SKILL.md` markdown_section | 1 | 2 | 8 |
| 22 | What should happen to the nvidia driver settings in the ansible group vars? | `docs/plans/2026-08-07-host-provisioning-plan.md` markdown_section | 2 | 19 | 2 |
| 23 | Can an agent decide on its own to skip the feature workflow? | `.claude/skills/feature-workflow/SKILL.md` markdown_section | 4 | 1 | 2 |
| 24 | Which model and sampling settings were chosen for the golden set LLM judge? | `docs-rag/decisions.jsonl` decision | 2 | 3 | 1 |
| 25 | How is substrate reality split between design review and the docs audit? | `docs-rag/decisions.jsonl` decision | 2 | 2 | 2 |
| 26 | What happens when a Docling conversion fails, does it fall back to reading raw text? | `docs-rag/decisions.jsonl` decision | 1 | 1 | 1 |
| 27 | Do we need chunk overlap when chunking by document structure? | `docs-rag/decisions.jsonl` decision | 2 | 2 | 1 |
| 28 | How is the markdown serializer configured for embedding chunks without changing table serialization? | `docs-rag/decisions.jsonl` decision | 4 | 1 | 5 |
| 29 | Why is Ollama published on a loopback port when other services are not? | `docs-rag/decisions.jsonl` decision | 1 | 1 | 1 |
| 30 | Does Ariadne's feature workflow set up git worktrees? | `docs-rag/decisions.jsonl` decision | 1 | 4 | 1 |
| 31 | What does the home page project card grid look like? | `docs-rag/decisions.jsonl` decision | 1 | 1 | 1 |
| 32 | Where are the unit tests for tracked terms database access? | `tests/unit/test_db_remaining.py` python_class | 1 | 1 | 5 |
| 33 | How is the entity cleaning configuration loaded from blocklist files? | `src/indexer/entity_cleaner.py` python_function | 1 | 3 | 2 |
| 34 | How is a document conversion failure recorded in the pipeline service? | `src/services/pipeline.py` python_function | 4 | 1 | 1 |
| 35 | What does the crawl command do when mirroring sites? | `src/cli.py` python_function | 3 | 6 | 20 |
| 36 | What rules decide whether an extracted entity is dropped? | `src/indexer/entity_cleaner.py` python_function | 6 | 1 | 3 |
| 37 | Which function returns counts of documents in each pipeline status? | `src/database/postgres/functions/get_queue_stats.sql` sql_function | 131 | 172 | 162 |
| 38 | How do I look up a project and its document counts by its slug? | `src/database/postgres/functions/get_project_by_slug_sp.sql` sql_function | 19 | 46 | 4 |
| 39 | How do I put every document back on the processing queue for reindexing? | `src/database/postgres/functions/re_enqueue_all.sql` sql_function | 29 | 68 | 473 |
