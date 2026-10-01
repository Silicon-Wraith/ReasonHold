## ReasonHold

This repository uses ReasonHold to say which documents govern which code, which documents are retracted, and which decisions are active.

- At the start of a session, run `reasonhold preamble` and read it. Treat its "Superseded content" rows as current truth.
- Before designing or changing code, run `reasonhold govern <path>` and `reasonhold decisions search "<topic>"`.
- Reading a file directly bypasses the retraction overlay: check `reasonhold govern <path>` before trusting a design document.
- Record decisions with `reasonhold decide` (see `reasonhold decide --help`); never edit `decisions.jsonl` by hand.
- Do not promote candidates or resolve conflicts; those are human steps.

This snippet is unverified for CLIs other than Claude Code: it relies on the agent following AGENTS.md, not on a hook.
