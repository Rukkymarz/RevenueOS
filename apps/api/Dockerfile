FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.lock ./
COPY revenueos/ ./revenueos/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . && useradd --system --uid 10001 --home /app appuser && mkdir -p /data/media && chown -R appuser:appuser /data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)" || exit 1
CMD ["uvicorn", "revenueos.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
