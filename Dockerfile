FROM python:3.12-slim
# uv pinned by version tag; pin by digest before final submission
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY . /app
RUN uv sync --locked
CMD ["make", "eval-replay"]
