# Cold-Case LLM Consortium — POC Status

**Date:** June 11, 2026
**Time:** 02:21
**Project:** End-to-end POC: LLM consortium for cold-case hypothesis
generation and Chain Event Graph construction
**Partners:** University of Edinburgh, Police Scotland
**Status:** Pipeline running end-to-end on local hardware against open-weights model

## 1. What the POC sets out to demonstrate

The system takes a structured cold-case file and produces (a) a set of
ranked candidate hypotheses with confidence scores, and (b) a Chain Event
Graph representing the top-ranked hypothesis with branching probabilities.
The architectural ambition is that multiple LLM "agents" act as a
consortium — debating, critiquing, and scoring each other's hypotheses —
rather than relying on a single LLM's output.

The POC is **decision-support**, not decision-making. A human investigator
reviews outputs at the end of the pipeline.

## 2. Key architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Model provenance | Open-weights only (Llama, Qwen, Mistral, DeepSeek-R1) | Sovereignty for sensitive use case; no third-party data transmission |
| Compute platform | Eddie HPC for production; local CPU for development | No cloud budget; Edinburgh institutional access |
| Orchestration framework | Phased orchestrator first, AutoGen swap planned | Phased gives deterministic flow + testability; AutoGen later for "live debate" mode |
| Output structure | Pydantic schemas with `extra=forbid` enforcement | Every cross-stage contract is typed and validated |
| Hallucination defence | Evidence-ID citation required in every claim | Validated post-hoc; LLM cannot reference evidence that doesn't exist |
| LLM serving | Ollama (local server, OpenAI-compatible API) | Easy install, model swapping by config, no code changes |
| Data for POC | Synthetic cold case with designed-in ambiguity | Avoids ethics-approval issues; permits ground-truth evaluation |
| Development strategy | Mock-first, GPU-free until integration | ~80% of code can be built and tested on a laptop |
| Logging | Per-run JSONL audit log + error artefacts | Research-grade evidence trail of model behaviour |
| Multimodal inputs | Deferred to separate preprocessing layer | Keeps the LLM pipeline focused; preprocessing as future module |
| Probability constraints in CEG | Neurosymbolic: LLM proposes structure + relative probabilities, deterministic code normalises to sum to 1.0 | Pure-LLM probability arithmetic did not reliably converge across multiple iterations, even with retry-with-feedback. The model would produce a different malformed CEG rather than fixing the arithmetic. |

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
        │  Critics (×N)   ─► critique +    │
        │       │            score         │
        │       ▼                          │
        │  Investigator   ─► revises       │
        │       │                          │
        │       ▼                          │
        │  All agents    ─► score          │
        │       │                          │
        │       ▼                          │
        │  Aggregator   ─► RankedHypotheses│
        └─────────────┬────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │  Stage 2: CEG generation         │
        │                                  │
        │  Top hypothesis + evidence       │
        │           ▼                      │
        │  Reasoning model                 │
        │           ▼                      │
        │  ChainEventGraph                 │
        │           ▼                      │
        │  Structural validation +         │
        │  retry-with-feedback (2 retries) │
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

Every component is independently testable; the orchestrator and
LLM-client interfaces are abstract base classes with concrete
implementations swappable by config.

## 4. What is built and tested

- **67 unit and integration tests passing.**
- **~3,500 lines of code** across schemas, clients, orchestrators,
  pipeline stages, CEG validator/renderer, IO helpers, CLI, and audit
  logging.
- **Synthetic toy case** (`cold_case_001`): the Carnaden Antiques Shop
  Killing — 13 structured evidence items, three named suspects, a
  designer-intended primary hypothesis hidden in `ground_truth.md`.
- **Working CLI**: `consortium-run run --case <dir> --config <yaml>`
  produces all output artefacts in a timestamped run directory.
- **Two-layer retry mechanism**:
  - JSON / Pydantic-validation retry inside the LLM client.
  - Structural-validation retry around the CEG stage, with the failed
    output fed back to the model alongside the structural errors.
- **Per-run audit log** (`events.jsonl`): structured record of every LLM
  call, every retry, every validation outcome, and full bad model
  outputs preserved in `errors/` for inspection.

## 5. First end-to-end results (local CPU, llama3.2:3b)

The pipeline runs to completion on a laptop CPU (Intel Core Ultra 7 165U,
no discrete GPU) in approximately 8–12 minutes per case. All artefacts
produced. Structural integrity preserved.

**Quality observations from the first run** (these are findings, not bugs):

