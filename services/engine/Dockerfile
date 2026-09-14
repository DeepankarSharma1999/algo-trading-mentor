FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY services/engine/pyproject.toml ./
RUN pip install --no-cache-dir . 2>/dev/null || pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" "pandas>=2.2" "numpy>=1.26,<3" "pydantic>=2.7" \
    "sqlalchemy>=2.0" "psycopg[binary]>=3.1" "pyarrow>=15" "anthropic>=0.40" "scipy>=1.12" "google-genai>=1.0"
COPY services/engine/ ./
COPY packages/schema/strategy.schema.json packages/schema/testable.rules.json /app/schema/
ENV SCHEMA_DIR=/app/schema
EXPOSE 8000
CMD ["uvicorn", "engine.main:app", "--host", "0.0.0.0", "--port", "8000"]
