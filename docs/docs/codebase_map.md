# Codebase Map

A guided tour of the repository. For each major component: what it
does, where it lives, what it depends on, and where to look when you
want to modify it.

Read this whenever you need to find something quickly. For the *why*
of design decisions, see `docs/architecture.md`.

---

## Top-level repository

.
├── cases/                  # Test/development case data
├── configs/                # YAML pipeline configurations
├── docs/                   # Documentation (you are here)
├── outputs/runs/           # Per-run output artefacts
├── prompts/                # Jinja2 templates
├── scripts/                # Entry-point Python scripts
├── src/consortium/         # The main package
├── tests/                  # Unit and integration tests
├── pyproject.toml          # Dependencies, build config
└── README.md               # Project README (also docs/README.md)

---

## src/consortium/ — the package

### `schemas/` — every typed object

All Pydantic models with `extra="forbid"`. These are the cross-stage
contracts. If you're modifying these, run all tests.

- **`evidence.py`** — `EvidenceCard` (one piece of evidence),
  `EvidenceType` enum, `Reliability` enum.
- **`case.py`** — `Case`, `CaseMetadata`, `Victim`, `Incident`. A Case
  is metadata + narrative + list of EvidenceCards.
- **`hypothesis.py`** — `Hypothesis` (a single candidate explanation),
  `EvidenceSupport`, `Actor`, `HypothesisEvent`, `AgentScore`,
  `RankedHypotheses`. `evidence_support` is the load-bearing field for
  hallucination defence.
- **`debate.py`** — `HypothesisGenerationOutput`, `CritiqueBundle`,
  `HypothesisCritique`, `ScoreBundle`, `HypothesisScore`. These are
  the per-phase structured outputs the consortium emits.
- **`ceg.py`** — `ChainEventGraph`, `CEGNode`, `CEGEdge`, `CEGStage`,
  `CEGNodeType`. Schema-level only; structural validation is in
  `ceg/validator.py`.
- **`event_tree.py`** — `EventTree`, `EventTreeNode`, `EventTreeEdge`.
  Simpler than ChainEventGraph: no explicit node typing, no stages,
  no leaf_node_ids field. Tree shape is structural, not declarative.
- **`__init__.py`** — re-exports everything for `from consortium.schemas
  import X` convenience.

### `clients/` — LLM clients

- **`base.py`** — `LLMClient` ABC and `Message` model. The ABC defines
  `chat()` (free text) and `chat_structured(response_model=...)`.
- **`mock.py`** — `MockClient`. Returns queued canned responses; used
  in every test that exercises a stage. Tracks calls in `.call_log` so
  tests can assert what was sent.
- **`ollama.py`** — `OllamaClient`. Wraps `ollama-python`, uses
  Ollama's structured-output mode (Pydantic JSON Schema as `format`),
  implements JSON-parse and validation retry inside `chat_structured`,
  emits `llm_call` and `llm_retry` audit events.

### `ceg/` — CEG and EventTree machinery

This is the most code-heavy module and where the neurosymbolic split
lives.

- **`validator.py`** — `validate_ceg_structure`,
  `validate_ceg_evidence_grounding`, `assert_ceg_valid`. Checks tree
  shape, probability sums, cycles, evidence ID existence on CEGs.
  Used after the deterministic conversion produces a CEG.

- **`event_tree_validator.py`** — Same idea but for event trees.
  Stricter than CEG validator: enforces single-parent rule and
  reachability from root. These constraints catch malformed LLM
  output before it reaches the converter.

- **`repair.py`** — `normalize_outgoing_probabilities` (for CEGs).
  Deterministic probability-sum repair. Returns the modified CEG plus
  a `RepairReport`.

- **`event_tree_repair.py`** — Deterministic structural repair for
  event trees. Three operations: orphan removal, DAG-to-tree
  expansion (duplicates shared descendants), probability
  normalisation. Returns the repaired tree plus an
  `EventTreeRepairReport` recording what was changed.

