FROM python:3.11.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.12.17 && uv sync --frozen --no-dev
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 9091
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9091"]
