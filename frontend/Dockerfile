# CollectAI frontend image (E1-S5): build the SPA, then serve the static
# bundle with nginx (same config `web` uses to proxy /api in compose).
# Built with repo root as the build context (docker-compose.yml's `web`
# service sets `context: .`) so this can also COPY `deploy/nginx/`.

FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/. .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
