# 05 — Evaluation harness

Three files under `evals/harness/`: `score.py` turns one record and one manifest into one number, `run.py` produces the runs that get scored, `report.py` turns a directory of runs into the tables the README and `CHANGELOG_EVAL.md` quote. This document fixes the arithmetic precisely enough that two people implementing it separately get the same number, and fixes the two pieces of discipline that are easy to promise and easy to lose: that a failed run is counted, and that the test split is swept at most twice live, with the reported comparison coming from a single recording window (ADR 0005).

**Reads with** `docs/spec/00-contract.md` (§Scoring contract, §Budgets, §Trace contract — it wins), `evals/CASES.md` (the metric, the secondary rows, the definition of a good result, the labelling protocol), `docs/spec/fixture-generator.md` (manifest shape and the `spec_sha256` freeze), `docs/spec/06-traces.md` (what the runner writes and what the report reads back), `docs/spec/04-output-schema.md` (`record.json`), `.vault/adr/0003-runtime-and-api-decisions.md` (§2 no seed, §6 record/replay), `docs/judging/requirements-matrix.md` (E1–E9, X05, X07–X09).

**Assumption, now discharged:** the first draft was written before `docs/spec/01-architecture.md` existed and said that document would win where the two overlapped. It has landed and it does. Three places are amended rather than argued with: replay concurrency is 1, not 8 (§5.2, 01 §8); `metrics.json` carries no wall-clock time (§4.3, §6, §10, 01 Decision 19); and the cost and runtime model is 01 §10's, this document's own estimate having been deleted (§11).

Amended 2026-08-29: three files became twelve, each under AGENTS.md's ~300 lines and each with the same responsibility split further. `run.py` keeps the sweep — the two pre-flight gates, the lock, the launch, the timing file — and hands off to `plan.py` (case selection and the cell plan), `ledger.py` (the test-split ledger and its hash chain) and `cells.py` (the child process, its trace repair and its scoring). `report.py` keeps what it reads off disk and hands off to `stats.py` (aggregates, the exact McNemar, the paired bootstrap, human time) and `tables.py` (the Markdown and the changelog row). `trace_check.py` keeps checks 1 and 2 and the CLI; checks 3 to 18 are `trace_checks.py`. Two files the plan never named were added: `verify_docs.py` (`make verify-docs`) and `failure_index.py` (`traces/failures/README.md`). Every path a sandboxed sweep redirects stays owned by `run.py` and is passed in, so no module-level default is rebound in one file and read in another. `score.py` did **not** split: `art30/verify/rules.py` loads `norm` out of it at run time so the metric and the tool cannot drift, and at 315 lines it is a recorded exception to the line rule. (DEVIATIONS.md D-08)

---

## 1. The number

`evals/CASES.md` §Primary metric: a tuple is `(store, field, reaches_erasure)`; per case precision, recall and F1; mean F1 across cases, dev and test separately. Everything else is a secondary row that is reported and never folded in.

Ten synthetic manifests carry 90 tuples between them, 38 of them reaching erasure and 52 not:

| Case | Tuples | Reaching | Not reaching | Case | Tuples | Reaching | Not reaching |
|---|---|---|---|---|---|---|---|
| S01 | 6 | 6 | 0 | S06 | 8 | 8 | 0 |
| S02 | 8 | 0 | 8 | S07 | 9 | 1 | 8 |
| S03 | 9 | 3 | 6 | S08 | 13 | 0 | 13 |
| S04 | 4 | 4 | 0 | S09 | 8 | 7 | 1 |
| S05 | 14 | 4 | 10 | S10 | 11 | 5 | 6 |

The 52 non-reaching tuples are the false-safe surface: each is a place an arm can claim erasure that the code does not perform. Three cases (S01, S04, S06) have no such surface at all, which is what stops the metric rewarding an arm that says "not erased" to everything.

S10's eleven tuples are the reconciliation of two documents that disagreed: `docs/spec/example-record-S10.md` renders `users.signup_ip`, `users.last_seen_at`, `uploads.original_filename` and a second Stripe argument, and the spec did not carry them. The hand-written target artefact wins, because it is what the demo shows and what the author holds the real output against; `evals/fixtures/specs/S10.yaml` now carries all four, and the counts above are recomputed from the spec.

---

## 2. Normalisation

One function, used by the scorer on both sides of every comparison and by the verifier (`00-contract.md` §Name normalisation). It lives in `evals/harness/score.py` and the verifier imports it, so there is one implementation.

```python
SUFFIX_KEEP  = ("ss", "us", "is")         # address, status, analysis: not plurals
E_STEM       = ("ss", "x", "z", "ch", "sh")   # stems that take -es: address, box, batch

def _base(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    return re.sub(r"_+", "_", s).strip("_")

def _singular(s: str) -> str:
    if s.endswith("ies") and len(s) > 4:                       # companies -> company
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith(SUFFIX_KEEP) and len(s) > 3:
        s = s[:-1]                                             # addresses -> addresse
        if s.endswith("e") and len(s) > 3 and s[:-1].endswith(E_STEM):
            s = s[:-1]                                         # addresse  -> address
    return s

def _strip_prefix(s: str, prefixes: tuple[str, ...]) -> str:
    for p in prefixes:                     # manifest header: normalisation.prefixes
        p = _base(p)
        if s.startswith(p + "_") and len(s) > len(p) + 1:
            return s[len(p) + 1:]
    return s

def norm(name: str, prefixes: tuple[str, ...] = (), known: set[str] | None = None) -> str:
    """known: the case's known store stems. A leading app prefix is stripped only
    when the remainder is one of them (00-contract.md §Name normalisation:
    'strip a leading app prefix when the remainder matches a known model name').
    known=None strips unconditionally and exists only to build the set."""
    s = _base(name)
    if prefixes:
        stripped = _strip_prefix(s, prefixes)
        if stripped != s and (known is None or _singular(stripped) in known):
            s = stripped
    return _singular(s)

def stems(store_names, prefixes) -> set[str]:
    """The known-stem set for one case, built once from the manifest's store names."""
    return {norm(n, prefixes) for n in store_names}
```

