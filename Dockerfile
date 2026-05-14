FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir ".[neo4j]"

COPY core/ core/
COPY server/ server/
COPY templates/ templates/
COPY main.py .

EXPOSE 18500

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:18500/api/system/health')" || exit 1

CMD ["python", "main.py", "start", "--host", "0.0.0.0", "--port", "18500"]
