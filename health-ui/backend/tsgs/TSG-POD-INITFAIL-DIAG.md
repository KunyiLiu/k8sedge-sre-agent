---
id: TSG-POD-INITFAIL-001
title: Init Container Failure Diagnosis
issue_type: InitContainerError
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - init_container_restart
  - backoff_failed_init_container
related_tsgs:
  - TSG-POD-IMAGEPULL-001
  - TSG-POD-MOUNT-001
keywords: ["initContainers", "bootstrap", "setup", "permissions", "image"]
---

## Summary
Diagnose failures in init containers that block Pod startup.

## Symptoms
- Events: `Back-off restarting failed init container`
- Pod never reaches `Running`

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Inspect Workload Spec
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Check `initContainers` `image`, `command`, `volumeMounts`, and required `permissions`.

## Stop Condition
Diagnosis complete when the failing init step or misconfiguration is identified.

## Escalation
Provide init container config and event excerpts to the application owner.
