---
id: TSG-POD-DNS-002
title: Fix DNS Resolution Failures
issue_type: DNSResolutionFailure
component: pod
phase: solution
severity: high
k8s_version: ">=1.24"
keywords: ["fix", "dnsPolicy", "nameserver", "search", "resolve"]
---

## Summary
Remediation for DNS issues inside Pods.

## Remediation Options

### Fix 1: Correct DNS Policy/Config
- Action: Use appropriate `dnsPolicy`/`dnsConfig` to resolve services and external hosts.

### Fix 2: Allow Network Access
- Action: Ensure NetworkPolicy permits DNS egress and target hosts.

## Validation
1. DNS queries resolve successfully.
2. App logs no longer show DNS errors.
