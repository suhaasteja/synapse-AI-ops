# Synapse AI Ops Monorepo

This repository contains two core projects for the AI Factory hackathon workflow:

1. **`cisco-track/ai_factory_hackathon_student`** — Upstream challenge dataset and evaluation resources.
2. **`cisco-track/ai-factory-ops`** — The multi-agent AIOps web application (Next.js + FastAPI) built on top of those resources.

---

## 1) `ai_factory_hackathon_student` (Data + Benchmark Layer)

**Path:** `cisco-track/ai_factory_hackathon_student/`

This project provides the synthetic AI Factory benchmark environment:
- **Telemetry**: Multi-layer data across infrastructure, orchestration, and performance.
- **Scenarios**: 18 challenge windows with specific incident ground truth.
- **Knowledge**: Runbooks and data dictionaries used for agentic reasoning.
- **Assets**: DuckDB dataset (`ai_factory.duckdb`) and raw CSV files.

### Key docs
- `cisco-track/ai_factory_hackathon_student/README.md`
- `cisco-track/ai_factory_hackathon_student/data/public/data_dictionary.md`
- `cisco-track/ai_factory_hackathon_student/data/public/runbooks.md`

### Role in this monorepo
This is the **source-of-truth data + challenge definition** layer.  
Downstream systems consume it for analysis, recommendation logic, and validation.

---

## 2) `ai-factory-ops` (Application Layer)

**Path:** `cisco-track/ai-factory-ops/`

This is the implementation project: a multi-agent AIOps assistant that turns operational questions into explainable diagnosis.

### What it provides
- **Orchestration**: FastAPI + LangGraph backend for intelligent agent routing.
- **Agents**: 5 specialists (Inference, Node Metrics, Serving, Alerts/Logs, Job Queue).
- **Interface**: Next.js chat UI with diagnostics and trace transparency.
- **Visual insights**: charted outputs (line/bar/area/pie) from validated chart suggestions.
- **Validation**: offline evaluation harness (`eval-agents`) for routing/evidence quality checks.
- **Deployment**: Render backend + Vercel frontend path.

### Key docs
- `cisco-track/ai-factory-ops/README.md`
- `cisco-track/ai-factory-ops/PROJECT_OVERVIEW.md`
- `cisco-track/ai-factory-ops/DEPLOYMENT.md`
- `cisco-track/ai-factory-ops/DEMO.md`
- `cisco-track/ai-factory-ops/HACKATHON_SUBMISSION.md`

---

## How the two projects connect

- `ai-factory-ops` **consumes** data/runbook context from `ai_factory_hackathon_student`.
- `ai-factory-ops` **operationalizes** the static dataset into a live, interactive assistant.
- Together they provide a full loop of **data → analysis → recommendation → validation**.

---

## Suggested entry points

- If you want to understand the **dataset/challenge first**:  
  start with `cisco-track/ai_factory_hackathon_student/README.md`

- If you want to run the **web app**:  
  start with `cisco-track/ai-factory-ops/README.md`

- If you want to deploy the stack:  
  use `cisco-track/ai-factory-ops/DEPLOYMENT.md`