1. The model produced four hypotheses but ranked them *all exculpatorily*
   — three hypotheses of the form "X was not the perpetrator" and one
   identifying an unknown third party. The designed-in intended answer
   (the shop assistant) was not surfaced as a leading explanation. This
   is consistent with what one might call a "presumption of innocence"
   bias in small LLMs when given exonerating evidence; it's an
   interesting hypothesis worth testing at scale.

2. CEG generation was initially attempted as a pure-LLM task. The
   structural-retry mechanism reliably caught and corrected graph-level
   errors (orphaned roots, dangling edges, cycles, leaf-with-outgoing-edges)
   when the failed CEG and the validator's complaints were fed back to
   the model as context. **However**, across multiple iterations the
   probability-sum constraint (outgoing edges from any non-leaf node sum
   to 1.0) was not reliably fixed by retry: the model would produce a
   different structurally-broken CEG rather than corrected arithmetic.
   This pattern is consistent with the failure being at the level of
   arithmetic execution rather than constraint comprehension. The
   architectural response was to make this stage **neurosymbolic** — the
   LLM proposes graph structure and relative probabilities, deterministic
   code scales the outgoing probabilities at each non-leaf node to sum to
   exactly 1.0. The LLM's relative-probability judgement is preserved;
   the formal constraint is enforced where it belongs. The normalisation
   pass is audit-logged (event type `ceg_probabilities_normalized`), so
   the frequency of normalisation across model sizes becomes itself a
   measurable property of model competence on this task.

3. The cross-evidence reasoning required to identify the intended primary
   suspect — connecting CCTV timing with witness statement contradiction
   and financial pressure — was not performed by the 3B model. We expect
   this to be a model-size-dependent capability and a candidate hypothesis
   for the upcoming evaluation.

## 6. What this positions us to do

The pipeline is now an instrument for research questions, not just a
piece of software. Concrete questions it can address:

- How does hypothesis quality vary with model size (3B → 8B → 32B → 70B)?
- How does heterogeneity in the consortium (same model vs different
  families) affect output diversity and calibration?
- Does the consortium architecture genuinely reduce hallucination, or
  does it amplify shared biases? (Comparable to single-LLM baseline.)
- Where does CEG construction break down in terms of model capability?
  Is it a model-size threshold or a prompt-engineering ceiling?
- How does the system respond to adversarial / underdetermined cases?

## 7. Roadmap

### Near-term (next 2–4 weeks)
- Install Ollama on Eddie and run the same pipeline with mid-size models
  (7B–32B class) to test the model-size hypothesis.
- Build a small benchmark of 3–5 synthetic cases with varied structure
  and run the pipeline against each on a panel of models.
- Implement the AutoGen orchestrator (same interface, swap-in
  replacement) and compare side-by-side with the phased orchestrator on
  the same cases.

### Medium-term (next 1–3 months)
- Define evaluation metrics: top-K ranking accuracy against intended
  hypothesis, calibration of confidence scores, evidence-grounding
  rate, structural validity rate.
- Implement the multimodal preprocessing layer (PDF / OCR / vision-LM)
  as a separate module that produces the structured text the current
  ingestion stage expects.

### Longer-term (post-POC)
- Replace the synthetic case set with anonymised real cases.
- Investigator-facing UI (Gradio first; eventually a richer interface
  via Police Scotland feedback).
- Operational deployment design (secure enclave, audit requirements,
  disclosure framework).

## 8. FAQ

Common questions about the design and decisions. Grouped for skimming.

### Foundational concepts

**Q: What is an EvidenceCard, and how is it made?**

An EvidenceCard is the structured representation of one discrete piece of
evidence in a case — one witness statement, one forensic report, one
phone-record extract. It's a Pydantic model with fields for: a stable ID
(`E001`, `E002`, …), type (witness_statement, forensic_report,
digital_record, physical_evidence, financial_record, other), substantive
content, source, timestamp, location, reliability (low/medium/high plus a
justification note), and chain-of-custody note. `extra="forbid"` is set on
the schema, so the LLM cannot introduce undeclared fields or omit required
ones silently.

For the POC, EvidenceCards are authored by hand and stored as JSON in the
case directory. The fields were selected to match what's typically
available in real Police Scotland evidence packages, while being minimal
enough to populate for synthetic cases. In a scaled-up version, a
preprocessing layer would extract EvidenceCards from PDFs, transcripts,
and other source artefacts via OCR and vision-LM pipelines.

**Q: What is a Chain Event Graph (CEG)?**

