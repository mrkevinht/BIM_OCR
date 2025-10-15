FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    pip install ".[worker]"

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
