#!/usr/bin/env bash
set -e

echo "Deleting demo failure workloads..."
# Grab the root directory of the script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl delete -f "$ROOT_DIR/demo-apps/imagepull.yaml" -n demo-apps || true
kubectl delete -f "$ROOT_DIR/demo-apps/wrong-cmd-crashloop.yaml" -n demo-apps || true
kubectl delete -f "$ROOT_DIR/demo-apps/livenessprobe-crashloop.yaml" -n demo-apps || true
kubectl delete -f "$ROOT_DIR/demo-apps/oom.yaml" -n demo-apps || true
kubectl delete -f "$ROOT_DIR/demo-apps/pending.yaml" -n demo-apps || true

kubectl delete -f "$ROOT_DIR/demo-apps/demo-apps-namespace.yaml" || true

echo "Deleting SRE Agent workloads..."

kubectl delete namespace sreagent || true

echo "Teardown complete"
