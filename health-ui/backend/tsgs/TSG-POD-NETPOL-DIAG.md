---
id: TSG-POD-NETPOL-001
title: NetworkPolicy Block Diagnosis
issue_type: NetworkPolicyBlocked
component: pod
phase: diagnosis
severity: high
k8s_version: ">=1.24"
signals:
  - network_timeouts
  - blocked_egress_or_ingress
related_tsgs:
  - TSG-POD-READINESS-001
  - TSG-POD-DNS-001
keywords: ["NetworkPolicy", "egress", "ingress", "deny", "timeout"]
---

## Summary
Diagnose connectivity issues caused by NetworkPolicy rules.

## Symptoms
- App logs: timeouts or connection refused

## Diagnostic Decision Tree

### Step 1: Inspect Logs/Status
```python
report = get_pod_diagnostics("<pod>", "<namespace>")
```

### Step 2: Review Workload Ports/Selectors
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Confirm expected ports and labels; compare with policy expectations.

## Stop Condition
Diagnosis complete when policy mismatches are identified.

## Escalation
Provide logs and workload details to network/platform teams.
