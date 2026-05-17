"""Shared schemas for CSV specialist agents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTrace(BaseModel):
    """Execution trace captured for a specialist agent."""

    agent_name: str
    routed_reason: str = Field(default="")
    query_used: str = Field(default="")
    sql_executed: str = Field(default="")
    rows_scanned: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Normalized response emitted by each specialist agent."""

    agent_name: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    trace: AgentTrace
