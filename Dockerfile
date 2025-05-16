FROM python:3.13.2 AS builder

ENV UV_PROJECT_ENVIRONMENT=/usr/local/
WORKDIR /project

# Download uv
COPY --from=ghcr.io/astral-sh/uv:0.6.4 /uv /bin/uv

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-dev

# ==============================================================================
# main stage
# ==============================================================================
FROM python:3.13.2-slim
WORKDIR /project

COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/

COPY . .

RUN python -m playwright install
CMD ["python", "-m", "src.main_loop"]