A CEG is a graphical representation of an event process that extends
Bayesian networks for asymmetric, discrete-event reasoning. It represents
sequences of events as a directed acyclic graph where nodes are
"situations" (states of the world), edges are events with conditional
probabilities, and outgoing edges from any non-leaf node sum to 1.0.
"Stages" are equivalence classes of nodes that share outgoing-transition
probabilities — they're what distinguishes a CEG from a plain event tree.

In this project, the CEG is generated from the top-ranked hypothesis after
the consortium completes. It represents the hypothesis as a branching
event sequence, capturing both the path the hypothesis claims occurred
and the alternative paths the evidence does not rule out. For the POC we
use trivial staging (one node per stage); identifying true equivalence
classes is a refinement.

**Q: What does "weighted aggregation" mean here?**

Each agent in the consortium scores every hypothesis in the final phase
(a float in [0.0, 1.0]). The aggregator combines these into a single
`confidence_score` per hypothesis via a weighted mean:

  confidence(H) = Σ (weight_i · score_i) / Σ weight_i

over the agents that scored H. Per-agent `weight` comes from configuration.
For the POC all weights are 1.0 (equal influence). If empirical work shows
one agent is systematically miscalibrated, its weight is reduced via
config edit, no code change. The aggregator is a separate component with
its own tests; alternative methods (weighted median, trimmed mean,
Bayesian aggregation) plug in behind the same interface.

### Architecture decisions

**Q: Why open-weights models only?**

Three reasons. (1) **Sensitivity.** Police data cannot be transmitted to
third-party APIs without breaking governance arrangements. Open-weights
models running on Eddie can be used with sensitive data once ethics
approval is in place. (2) **Reproducibility.** Closed APIs change
behaviour without notice — a result obtained from a hosted model in March
may be irreproducible by July. Open weights are fixed versioned artefacts.
(3) **Cost and access.** No API budget; no dependence on commercial
providers' availability or pricing.

The trade-off is that open-weights models are typically a generation
behind frontier closed models. Whether the consortium architecture can
make 8B-32B open models perform competitively on this task is itself one
of the research questions the POC positions us to answer.

**Q: What orchestration frameworks are we considering, and why isn't
AutoGen implemented?**

The orchestrator is a clean swap point in the architecture (the
`ConsortiumOrchestrator` abstract base class). One implementation exists:
`PhasedOrchestrator`, which runs the consortium as five deterministic
phases (generate → critique → revise → score → aggregate), each a
structured LLM call against the relevant agent's client.

Planned alternatives:
- **AutoGenOrchestrator**: uses AutoGen's `GroupChat` for multi-turn
  free-text debate between agents, with a final structured extraction
  pass. Gives a "live debate" rather than scripted phases.
- **LangGraphOrchestrator**: graph-based explicit state machine; useful
  for more complex flows with conditional branching.
- **CrewAIOrchestrator**: task-based with role-specialised tools; better
  suited for workflows where agents call external tools.

AutoGen is deferred because: (a) the phased approach is deterministic and
testable — a clean baseline before adding async debate machinery;
(b) AutoGen v0.4+ is async, while the rest of the pipeline is sync, so
integration requires a bridge layer; (c) AutoGen produces free-text
transcripts that need a separate structured-extraction pass — more LLM
calls, more places to fail; (d) the phased version is the baseline against
which to compare AutoGen's outputs once implemented. Comparison is the
whole point.

Plan: phased first (done) → AutoGen → side-by-side comparison on the
benchmark case set.

**Q: How does the consortium "challenge and double-check" each other in
practice?**

In the phased orchestrator:

1. Investigator generates initial hypotheses with evidence citations.
2. Each critic agent reviews all hypotheses, producing a structured
   critique: strengths, weaknesses, overlooked evidence, suggested
   revisions, and an overall assessment.
3. Investigator revises hypotheses in light of every critique, addressing
   each weakness in writing or explicitly acknowledging it cannot be
   addressed.
4. All agents (including the Investigator) independently score the
   revised hypotheses, with rationale.

The "challenge" emerges from role-specialised system prompts. The Forensic
Analyst is directed to scrutinise evidence rigour and flag inconsistencies
or unaddressed evidence. The Devil's Advocate is directed to surface
alternative explanations, question assumptions about motive/opportunity/
means, and identify confirmation bias. These two viewpoints are
deliberately at tension with the Investigator's narrative-building stance.

In the AutoGen version (planned), the critique and revision phases become
multi-turn free-text debate with explicit termination conditions —
reflecting natural multi-party discussion more directly.

**Q: Why three agents in the consortium (one Investigator + two Critics)
rather than more or fewer?**

