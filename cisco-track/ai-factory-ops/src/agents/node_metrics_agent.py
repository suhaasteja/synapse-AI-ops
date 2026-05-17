"""Node metrics specialist agent."""

from __future__ import annotations

import time

from .base import AgentResult, AgentTrace
from ..data import get_con


def run_node_metrics_agent(question: str, routed_reason: str) -> AgentResult:
    """Analyze node-level capacity and thermal signals."""
    started = time.perf_counter()
    sql = """
    SELECT
        COUNT(*) AS metric_rows,
        AVG(gpu_utilization_pct) AS avg_gpu_utilization_pct,
        AVG(memory_utilization_pct) AS avg_memory_utilization_pct,
        MAX(temperature_c) AS max_temperature_c,
        COUNT(*) FILTER (WHERE health_state <> 'healthy') AS unhealthy_rows
    FROM scenario_node_metrics
    """
    con = get_con()
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()

    metric_rows = int(row[0] or 0)
    avg_gpu_util = float(row[1] or 0.0)
    avg_mem_util = float(row[2] or 0.0)
    max_temp = float(row[3] or 0.0)
    unhealthy_rows = int(row[4] or 0)

    confidence = 0.78 if metric_rows else 0.5
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    evidence = [
        f"metric_rows={metric_rows}",
        f"avg_gpu_utilization_pct={avg_gpu_util:.2f}",
        f"avg_memory_utilization_pct={avg_mem_util:.2f}",
        f"max_temperature_c={max_temp:.2f}",
        f"unhealthy_rows={unhealthy_rows}",
    ]
    summary = (
        f"Node telemetry indicates average GPU utilization of {avg_gpu_util:.1f}% "
        f"with a max observed temperature of {max_temp:.1f}°C."
    )
    trace = AgentTrace(
        agent_name="node_metrics_agent",
        routed_reason=routed_reason,
        query_used=question,
        sql_executed=" ".join(sql.split()),
        rows_scanned=metric_rows,
        elapsed_ms=elapsed_ms,
        notes=["Checked thermal pressure and unhealthy node signals."],
    )
    return AgentResult(
        agent_name="node_metrics_agent",
        summary=summary,
        confidence=confidence,
        evidence=evidence,
        trace=trace,
    )
