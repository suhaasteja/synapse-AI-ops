"""Rule-based candidate generation for recommendations."""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel, Field

from .features import ScenarioFeatures


class ActionCatalog(BaseModel):
    """Track-to-action catalog loaded from action_menu.csv."""

    by_track: dict[str, set[str]]

    @classmethod
    def from_csv(cls, path: str | Path) -> "ActionCatalog":
        source = Path(path)
        with source.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        by_track: dict[str, set[str]] = {}
        for row in rows:
            track_id = str(row["track_id"]).strip()
            action_id = str(row["action_id"]).strip()
            by_track.setdefault(track_id, set()).add(action_id)
        return cls(by_track=by_track)

    def has_action(self, track_id: str, action_id: str) -> bool:
        return action_id in self.by_track.get(track_id, set())


class Candidate(BaseModel):
    """Rule candidate emitted prior to any LLM explanation."""

    action: str
    target: str
    reason_category: str
    confidence: float = Field(ge=0.0, le=1.0)
    triggered_rules: list[str]
    supporting_signals: list[str]
    runbook_excerpt: str | None = None


def _default_action_menu_path() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    symlink_path = project_root / "data" / "public" / "action_menu.csv"
    if symlink_path.exists():
        return symlink_path
    return project_root.parent / "ai_factory_hackathon_student" / "data" / "public" / "action_menu.csv"


def _confidence(num_corroborating_signals: int) -> float:
    return min(0.5 + 0.1 * num_corroborating_signals, 0.95)


def _candidate(
    *,
    action: str,
    target: str,
    reason_category: str,
    rule_name: str,
    signals: list[str],
) -> Candidate:
    return Candidate(
        action=action,
        target=target,
        reason_category=reason_category,
        confidence=_confidence(len(signals)),
        triggered_rules=[rule_name],
        supporting_signals=signals,
    )


def _perf_scale_up(features: ScenarioFeatures) -> Candidate | None:
    if (
        (features.queue_depth or 0) >= 50
        and (features.replica_unhealthy_count or 0) == 0
        and (features.p99_latency_ms or 0.0) >= 10_000
    ):
        signals = [
            f"queue_depth={features.queue_depth}",
            f"replica_unhealthy_count={features.replica_unhealthy_count}",
            f"p99_latency_ms={features.p99_latency_ms}",
        ]
        return _candidate(
            action="add_capacity",
            target=features.focus_entity,
            reason_category="latency_pressure",
            rule_name="perf_scale_up_capacity",
            signals=signals,
        )
    return None


def _perf_unhealthy_replicas(features: ScenarioFeatures) -> Candidate | None:
    if (features.replica_unhealthy_count or 0) > 0:
        signals = [
            f"replica_unhealthy_count={features.replica_unhealthy_count}",
            f"queue_depth={features.queue_depth}",
        ]
        return _candidate(
            action="reroute_traffic",
            target=features.focus_entity,
            reason_category="replica_health",
            rule_name="perf_reroute_unhealthy_replicas",
            signals=signals,
        )
    return None


def _perf_throttle(features: ScenarioFeatures) -> Candidate | None:
    if (features.error_rate_5xx or 0.0) >= 0.02 and (features.queue_depth or 0) >= 20:
        signals = [
            f"error_rate_5xx={features.error_rate_5xx}",
            f"queue_depth={features.queue_depth}",
        ]
        return _candidate(
            action="reduce_load",
            target=features.focus_entity,
            reason_category="error_surge",
            rule_name="perf_reduce_load_on_5xx_and_queue",
            signals=signals,
        )
    return None


def _placement_defragment(features: ScenarioFeatures) -> Candidate | None:
    if (features.fragmentation_score or 0) >= 20 and (features.pending_jobs or 0) > 0:
        signals = [
            f"fragmentation_score={features.fragmentation_score}",
            f"pending_jobs={features.pending_jobs}",
            f"largest_pending_gpus={features.largest_pending_gpus}",
        ]
        return _candidate(
            action="reserve_full_node",
            target=features.focus_entity,
            reason_category="fragmentation",
            rule_name="placement_reserve_full_node",
            signals=signals,
        )
    return None


