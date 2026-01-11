# Health Aggregator Frontend (React + Vite)

Minimal React + TypeScript app built with Vite. Serves a UI that calls backend APIs under `/api/*`.

## Prerequisites
- Node.js 20+
- npm (or yarn/pnpm)
- Backend running at `http://localhost:8000` for local dev (proxied by Vite)

## Run Locally
From `health-ui/frontend`:
```bash
# Install dependencies
npm install

# Start Vite dev server (http://localhost:5173)

```
- API requests to `/api/*` are proxied to `http://localhost:8000` (see `vite.config.ts`). Start the backend before the frontend.

## Build
```bash
npm run build
```
Build output goes to `dist/`.

## Test in Docker (standalone)
Build a production image and run Nginx:
```bash
cd ./health-ui

docker build -t sreagent-frontend:local ./frontend

docker run --rm -p 8080:80 sreagent-frontend:local
```
Notes:
- The container’s Nginx proxies `/api/*` to `sreagent-backend:8000` (see `nginx.conf`). When running standalone, ensure the backend is reachable or prefer Docker Compose below.

## Run via Docker Compose (frontend + backend)
Use `docker-compose.yml` in `health-ui/` to run both services:
```bash
cd ./health-ui

# Start only the backend first if needed
docker compose up -d sreagent-backend

# Start frontend (depends on backend)
docker compose up -d sreagent-frontend

# Or start both
docker compose up -d
```
- Frontend is served at `http://localhost:8080`.
- `/api/*` requests are proxied to the backend container via Nginx.

## Files of Interest
- `vite.config.ts`: dev server proxy to `http://localhost:8000`.
- `src/api.ts`: frontend calls to `/api/metrics/test`, `/api/health/issues`, `/api/health/diagnostic`.
- `Dockerfile`: multi-stage build (Node builder → Nginx static server).
- `nginx.conf`: serves static files and proxies `/api/*` to the backend service.
      // Enable lint rules for React DOM
