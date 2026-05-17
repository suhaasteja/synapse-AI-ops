"""Deterministic scenario feature extraction."""

from __future__ import annotations

from statistics import median

from pydantic import BaseModel

from .data import get_con


class ScenarioFeatures(BaseModel):
    """Typed features extracted for a single scenario."""

    scenario_id: str
    track: str
    window_start: str
    window_end: str
    focus_entity: str

    # performance_advisor
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    error_rate_4xx: float | None = None
    error_rate_5xx: float | None = None
    request_rate_rps: float | None = None
    replica_count: int | None = None
    replica_unhealthy_count: int | None = None
    kv_cache_pressure: float | None = None
    queue_depth: int | None = None

    # gpu_placement
    pending_jobs: int | None = None
    pending_high_priority: int | None = None
    largest_pending_gpus: int | None = None
    fragmentation_score: int | None = None
    unhealthy_node_count: int | None = None
    avg_gpu_util: float | None = None

    # failure_detective
    critical_alert_count: int | None = None
    checkpoint_failure_count: int | None = None
    checkpoint_timeout_count: int | None = None
    failed_job_count: int | None = None
    node_temp_outlier_count: int | None = None
    storage_latency_p95: float | None = None
    correlated_alert_clusters: int | None = None


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _track_baselines(track_id: str) -> dict[str, float]:
    """Build median-based baselines from scenario_signal_summary for a track."""
    con = get_con()
    try:
        rows = con.execute(
            """
            SELECT
                p95_latency_ms,
                max_queued_requests,
                error_count,
                max_stranded_gpus,
                critical_alerts,
                checkpoint_timeouts,
                storage_timeouts,
                max_temperature_c,
                p95_queue_wait_min
            FROM scenario_signal_summary
            WHERE track_id = ?
            """,
            [track_id],
        ).fetchall()
    finally:
        con.close()

    def col(idx: int) -> list[float]:
        return [float(r[idx]) for r in rows if r[idx] is not None]

    return {
        "p95_latency_ms": median(col(0)) if col(0) else 1.0,
        "max_queued_requests": median(col(1)) if col(1) else 1.0,
        "error_count": median(col(2)) if col(2) else 1.0,
        "max_stranded_gpus": median(col(3)) if col(3) else 1.0,
        "critical_alerts": median(col(4)) if col(4) else 1.0,
        "checkpoint_timeouts": median(col(5)) if col(5) else 1.0,
        "storage_timeouts": median(col(6)) if col(6) else 1.0,
        "max_temperature_c": median(col(7)) if col(7) else 1.0,
        "p95_queue_wait_min": median(col(8)) if col(8) else 1.0,
    }


