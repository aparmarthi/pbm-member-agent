# PRD: PBM Member-Service Agent (LangGraph)

## Problem
Members contacting a pharmacy benefit manager want fast, accurate answers about
their prescription orders — where an order is, why it's delayed, how to resolve a
hold — across chat and voice. A managed low-code agent shipped this capability
but concentrated control-flow, safety, and grounding inside an opaque platform.
This project rebuilds it on an open stack to expose and own those layers.

## Users
- **Members** checking their own order status (primary).
- **Caregivers** on a family plan viewing dependents' orders (permissioned).
- **Care specialists** receiving warm handoffs on escalation.

## North Star metric
**Contained resolution rate** — share of turns that answer the member's question
correctly from grounded system data without unnecessary escalation.

## Guardrail metrics
1. **Escalation recall on crisis/complex intent** — must approach 100%. A missed
   self-harm escalation is the highest-severity failure.
2. **Groundedness** — 0% of surfaced order facts fabricated (enforced structurally).
3. **Routing accuracy** — correct intent selection, especially escalation.

## Scope (this build)
- Order Status read path, both channels, deep.
- Crisis-safe escalation with 988 + human handoff.
- Deterministic reason-code resolution, priority ranking, pagination.
- Stubs (real interfaces): refill, drug price, order actions.

## Out of scope (next passes)
- Deep order-action execution (chat web deep-link vs. voice inline execute + auth).
- Real refill / drug-price flows.
- Persistence/checkpointer, multi-turn context resolution, RAG for benefit inquiry.

## Success criteria (acceptance, from source user stories)
- Statuses presented in priority order: self-serve holds → ready → other → delivered.
- Chat states "last 45 days"; voice states "last 10 days"; voice reads 3 at a time.
- `ONHOLD_RC14` and API errors transfer to a human.
- FastStart suppressed on voice.
- No orders → offer help / refill check, never a dead end.

## Trade-offs
- **Determinism over LLM freedom** for status derivation: sacrifices conversational
  flourish for faithfulness and testability. Correct for a regulated domain.
- **Mock-first LLM**: zero-cost, hermetic evals; live providers swap in via one env var.
