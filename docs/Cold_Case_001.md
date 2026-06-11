# Cold Case LLM Consortium — End-to-End Walkthrough
**Worked example: Cold Case 001, the Carnaden Antiques Shop Killing**

## 1. Purpose

This document traces a single complete run of the cold-case LLM consortium
pipeline from raw case materials to final outputs. It is intended as a
concrete reference for what the system produces today, what each output
means, and what the outputs reveal about the underlying model's
capabilities and limitations.

## 2. The case

Cold Case 001 is a synthetic cold case constructed to exercise the
consortium's reasoning capability. The scenario:

> On the evening of Friday, 4 November 2022, Ewan Drummond, sole owner
> of Drummond Antiques in the Scottish Borders village of Carnaden, was
> found dead in his shop. He had suffered a single blow to the head from
> a reproduction Georgian silver candlestick — one of his own pieces of
> stock. The shop showed no forced entry. Approximately £8,000 of silver
> stock was missing. No arrests followed; the case went cold in February
> 2023.

Three named persons of interest sit in the case file:

- **Calum Sinclair**, business partner. Surface motive (financial
  dispute, insurance payout) but a three-line alibi: traffic-camera
  data, cell-tower data, and a corroborated dinner reservation.
- **Marion Drummond**, ex-wife. Long-running financial dispute,
  possession of shop keys, partial alibi.
- **Robbie Thomson**, shop assistant. Knew the stock and security
  routine; under financial pressure; statement claims pub presence all
  evening but contradicted by CCTV showing him leaving at 21:34.

The case file contains 13 structured evidence items, summarised in
Table 1.

**Table 1.** Evidence items in Cold Case 001.

| ID | Type | Subject of evidence |
|---|---|---|
| E001 | forensic_report | Cause of death; time-of-death window 21:00–23:00 |
| E002 | physical_evidence | Murder weapon at scene |
| E003 | digital_record | CCTV from The Rowan pub showing Thomson exit 21:34 |
| E004 | witness_statement | Sinclair statement: dinner in Edinburgh until 22:00 |
| E005 | witness_statement | Marion Drummond statement: home alone |
| E006 | digital_record | Victim's last text: silver stock still out |
| E007 | digital_record | Sinclair cell-tower data, Edinburgh central |
| E008 | witness_statement | Restaurant manager corroborating Sinclair's dinner |
| E009 | digital_record | Traffic camera placing Sinclair's car on M8 |
| E010 | physical_evidence | Inventory of missing items |
| E011 | forensic_report | Partial fingerprint on rear door frame, no match |
| E012 | witness_statement | Thomson statement: at pub all evening |
| E013 | financial_record | Thomson bank account: unexplained £200 deposit |

The case is designed such that the surface-obvious suspect (Sinclair) has
the cleanest narrative motive but the most robust alibi, while the
designer-intended primary suspect (Thomson) is identifiable only through
cross-referencing — specifically E003 against E012 (statement
contradicted by CCTV), combined with E013 (financial pressure) and access
via knowledge of the security routine. The ground truth is recorded in
`ground_truth.md` and is not visible to the consortium during the run.

## 3. The pipeline

The pipeline operates in two sequential stages:

