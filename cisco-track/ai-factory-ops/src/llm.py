"""LLM/text explanation helpers for recommendations and orchestration planning."""

from __future__ import annotations

import json
import os
from typing import Any

from .charts import generate_fallback_charts, normalize_chart_suggestions
from .features import ScenarioFeatures
from .rules import Candidate
from .settings import settings


def _deterministic_reason(candidate: Candidate, top_signals: list[str], runbook_excerpt: str | None = None) -> str:
    """Fallback explanation when LLM is disabled or unavailable."""
    signals = "; ".join(top_signals[:3]) if top_signals else "no dominant anomalies detected"
    reason = (
        f"Triggered rules: {', '.join(candidate.triggered_rules)}. "
        f"Top signals: {signals}."
    )
    if runbook_excerpt:
        reason += " Runbook evidence was considered."
    return reason


def _extract_json_array(text: str) -> list[Any] | None:
    """Extract and parse the first JSON array found in text."""
    text = text.strip()
    if not text:
        return None

    # Fast path: full payload is JSON array.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    # Fallback: find first bracketed array in mixed text.
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    snippet = text[start : end + 1]
    try:
        parsed = json.loads(snippet)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        return None
    return None


def _extract_text_content(content: Any) -> str:
    """Normalize LiteLLM response message content into plain text."""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
                continue
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
        return " ".join(parts).strip()

    return str(content).strip()


