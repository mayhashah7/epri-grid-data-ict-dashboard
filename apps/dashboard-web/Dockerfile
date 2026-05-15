FROM node:20-alpine AS build
WORKDIR /app
COPY apps/dashboard-web/package.json apps/dashboard-web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY apps/dashboard-web/ ./
RUN npm run build

FROM nginx:alpine
COPY apps/dashboard-web/nginx-runtime.conf /etc/nginx/conf.d/default.conf
RUN printf '#!/bin/sh\nset -e\ncat > /usr/share/nginx/html/config.js <<EOF\nwindow.__AMI_API_BASE__ = "${API_BASE_URL}";\nEOF\necho "[entrypoint] Wrote config.js with API_BASE_URL=${API_BASE_URL}"\n' > /docker-entrypoint.d/40-inject-config.sh \
    && chmod +x /docker-entrypoint.d/40-inject-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
ENV API_BASE_URL=""
EXPOSE 80



