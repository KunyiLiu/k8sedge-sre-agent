# --- Stage 1: Build Stage ---
FROM node:20-alpine AS builder
WORKDIR /app

# Copy package files and install dependencies
# This layer is cached unless you change your package.json
COPY package*.json ./
RUN npm install

# Copy EVERYTHING (including index.html, vite.config.ts, and src)
COPY . .

# Run the build command defined in your package.json
RUN npm run build

# --- Stage 2: Production Stage ---
FROM nginx:alpine

# Copy the build output (dist folder) to Nginx's serve directory
# Vite puts everything from 'public' and your 'src' into 'dist' automatically
COPY --from=builder /app/dist /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf

# EXPOSE port 80 for AKS/Docker
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]