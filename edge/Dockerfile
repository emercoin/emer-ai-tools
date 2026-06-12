FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
# --proxy-headers/--forwarded-allow-ips: trust Caddy's X-Forwarded-Proto so the
# app builds https (not http) URLs/redirects behind the TLS terminator.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
