# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /app/apps/miniapp
COPY apps/miniapp/package*.json ./
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then NODE_EXTRA_CA_CERTS=/run/proxy-ca.pem npm ci --strict-ssl=true; else npm ci --strict-ssl=true; fi
COPY apps/miniapp ./
COPY assets /app/assets
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then PIP_CERT=/run/proxy-ca.pem pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
RUN useradd --uid 10001 --create-home app
COPY --chown=10001:10001 services services
COPY --chown=10001:10001 scripts scripts
COPY --chown=10001:10001 apps/bot apps/bot
COPY --chown=10001:10001 infrastructure/migrations infrastructure/migrations
COPY --chown=10001:10001 content content
COPY --chown=10001:10001 assets/mascots/lexi-generated.png assets/mascots/lexi-generated.png
COPY --chown=10001:10001 alembic.ini ./
COPY --from=frontend --chown=10001:10001 /app/apps/miniapp/dist /app/web
USER app
EXPOSE 8000
CMD ["bash", "scripts/hosted_start.sh"]
