# Two stages: Node builds the static site, Nginx serves it.
# Node, npm and the node_modules folder never reach the final image.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# The unprivileged Nginx image runs as a normal user and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.30-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