def _ensure_provider_env() -> None:
    """Populate provider env vars from settings loaded via .env."""
    if settings.google_api_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    if settings.gemini_api_key and not os.getenv("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
    if settings.openai_api_key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key


def _litellm_chat(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call LiteLLM completion and return normalized content text."""
    _ensure_provider_env()
    from litellm import completion

    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    choices = getattr(response, "choices", None) or response.get("choices", [])
    if not choices:
        return ""

    first = choices[0]
    message = getattr(first, "message", None) or first.get("message", {})
    content = getattr(message, "content", None) if hasattr(message, "content") else message.get("content")
    return _extract_text_content(content)


def _extract_agent_names_from_text(raw: str, available_agents: dict[str, str], max_agents: int) -> list[str]:
    """Best-effort salvage when model returns non-JSON text containing agent names."""
    lowered = raw.lower()
    picked: list[str] = []
    for agent_name in available_agents.keys():
        if agent_name.lower() in lowered:
            picked.append(agent_name)
    return picked[:max_agents]


def _infer_agent_names_from_question(question: str, max_agents: int) -> list[str]:
    """Infer likely agent set directly from user question keywords."""
    q = question.lower()
    inferred: list[str] = []

    def add(agent_name: str) -> None:
        if agent_name not in inferred:
            inferred.append(agent_name)

    if any(token in q for token in ["latency", "slo", "request", "ttft", "token"]):
        add("inference_agent")
    if any(token in q for token in ["gpu", "node", "temperature", "utilization", "rack", "health"]):
        add("node_metrics_agent")
    if any(token in q for token in ["replica", "serving", "queue depth", "queued requests", "ready replicas"]):
        add("serving_agent")
    if any(token in q for token in ["alert", "log", "error", "incident", "failure", "critical"]):
        add("alerts_logs_agent")
    if any(token in q for token in ["job", "queue", "placement", "wait", "failed jobs", "priority"]):
        add("job_queue_agent")

    return inferred[:max_agents]


def plan_route_detailed(
    question: str,
    available_agents: dict[str, str],
    max_agents: int = 5,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Use LLM to produce a strict routing plan plus planner diagnostics."""
    model = settings.aifops_router_model
    planner_debug: dict[str, Any] = {
        "llm_attempts": 0,
        "json_parse_ok": False,
        "salvage_used": False,
        "fallback_reason": None,
        "router_model": model,
    }

    agent_lines = "\n".join(f"- {name}: {capability}" for name, capability in available_agents.items())

    system_prompt = (
        "You are an AIOps orchestration planner. "
        "You route user questions to available specialist agents. "
        "Return ONLY valid JSON as an array with objects containing exactly: "
        "agent_name, reason, sub_query."
    )

    base_user_prompt = f"""
Available agents and capabilities:
{agent_lines}

User question:
{question}

Rules:
1) Use only agent_name values from the available list above.
2) Select between 1 and {max_agents} agents.
3) reason must be concise and specific.
4) sub_query must be a focused question for that selected agent.
5) Output JSON array only. No markdown, no prose.

Example:
[
  {{
    "agent_name": "inference_agent",
    "reason": "User asks about latency and SLO behavior.",
    "sub_query": "Summarize p95 latency, SLO violation rate, and error rates."
  }}
]
""".strip()

    last_raw = ""
    for attempt in range(2):
        planner_debug["llm_attempts"] = attempt + 1
        user_prompt = base_user_prompt
        if attempt == 1:
            user_prompt = f"{base_user_prompt}\n\nYour previous response was not valid JSON. Return only the JSON array now."

        try:
            raw = _litellm_chat(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=500,
                temperature=0.0,
            )
            last_raw = raw
            parsed = _extract_json_array(raw)
            if not isinstance(parsed, list):
                continue

            planner_debug["json_parse_ok"] = True
            validated: list[dict[str, str]] = []
            for item in parsed[:max_agents]:
                if not isinstance(item, dict):
                    continue
                agent_name = str(item.get("agent_name", "")).strip()
                reason = str(item.get("reason", "")).strip()
                sub_query = str(item.get("sub_query", "")).strip()
                if not agent_name:
                    continue
                if not reason:
                    reason = "LLM-selected agent for query coverage."
                if not sub_query:
                    sub_query = question
                validated.append(
                    {
                        "agent_name": agent_name,
                        "reason": reason,
                        "sub_query": sub_query,
                    }
                )
            if validated:
                return validated, planner_debug
            planner_debug["fallback_reason"] = "json_valid_but_no_usable_agents"
        except Exception:
            continue

    # Best-effort salvage from non-JSON text response.
    if last_raw:
        names = _extract_agent_names_from_text(last_raw, available_agents, max_agents)
        inferred = _infer_agent_names_from_question(question, max_agents)
        for name in inferred:
            if name not in names:
                names.append(name)
        names = names[:max_agents]

        if names:
            planner_debug["salvage_used"] = True
            planner_debug["fallback_reason"] = "non_json_output_salvaged"
            return (
                [
                    {
                        "agent_name": name,
                        "reason": "Recovered from non-JSON planner output.",
                        "sub_query": question,
                    }
                    for name in names
                ],
                planner_debug,
            )

    inferred_only = _infer_agent_names_from_question(question, max_agents)
    if inferred_only:
        planner_debug["salvage_used"] = True
        planner_debug["fallback_reason"] = planner_debug["fallback_reason"] or "planner_error_keyword_salvage"
        return (
            [
                {
                    "agent_name": name,
                    "reason": "Recovered from question keywords after planner failure.",
                    "sub_query": question,
                }
                for name in inferred_only
            ],
            planner_debug,
        )

    planner_debug["fallback_reason"] = planner_debug["fallback_reason"] or "llm_plan_empty_or_invalid_json"
    return [], planner_debug


def plan_route(
    question: str,
    available_agents: dict[str, str],
    max_agents: int = 5,
) -> list[dict[str, str]]:
    """Backward-compatible wrapper returning only the plan."""
    plan, _ = plan_route_detailed(question=question, available_agents=available_agents, max_agents=max_agents)
    return plan


def _build_chart_data_samples(agent_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create compact chart-ready numeric samples from agent evidence."""
    samples: list[dict[str, Any]] = []
    for result in agent_results:
        agent_name = str(result.get("agent_name", "")).strip()
        evidence = result.get("evidence", [])
        if not agent_name or not isinstance(evidence, list):
            continue

        metrics: list[dict[str, Any]] = []
        for item in evidence:
            text = str(item)
            if "=" not in text:
                continue
            key, raw = text.split("=", 1)
            key = key.strip()
            raw = raw.strip()
            try:
                value = float(raw)
            except Exception:
                continue
            metrics.append({"x": key, "y": value})
            if len(metrics) >= 8:
                break

        if not metrics:
            continue

        samples.append(
            {
                "agent_name": agent_name,
                "confidence": result.get("confidence"),
                "sample_points": metrics,
            }
        )
    return samples


def suggest_charts(
    user_question: str,
    planner_mode: str,
    agent_results: list[dict[str, Any]],
    max_charts: int = 3,
    max_points: int = 100,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Suggest safe chart payloads using LLM-first planning with deterministic fallback."""
    chart_debug: dict[str, Any] = {
        "llm_attempts": 0,
        "json_parse_ok": False,
        "fallback_used": False,
        "fallback_reason": None,
        "chart_model": settings.aifops_explainer_model,
    }

    if max_charts <= 0 or not agent_results:
        chart_debug["fallback_used"] = True
        chart_debug["fallback_reason"] = "no_agent_results_or_zero_max_charts"
        return [], chart_debug

    model = settings.aifops_explainer_model
    findings = [
        {
            "agent_name": str(item.get("agent_name", "")),
            "summary": str(item.get("summary", "")),
            "confidence": item.get("confidence"),
            "evidence": [str(e) for e in item.get("evidence", [])[:4]],
        }
        for item in agent_results
    ]
    sample_data = _build_chart_data_samples(agent_results)

    system_prompt = (
        "You are an AIOps chart planner. "
        "Return ONLY valid JSON as an array of chart suggestion objects. "
        "Do not include markdown or prose."
    )

    user_prompt_base = f"""
User question:
{user_question}

Planner mode:
{planner_mode}

Agent findings:
{json.dumps(findings, ensure_ascii=False)}

Sample chart-ready numeric data:
{json.dumps(sample_data, ensure_ascii=False)}

Requirements:
1) Return 1 to {max_charts} chart objects (if data supports it); otherwise return [].
2) Allowed chart_type values: "line", "bar", "area", "pie".
3) Choose the best representation:
   - "line" for trend/sequence progression,
   - "area" for cumulative magnitude trends,
   - "bar" for category comparisons,
   - "pie" for part-to-whole composition (shares/distribution/percentage split).
4) Avoid bar-only output when multiple charts are returned and data supports other chart types.
5) Each object must include exactly these fields:
   - title (string)
   - chart_type ("line"|"bar"|"area"|"pie")
   - x_key (string)
   - y_key (string)
   - series_key (string or null)
   - data (array of objects with x:string, y:number, optional series:string|null)
   - source_agents (array of agent names)
   - why_this_chart (string)
   - confidence (number 0..1)
6) Keep each data array <= {max_points} points.
7) Use only provided findings/sample data. Do not invent entities.
8) Output JSON array only.

Example:
[
  {{
    "title": "Agent Confidence Overview",
    "chart_type": "bar",
    "x_key": "agent_name",
    "y_key": "confidence",
    "series_key": null,
    "data": [{{"x": "inference_agent", "y": 0.86}}],
    "source_agents": ["inference_agent"],
    "why_this_chart": "Shows confidence by selected agents.",
    "confidence": 0.78
  }}
]
""".strip()

    last_raw = ""
    for attempt in range(2):
        chart_debug["llm_attempts"] = attempt + 1
        user_prompt = user_prompt_base
        if attempt == 1:
            user_prompt = f"{user_prompt_base}\n\nYour previous response was not valid JSON. Return only the JSON array now."

        try:
            raw = _litellm_chat(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=900,
                temperature=0.0,
            )
            last_raw = raw
            parsed = _extract_json_array(raw)
            if not isinstance(parsed, list):
                continue

            chart_debug["json_parse_ok"] = True
            raw_items = [item for item in parsed[:max_charts] if isinstance(item, dict)]
            normalized = normalize_chart_suggestions(raw_items, max_points=max_points)
            if normalized:
                return [item.model_dump() for item in normalized[:max_charts]], chart_debug
            chart_debug["fallback_reason"] = "json_valid_but_no_valid_charts"
        except Exception:
            continue

    chart_debug["fallback_used"] = True
    if last_raw and not chart_debug["fallback_reason"]:
        chart_debug["fallback_reason"] = "non_json_or_invalid_chart_payload"
    elif not chart_debug["fallback_reason"]:
        chart_debug["fallback_reason"] = "llm_chart_planner_error"

    fallback = generate_fallback_charts(
        user_question=user_question,
        agent_results=agent_results,
        max_charts=max_charts,
    )
    return [item.model_dump() for item in fallback], chart_debug


def explain(
    candidate: Candidate,
    features: ScenarioFeatures,
    top_signals: list[str],
    runbook_excerpt: str | None = None,
    use_llm: bool = True,
) -> str:
    """Generate a concise rationale using only pre-computed facts."""
    if not use_llm:
        return _deterministic_reason(candidate, top_signals, runbook_excerpt)

    model = settings.aifops_explainer_model

    system_prompt = (
        "You write one-paragraph operations rationales. "
        "Use only numbers and facts provided. Do not invent values. Output 2-4 sentences."
    )

    user_prompt = f"""
candidate_action: {candidate.action}
candidate_target: {candidate.target}
reason_category: {candidate.reason_category}
confidence: {candidate.confidence:.2f}
triggered_rules: {candidate.triggered_rules}
supporting_signals: {candidate.supporting_signals}
scenario_track: {features.track}
scenario_id: {features.scenario_id}
top_signals: {top_signals}
runbook_excerpt: {runbook_excerpt or "N/A"}
""".strip()

    try:
        explanation = _litellm_chat(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=220,
            temperature=0.0,
        )
        return explanation or _deterministic_reason(candidate, top_signals, runbook_excerpt)
    except Exception:
        return _deterministic_reason(candidate, top_signals, runbook_excerpt)


def summarize_orchestrated_answer(
    user_question: str,
    agent_results: list[dict[str, Any]],
    planner_mode: str,
) -> str:
    """Generate a compact executive summary for orchestrated chat output."""
    if not agent_results:
        return "No agent findings were available to summarize."

    model = settings.aifops_explainer_model

    findings = "\n".join(
        f"- {item.get('agent_name', 'unknown')}: {item.get('summary', '')}"
        for item in agent_results
    )

    system_prompt = (
        "You are an SRE/AIOps assistant writing for operators and engineering leads. "
        "Produce a clear executive narrative, not a list of metrics. "
        "Use only provided findings; do not invent values, entities, or causal claims."
    )
    user_prompt = f"""
User question:
{user_question}

Planner mode:
{planner_mode}

Agent findings:
{findings}

Output format requirements:
- Exactly one paragraph (no bullets, no headings).
- 3-5 sentences.
- Sentence 1: directly answer what appears to be wrong.
- Sentence 2-3: explain strongest corroborating signals across subsystems.
- Final sentence: one practical next investigation step.
- Keep it plain-English and explanatory (avoid "agent X reports" phrasing).
""".strip()

    try:
        summary = _litellm_chat(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=180,
            temperature=0.0,
        ).strip()
        if summary:
            return summary
    except Exception:
        pass

    # Deterministic fallback summary (single explanatory paragraph).
    if not agent_results:
        return "No agent findings were available to summarize."

    by_agent = {str(item.get("agent_name", "")): str(item.get("summary", "")).strip() for item in agent_results}
    inf = by_agent.get("inference_agent", "")
    node = by_agent.get("node_metrics_agent", "")
    serving = by_agent.get("serving_agent", "")
    alerts = by_agent.get("alerts_logs_agent", "")
    jobs = by_agent.get("job_queue_agent", "")

    parts: list[str] = []
    if inf:
        parts.append(f"The system is experiencing user-visible performance degradation, with inference signals indicating elevated latency and SLO pressure ({inf}).")
    else:
        parts.append("The system appears to be under operational stress with measurable performance impact.")

    supporting = [text for text in [serving, node, alerts, jobs] if text]
    if supporting:
        parts.append(
            "The strongest corroborating signals suggest multi-layer pressure across serving, infrastructure, and operations: "
            + "; ".join(supporting[:3])
            + "."
        )

    if jobs or alerts:
        parts.append("As an immediate next step, triage critical alert clusters and failed/queued jobs in the same time window as the latency spike to isolate the primary bottleneck.")
    else:
        parts.append("As an immediate next step, inspect the highest queue-depth interval and the hottest nodes during the latency spike window to isolate the bottleneck.")

    return " ".join(parts)
