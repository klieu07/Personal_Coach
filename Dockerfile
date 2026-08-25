FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 coachline \
    && mkdir -p /app/data \
    && chown -R coachline:coachline /app

USER coachline

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

CMD ["python", "-m", "app"]
