---
id: TSG-POD-MOUNT-001
title: Volume Mount Error Diagnosis
issue_type: MountVolumeError
component: pod
phase: diagnosis
severity: critical
k8s_version: ">=1.24"
signals:
  - mount_volume_setup_failed
  - unable_to_mount_volumes
related_tsgs:
  - TSG-POD-PENDING-001
  - TSG-POD-INITFAIL-001
keywords: ["MountVolume", "PVC", "CSI", "accessModes", "storageClass"]
---

## Summary
Diagnose volume mount failures.

## Symptoms
- Events: `MountVolume.SetUp failed` or `Unable to mount volumes for pod`

## Diagnostic Decision Tree

### Step 1: Inspect Events
```python
get_pod_events("<pod>", "<namespace>")
```

### Step 2: Check PVC Details
```python
get_pvc_details("<claim>", "<namespace>")
```
Confirm `status=Bound`, storage class, size, and access modes.

### Step 3: Review Workload VolumeMounts
```python
get_workload_yaml("Deployment", "<deploy>", "<namespace>")
```
Verify `volumeMounts` paths and names match.

## Stop Condition
Diagnosis complete when storage or mount misconfiguration is identified.

## Escalation
Provide event excerpts, PVC details, and workload spec to platform/app teams.
