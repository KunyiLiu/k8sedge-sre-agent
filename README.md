# k8sedge-sre-agent
AI-Powered Kubernetes Troubleshooting Agent (MVP)  An AI-assisted SRE troubleshooting system that detects unhealthy Kubernetes workloads using Prometheus metrics and guides users through human-in-the-loop, ReAct-style diagnostics powered by Azure AI Foundry.

## Project Overview

K8sEdge SRE Agent is a project that demonstrates how AI agents can assist SREs in diagnosing Kubernetes issues.

The system:

* Continuously detects unhealthy pods and nodes via Prometheus metrics

* Presents issues in a lightweight UI dashboard

* Launches a step-by-step diagnostic workflow using AI agents

* Uses TSG playbooks (Troubleshooting Guides) as RAG context

* Keeps humans in control by requiring explicit approval before handing off the solution stage and unsure state

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
         Diagnostic Agent (ReAct + RAG + function calling)
                   │
         (Human approval each step)
                   │
                   ▼
            Root Cause Identified
                   │
                   ▼
            Solution Agent (RAG)
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

Stops before the ambiguous state and asks for user approval

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

## Highlights

- **Not another chatbot:** The system combines a deterministic health aggregator, ReAct agents with explicit function-calling, TSG-backed RAG, and human approval gates. It avoids open-ended chat, focuses on actionable diagnostics, and produces a clear and auditable trail of actions and observations.
- **Faster triage:** Converts Prometheus signals and cluster context into structured, step-by-step diagnostics that converge on a defensible root cause.
- **Common pod issues covered:** CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled, Liveness/Readiness failures, DNS resolution errors, volume mount issues, security policy problems, network policy blocks, init container failures, terminating/evicted states.
- **Human-in-control:** All agent actions require explicit approval; unsafe or unknown actions are denied. The system is designed for guided remediation, not autonomous changes.
- **Clear handoffs:** Produces fix suggestions and an optional escalation summary that can be shared with on-call or platform teams.

## Evaluation

- **MTTR (diagnostic):** Track median time from issue detection to confirmed root cause. Compare baselines (manual) vs with the agent enabled. Instrument timestamps at detection, agent start, key steps, and RCA confirmation.
- **Human deny rate:** Measure the percentage of agent-proposed steps that the user denies. High deny rates can indicate overreach or unclear actions; use this to tune allowed actions and prompt strategies.
- **Accuracy (RCA confirmation):** Percentage of diagnostic sessions where users confirm the agent’s proposed root cause as correct.
- **Coverage:** Share of detected issues that fall within supported pod troubleshooting scenarios and can run end-to-end diagnostics.

## Constraints

- **Scope of RAG:** The knowledge corpus and TSG references currently focus on pod-level troubleshooting. Node-level, service/ingress, storage classes, and advanced networking are limited or out of scope.
- **Diagnostic focus:** Agents primarily diagnose pod issues (containers, images, probes, DNS, mounts, policies). Non-pod resources are treated only insofar as they impact pods.
- **Metrics source:** Current unhealthy detection relies on Prometheus queries targeting pod-related states.

## TODO

1. **Enable solution agents to run fix functions:** Add gated, auditable fix function execution with strong safeguards, dry-run modes, and explicit approval requirements.
2. **Add allowed actions policy:** Define a whitelist of permitted functions/commands (e.g., `kubectl` read-only, specific patch operations), with per-environment configuration and clear UI surfacing.
3. **Trigger agents via Kubernetes CRD:** Replace the separate periodic Prometheus polling backend with a custom resource that directly triggers diagnostic/solution agents. Controllers can react to CR events, referencing Prometheus findings and cluster context.