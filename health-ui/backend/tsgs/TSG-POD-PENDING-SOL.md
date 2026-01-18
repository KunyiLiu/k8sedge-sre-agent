---
id: TSG-POD-PENDING-002
title: Fix Pod Pending State
issue_type: Pending
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "scheduling", "resources", "tolerations", "affinity", "PVC", "quota"]
---

## Summary
Remediation steps to move a Pod from `Pending` to `Running` once the blocking cause is known.

## Remediation Options

### Fix 1: Adjust Resource Requests
- Action: Lower `resources.requests.cpu/memory` to fit cluster capacity or scale nodes.

### Fix 2: Update Constraints
- Action: Add required `tolerations` for node taints and relax `nodeSelector`/`affinity` if overly restrictive.

### Fix 3: Resolve PVC Issues
- Action: Ensure the PVC is `Bound` by using the correct `storageClass`, matching access modes, and sufficient size. Wait for PV provisioning if dynamic.

### Fix 4: Address Quota/Limit Policies
- Action: Update `ResourceQuota` (platform team) or adjust workload requests to comply. Review `LimitRange` defaults.

## Validation
1. Apply the change.
2. Monitor events until scheduling succeeds (absence of `FailedScheduling`).
3. Confirm Pod transitions from `Pending` to `Running`.
