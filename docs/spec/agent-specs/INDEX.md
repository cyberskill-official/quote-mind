# QuoteMind Agent Behavior Specification Pack — Index

**Pack ID:** QM-AGT-PACK · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6
**Purpose:** Per-agent spec sheets for per-feature context loading in Claude Cowork. When implementing an agent, load ONLY: the parent spec sections it names, this pack's one relevant sheet, and QM-REPO-001 §4 (module contracts). Do not load all eight sheets at once.

| Sheet | Agent | Model | Character in one line |
|---|---|---|---|
| AGT-01_Orchestrator.md | Orchestrator (Planner) | qwen3-max + PlanNotebook | Conducts; never computes, never approves |
| AGT-02_IntakeClassifier.md | IntakeClassifier | qwen-plus | Cheap single-pass triage; never invents customers |
| AGT-03_DocumentParser.md | DocumentParser | qwen-vl-ocr / qwen-plus | Extracts faithfully; never guesses quantities |
| AGT-04_CatalogMatcher.md | CatalogMatcher | embed-v4 + qwen3-max | Chooses only from retrieved candidates; price-blind |
| AGT-05_PricingEngine.md | PricingEngine | none (deterministic) | The AI never touches your money |
| AGT-06_QuoteDrafter.md | QuoteDrafter | qwen3-max | Writes the words around read-only numbers |
| AGT-07_CriticValidator.md | CriticValidator | code + qwen3-max | Recomputes everything; LLM cannot override code verdicts |
| AGT-08_DispatchAgent.md | DispatchAgent | code + qwen3-max slot | Renders, stores, sends, remembers; exactly once |

Shared conventions across all sheets: prompts live in src/quotemind/prompts/ with versioned headers; guardrails are code-enforced (middleware, set-membership, checksums), never prompt-only; every agent emits invoke_agent spans and a <=120-token trace summary; failure codes map to TASK-113 taxonomy.
