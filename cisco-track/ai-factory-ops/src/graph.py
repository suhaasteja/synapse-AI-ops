"""Scenario-scoped graph builder for interactive exploration."""

from __future__ import annotations

from collections import defaultdict

from src.data import get_con


def _node_color(node_type: str) -> str:
    palette = {
        "Scenario": "#6C63FF",
        "Focus": "#9C27B0",
        "Model": "#1976D2",
        "Node": "#00897B",
        "Rack": "#5D4037",
        "Job": "#455A64",
        "Alert": "#D32F2F",
    }
    return palette.get(node_type, "#607D8B")


def _add_node(nodes: dict[str, dict], node_id: str, label: str, node_type: str, details: dict | None = None) -> None:
    if node_id in nodes:
        return
    nodes[node_id] = {
        "id": node_id,
        "label": label,
        "type": node_type,
        "color": _node_color(node_type),
        "size": 26 if node_type in {"Scenario", "Focus"} else 20,
        "details": details or {},
    }


def _add_edge(edges: dict[tuple[str, str, str], dict], source: str, target: str, relation: str, weight: float = 1.0) -> None:
    key = (source, target, relation)
    if key not in edges:
        edges[key] = {
            "source": source,
            "target": target,
            "label": relation,
            "weight": float(weight),
        }
    else:
        edges[key]["weight"] += float(weight)


