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
 - `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX`, `AZURE_SEARCH_API_KEY`: Azure AI Search configuration for RAG over TSG content.
	 - Optional: `AZURE_SEARCH_TEXT_FIELD` (default `content`), `AZURE_SEARCH_VECTOR_FIELD` (if using vector search).

Example `.env` (place in `health-ui/.env` during Docker Compose, or in `backend/.env` for local):
```
AZURE_CLIENT_ID=<guid>
AZURE_TENANT_ID=<guid>
AZURE_CLIENT_SECRET=<secret>
PROMETHEUS_QUERY_ENDPOINT=https://<name>.<region>.prometheus.monitor.azure.com
AZURE_AI_PROJECT_ENDPOINT=https://<your-ai-project-endpoint>
AZURE_SEARCH_ENDPOINT=https://<your-search-name>.search.windows.net
AZURE_SEARCH_INDEX=sre-tsg-index
AZURE_SEARCH_API_KEY=<admin-or-query-key>
AZURE_SEARCH_TEXT_FIELD=content
AZURE_SEARCH_VECTOR_FIELD=vector
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

## Why WebSocket for the Workflow API

The diagnostic workflow is a long-running, step-by-step process (ReAct + function calling) that benefits from real-time, bidirectional communication between the UI and backend.

- Real-time streaming: The agent emits incremental events (think/act/observe, tool outputs, status changes). WebSockets let the server push updates immediately without polling or waiting for the full response.
- Bidirectional control: Human-in-the-loop approvals/denials, pause/resume, and cancellation are sent from the client mid-run. Duplex WebSocket messaging supports these control signals natively; SSE is server-to-client only and HTTP would require many request/response cycles.
- Session-centric state: Each workflow maintains context across steps. A persistent WebSocket session simplifies correlation, avoids repeated stateless rehydration, and reduces orchestration overhead.
- Backpressure and cancellation: The client can signal cancel/pause; the server can pace event flow. This is harder to model cleanly with plain HTTP.
- Efficiency: Eliminates repeated polling, reducing backend load and latency. The UI receives granular progress updates, improving UX for multi-minute diagnostics.
- Reliability hooks: Heartbeats/ping-pong and reconnection strategies can be layered for robust UX over flaky networks.

Notes:
- Metrics/health endpoints remain HTTP (short, stateless queries).
- Ensure ingress/proxies permit WebSocket upgrades and suitable timeouts (e.g., Nginx `upgrade` headers, idle timeout > workflow duration).

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

	## Azure AI Search (TSG RAG) Setup

	Use Azure AI Search to index the Troubleshooting Guides (TSGs) for Retrieval-Augmented Generation.

	1. Provision Azure AI Search
		- Create an Azure AI Search service (Basic or Standard) in Azure Portal.
		- Note the service endpoint (e.g., `https://<name>.search.windows.net`) and an Admin key.

	2. Create a `sre-tsg-index`
		- Minimal text-only schema (simple and effective):
		  ```json
		  {
			 "name": "sre-tsg-index",
			 "fields": [
				{"name": "id", "type": "Edm.String", "key": true},
				{"name": "title", "type": "Edm.String", "searchable": true, "filterable": true},
				{"name": "category", "type": "Edm.String", "searchable": true, "filterable": true, "facetable": true},
				{"name": "pod_issue", "type": "Edm.String", "searchable": true, "filterable": true, "facetable": true},
				{"name": "filepath", "type": "Edm.String", "filterable": true},
				{"name": "content", "type": "Edm.String", "searchable": true}
			 ]
		  }
		  ```
		- Optional vector search (advanced): add a `vector` field and `vectorSearch` config. If using integrated vectorization, attach a vectorizer linked to your Azure OpenAI embeddings deployment.

	3. Ingest TSG Markdown files
		- The TSG source files are under `health-ui/backend/tsgs/`.
		- Example Python ingestion (text-only) using `azure-search-documents`:
		  ```powershell
		  pip install azure-search-documents
		  ```
		  ```python
		  import os, glob
		  from azure.search.documents import SearchClient
		  from azure.core.credentials import AzureKeyCredential

		  endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
		  index_name = os.environ.get("AZURE_SEARCH_INDEX", "sre-tsg-index")
		  api_key = os.environ["AZURE_SEARCH_API_KEY"]
		  root = os.path.join("health-ui", "backend", "tsgs")

		  client = SearchClient(endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(api_key))
		  docs = []
		  for path in glob.glob(os.path.join(root, "*.md")):
				with open(path, "r", encoding="utf-8") as f:
					 content = f.read()
				fname = os.path.basename(path)
				title = fname.replace("TSG-", "").replace(".md", "")
				issue = next((p for p in [
					 "CRASHLOOP","IMAGEPULL","PENDING","OOM","LIVENESS","READINESS","DNS","MOUNT","SECURITY","NETPOL","INITFAIL","EVICTED","TERMINATING","CONTAINERCREATING"
				] if p in title.upper()), "GENERAL")
				docs.append({
					 "id": fname,
					 "title": title,
					 "category": "TSG",
					 "pod_issue": issue,
					 "filepath": path.replace("\\", "/"),
					 "content": content
				})
		  client.upload_documents(docs)
		  print(f"Uploaded {len(docs)} TSG docs to index '{index_name}'.")
		  ```

	4. Configure environment
		- Set `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX`, and `AZURE_SEARCH_API_KEY` in your `.env`.
		- For vector search, also set `AZURE_SEARCH_VECTOR_FIELD`.

	5. Retrieval behavior
		- Backend agents can use keyword + semantic search, or vector search if enabled. Ensure fields align with `AZURE_SEARCH_TEXT_FIELD`/`AZURE_SEARCH_VECTOR_FIELD`.

	## ChatAgents (Azure AI Agent Framework)

	Integrate ChatAgents with your Search index through Azure AI Foundry Projects.

	1. Create an Azure AI Project
		- In Azure AI Studio, create a Project and note its endpoint (e.g., `https://<project>.models.ai.azure.com`).

	2. Register Azure AI Search as Knowledge
		- In the Project, add a Knowledge connection to your Azure AI Search service and select the `sre-tsg-index`.
		- Choose retrieval mode: semantic keyword or vector (if configured). Optionally add chunking and page extraction.

	3. Create an Agent with Retrieval
		- Define a Chat Agent and enable Retrieval, selecting the Knowledge you created.
		- Provide system instructions to ground responses in Kubernetes diagnostics and TSGs.

	4. Backend configuration
		- Set `AZURE_AI_PROJECT_ENDPOINT` and Search env vars. The `/api/workflow/test` will use the Project to orchestrate a simple diagnostic step that can query Knowledge.

	5. Quick validation
		- After indexing and attaching Knowledge, call:
		  ```powershell
		  curl -X POST http://localhost:8000/api/workflow/test -H "Content-Type: application/json" -d '{"pod_name":"demo-pod-123"}'
		  ```
		- Inspect responses to confirm the agent retrieves relevant TSG content.

## Notes
- The Dockerfile uses `uv` and creates a virtual environment at `/app/.venv`.
- The backend app entrypoint is `app.main:app` (Uvicorn/ASGI).
- Azure identity uses `DefaultAzureCredential` in metrics API and `AzureCliCredential` in workflow; ensure your environment has the right credentials and access.