def _placement_drain_unhealthy(features: ScenarioFeatures) -> Candidate | None:
    if (features.unhealthy_node_count or 0) > 0 and (features.pending_jobs or 0) > 0:
        signals = [
            f"unhealthy_node_count={features.unhealthy_node_count}",
            f"pending_jobs={features.pending_jobs}",
        ]
        return _candidate(
            action="avoid_unhealthy_node",
            target=features.focus_entity,
            reason_category="node_health",
            rule_name="placement_avoid_unhealthy_node",
            signals=signals,
        )
    return None


def _placement_prioritize_urgent(features: ScenarioFeatures) -> Candidate | None:
    if (features.pending_high_priority or 0) > 0 and (features.avg_gpu_util or 0.0) < 70:
        signals = [
            f"pending_high_priority={features.pending_high_priority}",
            f"avg_gpu_util={features.avg_gpu_util}",
        ]
        return _candidate(
            action="prioritize_urgent_jobs",
            target=features.focus_entity,
            reason_category="priority_queue",
            rule_name="placement_prioritize_urgent",
            signals=signals,
        )
    return None


def _failure_move_job(features: ScenarioFeatures) -> Candidate | None:
    if (features.node_temp_outlier_count or 0) > 0 and (features.correlated_alert_clusters or 0) > 0:
        signals = [
            f"node_temp_outlier_count={features.node_temp_outlier_count}",
            f"correlated_alert_clusters={features.correlated_alert_clusters}",
        ]
        return _candidate(
            action="move_job",
            target=features.focus_entity,
            reason_category="thermal_fault",
            rule_name="failure_move_job_from_hot_nodes",
            signals=signals,
        )
    return None


def _failure_restart_from_checkpoint(features: ScenarioFeatures) -> Candidate | None:
    if (features.checkpoint_timeout_count or 0) > 0 and (features.storage_latency_p95 or 0.0) >= 150:
        signals = [
            f"checkpoint_timeout_count={features.checkpoint_timeout_count}",
            f"storage_latency_p95={features.storage_latency_p95}",
            f"checkpoint_failure_count={features.checkpoint_failure_count}",
        ]
        return _candidate(
            action="restart_from_checkpoint",
            target=features.focus_entity,
            reason_category="storage_checkpoint",
            rule_name="failure_restart_from_checkpoint",
            signals=signals,
        )
    return None


def _failure_escalate(features: ScenarioFeatures) -> Candidate | None:
    if (features.failed_job_count or 0) >= 3 and (features.critical_alert_count or 0) >= 3:
        signals = [
            f"failed_job_count={features.failed_job_count}",
            f"critical_alert_count={features.critical_alert_count}",
        ]
        return _candidate(
            action="escalate",
            target=features.focus_entity,
            reason_category="multi_signal_failure",
            rule_name="failure_escalate_complex_incident",
            signals=signals,
        )
    return None


def rank_candidates(
    features: ScenarioFeatures,
    action_catalog: ActionCatalog | None = None,
) -> list[Candidate]:
    """Return ranked rule candidates for a scenario."""
    catalog = action_catalog or ActionCatalog.from_csv(_default_action_menu_path())

    rule_map: dict[str, list] = {
        "performance_advisor": [_perf_scale_up, _perf_unhealthy_replicas, _perf_throttle],
        "gpu_placement": [_placement_defragment, _placement_drain_unhealthy, _placement_prioritize_urgent],
        "failure_detective": [_failure_move_job, _failure_restart_from_checkpoint, _failure_escalate],
    }

    rule_fns = rule_map.get(features.track, [])
    candidates: list[Candidate] = []
    for rule_fn in rule_fns:
        candidate = rule_fn(features)
        if candidate and catalog.has_action(features.track, candidate.action):
            candidates.append(candidate)

    if not candidates:
        fallback_action = None
        if catalog.has_action(features.track, "no_action"):
            fallback_action = "no_action"
        else:
            available_actions = sorted(catalog.by_track.get(features.track, set()))
            if available_actions:
                fallback_action = available_actions[0]

        if fallback_action is not None:
            candidates.append(
                Candidate(
                    action=fallback_action,
                    target=features.focus_entity,
                    reason_category="no_trigger",
                    confidence=0.5,
                    triggered_rules=["fallback_action"],
                    supporting_signals=["No rule predicates crossed thresholds."],
                )
            )

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)
