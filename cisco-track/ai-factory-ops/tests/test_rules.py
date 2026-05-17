"""Stage 3 tests for rule-based candidate generation."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.features import ScenarioFeatures
from src.rules import rank_candidates


def _base_features(track: str, scenario_id: str) -> ScenarioFeatures:
    return ScenarioFeatures(
        scenario_id=scenario_id,
        track=track,
        window_start="2026-04-01T00:00:00Z",
        window_end="2026-04-01T01:00:00Z",
        focus_entity="test-entity",
    )


def test_perf_scale_up_rule_fires() -> None:
    features = _base_features("performance_advisor", "perf-test")
    features.queue_depth = 120
    features.replica_unhealthy_count = 0
    features.p99_latency_ms = 50_000

    candidates = rank_candidates(features)

    assert candidates
    assert candidates[0].action == "add_capacity"
    assert "perf_scale_up_capacity" in candidates[0].triggered_rules


def test_placement_defragment_rule_fires() -> None:
    features = _base_features("gpu_placement", "gpu-test")
    features.fragmentation_score = 64
    features.pending_jobs = 5
    features.largest_pending_gpus = 8

    candidates = rank_candidates(features)

    assert candidates
    assert candidates[0].action == "reserve_full_node"
    assert "placement_reserve_full_node" in candidates[0].triggered_rules


def test_failure_restart_from_checkpoint_rule_fires() -> None:
    features = _base_features("failure_detective", "fail-test")
    features.checkpoint_timeout_count = 6
    features.storage_latency_p95 = 420.0
    features.checkpoint_failure_count = 6

    candidates = rank_candidates(features)

    assert candidates
    actions = [c.action for c in candidates]
    assert "restart_from_checkpoint" in actions
    matching = [c for c in candidates if c.action == "restart_from_checkpoint"][0]
    assert "failure_restart_from_checkpoint" in matching.triggered_rules
