---
id: TSG-POD-TERMINATING-001
title: Pod Stuck Terminating Diagnosis
issue_type: Terminating
component: pod
phase: diagnosis
severity: high
k8s_version: ">=1.24"
signals:
  - pod_stuck_terminating
  - finalizer_not_cleared
related_tsgs:
  - TSG-POD-READINESS-001
  - TSG-POD-LIVENESS-001
keywords: ["Terminating", "finalizers", "preStop", "gracePeriod"]
---

## Summary
Diagnose Pods stuck in `Terminating` due to long preStop, hanging connections, or finalizers.

## Symptoms
- Pod remains in `Terminating` beyond expected grace period

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Review Workload Hooks
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Check `preStop` hooks and `terminationGracePeriodSeconds`.

## Stop Condition
Diagnosis complete when a long-running hook or external finalizer is identified.

## Escalation
Provide events and workload hooks to application/platform team.
