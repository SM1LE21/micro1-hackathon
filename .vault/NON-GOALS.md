# NON-GOALS

What we deliberately do not build, so scope stays fixed. Additions allowed; removals need an ADR.

- No product polish beyond what the demo path and eval need.
- No multi-agent orchestration unless a measured iteration shows the single-threaded loop failing for a reason orchestration fixes.
- No live external side effects: consequential actions are sandboxed or simulated, human approval before anything irreversible.
- No private or client data. Public or synthetic only.
- No feature that does not map to a rubric line.
- [TO FILL: direction-specific exclusions after Q1]
