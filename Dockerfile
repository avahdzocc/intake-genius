FROM python:3.12-slim

WORKDIR /app

# Install dependencies separately so layer is cached
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

COPY src/ src/

# Create data directory for SQLite
RUN mkdir -p /app/data /app/credentials

ENV DATABASE_URL=/app/data/intake_genius.db
ENV PYTHONUNBUFFERED=1
ENV SEED_DEMO_DATA=true

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
