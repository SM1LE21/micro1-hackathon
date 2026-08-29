FROM python:3.12-slim
# uv pinned by version tag; pin by digest before final submission
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends make git && rm -rf /var/lib/apt/lists/*
# the dev group (pytest) is installed at build time so `make smoke` works offline inside the container
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY art30 ./art30
RUN uv sync --locked --no-install-project
COPY . /app
RUN uv sync --locked
# make eval-replay ends in `git diff --exit-code -- results/metrics.json`, so .git stays in the context
CMD ["make", "eval-replay"]
