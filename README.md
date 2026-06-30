# LLM Consortium for Cold-Case Hypothesis Generation

A proof-of-concept system that uses a consortium of large language models
to generate, critique, and rank candidate hypotheses for cold criminal
cases, then constructs a Chain Event Graph representation of the
top-ranked hypothesis.

Collaboration between the University of Edinburgh (PhD project, Adnan
Mahmud, s2887048) and Police Scotland.

> **Status**: research POC. Not approved for operational use. Not
> approved for use with real case data. See `docs/status/` for
> current state.

---

## What this system does

Given a structured cold-case file (case metadata, narrative, structured
evidence items), the system:

1. Runs a three-agent LLM consortium (one Investigator, two Critics)
   through five deterministic phases: generate hypotheses, critique
   them, revise them, score them, aggregate the scores.

2. Produces a ranked list of candidate hypotheses with per-agent and
   aggregated confidence scores.

3. For the top-ranked hypothesis, generates a Chain Event Graph: a
   directed acyclic graph representing the hypothesis as branching
   events with conditional probabilities.

Outputs are intended for **decision support** by a human investigator,
not autonomous decision-making.

---

## Quick start

### Prerequisites

- Python 3.11+ (project tested on 3.14.2 on Windows; Eddie HPC uses 3.11).
- An Ollama server reachable at `localhost:11434` with at least one
  model pulled. The default config uses `llama3.2:3b`, which runs on a
  laptop CPU.
- Optional: Graphviz on PATH if you want SVG renders of CEGs (the DOT
  file is always produced; SVG is just a convenience).

### Install

```bash
git clone https://github.com/Adnan1729/llm_cold_case_police.git
cd llm_cold_case_police
python -m venv .venv
source .venv/Scripts/activate    # Git Bash on Windows
                                 # or .venv/bin/activate on Unix
pip install -e .
```

### Pull a model

```bash
ollama pull llama3.2:3b
```

### Run

```bash
python scripts/run_pipeline.py run \
    --case cases/toy/cold_case_001 \
    --config configs/pipelines/poc_local_minimal.yaml
```

A timestamped run directory appears under `outputs/runs/`. It contains:

- `ranked_hypotheses.json` — full consortium output.
- `ceg.json`, `ceg.dot`, `ceg.svg` — Chain Event Graph artefacts.
- `events.jsonl` — structured audit log of every LLM call, validation
  outcome, and deterministic repair.
- `errors/` — full bad-LLM-output artefacts saved when retries fired.

Expected runtime on a laptop CPU with `llama3.2:3b`: **15-20 minutes**
per case. Faster on Eddie GPU nodes or with smaller consortia.

---

## Run the tests

```bash
pytest -v
```

Around 115 tests should pass. One test (`test_pipeline_renders_svg_if_graphviz_available`)
is skipped if Graphviz isn't on PATH; that's expected.

---

## Repository layout

```text
.
├── cases/toy/                  # Synthetic cold cases for development
│   └── cold_case_001/          # The Carnaden Antiques Shop Killing
├── configs/pipelines/          # YAML pipeline configurations
├── docs/                       # This documentation
├── outputs/runs/               # Per-run output directories
├── prompts/                    # Jinja2 templates for all LLM prompts
│   ├── system/                 # Per-agent system prompts
│   ├── consortium/             # Per-phase prompts
│   ├── ingestion/              # Evidence extraction prompts
│   └── event_tree/             # Event tree generation prompts
├── scripts/                    # Entry-point scripts
├── src/consortium/             # The package itself
│   ├── agents/                 # Agent definitions
│   ├── ceg/                    # CEG/EventTree validators, repair, converter
│   ├── clients/                # LLM client implementations
│   ├── orchestrators/          # Consortium orchestration strategies
│   ├── pipeline/               # Pipeline stages (ingestion, consortium, ceg)
│   ├── schemas/                # Pydantic models for every data structure
│   └── utils/                  # Audit logging, prompt rendering
└── tests/                      # Unit and integration tests

```
For a guided tour of the codebase, see `docs/codebase_map.md`.

---

## Documentation map

For someone picking up this work, read in this order:

| Document | Audience | Purpose |
|---|---|---|
| `docs/README.md` | Anyone | This file. Orientation. |
| `docs/continuation_brief.md` | Picking up the work | Briefing for resuming work — current state, immediate next steps, where to look |
| `docs/architecture.md` | Anyone doing technical work | Design decisions and the reasoning behind each |
| `docs/codebase_map.md` | Anyone modifying code | What every module does, where to find things |
| `docs/empirical_findings.md` | Researcher | What we've measured, what we've observed |
| `docs/status/*.md` | Supervisor / external | Date-stamped project status snapshots |

For someone presenting or discussing the work, the relevant docs are
the latest `docs/status/*.md` and `docs/empirical_findings.md`.

---

## Citation and acknowledgements

This project builds on:

- Chain Event Graphs (Smith & Anderson 2008; Thwaites, Smith & Cowell 2008).
- `cegpy` (Walley, Shenvi, Strong & Kobalczyk 2023): Walley et al.,
  *cegpy: Modelling with Chain Event Graphs in Python*, arXiv:2211.11366.
- Multi-agent LLM debate frameworks (general literature; this project
  uses a phased orchestrator with planned AutoGen swap-in).

---

## Contact

Adnan Mahmud — s2887048@ed.ac.uk
PhD, School of Engineering, University of Edinburgh