# pbm-member-agent

A LangGraph rebuild of a production-style **pharmacy benefit manager (PBM) member-service agent** — order status, refills, drug pricing, and safety-critical escalation — modeled on a real Agentforce deployment and re-implemented on an open stack to demonstrate end-to-end agent architecture, channel-aware design, and evaluation.

> **Clean-room / no PHI.** All member data is synthetic (`src/data/synthetic.py`). Reason codes and CX copy are drug-status configuration, not member data. No real data is committed; the data directory is gitignored defensively.

## Why this project

The reference system is a managed, low-code agent (Salesforce Agentforce). This rebuild un-blurs the three layers a managed platform fuses together, so each is explicit and testable:

| Managed concept | Here |
|---|---|
| Agent bundle | Compiled LangGraph `StateGraph` (`src/graph/build.py`) |
| Topic Selector | Crisis gate + LLM router (`src/graph/nodes/router.py`) |
| Topics / subagents | Nodes (`src/graph/nodes/`) |
| Variables | Typed `AgentState` (`src/graph/state.py`) |
| Apex / Flow actions | Plain typed tools (`src/graph/tools.py`) |
| Trust Layer moderation | Deterministic crisis gate, ordered *before* generic routing |
| Auth / step-up | `src/config/auth.py` + `auth_gate` node (Level 1.5, DOB recovery, privacy flag) |
| Order-status config | `src/config/reason_codes.py` (status truth table) |
| Refill-eligibility config | `src/config/condition_codes.py` (condition-code truth table) |

## Design principle: *LLM decides intent; code decides truth*

The LLM only classifies intent and (optionally) narrates. Order statuses are derived deterministically from the reason-code catalog and rendered by template — so output is faithful by construction, not by prompt pleading. This structurally prevents the hallucination/echo failures that plague prompt-only agents.

## Channel-aware core (the thesis)

One agent brain, channel-appropriate hands. Chat and voice share the graph but diverge by config (`src/config/channels.py`):

| | Chat | Voice |
|---|---|---|
| Lookback | 45 days (→ 6-month offer) | 10 days (30 for future fill) |
| Pagination | Top 3, "see more" | 3 at a time, "hear more" |
| Order actions | Deep-link to web CTA | Execute inline (confirm + step-up auth) |
| FastStart status | shown | suppressed |

## Safety: crisis handling done right

Self-harm/crisis intent is pinned to escalation **deterministically, before** any generic moderation — and the escalation always surfaces the **988 Suicide & Crisis Lifeline** plus a warm human handoff. This is the control a managed platform's built-in moderation layer did not guarantee; owning the graph means owning the ordering.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Scripted 8-act demo of every capability (add --pause to step through live)
python -m scripts.demo

# Interactive (uses the zero-cost mock LLM by default)
python -m src.serving.cli --scenario family_plan --channel chat
python -m src.serving.cli --scenario single_patient_mixed_statuses --channel voice

# Tests (hermetic, no API keys)
pytest -q
```

### Live LLM (optional)

Pluggable provider, selected by env var (see `.env.example`):

```bash
export LLM_PROVIDER=openrouter   # routes to Claude by default
export OPENROUTER_API_KEY=sk-or-...
# or
export LLM_PROVIDER=gemini
export GOOGLE_API_KEY=...
```

## Scenarios (synthetic)

`single_patient_mixed_statuses`, `family_plan`, `no_orders`, `escalation_required`, `payment_hold` — each mirrors a named scenario from the source requirements.

## Capabilities (built deep)

- **Order Status** — fetch → resolve → rank → paginate → render, channel-aware.
- **Refill** — condition-code eligibility engine (remaps, listing priority,
  cart-eligibility, controlled/too-old/renewal/transfer outcomes).
- **Drug Price** — coverage / prior-auth / covered-price with generic
  alternatives; never recommends a drug for a condition.
- **Authentication** — Level 1.5 step-up before PHI intents, intent-specific
  token prompts, DOB recovery, privacy-flag transfer, caller-type routing.
- **Escalation** — crisis-safe (988 + warm handoff), ordered before routing.

Both **chat and voice** run on the one graph, diverging by config.

## Status

- **Stubbed (real interfaces):** in-conversation order-action *execution*
  (payment-hold resolve, cancel, address) — chat deep-links today; voice
  inline-execute with confirmation + step-up auth is the next pass.
- **Tests:** 33 passing, hermetic (mock LLM, no keys).

See [docs/PRD.md](docs/PRD.md) and [docs/decisions.md](docs/decisions.md).
