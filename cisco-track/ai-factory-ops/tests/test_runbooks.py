"""Stage 4 tests for runbook retrieval."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.features import extract_features
from src.rules import rank_candidates
from src.runbooks import parse_runbooks, retrieve_best_runbook


def test_fail_001_retrieves_checkpoint_runbook() -> None:
    features = extract_features("fail-001")
    top_candidate = rank_candidates(features)[0]

    runbook_path = Path(__file__).resolve().parents[1] / "data" / "public" / "runbooks.md"
    sections = parse_runbooks(runbook_path)

    query_text = " ".join(
        top_candidate.triggered_rules
        + top_candidate.supporting_signals
        + [top_candidate.action, top_candidate.reason_category]
    )
    section, score = retrieve_best_runbook(query_text, sections)

    assert section is not None
    assert score > 0.0
    assert section.title == "CheckpointWriteTimeout"
