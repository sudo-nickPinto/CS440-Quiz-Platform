FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
ARG VITE_AUTH0_AUDIENCE
ARG VITE_API_BASE_URL=/api

ENV VITE_AUTH0_DOMAIN=${VITE_AUTH0_DOMAIN} \
    VITE_AUTH0_CLIENT_ID=${VITE_AUTH0_CLIENT_ID} \
    VITE_AUTH0_AUDIENCE=${VITE_AUTH0_AUDIENCE} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.28-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/healthz || exit 1
