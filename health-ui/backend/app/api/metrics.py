import time
from datetime import datetime
import httpx
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, HTTPException, Query, Body
from app.models import HealthIssue
from typing import List, Optional

router = APIRouter()
# 1. Get the Query Endpoint from your Azure Monitor Workspace "Overview" page
# It looks like: https://<name>.<region>.prometheus.monitor.azure.com
PROMETHEUS_QUERY_ENDPOINT = "https://defaultazuremonitorworkspace-wus2-ephda2e6e0dteqfh.westus2.prometheus.monitor.azure.com"
PROMETHEUS_TOKEN_SCOPE = "https://prometheus.monitor.azure.com/.default"

# Initialize credential (this will automatically use your ServiceAccount token in AKS)
credential = DefaultAzureCredential()

@router.get("/metrics/test")
async def query_prometheus():
    # 2. Get the Azure Token for Prometheus
    # The 'scope' for Managed Prometheus is always this specific URL
    token = credential.get_token(PROMETHEUS_TOKEN_SCOPE)

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

def format_duration(seconds: float) -> str:
    if seconds < 0: seconds = 0
    hours, rem = divmod(int(seconds), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02}h {minutes:02}m"

async def fetch_prom(query: str, token: str):
    # Use POST to avoid URL length and character encoding issues
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PROMETHEUS_QUERY_ENDPOINT}/api/v1/query", # Ensure this is the base endpoint /api/v1/query
            data={"query": query}, # 'data' in httpx sends form-encoded POST
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return []
        return response.json().get("data", {}).get("result", [])

@router.get("/health/issues", response_model=List[HealthIssue])
async def get_all_health_issues(namespace: Optional[str] = Query(None, description="Namespace to filter issues by")):
    """
    Returns a list of health issues for pods, nodes, and deployments.
    Optionally filter by namespace.
    """
    try:
        token = credential.get_token(PROMETHEUS_TOKEN_SCOPE).token
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Azure token: {e}")
    now = time.time()
    all_issues = []

    import asyncio
    try:
        # 1. THE POWER QUERY: Gets Reason + Transition Time (or Created time as fallback)
        # This query joins the error reason with the creation time of that pod
        if namespace:
            pod_query = (
                f'(kube_pod_container_status_waiting_reason{{namespace="{namespace}"}} == 1) '
                '* on(pod) group_left '
                f'kube_pod_created{{namespace="{namespace}"}}'
            )
            node_query = f'kube_node_status_condition{{condition="Ready", status!="true", namespace="{namespace}"}} == 1'
            dep_query = f'kube_deployment_status_replicas_unavailable{{namespace="{namespace}"}} > 0'
        else:
            pod_query = (
                '(kube_pod_container_status_waiting_reason == 1) '
                '* on(pod) group_left '
                'kube_pod_created'
            )
            node_query = 'kube_node_status_condition{condition="Ready", status!="true"} == 1'
            dep_query = 'kube_deployment_status_replicas_unavailable > 0'
    
        pod_results, node_results, dep_results = await asyncio.gather(
            fetch_prom(pod_query, token),
            fetch_prom(node_query, token),
            fetch_prom(dep_query, token)
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to query Prometheus: {e}")

    # --- 1. POD ISSUES (CrashLoop or Not Running) ---
    for item in pod_results:
        labels = item["metric"]
        reason = labels.get("reason", "Pending")
        created_at = float(item["value"][1])
        timespan = int(now - created_at)
        all_issues.append(HealthIssue(
            issueType=reason,
            severity="High",
            resourceType="Pod",
            namespace=labels.get("namespace"),
            resourceName=labels.get("pod"),
            container=labels.get("container"),
            unhealthySince=format_duration(timespan),
            unhealthyTimespan=timespan,
            message=f"Container is in {reason} state."
        ))

    # --- 2. NODE ISSUES (Not Ready) ---
    for item in node_results:
        node_name = item["metric"]["node"]
        try:
            since_res = await fetch_prom(f'kube_node_status_condition_last_transition_time{{node="{node_name}", condition="Ready"}}', token)
            start_time = float(since_res[0]["value"][1]) if since_res else now
        except Exception:
            start_time = now
        timespan = int(now - start_time)
        all_issues.append(HealthIssue(
            issueType="NodeNotReady",
            severity="Critical",
            resourceType="Node",
            resourceName=node_name,
            unhealthySince=format_duration(timespan),
            unhealthyTimespan=timespan,
            message="Node is not responding to heartbeats."
        ))

    # --- 3. DEPLOYMENT ISSUES (Degraded) ---
    for item in dep_results:
        all_issues.append(HealthIssue(
            issueType="DeploymentDegraded",
            severity="High",
            resourceType="Deployment",
            namespace=item["metric"].get("namespace"),
            resourceName=item["metric"]["deployment"],
            unhealthySince="Check Pods",
            unhealthyTimespan=0,
            message="Desired replicas do not match available replicas."
        ))

    return all_issues

@router.post("/health/diagnostic")
async def run_diagnostic(issue: HealthIssue = Body(...)):
    """
    Placeholder diagnostic API. Accepts a HealthIssue as POST body and returns a dummy result.
    """
    return {"status": "received", "issue": issue.dict(), "diagnostic": "Not implemented"}