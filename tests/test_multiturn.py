"""Multi-turn behavior: follow-up offers, step-up auth, lookback windows."""

from __future__ import annotations

from datetime import date, timedelta

from src.data import synthetic
from src.graph.tools import resolve_statuses
from src.models.schemas import Channel
from src.serving.session import AgentSession


def test_see_more_pages_through_orders():
    s = AgentSession("single_patient_mixed_statuses")
    first = s.send("where is my order")
    assert first.has_more and len(first.shown) == 3
    second = s.send("see more")
    assert "next 2" in second.reply
    assert {x.drug_name for x in second.shown}.isdisjoint({x.drug_name for x in first.shown[:1]})


def test_no_declines_offer_without_llm():
    s = AgentSession("single_patient_mixed_statuses")
    s.send("where is my order")
    assert s.send("no").intent.value == "closing"


def test_prior_auth_cost_followup():
    s = AgentSession("single_patient_mixed_statuses")
    assert "prior authorization" in s.send("how much is wegovy").reply
    assert "estimated cost of Wegovy is $" in s.send("yes").reply


def test_new_drug_question_is_not_answered_with_previous_drug():
    s = AgentSession("single_patient_mixed_statuses")
    s.send("how much is lipitor")
    assert s.send("how much is synthroid").reply.startswith("Synthroid")


def test_auth_token_then_dob_replays_original_request():
    s = AgentSession("single_patient_mixed_statuses", Channel.VOICE, verified=False)
    assert s.send("where is my order").handoff_target == "pending_auth"
    assert "date of birth" in s.send(f"it's {s.member.member_id}").reply
    turn = s.send("January 1, 1988")
    assert turn.intent.value == "order_status" and turn.shown


def test_auth_fails_after_two_bad_tokens():
    s = AgentSession("family_plan", Channel.VOICE, verified=False)
    s.send("I need a refill")
    assert "couldn't find" in s.send("123456789").reply
    turn = s.send("000000000")
    assert turn.escalated and turn.handoff_target == "live_agent"


def test_wrong_dob_reprompts_then_transfers():
    s = AgentSession("payment_hold", Channel.VOICE, verified=False)
    s.send("where is my order")
    s.send(s.member.member_id)
    assert "doesn't match" in s.send("1970-03-03").reply
    assert s.send("1970-03-04").escalated


def test_crisis_mid_auth_still_gets_988():
    s = AgentSession("single_patient_mixed_statuses", Channel.VOICE, verified=False)
    s.send("where is my order")
    turn = s.send("I want to end my life")
    assert turn.escalated and "988" in turn.reply


def test_voice_window_is_narrower_than_chat():
    member = synthetic.build("single_patient_mixed_statuses")
    chat = resolve_statuses(member, Channel.CHAT)
    voice = resolve_statuses(member, Channel.VOICE)
    assert len(chat) == 5 and len(voice) == 4  # 25-day-old delivery outside voice's 10 days


def test_window_is_relative_to_as_of():
    member = synthetic.build("single_patient_mixed_statuses")
    far_future = date.today() + timedelta(days=365)
    assert resolve_statuses(member, Channel.CHAT, as_of=far_future) == []


def test_chat_offers_six_month_search_then_finds_older_orders():
    s = AgentSession("older_orders_only")
    assert "last 6 months?" in s.send("where's my order").reply
    turn = s.send("yes")
    assert "last 6 months" in turn.reply and len(turn.shown) == 2


def test_rc14_reply_does_not_ask_anything_else():
    turn = AgentSession("escalation_required").send("where is my order")
    assert turn.escalated and "anything else" not in turn.reply


def test_held_rx_is_not_offered_for_refill():
    turn = AgentSession("escalation_required").send("refill please")
    assert turn.escalated and "you can order" not in turn.reply


def test_singular_pagination_copy():
    s = AgentSession("single_patient_mixed_statuses", Channel.VOICE)
    assert "hear the other one?" in s.send("where is my order").reply
    assert "Here's the other one:" in s.send("yes").reply
