"""Chart schema and fallback chart generation utilities."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ChartType = Literal["line", "bar", "area", "pie"]


class ChartPoint(BaseModel):
    """One chart data point with a canonical x/y pair and optional series."""

    x: str
    y: float
    series: str | None = None


class ChartSuggestion(BaseModel):
    """Validated chart suggestion payload returned to the frontend."""

    title: str = Field(min_length=1)
    chart_type: ChartType
    x_key: str = Field(min_length=1)
    y_key: str = Field(min_length=1)
    series_key: str | None = None
    data: list[ChartPoint] = Field(default_factory=list)
    source_agents: list[str] = Field(default_factory=list)
    why_this_chart: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    def capped(self, max_points: int = 100) -> "ChartSuggestion":
        """Return a copy with data points capped to a safe rendering size."""
        return self.model_copy(update={"data": self.data[:max_points]})


def _try_float(value: str) -> float | None:
    """Parse a numeric value from evidence text, returning None on failure."""
    try:
        return float(value)
    except Exception:
        return None


def _extract_numeric_evidence(evidence_items: list[str]) -> list[tuple[str, float]]:
    """Extract key=value numeric pairs from evidence strings."""
    numeric: list[tuple[str, float]] = []
    for item in evidence_items:
        if "=" not in item:
            continue
        key, raw = item.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        value = _try_float(raw)
        if not key or value is None:
            continue
        numeric.append((key, value))
    return numeric


def _confidence_overview_chart(agent_results: list[dict]) -> ChartSuggestion | None:
    """Build a cross-agent confidence bar chart."""
    rows: list[ChartPoint] = []
    sources: list[str] = []
    for result in agent_results:
        agent_name = str(result.get("agent_name", "")).strip()
        if not agent_name:
            continue
        confidence = result.get("confidence", None)
        try:
            conf = float(confidence)
        except Exception:
            continue
        rows.append(ChartPoint(x=agent_name, y=conf))
        sources.append(agent_name)

    if not rows:
        return None

    return ChartSuggestion(
        title="Agent Confidence Overview",
        chart_type="bar",
        x_key="agent_name",
        y_key="confidence",
        series_key=None,
        data=rows,
        source_agents=sources,
        why_this_chart="Shows relative confidence across selected specialist agents.",
        confidence=0.75,
    ).capped()


def _should_use_pie_chart(user_question: str, numeric: list[tuple[str, float]]) -> bool:
    """Heuristic for part-to-whole prompts where pie is usually a better fit."""
    q = user_question.lower()
    pie_tokens = ["share", "distribution", "breakdown", "percentage", "percent", "proportion", "split"]
    if not any(token in q for token in pie_tokens):
        return False
    if len(numeric) < 2:
        return False
    return all(value >= 0 for _, value in numeric)


def _agent_metrics_chart(agent_result: dict, user_question: str) -> ChartSuggestion | None:
    """Build a per-agent metric chart from numeric evidence items."""
    agent_name = str(agent_result.get("agent_name", "")).strip()
    evidence = agent_result.get("evidence", [])
    if not agent_name or not isinstance(evidence, list):
        return None

    numeric = _extract_numeric_evidence([str(item) for item in evidence])
    if not numeric:
        return None

    rows = [ChartPoint(x=key, y=value) for key, value in numeric[:8]]
    use_pie = _should_use_pie_chart(user_question, numeric[:8])

    return ChartSuggestion(
        title=f"{agent_name} key metrics",
        chart_type="pie" if use_pie else "bar",
        x_key="metric",
        y_key="value",
        series_key=None,
        data=rows,
        source_agents=[agent_name],
        why_this_chart=(
            "Shows part-to-whole composition of key numeric evidence returned by this agent."
            if use_pie
            else "Highlights the most important numeric evidence returned by this agent."
        ),
        confidence=float(agent_result.get("confidence", 0.6)) if agent_result.get("confidence") is not None else 0.6,
    ).capped()


def generate_fallback_charts(
    user_question: str,
    agent_results: list[dict],
    max_charts: int = 3,
) -> list[ChartSuggestion]:
    """Generate deterministic charts when LLM chart planning is unavailable."""
    if max_charts <= 0:
        return []

    charts: list[ChartSuggestion] = []

    overview = _confidence_overview_chart(agent_results)
    if overview is not None:
        charts.append(overview)

    for result in agent_results:
        if len(charts) >= max_charts:
            break
        per_agent = _agent_metrics_chart(result, user_question=user_question)
        if per_agent is not None:
            charts.append(per_agent)

    # Final cap and dedupe by title.
    unique: dict[str, ChartSuggestion] = {}
    for chart in charts:
        unique.setdefault(chart.title, chart.capped())

    return list(unique.values())[:max_charts]


def normalize_chart_suggestions(raw_items: list[dict], max_points: int = 100) -> list[ChartSuggestion]:
    """Validate and sanitize externally produced chart suggestion payloads."""
    normalized: list[ChartSuggestion] = []
    for raw in raw_items:
        try:
            suggestion = ChartSuggestion.model_validate(raw).capped(max_points=max_points)
        except Exception:
            continue
        if not suggestion.data:
            continue
        normalized.append(suggestion)
    return normalized
