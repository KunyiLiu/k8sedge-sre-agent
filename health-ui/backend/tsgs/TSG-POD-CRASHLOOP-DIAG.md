---
id: TSG-POD-CRASHLOOP-001
title: Pod CrashLoopBackOff Diagnosis
issue_type: CrashLoopBackOff
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - kube_pod_container_status_waiting_reason=CrashLoopBackOff
  - pod_restart_count_high
related_tsgs:
  - TSG-POD-IMAGEPULL-001
  - TSG-POD-OOM-001
keywords: ["exit code 1", "exit code 137", "exit code 139", "restarts", "back-off", "SIGTERM", "SIGSEGV"]
---

## Summary
This TSG helps identify the root cause of a pod repeatedly crashing after it has been scheduled and started.

## Symptoms
- Pod status shows CrashLoopBackOff
- Container restarts repeatedly
- `kubectl get pods` shows high restart count

## Probable Causes
- Application crash due to config or missing environment variables
- Incorrect container command or entrypoint
- Dependency service unavailable
- Liveness probe misconfiguration

## Diagnostic Decision Tree

Before starting, capture a single diagnostic report and reuse it across steps:
```python
report = get_pod_diagnostics("<pod>", "<namespace>")
```

### Step 1: Check Exit Codes
Use `report["last_exit_code"]` and `report["last_exit_reason"]` to branch the investigation.
- Exit Code 137: OOMKilled (Out of Memory). See TSG-POD-OOM.
- Exit Code 139: Segmentation fault (SIGSEGV). Likely an application bug or binary incompatibility.
- Exit Code 1 or 255: Generic application crash. Proceed to Step 2.

### Step 2: Retrieve Previous Logs
Because the container is crashing, current logs may be empty. Inspect `report["previous_logs"]`.
Look for: "Connection refused", "File not found", "Access denied", or common stack traces.

### Step 3: Inspect Environment and Config
Verify runtime configuration from the controller spec (Deployment/StatefulSet) and referenced resources.
```python
# If managed by a Deployment
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
- Are all `env` variables populated?
- Are referenced `ConfigMaps` or `Secrets` present?

## Stop Condition
Root cause is identified when:
- Logs clearly show application failure reason
- Pod spec misconfiguration is confirmed

## Escalation
If root cause cannot be determined:
- Collect logs and pod spec
- Escalate to application owner
