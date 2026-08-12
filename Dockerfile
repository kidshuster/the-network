FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENABLE_TEST_COMMANDS=false

COPY pyproject.toml README.md ./
COPY bot ./bot
COPY bin/docker-entrypoint.sh /app/bin/docker-entrypoint.sh

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && chmod +x /app/bin/docker-entrypoint.sh \
    && mkdir -p /app/data

ENTRYPOINT ["/app/bin/docker-entrypoint.sh"]
