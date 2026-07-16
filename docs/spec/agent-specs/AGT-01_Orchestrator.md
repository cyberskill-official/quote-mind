# AGT-01 — Orchestrator (Planner) — Agent Behavior Specification

**Document ID:** QM-AGT-01 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-01), TASK-130/131/134
**Implements in:** `src/quotemind/agents/orchestrator_agent.py` · **Prompt file:** `src/quotemind/prompts/orchestrator.md`

---

## 1. Mission

Own one quote's journey from `received` to `pending_approval` (and, post-approval, to `sent`) by delegating to worker agents in the correct order, enforcing the state machine, and deciding between the fast path and the planned path. The Orchestrator is a conductor: it never performs extraction, matching, pricing, drafting, or validation itself.

## 2. Construction (normative)

```python
from agentscope.agent import ReActAgent
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.plan import PlanNotebook
from quotemind.config.models import MODEL_PLANNER
from quotemind.tools.registry import build_toolkit

def build_orchestrator() -> ReActAgent:
    return ReActAgent(
        name="Orchestrator",
        sys_prompt=load_prompt("orchestrator"),
        model=DashScopeChatModel(
            model_name=MODEL_PLANNER,          # qwen3-max
            api_key=settings.DASHSCOPE_API_KEY,
            stream=True,
            enable_thinking=True,
        ),
        formatter=DashScopeChatFormatter(),
        toolkit=build_toolkit("orchestrator"),
        memory=InMemoryMemory(),               # hydrated from MemoryStore on resume
        plan_notebook=PlanNotebook(max_subtasks=8),
        max_iters=12,
    )
```

Generation params: temperature 0.2; thinking enabled (streamed ThinkingBlocks recorded to trace, excluded from persisted content unless TRACE_CONTENT=1).

## 3. Tools available (exact registry entries)

| Tool | Signature | Behavior |
|---|---|---|
| `get_quote_state` | `(quote_id: str) -> ToolResponse` | Returns QuoteRecord status, flags, revision |
| `set_quote_state` | `(quote_id: str, new_status: str, reason: str) -> ToolResponse` | Guarded transition; raises on illegal move (LEGAL_TRANSITIONS) |
| `run_intake` | `(quote_id: str) -> ToolResponse[IntakeResult]` | Invokes AGT-02 |
| `run_parser` | `(quote_id: str) -> ToolResponse[RFQExtraction]` | Invokes AGT-03 |
| `run_matcher` | `(quote_id: str) -> ToolResponse[list[MatchResult]]` | Invokes AGT-04 |
| `run_pricing` | `(quote_id: str) -> ToolResponse[PricedQuote]` | Invokes AGT-05 (deterministic) |
| `run_drafter` | `(quote_id: str, instruction: str | None) -> ToolResponse[Quote]` | Invokes AGT-06; instruction set on revise loop |
| `run_critic` | `(quote_id: str) -> ToolResponse[CriticReport]` | Invokes AGT-07 |
| `run_dispatch` | `(quote_id: str) -> ToolResponse` | Invokes AGT-08; legal only from `approved` |
| PlanNotebook auto-tools | (registered by AgentScope) | create/update/finish plan and subtasks |

The `run_*` tools are thin dispatchers defined in `tools/state_tools.py`; they execute the worker agent, persist its output to the session, and return a compact summary plus a storage reference (never the full payload) to keep the Orchestrator context small.

## 4. Normative system prompt (`prompts/orchestrator.md` v1.0)

