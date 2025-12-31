#!/usr/bin/env bash
set -e

echo "Creating namespaces..."
# Grab the root directory of the script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl apply -f "$ROOT_DIR/demo-apps/demo-apps-namespace.yaml"
# Apply sreagent namespace
kubectl apply -f "$ROOT_DIR/health-ui/k8s/sreagent-namespace.yaml"

echo "Deploying demo failure workloads..."

read -p "Deploy imagepull.yaml? (y/n): " resp
if [[ $resp == "y" ]]; then
  kubectl apply -f "$ROOT_DIR/demo-apps/imagepull.yaml" -n demo-apps
fi

read -p "Deploy wrong-cmd-crashloop.yaml? (y/n): " resp
if [[ $resp == "y" ]]; then
  kubectl apply -f "$ROOT_DIR/demo-apps/wrong-cmd-crashloop.yaml" -n demo-apps
fi

read -p "Deploy livenessprobe-crashloop.yaml? (y/n): " resp
if [[ $resp == "y" ]]; then
  kubectl apply -f "$ROOT_DIR/demo-apps/livenessprobe-crashloop.yaml" -n demo-apps
fi

read -p "Deploy oom.yaml? (y/n): " resp
if [[ $resp == "y" ]]; then
  kubectl apply -f "$ROOT_DIR/demo-apps/oom.yaml" -n demo-apps
fi

read -p "Deploy pending.yaml? (y/n): " resp
if [[ $resp == "y" ]]; then
  kubectl apply -f "$ROOT_DIR/demo-apps/pending.yaml" -n demo-apps
fi

echo "Deploying SRE Agent workloads..."

# Deploy backend
kubectl apply -f "$ROOT_DIR/health-ui/k8s/sreagent-backend.yaml"

# Wait for backend deployment to be ready
kubectl rollout status deployment/sreagent-backend -n sreagent --timeout=60s

# Deploy frontend
kubectl apply -f "$ROOT_DIR/health-ui/k8s/sreagent-frontend.yaml"

echo "Setup complete"
