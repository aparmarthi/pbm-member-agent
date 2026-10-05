"""Streamlit demo — chat with the agent as any synthetic member, on either channel.

Run:
    streamlit run src/serving/dashboard.py

Each assistant turn shows the decisions the graph made (intent, escalation,
handoff) so a reviewer can see "LLM decides intent; code decides truth" live.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# `streamlit run` puts this file's folder on sys.path, not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import synthetic  # noqa: E402
from src.models.schemas import Channel  # noqa: E402
from src.serving.session import AgentSession  # noqa: E402

st.set_page_config(page_title="PBM Member Agent", page_icon="💊")
st.title("PBM Member Agent")
st.caption("Synthetic members only · mock LLM by default · no PHI")

with st.sidebar:
    scenario = st.selectbox("Member scenario", sorted(synthetic.SCENARIOS))
    channel = Channel(st.radio("Channel", [c.value for c in Channel], horizontal=True))
    verified = st.checkbox("Session already authenticated", value=True)
    restart = st.button("Start new conversation")

config = (scenario, channel, verified)
if restart or st.session_state.get("config") != config:
    st.session_state.config = config
    st.session_state.session = AgentSession(scenario, channel, verified=verified)
    st.session_state.history = []

session: AgentSession = st.session_state.session
if not verified:
    st.sidebar.info(f"Test credentials — member ID `{session.member.member_id}`, "
                    f"DOB `{session.member.patients[0].dob}`")

for role, text, meta in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text.replace("\n", "  \n"))
        if meta:
            st.caption(meta)

if prompt := st.chat_input("Ask about orders, refills, or drug prices"):
    turn = session.send(prompt)
    meta = (f"intent: {turn.intent.value} · escalated: {turn.escalated} · "
            f"handoff: {turn.handoff_target or '—'}")
    st.session_state.history += [("user", prompt, ""), ("assistant", turn.reply, meta)]
    st.rerun()
