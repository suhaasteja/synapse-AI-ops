# AI Factory Ops Web Demo Script (90 seconds)

## Goal

Show the multi-agent web experience end-to-end: ask a production-style question, inspect orchestrated findings, and review visual insights + traces.

## Script

### 1) Setup backend + frontend (20s)

```bash
cd ai-factory-ops
pip install -r requirements.txt
python -m uvicorn src.api:app --reload
```

In a second terminal:

```bash
cd ai-factory-ops/web
npm install
npm run dev
```

Open `http://localhost:3000`.

Callout:
- Backend serves `/chat` and orchestrates specialist agents.
- Frontend renders final answer, charts, and diagnostics.

### 2) Run a correlation prompt in chat (25s)

Use a prompt like:

> Correlate high latency and SLO violations with node temperature, serving queue depth, critical alerts, and failed jobs. Rank likely root causes.

Callout:
- Planner selects relevant agents automatically.
- Response includes executive summary + evidence-backed findings.

### 3) Show Visual Insights (25s)

In the same response:
- Highlight chart cards (line/bar/area/pie depending on data).
- Explain confidence badges and source agents.
- Mention chart suggestions are schema-validated with safe fallback behavior.

### 4) Show Diagnostics transparency (15s)

Expand **Diagnostics (Planner, Agent Summaries, Traces)**:
- Show routing plan and selected agents.
- Show one trace with SQL executed, rows scanned, and elapsed time.

### 5) Closing line (5s)

“AI Factory Ops gives an explainable, multi-agent operational diagnosis in one chat flow, with evidence traces and visual insights for fast triage.”
