FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

ENV UV_PROJECT_ENVIRONMENT=/usr/local/
WORKDIR /project

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

RUN python -m playwright install-deps
RUN python -m playwright install

COPY . .
CMD ["python", "-m", "src.main_loop"]