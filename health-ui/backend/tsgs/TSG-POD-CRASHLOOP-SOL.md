---
id: TSG-POD-CRASHLOOP-002
title: Fix Pod CrashLoopBackOff
issue_type: CrashLoopBackOff
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "remediation", "patch", "restart", "update limits"]
---

## Summary
Provides remediation steps once the root cause of a CrashLoopBackOff is known.

## Remediation Options

### Fix 1: Missing Configuration
If logs indicated missing Environment Variables or ConfigMaps:
- Action: Update the Deployment/StatefulSet manifest to include the missing keys.
- Tool: `patch_deployment`

### Fix 2: Resource Constraints (OOM)
If the exit code was 137 and usage was at 100% of limits:
- Action: Increase `resources.limits.memory` in the pod spec.

### Fix 3: Liveness Probe Mismatch
If the pod crashes because the liveness probe kills it before it finishes starting:
- Action: Increase `initialDelaySeconds` in the `livenessProbe` configuration.

## Validation
1. Apply the fix.
2. Monitor the pod status for 120 seconds.
3. Confirm status is `Running` and `Restarts` count has stopped incrementing.
