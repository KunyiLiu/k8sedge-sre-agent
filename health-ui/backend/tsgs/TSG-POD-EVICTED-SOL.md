---
id: TSG-POD-EVICTED-002
title: Fix Pod Evictions
issue_type: Evicted
component: pod
phase: solution
severity: high
k8s_version: ">=1.24"
keywords: ["fix", "eviction", "resources", "qos", "priority"]
---

## Summary
Remediation for Pods evicted by node pressure.

## Remediation Options

### Fix 1: Adjust Resources
- Action: Lower memory/cpu usage or requests; optimize app; scale nodes.

### Fix 2: Improve QoS/Priority
- Action: Set reasonable requests/limits; consider PriorityClass.

## Validation
1. New Pod scheduling succeeds.
2. No further eviction events.
