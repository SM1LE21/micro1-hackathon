.PHONY: setup smoke baseline advanced eval eval-replay report traces

setup:
	uv sync --locked

smoke:
	uv run python -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"
	@test -f .env.example || (echo "missing .env.example" && exit 1)
	@test -f docs/problem/problem-statement.pdf || (echo "missing problem statement" && exit 1)
	@echo "smoke OK"

baseline:
	@echo "not implemented — built after direction decision (ADR 0002)" && exit 1

advanced:
	@echo "not implemented — built after eval harness + baseline" && exit 1

eval:
	@echo "not implemented — live evaluation, requires API key in .env" && exit 1

eval-replay:
	@echo "not implemented — must reproduce results/metrics.json with NO api key" && exit 1

report:
	@echo "not implemented — regenerates tables/figures from results/" && exit 1

traces:
	uvx claude-code-log@latest ~/.claude/projects/-Users-tun-Documents-micro1-hackathon -o traces/build-trajectory.html
	@echo "rendered traces/build-trajectory.html"
