import json
import logging
from typing import List, Callable, Optional

logger = logging.getLogger(__name__)


class MockK8sDiag:
    """Mocked Kubernetes diagnostics returning deterministic JSON strings for tests."""

    def __init__(self, profile: Optional[str] = None):
        # Normalize profile to lowercase for simple matching
        self.profile = (profile or "default").lower()

    def _load_kube_config(self) -> None:
        """No-op loader used in tests to mirror k8s config initialization."""
        logger.info("_load_kube_config() called (no-op)")
        return None

    def get_pod_diagnostics(self, name: str, namespace: str) -> str:
        """Fetch status, restart counts, last exit code/reason, and recent/current/previous logs.

        Mirrors `get_pod_diagnostics` in k8s_diag.py but returns deterministic mock data.
        Useful for testing CrashLoopBackOff and OOMKilled patterns without a real cluster.
        """
        logger.debug(f"-----------Calling get_pod_diagnostics(name={name}, namespace={namespace}, profile={self.profile})")
        if self.profile == "imagepullbackoff":
            report = {
                "phase": "ImagePullBackOff",
                "restarts": 0,
                "last_exit_reason": "ErrImagePull",
                "last_exit_code": None,
                "current_logs": f"Failed to pull image for {name} in {namespace} (private registry/auth required)",
                "previous_logs": ""
            }
        else:
            report = {
                "phase": "CrashLoopBackOff" if self.profile == "crashloop" else "Running",
                "restarts": 3 if self.profile == "crashloop" else 0,
                "last_exit_reason": "Error" if self.profile == "crashloop" else None,
                "last_exit_code": 1 if self.profile == "crashloop" else None,
                "current_logs": f"CRITICAL: {name} in {namespace} experiencing repeated failures; readiness probe failing; high error rate; immediate attention required",
                "previous_logs": "java.lang.NullPointerException at com.app.Main.init..."
            }
        return json.dumps(report, ensure_ascii=False, indent=2)

    def get_pod_events(self, name: str, namespace: str, limit: int = 20) -> str:
        """Return recent events for a Pod (reason + message) as deterministic mock data."""
        logger.debug(f"-----------Calling get_pod_events(name={name}, namespace={namespace}, limit={limit}, profile={self.profile})")
        if self.profile == "imagepullbackoff":
            events = [
                {
                    "type": "Warning",
                    "reason": "ErrImagePull",
                    "message": f"Failed to pull image for {name}",
                    "count": 3,
                },
                {
                    "type": "Warning",
                    "reason": "ImagePullBackOff",
                    "message": f"Back-off pulling image for {name}",
                    "count": 2,
                },
            ]
        else:
            events = [
                {
                    "type": "Warning",
                    "reason": "BackOff",
                    "message": f"Back-off restarting container for {name}",
                    "count": 5,
                },
                {
                    "type": "Normal",
                    "reason": "Pulled",
                    "message": f"Successfully pulled image for {name}",
                    "count": 1,
                },
            ]
        return json.dumps(events[-limit:], ensure_ascii=False, indent=2)

    def get_image_pull_events(self, name: str, namespace: str) -> str:
        """Filter Pod events to those likely related to image pull failures (mock)."""
        logger.debug(f"-----------Calling get_image_pull_events(name={name}, namespace={namespace}, profile={self.profile})")
        if self.profile == "imagepullbackoff":
            events = [
                {
                    "type": "Warning",
                    "reason": "ErrImagePull",
                    "message": f"Failed to pull image for {name}",
                    "count": 5,
                },
                {
                    "type": "Warning",
                    "reason": "ImagePullBackOff",
                    "message": f"Back-off pulling image for {name}",
                    "count": 3,
                },
            ]
        else:
            events = [
                {
                    "type": "Warning",
                    "reason": "ErrImagePull",
                    "message": f"Failed to pull image for {name}",
                    "count": 3,
                },
                {
                    "type": "Warning",
                    "reason": "ImagePullBackOff",
                    "message": f"Back-off pulling image for {name}",
                    "count": 2,
                },
            ]
        return json.dumps(events, ensure_ascii=False, indent=2)

    def get_service_account_details(self, name: str, namespace: str) -> str:
        """Return details of a ServiceAccount, including referenced imagePullSecrets (mock)."""
        logger.debug(f"-----------Calling get_service_account_details(name={name}, namespace={namespace}, profile={self.profile})")
        if self.profile == "imagepullbackoff":
            info = {
                "name": name,
                "secrets": [],
                "imagePullSecrets": [],
            }
        else:
            info = {
                "name": name,
                "secrets": ["default-token-abc123"],
                "imagePullSecrets": ["regcred"],
            }
        return json.dumps(info, ensure_ascii=False, indent=2)

    def get_secret_exists(self, name: str, namespace: str) -> str:
        """Return whether a Secret exists in the namespace (mock always True)."""
        logger.debug(f"-----------Calling get_secret_exists(name={name}, namespace={namespace}, profile={self.profile})")
        if self.profile == "imagepullbackoff":
            return json.dumps({"exists": False})
        return json.dumps({"exists": True})

    def get_workload_yaml(self, kind: str, name: str, namespace: str) -> str:
        """Return the full workload spec (as JSON string) for Deployment/StatefulSet (mock).

        Mirrors `get_workload_yaml` for resource review; structure matches Kubernetes objects
        commonly used in diagnostics (replicas, selectors, containers, resources, env).
        """
        logger.debug(f"-----------Calling get_workload_yaml(kind={kind}, name={name}, namespace={namespace}, profile={self.profile})")
        image = "mock.registry.local/mock:latest"
        if self.profile == "imagepullbackoff":
            image = "private.registry.local/protected/app:latest"
        obj = {
            "apiVersion": "apps/v1",
            "kind": kind,
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {
                        "containers": [
                            {
                                "name": name,
                                "image": image,
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                    "limits": {"cpu": "200m", "memory": "256Mi"},
                                },
                                "env": [{"name": "JAVA_OPTS", "value": "-Xmx128m"}],
                            }
                        ]
                    },
                },
            },
        }
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def get_pod_top_metrics(self, name: str, namespace: str) -> str:
        """Attempt to fetch live pod metrics (mock), shaped like metrics.k8s.io output."""
        logger.debug(f"-----------Calling get_pod_top_metrics(name={name}, namespace={namespace}, profile={self.profile})")
        if self.profile == "imagepullbackoff":
            metrics = {
                "metadata": {"name": name, "namespace": namespace},
                "timestamp": "2026-01-18T00:00:00Z",
                "containers": [
                    {"name": name, "usage": {"cpu": "0m", "memory": "0Mi"}}
                ],
            }
        else:
            metrics = {
                "metadata": {"name": name, "namespace": namespace},
                "timestamp": "2026-01-18T00:00:00Z",
                "containers": [
                    {"name": name, "usage": {"cpu": "50m", "memory": "180Mi"}}
                ],
            }
        return json.dumps(metrics, ensure_ascii=False, indent=2)

    def get_pod_scheduling_events(self, name: str, namespace: str, limit: int = 20) -> str:
        """Return events related to scheduling (e.g., FailedScheduling) for a Pod (mock)."""
        logger.debug(f"-----------Calling get_pod_scheduling_events(name={name}, namespace={namespace}, limit={limit}, profile={self.profile})")
        sched = [
            {
                "reason": "FailedScheduling",
                "message": f"0/3 nodes are available: 3 Insufficient memory for {name}.",
                "count": 4,
            }
        ]
        return json.dumps(sched[-limit:], ensure_ascii=False, indent=2)

    def get_nodes_overview(self) -> str:
        """List nodes with allocatable CPU/memory and taints for scheduling analysis (mock)."""
        logger.debug(f"-----------Calling get_nodes_overview(profile={self.profile})")
        nodes = [
            {
                "name": "node-1",
                "allocatable": {"cpu": "4", "memory": "8Gi"},
                "taints": [],
            },
            {
                "name": "node-2",
                "allocatable": {"cpu": "8", "memory": "16Gi"},
                "taints": [{"key": "dedicated", "value": "db", "effect": "NoSchedule"}],
            },
        ]
        return json.dumps(nodes, ensure_ascii=False, indent=2)

    def get_pvc_details(self, name: str, namespace: str) -> str:
        """Return status and bound PV for a PersistentVolumeClaim used by a Pod (mock)."""
        logger.debug(f"-----------Calling get_pvc_details(name={name}, namespace={namespace}, profile={self.profile})")
        info = {
            "name": name,
            "status": "Bound",
            "volumeName": "pv-123",
            "storageClass": "standard",
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": "10Gi"}},
        }
        return json.dumps(info, ensure_ascii=False, indent=2)

    def get_namespace_resource_quota(self, namespace: str) -> str:
        """Return ResourceQuota objects for a namespace to detect quota-related Pending states (mock)."""
        logger.debug(f"-----------Calling get_namespace_resource_quota(namespace={namespace}, profile={self.profile})")
        data = [
            {
                "metadata": {"name": "compute-quota", "namespace": namespace},
                "spec": {"hard": {"pods": "20", "limits.cpu": "10", "limits.memory": "20Gi"}},
                "status": {"used": {"pods": "5", "limits.cpu": "3", "limits.memory": "6Gi"}},
            }
        ]
        return json.dumps(data, ensure_ascii=False, indent=2)

    def get_namespace_limit_ranges(self, namespace: str) -> str:
        """Return LimitRange objects to understand default requests/limits constraints (mock)."""
        logger.debug(f"-----------Calling get_namespace_limit_ranges(namespace={namespace}, profile={self.profile})")
        data = [
            {
                "metadata": {"name": "default-limits", "namespace": namespace},
                "spec": {
                    "limits": [
                        {
                            "type": "Container",
                            "default": {"cpu": "500m", "memory": "512Mi"},
                            "defaultRequest": {"cpu": "250m", "memory": "256Mi"},
                        }
                    ]
                },
            }
        ]
        return json.dumps(data, ensure_ascii=False, indent=2)


def create_mock_tools(profile: Optional[str] = None) -> List[Callable]:
    """Return bound mock functions to inject as tools for agents."""
    mock = MockK8sDiag(profile=profile)
    return [
        mock.get_pod_diagnostics,
        mock.get_pod_events,
        mock.get_image_pull_events,
        mock.get_service_account_details,
        mock.get_secret_exists,
        mock.get_workload_yaml,
        mock.get_pod_top_metrics,
        mock.get_pod_scheduling_events,
        mock.get_nodes_overview,
        mock.get_pvc_details,
        mock.get_namespace_resource_quota,
        mock.get_namespace_limit_ranges,
    ]
