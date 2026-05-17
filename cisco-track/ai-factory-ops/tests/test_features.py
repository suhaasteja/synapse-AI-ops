"""Stage 2 tests for deterministic feature extraction."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.features import extract_features, summarize_top_signals


def test_extract_perf_features_sane() -> None:
    features = extract_features("perf-001")
    assert features.track == "performance_advisor"
    assert features.p95_latency_ms is not None
    assert features.p95_latency_ms >= 0
    assert features.error_rate_5xx is not None
    assert 0.0 <= features.error_rate_5xx <= 1.0

    signals = summarize_top_signals(features)
    assert len(signals) >= 3
    assert all(isinstance(item, str) and item.strip() for item in signals)


def test_extract_gpu_features_sane() -> None:
    features = extract_features("gpu-001")
    assert features.track == "gpu_placement"
    assert features.pending_jobs is not None
    assert features.pending_jobs >= 0
    assert features.fragmentation_score is not None
    assert features.fragmentation_score >= 0

    signals = summarize_top_signals(features)
    assert len(signals) >= 3
    assert all(isinstance(item, str) and item.strip() for item in signals)


def test_extract_failure_features_sane() -> None:
    features = extract_features("fail-001")
    assert features.track == "failure_detective"
    assert features.critical_alert_count is not None
    assert features.critical_alert_count >= 0
    assert features.storage_latency_p95 is not None
    assert features.storage_latency_p95 >= 0

    signals = summarize_top_signals(features)
    assert len(signals) >= 3
    assert all(isinstance(item, str) and item.strip() for item in signals)
