from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.metrics import router as metrics_router
from app.api.workflow_api import router as workflow_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # await close_project_client()

app = FastAPI(title="Health Aggregator API", lifespan=lifespan)

app.include_router(metrics_router, prefix="/api")
app.include_router(workflow_router, prefix="/api")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
