# The README results markers, and the edit `make verify-docs` is waiting for

`make verify-docs` runs `evals/harness/verify_docs.py`. It regenerates the results tables from
`results/metrics.json` with the same function `make report` uses (`evals.harness.tables.markdown`)
and diffs them against the block README.md carries between two HTML comments. This page states the
markers, the exact block, and the edit the lead makes once the first sweep exists. It edits nothing.

## The invocation

```
verify-docs:
	uv run python -m evals.harness.verify_docs
```

Defaults, all from `build_parser()` in the module: `--metrics results/metrics.json`,
`--readme README.md`, `--split test`. The Makefile passes no flags, so **the block in README.md is
the test split**, not dev. `--emit` prints the block and writes nothing.

## The markers

Two literal lines, byte for byte (`BEGIN` and `END` in the module):

```
<!-- metrics:begin -->
<!-- metrics:end -->
```

`extract()` takes everything between the first `BEGIN` and the first `END` after it. A README with
neither marker, or with them nested or out of order, is exit 2 and a printed instruction
(`MARKER_HELP`), never a silent pass. README.md already carries the pair, at lines 85 and 91.

## The block that must sit between them

`generate()` builds it as: the **first** Markdown table under `## test` in the generated report, a
blank line, the **second** table under `## test`. Nothing else. In the report those two tables are

1. the three-row primary table (`| Metric | Simple baseline | Agent solution | Change |`), and
2. the secondary table (`| Row | Baseline | Advanced |`), fourteen rows: the twelve in `SECONDARY`
   (`evals/harness/tables.py`:19-32) plus the inserted `Regressions` and `Machine minutes per run`
   rows. The emitted sample below has the same fourteen.

Everything the report prints around them stays out: the "Spread of the eval (std over cases)"
sentence that sits *between* the two tables in `results/report.md`, the McNemar and bootstrap lines
after them, and the dev section. `tables_for()` collects only lines starting with `|`, which is why
the prose between the tables disappears from the comparison and must not be pasted into the README.

Comparison is byte for byte after `normalise()`: CRLF becomes LF, trailing whitespace on each line
is dropped, blank lines at the two ends are dropped. Nothing else is forgiven. A changed word, a
changed number, an extra sentence inside the markers, all fail.

Shape of the emitted block, from the synthetic metrics object in `tests/test_verify_docs.py`
(`uv run python -c` against that fixture; the numbers below are that fixture's, not measurements):

```
<!-- metrics:begin -->
| Metric | Simple baseline | Agent solution | Change |
|---|---|---|---|
| Erasure-inventory F1 (test, mean of seeds) | 0.60 ± 0.02 | 0.90 ± 0.02 | +0.30 |
| Human time per task | 42.0 min | 3.5 min | -38.5 |
| Cost per task | $0.30 | $0.51 | +$0.21 |

| Row | Baseline | Advanced |
|---|---|---|
| Pass (runs) | 4/6 | 4/6 |
| Pass (cases, majority of seeds) | 2/2 | 2/2 |
| pass^3 | 1/2 | 1/2 |
| Regressions | n/a (no previous metrics.json) | n/a (no previous metrics.json) |
| False safe (matched) | 3 | 0 |
| Reaching claims on stores not in the manifest | 0 | 0 |
| False safe in a gate-rejected draft | 0 | 0 |
| Unverified per run | 0.50 | 0.50 |
| Invalid verdict for kind | 0 | 0 |
| Bad citations | 0 | 0 |
| Cost per run | $0.30 | $0.51 |
| Turns · tool calls | 11.0 · 17.0 | 11.0 · 17.0 |
| Machine minutes per run | 2.0 min | 4.0 min |
| success + failure = n | 6 + 0 = 6 | 6 + 0 = 6 |
<!-- metrics:end -->
```

## Exit codes, and what they look like today

| Code | Meaning | Observed 2026-08-29 |
|---|---|---|
| 0 | the README block equals the generated block | not reachable yet |
| 1 | they differ; a unified diff on stdout, the regenerate hint on stderr | not reachable yet |
| 2 | the comparison cannot be made | this is today's state |

```
$ make verify-docs
uv run python -m evals.harness.verify_docs
no /Users/tun/Documents/micro1-hackathon/results/metrics.json: nothing to verify the README against yet. Run `make eval-replay` (or `make report`) first; before the first sweep this is the expected state.
make: *** [verify-docs] Error 2
```

Exit 2 stops before the README is read, so the placeholder block now in README.md is not yet being
caught. It will be, the moment `results/metrics.json` lands.

## The edit the lead makes (after Sweep C and `make report`)

1. `uv run python -m evals.harness.verify_docs --emit > /tmp/block.md` (default split `test`).
2. Replace README.md lines 85 to 91 inclusive, **markers included**, with that file's contents.
   `--emit` prints the markers itself, so the paste is a whole-block replacement, not an insert.
3. `make verify-docs`, expect `verify-docs OK: README.md matches the test tables in metrics.json`.
4. Commit README.md and `results/metrics.json` in the same commit. They are one artefact now.

Three consequences of that paste, each needing a prose edit **outside** the markers:

- The F1 row label becomes `Erasure-inventory F1 (test, mean of seeds)`, and its Change cell is a
  plain signed delta (`+0.30`). The bootstrap CI the current placeholder puts in that cell is not in
  the generated table; if the README should quote the interval, it goes in the paragraph below the
  markers, where `comparison.test.f1_bootstrap.ci95` is already cited.
- The Human time and Cost cells lose their parentheticals. Generated cells are bare
  (`42.0 min`, `3.5 min`, `-38.5`), the delta is `gate − manual` with no unit and no sign flip. The
  explanation the placeholder row carries ("hand-labelling", "the machine minutes are unattended")
  must move into prose. Machine minutes are in the secondary table, so no information is lost.
- The secondary table arrives in the README. Line 102 today says the secondary rows live in
  `results/metrics.json` via `make report`; after the paste that sentence is only true of dev.

## Traps

- **Do not paste from `results/report.md`.** It carries the "Spread of the eval" sentence between
  the two tables, and the block would then differ from `--emit` at the first prose line.
- **Never run `make report --prev ...` on the way to generating the README block.** `verify_docs`
  calls `markdown(metrics)` with no previous file, so the two Regressions cells it expects are
  always `n/a (no previous metrics.json)`. A report generated with `--prev` prints case names there
  and the README pasted from it fails the diff for a reason that looks like nothing.
- No hand-typed numbers, ever. A number rounded by hand differs in the last digit and exits 1.
- Placeholders elsewhere in the README (`[identity_check.n]`, `[arms.baseline.test.false_safe_total]`,
  the REPRODUCE.md ones) are outside the markers and outside this checker. They are a separate
  pass and nothing fails if they are forgotten. Grep for `[` + `arms.` and `[identity_check` before
  submission.
- The dev tables are not checked by anything. If the README ever quotes a dev number inside the
  markers, the diff fails; keep dev in prose with its source named.

## Checking the wiring before a sweep exists

The comparison can be rehearsed offline against the synthetic metrics object the tests use:

```
uv run python - <<'PY'
import json, sys, pathlib
sys.path.insert(0, "tests")
from test_verify_docs import metrics_object
pathlib.Path("/tmp/m.json").write_text(json.dumps(metrics_object(), indent=2))
PY
uv run python -m evals.harness.verify_docs --metrics /tmp/m.json --split test --emit
```

That prints the block above and touches no repository file. `uv run pytest -q tests/test_verify_docs.py`
covers the same paths (markers absent, nested, drifted numbers, both splits).