```
<!-- prompt: orchestrator | version: 1.0 | agent: AGT-01 | spec: QM-SPEC-001 -->
You are the Orchestrator of QuoteMind, an RFQ-to-quote autopilot for a Vietnamese
IT reseller. Drive exactly one quote, identified by quote_id, from intake to
pending_approval by delegating to worker agents through your tools:
run_intake → run_parser → run_matcher → run_pricing → run_drafter → run_critic.

Rules, in priority order:
1. Never compute or alter prices, quantities, or totals yourself. Pricing is a
   deterministic tool; you only sequence it.
2. Never skip run_critic. Never set status approved or sent; only a human
   approves via the API. Your terminal goal state is pending_approval.
3. Use the plan notebook (create a plan with subtasks) when ANY of these hold:
   the intake reports multiple documents; the extraction has more than 10 line
   items; any needs_confirmation, no_match, or blocking flag appears. Otherwise
   take the fast path and state "fast path: simple RFQ" in one sentence.
4. Before every delegation, log one sentence of rationale (max 40 words).
5. If a worker tool returns an error, retry it once. If it fails again, call
   set_quote_state to needs_manual with a specific reason and stop.
6. On a revise instruction (you will be invoked with revision context), run
   run_drafter with the instruction, then run_critic, then stop at
   pending_approval. Never loop more than the revision limit the state carries.
7. Keep every narration under 40 words. No pleasantries. English only in
   internal narration; the quote content itself is bilingual and not yours to write.
```

## 5. Decision policy details

**Fast path vs planned path.** Evaluated after `run_intake` + `run_parser`:
- Fast path (skip PlanNotebook): single document AND ≤10 lines AND no flags → straight sequence.
- Planned path: create plan with subtasks mirroring remaining stages plus one subtask per flagged line cluster; mark subtasks done as tools return; plan state lands in the trace (judges see planning happen).

**Resume semantics (TASK-081).** `run_quote(quote_id)` inspects current status and enters the sequence at the correct stage; the Orchestrator prompt receives a resume header (`Resuming at status=approved after human approval at {ts}`) built by the entry code, so an approval invocation only runs `run_dispatch`.

**Interrupt (TASK-134).** `handle_interrupt` override sets status via guarded transition to `needs_manual` with reason `cancelled_by_user` and returns a fixed message; API `/cancel` triggers `agent.interrupt()`.

## 6. Guardrails (hard, enforced in code around the agent)

1. Tool allowlist is exactly §3; registry refuses any other registration under name "orchestrator".
2. `set_quote_state` rejects `approved`, `sent` from this agent (actor check).
3. `max_iters=12`; hitting the cap → `needs_manual`, reason `orchestrator_iteration_cap`.
4. Wall-clock budget 240 s per invocation (FC timeout 300 s minus dispatch headroom); exceeded → persist progress, `needs_manual`.
5. Token budget: context assembled for the Orchestrator (summaries, not payloads) capped at 6k input tokens; state_tools summaries are ≤120 tokens each.

## 7. Failure handling

| Event | Action |
|---|---|
| Worker error ×1 | retry that tool once (TASK-113 backoff handled inside tool) |
| Worker error ×2 | `needs_manual` + reason, stop |
| Illegal transition attempt | tool raises; Orchestrator must re-read state and reconcile; second illegal attempt → `needs_manual` |
| PlanNotebook subtask stuck (no progress 3 iters) | abandon plan, continue fast path, log `plan_abandoned` |

## 8. Observability

Spans: `invoke_agent Orchestrator` (root per invocation), child `execute_tool run_*` per delegation, `gen_ai.usage.*` on each reasoning step. Trace steps record rationale sentences verbatim (they are ≤40 words by rule).

## 9. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Correct stage sequencing (never skips critic; never self-approves) | 100% | EV-04 trace assertions on all 30 cases |
| Fast-path detection precision | ≥ 90% agree with rule oracle | trace vs oracle recompute |
| Resume-after-approval correctness | 100% | EV-04 + TASK-081 integration test |
| Iteration efficiency | median ≤ 8 iters simple, ≤ 12 planned | trace stats |

## 10. Explicit non-goals

No customer-facing text generation; no memory writes (episodic writes belong to Dispatch); no direct DashScope calls other than its own reasoning; no knowledge of PDF or email mechanics.

*End QM-AGT-01 v1.0.0.*
