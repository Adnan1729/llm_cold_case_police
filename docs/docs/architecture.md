# Architecture and Design Decisions

This document records the architectural choices made for the POC and
the reasoning behind each. Decisions are grouped by concern. For each,
the format is: **decision**, then **rationale**, then (where relevant)
**alternatives considered** and **trade-offs accepted**.

The aim is that any future contributor can read this document and
understand *why* the system looks the way it does, not just what it
does. Several of these decisions are load-bearing; changing them
without understanding the reasoning will likely break things subtly.

---

## 1. Model provenance and serving

**Decision**: open-weights models only, served via Ollama.

**Rationale**:
- Sensitivity. Real cold-case data cannot leave institutional
  infrastructure. Hosted APIs (OpenAI, Anthropic, Google) are
  unacceptable for any future real-data work.
- Reproducibility. Frontier closed models change behaviour without
  notice; results obtained in March may be irreproducible by July.
  Open weights are versioned, immutable artefacts.
- Cost. There is no API budget for the PhD project.
- Eddie deployment. Edinburgh's Eddie HPC is the long-term target
  compute platform; it supports Ollama natively.

**Alternatives**: Azure for Research credits, AWS Activate, OpenAI
research grants. All deferred until the open-weights approach is
demonstrably inadequate.

**Trade-off accepted**: open-weights models are a generation behind
frontier closed models. Whether the consortium architecture can make
8B-32B open models competitive on this task is itself one of the
research questions.

---

## 2. Compute platform

**Decision**: Eddie HPC for production; local CPU for development.

**Rationale**:
- Eddie is the available institutional resource. Mid-size open models
  (7B-32B) fit comfortably on Eddie's A100/V100 nodes.
- Local CPU development with `llama3.2:3b` lets the entire pipeline be
  iterated on a laptop without queueing for GPU time.
- The pipeline is environment-agnostic: same code runs on either.

**Trade-off accepted**: Eddie queue times are unpredictable for
interactive GPU sessions. Batch SGE submission works but adds friction.

---

## 3. Output schema enforcement

**Decision**: Pydantic models with `extra="forbid"` everywhere, plus
structured-output enforcement at the LLM serving layer.

**Rationale**:
- Pydantic enforces field types, ranges, and required fields. The model
  cannot return JSON missing a field or with a field out of range
  without raising at validation time.
- `extra="forbid"` means the model cannot introduce undeclared fields.
  This catches schema drift early.
- Ollama supports JSON-schema constrained generation via the `format`
  parameter; tokens that would violate the schema are masked out during
  generation. Combined with Pydantic validation, this gives two-layer
  enforcement.

**Why this is load-bearing**: the whole pipeline relies on each LLM
call returning a well-typed object. Without structured output, every
downstream stage would need parsing and recovery logic. With it,
downstream code consumes typed objects directly.

---

## 4. The consortium architecture

**Decision**: 1 Investigator + 2 Critics (Forensic Analyst, Devil's
Advocate). Five-phase orchestration: generate → critique → revise →
score → aggregate.

**Rationale**:
- Three is the smallest count that avoids the failure modes of 1v1
  debates (premature convergence or stalemate) while keeping the
  consortium small enough to reason about.
- Specialised roles ensure the critique perspective is genuinely
  different from the generation perspective. Forensic Analyst is
  primed to scrutinise evidence handling and forensic chain; Devil's
  Advocate is primed to surface alternative explanations and
  confirmation-bias risks.
- Phased orchestration is deterministic and testable. Each phase is
  one structured LLM call per relevant agent.

**Why phased rather than free debate**:
- The phased version is the baseline against which to compare
  alternative orchestration strategies (AutoGen, LangGraph, CrewAI).
- Free debate produces transcripts that need a separate structured-
  extraction pass — more LLM calls, more places to fail.
- A deterministic baseline is required for reproducibility.

**AutoGen is the intended swap-in**, not phased orchestration as the
end state. The orchestrator is a clean swap point (abstract base class
`ConsortiumOrchestrator`); implementing `AutoGenOrchestrator` is on the
near-term roadmap.

---

## 5. The CEG generation pipeline

**Decision**: two-step neurosymbolic pipeline — LLM produces an
EventTree, deterministic code converts it to a ChainEventGraph (with
cegpy AHC when applicable, fallback to direct conversion otherwise).

**Rationale and historical context**:

This decision was reached empirically across three iterations.

**Iteration 1** (early): LLM directly produced a ChainEventGraph in one
call. Failure mode: small models reliably violated probability-sum
constraints (outgoing edges from non-leaf nodes not summing to 1.0).
Retry-with-feedback didn't help; the model would produce a different
malformed graph rather than fixing the arithmetic.

