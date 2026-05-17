# AI Factory Ops Demo Script (90 seconds)

## Goal

Show deterministic recommendation generation, validation, and evidence-first UI quickly.

## Script

### 1) Setup (15s)

```bash
cd ai-factory-ops
pip install -r requirements.txt
```

### 2) Batch recommendations + validation (20s)

```bash
make recommend-all
make validate-all
```

Callout:
- Mention that all scenarios are produced in `output/*.json` and consolidated in `output/all.json`.
- Mention validation passes using the official hook.

### 3) One scenario drill-down in CLI (20s)

```bash
python -m src.cli extract --scenario-id perf-001
python -m src.cli propose --scenario-id perf-001
python -m src.cli runbook --scenario-id fail-001
```

Callout:
- Explain feature extraction → rules → candidate ranking.
- Show rule trail and supporting signals.

### 4) Launch UI (35s)

```bash
python -m src.cli ui
```

In browser:
1. Select `perf-001` and show recommendation card + evidence charts.
2. Select `fail-001` and expand runbook excerpt.
3. Use **What-if overrides** (e.g., lower p99 or checkpoint timeout) and show recommendation updates + change message.

## Closing line

“Decisions are deterministic and auditable; LLM is optional and only used for explanation quality.”
