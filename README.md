# k8sedge-sre-agent
AI-Powered Kubernetes Troubleshooting Agent (MVP)  An AI-assisted SRE troubleshooting system that detects unhealthy Kubernetes workloads using Prometheus metrics and guides users through human-in-the-loop, ReAct-style diagnostics powered by Azure AI Foundry.

## Project Overview

K8sEdge SRE Agent is a side project that demonstrates how AI agents can assist SREs in diagnosing Kubernetes issues.

The system:

* Continuously detects unhealthy pods and nodes via Prometheus metrics

* Presents issues in a lightweight UI dashboard

* Launches a step-by-step diagnostic workflow using AI agents

* Uses TSG playbooks (Troubleshooting Guides) as RAG context

* Keeps humans in control by requiring explicit approval before each diagnostic action

* Produces a clear root cause analysis and recommended fix

* Optionally generates an escalation summary (email/download)

This project is designed as an MVP-quality demo that balances realism, clarity, and cost efficiency.

## Architecture
```
Prometheus ──► Health Aggregator (Code)
                   │
                   ▼
           Unhealthy Issue List (UI)
                   │
            User selects issue
                   │
                   ▼
         Diagnostic Agent (ReAct + RAG)
                   │
         (Human approval each step)
                   │
                   ▼
            Root Cause Identified
                   │
                   ▼
            Solution Agent
                   │
                   ▼
       Fix Suggestions / Escalation
```

## Core Components
1. Kubernetes Cluster (AKS)

Azure Kubernetes Service (AKS)

Single system node pool (cost-optimized)

Demo workloads intentionally deployed in broken states

2. Prometheus (Metrics Source)

kube-state-metrics

Used to detect:

CrashLoopBackOff

ImagePullBackOff

Pending pods

Queried directly via Prometheus HTTP API

3. Health Aggregator (Deterministic)

Pure code (no LLM)

Periodically queries Prometheus

Builds a list of current unhealthy issues

Provides structured context to AI agents

4. AI Agents (Azure AI Foundry)
Diagnostic Agent

ReAct-style loop (Think → Act → Observe)

Uses:

RAG over Kubernetes TSG playbooks

Skills (kubectl, Prometheus query, log fetch)

Stops before each action and asks for user approval

Terminates when root cause confidence is reached

Solution Agent

Receives full diagnostic context

Generates:

Fix recommendations

Next-step guidance

Optional escalation summary

5. UI (MVP)

Lists unhealthy pods/nodes

Allows user to start diagnostic flow

Displays step-by-step reasoning and actions

Human-in-the-loop confirmation