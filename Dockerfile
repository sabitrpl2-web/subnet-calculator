# Image dasar: Python 3.12 versi ramping
FROM python:3.12-slim

# Salin program uv dari image resminya
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Pasang dependency terlebih dahulu
COPY pyproject.toml .python-version ./
RUN uv sync --no-dev --no-install-project

# Salin kode aplikasi
COPY main.py index.html ./

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "/app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
