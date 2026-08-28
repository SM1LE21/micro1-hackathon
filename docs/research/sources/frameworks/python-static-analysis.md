# Source excerpts — Python static analysis for a call graph

What the standard library gives us, and what the existing call-graph tools are. The build decision is in `docs/research/framework-behaviour.md`.

Python version under study: **3.12** (`.python-version` pins 3.12; AGENTS.md fixes it).

---

## 1. The `ast` module

Context: what the module is, and the caveat about grammar stability.

> The `ast` module helps Python applications to process trees of the Python abstract syntax grammar. The abstract syntax itself might change with each Python release; this module helps to find out programmatically what the current grammar looks like.

> Parse the source into an AST node. Equivalent to `compile(source, filename, mode, ast.PyCF_ONLY_AST)`.

[S35]

### Call nodes

> `class ast.Call(func, args, keywords)`
>
> A function call. `func` is the function, which will often be a `Name` or `Attribute` object. Of the arguments:
>
> * `args` holds a list of the arguments passed by position.
> * `keywords` holds a list of `keyword` objects representing arguments passed by keyword.

[S35]

> `class ast.Name(id, ctx)`
>
> A variable name. `id` holds the name as a string, and `ctx` is one of the following types.

[S35]

> `class ast.Attribute(value, attr, ctx)`
>
> Attribute access, e.g. `d.keys`. `value` is a node, typically a `Name`. `attr` is a bare string giving the name of the attribute, and `ctx` is `Load`, `Store` or `Del` according to how the attribute is acted on.

[S35]

`Call.func` is therefore either a `Name` (`delete_user()` → the string `delete_user`) or an `Attribute` (`storage.delete()` → the string `delete` hanging off a `Name` whose `id` is `storage`). Nothing in the tree says what `storage` is bound to. The `ast` documentation offers no type inference and does not claim to: it is the parse tree, and the abstract grammar it describes contains no types.

### Definitions and decorators

> `class ast.FunctionDef(name, args, body, decorator_list, returns, type_comment, type_params)`
>
> A function definition.
>
> * `name` is a raw string of the function name.
> * `args` is an `arguments` node.
> * `body` is the list of nodes inside the function.
> * `decorator_list` is the list of decorators to be applied, stored outermost first (i.e. the first in the list will be applied last).

[S35]

> `class ast.ClassDef(name, bases, keywords, body, decorator_list, type_params)`
>
> A class definition.
>
> * `name` is a raw string for the class name
> * `bases` is a list of nodes for explicitly specified base classes.
> * `decorator_list` is a list of nodes, as in `FunctionDef`.

[S35]

`decorator_list` is available as data. `@receiver(post_delete, sender=Avatar)` is a `Call` node in that list with a `keyword` whose `arg` is `"sender"` — readable without executing anything. What the decorator *does* is not readable; that is the boundary.

### Positions and source text

> Instances of `ast.expr` and `ast.stmt` subclasses have `lineno`, `col_offset`, `end_lineno`, and `end_col_offset` attributes. The `lineno` and `end_lineno` are the first and last line numbers of source text span (1-indexed so the first line is line 1) and the `col_offset` and `end_col_offset` are the corresponding UTF-8 byte offsets of the first and last tokens that generated the node.
>
> Note that the end positions are not required by the compiler and are therefore optional.

[S35]

> `ast.get_source_segment(source, node, *, padded=False)`
>
> Get source code segment of the *source* that generated *node*. If some location information (`lineno`, `end_lineno`, `col_offset`, or `end_col_offset`) is missing, return `None`.

[S35]

`lineno` is 1-indexed, which is what a `file:line` citation needs. `get_source_segment` returns `None` rather than guessing when positions are absent, which is the right failure mode for an evidence field.

---

## 2. Existing call-graph tools

Metadata read from PyPI JSON and the GitHub repository API on 2026-08-28.

