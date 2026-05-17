# AI Factory Ops — Project Overview

## What this project does

**AI Factory Ops** is a multi-agent AIOps web application that helps teams diagnose production issues faster using operational data and transparent reasoning.

A user asks a natural-language question (for example: *“Why are latency and critical alerts high?”*), and the system:

1. Routes the question to relevant specialist agents,
2. Runs targeted analysis over infrastructure and service telemetry,
3. Produces an executive summary and evidence-backed findings,
4. Shows visual insights (line/bar/area/pie),
5. Exposes traces so operators can inspect exactly what was queried and why.

In short, it turns noisy ops data into a clear, explainable diagnosis workflow.

---

## What problem it solves

Modern AI/ML systems fail across multiple layers at once (inference latency, GPU pressure, serving readiness, alert storms, job queue backlog).  
Most tools show fragmented metrics, forcing engineers to manually correlate signals under time pressure.

This project solves that by providing:

- **Cross-system correlation in one query**  
  Instead of checking five dashboards, users ask one question and get a synthesized analysis.

- **Multi-agent specialization**  
  Separate agents focus on inference, node metrics, serving, alerts/logs, and job queues.

- **Explainable operations decisions**  
  Every answer is traceable to concrete evidence and agent outputs.

- **Fast triage with visuals**  
  Auto-generated charts make patterns and bottlenecks easier to spot.

- **Safer LLM usage**  
  Structured outputs, validation, and fallbacks reduce brittle behavior.

---

## How it works (high level)

### 1) Web UI (Next.js)
- Chat interface for operator questions
- Final answer + visual insights + diagnostics accordion
- Trace drill-down per agent (query, rows scanned, elapsed time)

### 2) API + Orchestrator (FastAPI + LangGraph)
- Receives user question via `POST /chat`
- Builds routing plan using LLM-first orchestration with fallback logic
- Executes selected specialist agents
- Synthesizes answer and chart suggestions

### 3) Specialist agent layer
- `inference_agent` — latency, throughput, SLO violations
- `node_metrics_agent` — GPU utilization, memory, temperature, node health
- `serving_agent` — replica readiness and queue depth
- `alerts_logs_agent` — incident and alert evidence
- `job_queue_agent` — queued/failed jobs and backlog pressure

### 4) Visualization layer
- Suggests chart specs (`line`, `bar`, `area`, `pie`) from agent evidence
- Validates/sanitizes chart payloads
- Falls back to deterministic chart generation when needed

---

## Why this approach is useful

- **Operationally practical**: built for incident-style questions, not just static reports
- **Composable**: adding new agents scales domain coverage
- **Transparent**: diagnostics and traces build trust with engineering teams
- **Production-minded**: schema validation + fallback paths improve reliability

---

## Example use cases

- Correlate latency spikes with node thermal pressure and queue buildup
- Investigate whether critical alerts align with failed jobs
- Prioritize likely root causes across serving, infra, and inference signals
- Generate an executive incident summary for engineering leadership

---

## Outcome

AI Factory Ops helps teams move from **“What’s wrong?”** to **“What should we investigate first?”** with less manual correlation, clearer evidence, and faster incident response.
