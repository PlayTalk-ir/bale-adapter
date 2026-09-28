# Bale adapter — production image (Docker Compose on Laravel VPS).
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash app

WORKDIR /app

COPY requirements-docker.txt /app/requirements-docker.txt
RUN pip install --no-cache-dir -r /app/requirements-docker.txt

COPY bale_platform /app/bale_platform
COPY scripts /app/scripts
COPY kb /app/kb
COPY docs /app/docs

RUN mkdir -p /app/.session /app/data /app/kb /app/logs \
    && chown -R app:app /app

USER app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Not published to the host; exposed for documentation and inter-container access.
EXPOSE 8787

# Requires BALE_API_ENABLED=true (default in .env.example for Docker).
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('BALE_API_PORT','8787'), timeout=3)"

CMD ["python", "-m", "bale_platform.runner"]
