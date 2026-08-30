.PHONY: setup smoke test fixtures run baseline advanced eval eval-replay eval-replay-local reverify report traces gate-timing check-secrets check-traces verify-docs check-clean skill serve

CLAUDE_PROJECT_DIR ?= $(HOME)/.claude/projects/-Users-tun-Documents-micro1-hackathon
CLAUDE_SESSION_ID ?= 607542c8-6252-4232-8b55-d688feb5e054
CASE ?= S05
MODE ?= live
OUT ?= results/runs

setup:
	uv sync --locked

smoke:
	uv run python -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"
	uv run python -c "import anthropic, yaml, jsonschema"
	@test -f .env.example || (echo "missing .env.example" && exit 1)
	@test -f docs/problem/problem-statement.pdf || (echo "missing problem statement" && exit 1)
	uv run python -m evals.harness.trace_check traces/
	uv run pytest tests -q
	@echo "smoke OK"

test:
	uv run pytest tests -q

fixtures:
	uv run python evals/fixtures/gen.py --all
	uv run python evals/fixtures/gen.py --check
	git diff --exit-code -- evals/fixtures/synthetic evals/fixtures/manifests
	@echo "fixtures clean"

run:
	uv run art30 scan evals/fixtures/synthetic/$(CASE) --arm advanced --case $(CASE) --approve ask --mode $(MODE) --out $(OUT)

SWEEP_CASES ?= $(shell test -f evals/fixtures/manifests/R01.yaml && echo dev)

baseline:
	@test -n "$$ART30_MAX_USD" || grep -q '^ART30_MAX_USD=.' .env 2>/dev/null || { echo "set ART30_MAX_USD in .env before a live sweep (ADR 0005 item 4)"; exit 1; }
	uv run python -m evals.harness.run $(if $(SWEEP_CASES),--split dev,--cases S01,S02,S03,S04,S05,S06,S07) --arms baseline --seeds 1,2,3 --mode live --approve auto --jobs 4
	uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown $(if $(SWEEP_CASES),--split dev,--cases S01,S02,S03,S04,S05,S06,S07) --arms baseline

advanced:
	@test -n "$$ART30_MAX_USD" || grep -q '^ART30_MAX_USD=.' .env 2>/dev/null || { echo "set ART30_MAX_USD in .env before a live sweep (ADR 0005 item 4)"; exit 1; }
	uv run python -m evals.harness.run $(if $(SWEEP_CASES),--split dev,--cases S01,S02,S03,S04,S05,S06,S07) --arms advanced --seeds 1,2,3 --mode live --approve auto --jobs 4
	uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown $(if $(SWEEP_CASES),--split dev,--cases S01,S02,S03,S04,S05,S06,S07)

eval:
	uv run python -m evals.harness.run --split dev --arms baseline,advanced --seeds 1,2,3 --mode live --approve auto --jobs 4
	uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown

eval-replay:
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.run --split all --arms baseline,advanced --seeds 1,2,3 --mode replay --approve auto --jobs 1 --unlock-test --reason "replay of the committed sweep"
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
	git diff --exit-code -- results/metrics.json
	@echo "eval-replay reproduced results/metrics.json"

# a local-brain sweep has no recorded responses to replay: re-run the verifier over every
# recorded submission, re-score every record, re-aggregate, and diff (docs/runbook-sweeps.md)
reverify:
	uv run python -m evals.harness.reverify --runs results/runs

eval-replay-local:
	uv run python -m evals.harness.reverify --runs results/runs
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
	git diff --exit-code -- results/metrics.json
	@echo "eval-replay-local reproduced results/metrics.json"

report:
	uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown

gate-timing:
	uv run python -m evals.harness.run --cases S03,S05,R01,R02,R03,R04 --arms advanced --seeds 1 --mode replay --approve ask --jobs 1 --out results/.gate-timing --unlock-test --reason "gate timing, replay"
	@echo "record one line per case in results/gate-timing.yaml"

# author-only: gitleaks over full history before the final push (AGENTS.md code rules)
check-secrets:
	@command -v gitleaks >/dev/null || { echo "gitleaks not installed (author-only target): brew install gitleaks"; exit 1; }
	gitleaks detect --source . --log-opts="--all" --redact

# author-only: the transcripts live outside the repository. Judges read the committed HTML.
traces:
	@if [ -d "$(CLAUDE_PROJECT_DIR)" ]; then \
	  uvx claude-code-log@1.5.0 "$(CLAUDE_PROJECT_DIR)/$(CLAUDE_SESSION_ID).jsonl" -o traces/build-trajectory.html \
	  && gzip -9 -f traces/build-trajectory.html \
	  && echo "rendered traces/build-trajectory.html.gz (gunzip to read; the main session transcript, subagent transcripts excluded)"; \
	else \
	  echo "author-only target; transcripts not present."; \
	  echo "the rendered trajectory is committed at traces/build-trajectory.html.gz"; \
	fi

# qualification-gate checks (docs/judging/requirements-matrix.md, 08-plan.md section 2)
check-traces:
	uv run python -m evals.harness.failure_index
	@test -n "$$(ls traces/baseline/*.jsonl 2>/dev/null)" || { echo "no baseline traces"; exit 1; }
	@test -n "$$(ls traces/advanced/*.jsonl 2>/dev/null)" || { echo "no advanced traces"; exit 1; }
	@test -f traces/build-trajectory.html.gz || { echo "traces/build-trajectory.html.gz missing"; exit 1; }
	@echo "check-traces OK"

verify-docs:
	uv run python -m evals.harness.verify_docs

check-clean:
	@! git grep -niE "\btk ?media\b|\bfounta\b" -- ':!docs/problem/*' ':!AGENTS.md' ':!Makefile' >/dev/null || { echo "forbidden name in tree"; exit 1; }
	@! git log -p --all -- . ':!AGENTS.md' ':!Makefile' | grep -qiE "\btk ?media\b|\bfounta\b" || { echo "forbidden name in history"; exit 1; }
	@echo "check-clean OK"

# the three surfaces (ADR 0007): the skill is generated from the prompt files; the website drives the cli
skill:
	uv run python skill/build.py
	uv run python skill/build.py --check
	@echo "skill clean"

serve:
	uv run art30 serve --open
