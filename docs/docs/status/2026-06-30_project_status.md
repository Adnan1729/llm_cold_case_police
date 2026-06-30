# Project Status — 30 June 2026

Cold-case LLM consortium POC: development snapshot following the CEG-stage
architectural refactor.

This document supersedes the 11 June status. The earlier document
describes an earlier architecture and is retained for historical
reference.

---

## 1. What the POC sets out to demonstrate

The system takes a structured cold-case file and produces (a) a set of
ranked candidate hypotheses with confidence scores, and (b) a Chain
Event Graph representing the top-ranked hypothesis with branching
probabilities. The architectural ambition is that multiple LLM "agents"
act as a consortium — debating, critiquing, and scoring each other's
hypotheses — rather than relying on a single LLM's output.

The POC is **decision-support**, not decision-making. A human
investigator reviews outputs at the end of the pipeline.

---

## 2. Key architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Model provenance | Open-weights only (Llama, Qwen, Mistral, DeepSeek-R1) | Sovereignty for sensitive use case; no third-party data transmission |
| Compute platform | Eddie HPC for production; local CPU for development | No cloud budget; Edinburgh institutional access |
| Orchestration framework | Phased orchestrator first, AutoGen swap planned | Phased gives deterministic flow + testability; AutoGen later for "live debate" mode |
| Output structure | Pydantic schemas with `extra="forbid"` enforcement | Every cross-stage contract is typed and validated |
| Hallucination defence | Evidence-ID citation required in every claim | Validated post-hoc; LLM cannot reference non-existent evidence |
| LLM serving | Ollama (local server, OpenAI-compatible API) | Easy install, model swapping by config, no code changes |
| **CEG generation pipeline** | **Two-step: LLM event tree → deterministic conversion to CEG** | **Strict tree structure simpler for LLM; equivalence-class identification handled by cegpy/fallback** |
| **Probability constraints** | **Neurosymbolic: LLM proposes relative probs, deterministic code normalises** | **3B arithmetic unreliable; retry-with-feedback does not converge** |
| **Structural repair** | **Deterministic pass between LLM output and validator** | **Orphans, multi-parent DAG shapes, prob sums are mechanically fixable without LLM round-trip** |
| Data for POC | Synthetic cold case with designed-in ambiguity | Avoids ethics-approval delay; permits ground-truth evaluation |
| Development strategy | Mock-first, GPU-free until integration | ~80% of code can be built and tested on a laptop |
| Logging | Per-run JSONL audit log + error artefacts | Research-grade evidence trail of model behaviour |
| Multimodal inputs | Deferred to separate preprocessing layer | Keeps the LLM pipeline focused; preprocessing as future module |

The four bolded rows are new since the 11 June status. They reflect
the architectural refactor of the CEG-generation stage.

---

## 3. The pipeline architecture

