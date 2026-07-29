# Continuation Brief — Ingestion Phase

This brief covers a specific upcoming phase of work: building the
ingestion pipeline that produces `EvidenceCard` objects from raw
source material (PDFs and audio for the POC). This is upstream of
the existing LLM consortium pipeline.

Read this after reading `docs/continuation_brief.md` (the general
project brief). This document assumes familiarity with the existing
architecture.

---

## In one paragraph

The current pipeline consumes `EvidenceCard` objects — structured
Pydantic models with fields for evidence ID, type, content, source,
timestamp, location, reliability, and chain-of-custody notes. So
far these have been authored by hand for the toy case
`cold_case_001`. The next phase builds an ingestion layer that
produces `EvidenceCard` objects automatically from raw source
material. For the POC, "raw source material" means born-digital or
OCR'd PDFs, plus (if tractable) audio recordings via Whisper
transcription. Real-world source material — scanned documents,
video, structured databases, handwritten notes — is scope for a
later phase. Everything is synthetic: real Police Scotland data is
still deferred pending ethics approval.

---

## What the ingestion phase must produce

The output contract is fixed: a list of `EvidenceCard` objects
matching the existing `src/consortium/schemas/evidence.py` schema.
Nothing downstream of ingestion should need to change.

Each `EvidenceCard` needs:
- A stable ID (`E001`, `E002`, ...) assigned by the ingestion phase.
- All required schema fields populated.
- A `source` field that traces back to the specific source
  artefact (PDF filename + page number, or audio filename +
  timestamp range).
- A `chain_of_custody_note` describing the extraction path — which
  source, which extraction pass, which model produced the fields.

Chain-of-custody in the POC is *documentary*, not cryptographic.
The goal is that a human reviewing an `EvidenceCard` can trace it
back to the specific source material it came from. Formal
cryptographic provenance is a real-deployment concern, not a POC one.

---

## Scope for the POC

**In scope:**
- Born-digital PDFs (text extractable via `pdfplumber` or `pypdf`).
- OCR'd PDFs (images-in-PDFs, requiring Tesseract or equivalent).
- Audio files via Whisper transcription → text → LLM extraction.
- LLM-driven extraction of structured `EvidenceCard` fields from
  the resulting text.
- Provenance metadata (source file, page/timestamp, extraction
  pass) attached to every card.
- Synthetic source material — the POC generates its own PDFs and
  audio files representing the toy case.

**Out of scope for now:**
- Scanned PDFs with poor OCR quality (accept only clean scans).
- Video (frame extraction + ASR).
- Structured databases and spreadsheets (structured-source ingestion
  is a different problem).
- Handwritten notes.
- Multi-language material (English only).
- Real case data (ethics approval not pursued).
- Cryptographic provenance / signed audit chains.

---

## Design decision: LLM does the extraction

The ingestion phase should follow the same architectural pattern as
the existing pipeline: raw text goes to an LLM with a Pydantic
schema, structured output comes back, Pydantic validates it,
retry-with-feedback on failure. The infrastructure
(`OllamaClient.chat_structured`, `RunLogger`, validation retries)
is already in place — the ingestion phase adds new prompts, a new
Pydantic schema (`EvidenceExtractionOutput`, may already exist as
a stub), and orchestration.

**Why LLM-driven rather than pipeline-driven:** consistency with
the rest of the project, reuse of existing infrastructure, and the
fact that the extraction task involves semantic decisions (what
counts as one piece of evidence, how to characterise reliability,
how to write a coherent `content` field) that classical NLP
pipelines handle poorly.

**Why not agentic extraction:** for the POC, one LLM call per
source document is sufficient. A consortium of extractors is
overkill for this task and reserved for later if warranted.

## Design decision: audio handled by Whisper first

Ollama does not currently expose audio-native multimodal models
reliably on Windows. The pragmatic pattern for POC audio:

1. Whisper (`openai-whisper` Python package or `whisper-cpp`) runs
   locally, produces a transcript with word-level timestamps.
2. The transcript, plus the source-audio filename and timestamp
   metadata, is passed to the same LLM extraction stage that
   handles PDF text.
3. Every `EvidenceCard` produced from audio carries a source
   reference like `audio://interview_witness_003.wav#t=234.5-289.2`
   in its `source` field.

This means the LLM stage is uniform across source types: everything
upstream produces text with provenance, the LLM extracts over text.

**Not doing:** multimodal LLM inference on raw audio. Reserved for
later when the tooling stabilises.

---

## What needs to be built

Rough component list. The next chat should refine this into a
concrete implementation plan.

**Data:**
- Synthetic source material for `cold_case_001`. The existing
  `evidence.json` needs to be reverse-engineered into fake PDFs
  (witness statements, forensic reports, financial records) and
  fake audio files (interview recordings) that would notionally
  produce the same `EvidenceCard` set. This is a preparatory task
  before the ingestion pipeline can be tested end-to-end.

**Schemas:**
- Possibly a new `SourceDocument` schema tracking metadata about
  the raw source (filename, format, page/duration, extraction
  method used).
