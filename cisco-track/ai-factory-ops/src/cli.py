"""CLI entrypoints for AI Factory Ops."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from .data import list_scenarios
from .eval import run_eval_suite
from .features import extract_features, summarize_top_signals
from .recommend import Recommendation, build_recommendation
from .rules import rank_candidates
from .runbooks import parse_runbooks, retrieve_best_runbook

app = typer.Typer(help="AI Factory Ops CLI")
console = Console()


def _project_root() -> Path:
    """Return the ai-factory-ops project root directory."""
    return Path(__file__).resolve().parents[1]


def _action_menu_path() -> Path:
    """Return path to action menu CSV."""
    path = _project_root() / "data" / "public" / "action_menu.csv"
    if path.exists():
        return path
    fallback = _project_root().parents[0] / "ai_factory_hackathon_student" / "data" / "public" / "action_menu.csv"
    return fallback


def _normalize_track_id(track_value: str) -> str:
    """Normalize track aliases to official track IDs."""
    mapping = {
        "perf": "performance_advisor",
        "gpu": "gpu_placement",
        "fail": "failure_detective",
    }
    return mapping.get(track_value, track_value)


def _pick_stub_action(track_id: str, actions_df: pd.DataFrame) -> str:
    """Pick a valid placeholder action for a track."""
    candidates = actions_df.loc[actions_df["track_id"] == track_id, "action_id"].astype(str).tolist()
    if not candidates:
        raise typer.BadParameter(f"No actions found for track '{track_id}'")
    if "no_action" in candidates:
        return "no_action"
    return candidates[0]


@app.callback()
def main() -> None:
    """AI Factory Ops CLI commands."""
    return None


@app.command("list-scenarios")
def list_scenarios_cmd() -> None:
    """Print all available scenarios."""
    df = list_scenarios()

    if "track" not in df.columns:
        if "track_id" in df.columns:
            df = df.assign(track=df["track_id"])
        elif "scenario_id" in df.columns:
            df = df.assign(track=df["scenario_id"].astype(str).str.split("-").str[0])

    preferred_columns = ["scenario_id", "track", "focus_entity"]
    columns = [c for c in preferred_columns if c in df.columns]
    if not columns:
        columns = list(df.columns)

    table = Table(title="Evaluation Scenarios")
    for column in columns:
        table.add_column(column)

    for _, row in df[columns].iterrows():
        table.add_row(*[str(row[col]) for col in columns])

    console.print(table)


@app.command("emit-stub")
def emit_stub_cmd(
    scenario_id: str = typer.Option(..., "--scenario-id", help="Scenario ID to emit"),
    out: Path = typer.Option(..., "--out", help="Output JSON path"),
) -> None:
    """Emit a schema-valid stub recommendation for one scenario."""
    scenarios = list_scenarios()
    selected = scenarios[scenarios["scenario_id"] == scenario_id]
    if selected.empty:
        raise typer.BadParameter(f"Unknown scenario_id: {scenario_id}")

    row = selected.iloc[0]
    raw_track = str(row["track_id"] if "track_id" in selected.columns else row.get("track", ""))
    track_id = _normalize_track_id(raw_track)

    actions_df = pd.read_csv(_action_menu_path())
    action_id = _pick_stub_action(track_id, actions_df)

    recommendation = Recommendation(
        scenario_id=scenario_id,
        recommended_action=action_id,
        target=str(row.get("focus_entity", "unknown-target")),
        reason_category="stub",
        confidence=0.0,
        evidence=["stub recommendation for format validation"],
    )
    destination = recommendation.write(out)
    console.print(f"Wrote stub recommendation: {destination}")


@app.command("extract")
def extract_cmd(
    scenario_id: str = typer.Option(..., "--scenario-id", help="Scenario ID to extract features for"),
) -> None:
    """Extract deterministic features and print top anomaly signals."""
    features = extract_features(scenario_id)
    top_signals = summarize_top_signals(features)

    feature_table = Table(title=f"Scenario Features: {scenario_id}")
    feature_table.add_column("feature")
    feature_table.add_column("value")

    for key, value in features.model_dump().items():
        feature_table.add_row(key, str(value))

    console.print(feature_table)
    console.print("[bold]Top Signals[/bold]")
    for signal in top_signals:
        console.print(f"- {signal}")


@app.command("propose")
def propose_cmd(
    scenario_id: str = typer.Option(..., "--scenario-id", help="Scenario ID to propose actions for"),
) -> None:
    """Generate ranked rule-based action candidates for a scenario."""
    features = extract_features(scenario_id)
    candidates = rank_candidates(features)

    table = Table(title=f"Candidate Actions: {scenario_id}")
    table.add_column("rank")
    table.add_column("action")
    table.add_column("target")
    table.add_column("reason_category")
    table.add_column("confidence")
    table.add_column("triggered_rules")

    for idx, candidate in enumerate(candidates, start=1):
        table.add_row(
            str(idx),
            candidate.action,
            candidate.target,
            candidate.reason_category,
            f"{candidate.confidence:.2f}",
            ", ".join(candidate.triggered_rules),
        )

    console.print(table)
    console.print("[bold]Supporting Signals[/bold]")
    for idx, candidate in enumerate(candidates, start=1):
        console.print(f"{idx}. {candidate.action}")
        for signal in candidate.supporting_signals:
            console.print(f"   - {signal}")


@app.command("runbook")
def runbook_cmd(
    scenario_id: str = typer.Option(..., "--scenario-id", help="Scenario ID to retrieve runbook for"),
) -> None:
    """Retrieve the most relevant runbook section for the top candidate."""
    features = extract_features(scenario_id)
    candidates = rank_candidates(features)
    if not candidates:
        raise typer.BadParameter(f"No candidates available for scenario_id: {scenario_id}")

    top_candidate = candidates[0]
    runbook_path = _project_root() / "data" / "public" / "runbooks.md"
    if not runbook_path.exists():
        runbook_path = _project_root().parents[0] / "ai_factory_hackathon_student" / "data" / "public" / "runbooks.md"

    sections = parse_runbooks(runbook_path)
    query_text = " ".join(
        top_candidate.triggered_rules
        + top_candidate.supporting_signals
        + [top_candidate.action, top_candidate.reason_category]
    )
    section, score = retrieve_best_runbook(query_text, sections)

    if section is None:
        console.print("No runbook section matched the current candidate.")
        return

    console.print(f"[bold]Runbook Match: {scenario_id}[/bold]")
    console.print(f"Similarity score: {score:.2f}")
    console.print(f"Section: {section.title}")
    console.print(section.body)


@app.command("recommend")
def recommend_cmd(
    scenario_id: str = typer.Option(..., "--scenario-id", help="Scenario ID to recommend for"),
    out: Path = typer.Option(..., "--out", help="Output JSON path"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM and use deterministic rationale"),
) -> None:
    """Build and write final recommendation JSON for a scenario."""
    recommendation = build_recommendation(scenario_id=scenario_id, use_llm=not no_llm)
    destination = recommendation.write(out)
    console.print(f"Wrote recommendation: {destination}")


@app.command("recommend-all")
def recommend_all_cmd(
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM and use deterministic rationale"),
) -> None:
    """Generate recommendations for every scenario and write output/all.json."""
    scenarios = list_scenarios()
    output_dir = _project_root() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    combined: list[dict] = []
    summary_rows: list[tuple[str, str, str, str]] = []

    for scenario_id in scenarios["scenario_id"].astype(str).tolist():
        recommendation = build_recommendation(scenario_id=scenario_id, use_llm=not no_llm)
        destination = recommendation.write(output_dir / f"{scenario_id}.json")
        console.print(f"Wrote recommendation: {destination}")

        payload = recommendation.model_dump()
        combined.append(payload)

        top_signal = next(
            (
                item
                for item in recommendation.evidence
                if not item.startswith("rule:")
                and not item.startswith("runbook:")
                and not item.startswith("reason:")
            ),
            recommendation.evidence[0],
        )
        summary_rows.append(
            (
                recommendation.scenario_id,
                recommendation.recommended_action,
                f"{recommendation.confidence:.2f}",
                top_signal,
            )
        )

    all_path = output_dir / "all.json"
    all_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    console.print(f"Wrote combined recommendations: {all_path}")

    table = Table(title="Batch Recommendation Summary")
    table.add_column("scenario_id")
    table.add_column("action")
    table.add_column("confidence")
    table.add_column("top_signal")
    for scenario_id, action, confidence, top_signal in summary_rows:
        table.add_row(scenario_id, action, confidence, top_signal)
    console.print(table)


@app.command("eval-agents")
def eval_agents_cmd(
    corpus: Path = typer.Option(
        Path("tests/eval_corpus.yaml"),
        "--corpus",
        help="Path to evaluation corpus YAML",
    ),
    only_id: str | None = typer.Option(
        None,
        "--only-id",
        help="Run only one evaluation case id",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop at first failing case",
    ),
) -> None:
    """Run orchestrator evaluation corpus without UI."""
    exit_code = run_eval_suite(
        corpus_path=corpus,
        only_case_id=only_id,
        fail_fast=fail_fast,
        console=console,
    )
    raise typer.Exit(code=exit_code)


@app.command("ui")
def ui_cmd() -> None:
    """Launch the Streamlit demo UI."""
    ui_file = _project_root() / "src" / "ui.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_file)], check=False)


if __name__ == "__main__":
    app()
