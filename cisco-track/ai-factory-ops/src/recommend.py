"""Recommendation schema and pipeline helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .features import extract_features, summarize_top_signals
from .llm import explain
from .rules import rank_candidates
from .runbooks import parse_runbooks, retrieve_best_runbook


class Recommendation(BaseModel):
    """Structured recommendation payload for validator compatibility."""

    scenario_id: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    target: str = Field(min_length=1)
    reason_category: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1)

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: list[str]) -> list[str]:
        """Ensure at least one non-empty evidence string."""
        if not any(item.strip() for item in value):
            raise ValueError("evidence must contain at least one non-empty string")
        return value

    def to_json(self) -> str:
        """Return pretty-printed JSON string."""
        return self.model_dump_json(indent=2)

    def write(self, path: str | Path) -> Path:
        """Write recommendation JSON to disk."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json(), encoding="utf-8")
        return destination


def _project_root() -> Path:
    """Return the ai-factory-ops project root directory."""
    return Path(__file__).resolve().parents[1]


def _runbook_path() -> Path:
    """Resolve runbooks path from symlinked data or fallback dataset path."""
    path = _project_root() / "data" / "public" / "runbooks.md"
    if path.exists():
        return path
    return _project_root().parents[0] / "ai_factory_hackathon_student" / "data" / "public" / "runbooks.md"


def build_recommendation(scenario_id: str, use_llm: bool = True) -> Recommendation:
    """Build a full recommendation from deterministic features + top candidate."""
    features = extract_features(scenario_id)
    top_signals = summarize_top_signals(features)
    candidates = rank_candidates(features)
    if not candidates:
        raise ValueError(f"No candidate actions generated for scenario_id: {scenario_id}")

    top_candidate = candidates[0]
    runbook_title: str | None = None
    runbook_excerpt: str | None = None

    if features.track == "failure_detective":
        sections = parse_runbooks(_runbook_path())
        query_text = " ".join(
            top_candidate.triggered_rules
            + top_candidate.supporting_signals
            + [top_candidate.action, top_candidate.reason_category]
        )
        section, _score = retrieve_best_runbook(query_text, sections)
        if section is not None:
            runbook_title = section.title
            runbook_excerpt = section.body
            top_candidate.runbook_excerpt = section.body

    rationale = explain(
        candidate=top_candidate,
        features=features,
        top_signals=top_signals,
        runbook_excerpt=runbook_excerpt,
        use_llm=use_llm,
    )

    evidence: list[str] = []
    evidence.extend(top_signals[:5])
    evidence.extend([f"rule:{rule}" for rule in top_candidate.triggered_rules])
    if runbook_title:
        evidence.append(f"runbook:{runbook_title}")
    evidence.append(f"reason:{rationale}")

    return Recommendation(
        scenario_id=scenario_id,
        recommended_action=top_candidate.action,
        target=top_candidate.target,
        reason_category=top_candidate.reason_category,
        confidence=top_candidate.confidence,
        evidence=evidence,
    )
