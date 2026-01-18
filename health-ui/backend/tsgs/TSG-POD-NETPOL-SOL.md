---
id: TSG-POD-NETPOL-002
title: Fix NetworkPolicy Blocks
issue_type: NetworkPolicyBlocked
component: pod
phase: solution
severity: high
k8s_version: ">=1.24"
keywords: ["fix", "egress", "ingress", "allow", "selector"]
---

## Summary
Remediation for NetworkPolicy-related connectivity issues.

## Remediation Options

### Fix 1: Add Allow Rules
- Action: Permit required ingress/egress to services/namespaces.

### Fix 2: Align Labels and Ports
- Action: Ensure workload labels/ports match policy selectors.

## Validation
1. Connectivity works without timeouts.
2. Logs show successful communication.
