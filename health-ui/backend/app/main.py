from fastapi import FastAPI
from app.api.metrics import router as metrics_router
from app.api.workflow_api import router as workflow_router

app = FastAPI(title="Health Aggregator API")

app.include_router(metrics_router, prefix="/api")
app.include_router(workflow_router, prefix="/api")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
