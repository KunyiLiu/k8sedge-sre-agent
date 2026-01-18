---
id: TSG-POD-IMAGEPULL-002
title: Fix Pod ImagePullBackOff
issue_type: ImagePullBackOff
component: pod
phase: solution
severity: critical
k8s_version: ">=1.24"
keywords: ["fix", "imagePullSecrets", "registry", "tag", "digest", "auth"]
---

## Summary
Remediation steps for resolving image pull failures.

## Remediation Options

### Fix 1: Correct Image Reference
- Action: Update the Deployment/StatefulSet image to the correct registry/repo:tag or digest.
- Example:
```yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: myregistry.example.com/team/app:1.2.3
```

### Fix 2: Configure `imagePullSecrets`
- Action: Create a docker-registry secret and attach it.
- Commands:
```bash
kubectl create secret docker-registry regcred \
  --docker-server=myregistry.example.com \
  --docker-username=<user> \
  --docker-password=<token> \
  -n <namespace>
```
- Reference via ServiceAccount or Pod spec:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
imagePullSecrets:
  - name: regcred
```

### Fix 3: Address Network/Registry Access
- Action: Configure egress or proxy to allow registry access, or use a registry mirror.

## Validation
1. Apply the fix.
2. Monitor events until `Successfully pulled image` appears.
3. Confirm the Pod reaches `Running`.