- **`tree_to_dataframe.py`** — Converts EventTree to pandas DataFrame
  for cegpy consumption. Pseudo-count expansion. Supports a
  `use_generic_labels=True` mode that emits positional labels
  (outcome_0, outcome_1, ...) needed for cegpy's AHC.

- **`tree_to_ceg.py`** — The core conversion. Calls cegpy's StagedTree
  with AHC, then ChainEventGraph; reattaches LLM's specific labels
  using the label mapping; falls through to direct conversion when
  cegpy's AHC bug triggers. Returns the CEG plus a
  `CegpyConversionReport`.

- **`renderer.py`** — `ceg_to_dot`, `write_ceg_dot`,
  `render_ceg_to_svg`. Hand-written DOT serialiser (zero deps);
  SVG render needs the Graphviz binary.

### `orchestrators/` — consortium orchestration

- **`base.py`** — `ConsortiumOrchestrator` ABC. Single method
  `run(case, agents) -> RankedHypotheses`.
- **`phased.py`** — `PhasedOrchestrator`. Five deterministic phases:
  generate, critique, revise, score, aggregate. The current default.

### `pipeline/` — pipeline stages

- **`ingestion.py`** — `ingest_case_text`. Converts unstructured text
  to structured EvidenceCards via the ingestion model. Not yet used
  in production runs (toy case is already structured) but the wiring
  is in place.
- **`aggregation.py`** — `aggregate_weighted_mean`,
  `aggregate_with_ranks`. Combines per-agent scores into a final
  confidence and assigns ranks.
- **`consortium_stage.py`** — `run_consortium`. Thin wrapper around the
  orchestrator that adds case-level concerns (deduplication,
  hypothesis limit).
- **`ceg_stage.py`** — `generate_ceg`. The two-step pipeline: LLM emits
  EventTree → repair → validate (with retry) → convert to CEG via
  `event_tree_to_ceg`. Emits `event_tree_repaired`,
  `event_tree_validation_failed`, `event_tree_retry_succeeded`,
  `ceg_conversion_completed`, `ceg_ahc_fallback_triggered` audit events.

### `agents/` — agent definitions

- **`base.py`** — `Agent` dataclass. Name, role (investigator or
  critic), LLM client, system prompt template path, score weight for
  aggregation.

### `utils/` — supporting utilities

- **`prompts.py`** — `render_template`. Jinja2 loader pointed at
  `prompts/`. Used by every stage that calls an LLM.
- **`audit.py`** — `RunLogger`, `set_active_logger`,
  `get_active_logger`. Writes `events.jsonl` and `errors/`. The active
  logger is held in a contextvar so it's accessible from anywhere in
  the pipeline without being threaded through.

### `cli.py` — the entry-point app

Typer app with two commands:
- `run` — execute the pipeline end-to-end.
- `info` — load and display a case without running anything.

Installs as `consortium-run` via `[project.scripts]` in pyproject.toml.
`scripts/run_pipeline.py` is a thin wrapper that calls this.

### `io.py` — loading and writing

- `load_case_from_dir(path)` → Case.
- `load_pipeline_config(path)` → dict.
- `build_agents_from_config(cfg)` → list[Agent].
- `build_ceg_client_from_config(cfg)` → LLMClient (for the CEG stage).
- `make_run_directory(base, case_id)` → Path with timestamp prefix.
- `write_ranked_hypotheses(...)`, `write_ceg(...)` — output writers.
- `try_render_ceg_svg(...)` — graceful SVG render with fallback.

---

## prompts/ — Jinja2 templates

Every LLM-facing piece of text. Modifying these is the fastest way to
change behaviour without changing code.

- **`system/`** — per-agent system prompts.
  - `investigator.j2`, `forensic_analyst.j2`, `devils_advocate.j2`,
    `ingestion.j2`, `event_tree_generator.j2`.
