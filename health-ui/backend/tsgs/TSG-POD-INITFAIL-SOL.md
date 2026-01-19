---
id: TSG-POD-INITFAIL-002
title: Fix Init Container Failures
issue_type: InitContainerError
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "initContainers", "command", "image", "volumeMounts"]
---

## Summary
Remediation for init container issues blocking Pod startup.

## Remediation Options

### Fix 1: Correct Init Image/Command
- Action: Use valid image and command; ensure dependencies are present.

### Fix 2: Fix Volume Access
- Action: Ensure volumes mount to expected paths with correct permissions.

## Validation
1. Apply fix.
2. Events no longer show init retries.
3. Pod progresses to `Running`.
