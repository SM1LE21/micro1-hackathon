"""The deterministic verifier (docs/spec/03-verifier.md).

`build_graph(root)` reads a repository and returns the `Graph` the reach and check
builders work from: symbols, a name-based call graph with typed edges, the stores
the detectors can see on their own, the entry points where an account deletion can
begin, and the synthetic edges the framework rules R1-R28 add. Nothing here reads
a manifest, a model client or the harness.

Module map, one responsibility each:

| module          | 03-verifier.md | what it knows |
|-----------------|----------------|---------------|
| `discovery.py`  | 1.1            | the skip list, parsing, the R13 string search |
| `symbols.py`    | 1.2, 1.4       | definitions, decorators as data, raw call sites |
| `imports.py`    | 1.3            | the import map |
| `callgraph.py`  | 1.5, 1.6       | CG-1..CG-20 and `build_graph` |
| `binding.py`    | 1.5, CG-15     | the variable-to-model table, references |
| `rules.py`      | rule data      | loading, validation, matching |
| `stores.py`     | 3.1            | relational stores and the relations |
| `subjects.py`   | 3.9            | subject links and the completeness-guard list |
| `services.py`   | 3.2-3.8        | the stores that are not the database |
| `entrypoints.py`| 2              | discovery and the task table |
| `registration.py`| 2.2, 6.2      | the admin per model, a job's schedule |
| `declared.py`   | 2.5            | declared against discovered, and the cap |
| `context.py`    | 3              | the lookups the detectors share |
| `recipients.py` | 3.6            | R22-R24, the third-party stores |
| `facts.py`      | 4.4, R9-R12    | settings, schedules, receivers |
| `engines.py`    | 4.5, R6        | the engine a delete is bound to, and its PRAGMA |
| `findings.py`   | 1.6, 2, 3      | the records the graph carries |
| `astdata.py`    | 1.4            | AST nodes read as data |
| `synthetic.py`  | 4              | SE0-SE11 and the framework facts |
| `primitives.py` | 4.2 SE12       | a primitive attributed to one store |
| `keyed.py`      | 3.10           | the store a keyed primitive's own literal names |
"""

from art30.verify.callgraph import build_graph
from art30.verify.entities import Edge, Symbol
from art30.verify.findings import (Cite, EntryPoint, Graph, Receiver, Relation,
                                   Store, StoreField)
from art30.verify.declared import reconcile, registration_shapes
from art30.verify.rules import RuleSet, load_rules, norm

__all__ = ["build_graph", "load_rules", "norm", "reconcile", "registration_shapes",
           "Cite", "Edge", "EntryPoint", "Graph", "Receiver", "Relation", "RuleSet",
           "Store", "StoreField", "Symbol"]