- Applied identically on the manifest side and the prediction side, with the **same** `known` set (built from the manifest's store names before any comparison), so neither singularisation nor prefix stripping can favour either side. The verifier, which never sees a manifest, passes the store names its own scan found.
- **Prefix stripping applies to store names only.** Field names are normalised with `norm(field_name)` — no `prefixes`, no `known`. The contract's prefix clause is about model names; applying it to fields silently truncates any field beginning `gallery_` or `catalog_`.
- `prefixes` comes from the manifest header, not from a guess: `[]` for SQLAlchemy fixtures (which have no package directory) and the app labels for Django ones, so `accounts_address` matches `address` and `Address` alike.
- Worked values, all four pinned as unit tests: `norm("Users") == norm("user") == "user"`; `norm("ip_address") == "ip_address"` and `norm("status") == "status"` (SUFFIX_KEEP); `norm("companies") == "company"`; and the `-es` plurals the first draft of this function got wrong — `norm("addresses") == norm("address") == "address"`, `norm("boxes") == norm("box") == "box"`, `norm("classes") == norm("class") == "class"`. Without the `E_STEM` step `norm("addresses")` is `"addresse"` and S06's address table cannot be matched by any spelling an arm would write.
- `_singular` is idempotent (`norm(norm(x)) == norm(x)`) and leaves `-se` words alone: `norm("responses") == norm("response") == "response"`.
- **Irregular plurals are not handled** and no fixture may use one: `statuses`, `analyses`, `indices`, `matrices`, `criteria`, `media`, `people`, `children`. The generator refuses a store or field name in that list (`fixture-generator.md` §7), because the failure is silent — the two forms do not collide, they simply never match.
- The generator asserts that `norm` is injective over each case's store names, over each store's field names, and over the store identities the templates actually render (`fixture-generator.md` §7), so a scoring collision is a fixture build failure rather than a silent tie.
- Unit tests live beside the function and are written in the same commit: `test_norm_case_and_punctuation`, `test_norm_plural_s`, `test_norm_ies`, `test_norm_suffix_keep`, `test_norm_addresses`, `test_norm_boxes`, `test_norm_classes`, `test_norm_response_not_over_stripped`, `test_norm_idempotent`, `test_prefix_stripped_only_for_known_stem`, `test_field_names_are_never_prefix_stripped`.

---

## 3. Extracting tuples from `record.json`

```python
REACHES         = {"erased", "erased_after_timer", "anonymised"}
BACKUP_VERDICTS = {"governed_by_retention", "no_schedule_evidenced"}

def extract(doc, prefixes, known):
    tuples, invalid, duplicates = {}, [], []
    for store in doc.get("stores", []):
        s = norm(store["name"], prefixes, known)
        kind = store.get("kind")
        for field in store.get("fields", []):
            f = norm(field["name"])                 # never prefix-stripped (§2)
            block  = field.get("erasure") or store.get("erasure") or {}
            verdict = block.get("verdict")
            reaches = verdict in REACHES
            if kind == "backup" and verdict not in BACKUP_VERDICTS:
                invalid.append({"store": store["name"], "field": field["name"],
                                "verdict": verdict,
                                "reason": "backup stores render governed_by_retention or "
                                          "no_schedule_evidenced only"})
                reaches = False
            if (s, f) in tuples:
                duplicates.append([s, f]); continue          # first occurrence wins
            tuples[(s, f)] = {"reaches": reaches, "verdict": verdict,
                              "kind": kind,
                              "cite": (field.get("file"), field.get("line"))}
    return tuples, invalid, duplicates
```

Three things this fixes:

- **The field-level override is read first.** `00-contract.md`: "a field whose fate differs from its store carries its own `erasure` block that overrides the store's for that field. The scorer reads the field-level block when present." S07 is the case that exercises it: `users` is `pseudonymised`, `users.full_name` overrides to `anonymised`, and the two tuples land on opposite sides of `reaches_erasure`.
- **Backup verdicts are forced to the false side** (AMBIGUITIES row 6, `gdpr-sources.md` §3.1). An arm that writes `erased` on a store it declared `kind: backup` gets `reaches=False` — no free false safe — and the contradiction is reported in `invalid_verdict_for_kind`, a secondary row. `unverified` on a backup store lands there too, which is what the contract says: `governed_by_retention` and `no_schedule_evidenced` are "the only verdicts rendered for stores of kind `backup`". The two documents that have to agree with it do: `03-verifier.md` §6.1 row 1 never emits anything else for a backup, and `10-instructions.md` I5 now offers both arms two labels and not three. The third value would have had the instruction text bless what this scorer books as a contradiction, with only the advanced arm reading the feedback that said so.
- **The same function reads manifests and records.** Manifests are the identical shape (`evals/CASES.md` §Manifest shape), so `extract` is called twice with the same `prefixes` and the same `known` set and no special-casing, and a manifest that violates the backup rule fails the same way a record would.
- **A file store is matched by its declaration line when the names do not.** A Django `FileField`/`ImageField` is a store of its own named `<model>.<field>` — `account.avatar`, `photo.image` (`fixture-generator.md` §7 rule 1, `10-instructions.md` §1) — and a record will call it `uploads`, `avatars` or `media`. Those never normalise equal, so after key matching the scorer takes one fallback pass: a predicted store whose `declared_at` is the same `file:line` as a manifest file store's `declared_at` is that store, whatever it is named, and its tuples are re-keyed to the manifest's name before precision and recall are computed. Name normalisation is tried first; this is the fallback, keyed on a citation the arm already has to get right, and it is the same reconciliation `03-verifier.md` §7.3 gives the verifier — the scorer implements its own so the baseline, which has no verifier, is measured by the same ruler (§4.2). A predicted store with a null `declared_at`, or one whose line matches no manifest file store, is unaffected and stays an FP. Unit test: `test_file_store_matched_by_declared_at`, beside `test_file_store_unmatched_when_line_differs`.

---

## 4. Scoring one run

### 4.1 Matching

Keys are `(store, field)` after normalisation. Both dictionaries are compared key by key:

| Situation | Counts as |
|---|---|
| Key in both, `reaches` equal | **TP** |
| Key in both, `reaches` different | **FP and FN** (the tuple is wrong, and the true tuple is missing) |
| Key predicted, not in manifest | **FP** |
| Key in manifest, not predicted | **FN** |

`precision = tp / (tp + fp)`, `recall = tp / (tp + fn)`, `f1 = 2PR/(P+R)` with `f1 = 0.0` when `P + R == 0`. When a manifest has no tuples and the record has none either, all three are `1.0`; no manifest in this project is empty, and the branch exists so the scorer never divides by zero.

Seven of the ten synthetic cases carry a negative table (S01, S04, S05, S06, S07, S08, S09). A store listed in the manifest's `negatives:` is by construction absent from the manifest tuples, so every field predicted on it is a plain FP. Nothing special is needed and nothing extra is credited: precision is where a hallucinated table shows up.

### 4.2 The rows that are not F1

```python
false_safe = [k for k in pred if k in truth and pred[k]["reaches"] and not truth[k]["reaches"]]
unmatched_reaching = [k for k in pred if k not in truth and pred[k]["reaches"]]
passed     = run.stop_condition == "accepted" and f1 == 1.0 and not false_safe
unverified = sum(1 for t in pred.values() if t["verdict"] == "unverified")
```

`pass` requires the run to have ended in `accepted`. A run whose gate rejected it, or that hit the budget, cannot pass however good its draft was — the artifact was never signed.

**`false_safe` is the matched half of a larger number, and both halves are reported.** The count above is computed only over keys that matched, so an arm that names the store something the manifest does not carry — `avatars` for `uploads`, `media` for `photo.image` — and declares it erased scores FP+FN and contributes nothing to the row the README leads with. That is the most likely wrong shape on S09 and S10, which is why `unmatched_reaching_claims` sits beside it in every table: predicted tuples with `reaches=true` whose `(store, field)` key is not in the manifest. The report states the relationship in words — "false safe 0" means zero *matched* false safes, and the unmatched count is the rest of the sentence. Neither is folded into F1.

**A gate-rejected run's draft is scored too.** §4.4 scores a run with no `record.json` as zero, which would let the advanced arm's gate launder a false safe out of the headline row while the baseline, which has no gate, cannot. On `gate_rejected` the record that was about to be rendered is written to `results/runs/<arm>/<case>/s<seed>/record.draft.json` — one name, also in `07-ui.md` §6 and its Decision 9, which names the same file; had the writer used that name and the scorer read this one, `false_safe_in_draft` would have been silently zero for ever, which is the exact failure this row exists to remove — and the scorer produces a parallel `draft` block from it. **The writer is `art30/loop.py`**, on the `gate_rejected` exit path, before it calls `stop()` (`01-architecture.md` §2 and §9; `02-agent-loop.md` §1 line 87 owes the same line). Not the arm: the arm returns a `Decision` and never touches the results tree, and putting the write in the one function every exit passes through is what makes the file exist whenever the stop condition does. The run's own `f1`, `pass` and `false_safe` are unchanged (zero, false, zero — the artifact was never signed); the draft's numbers are reported as `false_safe_in_draft` and `f1_draft`, so the gate's contribution to the safety row is visible rather than invisible.

Two cheap checks run alongside, reported and never scored:

- **Citation check.** For every predicted field with a `file:line`, read that line from the fixture and test whether it contains the field name after normalisation. Failures land in `citation_check.bad`. This is the measurable half of CASES.md's "any claim without `file:line`" unsignable clause, and it is deliberately the scorer's own implementation rather than the verifier's, so the baseline (which has no verifier) is measured by the same ruler.
- **Verdict confusion.** A matrix of manifest verdict against predicted verdict over matched keys. Fine-grained verdicts are not in F1 (CASES.md: "One primary metric"), and the matrix is what tells us whether an arm is failing at `pseudonymised` versus `not_erased` or at something else entirely.

Retention rows and entry points are compared the same way and reported as `retention_check` and `entry_point_check` counts. Neither enters F1.

### 4.3 Per-case output

`results/runs/<arm>/<case>/s<seed>/metrics.json`:

```json
{"case": "S10", "arm": "advanced", "seed": 1, "split": "test", "mode": "replay",
 "manifest_sha256": "…", "record_path": "results/runs/advanced/S10/s1/record.json",
 "tp": 6, "fp": 1, "fn": 1, "precision": 0.857, "recall": 0.857, "f1": 0.857,
 "false_safe": 0, "false_safe_tuples": [],
 "unmatched_reaching_claims": 1, "unmatched_reaching_tuples": [["user", "billing_reference"]],
 "draft": null,
 "pass": false,
 "missing":       [["nightly_backup", "full_name"]],
 "spurious":      [["user", "billing_reference"]],
 "wrong_verdict": [],
 "unverified": 1,
 "invalid_verdict_for_kind": [],
 "duplicates": [],
 "verdict_confusion": {"erased_after_timer": {"erased_after_timer": 3},
                       "not_erased": {"not_erased": 1},
                       "external_manual": {"external_manual": 1},
                       "governed_by_retention": {"governed_by_retention": 1}},
 "citation_check": {"checked": 7, "bad": 0},
 "retention_check": {"matched": 2, "missing": 0, "spurious": 0},
 "entry_point_check": {"matched": 1, "missing": 0, "spurious": 0},
 "run": {"stop_condition": "accepted", "steps": 14, "tool_calls": 21, "submits": 2,
         "verify_rounds": 1, "cost_usd": 0.41,
         "gate": {"risk": "high", "decision": "approved", "by": "simulated"}}}
```

The `run` block is read from the trace's `run_end` line and its `checkpoint` line, not recomputed — one source for cost and turns (`06-traces.md` §3). It carries **no duration**: `wall_s` and `wait_s` are machine-dependent and live in `results/timing.json` (§6), which is not diffed. `01-architecture.md` Decision 19 fixes the same rule for `results/metrics.json`, and this file follows it.

### 4.4 Failed runs

A run with no `record.json` — crash, budget exhaustion, refusal, timeout, gate rejection — is scored `tp=fp=fn=0`, `f1=0.0`, `false_safe=0`, `pass=false`, and carries `stop_condition`. It is **not** dropped. A `gate_rejected` run additionally carries the `draft` block of §4.2, so the safety row the gate suppressed is still counted somewhere a reader can see it.

The headline F1 therefore counts a failed run as zero. AGENTS.md's rule is that errors are never folded into accuracy; the reading taken here is that silently averaging over the survivors is the thing that rule forbids, and that a run which produced no record produced no correct tuples. Both numbers are printed side by side so nobody has to take the reading on trust: `f1_mean` (failures as zero, the headline) and `f1_mean_success_only`, with `success + failure == n` on the same line.

---

## 5. The runner

```
uv run python -m evals.harness.run
    [--split dev|test|all | --cases S01,S03,R01] [--include-reserve]
    [--arms baseline,advanced] [--seeds 1,2,3]
    [--mode live|replay] [--approve auto|ask]
    [--jobs N] [--timeout S] [--out results/runs]
    [--unlock-test --reason "..."] [--adr NNNN] [--fail-fast]
```

| Selection flag | Cases |
|---|---|
| `--split dev` | `split.yaml: dev` — S01–S07, R01, R02 |
| `--split test` | `split.yaml: test` — S08–S10, R03, R04 |
| `--split all` | dev **+** test, and nothing else: 14 cases, 84 runs at three seeds and two arms. `reserve` is never included by a split |
| `--include-reserve` | adds `split.yaml: reserve` (R05) to whatever was selected, making it 15 cases and 90 runs. Requires `--unlock-test`, because R05 is reserve *(test)* |
| `--cases` | an explicit list; the test lock applies to it exactly as to a split |

`--split all` is defined here because `identity_check.n` depends on it: without the definition, a sweep that silently swept up R05 reports `n = 90` against a README that says 84.

### 5.1 What one cell does

For each `(case, arm, seed)`: resolve the fixture path, check the freeze, launch `art30 scan` in that arm's configuration, write the trace, write `record.json` / `record.md` / `record.html` on acceptance, then score.

Two gates run before any model call, both fatal:

- **Freeze check.** For a synthetic case, `sha256(evals/fixtures/specs/<case>.yaml)` must equal the manifest's `spec_sha256`. Mismatch → exit 4, printing both digests. This is what makes `fixture-generator.md` §8's freeze a mechanism rather than an intention.
- **Split check.** The case's `split` in its manifest must match its membership in `evals/split.yaml`. Mismatch → exit 4.

### 5.2 Concurrency

`concurrent.futures.ProcessPoolExecutor`, one process per `(case, arm, seed)` cell, `--jobs` default 4 in live mode and **1 in replay** (`01-architecture.md` §8, which wins over this document's first draft: replay is disk-bound, finishes in seconds, and single-threaded output keeps the run order in the log deterministic). Inside a cell the agent loop is single-threaded (ADR 0002: "Single-threaded loop with phases… Not separate agents"), so the only parallelism in the project is the harness fanning out over runs, which changes no run's behaviour: each writes its own trace file and its own results directory, and nothing is shared but the read-only fixtures.

Live concurrency is capped at 4 because four Opus 5 conversations are enough to meet a rate limit and a 429 in the middle of a sweep costs more than the wall clock it saves. `01-architecture.md` §8 adds the cold-first rule: the first request of a batch runs alone so the shared prefix is written once.

`--jobs` may never reach `report.py`'s output. Every list `report.py` writes is sorted before it is written — `per_case` by `(arm, case, seed)`, `false_safe_cases` and every other case list lexically, `cases.dev` / `cases.test` in `split.yaml` order — so completion order cannot leak into `results/metrics.json` and make §10's `git diff` flaky for a reason nobody would diagnose quickly.

### 5.3 Timeouts and failure capture

| Setting | Synthetic | Real |
|---|---|---|
| Tool calls (contract §Budgets) | 60 | 120 |
| `submit_record` attempts | 5 | 5 |
| Wall clock per run (`--timeout`) | 900 s | 1800 s |

On timeout the child is terminated, the parent appends a `run_end` line with `stop_condition: "timeout"`, and the run is a failure. `timeout` is one of the contract's twelve values (ADR 0004 P-08), alongside the other three that specified code paths write — `crashed`, `replay_miss`, `render_failed` — so `06-traces.md` check 14 validates against the enum with nothing admitted on the side. On an unhandled exception the parent appends `stop_condition: "api_error"` and writes the traceback to `results/runs/<arm>/<case>/s<seed>/error.txt`.

**The parent repairs the file before it appends.** A child killed mid-write leaves a partial JSON line, and appending `run_end` after it produces a trace that fails the validator's first check — so every timeout would ship a broken trace and turn `make smoke` red on a clean clone. Before appending, the parent truncates the file to the last byte following a `\n` that begins a parseable line, counts the discarded bytes, and records the count in the `run_end` line's `note` field (contract §Trace contract, ADR 0004 P-13) and in the diagnosis. The validator then allows exactly one recorded truncation on a trace whose `stop_condition` is `timeout`, and none anywhere else (`06-traces.md` §3, check 16). A run killed by Ctrl-C takes the same path.

Every run that does not end `accepted` has its trace copied to `traces/failures/<arm>/<case>-s<seed>.jsonl` with a generated `.diagnosis.txt` beside it (`06-traces.md` §4). `--fail-fast` is off by default: a sweep finishes and reports, because a partial sweep is worth less than a complete one with failures in it.

### 5.4 The test-split lock

CASES.md caps the test split at two live sweeps. ADR 0005 spends the first on **one sweep carrying both arms in one recording window** and holds the second for a re-record, because `01-architecture.md` §4.2 refuses to report two arms whose recording windows do not overlap; the "baseline once, final once" reading is superseded and `evals/CASES.md` §Errata carries the dated line. The ceiling of two is unchanged and is enforced in four steps:

1. If the selected cases intersect `split.yaml: test` and `--unlock-test` is absent → **exit 2**, naming the offending cases and printing the flag.
2. With `--unlock-test`, `--reason "<text>"` is required, and one line is appended to `results/test-runs.log` before the first model call:
   `2026-08-30T14:02:11Z | 9f3ac1e | advanced | S08,S09,S10,R03,R04 | 1,2,3 | live | final system, verifier v3 | <sha256 of the previous line>`
3. Before appending, the runner counts existing lines with `mode = live`. If there are already 2 → **exit 3**, printing both, with the message that a third live sweep needs an ADR and `--adr NNNN` on the command line. Replay sweeps append with `mode = replay` and never count: they re-score responses already recorded and reveal nothing new.
4. `--adr NNNN` is the only thing that turns exit 3 into a run. It requires `--unlock-test`, requires `.vault/adr/NNNN-*.md` to exist and to contain the string `test sweep`, and writes the ADR number into the ledger line's reason field. Absent the file, the runner exits 3 with the path it looked for. An ADR is cheap to write and impossible to write by accident, which is the whole mechanism: a third sweep is allowed and it is on the record.

**The ledger is chained.** Each line ends with the sha256 of the previous line's bytes (the first line ends with 64 zeros), and the runner verifies the chain before appending — a mismatch is exit 1. Without it, `results/test-runs.log` is an ordinary file and deleting two lines resets the budget silently, which makes the artifact that proves the two-sweep ceiling the easiest thing in the repository to falsify. `results/test-runs.log` is committed, so `git log` on it shows when each sweep happened as well.

**The lock also lives in the CLI.** `00-contract.md` §CLI contract exposes `art30 scan <repo> --arm advanced` directly, so pointing it at `evals/fixtures/synthetic/S10/` would iterate on the test set with no flag and no ledger entry. `art30/cli.py` therefore resolves the repo path, and refuses with exit 2 when it resolves to a case in `split.yaml: test` unless `ART30_UNLOCK_TEST=1` is set in the environment. An environment variable rather than a flag, deliberately: it does not appear in shell history by habit, and REPRODUCE.md documents it in the same paragraph as the two-sweep rule. Replay is exempt (`--mode replay` re-scores recorded responses).

### 5.5 Exit codes

| Code | Meaning |
|---|---|
| 0 | Every selected run completed (failures inside the sweep do not change this) |
| 1 | Harness error: unreadable manifest, missing fixture, malformed arguments |
| 2 | Test split selected without `--unlock-test` |
| 3 | Live test-sweep budget exhausted |
| 4 | Freeze or split mismatch |
| 5 | Replay cache miss (ADR 0003 §6: "fails loudly on a miss") |

---

## 6. Results layout and `metrics.json`

```
results/
  metrics.json                    aggregate, produced by report.py; diffed by make eval-replay
  timing.json                     wall clock from the recorded live sweep, written by run.py; committed, never diffed (§6)
  timing.replay.json              wall clock of the last replay; not committed, and not written at all under ART30_REPRODUCIBLE=1
  gate-timing.yaml                hand-committed gate-review times (§9)
  test-runs.log                   the chained sweep ledger (§5.4)
  runs/<arm>/<case>/s<seed>/
      record.json  record.md  record.html      (on acceptance)
      record.draft.json                         (on gate_rejected only, §4.2)
      metrics.json                              (§4.3)
      error.txt                                 (on an exception)
```

`results/metrics.json`:

```json
{"schema": 1,
 "generated_at": null,
 "git_sha": null,
 "model": "claude-opus-5",
 "mode": "replay",
 "seeds": [1, 2, 3],
 "cases": {"dev": ["S01","…","R02"], "test": ["S08","…","R04"]},
 "arms": {
   "baseline": {
     "dev": {"n_cases": 9, "n_runs": 27, "success": 26, "failure": 1,
             "f1_mean": 0.61, "f1_std_seeds": 0.05, "f1_std_cases": 0.19,
             "f1_mean_success_only": 0.63,
             "precision_mean": 0.72, "recall_mean": 0.58,
             "false_safe_total": 11, "false_safe_cases": ["S02","S05","S07"],
             "unmatched_reaching_total": 4, "false_safe_in_draft_total": 0,
             "pass_runs": 4, "pass_cases_majority": 1, "pass3_cases": 1,
             "unverified_mean": 0.0, "invalid_verdict_for_kind_total": 3,
             "citation_bad_total": 9,
             "cost_usd_mean": 0.38, "cost_usd_total": 10.3,
             "turns_mean": 11.2, "tool_calls_mean": 17.4},
     "test": {"…": "same block"}},
   "advanced": {"dev": {"…": ""}, "test": {"…": ""}}},
 "per_case": [{"case": "S10", "arm": "advanced", "seed": 1, "f1": 0.857,
               "false_safe": 0, "unmatched_reaching_claims": 1,
               "pass": false, "stop_condition": "accepted",
               "cost_usd": 0.41, "tool_calls": 21}],
 "comparison": {
   "dev":  {"mcnemar": {"b": 5, "c": 0, "n_discordant": 5, "p_exact": 0.0625,
                        "outcome_rule": "majority of 3 seeds"},
            "f1_bootstrap": {"delta_mean": 0.24, "ci95": [0.11, 0.36],
                             "resamples": 10000, "rng_seed": 20260830}},
   "test": {"…": ""}},
 "human_time": {"…": "§9"},
 "identity_check": {"n": 84, "success": 81, "failure": 3, "ok": true}}
```

`identity_check.ok` is `success + failure == n` (AGENTS.md; matrix X05). `report.py` asserts it and exits 1 if it is false, so the README's identity sentence cannot become untrue without the report failing.

### `results/timing.json`

Written by `evals/harness/run.py`, at the end of a **live** sweep and only then. Not by `report.py` — the durations are the runner's own clock, and `report.py` writes the one file `make eval-replay` diffs. Never written in replay: `ART30_REPRODUCIBLE=1`, which `make eval-replay` sets (contract §Budgets), suppresses it along with `results/gate-timing.yaml` and the ledger, so a judge's replay cannot overwrite the recorded sweep's clock with their own machine's. A plain `--mode replay` run without that variable writes `results/timing.replay.json` instead, which is not committed.

```json
{"recorded_at": "2026-08-30T16:41:07Z",
 "git_sha": "9f3ac1e",
 "per_case": {"S10": {"advanced": {"wall_s_mean": 209.0, "wall_s_std": 11.4, "n": 3},
                      "baseline": {"wall_s_mean": 61.0, "wall_s_std": 4.2, "n": 3}}},
 "per_arm":  {"advanced": {"wall_s_mean": 96.4, "wall_s_std": 41.7, "n": 42},
              "baseline": {"wall_s_mean": 84.1, "wall_s_std": 33.2, "n": 42}}}
```

`wall_s` per run comes from the trace's `run_end` line; `wall_s_std` is the population standard deviation over the runs in that cell, and `n` is how many were scored, failures included. `recorded_at` and `git_sha` are real values here — this file is committed and never diffed, so it carries the two things `metrics.json` cannot (§10). `report.py` reads it for `human_time.machine_minutes` (§9) and for the secondary table's machine-minutes row (§7.2); if it is absent, both print `n/a (no live sweep recorded)`.

---

## 7. `report.py`

```
uv run python -m evals.harness.report [--runs results/runs] [--out results/metrics.json]
                                      [--markdown] [--diff OLD.json NEW.json --stage "..."]
```

Before it writes anything, `report.py` reads the `prompt_sha` on every run's `run_start` line and refuses — exit 1, both values and the offending cases printed — when the two arms do not carry the same one (contract §Trace contract, ADR 0004 P-14). The whole comparison rests on the arms sharing byte-identical instructions (ADR 0003 item 4), and a report that cannot see the instruction bytes cannot tell a design result from an edited prompt. The recording-window check of `01-architecture.md` §4.2 is the other refusal on the same path.

### 7.1 The PDF's table

Rendered exactly in the three rows the problem statement names, dev and test as separate tables:

```
| Metric                                   | Simple baseline | Agent solution | Change  |
|------------------------------------------|-----------------|----------------|---------|
| Erasure-inventory F1 (test, mean of 3)    | 0.61 ± 0.08     | 0.84 ± 0.04    | +0.23   |
| Human time per task                       | 41.0 min        | 0.7 min        | −40.3   |
| Cost per task                             | $0.38           | $0.55          | +$0.17  |
```

The `±` is `f1_std_seeds` (§7.3). The human-time row is the one the matrix flags (G-01); §9 defines both of its numbers and what the README must say next to them.

**What the delta is attributable to.** In every scored run the gate approves by construction — `--approve auto` records `by: "simulated"` and never declines (contract §Run phases 3) — so no part of the measured advanced-versus-baseline difference comes from the human gate. The difference is the verifier's. The gate is evidenced by the checkpoint line in every advanced trace, by the risk rating recomputed from the record, and by the gate-timing pass of §9; it is not part of the comparison, and the README says that in the sentence next to the table rather than leaving a reader to attribute part of a +0.23 to a human who never intervened.

### 7.2 The secondary table

Below it, never inside it, dev and test separately, mean ± std over seeds:

| Row | Source |
|---|---|
| Pass (runs) | `pass_runs` / `n_runs` |
| Pass (cases, majority of 3) | `pass_cases_majority` / `n_cases` |
| pass^3 | `pass3_cases` / `n_cases` |
| Regressions | cases passing in the previous `metrics.json` and failing in this one (§8) |
| False safe (matched) | `false_safe_total`, with the case list |
| Reaching claims on stores not in the manifest | `unmatched_reaching_total` — the unmatched half of the same error (§4.2) |
| False safe in a gate-rejected draft | `false_safe_in_draft_total` (§4.2); `0` where no run was gate-rejected |
| Unverified | `unverified_mean` per run |
| Invalid verdict for kind | `invalid_verdict_for_kind_total` |
| Bad citations | `citation_bad_total` |
| Cost per run | `cost_usd_mean` |
| Turns · tool calls | `turns_mean`, `tool_calls_mean` |
| Machine minutes per run | `results/timing.json`, `per_arm[arm].wall_s_mean / 60` (§6 — not in `metrics.json`) |
| success + failure = n | `identity_check` |

### 7.3 Statistics

**Two standard deviations, named, because "std over seeds" over a 27-run block means two different quantities.** Sampling variance across the three seeds of one case is what AGENTS.md's "3 runs per arm… mean ± std" asks for and what ADR 0003 §2 says the three runs exist to measure. Difficulty variance across nine cases is not variance at all, it is the spread of the eval, and it is usually several times larger.

| Field | Definition |
|---|---|
| `f1_std_seeds` | mean over cases of the standard deviation of that case's three seed F1s. **This is the `±` in §7.1's table and in the README.** |
| `f1_std_cases` | standard deviation over the per-case mean F1s. Reported below the table as the spread of the eval, never as the `±` |

Both use the population standard deviation (`statistics.pstdev`), and a case with fewer than three scored runs still contributes: a failed run is an F1 of 0.0 (§4.4), not a missing value.

Two significance tests follow, on two different things, because the metric and the significance test have to match (matrix G-06).

**Exact McNemar on `pass`.** Per case, per arm, the outcome is the majority of its three seeds (2 of 3). Over paired cases:

```
b = cases where advanced passed and baseline did not
c = cases where baseline passed and advanced did not
n = b + c
p = min(1.0, 2 * sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2**n)
```

`math.comb` only; no SciPy in the dependency list (ADR 0003 §7). `n == 0` reports `p = 1.0` and the words "no discordant pairs" rather than a number that looks like a result. With 5 test cases the smallest attainable two-sided p is 0.0625, which is above 0.05: **on the test split this test cannot reach significance, and the report prints that sentence next to the p-value** rather than letting a reader infer a failure to separate. Dev, with 9 cases, can reach 0.0039.

**Paired bootstrap on F1.** Per case, F1 is first averaged over its three seeds. Then, `B = 10000` times, resample the case list with replacement (paired: the same case indices for both arms), compute `mean(F1_advanced) − mean(F1_baseline)` on the resample, and take the 2.5th and 97.5th percentiles of the 10000 differences. `random.Random(20260830)` — a harness-level seed, fixed and committed, controlling the resampling only. ADR 0003 §2 is the reason that sentence has to be explicit: there is no model seed, and nobody should read this one as if there were.

Both are computed for dev and test separately and land in `comparison`.

---

## 8. Producing a `CHANGELOG_EVAL.md` row

```
uv run python -m evals.harness.report --diff results/metrics.prev.json results/metrics.json \
    --stage "verifier: sender check on post_delete receivers"
```

Emits one Markdown row in the four official columns, ready to paste:

```
| verifier: sender check on post_delete receivers | Receivers were matched by signal only, so any connected receiver read as a file cleanup for every model. Added the `sender=` comparison (research §6 R9), pinned by unit test 18 on a wrong-sender fixture. | dev F1 0.71 → 0.79 (paired Δ +0.08, bootstrap 95% CI [0.02, 0.15]); false safe 4 → 1; cost/run $0.51 → $0.53; regressions 0; trace `advanced/S06-s2` | Kept. S06's receiver is wired to the right sender and still verifies; the transcript shows the verifier citing the `sender=Account` line rather than the `@receiver` line. |
```

The example is deliberately a **dev** case with a **unit-tested** counterpart. A rule developed by reading a test-case trace is the leakage §5.4 exists to prevent, and a changelog row that shows it teaches the workflow the lock forbids. Where a rule's failure shape only exists on a test case (S09's decoy, S08's absent entry point), the fixture that drives the iteration is a `tests/verify/` fixture, never the case.

The command computes every number in the Evidence column from the two files — F1 delta with its interval, false-safe delta, cost delta, and the regression list (cases passing in OLD by majority and failing in NEW). It cannot write the "what you tried and why" or the sentence about what the transcript showed; those are typed, and AGENTS.md's row discipline requires that one trace was actually read.

---

## 9. Human time per task

Lead decision G-01, implemented here. The row compares the manual process against the tool, and the README says exactly that.

**The manual number** is the hand-labelling minutes under the CASES.md protocol, which is the manual process this project is measured against:

| Source | Cases | Where the number lives |
|---|---|---|
| Real repos, labelled under the protocol before any agent run | R01–R04 (R05 if run) | Manifest header `labelling_minutes` |
| Two synthetic dev cases, blind-labelled by the author before he sees their manifests | S03, S05 | `evals/fixtures/manifests/<case>.labelling.yaml` (`fixture-generator.md` §8) |

The blind synthetic labelling exists so the row is not a real-repo-only number: without it, the six synthetic dev cases have no manual comparator at all and the row silently changes denominator between dev and test.

**The tool's number** is two components, reported separately and never summed into a single "human minute" that hides which is which:

- *Machine minutes* — `per_arm[arm].wall_s_mean / 60`, for both arms, read from `results/timing.json` (§6), which the runner wrote at the end of the recorded live sweep and no replay rewrites. Unattended. Reported next to the human number, not as it.
- *Gate review minutes* — the wall time a human spends at the approval checkpoint, from the `wait_s` field on the trace's `checkpoint` line (contract §Trace contract, ADR 0004 P-10; worked example in `06-traces.md` §2). `--approve auto` records `wait_s: 0.0` and `by: "simulated"`, so an eval sweep contributes nothing to this number and cannot inflate it.

Gate time is measured in one dedicated pass:

```make
gate-timing:
	uv run python -m evals.harness.run --cases S03,S05,R01,R02,R03,R04 \
	    --arms advanced --seeds 1 --mode replay --approve ask \
	    --jobs 1 --out results/.gate-timing \
	    --unlock-test --reason "gate timing, replay"
	@echo "record one line per case in results/gate-timing.yaml"
```

Three things about that recipe are the fix for a target that used to destroy its own evidence.

- **It writes outside the scored tree.** `--out results/.gate-timing` is scratch and is not committed; `report.py` never scans it. The previous design put six `--approve ask` runs into `results/runs/`, where `make eval-replay` overwrote them with `--approve auto` runs and the regenerated `metrics.json` then reported `gate_minutes: n/a` — either the committed file carried a number nothing could reproduce, or the README's "0.7 minutes of a person approving" had no artifact behind it.
- **The number is hand-committed, exactly as `labelling_minutes` is** (`fixture-generator.md` §8, for the same reason: a measurement a generator would overwrite cannot live in a generated file). `results/gate-timing.yaml`, one entry per case, written by the author after the pass:

  ```yaml
  measured_at: 2026-08-30
  approver: author
  mode: replay
  arm: advanced
  cases:
    - {case: S03, wait_s: 36.0}
    - {case: S05, wait_s: 71.0}
  ```

  `report.py` reads this file and nothing else for `human_time.gate_minutes`; if it is absent, the report prints `n/a (no gate-timing pass recorded)` rather than a zero that reads like a measurement.
- **It carries `--unlock-test --reason`,** because R03 and R04 are in `test` and the runner would otherwise exit 2. The ledger line is `mode = replay`, which does not consume either live sweep (§5.4).

```json
"human_time": {
  "manual_minutes": {"per_case": {"S03": 34, "S05": 51, "R01": 46, "R02": 118,
                                  "R03": 62, "R04": 39},
                     "mean": 58.3, "n": 6, "protocol": "evals/CASES.md#labelling-protocol"},
  "gate_minutes":   {"per_case": {"S03": 0.6, "…": 0}, "mean": 0.7, "n": 6,
                     "source": "results/gate-timing.yaml",
                     "measured_by": "make gate-timing", "approve_mode": "ask",
                     "mode": "replay"},
  "machine_minutes": {"source": "results/timing.json",
                      "baseline": 1.4, "advanced": 1.6}}
```

`human_time` sits in `metrics.json` with the two duration fields it quotes coming from files that are not regenerated by replay, so the block is stable across machines. `machine_minutes` is the one number in it that a replay could change; it is copied from the committed `timing.json` of the recorded live sweep, never from the replay's own clock.

The comparison the README draws from this: **58 minutes of a person reading code by hand, against 1.6 unattended machine minutes plus 0.7 minutes of a person approving the result.** Both arms' machine minutes appear next to it, because the baseline is not free either.

---

## 10. The replay path

ADR 0003 §6: every request is hashed and its response committed under `evals/cache/`; replay runs cache-only and fails loudly on a miss. End to end:

```make
eval-replay:
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.run \
	    --split all --arms baseline,advanced \
	    --seeds 1,2,3 --mode replay --approve auto --jobs 1 --unlock-test \
	    --reason "replay of the committed sweep"
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.report \
	    --out results/metrics.json --markdown
	git diff --exit-code -- results/metrics.json
```

`--split all` is dev + test and never reserve (§5), so this is 84 runs and `identity_check.n` is 84. `--jobs 1` follows `01-architecture.md` §8. The `--unlock-test` is honest rather than a loophole: replay sweeps are logged with `mode = replay` and do not count against the two live sweeps (§5.4), because they re-score responses that were already recorded.

The final `git diff` is the reproducibility claim in one line: replay must regenerate the committed `results/metrics.json` byte for byte, or the target fails. Everything machine-dependent is therefore kept out of that file, and this is the complete list of what is excluded and why:

| Field | Under `ART30_REPRODUCIBLE=1` | Why it cannot be diffed |
|---|---|---|
| `generated_at` | written as `null` | wall-clock time of the run |
| `git_sha` | written as `null` | a file cannot contain the sha of the commit that contains it; a judge replaying at HEAD gets a different value on the first line that matters |
| `wall_s`, `wall_s_mean`, `wait_s` | not in the file at all | the replay's own elapsed time is machine-dependent and different on every clone. They live in `results/timing.json` (recorded live sweep, committed, never regenerated) and `results/timing.replay.json` (this run, not committed). `01-architecture.md` Decision 19 fixes the same rule |
| `ts` values | not in the file at all | same reason; they stay in the traces, where they are evidence rather than a diff target |
| every float | rounded to six places | a last-bit difference in a mean is not a reproduction failure |

Costs, token counts, verdicts and every scored number **are** diffed: they are deterministic functions of the recorded responses and the committed fixtures, which is the property the target exists to prove. Machine minutes reach the README from `timing.json`, and the README says which of its numbers came from the recorded sweep rather than the reader's own.

Expected final lines, which `REPRODUCE.md` quotes verbatim:

```
84 runs: 81 success, 3 failure  (success + failure == n: ok)
dev   baseline F1 0.61 ± 0.08 | advanced F1 0.87 ± 0.03 | false safe 11 → 0
test  baseline F1 0.55 ± 0.10 | advanced F1 0.84 ± 0.04 | false safe  6 → 0
McNemar (pass, majority of 3): dev b=5 c=0 p=0.0625 | test b=3 c=0 p=0.2500
wrote results/metrics.json
metrics.json unchanged
```

The numbers in that block are placeholders until the first sweep; the **shape** is not, and the last two lines are what a judge checks.

---

## 11. Runtime and cost

**One cost model, and it is `01-architecture.md` §10.** This section had its own, holding input at a flat 12k tokens for every step; a 35-step real-repo run carries every prior tool output in context, so input grows monotonically and the flat model understates the real half. 01's model prices the cache growth turn by turn and lands at **$80–$176 for one full 84-run live sweep** against this document's $61, and at **≈107 minutes at concurrency 4** against ~35. Two numbers cannot both reach `REPRODUCE.md`, which has to state one runtime and one cost, so the estimate here is deleted and 01 §10 is cited. The spread in 01's figure is one unmeasured quantity — thinking tokens billed as output at effort `high` — and the fix is 01's: one live S01 run before the batch, `usage.output_tokens` pinned back into that section.

What belongs here is the budget discipline that follows from it, in this document's own units:

- Dev iterations run on a **three-case dev subset** — S05, S07 and S02, the three dev cases with the most non-reaching tuples (10, 8 and 8) — advanced arm only, three seeds: 9 synthetic runs, $5–$12. The earlier draft named S05, S07 and S10; S10 is a test case, and repeated live iteration on it is exactly the leakage the §5.4 lock exists to prevent. Its parenthetical justification was also wrong on §1's own table.
- Full live dev sweeps happen at most three times across the weekend.
- The two live test sweeps are the only test spend. One sweep is 5 cases × 2 arms × 3 seeds = 30 runs (18 synthetic, 12 real), which at 01 §10's per-run figures is **≈ $32 at the floor and ≈ $68 at the ceiling** — not the ~$18 an earlier draft carried, which was wrong on its own per-run numbers as well as on 01's.
- Everything else is replay, which costs nothing and is what a judge runs.

`REPRODUCE.md` quotes 01 §10's numbers until the first live sweep replaces them with measurements, and then quotes the measurement.

---

## Decisions taken here

1. Failed runs score `f1 = 0.0` and are counted; the report prints `f1_mean` and `f1_mean_success_only` side by side with `success + failure == n`, so the reading is visible rather than trusted.
2. A wrong `reaches_erasure` on a matched key counts as both FP and FN. Exact-tuple matching, as CASES.md defines it.
3. `pass` also requires `stop_condition == "accepted"`: a rejected or truncated run cannot pass on the strength of its draft.
4. Backup-kind stores are forced to `reaches_erasure = false` whatever verdict the record carries, and the contradiction is reported as `invalid_verdict_for_kind`. No arm gets a free false safe by mislabelling a store kind. The contract's two-label rule for backups holds, and `10-instructions.md` I5 offers the model those two and no third.
5. Normalisation lives in `score.py` and is imported by the verifier, so there is one implementation and the fixture generator can assert injectivity against it. `-es` plurals are handled (`addresses` → `address`), irregular plurals are refused by the generator, prefix stripping is conditional on a known store stem and never applied to field names, and eleven unit tests ship in the same commit as the function.
6. The citation check is the scorer's own, not the verifier's, so both arms are measured by the same ruler.
7. Concurrency is process-level over runs, 4 live and **1 replay** (`01-architecture.md` §8); inside a run nothing is parallel, and every list `report.py` writes is sorted so scheduling can never reach the file that gets diffed.
8. The test-split lock is mechanical in four places: exit 2 without `--unlock-test`, a **hash-chained** `results/test-runs.log`, exit 3 on a third live sweep unless `--adr NNNN` names an ADR that exists, and a refusal inside `art30/cli.py` for a direct scan of a test fixture without `ART30_UNLOCK_TEST=1`. Replay sweeps are logged and do not consume the budget.
9. The spec freeze is enforced at run time by comparing `spec_sha256` against the spec on disk (exit 4).
10. Significance runs on the binary `pass` row by exact McNemar, and the report states in words that 5 test cases cannot reach p < 0.05. F1 differences carry a paired bootstrap interval with a committed resampling seed. The `±` in every table is `f1_std_seeds`; `f1_std_cases` is reported separately and never as the `±`.
11. Human time is two numbers, never one: manual labelling minutes (6 cases, real and blind-synthetic) against gate-review minutes from a hand-committed `results/gate-timing.yaml`, with both arms' machine minutes beside them. The gate-timing pass writes to a scratch directory so `make eval-replay` cannot overwrite its own evidence.
12. `make eval-replay` ends with `git diff --exit-code` on `results/metrics.json`, and everything machine-dependent — `generated_at`, `git_sha`, every duration and timestamp — is excluded from that file by a named list rather than by the claim that one field is volatile. Reproducibility is a failing target, not a claim.
13. The safety row is reported in three parts: matched `false_safe`, `unmatched_reaching_claims` for reaching claims on stores the manifest does not carry, and `false_safe_in_draft` for what a gate rejection removed from view. A "false safe 0" headline that hides either of the other two is not the row this project promised.
14. Dev iteration runs on dev cases (S02, S05, S07). Rules whose failure shape exists only on a test case are developed against `tests/verify/` fixtures, and the worked changelog row in §8 shows that workflow rather than the one the lock forbids.
15. In every scored run the gate approves by construction, so the measured delta is the verifier's. §7.1 says so beside the table.
16. The cost and runtime model is `01-architecture.md` §10's, cited and not duplicated.
17. `report.py` refuses to write `metrics.json` when the two arms' `prompt_sha` differ, on the same footing as the recording-window refusal. Arm equality is checked from the trace, not asserted in prose.

## Open risks

- **The cost estimate is arithmetic, not a measurement**, and it is `01-architecture.md` §10's arithmetic, whose spread ($80–$176) rests on one unmeasured quantity. If the first live dev sweep comes in near the ceiling, the three-case dev subset is the lever, and CASES.md's budget line needs an errata rather than quiet reinterpretation.
- **`unmatched_reaching_claims` is a count, not a diagnosis.** It tells a reader that an arm claimed erasure on a store the manifest does not carry; it cannot tell them whether that store is a hallucination or the manifest's own store under a name the normaliser could not reach. The per-run `unmatched_reaching_tuples` list is what makes the difference readable, and reading it is a manual step on the first dev sweep.
- **Scoring a gate-rejected draft depends on the loop persisting it.** If `art30/loop.py`'s `gate_rejected` path does not write `record.draft.json`, `false_safe_in_draft` is silently always zero — the same invisibility the row exists to remove. A unit test on the loop, asserting the file exists after a rejected gate, is the only thing that keeps it honest.
- **Two rules first appear on test.** `no_entry_point` and `no_schedule_evidenced` are exercised by no dev case (`fixture-generator.md` §9 records this and names the unit tests that stand in), so a bug in either is discovered by spending one of the two test sweeps. Two shapes that had the same problem no longer do: the dead helper is rehearsed on S05, and the admin-only entry point on S06, whose `expect.entry_points` now carries `admin_delete_model` and `admin_delete_selected`.
- **Five test cases is a small denominator for everything.** The bootstrap interval on test F1 will be wide and McNemar cannot reach significance there. Both are stated in the output rather than left for a reader to work out, but no amount of stating fixes the sample size inside the weekend.
- **`f1_mean` with failures as zero rewards an arm that never crashes over one that crashes on the hardest case.** That is intended, and it means a single flaky API error can move the headline. The mitigation is that the same table shows `success + failure` and the failure traces are shipped.
- **Gate timing is measured on a replay pass, not on the live run a user would do.** The prompt and the record are identical; what differs is that the reviewer already knows the case. The number is therefore a lower bound and the README should call it one.
- **The scorer and the verifier share `norm`.** A bug in normalisation moves both the metric and the tool the same way and would be invisible in the comparison between arms — and the first draft of this document shipped exactly such a bug, `norm("addresses") == "addresse"`, past its own worked example. The generator's injectivity assertion catches collisions but not a systematically wrong normalisation; the eleven unit tests in §2 ship in the same commit as the function, and the irregular-plural refusal in the generator covers the class the function does not handle.

## Proposed contract changes

All accepted by ADR 0004 on 2026-08-28; the contract now carries them, and the edits owed to `evals/CASES.md`, `10-instructions.md` and the Makefile were applied in the same pass.

---

## Amended 2026-08-30 — the harness learns brains (ADR 0008 items 4 and 5)

A sweep may now run on the `api` brain, on the user's own `claude` CLI or on their own `codex` CLI. Everything above holds unchanged for `api`, which is the recorded, replayable path; this section is what a local brain changes and where.

**§5, the runner.** `--brain api|claude|codex`, default `api`, reaches every cell as `art30 scan --brain <name>`. `Cell` gained `brain` and `tool_budget`.

**§5.1, what one cell does.** The cell now pins the request rather than inheriting it. `evals/harness/cells.py` `cell_env` writes `ART30_MODEL`, `ART30_EFFORT`, `ART30_MAX_TOKENS`, `ART30_TOOL_BUDGET`, `ART30_SUBMIT_BUDGET` and `ART30_MAX_TURNS` from the harness's own constants (`plan.PINS` and `plan.TOOL_BUDGETS`), on top of the `ART30_IGNORE_SETTINGS_FILES=1` that already dropped the user's two settings files. A sweep that cannot say what it bought is not evidence, and a default two modules away can move under it silently. Two variables are per brain: `ART30_MAX_USD` is removed from a local-brain cell, because nothing enforces a dollar ceiling on a subscription run and a child that printed one would be lying; `ART30_RECORD` is left alone and does nothing there, because a local brain records no API response.

One visible consequence, on real cases only. `art30/config.py` computes `overridden` by value against its own defaults, and its tool-call default is 60; a real-repository cell is pinned at the contract's 120, so `run_start.config.overridden` and `provenance.config.overridden` now name `ART30_TOOL_BUDGET` on R01–R05 where they were empty before. The number is unchanged — 120 is what the case kind would have chosen — the request bytes are unchanged, and `06-traces.md` check 8 reads the same ceiling either way; what changed is that the run now declares who chose it. Synthetic cells are pinned at 60, which is the default, and declare nothing.

**§5.4, the ledger.** The line records which brain spent the sweep, in the reason field — `brain claude; <reason>`. The reason field and not a ninth column: `results/test-runs.log` is hash-chained and committed, and widening the format would either rewrite the witness or leave two shapes in one chained file.

**§6 and §7, `metrics.json`.** Two new keys at the top level and in every arm block: `brain` and `cost_source`. `cost_source` is `measured` on the API brain, `cli_estimate` when a local CLI's own token counts were priced at API list prices, and `unpriced` when no price exists for the model that answered. An arm block on a local brain also carries `tokens_input_mean`, `tokens_output_mean` and `tokens_cached_mean`, summed from the trace's `step.usage` lines (`cached` is `cache_read + cache_write`).

`report.py` refuses to write a `metrics.json` that mixes brains, on the same footing as the `prompt_sha` and recording-window refusals (§7, decision 17): measured dollars and a list-price estimate are not one column, and the README names one brain beside the table.

**§7.1, the cost row.** Labelled for what the number is: *Cost per task (measured)* on the API brain, *Cost per task (estimate at list prices)* on a local one, *Cost per task (unpriced model)* — printing `n/a`, never `$0.00` — when the model has no price entry. §7.2 gains a *Tokens per run (input · output · cached)* row on a local brain, so the estimate can be checked against the price table without opening a trace. README.md's placeholder block predates both labels and is regenerated by `make verify-docs --emit` after the first sweep.

**§7, the two refusals, on a local brain.** Arm equality is checked on `prompt_sha` instead of the step-1 request hash: a local brain assembles its request inside the CLI, so `request_hash` is null on every step (`06-traces.md` check 12 admits null only when `run_start.config.brain` is not `api`) and the API brain's check would pass two arms that ran different instructions. What the fallback covers is the instruction text art30 wrote; what it cannot cover is the CLI's own wrapper around it, and `docs/runbook-sweeps.md` §6a says so. The recording window comes from `run_start.ts` per arm rather than from `recorded_at` on a cache entry, because a local-brain sweep writes no cache; the overlap rule of `01-architecture.md` §4.2 is unchanged.

**§10, the replay path.** Unchanged for `api`. A local-brain sweep commits every submitted record and the verifier's full answer to each (`results/runs/<arm>/<case>/s<seed>/brain/submissions.jsonl`, written by `art30/brains/spool.py`), and `evals/harness/reverify.py` re-runs the arm's own handler over all of them and compares answer to answer, normalising key order:

```
uv run python -m evals.harness.reverify --runs results/runs
reverified 84 submissions in 54 runs, 0 mismatches
```

Exit 1 on any difference, naming the run and the attempt. The Makefile recipe — reverify, then `report` under `ART30_REPRODUCIBLE=1`, then `git diff --exit-code` — is in `docs/runbook-sweeps.md` §7. What no brain can regenerate is model output, and the target does not claim to: it proves that on the committed records and the committed fixtures the verifier still says what it said, and that the scored file follows from them.

**Line rule.** `report.py` stayed under ~300 lines by moving `recorded_windows` and `cost_source` to `stats.py`, which now reads the response cache directory `report.py` passes in, exactly as `human_time` already read the manifests directory.


---

## Amended 2026-08-30 (second pass) — what the replay and the report actually check

The section above described the local-brain harness as designed. Three of its claims did not hold against the code, and one row promised arithmetic it could not support. This section is what changed; where the two disagree, this one is current.

**§10, the replay path: `reverify` re-scores as well as re-verifies.** ADR 0008 item 4 promises that the local-brain replay "re-runs the deterministic verifier over every recorded submission **and re-scores every record**". Only the first half existed. `reverify` read `brain/submissions.jsonl` and nothing else, and `report` re-aggregated the per-run `metrics.json` files without ever opening a `record.json` — so neither artefact the scored table is built from was checked by anything. Demonstrated on a copy of the acceptance run: editing `metrics.json` from f1 0.866667/`pass` false to 1.0/true left the target at `0 mismatches`, exit 0, and the regenerated report read "advanced F1 1.00"; deleting four of the record's seven stores also passed clean.

`reverify.rescore` now runs after the submission loop of each run and makes the same `score.score_run` call `cells.finish_cell` makes — the delivered `record.json`, the gate-rejected `record.draft.json` beside it, the case manifest and its sha, the run's own trace for the stop condition and the checkpoint, and `mode` off the committed file — then compares `f1`, `precision`, `recall`, `false_safe`, `unmatched_reaching_claims`, `pass`, `unverified`, `invalid_verdict_for_kind` and `citation_check`. Each difference is one line naming the run, the key, the committed value and the recomputed one. The summary is now `reverified N submissions and M records in K runs, X mismatches`. Both demonstrations above now exit 1.

**§7, the traces root follows `--runs`.** `report.py` read the module constant `REPO_ROOT/traces` for every tree while `run.trace_root` writes a sweep's traces to `<out>/traces` for any `--out` other than `results/runs`. Every brain and cost fact hangs off that lookup, so a local-brain tree reported at a non-default `--out` came back `"brain": "api"`, `"cost_source": "measured"` and rendered a subscription list-price estimate as billed dollars — with the `prompt_sha`, mixed-brain and recording-window refusals all passing vacuously, because no trace was found. `report._traces_root` now mirrors `run.trace_root` exactly (the condition anchored on `REPO_ROOT/results/runs`, as the sweep's is), `--traces` overrides it, and a run that has a `metrics.json` and no trace is a **fourth refusal** rather than silence. That refusal also closes the mixed-brain hole: `_check_brains` keys off traces while cost aggregation keys off the per-run metrics, so a scored run with no trace used to contribute dollars to the aggregate with no brain check at all.

**§7, the cost source is the run's, not `run_start`'s.** `run_start.config.cost_source` is decided by `art30/brains/driver.py` before the CLI has named its model, and `pricing.priced(None)` is optimistic there by construction, so a `claude` run always starts out saying `cli_estimate`. A CLI whose default model has no price entry then prices every step at 0.0, settles on `cost_source: "unpriced"` in `driver._cost_source()`, writes that to `record.json`'s provenance — and the report, reading only the first line of the trace, printed "Cost per task (estimate at list prices) | $0.00", which is exactly the `$0.00`-reads-as-free outcome ADR 0008 item 3 forbids. `_collect` now reads each run's `record.json` beside its `metrics.json` and lets `provenance.cost_source` and `provenance.brain` override the `run_start.config` values, keeping `run_start` as the fallback for a run that produced no record. `tables.py`'s existing `n/a` branch fires from there.

**§6, `brain_model`, and the three settings a cell does not pin by value.** `metrics.json` asserted `"model": "claude-opus-5"` — the API brain's pinned `ART30_MODEL` — on sweeps where the CLI chose the model. `provenance.brain_model` is the only record of what answered (`run_start.config.brain_model` is the *configured* value, null in the acceptance run). `metrics.json` now carries `"brain_model"` beside `"brain"` at the top level and in every arm block, `"model"` is the observed model when `brain != "api"`, and a **fifth refusal** fires when the runs do not share one `brain_model` — the drift the `prompt_sha` fallback cannot see, because the instruction text is a constant of the checkout and would compare equal across two arms swept at two different CLI defaults.

`plan.PINS` gained `ART30_CLAUDE_MODEL`, `ART30_CODEX_MODEL` and `ART30_CODEX_PRICES`, all pinned to the empty string, which `art30/settings.py` `_env_layer` reads as no value. They are pinned *away*, not to a number: unpinned, an exported `ART30_CLAUDE_MODEL` moved every cell of a sweep and an exported `ART30_CODEX_PRICES` moved every dollar in the cost column, and neither appears in `provenance.config.overridden`, which `art30/config.py` computes from its five request variables. What the CLI then chose is recorded rather than pinned, and the `brain_model` refusal above is what checks it.

**§7.2, the tokens row splits the cache column.** The row folded `cache_read` and `cache_write` into one `cached` number, but a cache read prices at 0.1x input and `art30/brains/pricing.py` charges Claude Code's one-hour cache writes at 2x input. The row exists "so the estimate can be checked against the price table without opening a trace", and folded together the arithmetic could not be reproduced from it. The row is now *Tokens per run (input · output · cache read · cache write)*; the arm block keeps `tokens_cached_mean` as read + write for continuity and adds `tokens_cache_read_mean` and `tokens_cache_write_mean`. The acceptance run reads `14 · 9,435 · 114,399 · 29,249` where it used to read `14 · 9,435 · 143,648`.

**`trace_checks.check_steps` takes its brain as an argument.** Check 12's brain reached the check through a module-level dict keyed by `str(path)`, written by `check_start` and never cleared: the verdict depended on call order and on process-lifetime state, any direct caller got the strict `api` default with no way to say otherwise, and the map grew one entry per trace for the life of the process. `check_steps(path, steps, accepted, brain=None)` now takes it, falls back to the dict when it is not passed, and pops the entry on the way out. `trace_check.check_trace` is unchanged.

**Line rule.** These additions took `report.py` past ~300 lines, so the reading half moved to a new sibling, `evals/harness/facts.py`: one run's trace, the record it delivered and the metrics it was scored at, turned into the rows and facts the refusals read. `report.py` keeps the plan expansion, the five refusals, the two files it reads by name — the timing file and the labelling sidecars — and every path a sandboxed report redirects, `_traces_root` included, which is why the trace root is computed there and passed in. `report.py` is 289 lines, `facts.py` 141; `reverify.py` is 247.
