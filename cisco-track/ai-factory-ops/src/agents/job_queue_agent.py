"""Job queue specialist agent."""

from __future__ import annotations

import time

from .base import AgentResult, AgentTrace
from ..data import get_con


def run_job_queue_agent(question: str, routed_reason: str) -> AgentResult:
    """Analyze queue pressure, wait times, and job failures."""
    started = time.perf_counter()
    sql = """
    SELECT
        COUNT(*) AS total_jobs,
        COUNT(*) FILTER (WHERE status = 'queued') AS queued_jobs,
        COUNT(*) FILTER (WHERE status = 'failed') AS failed_jobs,
        AVG(queue_wait_min) AS avg_queue_wait_min,
        MAX(queue_wait_min) AS max_queue_wait_min
    FROM scenario_job_queue
    """
    con = get_con()
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()

    total_jobs = int(row[0] or 0)
    queued_jobs = int(row[1] or 0)
    failed_jobs = int(row[2] or 0)
    avg_wait = float(row[3] or 0.0)
    max_wait = float(row[4] or 0.0)

    confidence = 0.79 if total_jobs else 0.5
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    evidence = [
        f"total_jobs={total_jobs}",
        f"queued_jobs={queued_jobs}",
        f"failed_jobs={failed_jobs}",
        f"avg_queue_wait_min={avg_wait:.2f}",
        f"max_queue_wait_min={max_wait:.2f}",
    ]
    summary = (
        f"Job system has {queued_jobs} queued and {failed_jobs} failed jobs "
        f"with average queue wait of {avg_wait:.1f} minutes."
    )
    trace = AgentTrace(
        agent_name="job_queue_agent",
        routed_reason=routed_reason,
        query_used=question,
        sql_executed=" ".join(sql.split()),
        rows_scanned=total_jobs,
        elapsed_ms=elapsed_ms,
        notes=["Checked backlog, failures, and queue wait behavior."],
    )
    return AgentResult(
        agent_name="job_queue_agent",
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        trace=trace,
    )
