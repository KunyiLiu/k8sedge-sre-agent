---
id: TSG-POD-TERMINATING-002
title: Fix Pod Stuck Terminating
issue_type: Terminating
component: pod
phase: solution
severity: high
k8s_version: ">=1.24"
keywords: ["fix", "finalizers", "preStop", "gracePeriod"]
---

## Summary
Remediation for Pods stuck in termination.

## Remediation Options

### Fix 1: Optimize preStop
- Action: Shorten or make preStop idempotent.

### Fix 2: Adjust Grace Period
- Action: Set `terminationGracePeriodSeconds` appropriate to app shutdown.

## Validation
1. Pod terminates within configured grace period.
2. No prolonged `Terminating` state.
