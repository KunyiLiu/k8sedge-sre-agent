---
id: TSG-POD-DNS-001
title: DNS Resolution Failure Diagnosis
issue_type: DNSResolutionFailure
component: pod
phase: diagnosis
severity: high
k8s_version: ">=1.24"
signals:
  - dns_resolution_failed
  - connection_timeout
related_tsgs:
  - TSG-POD-NETPOL-001
  - TSG-POD-READINESS-001
keywords: ["DNS", "nameserver", "no such host", "timeout", "cluster-dns"]
---

## Summary
Diagnose DNS resolution failures within Pods.

## Symptoms
- App logs: `no such host`, `i/o timeout`

## Diagnostic Decision Tree

### Step 1: Inspect Logs
```python
report = get_pod_diagnostics("<pod>", "<namespace>")
```
Look for DNS error strings.

### Step 2: Review Workload Config
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Check DNS policy/settings and sidecars that may modify networking.

## Stop Condition
Diagnosis complete when misconfigured DNS or blocked access is identified.

## Escalation
Provide logs and config to platform/network teams.
