---
id: TSG-POD-OOM-002
title: Fix Pod OOMKilled
issue_type: OOMKilled
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["increase memory limit", "heap", "resource requests", "limits", "restart"]
---

## Summary
Common remediation steps for pods killed by OOM.

## Remediation Options

### Fix 1: Increase Memory Limits/Requests
- Action: Raise `resources.limits.memory` and align `requests.memory` with expected workload.

### Fix 2: Tune Application Memory Settings
- Action: Adjust runtime memory parameters (e.g., JVM `-Xmx`, Node.js `--max-old-space-size`).

### Fix 3: Reduce Memory Pressure
- Action: Lower concurrency, shrink caches, or change data processing strategy.

## Validation
1. Apply the fix.
2. Monitor for absence of `OOMKilled` events.
3. Confirm restarts stop increasing and Pod remains `Running`.
