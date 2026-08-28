.PHONY: setup smoke fixtures run baseline advanced eval eval-replay report traces gate-timing check-secrets check-traces verify-docs check-clean

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
	@if [ -f evals/harness/trace_check.py ]; then uv run python -m evals.harness.trace_check traces/; else echo "trace_check.py not built yet - skipped"; fi
	@echo "smoke OK"

fixtures:
	@echo "not implemented - evals/fixtures/gen.py (docs/spec/fixture-generator.md); must leave a clean git diff" && exit 1

run:
	@echo "not implemented - art30 scan evals/fixtures/synthetic/$(CASE) --arm advanced --approve ask --mode $(MODE) --out $(OUT) (docs/spec/07-ui.md; test cases need ART30_UNLOCK_TEST=1)" && exit 1

baseline:
	@echo "not implemented - built after fixtures and harness (ADR 0002 order)" && exit 1

advanced:
	@echo "not implemented - built after the baseline number exists" && exit 1

eval:
	@echo "not implemented - live evaluation, requires ANTHROPIC_API_KEY in .env" && exit 1

eval-replay:
	@echo "not implemented - reproduces results/metrics.json with NO api key, then: git diff --exit-code -- results/metrics.json" && exit 1

report:
	@echo "not implemented - regenerates tables from results/ (docs/spec/05-eval-harness.md section 7)" && exit 1

gate-timing:
	@echo "not implemented - docs/spec/05-eval-harness.md section 9" && exit 1

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
	@! git grep -niE "tk ?media|founta" -- ':!docs/problem/*' ':!AGENTS.md' ':!Makefile' >/dev/null || { echo "forbidden name in tree"; exit 1; }
	@! git log -p --all -- . ':!AGENTS.md' ':!Makefile' | grep -qiE "tk ?media|founta" || { echo "forbidden name in history"; exit 1; }
	@echo "check-clean OK"
