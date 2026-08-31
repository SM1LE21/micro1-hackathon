# Demo run artefacts

Three files from the demo repository D01 (`evals/fixtures/synthetic/D01`, a Django membership site
whose avatar file survives account deletion). D01 is never scored (`evals/split.yaml` `demo:`).

- `D01-s1.jsonl` — the trace of a live `art30 scan` on the advanced arm through the local website,
  `--brain claude`, 2026-08-31. Its `checkpoint` line is the one human gate in this repository's
  traces answered by a person and not by `--approve auto`: `"by":"human"`, `"wait_s":261.826`,
  risk `high`. Every scored trace under `traces/` has `by: simulated` by construction
  (`docs/spec/05-eval-harness.md` §7.1). Local paths were stripped; nothing else was edited.
- `D01-record.md` — the record that run rendered, section D carrying `member.avatar · NOT ERASED`.
- `d01-false-claim.json` — the same run's `record.json` with that one verdict flipped to `erased`,
  for the verifier shot in `docs/video-script.md`:

  ```
  uv run python skill/art30/scripts/verify.py --repo evals/fixtures/synthetic/D01 --record docs/demo/d01-false-claim.json
  ```

  prints `REJECT   member.avatar · erasure.verdict=erased` with the reason (no path from the entry
  point to an object-storage deletion primitive; a row cascade does not delete the file) and exits 1.
  On the true record it prints `accepted` and exits 0.

`evals/harness/trace_check.py` is not run over this directory: check 13 wants the arm as the parent
directory name, which `traces/<arm>/` has and `docs/demo/` does not. Every other check passes on it.