1. **Consortium stage.** Three LLM agents — one Investigator and two
   Critics (Forensic Analyst and Devil's Advocate) — generate, critique,
   revise, and score candidate hypotheses across five deterministic
   phases. The output is a ranked list of hypotheses with confidence
   scores computed by weighted aggregation of agent scores.

2. **Chain Event Graph stage.** The top-ranked hypothesis is converted
   into a Chain Event Graph: a directed acyclic graph where nodes are
   states of the world, edges are events with conditional probabilities,
   and outgoing edges from any non-leaf node sum to one. The CEG makes
   the hypothesis's branching event structure explicit.

For this run all four roles (Investigator, two Critics, CEG generator)
were served by the same Ollama-hosted model (Llama 3.2 3B). In production
the consortium would use different model families per agent to introduce
epistemic diversity.

## 4. The run

The run was executed on a laptop CPU (Intel Core Ultra 7 165U, no
discrete GPU). Total wall-clock duration: 59 minutes.

```bash
$ python scripts/run_pipeline.py run \
    --case cases/toy/cold_case_001 \
    --config configs/pipelines/poc_local_minimal.yaml
```

Per-call timing extracted from the audit log (`events.jsonl`) is shown
in Table 2. Every call succeeded on the first attempt — no JSON, schema,
or structural retries were triggered.

**Table 2.** Per-call timing for the run.

| Phase | Agent | Structured output | Duration |
|---|---|---|---|
| Generate | Investigator | `HypothesisGenerationOutput` | 7m 48s |
| Critique | Forensic Analyst | `CritiqueBundle` | 7m 10s |
| Critique | Devil's Advocate | `CritiqueBundle` | 8m 47s |
| Revise | Investigator | `HypothesisGenerationOutput` | 8m 27s |
| Score | Investigator | `ScoreBundle` | 6m 37s |
| Score | Forensic Analyst | `ScoreBundle` | 6m 36s |
| Score | Devil's Advocate | `ScoreBundle` | 6m 37s |
| **Consortium total** |  |  | **52m 02s** |
| CEG generation | — | `ChainEventGraph` | 7m 00s |
| **Run total** |  |  | **59m 02s** |

## 5. Stage 1 output: ranked hypotheses

The consortium produced four hypotheses, ranked in Table 3 by the
weighted mean of per-agent scores.

**Table 3.** Ranked hypotheses (3 dp confidence) from the consortium.

| Rank | ID | Confidence | Hypothesis |
|---|---|---|---|
| 1 | H1 | 0.433 | Calum Sinclair's alibi is shaky due to unexplained gaps in his cell tower data |
| 2 | H3 | 0.367 | Robbie Thomson's involvement is uncertain due to inconsistencies in his statement and partial fingerprint evidence |
| 3 | H2 | 0.333 | Marion Drummond's involvement is questionable due to inconsistencies in her alibi and financial dispute |
| 4 | H4 | 0.300 | Calum Sinclair's involvement is questionable due to inconsistencies in his statement and financial records |

The top-ranked hypothesis identifies Calum Sinclair (the business
partner) as the leading person of interest, citing a gap in his cell
tower handoffs between 22:45 and 23:15. The hypothesis ranked second
identifies Robbie Thomson — the designer-intended primary suspect — but
with lower confidence and noticeably hedged framing.

The three agents broadly agreed on their scoring (within ±0.2 of each
other for most hypotheses), with the Devil's Advocate slightly more
willing to entertain less-favoured hypotheses than the other agents.

## 6. Stage 2 output: Chain Event Graph

The CEG was generated for H1. It contains five nodes (one root, two
situation nodes, two leaves) and five edges. Figure 1 shows the rendered
graph.

![Chain Event Graph for hypothesis H1](../outputs/runs/20260611_042756_cold_case_001/ceg.svg)

**Figure 1.** Chain Event Graph for hypothesis H1 ("Calum Sinclair's
alibi is shaky"). Nodes are states of the world; edges are events
labelled with their conditional probabilities. The root state N0 is
shown in blue, leaf outcome states (N2, N4) in yellow. From any non-leaf
node, outgoing edge probabilities sum to one.

The graph encodes the following narrative:

- **N0 (root):** Initial state. Associated evidence: E002 (the physical
  evidence at the scene).
- **N1 (situation):** "Calum Sinclair leaves his location." Associated
  evidence: E012, E013.
- **N2 (leaf):** Outcome — "Calum Sinclair is the killer." Associated
  evidence: E008.
- **N3 (situation):** "Calum Sinclair arrives at Drummond Antiques."
  Associated evidence: E009, E010.
- **N4 (leaf):** Outcome — "Calum Sinclair is not the killer."

From N1, the model assigned p=0.70 to "Calum kills Ewan Drummond" and
p=0.30 to the negation. From N3, p=0.40 and p=0.60 respectively. The
sole outgoing edge from the root (T0) has p=1.00.

That last probability was not produced by the model. The model
originally assigned p=0.50 to T0, which is mathematically incorrect — a
single outgoing edge from a non-leaf node must have probability 1.0.
The deterministic normalisation pass scaled it. This intervention is
recorded in the audit log as a `ceg_probabilities_normalized` event,
specifying the affected node and the original sum.

## 7. Observations

Several observations from this run merit comment, each pointing at a
research thread.

**The run reached completion with no retries triggered.** Every LLM
call's output passed Pydantic validation on first attempt; the CEG
passed structural validation on first attempt (modulo one
normalisation). This is the first end-to-end run where no retry
mechanisms were needed, suggesting the prompt-and-schema regime has
settled into a stable equilibrium with the 3B model.

**The model does not surface the designer-intended primary suspect.**
Thomson appears at rank 2, but Sinclair — the surface-obvious suspect
with the strong alibi — appears at rank 1. The cross-evidence reasoning
required to upgrade Thomson (E003 contradicting E012, combined with
E013) does not appear to have been performed. This is consistent with
the hypothesis that multi-evidence cross-referencing is a
model-capability threshold that 3B sits below. Scaling experiments
across 7B–32B model classes on Eddie will test this directly.

**All hypothesis framing is hedged.** Each of the four hypotheses is
phrased as "X's involvement is questionable" or "X's alibi is shaky"
rather than "X is the killer." This "presumption of innocence" framing
was observed in earlier runs and is now reproducible. Whether it is a
model-scale artefact, a prompt artefact, or a deeper property of
instruction-tuned LLMs on adversarial-investigative tasks is open.

**Probability normalisation was triggered once.** The model assigned
p=0.50 to the root's sole outgoing edge. The neurosymbolic split — LLM
proposes structure and relative probabilities, deterministic code
enforces the sum-to-one constraint — operated exactly as designed.
Across more runs, the normalisation frequency becomes a measurable
property of model competence on this task.

**The CEG contains an orphaned situation node.** Node N3 ("Calum
Sinclair arrives at Drummond Antiques") has no incoming edges and is
therefore unreachable from the root. The structural validator accepted
the graph because its connectedness checks are limited to detecting
cycles and dangling edge references — full root-reachability of all
nodes is not yet enforced. This is a validator gap and a candidate for
hardening in the next iteration.

**Evidence is cited by ID but not always semantically appropriate.**
Examination of the CEG reveals that the model has associated some nodes
with evidence IDs that exist but do not actually support the claim. The
most striking case is N2 ("Outcome: Calum Sinclair is the killer"),
which is associated with E008 — the restaurant manager's statement
corroborating Sinclair's dinner alibi, which is in fact evidence
*against* the outcome. Similarly, N1 ("Calum Sinclair leaves his
location") is associated with E012 and E013, both of which are items
relating to Thomson rather than Sinclair. The evidence-grounding
validator catches the "fabricated evidence" failure mode (citing
non-existent IDs) but does not catch this more subtle "cited but
semantically unrelated" failure mode. Closing this gap likely requires
an LLM-as-judge pass over each evidence association, or a structured
per-claim entailment check against the cited evidence. This is one of
the more interesting failure modes to emerge from the POC and a clear
candidate for the next iteration.

## 8. What this demonstrates

The pipeline now operates end-to-end on the toy case without
intervention, produces all expected artefacts, and provides an auditable
record of every model call and every deterministic intervention. The
infrastructure is ready for the next research phase: scaling to
mid-size open-weights models on Eddie, building a benchmark of
synthetic cases, and varying consortium composition.

Two specific research questions are now tractable with the current
codebase that were not before:

1. **Does the consortium architecture outperform a single-LLM
   baseline?** With the audit log we can run the same case under both
   configurations and compare hypothesis ranking, calibration, and
   evidence-grounding quality.

2. **At what model size does the small-model "presumption of innocence"
   framing break?** By running the same case across 3B → 7B → 8B → 32B
   classes, we can locate the threshold at which the consortium begins
   to commit to identifications rather than hedged non-identifications.

The current run is, in effect, the baseline against which all
subsequent runs will be measured.