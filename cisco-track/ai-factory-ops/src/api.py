"""FastAPI interface for orchestrated CSV-agent chat."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .orchestrator import run_orchestrated_query


class ChatRequest(BaseModel):
    """Incoming chat request payload."""

    question: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """Outgoing chat response with traces and chart suggestions for UI."""

    question: str
    answer: str
    planner_mode: str
    planner_debug: dict
    chart_debug: dict
    plan: list[dict]
    agent_results: list[dict]
    traces: list[dict]
    chart_suggestions: list[dict]


app = FastAPI(title="AI Factory Ops Orchestrator API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Basic health endpoint for UI/backend checks."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """Run orchestrator over user query and return answer + traces."""
    result = run_orchestrated_query(payload.question)
    return ChatResponse(**result)
