"""LangGraph orchestrator for CSV specialist agents."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import (
    AgentResult,
    run_alerts_logs_agent,
    run_inference_agent,
    run_job_queue_agent,
    run_node_metrics_agent,
    run_serving_agent,
)
from .llm import plan_route_detailed, summarize_orchestrated_answer


class PlannerStep(TypedDict):
    """One routed sub-agent call."""

    agent_name: str
    reason: str
    sub_query: str


class OrchestratorState(TypedDict):
    """State passed across LangGraph nodes."""

    question: str
    route_plan: list[PlannerStep]
    planner_mode: str
    planner_debug: dict[str, Any]
    agent_results: list[dict[str, Any]]
    traces: list[dict[str, Any]]
    final_answer: str


_AGENT_RUNNERS = {
    "inference_agent": run_inference_agent,
    "node_metrics_agent": run_node_metrics_agent,
    "serving_agent": run_serving_agent,
    "alerts_logs_agent": run_alerts_logs_agent,
    "job_queue_agent": run_job_queue_agent,
}

_AGENT_CAPABILITIES = {
    "inference_agent": "Best for request latency, token throughput, status codes, and SLO violations in scenario_requests.",
    "node_metrics_agent": "Best for GPU/node utilization, memory, power, temperature, and health_state in scenario_node_metrics.",
    "serving_agent": "Best for replica readiness, desired-vs-ready gaps, and queued_requests in scenario_serving_replicas.",
    "alerts_logs_agent": "Best for incident evidence from scenario_alerts and scenario_logs, including critical alert volume.",
    "job_queue_agent": "Best for queued/failed jobs and queue wait pressure in scenario_job_queue.",
}


def _dedupe_plan(plan: list[PlannerStep]) -> list[PlannerStep]:
    """Deduplicate route steps while preserving order."""
    seen: set[str] = set()
    deduped: list[PlannerStep] = []
    for step in plan:
        if step["agent_name"] in seen:
            continue
        seen.add(step["agent_name"])
        deduped.append(step)
    return deduped


def _deterministic_route_agents(question: str) -> list[PlannerStep]:
    """Fallback deterministic router when LLM planning is unavailable."""
    q = question.lower()
    plan: list[PlannerStep] = []

    def add(agent_name: str, reason: str) -> None:
        plan.append(
            {
                "agent_name": agent_name,
                "reason": reason,
                "sub_query": question,
            }
        )

    if any(token in q for token in ["latency", "slo", "request", "ttft", "token"]):
        add("inference_agent", "Query references request latency/SLO behavior.")
    if any(token in q for token in ["gpu", "node", "temperature", "utilization", "rack", "health"]):
        add("node_metrics_agent", "Query references GPU/node health or capacity.")
    if any(token in q for token in ["replica", "serving", "queue depth", "queued requests", "ready replicas"]):
        add("serving_agent", "Query references serving replica readiness or queue pressure.")
    if any(token in q for token in ["alert", "log", "error", "incident", "failure", "critical"]):
        add("alerts_logs_agent", "Query references incident evidence from alerts/logs.")
    if any(token in q for token in ["job", "queue", "placement", "wait", "failed jobs", "priority"]):
        add("job_queue_agent", "Query references job lifecycle or queue pressure.")

    if not plan:
        add("inference_agent", "Default coverage for user query.")
        add("node_metrics_agent", "Default coverage for user query.")
        add("serving_agent", "Default coverage for user query.")
        add("alerts_logs_agent", "Default coverage for user query.")
        add("job_queue_agent", "Default coverage for user query.")

    return _dedupe_plan(plan)


def _route_agents(question: str) -> tuple[list[PlannerStep], str, dict[str, Any]]:
    """Route query using LLM planning first, then deterministic fallback."""
    llm_plan_raw, planner_debug = plan_route_detailed(
        question=question,
        available_agents=_AGENT_CAPABILITIES,
        max_agents=len(_AGENT_RUNNERS),
    )

    validated: list[PlannerStep] = []
    for item in llm_plan_raw:
        agent_name = item.get("agent_name", "")
        reason = item.get("reason", "")
        sub_query = item.get("sub_query", "")
        if agent_name not in _AGENT_RUNNERS:
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

    validated = _dedupe_plan(validated)
    if validated:
        return validated, "llm", planner_debug

    return _deterministic_route_agents(question), "fallback", planner_debug


def _planner_node(state: OrchestratorState) -> OrchestratorState:
    """Build a routing plan based on the user query."""
    question = state["question"]
    route_plan, planner_mode, planner_debug = _route_agents(question)
    return {
        **state,
        "route_plan": route_plan,
        "planner_mode": planner_mode,
        "planner_debug": planner_debug,
    }


def _execute_agents_node(state: OrchestratorState) -> OrchestratorState:
    """Execute routed specialist agents and collect normalized results/traces."""
    route_plan = state.get("route_plan", [])
    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []

    for step in route_plan:
        runner = _AGENT_RUNNERS[step["agent_name"]]
        agent_result: AgentResult = runner(step["sub_query"], step["reason"])
        results.append(agent_result.model_dump())
        traces.append(agent_result.trace.model_dump())

    return {
        **state,
        "agent_results": results,
        "traces": traces,
    }


def _synthesis_node(state: OrchestratorState) -> OrchestratorState:
    """Compose final user-facing response from specialist findings."""
    results = state.get("agent_results", [])
    planner_mode = state.get("planner_mode", "unknown")
    planner_debug = state.get("planner_debug", {})
    if not results:
        final = "I could not find enough evidence from the CSV agents to answer this query."
        return {**state, "final_answer": final}

    avg_confidence = sum(item["confidence"] for item in results) / len(results)
    executive_summary = summarize_orchestrated_answer(
        user_question=state.get("question", ""),
        agent_results=results,
        planner_mode=planner_mode,
    )
    lines = [
        "### Executive Summary",
        "",
        executive_summary,
        "",
        "### Orchestrated Analysis",
        "",
        f"- Planner mode: {planner_mode}",
        f"- Planner attempts: {planner_debug.get('llm_attempts', 0)} | JSON parse: {'yes' if planner_debug.get('json_parse_ok') else 'no'} | Salvage: {'yes' if planner_debug.get('salvage_used') else 'no'}",
        f"- Agents consulted: {', '.join(item['agent_name'] for item in results)}",
        f"- Aggregate confidence: {avg_confidence:.2f}",
        "",
        "#### Findings",
    ]
    for item in results:
        lines.append(f"- **{item['agent_name']}**: {item['summary']}")
    lines.append("")
    lines.append("#### Evidence Highlights")
    for item in results:
        top = item.get("evidence", [])[:2]
        if top:
            lines.append(f"- **{item['agent_name']}** → " + "; ".join(top))

    return {
        **state,
        "final_answer": "\n".join(lines).strip(),
    }


def build_orchestrator_graph():
    """Build and compile the LangGraph workflow."""
    graph = StateGraph(OrchestratorState)
    graph.add_node("planner", _planner_node)
    graph.add_node("execute_agents", _execute_agents_node)
    graph.add_node("synthesis", _synthesis_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "execute_agents")
    graph.add_edge("execute_agents", "synthesis")
    graph.add_edge("synthesis", END)
    return graph.compile()


def run_orchestrated_query(question: str) -> dict[str, Any]:
    """Run one user query through planner + specialist agents + synthesis."""
    app = build_orchestrator_graph()
    initial_state: OrchestratorState = {
        "question": question,
        "route_plan": [],
        "planner_mode": "unknown",
        "planner_debug": {},
        "agent_results": [],
        "traces": [],
        "final_answer": "",
    }
    final_state = app.invoke(initial_state)
    return {
        "question": question,
        "answer": final_state.get("final_answer", ""),
        "planner_mode": final_state.get("planner_mode", "unknown"),
        "planner_debug": final_state.get("planner_debug", {}),
        "plan": final_state.get("route_plan", []),
        "agent_results": final_state.get("agent_results", []),
        "traces": final_state.get("traces", []),
    }
