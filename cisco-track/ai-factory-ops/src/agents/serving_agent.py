"""Serving replicas specialist agent."""

from __future__ import annotations

import time

from .base import AgentResult, AgentTrace
from ..data import get_con


def run_serving_agent(question: str, routed_reason: str) -> AgentResult:
    """Analyze serving replica health and queue pressure."""
    started = time.perf_counter()
    sql = """
    SELECT
        COUNT(*) AS rows_count,
        AVG(queued_requests) AS avg_queued_requests,
        MAX(queued_requests) AS max_queued_requests,
        AVG(desired_replicas - ready_replicas) AS avg_unready_replicas
    FROM scenario_serving_replicas
    """
    con = get_con()
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()

    rows_count = int(row[0] or 0)
    avg_queue = float(row[1] or 0.0)
    max_queue = float(row[2] or 0.0)
    avg_unready = float(row[3] or 0.0)

    confidence = 0.76 if rows_count else 0.5
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    evidence = [
        f"rows_count={rows_count}",
        f"avg_queued_requests={avg_queue:.2f}",
        f"max_queued_requests={max_queue:.2f}",
        f"avg_unready_replicas={avg_unready:.2f}",
    ]
    summary = (
        f"Serving layer shows average queue depth {avg_queue:.1f} and "
        f"peak queue {max_queue:.1f}, with {avg_unready:.2f} replicas unready on average."
    )
    trace = AgentTrace(
        agent_name="serving_agent",
        routed_reason=routed_reason,
        query_used=question,
        sql_executed=" ".join(sql.split()),
        rows_scanned=rows_count,
        elapsed_ms=elapsed_ms,
        notes=["Checked queue depth and ready-vs-desired replica gap."],
    )
    return AgentResult(
        agent_name="serving_agent",
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        trace=trace,
    )
