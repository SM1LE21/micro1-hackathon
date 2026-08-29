# Docker rehearsal — attempted 2026-08-29, not runnable on this machine

Status: **not rehearsed.** No container runtime exists on the build machine, so the three commands
below were never executed. What follows is the attempt, a static review of the Dockerfile against
what those commands would do (one blocker found and reproduced without Docker), and the checklist
the rehearsal has to satisfy in its slot, `08-plan.md`:176 (Mon 14:30-15:00). If it has not
happened by 15:00, kill switch 10 (`08-plan.md`:247, cut list item 4 at `08-plan.md`:273) cuts it
and REPRODUCE.md says the path is unrehearsed.

## What was attempted

```
$ docker version
zsh: command not found: docker

$ which docker colima podman
docker not found
```

Nothing else is installed either: no `/Applications/Docker.app`, no OrbStack, no Rancher Desktop,
no Podman, no `~/.docker`, no `/var/run/docker.sock`. This is an absent runtime, not a stopped
daemon, so no `colima start` or `docker desktop start` recovers it. Installing one costs a download
the offline build machine has no budgeted slot for; the rehearsal moves to whichever machine records
the video, or to the author's own before submission.

The commands the rehearsal must run, verbatim:

```
docker build -t hackathon .
docker run --rm hackathon make smoke
docker run --rm hackathon make eval-replay
```

## Blocker found by static review: `make smoke` cannot pass inside this image

`Dockerfile` line 5 sets `ENV ... UV_NO_DEV=1`, and it stays set at runtime. `pytest` is in
`[dependency-groups] dev` in `pyproject.toml`, so `uv sync --locked` at build time installs
everything except pytest, and `make smoke`'s last real step, `uv run pytest tests -q`, has nothing
to spawn. Reproduced in this repository, without Docker and without touching the
environment (verified 2026-08-29, uv 0.11.26; `--dry-run` resolves and prints, it writes nothing):

```
$ UV_NO_DEV=1 uv sync --locked --dry-run
Would use project environment at: .venv
Resolved 29 packages in 4ms
Would uninstall 5 packages
 - iniconfig==2.3.0
 - packaging==26.3
 - pluggy==1.6.0
 - pygments==2.21.0
 - pytest==9.1.1
$ uv sync --locked --dry-run
Would use project environment at: .venv
Resolved 29 packages in 3ms
Checked 27 packages in 0.52ms
Would make no changes
```

The five packages the variable removes are pytest and its dependencies, and the second command is
the control: without the variable the same lockfile leaves the environment alone.

The error itself, produced from the same lockfile into a scratch environment so the repository's own
`.venv` is untouched (`UV_PROJECT_ENVIRONMENT` abbreviated to `<scratch>`; 22 packages installed,
not 27):

```
$ UV_PROJECT_ENVIRONMENT=<scratch> UV_NO_DEV=1 uv sync --locked
Using CPython 3.12.13
Creating virtual environment at: <scratch>
Resolved 29 packages in 3ms
Installed 22 packages in 21ms
$ UV_PROJECT_ENVIRONMENT=<scratch> UV_NO_DEV=1 uv run pytest --version
error: Failed to spawn: `pytest`
  Caused by: No such file or directory (os error 2)
(exit 2)
```

