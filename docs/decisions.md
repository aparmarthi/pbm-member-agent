# Decision Log

## ADR-001: LangGraph over vanilla LangChain AgentExecutor
**Decision:** Model the agent as a compiled `StateGraph`, not a ReAct
`AgentExecutor`.
**Why:** The reference agent is a deterministic state machine with LLM steps
embedded (topics, guarded transitions, imperative "if X then call action"
blocks), not an open-ended tool-picking loop. LangGraph's nodes/edges map 1:1 to
topics/transitions and keep control flow in code where it's testable. A ReAct
loop would relocate that logic into fragile prose — the root cause of several
production defects.

## ADR-002: LLM decides intent; code decides truth
**Decision:** The LLM classifies intent and optionally narrates. Order-status
derivation is 100% deterministic (reason-code catalog + template render).
**Why:** Regulated healthcare context. Faithfulness must be structural, not a
matter of prompt compliance. Eliminates the hallucination/echo failure class by
construction and makes outputs unit-testable.

## ADR-003: Crisis gate ordered before generic routing
**Decision:** A deterministic crisis gate runs *before* the LLM router and pins
self-harm intent to escalation; escalation always surfaces 988 + human handoff.
**Why:** In the reference platform, a built-in content-moderation classifier
intercepted self-harm input ahead of the customer's escalation topic and emitted
a canned refusal — a patient-safety failure the customer could not reorder.
Owning the graph means owning the ordering; we guarantee crisis intent reaches a
warm handoff. This is the strongest argument for an open stack in this domain.

## ADR-004: Channel-aware core (same brain, different hands)
**Decision:** One graph; chat/voice diverge via `ChannelConfig` data
(lookback, pagination, action fulfillment), not forked prompts or forked graphs.
**Why:** The two channels genuinely differ — chat can deep-link to an
authenticated web page for actions (lowest liability), while voice must execute
in-conversation (raising the bar: confirmation, step-up auth). Encoding the
divergence as data keeps it explicit and testable and demonstrates channel
product reasoning without duplicating the agent.

## ADR-006: Config-as-data truth tables for statuses, refills, and auth
**Decision:** Encode reason codes, refill condition codes, and auth tiers as
typed data tables (`src/config/`), not prose in prompts.
**Why:** These are large, exact, regulated mappings (~30 status codes, ~25
condition codes with remap + priority rules, tiered auth). As data they are
unit-testable, diffable, and impossible for the LLM to get wrong. This is the
same "config-as-data" pattern the reference platform used in custom metadata —
reproduced here in a form a reviewer can read and test.

## ADR-007: Auth gate as a graph node, before PHI intents
**Decision:** A deterministic `auth_gate` node runs after routing and enforces
Level 1.5 step-up before any PHI-exposing intent; the LLM never adjudicates
identity.
**Why:** Identity/PHI access is a compliance boundary, not a conversational
nicety. Making it a graph node keeps it explicit, ordered, and testable, and
lets chat (session-verified) and voice (token + DOB) share one contract.

## ADR-005: Pluggable LLM provider, mock default
**Decision:** LLM behind an interface with mock | openrouter | gemini backends;
mock is default.
**Why:** Repo clones and runs with zero keys/cost; evals stay hermetic and
CI-friendly; live Claude (via OpenRouter) or Gemini swap in with one env var,
enabling multi-model consensus evaluation later. Provider-agnostic design is an
MLE signal and costs ~30 lines.

## ADR-008: Checkpointed sessions; follow-ups resolved in code
**Decision:** The graph compiles with a LangGraph checkpointer keyed by
`thread_id` (`MemorySaver` in-process; `src/serving/session.py`). When a node
offers something ("see more", "hear the estimated cost", "check 6 months"), it
records an `offer` in state. If the next turn is a yes, no, or "more", the
router maps it straight to the follow-up without calling the LLM.
**Why:** "Yes" on its own has no intent; an LLM classifying it in isolation
routes it off-topic, and one given the full history can still pick the wrong
offer. The agent knows exactly what it offered, so resolving the follow-up is a
lookup, not a guess. This extends ADR-002 to dialogue state.
**Trade-off:** `MemorySaver` loses sessions on restart and never expires them.
A deployment would swap in a Postgres/Redis saver (same interface). A free-form
follow-up ("what about the second one?") still goes to the LLM.

## ADR-009: Identity tokens never reach the LLM
**Decision:** While auth is pending, the router skips the LLM entirely and the
auth gate consumes the utterance as a credential. Member ID or Rx number is
matched against *this member's* record, then DOB is parsed (ISO, US numeric,
or spelled out). Bounded retries end in a human transfer, and the parked
request is replayed after verification.
**Why:** Sending identifiers to a third-party model adds PHI exposure for no
benefit; matching is exact and deterministic. Replaying the original request
means the member doesn't have to repeat themselves.
**Exception:** an escalation intent (crisis or "get me a human") clears pending
auth and proceeds. This was a regression caught by the `crisis_mid_auth` eval:
a crisis utterance had been consumed as a failed credential.

## ADR-010: Lookback enforced against relative dates
**Decision:** `resolve_statuses` filters by the channel's window from an
injectable `as_of` date (chat 45 days, voice 10, future fills 30), and
synthetic order dates are generated relative to today.
**Why:** With fixed dates, the window either filtered everything out as time
passed or wasn't really being tested. Relative dates keep the voice-vs-chat
difference (4 vs 5 orders) stable and testable, and `as_of` keeps tests
deterministic.

## ADR-011: Evals as gated, versioned artifacts, not tuned against
**Decision:** `python -m evals.run` scores routing, crisis recall/false alarms,
groundedness (an independent oracle, not the renderer), and multi-turn task
completion/containment. It saves timestamped JSON and exits non-zero below
thresholds.
**Why:** Training-style unit tests prove the code does what I wrote. Evals
measure whether it does what members need, and track that across changes.
**Open finding (flagged, not yet implemented):** crisis recall is 0.60 on the
keyword gate. The keywords were deliberately *not* patched to the four misses,
since that would overfit the only measurement. Proposed architectural change:
an LLM `crisis` flag OR'd with the gate, a 988 message driven by that state
flag, and a held-out crisis set built from clinical phrasing categories.
