# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
# Use npm ci when a lockfile exists, otherwise fall back to npm install.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

# ---- Runtime stage ----
FROM nginx:1.27-alpine

# Backend the SPA proxies /api to. Override at runtime, e.g.
#   -e BACKEND_URL=http://web:8080
ENV BACKEND_URL=http://web:8080

# nginx image renders templates with envsubst on startup.
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
COPY env-config.js.template /usr/share/nginx/html/env-config.js.template

EXPOSE 80
CMD ["sh", "-c", "envsubst < /usr/share/nginx/html/env-config.js.template > /usr/share/nginx/html/env-config.js && exec nginx -g 'daemon off;'" ]
