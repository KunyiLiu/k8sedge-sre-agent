---
id: TSG-POD-LIVENESS-002
title: Fix Pod Liveness Probe Failures
issue_type: LivenessProbeFailed
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "initialDelay", "timeout", "endpoint", "restarts"]
---

## Summary
Remediation to prevent liveness probes from killing the application too early.

## Remediation Options

### Fix 1: Adjust Timing
- Action: Increase `initialDelaySeconds`/`failureThreshold` and ensure the app is ready before probing.

### Fix 2: Correct Endpoint
- Action: Ensure liveness endpoint is lightweight and always responsive when the app is healthy.

## Validation
1. Apply the change.
2. Confirm restarts stop climbing.
3. Pod remains `Running` without probe failures.
