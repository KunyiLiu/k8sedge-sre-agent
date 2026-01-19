---
id: TSG-POD-CONTAINERCREATING-002
title: Fix ContainerCreating Stuck Pods
issue_type: ContainerCreating
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "CNI", "sandbox", "runtime", "image pull"]
---

## Summary
Remediation steps for Pods stuck in `ContainerCreating`.

## Remediation Options

### Fix 1: Resolve Image Pull Issues
- Action: Correct image reference or configure `imagePullSecrets`.

### Fix 2: Address CNI/Runtime
- Action: Ensure CNI is healthy; restart node services or cordon/drain problematic nodes (platform team).

## Validation
1. Events no longer show `Failed create pod sandbox`.
2. Pod transitions past `ContainerCreating` to `Running`.
