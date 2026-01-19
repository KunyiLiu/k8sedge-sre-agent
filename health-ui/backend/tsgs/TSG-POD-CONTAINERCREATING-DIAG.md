---
id: TSG-POD-CONTAINERCREATING-001
title: ContainerCreating Diagnosis
issue_type: ContainerCreating
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - pod_status_phase=Pending
  - failed_create_pod_sandbox
related_tsgs:
  - TSG-POD-IMAGEPULL-001
  - TSG-POD-PENDING-001
keywords: ["ContainerCreating", "sandbox", "CNI", "runtime", "CRI"]
---

## Summary
Diagnose Pods stuck in `ContainerCreating` due to runtime or CNI issues.

## Symptoms
- Events show `Failed create pod sandbox` or CNI plugin errors

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Check Image Pull
```python
get_image_pull_events("<pod>", "<namespace>")
```
Confirm no `ErrImagePull`/`ImagePullBackOff`.

### Step 3: Node Conditions Overview
```python
get_nodes_overview()
```
Check taints and allocatable resources; ensure node readiness.

## Stop Condition
Diagnosis complete when sandbox/CNI/runtime error is identified or ruled out.

## Escalation
Provide event excerpts and node overview to platform/SRE.
