import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.skills.k8s_diag import get_pod_diagnostics, get_pod_events, get_nodes_overview

def test_get_pod_diagnostics():
    # Replace with a real pod name and namespace from your cluster
    pod_name = "crashloop-7b88fd64b6-tcfzj"
    namespace = "demo-apps"
    print("Pod Diagnostics:")
    print(get_pod_diagnostics(pod_name, namespace))

def test_get_pod_events():
    pod_name = "crashloop-7b88fd64b6-tcfzj"
    namespace = "demo-apps"
    print("Pod Events:")
    print(get_pod_events(pod_name, namespace))

def test_get_workload_yaml():
    from app.skills.k8s_diag import get_workload_yaml
    kind = "Pod"
    name = "crashloop-7b88fd64b6-tcfzj"
    namespace = "demo-apps"
    print("Workload YAML:")
    print(get_workload_yaml(kind, name, namespace))

def test_get_nodes_overview():
    print("Nodes Overview:")
    print(get_nodes_overview())

if __name__ == "__main__":
    test_get_pod_diagnostics()
    test_get_pod_events()
    test_get_workload_yaml()
    test_get_nodes_overview()
