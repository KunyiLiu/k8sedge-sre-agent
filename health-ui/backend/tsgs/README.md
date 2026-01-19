# TSGs Indexing & Chunking Guidance

This folder contains Troubleshooting Guides (TSGs) for Kubernetes health issues. Each file includes YAML front-matter followed by markdown sections. To enable fast, accurate retrieval:

- Chunk by semantic section:
  - Chunk 1: Summary + Symptoms
  - Chunk 2: Probable Causes (if present)
  - Chunk 3: Diagnostic Decision Tree (early steps)
  - Chunk 4: Diagnostic Decision Tree (later steps)
  - Chunk 5: Stop Condition + Escalation
  - For solution TSGs, chunk by Fix Options and Validation.

- Shared metadata (from YAML front-matter):
  - issue_type: e.g., CrashLoopBackOff, ImagePullBackOff, OOMKilled, Pending
  - component: e.g., pod
  - phase: diagnosis | solution
  - severity: critical | high | warning
  - tsg_id: value from `id`
  - signals: list of signal strings
  - keywords: list of keywords aiding retrieval (optional)
  - related_tsgs: list of IDs to link navigation across issues

- Function-based steps:
  - Diagnostic blocks reference skills in `backend/skills/k8s_diag.py` (e.g., `get_pod_diagnostics`, `get_pod_events`). Index code fences as text, not executable code.

- File naming:
  - Use the pattern: TSG-<RESOURCE>-<ISSUE>-<NNN>.md with `phase` indicated in the content front-matter.

- Validation:
  - Prefer concrete, observable stop/validation conditions (Pod state transitions, event disappearance, restart stabilization).

This guidance ensures TSGs are consistently chunked and retrievable with shared metadata across diagnosis and solution phases.
