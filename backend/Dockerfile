FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# Create the log directory and run as a non-root user.
RUN mkdir -p /app/logs && \
    useradd --create-home --uid 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Default command runs the web API; the worker service overrides this.
# Threaded (gthread) workers so long-lived SSE streams don't tie up a whole
# worker process the way sync workers would.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", \
     "--worker-class", "gthread", "--workers", "2", "--threads", "8", \
     "--timeout", "120", "--keep-alive", "5", \
     "--access-logfile", "-", "wsgi:app"]
