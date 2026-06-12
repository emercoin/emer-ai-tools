FROM python:3.12-slim
# Ownership annotation for the MCP registry (must equal server.json `name`).
LABEL io.modelcontextprotocol.server.name="io.github.emercoin/emercoin-agent"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
CMD ["python", "server.py"]
