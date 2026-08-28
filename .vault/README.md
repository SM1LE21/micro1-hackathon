# .vault — agent-maintained knowledge base

Working memory for this project. Agents keep it current; Tun reads it, agents write it.

| File | Purpose |
|---|---|
| `STATUS.md` | Current state + next action. Read at every session start, update at every session end. |
| `QUESTIONS.md` | Open decisions waiting on Tun. |
| `AMBIGUITIES.md` | Problem-statement ambiguities: both readings, the chosen one, why. |
| `NON-GOALS.md` | What we deliberately do not build. Scope creep dies here. |
| `adr/` | One architecture decision record per decision. Template: `adr/0000-template.md`. |

Not judge-facing. Judge-facing docs are `README.md`, `REPRODUCE.md`, `CHANGELOG_EVAL.md`, `HOT_TAKE.md` at repo root.
