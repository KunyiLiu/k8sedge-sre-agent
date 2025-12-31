# Use official Node image for building
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json tsconfig*.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm install && npm run build

# Use nginx for serving static files
FROM nginx:alpine
WORKDIR /usr/share/nginx/html
COPY --from=builder /app/dist .
COPY public/vite.svg /usr/share/nginx/html/vite.svg
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