- Possibly extend `EvidenceCard.source` and
  `chain_of_custody_note` to hold richer provenance data. The
  existing string fields may be enough — a design decision.

**Text extraction module:**
- `src/consortium/ingestion/pdf_extraction.py` — wraps `pdfplumber`
  for born-digital PDFs and Tesseract for OCR'd ones. Returns text
  plus per-page provenance.
- `src/consortium/ingestion/audio_extraction.py` — wraps Whisper.
  Returns transcript plus word-level timestamp mapping.

**LLM extraction module:**
- `src/consortium/ingestion/evidence_extraction.py` — takes
  extracted text plus provenance, calls the LLM with the
  evidence-extraction prompt, produces a list of `EvidenceCard`
  objects.
- A refined `evidence_extraction.j2` prompt (a stub already exists
  at `prompts/ingestion/evidence_extraction.j2`).

**Orchestration:**
- `src/consortium/pipeline/ingestion_stage.py` — coordinates text
  extraction and LLM extraction across a set of source documents,
  produces the final `EvidenceCard` list.
- CLI extension: `consortium-run ingest --sources <dir> --out <file>`.

**Tests:**
- Unit tests per module (text extraction, audio extraction, LLM
  extraction with mocks).
- Integration test running the full ingestion pipeline against a
  set of synthetic source documents and comparing the output to a
  known `EvidenceCard` set.

---

## Interaction with the existing pipeline

The ingestion phase is *upstream* of everything currently built.
Its output — a list of `EvidenceCard` objects — is the input to
the case-loading step in `src/consortium/io.py::load_case_from_dir`.

The cleanest integration is that the ingestion phase produces the
same `evidence.json` file that `load_case_from_dir` already reads.
This means:
- The existing pipeline needs no changes.
- Cases can be constructed either by hand (as `cold_case_001`
  currently is) or by running ingestion over source material.
- Both flows produce the same downstream artefacts.

A possible CLI extension: `consortium-run ingest --case-dir X`
would populate the `evidence.json` in an existing case directory
from source material in a sibling `sources/` subdirectory. Then
`consortium-run run --case X` proceeds as normal.

---

## Open questions for the next session

These should be decided early in the next chat, not left ambiguous:

1. **How rich should provenance metadata be?** Adding a
   `SourceDocument` schema and cross-referencing it from
   `EvidenceCard` is more work than just storing a source string.
   Which end?

2. **Should the ingestion LLM be different from the consortium
   LLMs?** Extraction is a lower-reasoning task than hypothesis
   generation. Using a smaller/faster model for extraction is a
   reasonable optimisation. But it means another model to manage.

3. **How does ingestion handle documents that contain multiple
   pieces of evidence?** A single witness statement PDF might
   describe multiple incidents. Does the LLM produce multiple
   `EvidenceCard` objects from one source, and how is the
   provenance apportioned?

4. **What does an ingestion audit log look like?** The existing
   audit log covers LLM calls in the consortium and CEG stages.
   Ingestion adds text extraction, audio transcription, and its
   own LLM calls. Are these all logged the same way? Same
   `events.jsonl` file, or a separate one per stage?

5. **What's the synthetic-source-material generation strategy?**
   Hand-writing fake PDFs and recording fake audio is
   time-consuming. Options include: writing them by hand (highest
   fidelity, slowest); using an LLM to draft them from the
   existing `evidence.json` (fast, but risks circular reasoning
   where the ingestion LLM re-derives what the generation LLM
   put in); a middle path of LLM drafts with human editing
   (probably the right answer).

---

## Read this before starting

In this order:

1. `docs/README.md` — repository orientation.
2. `docs/continuation_brief.md` — general project brief.
3. `docs/architecture.md` — architectural decisions, especially
   section 12 which lists ingestion as anticipated future work.
4. `docs/codebase_map.md` — where things live, especially the
   `pipeline/`, `clients/`, and `utils/` modules the ingestion
   phase will reuse.
5. This document.

Then examine:
- `src/consortium/schemas/evidence.py` — the schema you must
  produce.
- `src/consortium/clients/ollama.py` — the LLM client pattern
  you will reuse.
- `src/consortium/pipeline/ingestion.py` — the existing stub;
  may already contain scaffolding.
- `prompts/ingestion/evidence_extraction.j2` — existing prompt
  stub.
- `cases/toy/cold_case_001/evidence.json` — the format you must
  produce.

---

## What good progress looks like

For the next session, working backwards from a definition of "done"
for the POC ingestion phase:

- One synthetic PDF source (a fake witness statement) produces
  one correct `EvidenceCard` when passed through the ingestion
  pipeline.
- One synthetic audio source (a fake interview recording)
  produces one correct `EvidenceCard`.
- The provenance in each `EvidenceCard` traces back to the
  specific source and location within it.
- The ingestion pipeline logs its work to `events.jsonl` in the
  same style as the existing pipeline.
- Ingesting the full synthetic source set for `cold_case_001`
  produces an `evidence.json` that, while not necessarily
  identical to the hand-authored version, is structurally
  equivalent — same number of cards, same evidence IDs, same
  types.

Ambitious but reachable in a few focused sessions.
