FROM python:3.12-slim
# uv installs deps ~10x faster than pip; this layer is cached and only rebuilds when
# requirements.txt changes, so routine code edits rebuild just the COPY app layer.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
