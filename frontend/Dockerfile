FROM node:24.16.0-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_APP_NAME="Vigía Financiera"
ARG VITE_APP_SHORT_NAME=VIGÍA
ARG VITE_ORGANIZATION="Seguridad financiera · Perú"
ARG VITE_ACCENT_COLOR=#b8ed83
ARG VITE_POLL_INTERVAL_MS=5000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL VITE_APP_NAME=$VITE_APP_NAME VITE_APP_SHORT_NAME=$VITE_APP_SHORT_NAME VITE_ORGANIZATION=$VITE_ORGANIZATION VITE_ACCENT_COLOR=$VITE_ACCENT_COLOR VITE_POLL_INTERVAL_MS=$VITE_POLL_INTERVAL_MS
RUN npm run build
FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://127.0.0.1/health || exit 1
