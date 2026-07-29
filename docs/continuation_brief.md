# Continuation Brief

Read this if you are picking up work on this project. The intent is
that, after reading this document and the linked artefacts, you are in
a position to make a useful contribution within an hour.

This is not a tutorial on the project domain. For that, read the
`docs/status/` documents in chronological order. This is a working
brief: what state things are in, what to read first, what to do next.

---

## In one paragraph

This is a research POC for using a consortium of LLM agents to
generate and rank candidate hypotheses for cold criminal cases, with
a Chain Event Graph representation of the top-ranked hypothesis as a
secondary output. The current implementation runs end-to-end on a
laptop CPU using `llama3.2:3b` via Ollama, completing a synthetic
toy case in 15-20 minutes. Around 115 tests pass. The architecture
has gone through three iterations on the CEG-generation stage; the
current version uses a neurosymbolic split where the LLM produces an
event tree and deterministic code converts it to a CEG via cegpy.
The toy case has been run end-to-end successfully but the
3B-class model's output quality is poor (hallucinated entities,
exculpatory framing, empty critic responses). The next research
milestone is running on Eddie HPC with mid-size open models.

---

## What state things are in

**Working**:
- End-to-end pipeline from case file to ranked hypotheses to CEG.
- Two-step CEG generation (LLM → EventTree → cegpy/direct → CEG).
- Three-layer defence: schema validation, structural validation,
  deterministic repair.
- Full audit logging of every LLM call, retry, validation outcome,
  and repair.
- ~115 unit and integration tests passing.
- CLI: `python scripts/run_pipeline.py run --case ... --config ...`
- Synthetic toy case (`cold_case_001`) with designed-in ground truth.

**Not working / known issues**:
- 3B model produces low-quality outputs (see
  `docs/empirical_findings.md`). Symptoms: hallucinated entities,
  duplicate hypotheses, exculpatory framing, occasionally empty
  critic responses.
- Semantic evidence-grounding not validated. Model can cite real
  evidence that doesn't actually support the claim, and nothing
  catches it.
- AHC stage-identification rarely engages on POC-scale trees;
  fallback to direct conversion is the common path. Expected to
  improve at scale.

**Out of scope for now**:
- Multimodal preprocessing (PDFs, OCR, vision-LM, ASR).
- Real-data trials (requires ethics approval, deferred).
- UI beyond a Gradio stub.
- AutoGen orchestrator (planned, not started).

---

## What to read, in order

1. **`docs/README.md`** — repository orientation, quick start.
2. **`docs/status/`** — open the most recent one. It is the
   supervisor-facing snapshot of the project state.
3. **`docs/architecture.md`** — the design decisions and *why*. Read
   this before changing anything substantial.
4. **`docs/codebase_map.md`** — where everything lives. Reference
   when you need to find something specific.
5. **`docs/empirical_findings.md`** — what we have measured so far.
   Read before drawing conclusions from new runs.

For practical orientation:

6. Run the test suite to confirm the local setup works:
   `pytest -v`
7. Look at the most recent run output:
   `ls outputs/runs/` then read the `events.jsonl` of the latest.
8. Optionally: run the pipeline yourself to see it work end-to-end:
```bash
   python scripts/run_pipeline.py run \
       --case cases/toy/cold_case_001 \
       --config configs/pipelines/poc_local_minimal.yaml
```
   Allow 15-20 minutes.

---

## Working principles to maintain

These principles have been established through several iterations.
Before changing the system in ways that conflict with any of them,
re-read `docs/architecture.md` to understand why they exist.

**Open-weights only.** Hosted APIs are not acceptable for this
project. Run everything through Ollama (local or Eddie).

**Strict schemas.** Every cross-stage data structure is a Pydantic
model with `extra="forbid"`. LLM outputs are JSON-schema-constrained
at generation time and Pydantic-validated on receipt. Don't add
free-text passthrough between stages.

**Neurosymbolic split where possible.** When the LLM is asked to do
something it does badly (arithmetic, structural validity), introduce
a deterministic pass instead of expecting the model to comply. Log
when the deterministic pass intervenes — that's research data.

**Audit everything.** Every LLM call, every retry, every validation
failure, every deterministic repair gets logged as a structured event
in `events.jsonl`. The audit log is the primary research artefact.

**Mock-first, GPU-last.** Most of the code is tested against
`MockClient` instances with canned responses. Only the integration
tests actually need Ollama. Adding new logic should not require GPU.

**Synthetic data only for now.** Real cold-case data requires ethics
approval that has not been pursued. The toy case is sufficient for
the current research questions.

---

## What is the immediate next thing to do

The next concrete milestone, blocking other work:

**Eddie HPC deployment**: install Ollama on Eddie, pull mid-size
models (recommended: `qwen2.5:7b`, `llama3.1:8b`, optionally
`deepseek-r1:14b` for the CEG stage), run the existing pipeline
against `cold_case_001` with the mid-size models, and capture the
audit log.

