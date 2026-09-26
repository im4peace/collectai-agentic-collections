# CollectAI backend image (E1-S5). One image, two uses in docker-compose:
#   - `migrate` service: `python -m collectai.bootstrap.cli migrate` then `seed`
#   - `api` service:     `uvicorn collectai.bootstrap.main:build_app --factory`
# Multi-stage: a `deps` stage resolves dependencies once, a slim `runtime`
# stage copies only the installed environment and source, no build tools.

FROM python:3.11-slim AS deps
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml alembic.ini constraints.txt ./
COPY src ./src
RUN pip install --no-cache-dir -c constraints.txt --prefix=/install .

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deps /install /usr/local
COPY --from=deps /app/src ./src
COPY --from=deps /app/alembic.ini ./alembic.ini
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "collectai.bootstrap.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
