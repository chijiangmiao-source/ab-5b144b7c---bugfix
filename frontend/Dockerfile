# Build stage: produce static assets from the React/Vite project.
FROM node:20-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

# Runtime stage: nginx serves assets and reverse-proxies API calls.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html

HEALTHCHECK --interval=5s --timeout=3s --start-period=4s --retries=20 \
  CMD wget -qO- http://127.0.0.1/health >/dev/null 2>&1 || exit 1

EXPOSE 80