This single milestone unblocks several of the research questions
listed below.

The full near-term roadmap, from the project status doc:

1. **Eddie deployment** (in progress). Required for next milestone.
2. **Mid-size model run on toy case**. Expected to break the
   "exculpatory framing" pattern observed with 3B.
3. **Empty-critique fix**: either tighten the critique schema to
   require at least one critique per hypothesis, or strengthen the
   critic prompts. Decide which after seeing how often empty critiques
   recur with mid-size models.
4. **Second toy case**. Built to be unambiguous (the obvious suspect
   IS the answer). Used as a variance check — if the system fails on
   the easy case, the harder case results are uninterpretable.
5. **Benchmark of 5-10 synthetic cases** with varied structures.
6. **AutoGen orchestrator** implementation, side-by-side with phased.
7. **Single-LLM baseline** for comparison.

---

## Things not to do without discussion

**Do not** remove the deterministic repair pass. The empirical
record strongly supports keeping it.

**Do not** loosen the schemas. `extra="forbid"` and tight tree
validation catch real LLM failures.

**Do not** swap Ollama for a hosted API even temporarily.

**Do not** add cegpy direct dependencies to other modules. The
cegpy-using code is contained in `src/consortium/ceg/tree_to_ceg.py`
specifically so that cegpy is replaceable if the version bug we
worked around becomes blocking.

**Do not** modify the toy case file (`cases/toy/cold_case_001/`)
without recording the change in `docs/empirical_findings.md`. The
case is research material; changing it invalidates prior runs.

**Do not** delete run directories under `outputs/runs/`. They are
research artefacts. They are gitignored but should be retained
locally.

---

## Useful commands

```bash
# Run all tests
pytest -v

# Run one test file
pytest tests/unit/test_event_tree_repair.py -v

# Run the full pipeline
python scripts/run_pipeline.py run \
    --case cases/toy/cold_case_001 \
    --config configs/pipelines/poc_local_minimal.yaml

# Inspect a case without running the pipeline
python scripts/run_pipeline.py info --case cases/toy/cold_case_001

# Quick check Ollama is responding
python scripts/smoke_test_ollama.py

# Quick check cegpy is installed and AHC runs
python scripts/smoke_test_cegpy.py

# After a cegpy version bump, check edge attribute conventions
python scripts/inspect_cegpy_edges.py

# Browse audit logs from past runs
ls -lt outputs/runs/
cat outputs/runs/<latest>/events.jsonl | jq

# Count validation errors by response model across all runs
jq -r 'select(.event=="llm_call" and .outcome=="validation_error") |
       .response_model' \
    outputs/runs/*/events.jsonl | sort | uniq -c

# Find all places audit events are emitted
grep -rn "logger.event\|audit.event" src/

# Run with CEG generation skipped (faster iteration on consortium)
python scripts/run_pipeline.py run \
    --case cases/toy/cold_case_001 \
    --config configs/pipelines/poc_local_minimal.yaml \
    --skip-ceg
```

---

## How to extend the system

A few common extension points and where to look.

**Adding a new evidence type**: extend `EvidenceType` enum in
`src/consortium/schemas/evidence.py`. No other changes needed.

**Adding a new agent role**: extend the `Agent` dataclass in
`src/consortium/agents/base.py` if a new role needs new attributes.
Otherwise just add a config entry under `agents:` in your YAML.

**Adding a new orchestrator**: subclass `ConsortiumOrchestrator` in
`src/consortium/orchestrators/`. Implement `run(case, agents)`. The
existing `PhasedOrchestrator` is a reference.

**Adding a new aggregation method**: write a function with signature
`(hypotheses, agent_weights) -> RankedHypotheses` in
`src/consortium/pipeline/aggregation.py`. Pass it as the `aggregator`
arg to `run_consortium`.

**Adding a new audit event type**: just call `logger.event("name",
**kwargs)` from anywhere. New event types don't need pre-declaration.
Document the new event in `docs/architecture.md` under section 9
when you add it.

**Adding a new test case**: create a directory under `cases/toy/`
matching the structure of `cold_case_001/`. The loader is
configuration-agnostic.

---

## Questions to ask before making non-trivial changes

If you find yourself wanting to make a substantial change, ask:

- Have I read the relevant section of `docs/architecture.md`?
- Have I checked the most recent `docs/status/*.md` for current
  priorities?
- Does this change align with the working principles above?
- Will the audit log capture the effect of this change so we can
  measure it across future runs?

If any answer is unclear, leave a note in
`docs/empirical_findings.md` describing the question and proceeding
with the simplest implementation that doesn't preclude alternatives.

---

## File of last resort

When in doubt about *anything*, look at the most recent run's
`events.jsonl`. It records exactly what the pipeline did, in order,
with timing. Most questions about "how does X work" can be answered
by tracing through one run's audit log.