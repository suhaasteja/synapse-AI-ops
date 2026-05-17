"""Inference requests specialist agent."""

from __future__ import annotations

import time

from .base import AgentResult, AgentTrace
from ..data import get_con


def run_inference_agent(question: str, routed_reason: str) -> AgentResult:
    """Analyze request latency/SLO signals from scenario_requests."""
    started = time.perf_counter()
    sql = """
    SELECT
        COUNT(*) AS request_count,
        AVG(latency_ms) AS avg_latency_ms,
        approx_quantile(latency_ms, 0.95) AS p95_latency_ms,
        AVG(CASE WHEN slo_violation THEN 1.0 ELSE 0.0 END) AS slo_violation_rate,
        AVG(CASE WHEN status_code >= 500 THEN 1.0 ELSE 0.0 END) AS error_5xx_rate
    FROM scenario_requests
    """
    con = get_con()
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()

    request_count = int(row[0] or 0)
    avg_latency = float(row[1] or 0.0)
    p95_latency = float(row[2] or 0.0)
    slo_rate = float(row[3] or 0.0)
    error_5xx_rate = float(row[4] or 0.0)

    confidence = 0.65
    if request_count > 0:
        confidence = 0.8

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    evidence = [
        f"request_count={request_count}",
        f"avg_latency_ms={avg_latency:.2f}",
        f"p95_latency_ms={p95_latency:.2f}",
        f"slo_violation_rate={slo_rate:.4f}",
        f"error_5xx_rate={error_5xx_rate:.4f}",
    ]
    summary = (
        f"Inference traffic shows p95 latency of {p95_latency:.1f}ms with "
        f"{slo_rate:.2%} SLO violations across {request_count} requests."
    )
    trace = AgentTrace(
        agent_name="inference_agent",
        routed_reason=routed_reason,
        query_used=question,
        sql_executed=" ".join(sql.split()),
        rows_scanned=request_count,
        elapsed_ms=elapsed_ms,
        notes=["Focused on scenario_requests for latency and SLO behavior."],
    )
    return AgentResult(
        agent_name="inference_agent",
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        trace=trace,
    )
