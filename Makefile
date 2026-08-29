.PHONY: setup smoke test fixtures run baseline advanced eval eval-replay report traces gate-timing check-secrets check-traces verify-docs check-clean

CLAUDE_PROJECT_DIR ?= $(HOME)/.claude/projects/-Users-tun-Documents-micro1-hackathon
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

baseline:
	uv run python -m evals.harness.run --split dev --arms baseline --seeds 1,2,3 --mode live --approve auto --jobs 4

advanced:
	uv run python -m evals.harness.run --split dev --arms advanced --seeds 1,2,3 --mode live --approve auto --jobs 4

eval:
	uv run python -m evals.harness.run --split dev --arms baseline,advanced --seeds 1,2,3 --mode live --approve auto --jobs 4
	uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown

eval-replay:
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.run --split all --arms baseline,advanced --seeds 1,2,3 --mode replay --approve auto --jobs 1 --unlock-test --reason "replay of the committed sweep"
	ART30_REPRODUCIBLE=1 uv run python -m evals.harness.report --runs results/runs --out results/metrics.json --markdown
	git diff --exit-code -- results/metrics.json
	@echo "eval-replay reproduced results/metrics.json"

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
	@test -d "$(CLAUDE_PROJECT_DIR)" || { \
	  echo "author-only target; transcripts not present."; \
	  echo "the rendered trajectory is committed at traces/build-trajectory.html"; \
	  exit 0; }
	uvx claude-code-log@1.5.0 "$(CLAUDE_PROJECT_DIR)" -o traces/build-trajectory.html
	@echo "rendered traces/build-trajectory.html"

# qualification-gate checks (docs/judging/requirements-matrix.md, 08-plan.md section 2)
check-traces:
	@test -n "$$(ls traces/baseline/*.jsonl 2>/dev/null)" || { echo "no baseline traces"; exit 1; }
	@test -n "$$(ls traces/advanced/*.jsonl 2>/dev/null)" || { echo "no advanced traces"; exit 1; }
	@test -f traces/build-trajectory.html || { echo "traces/build-trajectory.html missing"; exit 1; }
	@echo "check-traces OK"

verify-docs:
	@echo "not implemented - re-run make report and diff its table against the README results block" && exit 1

check-clean:
	@! git grep -niE "\btk ?media\b|\bfounta\b" -- ':!docs/problem/*' ':!AGENTS.md' ':!Makefile' >/dev/null || { echo "forbidden name in tree"; exit 1; }
	@! git log -p --all -- . ':!AGENTS.md' ':!Makefile' | grep -qiE "\btk ?media\b|\bfounta\b" || { echo "forbidden name in history"; exit 1; }
	@echo "check-clean OK"
