---
id: TSG-POD-EVICTED-001
title: Pod Evicted Diagnosis
issue_type: Evicted
component: pod
phase: diagnosis
severity: high
k8s_version: ">=1.24"
signals:
  - pod_evicted
  - node_pressure
related_tsgs:
  - TSG-POD-OOM-001
  - TSG-POD-PENDING-001
keywords: ["Evicted", "NodeMemoryPressure", "NodeDiskPressure", "qos", "priority"]
---

## Summary
Diagnose Pods evicted due to node resource pressure.

## Symptoms
- Events show `Evicted` with `NodeMemoryPressure`/`NodeDiskPressure`

## Diagnostic Decision Tree

### Step 1: Inspect Eviction Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Check Node Resources
```python
get_nodes_overview()
```

### Step 3: Review Pod Resource Policy
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Confirm requests/limits and QoS class implications.

## Stop Condition
Diagnosis complete when eviction cause is identified.

## Escalation
Provide events and node overview to platform team.
