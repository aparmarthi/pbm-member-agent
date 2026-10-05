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
