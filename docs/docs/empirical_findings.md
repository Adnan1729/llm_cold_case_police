# Empirical Findings

This document records observations from actual pipeline runs. Each
finding is a concrete data point — what was tried, what happened, and
what (if anything) it changes about how the system is designed.

Findings are ordered chronologically by the run that produced them.
For each, the format is: **context**, **what happened**, **what it
means**.

This document is intended to support the eventual write-up. Treat it
as a research lab notebook: facts and observations, not interpretation.
Interpretation belongs in the status documents.

---

## Run 1 — first end-to-end completion (2026-06-11)

**Context**: First pipeline run that completed end-to-end. Local CPU
(Intel Core Ultra 7 165U), `llama3.2:3b` for all agents and CEG
generation. Architecture at the time: LLM directly produced
ChainEventGraph in one call.

**What happened**:
- Total runtime: 12 minutes 30 seconds.
- Consortium completed all five phases. Four hypotheses produced.
- All four hypotheses framed exculpatorily ("X was not the
  perpetrator" or "unknown third party") rather than identifying a
  perpetrator.
- Thomson (the intended primary suspect per ground truth) ranked
  third (confidence 0.533).
- CEG generation initially failed structural validation (orphaned
  root, probability sums ≠ 1.0, leaf with outgoing edges). Retry
  mechanism corrected the orphan and leaf issues on second attempt
  but not the probability sums.

**What it means**:
- The pipeline can run end-to-end on laptop CPU with a 3B model.
- 3B model exhibits a "presumption of innocence" framing bias —
  ranks exculpatory hypotheses above identifying ones, even when the
  case is designed to support an identification.
- Cross-evidence reasoning (E003 CCTV contradicting E012 statement,
  combined with E013 financial pressure) was not performed by 3B.
- CEG structural retry works for some failure modes but not for
  probability arithmetic.

---

## Run 2 — probability arithmetic failure pattern (2026-06-11)

**Context**: Same setup as Run 1. Three CEG-generation attempts with
retry-with-feedback feeding structural problems back to the model.

**What happened**: All three attempts produced structurally different
CEGs, all with the same underlying problem — outgoing probabilities
at non-leaf nodes did not sum to 1.0.

- Attempt 1: probabilities summed to 0.4 at one node.
- Attempt 2: different graph structure, probabilities summed to 0.7 at
  one node.
- Attempt 3: different graph again, probabilities summed to a third
  value.

In every case, the validator's error message ("outgoing probabilities
from node N sum to X, expected 1.0") was fed back to the model
verbatim. The model regenerated different graphs each time but did
not fix the arithmetic.

**What it means**: 3B model failure on probability-sum constraint is
not a misunderstanding of the constraint — it's an inability to
execute the calculation reliably. Retry-with-feedback does not
correct it. This is the empirical observation that motivated the
neurosymbolic normalisation pass.

---

## Run 3 — neurosymbolic normalisation works (2026-06-11)

**Context**: Added `normalize_outgoing_probabilities` as a
deterministic repair pass between the LLM call and the structural
validator. LLM proposes structure and relative probabilities;
deterministic code scales outgoing edges at each non-leaf node to sum
to 1.0.

**What happened**:
- Pipeline completed without any structural retries firing.
- Normalisation event logged once: N0 had a single outgoing edge with
  probability 0.5; normalised to 1.0.
- CEG passed structural validation.

**What it means**: First confirmation that the neurosymbolic split
works. LLM did structural reasoning, deterministic code enforced the
numerical constraint. From this run onward, `ceg_probabilities_normalized`
became an audit-logged metric that measures how often arithmetic
repair was needed.

**Side observation**: The resulting CEG had an orphaned situation
node (N3 unreachable from root). The validator's connectedness checks
caught cycles and dangling edges but not unreachable nodes. This
limitation was carried forward as a known issue.

---

## Run 4 — semantic grounding gap (2026-06-11)

**Context**: Run 3's output, but examined for semantic correctness
rather than structural correctness.

**What happened**: Several nodes and edges in the CEG cited evidence
IDs that exist in the case but do not support the claim being made.
Most striking: node N2, labelled "Outcome: Calum Sinclair is the
killer," cited E008 — the restaurant manager's statement that
*exculpates* Sinclair.

**What it means**: Evidence-grounding validation catches the
"fabricated evidence ID" failure mode (referencing E999 when no such
evidence exists). It does not catch "cited but semantically
unrelated." Closing this gap requires either an LLM-as-judge pass
over each evidence association, or a per-claim entailment check.
Logged as future work.

---

## Run 5 — first cegpy-pipeline run (2026-06-30)

**Context**: Major architectural change. CEG generation refactored
into two stages: LLM produces an EventTree, deterministic code
converts to ChainEventGraph (cegpy AHC when applicable, direct
conversion otherwise). Repair pass added before validation. Same
model (`llama3.2:3b`), same case.

**What happened**:
- Total runtime: 18 minutes (consortium 15 min, CEG stage 3 min).
- Consortium produced four hypotheses. All four hallucinated a "debt
  collector" not present anywhere in the case. Two pairs of
  hypotheses had nearly-identical summaries. Confidence scores
  collapsed to 0.05-0.09 across all four.
- Both critic agents returned 24-character responses — effectively
  empty critique bundles (`{"critiques":[]}`). The pipeline accepted
  this because the schema permits empty lists.
- Event tree generation: LLM produced a tree-shaped graph (no
  orphans, no DAG-but-not-tree issues this time) but with numerically
  incoherent probabilities. N0 outgoing sum = 0.4, N1 = 1.6
  (three edges summing way over), N2 = 0.9.
- Repair pass: three probability normalisations applied. No structural
  repairs needed (no orphans, no duplications).
- Conversion: AHC fallback engaged (`ahc_fallback_triggered: true`).
  N0 had branching factor 1, N1 had 3, N2 had 1 — three singleton
  hyperstage classes, nothing for AHC to merge.
- CEG produced, structurally valid, semantically reflecting the
  upstream debt-collector hallucination.

**What it means** (several distinct findings):

1. **The repair pass earns its place.** Three probability
   normalisations on the first real run. The model still cannot do the
   arithmetic; the repair fixes it without an LLM round-trip.

2. **Structural correctness and semantic correctness now decouple
   cleanly.** The pipeline produces structurally valid output
   regardless of the upstream model's reasoning quality. This makes
   evaluation cleaner — they're separate metrics.

3. **The critique stage degrades silently.** Empty critiques (24-char
   responses) are syntactically valid output that satisfy the schema.
   The pipeline cannot tell the difference between "the critics
   thought hard and have nothing to add" and "the model returned
   nothing." This is a measurement worth making across runs.

4. **The AHC-fallback rate on small trees is high.** This run had
   three distinct branching factors and no merging opportunity.
   cegpy's value-add scales with tree size and pattern repetition.
   Worth tracking as a function of model size — larger models will
   produce richer trees and AHC will engage more often.

5. **Hallucinations propagate.** The consortium hallucinated a debt
   collector; the CEG faithfully visualised that hallucination. No
   amount of CEG-stage infrastructure helps with this — it's an
   upstream model-quality issue.

6. **Timing has improved substantially.** 18 minutes is down from 59
   minutes in the previous architecture. Most of the budget is now
   the consortium reasoning, not structural output formatting.

---

## Aggregate observations across runs

These are patterns visible across multiple runs rather than single-
run findings.

**Run-to-run variance is high.** Same input, same model, same
config — outputs differ substantially between runs. This is partly
the consortium's temperature (0.6 in generation phases) and partly
intrinsic to small-model behaviour. Worth measuring formally:
multiple runs of the same case, comparison of confidence-score
variance, hypothesis-set Jaccard similarity, etc.

**The "presumption of innocence" framing is a stable phenomenon.**
Observed in Run 1 (Thomson hedged at rank 3) and Run 5 (all four
hypotheses framed as "Robbie Thomson is not the killer" or similar).
This appears to be a property of instruction-tuned 3B models when
given evidence that could support an identification. Worth testing
whether 7B/13B/30B+ models break this framing.

**Probability arithmetic is the most consistent 3B failure mode.**
Across every CEG-stage run, the model has produced numerically
incoherent probabilities. The deterministic normalisation pass has
fired on every run that produced an output. This is the strongest
empirical justification for the neurosymbolic split.

**Structural failure modes have shifted across architectures.**
Old architecture (direct ChainEventGraph generation): orphaned
roots, leaves with outgoing edges, mixed structural failures plus
probability failures. New architecture (EventTree generation):
mostly probability failures only, occasionally DAG-but-not-tree
(handled by the repair pass).

---

## Measurements still to be made

These are metrics that the audit log infrastructure now supports
collecting, but for which we don't yet have enough runs to draw
conclusions.

**Per-model failure rate** of each retry layer (Pydantic, structural,
evidence-grounding). Currently we have N=1 per model size. Need
≥5 runs per model size to characterise.

**AHC-fallback engagement rate** as a function of model size.
Larger models produce richer trees → more situations with shared
branching factors → AHC engages more. Single data point so far.

**Critique-quality rate**. How often do critics return non-empty
critiques? If the empty-critiques pattern from Run 5 recurs, this
becomes a load-bearing observation about the pipeline.

**Consortium vs single-LLM baseline**. Same case, same model, single
LLM directly producing ranked hypotheses. Does the consortium
architecture outperform the baseline? Required before claiming
consortium benefit.

**Hypothesis-set stability across runs**. Same case, same model, N
runs. How often does the top-ranked hypothesis change? This bounds
how much we can trust a single-run output.

---

## Failure-mode catalogue

A summary of observed failure modes, by stage. Useful for diagnosing
new runs.

### Consortium stage

- **Exculpatory framing**: model produces "X was not the killer" rather
  than "X was the killer." Bias of small instruction-tuned models.
- **Empty critiques**: critic agents return `{"critiques":[]}`. Schema
  accepts this; downstream stages don't catch it.
- **Hallucinated entities**: model invents named entities not present
  in the case (Run 5's debt collector). Evidence-grounding validation
  does not catch this when the hallucination is in narrative rather
  than in `evidence_id` references.
- **Duplicate hypotheses**: model produces near-identical hypothesis
  summaries. No dedup currently. Worth adding similarity-based
  deduplication or strengthening the prompt.
- **Confused names**: model conflates named entities ("Robbie
  Sinclair" mashing Thomson and Sinclair). 3B-specific.

### CEG stage

- **Probability sums ≠ 1.0**: every run to date. Repaired
  deterministically.
- **DAG-but-not-tree**: nodes with multiple parents. Repaired by
  duplication.
- **Orphaned subgraphs**: nodes the model invented and forgot to wire
  up. Repaired by removal.
- **cegpy singleton-class crash**: small trees with distinct branching
  factors. Handled by fallback to direct conversion.
- **Semantic grounding errors**: cited evidence IDs exist but don't
  support the claim. Not yet caught by any validator.

### Generic across stages

- **Run-to-run variance**: same input produces materially different
  outputs across runs. Inherent to the model and the temperature.

---

## How to add a finding to this document

After each pipeline run that produces something new (a new failure
mode, a confirmation of an expected pattern, a quantitative
measurement worth recording), add an entry. Follow the structure of
existing entries:

- **Date and short title** as the section header.
- **Context**: what model, what config, what version of the pipeline
  if architectural changes are recent.
- **What happened**: factual description. Cite the run directory if
  the artefacts are still available.
- **What it means**: only the direct implications, not broader
  interpretation. Interpretation belongs in status docs.

When in doubt: write the finding. Better to have too many notes than
to wonder later what a particular run revealed.