| Tool | Latest release | Licence | Repo state | Fit |
|---|---|---|---|---|
| **PyCG** (`pycg` 0.0.8) | 2023-11-26 | Apache-2.0 | **archived**, 0 open issues, last push 2023-11-26 | Research-grade whole-program call graph with flow-sensitive assignment tracking. Unmaintained. |
| **pyan3** 2.8.1 | 2026-08-22 | **GPL-2.0** | active (last push 2026-08-22, 8 open issues) | Name-and-binding analyser, actively developed. Licence is copyleft. |
| **code2flow** 2.5.1 | 2023-01-08 | MIT | active-ish (last push 2025-07-27, 38 open issues) | Visualisation tool; multi-language; explicitly approximate. |
| **jedi** 0.20.0 | 2026-05-01 | MIT | active (last push 2026-07-09) | Static inference engine for editors — completion and goto, not a call graph. |
| **pyright** (`pyright` 1.1.411 wrapper) | 2026-06-25 | MIT | very active (last push 2026-08-28) | Type checker. Node.js runtime; JSON output is diagnostics, not a graph. |

[S36], [S37], [S38], [S39], [S40]

Context: pyan's own account of its limits, from the README of the current release.

> Of course, this simple approach cannot correctly track cases where the current binding of `self.f` depends on the order in which the methods of the class are executed. To keep things simple, Pyan decides to ignore this complication, just reads through the code in a linear fashion (twice so that any forward-references are picked up), and uses the most recent binding that is currently in scope.

> **Lambdas and comprehensions are folded into the function that contains them.** A lambda that calls `knot` is drawn as its enclosing function calling `knot`. This hides a scope boundary that is really there

[S37]

Licence, from `LICENSE.md` in the same repository:

> GNU GENERAL PUBLIC LICENSE
>
> Version 2, June 1991

[S37]

Context: code2flow states the general limit up front.

> Code2flow provides a *pretty good estimate* of your project's structure. No algorithm can generate a perfect call graph for a dynamic language – even less so if that language is duck-typed.

and lists the specific ones:

> Code2flow is internally powered by ASTs. Most limitations stem from a token not being named what code2flow expects it to be named.
>
> * All functions without definitions are skipped. This most often happens when a file is not included.
> * Functions with identical names in different namespaces are (loudly) skipped. E.g. If you have two classes with identically named methods, code2flow cannot distinguish between these and skips them.
> * Imported functions from outside your project directory (including from standard libraries) which share names with your defined functions may not be handled correctly.
> * Anonymous or generated functions are skipped. This includes lambdas and factories.
> * If a function is renamed, either explicitly or by being passed around as a parameter, it will be skipped.

[S38]

Every one of these is a name-resolution limit, which is the same class of limit a stdlib `ast` implementation has. None of the four tools resolves `storage.delete()` to a concrete storage backend, and none of them knows that `on_delete=CASCADE` is an edge.

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S35 | `ast` — Abstract Syntax Trees (Python 3.12) | https://docs.python.org/3.12/library/ast.html | 2026-08-28 | Node shapes for `Call`/`Name`/`Attribute`/`FunctionDef`/`ClassDef`, position attributes, `get_source_segment`, `parse` |
| S36 | PyCG — PyPI metadata and GitHub repository | https://pypi.org/pypi/pycg/json · https://github.com/vitsalis/PyCG | 2026-08-28 | Version 0.0.8, Apache-2.0, archived 2023-11-26 |
| S37 | pyan — PyPI metadata, README and LICENSE.md | https://pypi.org/pypi/pyan3/json · https://github.com/Technologicat/pyan | 2026-08-28 | Version 2.8.1 (2026-08-22), GPL-2.0, self-described resolution limits |
| S38 | code2flow — PyPI metadata and README | https://pypi.org/pypi/code2flow/json · https://github.com/scottrogowski/code2flow | 2026-08-28 | Version 2.5.1, MIT, "pretty good estimate", known limitations list |
| S39 | jedi — PyPI metadata and GitHub repository | https://pypi.org/pypi/jedi/json · https://github.com/davidhalter/jedi | 2026-08-28 | Version 0.20.0, MIT, editor-oriented scope |
| S40 | pyright — PyPI wrapper metadata and GitHub repository | https://pypi.org/pypi/pyright/json · https://github.com/microsoft/pyright | 2026-08-28 | Version 1.1.411, MIT, type checker not a call graph |
