"""Alerts + logs specialist agent."""

from __future__ import annotations

import time

from .base import AgentResult, AgentTrace
from ..data import get_con


def run_alerts_logs_agent(question: str, routed_reason: str) -> AgentResult:
    """Analyze high-severity incident and log signals."""
    started = time.perf_counter()
    alerts_sql = """
    SELECT
        COUNT(*) AS total_alerts,
        COUNT(*) FILTER (WHERE severity = 'critical') AS critical_alerts,
        COUNT(DISTINCT alert_type) AS distinct_alert_types
    FROM scenario_alerts
    """
    logs_sql = """
    SELECT
        COUNT(*) AS total_logs,
        COUNT(*) FILTER (WHERE severity IN ('error', 'critical')) AS severe_logs
    FROM scenario_logs
    """
    con = get_con()
    try:
        arow = con.execute(alerts_sql).fetchone()
        lrow = con.execute(logs_sql).fetchone()
    finally:
        con.close()

    total_alerts = int(arow[0] or 0)
    critical_alerts = int(arow[1] or 0)
    distinct_alert_types = int(arow[2] or 0)
    total_logs = int(lrow[0] or 0)
    severe_logs = int(lrow[1] or 0)

    confidence = 0.82 if total_alerts or total_logs else 0.5
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    evidence = [
        f"total_alerts={total_alerts}",
        f"critical_alerts={critical_alerts}",
        f"distinct_alert_types={distinct_alert_types}",
        f"total_logs={total_logs}",
        f"severe_logs={severe_logs}",
    ]
    summary = (
        f"Incident streams show {critical_alerts} critical alerts across "
        f"{distinct_alert_types} alert types and {severe_logs} severe log entries."
    )
    trace = AgentTrace(
        agent_name="alerts_logs_agent",
        routed_reason=routed_reason,
        query_used=question,
        sql_executed=f"{' '.join(alerts_sql.split())} || {' '.join(logs_sql.split())}",
        rows_scanned=total_alerts + total_logs,
        elapsed_ms=elapsed_ms,
        notes=["Correlated alert severity with severe log volume."],
    )
    return AgentResult(
        agent_name="alerts_logs_agent",
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        trace=trace,
    )
