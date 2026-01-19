---
id: TSG-POD-LIVENESS-001
title: Pod Liveness Probe Diagnosis
issue_type: LivenessProbeFailed
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - liveness_probe_failed
  - pod_restart_count_high
related_tsgs:
  - TSG-POD-CRASHLOOP-001
  - TSG-POD-READINESS-001
keywords: ["liveness", "restart", "kill", "SIGTERM", "back-off"]
---

## Summary
Diagnose Pods where liveness probe failures cause repeated restarts.

## Symptoms
- Events show `Liveness probe failed`
- Restart count increases

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Inspect Logs and Status
```python
report = get_pod_diagnostics("<pod>", "<namespace>")
```
Use `report["previous_logs"]` for crash context; check `restarts`.

### Step 3: Verify Probe Configuration
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Confirm liveness endpoint correctness and timing.

## Stop Condition
Identified endpoint mismatch or timing that kills the app prematurely.

## Escalation
Provide logs and probe configuration to the application owner.
