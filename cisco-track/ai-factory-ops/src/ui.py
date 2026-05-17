"""Minimal Streamlit demo UI for AI Factory Ops."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data import get_con, list_scenarios
from src.features import extract_features, summarize_top_signals
from src.graph import build_scenario_graph
from src.recommend import build_recommendation
from src.rules import rank_candidates
from src.runbooks import parse_runbooks, retrieve_best_runbook


def _timeseries_for_scenario(scenario_id: str, track: str) -> dict[str, pd.DataFrame]:
    con = get_con()
    try:
        if track == "performance_advisor":
            latency = con.execute(
                """
                SELECT timestamp, latency_ms, queue_wait_ms
                FROM scenario_requests
                WHERE scenario_id = ?
                ORDER BY timestamp
                """,
                [scenario_id],
            ).df()
            replicas = con.execute(
                """
                SELECT timestamp, queued_requests, kv_cache_used_gb
                FROM scenario_serving_replicas
                WHERE scenario_id = ?
                ORDER BY timestamp
                """,
                [scenario_id],
            ).df()
            return {"requests": latency, "replicas": replicas}

        if track == "gpu_placement":
            placement = con.execute(
                """
                SELECT timestamp, stranded_gpus, queued_large_jobs, queued_high_priority_jobs
                FROM scenario_placement_snapshots
                WHERE scenario_id = ?
                ORDER BY timestamp
                """,
                [scenario_id],
            ).df()
            queue = con.execute(
                """
                SELECT submitted_at, queue_wait_min, requested_gpus
                FROM scenario_job_queue
                WHERE scenario_id = ?
                ORDER BY submitted_at
                """,
                [scenario_id],
            ).df()
            return {"placement": placement, "queue": queue}

        storage = con.execute(
            """
            SELECT timestamp, p95_latency_ms, timeout_count
            FROM scenario_storage_metrics
            WHERE scenario_id = ?
            ORDER BY timestamp
            """,
            [scenario_id],
        ).df()
        alerts = con.execute(
            """
            SELECT timestamp, severity
            FROM scenario_alerts
            WHERE scenario_id = ?
            ORDER BY timestamp
            """,
            [scenario_id],
        ).df()
        if not alerts.empty:
            alerts["critical"] = (alerts["severity"] == "critical").astype(int)
        return {"storage": storage, "alerts": alerts}
    finally:
        con.close()


def _node_positions(nodes: list[dict]) -> dict[str, tuple[float, float]]:
    """Build deterministic radial positions grouped by node type."""
    by_type: dict[str, list[dict]] = {}
    for node in nodes:
        by_type.setdefault(str(node.get("type", "Other")), []).append(node)

    order = ["Scenario", "Focus", "Model", "Node", "Rack", "Job", "Alert"]
    radius_by_type = {
        "Scenario": 0.0,
        "Focus": 0.35,
        "Model": 0.75,
        "Node": 1.15,
        "Rack": 1.55,
        "Job": 1.95,
        "Alert": 2.35,
    }

    positions: dict[str, tuple[float, float]] = {}
    for node_type in order + [t for t in by_type.keys() if t not in order]:
        group = by_type.get(node_type, [])
        if not group:
            continue
        radius = radius_by_type.get(node_type, 2.6)
        n = len(group)
        for idx, node in enumerate(group):
            angle = (2 * math.pi * idx / max(n, 1)) + (0.15 * radius)
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            positions[str(node["id"])] = (x, y)
    return positions


def _render_graph(graph_payload: dict[str, object]) -> go.Figure:
    nodes = graph_payload.get("nodes", [])
    edges = graph_payload.get("edges", [])
    positions = _node_positions(nodes)

    edge_x: list[float] = []
    edge_y: list[float] = []
    for edge in edges:
        src = str(edge["source"])
        dst = str(edge["target"])
        if src not in positions or dst not in positions:
            continue
        x0, y0 = positions[src]
        x1, y1 = positions[dst]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line={"width": 1, "color": "#B0BEC5"},
        hoverinfo="none",
        name="relationships",
    )

    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_color: list[str] = []
    node_size: list[int] = []
    hover_text: list[str] = []

    for node in nodes:
        node_id = str(node["id"])
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        node_x.append(x)
        node_y.append(y)
        label = str(node.get("label", node_id))
        node_type = str(node.get("type", "unknown"))
        node_text.append(label)
        node_color.append(str(node.get("color", "#607D8B")))
        node_size.append(int(node.get("size", 18)))
        hover_text.append(f"{label}<br>type={node_type}<br>id={node_id}")

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        hovertext=hover_text,
        hoverinfo="text",
        marker={
            "size": node_size,
            "color": node_color,
            "line": {"width": 1, "color": "#ECEFF1"},
        },
        name="entities",
    )

    figure = go.Figure(data=[edge_trace, node_trace])
    figure.update_layout(
        title="Scenario Graph Explorer",
        showlegend=False,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        xaxis={"showgrid": False, "zeroline": False, "visible": False},
        yaxis={"showgrid": False, "zeroline": False, "visible": False},
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=560,
    )
    return figure


def run_ui() -> None:
    st.set_page_config(page_title="AI Factory Ops", layout="wide")
    st.title("AI Factory Ops — Recommendation Demo")

    scenarios = list_scenarios()
    scenario_ids = scenarios["scenario_id"].astype(str).tolist()

    with st.sidebar:
        st.header("Controls")
        scenario_id = st.selectbox("Scenario", scenario_ids, index=0)
        no_llm = st.checkbox("Use no-LLM mode", value=True)
        st.divider()
        st.subheader("Graph filters")
        graph_view = st.radio("Graph view", ["logical", "physical"], horizontal=True)
        critical_only = st.checkbox("Critical alerts only", value=False)

    selected = scenarios[scenarios["scenario_id"] == scenario_id].iloc[0]
    track = str(selected["track_id"] if "track_id" in selected.index else "")
    focus_entity = str(selected.get("focus_entity", "unknown"))

    recommendation = build_recommendation(scenario_id, use_llm=not no_llm)
    features = extract_features(scenario_id)
    top_signals = summarize_top_signals(features)
    candidates = rank_candidates(features)
    base_candidate = candidates[0] if candidates else None

    st.subheader("What if? overrides")
    overrides: dict[str, float | int] = {}
    if track == "performance_advisor":
        current_p99 = float(features.p99_latency_ms or 0.0)
        overrides["p99_latency_ms"] = st.slider(
            "Override p99 latency (ms)",
            0.0,
            max(5000.0, current_p99 * 2),
            current_p99,
            step=100.0,
        )
        current_queue = int(features.queue_depth or 0)
        overrides["queue_depth"] = st.slider(
            "Override queue depth",
            0,
            max(200, current_queue * 2 + 1),
            current_queue,
            step=1,
        )
    elif track == "gpu_placement":
        current_frag = int(features.fragmentation_score or 0)
        overrides["fragmentation_score"] = st.slider(
            "Override fragmentation score",
            0,
            max(100, current_frag * 2 + 1),
            current_frag,
            step=1,
        )
        current_hp = int(features.pending_high_priority or 0)
        overrides["pending_high_priority"] = st.slider(
            "Override pending high-priority jobs",
            0,
            max(50, current_hp * 2 + 1),
            current_hp,
            step=1,
        )
    else:
        current_cp_to = int(features.checkpoint_timeout_count or 0)
        overrides["checkpoint_timeout_count"] = st.slider(
            "Override checkpoint timeout count",
            0,
            max(20, current_cp_to * 2 + 1),
            current_cp_to,
            step=1,
        )
        current_storage = float(features.storage_latency_p95 or 0.0)
        overrides["storage_latency_p95"] = st.slider(
            "Override storage p95 latency (ms)",
            0.0,
            max(500.0, current_storage * 2),
            current_storage,
            step=5.0,
        )

    base_values = features.model_dump()
    override_applied = any(base_values.get(k) != v for k, v in overrides.items())

    active_candidate = base_candidate
    reason_text = next(
        (e.replace("reason:", "", 1).strip() for e in recommendation.evidence if e.startswith("reason:")),
        "No reason generated.",
    )

    if override_applied:
        patched_features = features.model_copy(update=overrides)
        patched_candidates = rank_candidates(patched_features)
        if patched_candidates:
            active_candidate = patched_candidates[0]
            reason_text = (
                f"Triggered rules: {', '.join(active_candidate.triggered_rules)}. "
                f"Top signals: {'; '.join(active_candidate.supporting_signals[:3])}."
            )
            if base_candidate and base_candidate.action != active_candidate.action:
                st.info(
                    f"Recommendation changed from `{base_candidate.action}` to `{active_candidate.action}` "
                    f"because rule `{active_candidate.triggered_rules[0]}` now fires."
                )
            elif base_candidate and base_candidate.action == active_candidate.action:
                st.caption("Override applied, but top recommendation remained the same.")

    display_action = active_candidate.action if active_candidate else recommendation.recommended_action
    display_target = active_candidate.target if active_candidate else recommendation.target
    display_confidence = active_candidate.confidence if active_candidate else recommendation.confidence
    display_reason_category = active_candidate.reason_category if active_candidate else recommendation.reason_category

    col1, col2, col3 = st.columns(3)
    col1.metric("Action", display_action)
    col2.metric("Target", display_target)
    col3.metric("Confidence", f"{display_confidence:.2f}")

    st.subheader("Reason Category")
    st.write(display_reason_category)

    st.subheader("Reason")
    st.write(reason_text)

    st.subheader("Top Signals")
    for signal in top_signals:
        st.markdown(f"- {signal}")

    st.subheader("Triggered Rules")
    if active_candidate:
        for rule in active_candidate.triggered_rules:
            st.markdown(f"- `{rule}`")
    else:
        st.markdown("- none")

    if track == "failure_detective" and active_candidate:
        runbook_path = Path(__file__).resolve().parents[1] / "data" / "public" / "runbooks.md"
        sections = parse_runbooks(runbook_path)
        query_text = " ".join(
            active_candidate.triggered_rules
            + active_candidate.supporting_signals
            + [active_candidate.action, active_candidate.reason_category]
        )
        section, score = retrieve_best_runbook(query_text, sections)
        with st.expander("Runbook Excerpt", expanded=False):
            if section:
                st.write(f"**{section.title}** (score={score:.2f})")
                st.write(section.body)
            else:
                st.write("No runbook section matched.")

    st.subheader("Scenario Graph Explorer")
    graph_payload = build_scenario_graph(
        scenario_id=scenario_id,
        view_mode=graph_view,
        critical_only=critical_only,
    )
    st.plotly_chart(_render_graph(graph_payload), use_container_width=True)

    node_options = graph_payload.get("nodes", [])
    if node_options:
        option_labels = [f"{n['label']} [{n['type']}]" for n in node_options]
        selected_label = st.selectbox("Inspect graph node details", option_labels, index=0)
        selected_idx = option_labels.index(selected_label)
        selected_node = node_options[selected_idx]
        node_id = selected_node["id"]
        details = graph_payload.get("details", {}).get(node_id, selected_node.get("details", {}))
        st.json({"node_id": node_id, "label": selected_node.get("label"), "type": selected_node.get("type"), "details": details})

    st.subheader("Evidence Charts")
    ts = _timeseries_for_scenario(scenario_id, track)
    if track == "performance_advisor":
        if not ts["requests"].empty:
            st.caption("Scenario window is pre-filtered; full chart range corresponds to the anomalous window.")
            req = ts["requests"].set_index("timestamp")
            st.line_chart(req[["latency_ms", "queue_wait_ms"]])
        if not ts["replicas"].empty:
            rep = ts["replicas"].set_index("timestamp")
            st.line_chart(rep[["queued_requests", "kv_cache_used_gb"]])
    elif track == "gpu_placement":
        if not ts["placement"].empty:
            pl = ts["placement"].set_index("timestamp")
            st.line_chart(pl[["stranded_gpus", "queued_large_jobs", "queued_high_priority_jobs"]])
    else:
        if not ts["storage"].empty:
            storage = ts["storage"].set_index("timestamp")
            st.line_chart(storage[["p95_latency_ms", "timeout_count"]])
        if not ts["alerts"].empty and "critical" in ts["alerts"].columns:
            alerts = ts["alerts"].set_index("timestamp")
            st.line_chart(alerts[["critical"]])

    with st.expander("Raw Features", expanded=False):
        st.code(json.dumps(features.model_dump(), indent=2), language="json")

    st.caption(f"Track: {track} | Focus entity: {focus_entity}")


if __name__ == "__main__":
    run_ui()
