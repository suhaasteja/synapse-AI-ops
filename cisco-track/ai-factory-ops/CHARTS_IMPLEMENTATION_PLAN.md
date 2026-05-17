# Charts Integration Plan for AI Factory Ops
Date: 2026-05-17
POC: AdaL
TL;DR: Add safe, explainable chart rendering to chat responses by introducing a chart planner layer (LLM-guided, schema-validated) that consumes deterministic agent outputs and renders in Next.js with fixed chart components first (line/bar/area), then expand.

## 1) Objectives

1. Improve answer comprehension with visual summaries tied to agent evidence.
2. Keep reliability high by separating:
   - data extraction (deterministic, DuckDB-backed agents),
   - chart selection (LLM),
   - rendering (strict frontend schema).
3. Preserve security by validating/sanitizing chart configs before rendering.

## 2) Current System Snapshot

- Backend:
  - LangGraph orchestrator
  - 5 specialist agents (inference, node, serving, alerts/logs, job queue)
  - LLM-first planner with salvage/fallback and diagnostics
- Frontend:
  - Next.js chat UI
  - Final answer + diagnostics accordion/traces
- Evaluation:
  - Offline corpus and runner available (`eval-agents`, `make eval`)

## 3) Proposed MVP Architecture (Phase 1)

### 3.1 Data Flow

1. User submits question.
2. Orchestrator routes to agents and collects `agent_results`.
3. New chart-planner step generates chart suggestions from:
   - selected agent outputs
   - compact sampled/aggregated chart-ready data payloads
4. Backend returns `chart_suggestions` in `/chat` response.
5. Frontend renders safe chart cards using fixed chart components.

### 3.2 Why this architecture

- Avoids fragile fully-freeform JSON chart rendering at first.
- Enables incremental rollout with predictable UI behavior.
- Makes debugging easy (chart suggestion + source agent + rationale).

## 4) MVP Scope (Implement Now)

### 4.1 Chart types
- line
- bar
- area

### 4.2 Candidate chart cards per response
- 1 to 3 suggested charts max.

### 4.3 Chart payload contract (backend -> frontend)
```json
{
  "title": "string",
  "chart_type": "line|bar|area",
  "x_key": "string",
  "y_key": "string",
  "series_key": "string|null",
  "data": [{"x": "...", "y": 0, "series": "..."}],
  "source_agents": ["inference_agent"],
  "why_this_chart": "string",
  "confidence": 0.0
}
```

### 4.4 Safety rules
- whitelist chart_type
- non-empty x/y keys
- cap points per chart (e.g., 100)
- reject unknown fields
- no executable callbacks in payload

## 5) Step-by-Step Execution Plan

## Step A — Backend chart schema + generator utilities
- Add Pydantic models for chart payload.
- Add helper to normalize agent evidence into chart-ready rows.
- Add deterministic fallback chart generator (if LLM chart planner fails).

Deliverables:
- `src/charts.py` (new)

## Step B — LLM chart planner
- Add `suggest_charts(...)` in `src/llm.py`.
- Prompt includes:
  - user question
  - planner mode
  - selected agents and findings
  - sample chart-ready data
- Return strict JSON array of chart suggestions.
- Validate output, fallback to deterministic charts if invalid.

Deliverables:
- `src/llm.py` updates

## Step C — Orchestrator integration
- Add new synthesis extension:
  - produce `chart_suggestions` from selected agent outputs.
- Include chart diagnostics in planner debug surface.

Deliverables:
- `src/orchestrator.py` updates

## Step D — API response extension
- Extend `/chat` response model with `chart_suggestions`.

Deliverables:
- `src/api.py` updates

## Step E — Frontend rendering (safe fixed components)
- Add chart section under Final Answer.
- Use fixed mapping from chart_type -> component.
- Show title, rationale, source agents.
- If no suggestions, hide section.

Deliverables:
- `web/src/app/page.tsx` updates
- Optional: `web/src/components/charts/*` new files (if needed)

## Step F — Evaluation extension
- Add eval checks for:
  - chart presence on correlation prompts
  - schema validity
  - point caps and safe types

Deliverables:
- `src/eval.py` updates
- `tests/eval_corpus.yaml` additions

## Step G — Verification
- run `python -m src.cli eval-agents`
- run `pytest -q`
- run frontend build

## 6) Risks + Mitigations

1. LLM returns invalid chart config
   - Mitigation: strict schema validation + deterministic fallback.
2. Overly dense chart data
   - Mitigation: aggregate and cap rows.
3. Redundant/low-value charts
   - Mitigation: rank and keep top 1-3 by confidence + diversity.
4. UI clutter
   - Mitigation: keep charts collapsed behind “Visual Insights” section if needed.

## 7) Out of Scope for MVP

- Fully freeform Vega-Lite spec execution from model output.
- Interactive linked brushing/filtering.
- Time-window UI controls (can be next milestone).

## 8) Success Criteria

1. Correlation prompts produce at least 1 meaningful chart suggestion.
2. No invalid chart payload reaches UI render.
3. Existing functionality unaffected (planner, traces, eval suite).
4. Build/tests pass.

## 9) Next Milestones (Post-MVP)

1. Expand chart types (stacked bar/scatter/heatmap).
2. Add scenario/time-window scoped charting.
3. Add downloadable PNG/CSV from chart cards.
4. Optional full JSON chart grammar mode with strict schema validator.
