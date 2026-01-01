import httpx
from datetime import datetime
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter

router = APIRouter()
# 1. Get the Query Endpoint from your Azure Monitor Workspace "Overview" page
# It looks like: https://<name>.<region>.prometheus.monitor.azure.com
PROMETHEUS_QUERY_ENDPOINT = "https://defaultazuremonitorworkspace-wus2-ephda2e6e0dteqfh.westus2.prometheus.monitor.azure.com"

# Initialize credential (this will automatically use your ServiceAccount token in AKS)
credential = DefaultAzureCredential()

@router.get("/metrics/test")
async def query_prometheus():
    # 2. Get the Azure Token for Prometheus
    # The 'scope' for Managed Prometheus is always this specific URL
    token = credential.get_token("https://prometheus.monitor.azure.com/.default")

    async with httpx.AsyncClient() as client:
        # 3. Construct the PromQL query
        # 'up' is the standard metric to check if targets are being scraped
        params = {"query": "up"} 
        headers = {"Authorization": f"Bearer {token.token}"}

        response = await client.get(
            f"{PROMETHEUS_QUERY_ENDPOINT}/api/v1/query",
            params=params,
            headers=headers
        )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()
