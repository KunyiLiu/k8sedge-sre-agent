# Health Aggregator Backend (FastAPI)

FastAPI backend for the Health Aggregator UI. Provides endpoints to query cluster health issues via Azure Managed Prometheus and a simple workflow test using Azure AI Agent Framework.

## Prerequisites
- Python 3.12+ (for local dev)
- PowerShell 5.1 (Windows default shell)
- Optional: `uv` package manager for faster installs
- Docker and Docker Compose (for container testing)
- Azure credentials and access to an Azure Monitor Prometheus workspace

## Configuration
The backend reads configuration from environment variables. For local runs, you can use a `.env` file in the project root (`health-ui`) or in `backend/`. For Docker Compose, you can place `.env` in `health-ui` and Compose will load it automatically.

Required variables:
- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`: Azure service principal for Azure Monitor and Agents.
- `PROMETHEUS_QUERY_ENDPOINT`: Your Azure Monitor Prometheus query endpoint, e.g. `https://<name>.<region>.prometheus.monitor.azure.com`.
- `AZURE_AI_PROJECT_ENDPOINT`: Endpoint for Azure AI Agent Framework Projects (used by `/api/workflow/test`).

Example `.env` (place in `health-ui/.env` during Docker Compose, or in `backend/.env` for local):
```
AZURE_CLIENT_ID=<guid>
AZURE_TENANT_ID=<guid>
AZURE_CLIENT_SECRET=<secret>
PROMETHEUS_QUERY_ENDPOINT=https://<name>.<region>.prometheus.monitor.azure.com
AZURE_AI_PROJECT_ENDPOINT=https://<your-ai-project-endpoint>
```

## Run Locally (without Docker)

Option A — using `uv` (recommended):
1. Install `uv` on Windows.
	```powershell
	(Invoke-WebRequest https://astral.sh/uv/install.ps1 -UseBasicParsing).Content | powershell -noprofile -
	```
2. From `health-ui/backend`, create the virtual env and install deps.
	```powershell
	uv sync
	```
3. Set environment variables (or create `backend/.env`).
4. Start the FastAPI app.
	```powershell
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
	```

Option B — using `pip`:
1. Create and activate a virtual environment.
	```powershell
	cd c:\source\k8sedge-sre-agent\health-ui\backend
	python -m venv .venv
	.\.venv\Scripts\Activate.ps1
	```
2. Install dependencies declared in `pyproject.toml`.
	```powershell
	python -m pip install --upgrade pip
	pip install .
	```
	If `pip install .` fails, install the core packages directly:
	```powershell
	pip install fastapi uvicorn aiohttp httpx python-dotenv azure-identity azure-ai-projects agent-framework agent-framework-azure-ai
	```
3. Set environment variables (or create `backend/.env`).
4. Start the app.
	```powershell
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
	```

## API Quick Test
Once running locally on `http://localhost:8000`:
- Health check:
  ```powershell
  curl http://localhost:8000/healthz
  ```
- Prometheus test query (`/api/metrics/test`):
  ```powershell
  curl http://localhost:8000/api/metrics/test
  ```
- Aggregated health issues (`/api/health/issues`):
  ```powershell
  curl "http://localhost:8000/api/health/issues?namespace=<optional-namespace>"
  ```
- Workflow diagnostic test (`/api/workflow/test`):
  ```powershell
  curl -X POST http://localhost:8000/api/workflow/test -H "Content-Type: application/json" -d '{"pod_name":"demo-pod-123"}'
  ```

## Run with Docker (standalone)
Build and run just the backend container from `health-ui/`:
```powershell
cd c:\source\k8sedge-sre-agent\health-ui
docker build -t sreagent-backend:local ./backend
docker run --rm -p 8000:8000 `
  -e AZURE_CLIENT_ID=$Env:AZURE_CLIENT_ID `
  -e AZURE_TENANT_ID=$Env:AZURE_TENANT_ID `
  -e AZURE_CLIENT_SECRET=$Env:AZURE_CLIENT_SECRET `
  -e PROMETHEUS_QUERY_ENDPOINT=$Env:PROMETHEUS_QUERY_ENDPOINT `
  -e AZURE_AI_PROJECT_ENDPOINT=$Env:AZURE_AI_PROJECT_ENDPOINT `
  sreagent-backend:local
```

## Run via Docker Compose (backend + frontend)
Use the provided `docker-compose.yml` in `health-ui/`.
1. Ensure `health-ui/.env` contains all required variables (including `AZURE_AI_PROJECT_ENDPOINT`).
2. Bring the stack up.
	```powershell
	cd c:\source\k8sedge-sre-agent\health-ui
	docker compose up -d sreagent-backend
	```
	To run both backend and frontend:
	```powershell
	docker compose up -d
	```
3. Test the backend:
	```powershell
	curl http://localhost:8000/healthz
	```

## Notes
- The Dockerfile uses `uv` and creates a virtual environment at `/app/.venv`.
- The backend app entrypoint is `app.main:app` (Uvicorn/ASGI).
- Azure identity uses `DefaultAzureCredential` in metrics API and `AzureCliCredential` in workflow; ensure your environment has the right credentials and access.

