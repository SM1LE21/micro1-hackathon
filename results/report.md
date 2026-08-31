# Evaluation report

Both arms run the same prompt and the same tools; the gate approves by construction in every scored run, so the measured difference is the verifier's (05-eval-harness.md 7.1).

## dev

| Metric | Simple baseline | Agent solution | Change |
|---|---|---|---|
| Erasure-inventory F1 (dev, mean of seeds) | 0.86 ± 0.07 | 0.90 ± 0.06 | +0.03 |
| Human time per task | n/a | n/a | n/a |
| Cost per task (estimate at list prices) | $0.34 | $0.37 | +$0.03 |

Spread of the eval (std over cases): baseline 0.15, advanced 0.10. The ± above is the standard deviation over seeds, never over cases.

| Row | Baseline | Advanced |
|---|---|---|
| Pass (runs) | 9/21 | 11/21 |
| Pass (cases, majority of seeds) | 3/7 | 3/7 |
| pass^3 | 2/7 | 3/7 |
| Regressions | n/a (no previous metrics.json) | n/a (no previous metrics.json) |
| False safe (matched) | 0 | 0 |
| Reaching claims on stores not in the manifest | 7 | 3 |
| False safe in a gate-rejected draft | 0 | 0 |
| Unverified per run | 0.52 | 0.52 |
| Invalid verdict for kind | 0 | 0 |
| Bad citations | 0 | 0 |
| Cost per run | $0.34 | $0.37 |
| Tokens per run (input · output · cache read · cache write) | 13 · 5,031 · 114,941 · 15,759 | 14 · 5,755 · 124,806 · 16,561 |
| Turns · tool calls | 6.7 · 14.0 | 7.0 · 14.2 |
| Machine minutes per run | n/a | n/a |
| success + failure = n | 20 + 1 = 21 | 21 + 0 = 21 |

McNemar (pass, majority of seeds): b=0 c=0 p=1.0000 — no discordant pairs
Paired bootstrap on F1: delta +0.034, 95% CI [-0.007, +0.085] over 10000 resamples, rng seed 20260830.
"False safe" counts matched tuples only; the unmatched half is the row above it.

## test

| Metric | Simple baseline | Agent solution | Change |
|---|---|---|---|
| Erasure-inventory F1 (test, mean of seeds) | 0.88 ± 0.04 | 0.86 ± 0.03 | -0.01 |
| Human time per task | n/a | n/a | n/a |
| Cost per task (estimate at list prices) | $0.37 | $0.50 | +$0.13 |

Spread of the eval (std over cases): baseline 0.09, advanced 0.13. The ± above is the standard deviation over seeds, never over cases.

| Row | Baseline | Advanced |
|---|---|---|
| Pass (runs) | 2/9 | 3/9 |
| Pass (cases, majority of seeds) | 1/3 | 1/3 |
| pass^3 | 0/3 | 1/3 |
| Regressions | n/a (no previous metrics.json) | n/a (no previous metrics.json) |
| False safe (matched) | 0 | 0 |
| Reaching claims on stores not in the manifest | 1 | 0 |
| False safe in a gate-rejected draft | 0 | 0 |
| Unverified per run | 0.00 | 0.00 |
| Invalid verdict for kind | 0 | 0 |
| Bad citations | 4 | 3 |
| Cost per run | $0.37 | $0.50 |
| Tokens per run (input · output · cache read · cache write) | 15 · 6,350 · 145,236 · 13,998 | 16 · 8,698 · 157,188 · 20,788 |
| Turns · tool calls | 7.6 · 16.4 | 8.1 · 16.9 |
| Machine minutes per run | n/a | n/a |
| success + failure = n | 5 + 4 = 9 | 6 + 3 = 9 |

McNemar (pass, majority of seeds): b=0 c=0 p=1.0000 — no discordant pairs With 3 test cases the smallest attainable two-sided p is 0.25, so this test cannot reach p < 0.05 on the test split.
Paired bootstrap on F1: delta -0.014, 95% CI [-0.061, +0.020] over 10000 resamples, rng seed 20260830.
"False safe" counts matched tuples only; the unmatched half is the row above it.

