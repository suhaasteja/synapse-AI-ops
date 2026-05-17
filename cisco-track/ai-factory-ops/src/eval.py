"""Evaluation runner for multi-agent orchestration prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

from .charts import normalize_chart_suggestions
from .orchestrator import run_orchestrated_query


@dataclass
class EvalCase:
    """One evaluation case for orchestrator behavior."""

    case_id: str
    prompt: str
    expected_agents: list[str]
    allow_extra_agents: bool
    min_agent_count: int
    max_agent_count: int | None
    expected_planner_mode: str | None
    required_evidence_patterns: list[str]
    min_chart_count: int


def _load_eval_cases(corpus_path: Path) -> list[EvalCase]:
    """Load evaluation cases from YAML corpus."""
    raw = yaml.safe_load(corpus_path.read_text(encoding="utf-8"))
    rows = raw.get("test_cases", []) if isinstance(raw, dict) else []
    cases: list[EvalCase] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("id", "")).strip()
        prompt = str(row.get("prompt", "")).strip()
        if not case_id or not prompt:
            continue
        expected_agents = [str(item).strip() for item in row.get("expected_agents", []) if str(item).strip()]
        case = EvalCase(
            case_id=case_id,
            prompt=prompt,
            expected_agents=expected_agents,
            allow_extra_agents=bool(row.get("allow_extra_agents", True)),
            min_agent_count=int(row.get("min_agent_count", 1)),
            max_agent_count=int(row["max_agent_count"]) if row.get("max_agent_count") is not None else None,
            expected_planner_mode=str(row["expected_planner_mode"]).strip() if row.get("expected_planner_mode") else None,
            required_evidence_patterns=[
                str(item).strip().lower()
                for item in row.get("required_evidence_patterns", [])
                if str(item).strip()
            ],
            min_chart_count=int(row.get("min_chart_count", 0)),
        )
        cases.append(case)
    return cases


def _case_result(case: EvalCase) -> dict[str, Any]:
    """Run one evaluation case and compute pass/fail fields."""
    response = run_orchestrated_query(case.prompt)
    plan = response.get("plan", [])
    actual_agents = [str(step.get("agent_name", "")).strip() for step in plan if str(step.get("agent_name", "")).strip()]
    actual_set = set(actual_agents)
    expected_set = set(case.expected_agents)

    missing = sorted(expected_set - actual_set)
    extras = sorted(actual_set - expected_set) if expected_set else []

    mode = str(response.get("planner_mode", "unknown"))
    mode_ok = True if case.expected_planner_mode is None else mode == case.expected_planner_mode

    count_ok = len(actual_agents) >= case.min_agent_count
    if case.max_agent_count is not None:
        count_ok = count_ok and len(actual_agents) <= case.max_agent_count

    routing_ok = not missing and (case.allow_extra_agents or not extras)

    answer_text = str(response.get("answer", "")).lower()
    missing_patterns = [
        pattern for pattern in case.required_evidence_patterns if not re.search(re.escape(pattern), answer_text)
    ]
    evidence_ok = not missing_patterns

    raw_charts = response.get("chart_suggestions", [])
    raw_chart_items = [item for item in raw_charts if isinstance(item, dict)] if isinstance(raw_charts, list) else []
    valid_charts = normalize_chart_suggestions(raw_chart_items, max_points=100)
    chart_count = len(valid_charts)
    charts_ok = chart_count >= case.min_chart_count

    expected_count = len(case.expected_agents) if case.expected_agents else max(1, len(actual_agents))
    overlap = len(actual_set & expected_set) if expected_set else len(actual_set)
    route_score = overlap / expected_count if expected_count else 1.0
    mode_score = 1.0 if mode_ok else 0.0
    evidence_score = (
        1.0
        if not case.required_evidence_patterns
        else (len(case.required_evidence_patterns) - len(missing_patterns)) / len(case.required_evidence_patterns)
    )
    chart_score = 1.0 if case.min_chart_count <= 0 else min(chart_count / case.min_chart_count, 1.0)
    overall_score = round((route_score + mode_score + evidence_score + chart_score) / 4.0, 3)

    passed = routing_ok and mode_ok and count_ok and evidence_ok and charts_ok

    notes: list[str] = []
    if missing:
        notes.append(f"missing={','.join(missing)}")
    if extras and not case.allow_extra_agents:
        notes.append(f"extras={','.join(extras)}")
    if not mode_ok:
        notes.append(f"mode={mode}, expected={case.expected_planner_mode}")
    if not count_ok:
        notes.append(f"count={len(actual_agents)}")
    if missing_patterns:
        notes.append(f"evidence_missing={','.join(missing_patterns)}")
    if not charts_ok:
        notes.append(f"charts={chart_count}, min={case.min_chart_count}")
    if not notes:
        notes.append("ok")

    return {
        "id": case.case_id,
        "pass": passed,
        "mode": mode,
        "agent_count": len(actual_agents),
        "chart_count": chart_count,
        "agents": actual_agents,
        "missing": missing,
        "score": overall_score,
        "notes": "; ".join(notes),
    }


def run_eval_suite(
    corpus_path: Path,
    only_case_id: str | None = None,
    fail_fast: bool = False,
    console: Console | None = None,
) -> int:
    """Run evaluation suite and print rich summary."""
    out = console or Console()
    if not corpus_path.exists():
        out.print(f"[red]Eval corpus not found:[/red] {corpus_path}")
        return 2

    cases = _load_eval_cases(corpus_path)
    if only_case_id:
        cases = [case for case in cases if case.case_id == only_case_id]
    if not cases:
        out.print("[yellow]No evaluation cases selected.[/yellow]")
        return 1

    detail = Table(title="Orchestrator Evaluation")
    detail.add_column("id")
    detail.add_column("pass")
    detail.add_column("mode")
    detail.add_column("agents")
    detail.add_column("charts")
    detail.add_column("score")
    detail.add_column("notes")

    passed = 0
    for case in cases:
        result = _case_result(case)
        ok = bool(result["pass"])
        if ok:
            passed += 1
        detail.add_row(
            result["id"],
            "[green]PASS[/green]" if ok else "[red]FAIL[/red]",
            str(result["mode"]),
            str(result["agent_count"]),
            str(result.get("chart_count", 0)),
            f"{float(result['score']):.3f}",
            str(result["notes"]),
        )
        if fail_fast and not ok:
            break

    out.print(detail)

    total = len(cases)
    summary = Table(title="Evaluation Summary")
    summary.add_column("total")
    summary.add_column("passed")
    summary.add_column("failed")
    summary.add_column("pass_rate")
    summary.add_row(
        str(total),
        str(passed),
        str(total - passed),
        f"{(passed / total) * 100:.1f}%",
    )
    out.print(summary)

    return 0 if passed == total else 1
