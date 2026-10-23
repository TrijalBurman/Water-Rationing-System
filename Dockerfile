FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml requirements.lock README.md ./
COPY backend ./backend
COPY frontend ./frontend
RUN pip install --no-cache-dir -c requirements.lock . \
    && groupadd --system --gid 10001 waterwise \
    && useradd --system --uid 10001 --gid waterwise --no-create-home waterwise \
    && mkdir -p /app/data \
    && chown -R waterwise:waterwise /app/data

USER waterwise
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
