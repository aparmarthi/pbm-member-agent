"""Serving surface (FastAPI + Streamlit) and eval-suite regression gates."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from src.evaluation.harness import eval_conversations, eval_groundedness
from src.graph.build import build_graph
from src.serving.app import app

_REPO = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_session_round_trip_keeps_context():
    sid = client.post("/sessions", json={"scenario": "single_patient_mixed_statuses"}).json()[
        "session_id"]
    first = client.post(f"/sessions/{sid}/messages", json={"text": "where is my order"}).json()
    assert first["intent"] == "order_status" and first["has_more"] is True
    second = client.post(f"/sessions/{sid}/messages", json={"text": "see more"}).json()
    assert "next 2" in second["reply"]


def test_unknown_scenario_and_session_are_rejected():
    assert client.post("/sessions", json={"scenario": "nope"}).status_code == 422
    assert client.post("/sessions/missing/messages", json={"text": "hi"}).status_code == 404
    assert client.post("/sessions", json={"channel": "fax"}).status_code == 422


def test_streamlit_dashboard_chats():
    at = AppTest.from_file(str(_REPO / "src/serving/dashboard.py")).run()
    at.chat_input[0].set_value("where is my order").run()
    assert not at.exception
    assert any("last 45 days" in m.markdown[0].value for m in at.chat_message)


def test_groundedness_suite_is_perfect():
    metrics, failures = eval_groundedness(build_graph(), [])
    assert metrics["groundedness"] == 1.0, failures


def test_conversation_suite_completes():
    metrics, failures = eval_conversations([])
    assert metrics["task_completion_rate"] == 1.0, failures
