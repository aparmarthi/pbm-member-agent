"""FastAPI service — the agent behind a session-based HTTP API.

Endpoints:
    GET  /health                         liveness + active LLM provider
    GET  /scenarios                      synthetic member scenarios
    POST /sessions                       start a conversation → session_id
    POST /sessions/{session_id}/messages send one member turn → AgentTurnResult

Run:
    uvicorn src.serving.app:app --reload --port 8000

Sessions live in process memory (see ``session.py``); a deployment would back
them with a persistent checkpointer and expire idle threads.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.data import synthetic
from src.models.schemas import AgentTurnResult, Channel
from src.serving.session import AgentSession

app = FastAPI(title="PBM Member Agent", version="0.2.0")
_sessions: dict[str, AgentSession] = {}


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: str
    provider: str


class SessionCreate(BaseModel):
    """Request to start a conversation."""

    scenario: str = "single_patient_mixed_statuses"
    channel: Channel = Channel.CHAT
    verified: bool = Field(default=True, description="False exercises step-up auth.")


class SessionCreated(BaseModel):
    """A started conversation."""

    session_id: str
    scenario: str
    channel: Channel
    verified: bool


class MessageIn(BaseModel):
    """One member utterance."""

    text: str = Field(min_length=1, max_length=2000)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok", provider=os.getenv("LLM_PROVIDER", "mock"))


@app.get("/scenarios", response_model=list[str])
def scenarios() -> list[str]:
    """List synthetic member scenarios a session can load."""
    return sorted(synthetic.SCENARIOS)


@app.post("/sessions", response_model=SessionCreated, status_code=201)
def create_session(body: SessionCreate) -> SessionCreated:
    """Start a conversation for a synthetic member."""
    if body.scenario not in synthetic.SCENARIOS:
        raise HTTPException(status_code=422, detail=f"Unknown scenario {body.scenario!r}")
    session = AgentSession(body.scenario, body.channel, verified=body.verified)
    _sessions[session.thread_id] = session
    return SessionCreated(session_id=session.thread_id, scenario=body.scenario,
                          channel=body.channel, verified=body.verified)


@app.post("/sessions/{session_id}/messages", response_model=AgentTurnResult)
def send_message(session_id: str, body: MessageIn) -> AgentTurnResult:
    """Send one member turn and return the agent's reply and decisions."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session.send(body.text)