Three considerations. (1) **Role specialisation.** Different prompts give
different epistemic stances on the same evidence. (2) **Model diversity.**
At scaled-up sizes, each agent will use a different open-weights model
family (Llama / Qwen / Mistral). This is the epistemic-diversity lever:
agents trained on different distributions disagree in non-trivial ways,
which we hope reduces shared-bias errors. (3) **Minimum viable
consortium.** Three is the smallest count that gives both quorum (two
critics provide independent perspectives on the Investigator) and avoids
the 1v1 dynamic of just-two-agents debates, which tend to either converge
prematurely or stalemate.

The architecture supports any number of agents (it's a config edit).
Experiments with larger consortia (5, 7, 11) are a follow-on question.

### Engineering choices

**Q: What is "structured output" and why does it matter?**

Modern LLM-serving stacks can constrain generation at decode time to
produce JSON matching a specific schema. Ollama accepts a JSON Schema via
the `format` parameter; tokens that would violate the schema are masked
out as they're generated. Our Pydantic models produce that JSON Schema
automatically (`model.model_json_schema()`).

Without this, you have to ask the LLM to "please return JSON" and hope.
With it, the output is well-typed by construction, and our Pydantic models
validate it again on the client side as defence in depth. This is the
single biggest reliability improvement in the LLM-application stack over
the past two years. Every structured stage in the pipeline depends on it.

**Q: How does the two-layer retry mechanism work?**

Two distinct kinds of validation, each with its own retry layer.

**Layer 1 (inside the LLM client):** JSON parse errors and Pydantic
schema validation errors. If the LLM produces malformed JSON or JSON
that doesn't conform to the schema, the client appends the bad output and
the error message to the conversation and tries again (default: one
retry). This handles things like missing required fields, type mismatches,
out-of-range values.

**Layer 2 (around CEG generation):** Structural validation that Pydantic
can't enforce — graph connectivity, probability sums, leaves with outgoing
edges, cycles, dangling edge references. If a CEG passes Pydantic but
fails the structural validator, the failed CEG + structural problems are
fed back to the model for another attempt (default: two retries).

Each retry layer logs separately, so the frequency and pattern of each
failure type is measurable from the audit log.

**Q: What is evidence grounding, and how is hallucination guarded
against?**

Every claim a hypothesis makes about evidence must cite the evidence via
an `EvidenceSupport` entry referencing the evidence by ID (`E001`, `E002`,
…). The validator can post-hoc check that every cited ID exists in the
case, and that the narrative does not reference evidence IDs absent from
`evidence_support`. The same applies to CEGs: every `associated_evidence`
reference is checked against the case.

This eliminates the "model fabricated a piece of evidence wholesale"
failure mode — the most damaging hallucination for an investigative
tool. It does not eliminate softer failures (misinterpreting what real
evidence says, inferring connections between real items that aren't
warranted). Those are harder problems and partly the reason for the
consortium architecture itself — the critics are explicitly directed to
flag overreach.

**Q: Why is CEG probability normalisation not "cheating"?**

This part of the architecture is deliberately **neurosymbolic**: the
LLM does the symbolic reasoning (which events follow which, what the
branching structure should be, what the relative probabilities are);
deterministic code enforces the numerical constraint (outgoing edges
sum to 1.0). We arrived at this design empirically. Initially, CEG
generation was a pure-LLM task with retry-with-feedback. The
structural-retry mechanism worked well for graph-level errors but did
not reliably correct probability arithmetic — even when fed the exact
validation error, the 3B model tended to produce a *different* malformed
CEG rather than fixing the sum. This suggests the failure isn't a
misunderstanding of the constraint but an inability to execute the
calculation reliably.

The architectural response is to split concerns. The model retains all
the structural reasoning; the formal constraint is enforced where it
belongs — in code.

This isn't cheating because: (a) the model's relative-probability
judgement is preserved; (b) the normalisation is audit-logged
(`ceg_probabilities_normalized` events), so we can measure how often it
was needed, separately from any other metric; (c) the frequency of
normalisation across model sizes is itself a measure of model competence
on this task — a research finding, not a hidden fudge. The alternative
(require the LLM to do the arithmetic itself) would either reject many
otherwise-usable outputs or require a much larger model to be reliable.
We can directly measure that trade-off.

**Q: What does the audit log capture, and why?**

Each pipeline run produces an `events.jsonl` file with one JSON object per
event. Event types include:

- `run_start` / `run_end` — case ID, agents, success/failure, duration.
- `stage_start` / `stage_end` / `stage_error` — per-stage timing and outcome.
- `llm_call` — every LLM attempt: client, model, method, response model,
  attempt number, duration, prompt/response sizes, outcome.
- `llm_retry` — when a retry is triggered, including reason.
- `ceg_probabilities_normalized` — when the normaliser had to scale
  probabilities, including the original sum.
- `ceg_structural_validation_failed` — structural problems found in a
  CEG attempt.
- `ceg_structural_retry_succeeded` — when retry corrected the issues.

Full bad model outputs (on JSON-parse or validation failures) and
exception tracebacks are saved as separate text artefacts in `errors/` and
referenced by relative path from the events. From these events the
following can be computed across many runs: validation failure rate by
response model, retry success rate, time per stage, normalisation
frequency per model family. This is the research-grade evidence trail.

### Data, evaluation, and ops

**Q: How was the toy case designed?**

The toy case (Cold Case 001 — Carnaden Antiques Shop Killing) is a
synthetic Scottish Borders cold case constructed to exercise the
consortium's reasoning capability. It has:

- 13 evidence items spanning witness statements, forensic reports, digital
  records, physical evidence, and financial records.
- Three named persons of interest with distinct motive/means/opportunity
  profiles.
- An evidentiary structure where the surface-obvious suspect (Sinclair,
  the business partner) has the cleanest narrative motive but a robust
  three-line alibi.
- An *intended* primary suspect (Thomson, the shop assistant) identified
  by cross-referencing CCTV timing with a witness-statement contradiction,
  financial pressure, and access to keys.

The "intended" answer is documented in `ground_truth.md`, which is not
shown to the consortium. It exists purely so we can measure whether the
system reaches it. The case is designed to be solvable but not obvious —
a lazy reading leads to Sinclair; the correct reading requires
cross-referencing that we hypothesise scales with model size.

**Q: How does multimodal ingestion (PDFs, images, audio) fit into the
design?**

The current ingestion stage takes unstructured text and produces structured
EvidenceCards. Real cold-case material is multimodal — PDFs (typed or
scanned), photographs, audio, video. These will be handled by a separate
**preprocessing layer** that normalises everything into the structured-
text form the current ingestion stage already consumes:

- PDF text extraction (pdfplumber, pypdf) for born-digital documents.
- OCR (Tesseract, easyOCR) for scanned PDFs.
- Vision-language model captioning for images.
- Whisper ASR for audio.

The architectural separation means the LLM-pipeline code doesn't change
when multimodal support is added; the preprocessing layer is a pure
data-transformation module. Provenance metadata (which source file, which
page) is tracked at the preprocessing stage and threaded into the
EvidenceCard's `source` and `chain_of_custody_note` fields.

This work is deferred to post-POC because the toy case is already
structured (so it's not needed for the current research questions) and the
preprocessing layer can be developed independently of everything else.

**Q: Why Eddie HPC rather than cloud?**

The project has no cloud budget. Eddie is the available institutional
compute resource at the University of Edinburgh. It runs Ollama natively
and can host the 7-32B-class models the consortium will use for serious
evaluation.

Trade-offs: free at point of use; no third-party data egress; mid-size
open models run well on its A100/V100 GPUs; eventual real-data work needs
an institutional environment anyway. Against this: queue latency for
interactive GPU sessions; SGE-based scheduling rather than the more
familiar Slurm; no native auto-scaling.

Cloud alternatives (Azure for Research, AWS Activate) remain options if
Eddie's queue becomes a bottleneck. This is contingency, not the primary
plan.

**Q: How will the system be evaluated?**

Evaluation is the primary post-POC research workstream. The plan involves
several metrics computed across a benchmark of synthetic cases:

1. **Hypothesis ranking accuracy.** Top-K accuracy of placing the
   designer-intended hypothesis in the ranked output.
2. **Calibration of confidence scores.** Whether the system expresses
   appropriate uncertainty — Brier score, ECE, or reliability diagrams.
3. **Evidence grounding rate.** Fraction of claims properly grounded in
   cited evidence after the validator filters.
4. **CEG structural validity rate.** Fraction of CEGs that validate on
   first attempt vs needing repair or retry.
5. **Cross-model consistency.** Whether different model families in the
   consortium reach similar conclusions on the same case.
6. **Consortium vs single-LLM baseline.** Whether the consortium
   architecture meaningfully outperforms a single LLM given identical
   evidence.
7. **Human expert assessment.** Retired or serving investigators score
   outputs on a Likert scale; inter-rater reliability becomes the
   headline measure.

A benchmark of 5–10 synthetic cases of varied structure is the immediate
evaluation infrastructure to build.