def extract_features(scenario_id: str) -> ScenarioFeatures:
    """Extract deterministic features for one scenario using scenario_* views."""
    con = get_con()
    try:
        meta = con.execute(
            """
            SELECT scenario_id, track_id, start_time, end_time, focus_entity
            FROM evaluation_scenarios
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()
        if meta is None:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")

        sid, track_id, start_time, end_time, focus_entity = meta

        perf = con.execute(
            """
            SELECT
                approx_quantile(latency_ms, 0.50) AS p50_latency_ms,
                approx_quantile(latency_ms, 0.95) AS p95_latency_ms,
                approx_quantile(latency_ms, 0.99) AS p99_latency_ms,
                AVG(CASE WHEN status_code BETWEEN 400 AND 499 THEN 1.0 ELSE 0.0 END) AS error_rate_4xx,
                AVG(CASE WHEN status_code >= 500 THEN 1.0 ELSE 0.0 END) AS error_rate_5xx,
                COALESCE(
                    COUNT(*) / NULLIF(date_diff('second', MIN(timestamp), MAX(timestamp)), 0),
                    0.0
                ) AS request_rate_rps
            FROM scenario_requests
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        replicas = con.execute(
            """
            SELECT
                COALESCE(MAX(desired_replicas), 0) AS replica_count,
                COALESCE(MAX(desired_replicas - ready_replicas), 0) AS replica_unhealthy_count,
                COALESCE(MAX(kv_cache_used_gb), 0.0) AS kv_cache_pressure,
                COALESCE(MAX(queued_requests), 0) AS queue_depth
            FROM scenario_serving_replicas
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        placement = con.execute(
            """
            SELECT
                COALESCE(COUNT(*) FILTER (WHERE status = 'queued'), 0) AS pending_jobs,
                COALESCE(COUNT(*) FILTER (WHERE status = 'queued' AND priority = 'high'), 0) AS pending_high_priority,
                COALESCE(MAX(requested_gpus) FILTER (WHERE status = 'queued'), 0) AS largest_pending_gpus
            FROM scenario_job_queue
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        placement_nodes = con.execute(
            """
            SELECT
                COALESCE(SUM(stranded_gpus), 0) AS fragmentation_score,
                COALESCE(COUNT(DISTINCT node_id) FILTER (WHERE health_state <> 'healthy'), 0) AS unhealthy_node_count
            FROM scenario_placement_snapshots
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        node_util = con.execute(
            """
            SELECT
                COALESCE(AVG(gpu_utilization_pct), 0.0) AS avg_gpu_util,
                COALESCE(COUNT(*) FILTER (WHERE temperature_c >= 85), 0) AS node_temp_outlier_count
            FROM scenario_node_metrics
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        failure = con.execute(
            """
            SELECT
                COALESCE(COUNT(*) FILTER (WHERE severity = 'critical'), 0) AS critical_alert_count,
                COALESCE(COUNT(DISTINCT service || ':' || alert_type), 0) AS correlated_alert_clusters
            FROM scenario_alerts
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        checkpoint = con.execute(
            """
            SELECT
                COALESCE(COUNT(*) FILTER (WHERE status <> 'success'), 0) AS checkpoint_failure_count,
                COALESCE(COUNT(*) FILTER (WHERE error_type ILIKE '%timeout%'), 0) AS checkpoint_timeout_count
            FROM scenario_checkpoint_events
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        failed_jobs = con.execute(
            """
            SELECT COALESCE(COUNT(*) FILTER (WHERE status = 'failed'), 0) AS failed_job_count
            FROM scenario_job_queue
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

        storage = con.execute(
            """
            SELECT COALESCE(MAX(p95_latency_ms), 0.0) AS storage_latency_p95
            FROM scenario_storage_metrics
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()

    finally:
        con.close()

    return ScenarioFeatures(
        scenario_id=str(sid),
        track=str(track_id),
        window_start=str(start_time),
        window_end=str(end_time),
        focus_entity=str(focus_entity),
        p50_latency_ms=float(perf[0]) if perf and perf[0] is not None else None,
        p95_latency_ms=float(perf[1]) if perf and perf[1] is not None else None,
        p99_latency_ms=float(perf[2]) if perf and perf[2] is not None else None,
        error_rate_4xx=float(perf[3]) if perf and perf[3] is not None else None,
        error_rate_5xx=float(perf[4]) if perf and perf[4] is not None else None,
        request_rate_rps=float(perf[5]) if perf and perf[5] is not None else None,
        replica_count=int(replicas[0]) if replicas and replicas[0] is not None else None,
        replica_unhealthy_count=int(replicas[1]) if replicas and replicas[1] is not None else None,
        kv_cache_pressure=float(replicas[2]) if replicas and replicas[2] is not None else None,
        queue_depth=int(replicas[3]) if replicas and replicas[3] is not None else None,
        pending_jobs=int(placement[0]) if placement and placement[0] is not None else None,
        pending_high_priority=int(placement[1]) if placement and placement[1] is not None else None,
        largest_pending_gpus=int(placement[2]) if placement and placement[2] is not None else None,
        fragmentation_score=int(placement_nodes[0]) if placement_nodes and placement_nodes[0] is not None else None,
        unhealthy_node_count=int(placement_nodes[1]) if placement_nodes and placement_nodes[1] is not None else None,
        avg_gpu_util=float(node_util[0]) if node_util and node_util[0] is not None else None,
        critical_alert_count=int(failure[0]) if failure and failure[0] is not None else None,
        checkpoint_failure_count=int(checkpoint[0]) if checkpoint and checkpoint[0] is not None else None,
        checkpoint_timeout_count=int(checkpoint[1]) if checkpoint and checkpoint[1] is not None else None,
        failed_job_count=int(failed_jobs[0]) if failed_jobs and failed_jobs[0] is not None else None,
        node_temp_outlier_count=int(node_util[1]) if node_util and node_util[1] is not None else None,
        storage_latency_p95=float(storage[0]) if storage and storage[0] is not None else None,
        correlated_alert_clusters=int(failure[1]) if failure and failure[1] is not None else None,
    )


def summarize_top_signals(features: ScenarioFeatures) -> list[str]:
    """Return 3-5 anomaly-style human-readable top signals."""
    con = get_con()
    try:
        summary = con.execute(
            """
            SELECT
                p95_latency_ms,
                error_count,
                max_queued_requests,
                max_stranded_gpus,
                checkpoint_timeouts,
                storage_timeouts,
                critical_alerts,
                max_temperature_c,
                p95_queue_wait_min
            FROM scenario_signal_summary
            WHERE scenario_id = ?
            """,
            [features.scenario_id],
        ).fetchone()
    finally:
        con.close()

    if summary is None:
        return ["No scenario_signal_summary entry found."]

    baseline = _track_baselines(features.track)

    signals: list[tuple[float, str]] = []
    p95_latency_ms, error_count, max_queued_requests, max_stranded_gpus, checkpoint_timeouts, storage_timeouts, critical_alerts, max_temperature_c, p95_queue_wait_min = summary

    if features.track == "performance_advisor":
        ratio = _safe_div(float(p95_latency_ms or 0.0), baseline["p95_latency_ms"])
        signals.append((ratio, f"p95 latency {float(p95_latency_ms or 0.0):.1f}ms vs {baseline['p95_latency_ms']:.1f}ms baseline ({ratio:.2f}x)"))
        qratio = _safe_div(float(max_queued_requests or 0.0), baseline["max_queued_requests"])
        signals.append((qratio, f"max queued requests {int(max_queued_requests or 0)} vs {baseline['max_queued_requests']:.1f} baseline ({qratio:.2f}x)"))
        eratio = _safe_div(float(error_count or 0.0), baseline["error_count"])
        signals.append((eratio, f"error count {int(error_count or 0)} vs {baseline['error_count']:.1f} baseline ({eratio:.2f}x)"))
    elif features.track == "gpu_placement":
        fratio = _safe_div(float(max_stranded_gpus or 0.0), baseline["max_stranded_gpus"])
        signals.append((fratio, f"stranded GPUs {int(max_stranded_gpus or 0)} vs {baseline['max_stranded_gpus']:.1f} baseline ({fratio:.2f}x)"))
        wratio = _safe_div(float(p95_queue_wait_min or 0.0), baseline["p95_queue_wait_min"])
        signals.append((wratio, f"p95 queue wait {float(p95_queue_wait_min or 0.0):.1f} min vs {baseline['p95_queue_wait_min']:.1f} baseline ({wratio:.2f}x)"))
        qratio = _safe_div(float(max_queued_requests or 0.0), baseline["max_queued_requests"])
        signals.append((qratio, f"queued pressure {int(max_queued_requests or 0)} vs {baseline['max_queued_requests']:.1f} baseline ({qratio:.2f}x)"))
    else:
        crratio = _safe_div(float(critical_alerts or 0.0), baseline["critical_alerts"])
        signals.append((crratio, f"critical alerts {int(critical_alerts or 0)} vs {baseline['critical_alerts']:.1f} baseline ({crratio:.2f}x)"))
        toratio = _safe_div(float(checkpoint_timeouts or 0.0), baseline["checkpoint_timeouts"])
        signals.append((toratio, f"checkpoint timeouts {int(checkpoint_timeouts or 0)} vs {baseline['checkpoint_timeouts']:.1f} baseline ({toratio:.2f}x)"))
        sratio = _safe_div(float(storage_timeouts or 0.0), baseline["storage_timeouts"])
        signals.append((sratio, f"storage timeouts {int(storage_timeouts or 0)} vs {baseline['storage_timeouts']:.1f} baseline ({sratio:.2f}x)"))
        tratio = _safe_div(float(max_temperature_c or 0.0), baseline["max_temperature_c"])
        signals.append((tratio, f"max temperature {float(max_temperature_c or 0.0):.1f}C vs {baseline['max_temperature_c']:.1f}C baseline ({tratio:.2f}x)"))

    signals_sorted = sorted(signals, key=lambda x: x[0], reverse=True)
    return [text for _, text in signals_sorted[:5]]