┌──────────────────────────────────┐
    │  Case directory                  │
    │  (case.yaml, narrative.md,       │
    │   evidence.json)                 │
    └─────────────┬────────────────────┘
                  │
                  ▼
    ┌──────────────────────────────────┐
    │  Stage 1: Consortium             │
    │                                  │
    │  Investigator   ─► generates     │
    │       │            hypotheses    │
    │       ▼                          │
    │  Critics (×N)   ─► critique      │
    │       │                          │
    │       ▼                          │
    │  Investigator   ─► revises       │
    │       │                          │
    │       ▼                          │
    │  All agents    ─► score          │
    │       │                          │
    │       ▼                          │
    │  Aggregator    ─► RankedHypotheses│
    └─────────────┬────────────────────┘
                  │
                  ▼
    ┌──────────────────────────────────┐
    │  Stage 2: CEG generation (NEW)   │
    │                                  │
    │  Top hypothesis + evidence       │
    │           ▼                      │
    │  LLM  ─► EventTree               │
    │           ▼                      │
    │  Repair pass (deterministic)     │
    │   - orphan removal               │
    │   - DAG-to-tree expansion        │
    │   - probability normalisation    │
    │           ▼                      │
    │  Structural + grounding validate │
    │           ▼                      │
    │  cegpy AHC (or fallback) ─► CEG  │
    └─────────────┬────────────────────┘
                  │
                  ▼
    ┌──────────────────────────────────┐
    │  Output artefacts (per-run)      │
    │  ranked_hypotheses.json          │
    │  ceg.json / ceg.dot / ceg.svg    │
    │  events.jsonl  (audit log)       │
    │  errors/*.txt  (artefacts)       │
    └──────────────────────────────────┘

The change since 11 June is Stage 2. The new pipeline applies the
neurosymbolic principle twice: structural (LLM produces a strict tree,
deterministic code converts to CEG) and numerical (deterministic
normalisation of probability sums).

---

## 4. What is built and tested

- **115 unit and integration tests passing.**
- **~3,500 lines of code** across schemas, clients, orchestrators,
  pipeline stages, CEG validator/renderer, EventTree validator/repair,
  EventTree-to-CEG converter, IO helpers, CLI, and audit logging.
- **Synthetic toy case** (`cold_case_001`): the Carnaden Antiques Shop
  Killing — 13 structured evidence items, three named suspects, a
  designer-intended primary hypothesis hidden in `ground_truth.md`.
- **Working CLI**: `consortium-run run --case <dir> --config <yaml>`
  produces all output artefacts in a timestamped run directory.
- **Three-layer defence**:
  - JSON / Pydantic-validation retry inside the LLM client.
  - Deterministic structural repair (orphans, DAG-to-tree,
    probability normalisation).
  - Structural-validation retry around the event tree stage, with
    the failed output fed back to the model alongside structural errors.
- **cegpy integration** with AHC engagement where applicable and a
  graceful fallback to direct 1:1 conversion when AHC has nothing to
  merge (the singleton-hyperstage case).
- **Per-run audit log** (`events.jsonl`): structured record of every
  LLM call, every retry, every validation outcome, every repair, plus
  full bad model outputs preserved in `errors/`.

---

## 5. The latest end-to-end run

A single end-to-end run was completed on 30 June 2026 using the new
architecture. Local CPU (Intel Core Ultra 7 165U), `llama3.2:3b` for
all four roles (Investigator, two Critics, CEG generator).

**Timing**: 18 minutes total (15 min consortium, 3 min CEG stage).
Down from 59 minutes in the previous architecture.

**Structural outcome**: pipeline completed end-to-end without raising.
The CEG produced is structurally valid (no orphans, no cycles,
probability sums correct, valid tree-to-CEG conversion).

**The repair pass did real work**:
- Three probability normalisations on the first attempt (N0: 0.4 → 1.0,
  N1: 1.6 → 1.0, N2: 0.9 → 1.0).
- No structural repairs needed (no orphans, no DAG shape).
- This is the first empirical demonstration that the repair pass earns
  its place: probability arithmetic is the persistent 3B failure mode.

**AHC fallback engaged**, as expected for a small tree with distinct
branching factors at each non-leaf node. The audit log records the
fallback (`ceg_ahc_fallback_triggered: true`), so this is a metric we
can track across future runs.

**Semantic quality was poor** (the 3B model's intrinsic limit):
- Consortium hallucinated a "debt collector" character not present
  anywhere in the case.
- Two pairs of hypotheses had nearly-identical summaries.
- Critic agents both returned 24-character responses — effectively
  empty `{"critiques":[]}` bundles. The schema accepts this; the
  pipeline didn't catch it.
- Final confidence scores collapsed to 0.05-0.09 across all four
  hypotheses.

**The CEG faithfully visualised the consortium's hallucination**, with
the debt-collector framing carried through. This is the cleanest
possible illustration of the structural/semantic decoupling: the
infrastructure produced valid output for invalid input.

---

## 6. The structural/semantic decoupling

The architectural refactor has produced an unanticipated and useful
property: structural correctness and semantic correctness are now
**fully decoupled** in the pipeline.

- **Structural correctness** — well-formed JSON, valid Pydantic
  objects, tree-shaped event trees, probability sums of 1.0, valid CEG
  conversion — is now handled by the infrastructure. Failure rates
  are bounded by code quality, not model quality.

- **Semantic correctness** — does the hypothesis make sense given the
  evidence, are the labels appropriate, do citations support the
  claims — depends entirely on the upstream LLM's reasoning quality.

This decoupling has two consequences for the research programme.

First, evaluation becomes cleaner. Structural validity and semantic
validity are separate metrics that can be measured separately.
Structural validity is binary and the pipeline now always achieves
it. Semantic validity is the question worth asking, and it depends on
model size, prompt quality, and consortium composition.

Second, the architectural contribution of the POC (neurosymbolic
structural enforcement) is independent of and complementary to the
model-quality question. The infrastructure works regardless of model
size; what model size buys is semantic quality, not structural
quality.

This is worth framing carefully in the eventual paper. The
contribution is not "we made small models work for CEG generation"
(they don't, semantically). The contribution is "structural
correctness is a solved problem once you split the work correctly;
the remaining problem is purely about model reasoning quality, which
is a separate research question."

---

## 7. What this positions us to do

The pipeline is now an instrument for research questions, not just a
piece of software. Concrete questions it can address:

- How does hypothesis quality vary with model size (3B → 8B → 32B → 70B)?
- How does heterogeneity in the consortium (same model vs different
  families) affect output diversity and calibration?
- Does the consortium architecture genuinely reduce hallucination, or
  does it amplify shared biases? (Comparable to a single-LLM baseline.)
- At what model size does the "exculpatory framing" bias break?
- How often does cegpy's AHC engage versus fall through? Does this
  vary with model size, as we expect?
- How frequent is the empty-critique failure mode? Does it persist at
  larger model sizes?

---

## 8. Roadmap

### Near-term (next 2–4 weeks)
- Install Ollama on Eddie and run the same pipeline with mid-size
  models (7B–32B class) to test the model-size hypothesis.
- Build a small benchmark of 3–5 synthetic cases with varied structure
  and run the pipeline against each on a panel of models.
- Decide on a fix for the empty-critique pattern (schema tightening or
  prompt strengthening), conditional on whether it recurs at mid-size.
- Implement the AutoGen orchestrator (same interface, swap-in
  replacement) and compare side-by-side with the phased orchestrator
  on the same cases.

### Medium-term (next 1–3 months)
- Define evaluation metrics: top-K ranking accuracy against intended
  hypothesis, calibration of confidence scores, evidence-grounding
  rate, structural validity rate, AHC engagement rate.
- Add a semantic-grounding validator (LLM-as-judge pass over each
  evidence association) to close the "cited but semantically
  unrelated" failure mode.
- Implement the multimodal preprocessing layer (PDF / OCR / vision-LM)
  as a separate module that produces the structured text the current
  ingestion stage expects.
- Begin ethics-approval engagement with Edinburgh and Police Scotland
  for eventual real-data trials.

### Longer-term (post-POC)
- Replace the synthetic case set with anonymised real cases.
- Investigator-facing UI (Gradio first; eventually a richer interface
  via Police Scotland feedback).
- Operational deployment design (secure enclave, audit requirements,
  disclosure framework).

---

## 9. FAQ

### Foundational concepts

**Q: What is an EvidenceCard, and how is it made?**

An EvidenceCard is the structured representation of one discrete piece
of evidence — one witness statement, one forensic report, one phone-
record extract. It's a Pydantic model with fields for: a stable ID
(`E001`, `E002`, …), type (witness_statement, forensic_report,
digital_record, physical_evidence, financial_record, other),
substantive content, source, timestamp, location, reliability
(low/medium/high with a justification note), and chain-of-custody
note. `extra="forbid"` is set, so the LLM cannot introduce undeclared
fields or omit required ones silently.

For the POC, EvidenceCards are authored by hand and stored as JSON in
the case directory. The fields were selected to match what's typically
available in real Police Scotland evidence packages, while being
minimal enough to populate for synthetic cases.

**Q: What is a Chain Event Graph (CEG)?**

A CEG is a graphical representation of an event process that extends
Bayesian networks for asymmetric, discrete-event reasoning. Developed
in the statistical literature by Jim Smith, Robert Riccomagno and
colleagues (Smith & Anderson 2008; Thwaites, Smith & Cowell 2008), it
represents sequences of events as a directed acyclic graph where
nodes are "situations" (states of the world), edges are events with
conditional probabilities, and outgoing edges from any non-leaf node
sum to 1.0. "Stages" are equivalence classes of nodes that share
outgoing-transition probabilities — they distinguish a CEG from a
plain event tree.

In this project, the CEG is generated from the top-ranked hypothesis
after the consortium completes. It represents the hypothesis as a
branching event sequence, capturing both the path the hypothesis
claims occurred and the alternative paths the evidence does not rule
out.

**Q: What is an EventTree, and why is it a separate concept?**

An EventTree is a strict tree of events — exactly one node has no
incoming edges (the root), and every other node has exactly one
incoming edge (a single parent). Compared to a CEG, an EventTree has
no equivalence-class staging, no explicit root/situation/leaf typing,
and no `leaf_node_ids` field (leaves are inferred from position).

The current pipeline asks the LLM for an EventTree, then converts it
to a CEG deterministically. The reason is empirical: small LLMs
reliably fail at the equivalence-class identification step that
distinguishes a CEG from a tree. Asking them for a simpler structure
(a tree) and handling the equivalence-class step in code is the
neurosymbolic split that makes the pipeline reliable at this scale.

### Architecture decisions

**Q: Why open-weights models only?**

Three reasons. (1) Sensitivity: police data cannot be transmitted to
third-party APIs without breaking governance arrangements. (2)
Reproducibility: closed APIs change behaviour without notice — a
result obtained from a hosted model in March may be irreproducible
by July. Open weights are fixed versioned artefacts. (3) Cost and
access: no API budget; no dependence on commercial providers'
availability.

The trade-off is that open-weights models are typically a generation
behind frontier closed models. Whether the consortium architecture
can make 8B-32B open models perform competitively is itself one of
the research questions.

**Q: Why is CEG generation split into two stages now?**

Empirically. In the original architecture the LLM directly produced
a ChainEventGraph in one call. Two persistent failure modes emerged:
the model produced probabilities that didn't sum to 1.0 at non-leaf
nodes (and retry-with-feedback didn't fix this), and it conflated
the equivalence-class staging concept with the branching structure.

Splitting the task gave the LLM the easier part — producing a strict
tree without staging — and gave deterministic code the parts the LLM
was bad at. Specifically: cegpy's AHC algorithm does the equivalence-
class identification (or, where AHC has nothing to merge, a direct
1:1 conversion gives the same result the AHC would have given). A
deterministic normalisation pass handles probability arithmetic.

This is the load-bearing architectural decision of the project.

**Q: What is cegpy and why are we using it?**

cegpy is a Python library for working with Chain Event Graphs,
developed at Warwick / Turing Institute (Walley, Shenvi, Strong,
Kobalczyk 2023). It implements the canonical AHC (Agglomerative
Hierarchical Clustering) algorithm for identifying stages in an event
tree based on similarity of conditional probability distributions.

We use it for the conversion step because it's the academically
standard implementation — using it means the equivalence-class
identification is the one CEG literature endorses. Where AHC cannot
operate (small trees with all-distinct branching factors), we fall
back to direct conversion, which gives the result AHC would have
given if it could operate.

**Q: What orchestration frameworks are we considering, and why isn't
AutoGen implemented?**

The orchestrator is a clean swap point. One implementation exists:
`PhasedOrchestrator`, which runs the consortium as five deterministic
phases.

Planned alternatives include AutoGenOrchestrator (multi-turn free-
text debate with a final structured-extraction pass) and
LangGraphOrchestrator (explicit state-machine flows).

AutoGen is deferred because: (a) phased is deterministic and testable,
providing a clean baseline; (b) AutoGen v0.4+ is async, while the
rest of the pipeline is sync, so integration requires a bridge layer;
(c) free debate produces transcripts that need a separate
structured-extraction pass — more LLM calls, more places to fail;
(d) the phased version is the baseline against which to compare
AutoGen's outputs once implemented.

### Engineering choices

**Q: What is "structured output" and why does it matter?**

Modern LLM-serving stacks can constrain generation at decode time to
produce JSON matching a specific schema. Ollama accepts a JSON Schema
via the `format` parameter; tokens that would violate the schema are
masked out as they're generated. Our Pydantic models produce that
JSON Schema automatically (`model.model_json_schema()`).

Without this, you have to ask the LLM to "please return JSON" and
hope. With it, the output is well-typed by construction, and Pydantic
validates it again on the client side as defence in depth. This is
the single biggest reliability improvement in the LLM-application
stack over the past two years.

**Q: Why is the repair pass not "cheating"?**

The repair pass is deliberately **neurosymbolic**: the LLM does the
narrative reasoning (which events follow which, what the branching
structure should be, what the relative probabilities are);
deterministic code enforces the structural constraints (tree shape,
probability sums).

We arrived at this design empirically. The model's failure mode on
probability arithmetic isn't a misunderstanding of the constraint —
it's an inability to execute the calculation reliably. Even when fed
the validation error verbatim, a 3B model produces a different
malformed output rather than fixing the arithmetic.

This isn't cheating because: (a) the model's relative-probability
judgement is preserved; (b) the repair is audit-logged, so we can
measure how often it was needed, separately from any other metric;
(c) the frequency of repair across model sizes is itself a measure
of model competence on this task — a research finding, not a hidden
fudge.

**Q: What does the audit log capture, and why?**

Each pipeline run produces an `events.jsonl` file with one JSON
object per event. Event types include `run_start`/`run_end`,
`stage_start`/`stage_end`/`stage_error`, `llm_call` (every attempt,
with timing, sizes, outcome), `llm_retry`,
`event_tree_validation_failed`, `event_tree_retry_succeeded`,
`event_tree_repaired`, `ceg_conversion_completed`,
`ceg_probabilities_normalized`, `ceg_ahc_fallback_triggered`. Full
bad model outputs (on JSON-parse or validation failures) and
exception tracebacks are saved as text artefacts in `errors/`.

From these events, the following can be computed across many runs:
validation failure rate by response model, retry success rate, time
per stage, AHC engagement rate per model family, repair frequency
per model size. This is the research-grade evidence trail for the
eventual paper.

### Data, evaluation, and ops

**Q: How was the toy case designed?**

The toy case (Cold Case 001 — Carnaden Antiques Shop Killing) is a
synthetic Scottish Borders cold case constructed to exercise the
consortium's reasoning capability. It has 13 evidence items spanning
witness statements, forensic reports, digital records, physical
evidence, and financial records; three named persons of interest
with distinct motive/means/opportunity profiles; an evidentiary
structure where the surface-obvious suspect (Sinclair) has the
cleanest narrative motive but a robust three-line alibi; and an
*intended* primary suspect (Thomson) identified by cross-referencing
CCTV timing with a witness-statement contradiction, financial
pressure, and access to keys.

The intended answer is documented in `ground_truth.md` and is not
shown to the consortium. It exists so we can measure whether the
system reaches it.

**Q: How will the system be evaluated?**

Evaluation is the primary post-POC research workstream. Metrics under
consideration: top-K hypothesis ranking accuracy, calibration of
confidence scores (Brier score, ECE), evidence-grounding rate,
structural validity rate, cross-model consistency, AHC engagement
rate, consortium-vs-single-LLM-baseline comparison, and human-expert
assessment via Likert scoring of outputs.

A benchmark of 5-10 synthetic cases of varied structure is the
immediate evaluation infrastructure to build.
