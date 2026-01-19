---
id: TSG-POD-PENDING-001
title: Pod Pending Diagnosis
issue_type: Pending
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - pod_status_phase=Pending
  - pod_scheduling_failed
related_tsgs:
  - TSG-POD-IMAGEPULL-001
  - TSG-POD-CRASHLOOP-001
keywords: ["FailedScheduling", "0/ N nodes", "Insufficient cpu", "Insufficient memory", "taint", "toleration", "affinity", "nodeSelector", "PVC pending", "quota"]
---

## Summary
Diagnose pods stuck in `Pending` due to scheduling constraints, resource shortages, or storage/quota issues.

## Symptoms
- Pod phase remains `Pending`
- Events show `FailedScheduling` with reasons like `Insufficient cpu/memory`, taints, or constraints
- Container does not start (`ContainerCreating` does not appear)

## Diagnostic Decision Tree

Before starting, capture events and workload spec:
```python
sched = get_pod_scheduling_events("<pod>", "<namespace>")
workload = get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```

### Step 1: Inspect Scheduling Events
Use `sched` to identify primary reason:
- `0/ N nodes are available`: resource or constraint mismatch
- `Insufficient cpu/memory`: capacity issue
- `node(s) had taint ...`: missing tolerations
- `node(s) didn't match Pod's node affinity`: affinity mismatch

### Step 2: Check Requests vs Cluster Capacity
Review requests/limits in `workload` and current node capacity/taints:
```python
nodes = get_nodes_overview()
```
- Are `requests.cpu`/`requests.memory` too high for available nodes?
- Do node taints require specific tolerations?

### Step 3: Validate Constraints
From the workload spec:
- `nodeSelector`/`affinity` overly restrictive?
- Missing `tolerations` for tainted nodes?

### Step 4: Storage and Quota
If the Pod uses PVC or quota-bound resources:
```python
pvc = get_pvc_details("<claim>", "<namespace>")
rq = get_namespace_resource_quota("<namespace>")
lr = get_namespace_limit_ranges("<namespace>")
```
- PVC status is `Bound`?
- ResourceQuota blocking creation?
- LimitRange forcing requests above capacity?

## Stop Condition
Diagnosis is complete when you identify one of:
- Capacity shortfall (requests > allocatable)
- Constraint mismatch (taints/tolerations, affinity, nodeSelector)
- Storage pending (PVC not bound)
- Namespace policy limits (ResourceQuota/LimitRange)

## Escalation
If unresolved:
- Provide scheduling events, workload spec, and node overview
- Escalate to platform/SRE for capacity or policy adjustments
