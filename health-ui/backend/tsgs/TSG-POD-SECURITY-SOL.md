---
id: TSG-POD-SECURITY-002
title: Fix Pod Security Admission Violations
issue_type: PodSecurityViolation
component: pod
phase: solution
severity: high
k8s_version: ">=1.24"
keywords: ["fix", "securityContext", "capabilities", "runAsUser", "PSA"]
---

## Summary
Remediation for Pod Security admission failures.

## Remediation Options

### Fix 1: Align securityContext
- Action: Remove forbidden capabilities; set `runAsUser`/`runAsNonRoot` per policy.

### Fix 2: Use Allowed Profiles
- Action: Adopt permitted seccomp/apparmor/SELinux profiles.

## Validation
1. Pod admitted without policy violations.
2. Pod reaches `Running`.
