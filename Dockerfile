FROM python:3.10.12 AS builder

ENV UV_PROJECT_ENVIRONMENT=/usr/local/
WORKDIR /project

# Download uv
COPY --from=ghcr.io/astral-sh/uv:0.6.4 /uv /bin/uv

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-dev

# ==============================================================================
# main stage
# ==============================================================================
FROM mcr.microsoft.com/playwright/python
WORKDIR /project

COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
RUN python -m playwright install

COPY . .
CMD ["python", "-m", "src.main_loop"]