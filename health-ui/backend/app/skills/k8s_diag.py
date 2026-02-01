from typing import Optional
import json
import logging

try:
    from kubernetes import client, config
except Exception:  # pragma: no cover
    client = None  # type: ignore
    config = None  # type: ignore

logger = logging.getLogger(__name__)

_v1_api = None

def get_v1_api():
    global _v1_api
    if _v1_api is None:
        _load_kube_config()
        _v1_api = client.CoreV1Api()
    return _v1_api


def _load_kube_config() -> None:
    if config is None:
        return
    try:
        # Prefer in-cluster in production
        config.load_incluster_config()
    except Exception:
        # Fallback to local kubeconfig for dev
        config.load_kube_config()


def get_pod_diagnostics(name: str, namespace: str) -> str:
    """
    Fetch status, restart counts, last exit code/reason, and recent/current/previous logs for the first container.
    Useful for diagnosing CrashLoopBackOff and OOMKilled.
    """
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_pod_diagnostics: name={name}, namespace={namespace}")
    v1 = get_v1_api()
    try:
        pod = v1.read_namespaced_pod(name=name, namespace=namespace)
        cstatus = (pod.status.container_statuses or [None])[0]
        last_state = getattr(cstatus, "last_state", None)
        term = getattr(last_state, "terminated", None) if last_state else None
        exit_code = getattr(term, "exit_code", None)
        reason = getattr(term, "reason", None)
        restarts = getattr(cstatus, "restart_count", 0) if cstatus else 0

        current_logs = ""
        try:
            current_logs = v1.read_namespaced_pod_log(name, namespace, tail_lines=200)
        except Exception:
            current_logs = "(no current logs)"

        prev_logs = ""
        if restarts and restarts > 0:
            try:
                prev_logs = v1.read_namespaced_pod_log(name, namespace, previous=True, tail_lines=200)
            except Exception:
                prev_logs = "(no previous logs)"

        report = {
            "phase": pod.status.phase,
            "restarts": restarts,
            "last_exit_reason": reason,
            "last_exit_code": exit_code,
            "current_logs": current_logs,
            "previous_logs": prev_logs,
        }
        return json.dumps(report, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_pod_events(name: str, namespace: str, limit: int = 20) -> str:
    """Return recent events for a Pod (reason + message)."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_pod_events: name={name}, namespace={namespace}, limit={limit}")
    v1 = get_v1_api()
    try:
        # Field selector for involvedObject.name can retrieve Pod events
        field_selector = f"involvedObject.kind=Pod,involvedObject.name={name}"
        ev = v1.list_namespaced_event(namespace=namespace, field_selector=field_selector)
        items = ev.items[-limit:]
        events = [
            {
                "type": getattr(i, "type", None),
                "reason": getattr(i, "reason", None),
                "message": getattr(i, "message", None),
                "count": getattr(i, "count", None),
            }
            for i in items
        ]
        return json.dumps(events, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_image_pull_events(name: str, namespace: str) -> str:
    """Filter Pod events to those likely related to image pull failures."""
    
    logger.debug(f"-----------Calling get_image_pull_events: name={name}, namespace={namespace}")
    data = get_pod_events(name, namespace)
    try:
        events = json.loads(data)
        if not isinstance(events, list):
            return data
        filtered = [
            e for e in events
            if any(
                k in (e.get("reason") or "") or k in (e.get("message") or "")
                for k in ["ImagePull", "Pulling image", "ErrImagePull", "ImagePullBackOff", "Failed to pull image"]
            )
        ]
        return json.dumps(filtered, ensure_ascii=False, indent=2)
    except Exception:
        return data


def get_service_account_details(name: str, namespace: str) -> str:
    """Return details of a ServiceAccount, including referenced imagePullSecrets."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_service_account_details: name={name}, namespace={namespace}")
    v1 = get_v1_api()
    try:
        sa = v1.read_namespaced_service_account(name=name, namespace=namespace)
        info = {
            "name": sa.metadata.name,
            "secrets": [s.name for s in (sa.secrets or []) if getattr(s, "name", None)],
            "imagePullSecrets": [s.name for s in (sa.image_pull_secrets or []) if getattr(s, "name", None)],
        }
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_secret_exists(name: str, namespace: str) -> str:
    logger.debug(f"-----------Calling get_secret_exists: name={name}, namespace={namespace}")
    """Return whether a Secret exists in the namespace."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()
    v1 = get_v1_api()
    try:
        v1.read_namespaced_secret(name=name, namespace=namespace)
        return json.dumps({"exists": True})
    except Exception:
        return json.dumps({"exists": False})


def get_workload_yaml(kind: str, name: str, namespace: str) -> str:
    """Return a cleaned JSON representation of a Pod, Deployment, or StatefulSet."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_workload_yaml: kind={kind}, name={name}, namespace={namespace}")
    
    k = kind.lower()
    try:
        if k == "pod":
            api = client.CoreV1Api()
            obj = api.read_namespaced_pod(name=name, namespace=namespace)
        elif k == "deployment":
            api = client.AppsV1Api()
            obj = api.read_namespaced_deployment(name=name, namespace=namespace)
        elif k == "statefulset":
            api = client.AppsV1Api()
            obj = api.read_namespaced_stateful_set(name=name, namespace=namespace)
        else:
            return f"Unsupported kind: {kind}. Use 'Pod', 'Deployment', or 'StatefulSet'."

        # Convert to dictionary
        data = obj.to_dict()

        # --- Cleaning Logic ---
        # managedFields can be 50% of the total YAML size—useless for diagnostics
        if "metadata" in data:
            data["metadata"].pop("managedFields", None)
            data["metadata"].pop("ownerReferences", None) # Optional: remove if not needed
            
        # If the agent is reviewing 'workload', they usually care about spec, not status
        # (Status info is already covered by your get_pod_diagnostics function)
        data.pop("status", None)

        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return f"Tool Error: {str(e)}"

