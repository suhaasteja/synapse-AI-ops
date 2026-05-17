"""Data access helpers for AI Factory Ops."""

import os
from pathlib import Path

import duckdb
import pandas as pd


def _default_db_path() -> Path:
    """Return the default path to the provided DuckDB database."""
    env_path = os.getenv("DUCKDB_PATH", "").strip()
    if env_path:
        return Path(env_path)

    # Support both local and Render monorepo layouts.
    candidates = [
        Path(__file__).resolve().parents[1] / "ai_factory.duckdb",
        Path(__file__).resolve().parents[2] / "ai_factory_hackathon_student" / "ai_factory.duckdb",
        Path(__file__).resolve().parents[3] / "ai_factory_hackathon_student" / "ai_factory.duckdb",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def get_con(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open a read-only DuckDB connection to the AI Factory database."""
    path = Path(db_path) if db_path is not None else _default_db_path()
    if not path.exists():
        raise FileNotFoundError(f"DuckDB file not found at: {path}")
    return duckdb.connect(database=str(path), read_only=True)


def list_scenarios(db_path: str | Path | None = None) -> pd.DataFrame:
    """Return all evaluation scenarios as a pandas DataFrame."""
    con = get_con(db_path)
    try:
        return con.execute(
            """
            SELECT *
            FROM evaluation_scenarios
            ORDER BY scenario_id
            """
        ).df()
    finally:
        con.close()