def build_scenario_graph(
    scenario_id: str,
    view_mode: str = "logical",
    critical_only: bool = False,
) -> dict[str, object]:
    """Build graph payload for a single scenario."""
    con = get_con()
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}
    details: dict[str, dict] = {}

    try:
        scenario = con.execute(
            """
            SELECT scenario_id, track_id, focus_entity, start_time, end_time
            FROM evaluation_scenarios
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()
        if scenario is None:
            return {"nodes": [], "edges": [], "details": {}}

        sid, track_id, focus_entity, start_time, end_time = scenario
        scenario_node = f"scenario:{sid}"
        _add_node(
            nodes,
            scenario_node,
            sid,
            "Scenario",
            {
                "track": track_id,
                "focus_entity": focus_entity,
                "start_time": str(start_time),
                "end_time": str(end_time),
            },
        )
        details[scenario_node] = nodes[scenario_node]["details"]

        focus_type = "Focus"
        focus_lower = str(focus_entity).lower()
        if focus_lower.startswith("gpu-node"):
            focus_type = "Node"
        elif focus_lower.startswith("rack-"):
            focus_type = "Rack"
        focus_node = f"focus:{focus_entity}"
        _add_node(nodes, focus_node, str(focus_entity), focus_type, {"focus_entity": focus_entity})
        _add_edge(edges, scenario_node, focus_node, "focuses_on")

        models = con.execute(
            """
            SELECT model_name, COUNT(*) AS requests
            FROM scenario_requests
            WHERE scenario_id = ?
            GROUP BY model_name
            ORDER BY requests DESC
            LIMIT 8
            """,
            [scenario_id],
        ).fetchall()
        for model_name, requests in models:
            model_id = f"model:{model_name}"
            _add_node(nodes, model_id, str(model_name), "Model", {"requests": int(requests)})
            details[model_id] = {"model_name": model_name, "requests": int(requests)}
            _add_edge(edges, scenario_node, model_id, "observes_model", weight=float(requests))

        served_pairs = con.execute(
            """
            SELECT model_name, gpu_node_id, COUNT(*) AS traffic
            FROM scenario_requests
            WHERE scenario_id = ? AND model_name IS NOT NULL AND gpu_node_id IS NOT NULL
            GROUP BY model_name, gpu_node_id
            ORDER BY traffic DESC
            LIMIT 24
            """,
            [scenario_id],
        ).fetchall()
        for model_name, gpu_node_id, traffic in served_pairs:
            model_id = f"model:{model_name}"
            node_id = f"node:{gpu_node_id}"
            _add_node(nodes, node_id, str(gpu_node_id), "Node", {"traffic": int(traffic)})
            details[node_id] = {"node_id": gpu_node_id, "traffic": int(traffic)}
            _add_edge(edges, model_id, node_id, "served_on", weight=float(traffic))

        node_racks = con.execute(
            """
            SELECT node_id, rack_id
            FROM scenario_node_metrics
            WHERE scenario_id = ?
            GROUP BY node_id, rack_id
            """,
            [scenario_id],
        ).fetchall()
        for node_id_raw, rack_id in node_racks:
            if node_id_raw is None or rack_id is None:
                continue
            node_id = f"node:{node_id_raw}"
            rack_node = f"rack:{rack_id}"
            _add_node(nodes, node_id, str(node_id_raw), "Node")
            _add_node(nodes, rack_node, str(rack_id), "Rack")
            details.setdefault(rack_node, {"rack_id": rack_id})
            _add_edge(edges, node_id, rack_node, "part_of")

        alert_where = "AND severity = 'critical'" if critical_only else ""
        alerts = con.execute(
            f"""
            SELECT alert_type, severity, node_id, model_name, COUNT(*) AS cnt
            FROM scenario_alerts
            WHERE scenario_id = ? {alert_where}
            GROUP BY alert_type, severity, node_id, model_name
            ORDER BY cnt DESC
            LIMIT 18
            """,
            [scenario_id],
        ).fetchall()

        alert_totals: dict[str, int] = defaultdict(int)
        for alert_type, severity, node_id_raw, model_name, cnt in alerts:
            alert_id = f"alert:{alert_type}"
            alert_totals[alert_id] += int(cnt)
            _add_node(nodes, alert_id, str(alert_type), "Alert", {"severity": severity, "count": int(cnt)})
            details[alert_id] = {"alert_type": alert_type, "severity": severity, "count": alert_totals[alert_id]}
            _add_edge(edges, scenario_node, alert_id, "has_alert", weight=float(cnt))

            if node_id_raw:
                node_id = f"node:{node_id_raw}"
                _add_node(nodes, node_id, str(node_id_raw), "Node")
                _add_edge(edges, alert_id, node_id, "raised_on", weight=float(cnt))
            if model_name:
                model_id = f"model:{model_name}"
                _add_node(nodes, model_id, str(model_name), "Model")
                _add_edge(edges, alert_id, model_id, "raised_on", weight=float(cnt))

        if view_mode == "physical":
            jobs = con.execute(
                """
                SELECT job_id, status, priority, assigned_nodes
                FROM scenario_job_queue
                WHERE scenario_id = ?
                ORDER BY submitted_at DESC
                LIMIT 14
                """,
                [scenario_id],
            ).fetchall()
            for job_id_raw, status, priority, assigned_nodes in jobs:
                if job_id_raw is None:
                    continue
                job_id = f"job:{job_id_raw}"
                _add_node(
                    nodes,
                    job_id,
                    str(job_id_raw),
                    "Job",
                    {"status": status, "priority": priority, "assigned_nodes": assigned_nodes},
                )
                details[job_id] = {"job_id": job_id_raw, "status": status, "priority": priority, "assigned_nodes": assigned_nodes}
                _add_edge(edges, scenario_node, job_id, "contains_job")

                if assigned_nodes:
                    for node_name in str(assigned_nodes).split("|"):
                        node_name = node_name.strip()
                        if not node_name:
                            continue
                        node_id = f"node:{node_name}"
                        _add_node(nodes, node_id, node_name, "Node")
                        _add_edge(edges, job_id, node_id, "assigned_to")

    finally:
        con.close()

    # Keep graph readable by trimming the least informative edges if needed.
    edge_list = sorted(edges.values(), key=lambda item: item["weight"], reverse=True)
    if len(edge_list) > 140:
        edge_list = edge_list[:140]
        keep_ids = {e["source"] for e in edge_list} | {e["target"] for e in edge_list}
        nodes = {k: v for k, v in nodes.items() if k in keep_ids}
        details = {k: v for k, v in details.items() if k in keep_ids}

    return {
        "nodes": list(nodes.values()),
        "edges": edge_list,
        "details": details,
    }
