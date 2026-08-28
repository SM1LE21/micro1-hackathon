# 90-second execution segment (video minutes ~1:00–2:30)

The video runs 3:00–3:30 total: problem + baseline (0:00–1:00), this segment (one realistic execution start to finish), then the comparison table, changelog highlights, the change that contributed most, one removed experiment (2:30–3:30). This file is only the middle segment.

Case: the hard case — a soft-delete that never reaches object storage. Use the real-repo `FileField` instance if a vendored repo shows it naturally; otherwise the synthetic case `S10`. Screen: terminal left, rendered record right. Nothing pre-recorded; one take, cuts allowed only between the timestamps below.

| Time | On screen | Voice |
|---|---|---|
| 0:00–0:10 | Repo tree of the case: `models.py`, `storage.py`, `jobs/purge.py`, `api/account.py` | "A small SaaS: users, avatar uploads in object storage, a payment customer, a nightly purge job. Two questions: what personal data does it hold, and when someone closes their account, is it gone?" |
| 0:10–0:25 | `make run CASE=S10` — tool calls scroll: `list_tree`, `read_file`, `grep`. Step counter visible top right. | "The agent reads the code the way you would — it doesn't run anything. Every read is a tool call in the trace." |
| 0:25–0:40 | Classifier output: table of fields with category and `file:line` | "Twelve fields, six stores. `notes` on the support ticket is flagged from a comment that says it may contain phone numbers — a grep would miss that." |
| 0:40–1:00 | Verifier rejection in the trace, highlighted: `REJECT store=uploads claim=erased reason=no path close_account → storage.delete; helper cleanup_user_files defined at storage.py:41, never called`. Draft revised to `not erased`. | "Here's the moment. The first draft said uploads are deleted, because a cleanup function exists. The verifier walked the call graph from `close_account` and found no path to it. The function is dead code. The claim is struck, the agent revises." |
| 1:00–1:15 | Human gate: approval prompt with risk rating, legal cells shown as `requires human completion`. Press `y`. | "Before anything renders, a person approves. The legal columns are empty on purpose — the agent never writes a legal basis." |
| 1:15–1:30 | Rendered record: Art. 30 inventory, erasure table with one red row, every cell carrying `file:line`. Hover one cell → the line of code. | "Every line in this document points at a line of code. The red row is the bug I shipped in my own product and found a month later. Here it takes forty seconds." |

Hard cuts to avoid: never show the baseline's wrong answer in this segment (it belongs in 0:00–1:00, side by side with this output at 2:30). Never say "compliant".

Checklist before recording: the trace file of this exact run is saved under `traces/advanced/` and its ID appears in the README results table.
