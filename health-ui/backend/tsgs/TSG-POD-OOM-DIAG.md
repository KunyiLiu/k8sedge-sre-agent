---
id: TSG-POD-OOM-001
title: Pod OOMKilled Diagnosis
issue_type: OOMKilled
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - container_last_state_terminated_reason=OOMKilled
  - container_last_state_terminated_exit_code=137
  - pod_restart_count_high
related_tsgs:
  - TSG-POD-CRASHLOOP-001
  - TSG-POD-OOM-002
keywords: ["OOMKilled", "exit code 137", "memory limit", "cgroup", "Killed"]
---

## Summary
Identify causes of pods being killed due to out-of-memory (OOM) conditions.

## Symptoms
- Pod restarts with `OOMKilled` in `lastState.terminated.reason`
- Exit code `137`
- Logs may show `OutOfMemoryError` (e.g., JVM) or process termination

## Diagnostic Decision Tree

### Step 1: Confirm OOMKilled
```python
get_pod_diagnostics("<pod>", "<namespace>")
```
Confirm `last_exit_reason` is `OOMKilled` and `last_exit_code` is `137`.

### Step 2: Inspect Resource Requests/Limits
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
- Are `resources.limits.memory` set too low?
- Are `requests.memory` and `limits.memory` aligned with actual usage?

### Step 3: Check Runtime Memory Usage
If available, review metrics:
```python
get_pod_top_metrics("<pod>", "<namespace>")
```
- Was memory usage near or above limit?
- Do logs indicate leaks or excessive caching?

## Stop Condition
Diagnosis is complete when:
- Memory limit is insufficient for workload, or
- App exhibits memory leak or misconfiguration (e.g., JVM `-Xmx` too high).

## Escalation
If unresolved:
- Capture heap/config details and workload pattern
- Escalate to application owner for memory profiling
