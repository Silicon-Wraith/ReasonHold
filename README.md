# ReasonHold

ReasonHold tells coding agents what to believe about a repository: which documents govern which code, which documents (or sections) a later decision has retracted, which decisions are active, and where documents conflict. It never generates text; it indexes, ranks and refuses.

## What it keeps

Three committed files, read the same way on every branch:

- `reasonhold.yaml` (or a legacy `sync-doc.yaml`): placement. Areas, checks binding documents to code, global documents, an optional authority ladder.
- `decisions.jsonl`: an append-only decision log. A decision can retract documents (`supersedes`) and retire earlier decisions (`supersedes_records`).
- `reasonhold.pending.jsonl`: an append-only sidecar of agents' proposed bindings, reported conflicts, their resolutions, and mechanical-curation history.

A Weaviate collection per (project, branch) is derived from them and can always be rebuilt.

## Install

    pip install reasonhold            # or: pip install 'reasonhold[agno]'

Requirements: Python 3.11+, a Weaviate instance (local on port 8081 by default, or Weaviate Cloud via `REASONHOLD_WEAVIATE_CLOUD_URL` and an API key in the variable named by `REASONHOLD_WEAVIATE_API_KEY_ENV`), and an embedding service (Ollama with `qwen3-embedding:0.6b` by default, or any OpenAI-compatible endpoint).

## Start

    reasonhold init        # scaffold reasonhold.yaml; review every list
    reasonhold check       # validate the manifest and both logs
    reasonhold index       # build this branch's index
    reasonhold coverage    # what the manifest fails to place (non-zero exit on holes)

## Use

| Need | Command | MCP tool |
|---|---|---|
| What governs this path | `reasonhold govern <path>` | `governing_docs` |
| Search documents and code | `reasonhold search "<query>"` | `search_docs` |
| Search decisions | `reasonhold decisions search "<query>"` | `search_decisions` |
| Record a decision | `reasonhold decide ...` | `store_decision` |
| Retractions for a document | `reasonhold govern <path>` | `retractions_for` |
| Exact symbols | `reasonhold symbols <chunk_type>` | `symbols` |
| Index freshness | `reasonhold freshness` | `freshness` |
| Open conflicts | `reasonhold conflicts` | `conflicts` |
| Promote or reject a proposal | `reasonhold candidates promote <id>`, `reasonhold candidates reject <id>` | none: human only |

Answers say which branch's index they came from and whether it is fresh. Queries never index; a stale index produces a warning, and an exact "nothing found" from a stale index is refused.

## Wire it into agents

- **MCP (stdio):** add `src/reasonhold/resources/mcp.json` to your client's MCP configuration (`reasonhold mcp`).
- **Claude Code session start:** merge `resources/hooks/claude-settings.json` into `.claude/settings.json`. The preamble fails open and fits in 60 lines and 4096 bytes.
- **Re-index after merges:** copy `resources/hooks/post-merge` to `.git/hooks/post-merge` and make it executable.
- **Skills:** `reasonhold skills install [--root <repo>]` copies the skill pack into `.claude/skills/` and writes `.claude/skills/.reasonhold-version`. It replaces only skill directories it installed and refuses if another directory has a packaged skill's name. The preamble says when the installed pack is missing or from another version: "skills from <x>, package <y>: run `reasonhold skills install`". For other CLIs, append `resources/agents-snippet.md` to `AGENTS.md`; that path is unverified until tested per CLI.
- **Agno:** `from reasonhold.agno import ReasonHoldTools, ReasonHoldKnowledge, reasonhold_context`.

Find the resources directory with `python -c "import reasonhold, pathlib; print(pathlib.Path(reasonhold.__file__).parent / 'resources')"`.

## One project per location

By default a session serves its own repository's knowledge base and writes only there: `reasonhold mcp` runs at the repository root and answers for that project alone.

Reading another project is opt-in and read-only. Add a local MCP entry that is not committed, for example with Claude Code's local scope:

    claude mcp add -s local other-project -- reasonhold mcp --root /path/to/other-repo --read-only

`--read-only` registers only the query tools (`search_docs`, `search_decisions`, `list_indexed_files`, `governing_docs`, `retractions_for`, `decision`, `conflicts`, `symbols`, `freshness`, `coverage`). Decisions, proposals and conflicts are recorded only in the project the session is working in. Keep the other repository's path out of committed configuration; it differs per machine.

## Limits

- Reading a file directly bypasses the retraction overlay. The preamble, `governing_docs` and `retractions_for` are how an agent learns a document is stale.
- Codex and other CLIs are unverified: only Claude Code's SessionStart hook is tested.
- One embedding model per collection; changing it needs `reasonhold index --full`.
- Each branch has its own collection; a new branch starts with a full index.
