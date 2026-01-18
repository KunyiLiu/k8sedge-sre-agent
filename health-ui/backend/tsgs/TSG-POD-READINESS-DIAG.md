---
id: TSG-POD-READINESS-001
title: Pod Readiness Probe Diagnosis
issue_type: ReadinessProbeFailed
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - readiness_probe_failed
  - pod_not_ready
related_tsgs:
  - TSG-POD-LIVENESS-001
  - TSG-POD-CRASHLOOP-001
keywords: ["readiness", "503", "timeout", "healthcheck", "start-up"]
---

## Summary
Diagnose Pods failing readiness checks that prevent them from becoming Ready.

## Symptoms
- Pod condition `Ready=False`
- Events show `Readiness probe failed`
- Service endpoints do not include the Pod

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```
Identify repeated readiness failures and messages.

### Step 2: Inspect Logs and Status
```python
report = get_pod_diagnostics("<pod>", "<namespace>")
```
Use `report["current_logs"]` and `report["previous_logs"]` to find startup/health errors.

### Step 3: Verify Probe Configuration
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Confirm probe `path/port/scheme`, `initialDelaySeconds`, `timeoutSeconds`, and `periodSeconds` align with app startup.

## Stop Condition
Diagnosis is complete when the failing healthcheck endpoint or timing mismatch is identified.

## Escalation
If unresolved, provide event excerpts, logs, and probe configuration to the application owner.
