---
id: TSG-POD-READINESS-002
title: Fix Pod Readiness Probe Failures
issue_type: ReadinessProbeFailed
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "healthcheck", "timeout", "initialDelay", "port", "path"]
---

## Summary
Remediation steps to make readiness checks succeed.

## Remediation Options

### Fix 1: Correct Endpoint
- Action: Ensure the readiness endpoint exists and returns 200 when the app is ready.

### Fix 2: Adjust Timing
- Action: Increase `initialDelaySeconds`/`timeoutSeconds` to match actual startup time.

### Fix 3: Align Port/Path/Scheme
- Action: Match probe `port`, `path`, and `scheme` to the application.

## Validation
1. Apply the probe change.
2. Confirm events no longer show `Readiness probe failed`.
3. Pod transitions to `Ready` and joins Service endpoints.