**Iteration 2**: added a deterministic probability normalisation pass.
The model proposed graph structure and relative probabilities,
deterministic code normalised them to sum to 1.0. This worked
("neurosymbolic split 1"). Audit-logged as `ceg_probabilities_normalized`.
This iteration was the first one to complete end-to-end on
`cold_case_001`.

**Iteration 3** (current): split CEG generation into two stages.

- **Stage A**: LLM produces an EventTree, a *simpler* graphical
  structure (strict tree, no equivalence-class staging, no explicit
  leaf-typing).
- **Stage B**: deterministic code converts the EventTree to a CEG.
  cegpy's AHC algorithm identifies stages where it can; when AHC
  cannot operate (singleton-class case), direct 1:1 conversion is
  used as a fallback.

This is the load-bearing architectural decision of the project. Reasoning:

- The LLM's hardest job was identifying equivalence classes (which
  nodes share outgoing probability distributions). This is a
  statistical clustering task, not a narrative-reasoning task. Small
  models fail at it consistently.
- Event trees are strict trees with no equivalence-class staging. The
  schema is tighter (single root, every other node has exactly one
  parent). The validator catches more failure modes at schema time.
- The conversion is deterministic. cegpy's AHC, where it engages, does
  the equivalence-class identification a statistician would have done
  by hand. Where AHC has nothing to merge (every situation in its own
  singleton class), direct conversion gives the same result it would
  have given if it could.

**Empirical observation from the first cegpy-pipeline run**: the
LLM still produced numerically incoherent probabilities (one node's
outgoing edges summed to 1.6, another to 0.4). These were repaired
deterministically without an LLM round-trip. So we now have *two
neurosymbolic splits*: structural (tree generation) and numerical
(probability normalisation).

**Why cegpy, not stagedtrees or hand-rolled clustering**: cegpy is the
canonical Python implementation of CEG learning, written by domain
statisticians (Walley, Shenvi, Strong, Kobalczyk; Warwick/Turing). Its
AHC algorithm is the academically standard approach. Using it means
the stage-identification step is the one the CEG literature would
endorse.

**cegpy quirk worth knowing**: cegpy crashes on `max() of empty
sequence` when every situation is in a singleton hyperstage class.
This is a real bug in cegpy 1.0.x. We catch the specific exception and
fall through to direct conversion. The fallback rate is itself an
audit-logged metric (`ceg_ahc_fallback_triggered`).

---

## 6. Two-layer retry with feedback

**Decision**: every LLM call has retry-on-validation-failure with the
validation errors fed back to the model as conversation history.

**Layer 1** (inside `OllamaClient.chat_structured`): JSON-parse errors
and Pydantic schema validation errors. One retry by default.

**Layer 2** (in `generate_ceg`): structural validation errors that
Pydantic can't enforce — tree shape, reachability, probability sums.
Two retries by default. The failed object plus the validator's problem
list are appended as conversation history before the retry.

**Rationale**:
- Pydantic catches different errors than structural validators. Each
  needs its own retry semantics.
- Feeding errors back to the model often works for syntactic problems
  ("missing field X") but unreliably for arithmetic problems ("these
  numbers must sum to 1.0"). The latter is what motivated the
  neurosymbolic normalisation pass.

**Audit-logged events** distinguishing the layers:
- `llm_retry` — Layer 1.
- `event_tree_validation_failed`, `event_tree_retry_succeeded` — Layer 2.

---

## 7. Deterministic repair before final validation

**Decision**: between the LLM call and the structural validator, a
deterministic repair pass attempts to fix recoverable structural issues
(orphaned nodes, DAG-but-not-tree shapes, probability sums).

**Rationale**: 3B-class models produce "close to a tree" structures —
sometimes a DAG where N3 has two parents, sometimes orphaned subgraphs
the model invented and forgot to wire up. These are mechanically
fixable. Forcing the LLM to fix them via retry wastes inference budget
and often doesn't converge.

**The three repairs, in order**:
1. **Orphan removal**: drop nodes unreachable from the root, and their
   edges.
2. **DAG-to-tree expansion**: when a node has multiple parents,
   duplicate the node and its subtree once per incoming edge. Each
   duplicate has a unique parent. Result: a strict tree. cegpy may
   merge the duplicates back if their distributions are equivalent.
3. **Probability normalisation**: scale outgoing probabilities to sum
   to 1.0 at each non-leaf node.

A safety cap (`max_expanded_nodes=200`) prevents pathological
expansion. If the cap would be exceeded, expansion is skipped and the
validator's retry mechanism takes over.

The repair report is audit-logged (`event_tree_repaired`). This means
the audit trail preserves exactly what the LLM produced versus what
deterministic code fixed.

---

## 8. Hallucination defence

**Decision**: every evidence reference must use an evidence ID, and
validators check that referenced IDs exist in the case.

**Implementation**:
- `Hypothesis.evidence_support` is a list of `EvidenceSupport` objects,
  each carrying an `evidence_id` (e.g. "E003"), a role
  (supports/contradicts/neutral), and a weight.
- `validate_evidence_grounding` cross-checks all referenced IDs against
  the case's evidence list.
- Same for CEG nodes and edges.

**What this catches**: the worst hallucination — the model fabricating
a piece of evidence wholesale. With grounding validation, the model
cannot reference "E999" if no such evidence exists; it can be told it
hallucinated and asked to retry.

**What this does NOT catch**: subtler failures where the model
references real evidence but misinterprets what it says, or implies
a connection between real items that isn't warranted. These remain
open problems and motivate the consortium architecture (the critics
should flag overreach).

**Observed limitation from runs to date**: the validator catches
"unknown evidence ID" but does not catch "cited but semantically
unrelated evidence." For example, node N2 labelled "Outcome: Sinclair
is the killer" associated with E008 (the restaurant manager statement
that *exculpates* Sinclair). The model cited real evidence; the
citation just didn't support the claim. This is a semantic-grounding
problem requiring either an LLM-as-judge pass or a per-claim
entailment check. Identified as future work.

