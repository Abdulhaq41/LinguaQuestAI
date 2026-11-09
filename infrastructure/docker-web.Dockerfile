# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS build
WORKDIR /app/apps/miniapp
COPY apps/miniapp/package*.json ./
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then NODE_EXTRA_CA_CERTS=/run/proxy-ca.pem npm ci --strict-ssl=true; else npm ci --strict-ssl=true; fi
COPY apps/miniapp ./
COPY assets /app/assets
RUN npm run build
FROM nginx:stable-alpine
COPY infrastructure/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=nginx:nginx /app/apps/miniapp/dist /usr/share/nginx/html
EXPOSE 80