- **`consortium/`** — per-phase consortium prompts.
  - `initial_generation.j2`, `critique.j2`, `revise.j2`, `score.j2`.
- **`ingestion/`** — `evidence_extraction.j2`.
- **`event_tree/`** — `generate_from_hypothesis.j2`. The replacement
  for the old `ceg/generate_from_hypothesis.j2`.
- **`ceg/`** — old CEG-generation prompt. Still present but not used
  by the current pipeline.

---

## configs/ — pipeline configurations

YAML files defining a pipeline run.

- **`pipelines/poc_default.yaml`** — multi-family setup (Llama, Qwen,
  Mistral on different agents). For Eddie or stronger laptops.
- **`pipelines/poc_local_minimal.yaml`** — `llama3.2:3b` for all
  agents. The CPU-friendly default.

Each config defines:
- `pipeline:` — top-level settings (max_hypotheses, run_ceg_stage flag).
- `agents:` — list of agent specs (name, role, provider, model, host,
  weight, system_prompt_template).
- `ceg:` — settings for the CEG-stage LLM.

---

## cases/toy/ — synthetic cases

- **`cold_case_001/`** — the Carnaden Antiques Shop Killing.
  - `case.yaml` — metadata.
  - `narrative.md` — case narrative for context.
  - `evidence.json` — 13 structured EvidenceCards.
  - `ground_truth.md` — designer-intended answer (Thomson). Not shown
    to the consortium.

When adding new cases, follow this directory shape exactly so
`load_case_from_dir` works without changes.

---

## scripts/ — entry points

- **`run_pipeline.py`** — thin wrapper around `consortium.cli`.
- **`smoke_test_ollama.py`** — confirms Ollama is reachable and the
  configured model responds.
- **`smoke_test_cegpy.py`** — confirms cegpy is installed and AHC
  runs on a tiny synthetic dataset.
- **`inspect_cegpy_edges.py`** — diagnostic. Prints how cegpy stores
  edge metadata. Use after a cegpy version bump.

---

## tests/ — test suite

Around 115 tests in two directories:

- **`tests/unit/`** — one file per module of interest. Naming follows
  `test_<module>.py`.
- **`tests/integration/`** — end-to-end with mocks.
  `test_pipeline_end_to_end.py` runs the full consortium and CEG
  stages with `MockClient` instances.

Run all: `pytest -v`.
Run one: `pytest tests/unit/test_event_tree_repair.py -v`.

A test marked `pytest.importorskip("cegpy")` at module level will be
collected but skipped if cegpy is not installed. The same pattern is
used for graphviz tests requiring the system binary.

---

## outputs/runs/ — per-run output directories

Created per pipeline run. Directory naming: `<YYYYMMDD_HHMMSS>_<case_id>`.

Contents:
- `ranked_hypotheses.json` — the consortium's output.
- `ceg.json`, `ceg.dot`, `ceg.svg` — the CEG and its renders.
- `events.jsonl` — structured audit log, one JSON object per line.
- `errors/` — bad-LLM-output artefacts and traceback files.

This directory is gitignored. Outputs are not part of the repo.

---

## How to find things quickly

- "Where is X type defined?" — `src/consortium/schemas/`.
- "Where is the prompt for Y?" — `prompts/`.
- "Where does the CEG actually get built?" —
  `src/consortium/pipeline/ceg_stage.py` (orchestration) and
  `src/consortium/ceg/tree_to_ceg.py` (conversion).
- "Where is the retry logic?" — `OllamaClient.chat_structured` (Layer
  1) and `generate_ceg` (Layer 2).
- "Where do audit events get emitted?" — see grep:
  `grep -rn "logger.event\|audit.event" src/`
- "Where is the cegpy fallback handled?" —
  `src/consortium/ceg/tree_to_ceg.py`, in `event_tree_to_ceg`,
  search for `ahc_fallback_triggered`.
- "What ran in the last pipeline execution?" — `outputs/runs/`, look
  at the most recent timestamped directory, read `events.jsonl`.