---

## 9. Audit logging

**Decision**: every pipeline run produces a structured `events.jsonl`
file recording every LLM call, retry, validation outcome, and
deterministic repair. Full bad LLM outputs are saved as separate
artefacts under `errors/`.

**Rationale**:
- A POC is research, not just software. Every run must be reproducible
  and inspectable after the fact.
- Metrics for the eventual paper (validation failure rates, retry
  success rates, normalisation frequencies) require structured event
  data, not just aggregate counts.
- Failed LLM outputs are themselves data; saving them lets us
  characterise failure modes precisely rather than impressionistically.

**The `RunLogger` is held in a `contextvars`-scoped active reference**,
so downstream code (OllamaClient, ceg_stage) can log without an
explicit logger being threaded through every call.

**Event types** currently emitted:
- `run_start`, `run_end`
- `stage_start`, `stage_end`, `stage_error`
- `llm_call`, `llm_retry`
- `event_tree_validation_failed`, `event_tree_retry_succeeded`
- `event_tree_repaired`
- `ceg_conversion_completed`
- `ceg_probabilities_normalized`
- `ceg_ahc_fallback_triggered`

---

## 10. Synthetic data for the POC

**Decision**: a single synthetic toy case (`cold_case_001`) is used
for all development and current evaluation. Real data is deferred until
after ethics approval.

**Rationale**:
- Ethics approval for real police data is a multi-month process. The
  POC needs to iterate fast.
- A synthetic case with a designed-in intended answer (recorded in
  `ground_truth.md`, not shown to the consortium) permits evaluation
  without ground-truth uncertainty.
- The case (Carnaden Antiques Shop Killing) is constructed to test
  specific reasoning capabilities: cross-evidence reasoning (Thomson
  CCTV vs witness statement), surface-suspect rejection (Sinclair has
  clear motive but solid alibi), red herrings (E011 partial print
  matches no one).

**Trade-off accepted**: results on a synthetic case don't generalise
without further validation. A benchmark of multiple synthetic cases
is on the medium-term roadmap, followed eventually by real-data trials
under ethics approval.

---

## 11. Modular swap points

**Decision**: every component is behind an abstract base class so it
can be swapped without touching unrelated code.

**Swap points**:
- `LLMClient` — `MockClient` for tests, `OllamaClient` for real runs.
  Adding a new provider (vLLM, hosted API) means writing one class.
- `ConsortiumOrchestrator` — `PhasedOrchestrator` currently;
  `AutoGenOrchestrator` planned.
- `Agent` is dataclass; agent count and roles are config-driven, not
  code-driven.
- `RankingAggregator` (`AggregatorFn` type) — weighted mean is the
  default; alternative aggregators (median, trimmed mean, Bayesian)
  plug in behind the same interface.

**Why this matters**: the research questions the POC addresses
(consortium size, model heterogeneity, orchestration strategy
comparison) are *parameter sweeps* over these swap points. Making them
swap-points up front means the experiments are config edits, not code
rewrites.

---

## 12. What is deliberately not in the POC

To avoid scope creep, these are out:

- **Multimodal preprocessing** (PDFs, OCR, vision-LM, ASR). Deferred
  to a separate preprocessing layer that produces the same structured
  text the current ingestion stage consumes. Not on the critical path.
- **Investigator-facing UI**. There's a Gradio stub; not load-bearing
  for any current research question.
- **Operational deployment design** (secure enclave, audit retention
  policy, disclosure framework). Required for real-data work but not
  for the POC.
- **Real-time inference**. Pipeline takes 15-20 minutes per case on
  laptop CPU, faster on Eddie. Operational tools would need very
  different latency characteristics.
- **Active learning / human-in-the-loop**. Each run is currently a
  one-shot pipeline. Adding investigator feedback into the loop is a
  research project in its own right.