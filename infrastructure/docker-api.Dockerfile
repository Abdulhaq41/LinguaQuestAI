# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then PIP_CERT=/run/proxy-ca.pem pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY --chown=10001:10001 services services
COPY --chown=10001:10001 scripts scripts
COPY --chown=10001:10001 apps/bot apps/bot
COPY --chown=10001:10001 infrastructure/migrations infrastructure/migrations
COPY --chown=10001:10001 content content
COPY --chown=10001:10001 assets/mascots/lexi-generated.png assets/mascots/lexi-generated.png
COPY --chown=10001:10001 alembic.ini ./
RUN useradd --uid 10001 --create-home app
USER app
EXPOSE 8000
CMD ["uvicorn","services.api.main:app","--host","0.0.0.0","--port","8000","--no-access-log"]