That is exactly the missing-binary error the rehearsal is supposed to rule out, and it also breaks
`make test` in the image. `make eval-replay` (the image's `CMD`) does not import pytest and is
unaffected.

Recommended fix, for the lead to make (this page edits no file): **drop `UV_NO_DEV=1` from the
`ENV` line.** The dev group is one package; installing it at build time keeps the container able to
run the full suite with no network at run time. `uv run` reads the same variable
(`uv run --help`: `--no-dev  Disable the development dependency group [env: UV_NO_DEV=]`), so the
ENV line must go: installing pytest at build time while leaving `UV_NO_DEV=1` set would let the
first `uv run` inside the container uninstall it again. That is what rules out the otherwise
tempting "keep the ENV line, add the dev group to the sync". The alternatives are worse:

- `docker run -e UV_NO_DEV=0 ... make smoke` works (verified in the same scratch environment:
  `UV_NO_DEV=0 uv run pytest --version` printed `Installed 5 packages in 4ms` then `pytest 9.1.1`),
  but it installs pytest *inside the container at run time*, which needs a network the judge may not
  have and is a flag nobody will remember.
- Keeping `UV_NO_DEV=1` and telling judges not to run `make smoke` in Docker contradicts
  `REPRODUCE.md`, which offers Docker as the path "for a machine without uv".

## The rest of the static review

Nothing else below blocks the rehearsal; each is a thing to watch for while it runs.

- **`uv` is pinned to a moving tag.** `COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/` pulls
  whatever `0.12` points at that day. The Dockerfile's own comment says to pin by digest before
  submission. The rehearsal is the moment to read the built image's `uv --version` and write the
  digest in, so the version in the image matches the one `REPRODUCE.md` names.
- **`.git` is in the build context on purpose.** `make eval-replay` ends in
  `git diff --exit-code -- results/metrics.json`; `.dockerignore` documents why `.git` is not
  excluded. Both the git binary and the repository must survive into the image, and `make` is
  installed on the same line. If the rehearsal ever runs with `--user`, git will refuse the tree it
  does not own ("detected dubious ownership"); run as the image's default root, or add
  `git config --global --add safe.directory /app`.
- **`evals/cache/` must reach the image.** Replay is cache-only and fails loudly on a miss
  (ADR 0003 §6). The directory does not exist yet; `.dockerignore` does not exclude it, so once the
  sweep commits it the `COPY . /app` picks it up. The rehearsal has to happen **after** the recorded
  sweep, or it can only reproduce the miss, not the numbers.
- **`traces/build-trajectory.html` is excluded** by `.dockerignore`, so `make check-traces` inside
  the container will fail on a file that is committed in the repository. Do not run that target in
  Docker; it is a host-side check.
- **Layer nit.** `COPY art30 ./art30` sits above `RUN uv sync --locked --no-install-project`, which
  by definition does not install the project, so every edit under `art30/` busts the dependency
  layer for nothing. Moving that COPY below the sync would keep the cache warm. Not worth a change
  this close to the freeze unless the build is being edited anyway.
- **Context size** is about 30 MB (71 MB tree, minus the 41 MB `.venv` that `.dockerignore`
  excludes), of which 14 MB is `.git` and 11 MB the generated fixtures. `.pytest_cache/` is not
  excluded and could be; it is a few hundred kilobytes.

## What the rehearsal must show

Run it on a machine with Docker, after the recorded sweep is committed, and paste the real outputs
into this file under a dated heading. It passes when all of this is true:

1. `docker build -t hackathon .` exits 0 from a clean cache, and its wall time is recorded.
   The uv version the image ended up with is recorded too (`docker run --rm hackathon uv --version`).
2. `docker run --rm hackathon make smoke` prints the Python 3.12 assertion, the import check,
   the trace_check pass, the pytest summary and `smoke OK`, and exits 0. The host baseline, re-run
   2026-08-29, is `652 passed, 2 skipped, 2 xfailed in 2.53s` then `smoke OK`, in 3.0 s wall (the
   full paste is in `README.md` §`make setup && make smoke`); the container should agree on the
   counts.
3. `docker run --rm hackathon make eval-replay` reproduces `results/metrics.json` and ends in
   `git diff --exit-code` with no diff, printing the summary block `05-eval-harness.md` §10 fixes
   and `eval-replay reproduced results/metrics.json`. Wall time recorded.
4. No step needs a network, an API key, or a flag not written in `REPRODUCE.md`.
5. Any failure is a stated refusal with an exit code, not a Python traceback and not a
   "command not found".

Until the cache exists, the honest rehearsal target is weaker and still worth running: the build
succeeds, `make smoke` passes, and `make eval-replay` refuses **for the documented reason**. On the
host today that refusal is a manifest that has not been labelled yet, not a replay miss:

```
$ ART30_REPRODUCIBLE=1 uv run python -m evals.harness.run --split all --arms baseline,advanced --seeds 1,2,3 --mode replay --approve auto --jobs 1 --unlock-test --reason "evidence check, no writes" --out <scratch>
cannot read manifest /Users/tun/Documents/micro1-hackathon/evals/fixtures/manifests/R01.yaml: [Errno 2] No such file or directory: '/Users/tun/Documents/micro1-hackathon/evals/fixtures/manifests/R01.yaml'
(exit 1)
```

That is `make eval-replay`'s first command with `--out` redirected to a scratch directory, so the
check wrote nothing under `results/`; the abort happens before `--out` is used, so the line is the
one the Makefile target prints.

R01 to R04 are unlabelled, so `--split all` aborts before any cell runs. That is the pre-flight gate
doing its job, printed as one line with no traceback, and it is what a container run would print
today. Once the four manifests land and the cache is empty, the same command reaches the cells and
ends in the replay-miss path (`stop_condition: replay_miss`, exit 5, "the cache held no response for
the request", `evals/harness/cells.py`). Both are acceptable rehearsal outcomes before the sweep;
a traceback is not.

## Timings

None recorded. Nothing ran.