def get_pod_top_metrics(name: str, namespace: str) -> str:
    """Attempt to fetch live pod metrics from metrics.k8s.io; falls back with guidance if unavailable."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_pod_top_metrics: name={name}, namespace={namespace}")
    try:
        co = client.CustomObjectsApi()
        obj = co.get_namespaced_custom_object(
            group="metrics.k8s.io", version="v1beta1", namespace=namespace, plural="pods", name=name
        )
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception as e:
        return (
            "Metrics API unavailable or error. Ensure metrics-server is installed. "
            f"Detail: {str(e)}"
        )


def get_pod_scheduling_events(name: str, namespace: str, limit: int = 20) -> str:
    """Return events related to scheduling (e.g., FailedScheduling) for a Pod."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_pod_scheduling_events: name={name}, namespace={namespace}, limit={limit}")
    v1 = get_v1_api()
    try:
        field_selector = f"involvedObject.kind=Pod,involvedObject.name={name}"
        ev = v1.list_namespaced_event(namespace=namespace, field_selector=field_selector)
        items = ev.items[-limit:]
        sched = [
            {
                "reason": getattr(i, "reason", None),
                "message": getattr(i, "message", None),
                "count": getattr(i, "count", None),
            }
            for i in items
            if (getattr(i, "reason", "") or "").lower().find("schedul") >= 0
        ]
        return json.dumps(sched, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_nodes_overview() -> str:
    """List nodes with allocatable CPU/memory and taints for scheduling analysis."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_nodes_overview")
    v1 = get_v1_api()
    try:
        nodes = v1.list_node()
        data = []
        for n in nodes.items:
            alloc = n.status.allocatable or {}
            taints = [
                {"key": t.key, "value": t.value, "effect": t.effect}
                for t in (n.spec.taints or [])
            ]
            data.append({
                "name": n.metadata.name,
                "allocatable": alloc,
                "taints": taints,
            })
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_pvc_details(name: str, namespace: str) -> str:
    """Return status and bound PV for a PersistentVolumeClaim used by a Pod."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_pvc_details: name={name}, namespace={namespace}")
    v1 = get_v1_api()
    try:
        pvc = v1.read_namespaced_persistent_volume_claim(name=name, namespace=namespace)
        info = {
            "name": pvc.metadata.name,
            "status": getattr(pvc.status, "phase", None),
            "volumeName": getattr(pvc.spec, "volume_name", None),
            "storageClass": getattr(pvc.spec, "storage_class_name", None),
            "accessModes": getattr(pvc.spec, "access_modes", []),
            "resources": getattr(pvc.spec, "resources", {}).to_dict() if getattr(pvc.spec, "resources", None) else {},
        }
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_namespace_resource_quota(namespace: str) -> str:
    """Return ResourceQuota objects for a namespace to detect quota-related Pending states."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_namespace_resource_quota: namespace={namespace}")
    v1 = get_v1_api()
    try:
        rq = v1.list_namespaced_resource_quota(namespace=namespace)
        return json.dumps([r.to_dict() for r in rq.items], ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def get_namespace_limit_ranges(namespace: str) -> str:
    """Return LimitRange objects to understand default requests/limits constraints."""
    if client is None:
        return "Tool Error: kubernetes client not installed"
    _load_kube_config()

    logger.debug(f"-----------Calling get_namespace_limit_ranges: namespace={namespace}")
    v1 = get_v1_api()
    try:
        lr = v1.list_namespaced_limit_range(namespace=namespace)
        return json.dumps([l.to_dict() for l in lr.items], ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Tool Error: {str(e)}"


def create_tools():
    """Return a list of all diagnostic tool callables for agent registration."""
    return [
        get_pod_diagnostics,
        get_pod_events,
        get_image_pull_events,
        get_service_account_details,
        get_secret_exists,
        get_workload_yaml,
        get_pod_top_metrics,
        get_pod_scheduling_events,
        get_nodes_overview,
        get_pvc_details,
        get_namespace_resource_quota,
        get_namespace_limit_ranges,
    ]
