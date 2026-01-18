---
id: TSG-POD-IMAGEPULL-001
title: Pod ImagePullBackOff Diagnosis
issue_type: ImagePullBackOff
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - kube_pod_container_status_waiting_reason=ImagePullBackOff
  - kube_pod_container_status_waiting_reason=ErrImagePull
related_tsgs:
  - TSG-POD-CRASHLOOP-001
  - TSG-POD-IMAGEPULL-002
keywords: ["ImagePullBackOff", "ErrImagePull", "pull access denied", "manifest unknown", "401 Unauthorized", "DNS", "timeout"]
---

## Summary
Diagnose pods failing to start due to image pull errors from the container registry.

## Symptoms
- Pod Status: `ImagePullBackOff` or `ErrImagePull`
- Events: `Failed to pull image` messages
- Container never transitions to `Running`

## Diagnostic Decision Tree

### Step 1: Inspect Events for Registry Errors
```python
get_image_pull_events("<pod>", "<namespace>")
```
Look for:
- `pull access denied`, `requested access to the resource is denied`
- `manifest unknown`, `tag not found`
- `401 Unauthorized`, `403 Forbidden`
- DNS resolution failures or timeouts

### Step 2: Validate Image Reference
Confirm registry, repository, tag/digest are correct.
- Is the tag spelled correctly?
- Does the digest exist?
- Can you pull locally from the same registry?

### Step 3: Check `imagePullSecrets` and ServiceAccount
Verify authentication is configured and referenced.
```python
get_service_account_details("<service-account>", "<namespace>")
# If you know the secret name
get_secret_exists("<secret>", "<namespace>")
```
- Does the `imagePullSecrets` entry point to a valid secret?
- Is the secret in the same namespace?
- Is the service account used by the Pod configured with `imagePullSecrets`?

## Stop Condition
Diagnosis is complete when you identify one of:
- Incorrect image reference (registry/repo/tag/digest)
- Missing or invalid `imagePullSecrets` / denied access
- Registry/connectivity issues (network/DNS/proxy)

## Escalation
If unresolved:
- Collect the Pod events and image reference details
- Escalate to the platform/registry team with error excerpts
