---
id: TSG-POD-SECURITY-001
title: Pod Security Admission Diagnosis
issue_type: PodSecurityViolation
component: pod
phase: diagnosis
severity: high
k8s_version: ">=1.24"
signals:
  - pod_security_admission_denied
  - forbidden_security_context
related_tsgs:
  - TSG-POD-PENDING-001
  - TSG-POD-TERMINATING-001
keywords: ["PSA", "securityContext", "runAsUser", "capabilities", "SELinux"]
---

## Summary
Diagnose Pod admission failures due to Pod Security policies.

## Symptoms
- Events show violations (forbidden by PodSecurity)

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Review Workload Security Context
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Check `securityContext` (runAsUser, capabilities, privileged).

## Stop Condition
Diagnosis complete when violating field(s) are identified.

## Escalation
Provide events and securityContext to platform/security teams.
