# Cold-Case LLM Consortium — POC Status

**Date:** June 11, 2026
**Time:** 02:21
**Project:** End-to-end POC: LLM consortium for cold-case hypothesis
generation and Chain Event Graph construction
**Partners:** Police Scotland, University of Edinburgh
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
| Data for POC | Synthetic cold case with designed-in ambiguity | Avoids ethics-approval delay; permits ground-truth evaluation |
| Development strategy | Mock-first, GPU-free until integration | ~80% of code can be built and tested on a laptop |
| Logging | Per-run JSONL audit log + error artefacts | Research-grade evidence trail of model behaviour |
| Multimodal inputs | Deferred to separate preprocessing layer | Keeps the LLM pipeline focused; preprocessing as future module |

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
        │       │            score          │
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

- **60 unit and integration tests passing.**
- **~3,000 lines of code** across schemas, clients, orchestrators,
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

2. The CEG generation failed structural validation on the first attempt
   (orphaned root, probability sums ≠ 1.0, leaf node with outgoing edges)
   but the structural-retry mechanism corrected it on the second attempt
   when fed the validation errors back as context. The retry mechanism
   is doing real work and that fact is captured in `events.jsonl`.

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
- Begin ethics-approval engagement with Edinburgh and Police Scotland
  for eventual real-data trials.

### Longer-term (post-POC)
- Replace the synthetic case set with anonymised real cases.
- Investigator-facing UI (Gradio first; eventually a richer interface
  via Police Scotland feedback).
- Operational deployment design (secure enclave, audit requirements,
  disclosure framework).

## 8. Outstanding questions for supervisor

1. Are we positioning this work for a specific publication venue, and
   if so, what should the evaluation rigor look like to be credible
   there?
2. What's the right next conversation with Police Scotland — a status
   update, a working demo, or both?
3. Is there bandwidth to bring in a research assistant or collaborator
   for the evaluation and benchmarking work, which is the most
   labour-intensive part ahead?