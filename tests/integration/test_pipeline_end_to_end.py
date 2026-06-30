"""End-to-end integration test for the cold-case pipeline.

Stages exercised:
1. Load the toy case from disk.
2. Run the consortium (PhasedOrchestrator with mocked LLM responses).
3. Aggregator computes confidence and ranks hypotheses.
4. Generate a CEG from the top-ranked hypothesis (mocked).
5. Validate the CEG structurally.
6. Render to DOT on disk; optionally to SVG if Graphviz is installed.

Mocked responses are realistic for the toy case (matching the intended
ground truth: Thomson ranks above Sinclair) but their purpose here is to
exercise pipeline plumbing, not LLM quality.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from consortium.agents import Agent
from consortium.ceg import render_ceg_to_svg, write_ceg_dot
from consortium.clients import MockClient
from consortium.orchestrators import PhasedOrchestrator
from consortium.pipeline import generate_ceg, run_consortium
from consortium.schemas import (
    Actor,
    ActorRole,
    Case,
    CaseMetadata,
    CEGEdge,
    CEGNode,
    CEGNodeType,
    CEGStage,
    ChainEventGraph,
    CritiqueBundle,
    EvidenceCard,
    EvidenceSupport,
    Hypothesis,
    HypothesisCritique,
    HypothesisEvent,
    HypothesisGenerationOutput,
    HypothesisScore,
    ScoreBundle,
    SupportRole,
    EventTree,
    EventTreeEdge,
    EventTreeNode,
)


CASE_DIR = (
    Path(__file__).resolve().parents[2]
    / "cases"
    / "toy"
    / "cold_case_001"
)


# ----------------------------------------------------------------------
# Loading the toy case
# ----------------------------------------------------------------------

def _load_toy_case() -> Case:
    with open(CASE_DIR / "case.yaml") as f:
        meta_data = yaml.safe_load(f)
    meta_data.pop("artefacts", None)
    metadata = CaseMetadata.model_validate(meta_data)

    narrative = (CASE_DIR / "narrative.md").read_text(encoding="utf-8")

    with open(CASE_DIR / "evidence.json") as f:
        ev_data = json.load(f)
    evidence = [
        EvidenceCard.model_validate(item) for item in ev_data["evidence_items"]
    ]

    return Case(metadata=metadata, narrative=narrative, evidence=evidence)


# ----------------------------------------------------------------------
# Mocked hypotheses matching the toy case
# ----------------------------------------------------------------------

def _h1_thomson() -> Hypothesis:
    """Intended primary hypothesis per ground_truth.md."""
    return Hypothesis(
        id="H1",
        one_line_summary=(
            "Robbie Thomson killed Drummond during attempted theft after "
            "leaving The Rowan at 21:34."
        ),
        narrative=(
            "After leaving The Rowan at 21:34 (E003), contradicting his own "
            "statement of being at the pub all evening (E012), Thomson "
            "returned to the shop using his keys. The victim's 19:22 text "
            "(E006) had informed him the high-value silver was accessible. "
            "The post-mortem window (E004, starting 21:00) and the missing "
            "high-value items (E010) are consistent with a theft that turned "
            "violent. Thomson's recent financial pressure (E013) provides "
            "motive; the unexplained £200 deposit the following Monday is "
            "consistent with conversion of stolen items, though not proof. "
            "Neighbour Cameron (E001) heard raised voices around 21:00 from "
            "the direction of the shop, consistent with a confrontation."
        ),
        actors=[
            Actor(name="Robbie Thomson", role=ActorRole.PERPETRATOR),
            Actor(name="Ewan Drummond", role=ActorRole.VICTIM),
        ],
        timeline=[
            HypothesisEvent(
                sequence_index=0,
                timestamp="2022-11-04T19:22:00",
                description="Receives text from Drummond about silver being out",
                supporting_evidence=["E006"],
            ),
            HypothesisEvent(
                sequence_index=1,
                timestamp="2022-11-04T21:34:00",
                description="Leaves The Rowan, walks south towards shop",
                supporting_evidence=["E003"],
            ),
            HypothesisEvent(
                sequence_index=2,
                timestamp="2022-11-04T21:45:00",
                description="Enters shop using keys; confronts Drummond",
                supporting_evidence=["E001"],
            ),
            HypothesisEvent(
                sequence_index=3,
                timestamp="2022-11-04T21:50:00",
                description="Single blow to back of head; victim dies",
                supporting_evidence=["E004", "E005"],
            ),
            HypothesisEvent(
                sequence_index=4,
                timestamp=None,
                description="Takes silver tea service, jewellery box, letter opener",
                supporting_evidence=["E010"],
            ),
        ],
        evidence_support=[
            EvidenceSupport(evidence_id="E001", role=SupportRole.SUPPORTS,
                            weight=0.5, note="Raised voices near time of death"),
            EvidenceSupport(evidence_id="E002", role=SupportRole.NEUTRAL,
                            weight=0.2, note="Pub landlord recall is vague"),
            EvidenceSupport(evidence_id="E003", role=SupportRole.SUPPORTS,
                            weight=0.9, note="CCTV places Thomson leaving at 21:34"),
            EvidenceSupport(evidence_id="E004", role=SupportRole.SUPPORTS,
                            weight=0.7, note="TOD window opens at 21:00"),
            EvidenceSupport(evidence_id="E006", role=SupportRole.SUPPORTS,
                            weight=0.8, note="Text alerted Thomson to silver"),
            EvidenceSupport(evidence_id="E010", role=SupportRole.SUPPORTS,
                            weight=0.8, note="Missing items match theft profile"),
            EvidenceSupport(evidence_id="E012", role=SupportRole.CONTRADICTS,
                            weight=0.7, note="Statement contradicts E003 CCTV"),
            EvidenceSupport(evidence_id="E013", role=SupportRole.SUPPORTS,
                            weight=0.7, note="Financial pressure plus unexplained cash"),
        ],
        unexplained_evidence=["E011"],
        is_exculpatory=False,
    )


def _h2_sinclair() -> Hypothesis:
    """Surface-obvious but alibi-blocked alternative."""
    return Hypothesis(
        id="H2",
        one_line_summary=(
            "Calum Sinclair killed Drummond over business dispute, "
            "despite apparent alibi."
        ),
        narrative=(
            "Sinclair had clear motive (active dispute over shop sale, "
            "E008) and was the last person known to have spoken to "
            "Drummond (E006). The 18:47 phone call ended frostily. "
            "However, cell tower data (E007) places Sinclair in central "
            "Edinburgh throughout the window of death, and three "
            "independent witnesses plus restaurant records corroborate "
            "his presence at dinner (E008). For this hypothesis to hold, "
            "the alibi would need to be successfully challenged, which "
            "the current evidence does not enable."
        ),
        actors=[
            Actor(name="Calum Sinclair", role=ActorRole.PERPETRATOR),
            Actor(name="Ewan Drummond", role=ActorRole.VICTIM),
        ],
        timeline=[
            HypothesisEvent(
                sequence_index=0,
                timestamp="2022-11-04T18:47:00",
                description="Frosty phone call between Sinclair and Drummond",
                supporting_evidence=["E006", "E008"],
            ),
        ],
        evidence_support=[
            EvidenceSupport(evidence_id="E006", role=SupportRole.SUPPORTS,
                            weight=0.5, note="Last call from Sinclair"),
            EvidenceSupport(evidence_id="E007", role=SupportRole.CONTRADICTS,
                            weight=0.9, note="Cell tower data places Sinclair in Edinburgh"),
            EvidenceSupport(evidence_id="E008", role=SupportRole.CONTRADICTS,
                            weight=0.8, note="Multiple corroborating alibi witnesses"),
        ],
        unexplained_evidence=["E001", "E003", "E010", "E011", "E013"],
        is_exculpatory=False,
    )


# ----------------------------------------------------------------------
# Mocked CEG for the Thomson hypothesis
# ----------------------------------------------------------------------

def _thomson_event_tree(case_id: str) -> EventTree:
    """Event-tree precursor for the CEG-generation stage of the pipeline test.

    Two situations (N1, N2) share branching factor 2, so cegpy's AHC has
    pairs to evaluate. N0 has a single outgoing edge, which cegpy
    handles via its immediate-merge path.
    """
    return EventTree(
        case_id=case_id,
        hypothesis_id="H1",
        nodes=[
            EventTreeNode(id="N0",
                          description="Thomson at The Rowan, 19:06-21:34",
                          associated_evidence=["E003"]),
            EventTreeNode(id="N1",
                          description="Thomson on High Street after leaving pub",
                          associated_evidence=["E003"]),
            EventTreeNode(id="N2",
                          description="Thomson inside the shop with Drummond",
                          associated_evidence=["E001", "E006"]),
            EventTreeNode(id="N3",
                          description="Drummond killed; items taken",
                          associated_evidence=["E004", "E010"]),
            EventTreeNode(id="N4",
                          description="No incident; Thomson goes home"),
            EventTreeNode(id="N5",
                          description="Theft only; no violence",
                          associated_evidence=["E010"]),
        ],
        edges=[
            EventTreeEdge(id="T0", from_node="N0", to_node="N1",
                          event_label="Leaves pub at 21:34",
                          conditional_probability=1.0,
                          associated_evidence=["E003"]),
            EventTreeEdge(id="T1", from_node="N1", to_node="N2",
                          event_label="Walks to shop",
                          conditional_probability=0.7),
            EventTreeEdge(id="T2", from_node="N1", to_node="N4",
                          event_label="Walks home (innocent alternative)",
                          conditional_probability=0.3),
            EventTreeEdge(id="T3", from_node="N2", to_node="N3",
                          event_label="Confrontation; blow to head",
                          conditional_probability=0.75,
                          associated_evidence=["E004", "E005"]),
            EventTreeEdge(id="T4", from_node="N2", to_node="N5",
                          event_label="Theft without violence",
                          conditional_probability=0.25,
                          associated_evidence=["E010"]),
        ],
        root_node_id="N0",
    )

def _thomson_ceg(case_id: str) -> ChainEventGraph:
    """A valid CEG with one branch point: shop visit vs going home."""
    return ChainEventGraph(
        case_id=case_id,
        hypothesis_id="H1",
        nodes=[
            CEGNode(id="N0", type=CEGNodeType.ROOT,
                    description="Thomson at The Rowan, 19:06–21:34",
                    associated_evidence=["E003"]),
            CEGNode(id="N1", type=CEGNodeType.SITUATION,
                    description="Thomson on High Street after leaving pub",
                    associated_evidence=["E003"]),
            CEGNode(id="N2", type=CEGNodeType.SITUATION,
                    description="Thomson inside the shop with Drummond",
                    associated_evidence=["E001", "E006"]),
            CEGNode(id="N3", type=CEGNodeType.LEAF,
                    description="Drummond killed; items taken",
                    associated_evidence=["E004", "E010"]),
            CEGNode(id="N4", type=CEGNodeType.LEAF,
                    description="No incident; Thomson goes home"),
            CEGNode(id="N5", type=CEGNodeType.LEAF,
                    description="Theft only; no violence",
                    associated_evidence=["E010"]),
        ],
        edges=[
            CEGEdge(id="T0", from_node="N0", to_node="N1",
                    event_label="Leaves pub at 21:34",
                    conditional_probability=1.0,
                    associated_evidence=["E003"]),
            CEGEdge(id="T1", from_node="N1", to_node="N2",
                    event_label="Walks to shop",
                    conditional_probability=0.7),
            CEGEdge(id="T2", from_node="N1", to_node="N4",
                    event_label="Walks home (innocent alternative)",
                    conditional_probability=0.3),
            CEGEdge(id="T3", from_node="N2", to_node="N3",
                    event_label="Confrontation; blow to head",
                    conditional_probability=0.75,
                    associated_evidence=["E004", "E005"]),
            CEGEdge(id="T4", from_node="N2", to_node="N5",
                    event_label="Theft without violence",
                    conditional_probability=0.25,
                    associated_evidence=["E010"]),
        ],
        stages=[
            CEGStage(id="S0", member_nodes=["N0"]),
            CEGStage(id="S1", member_nodes=["N1"]),
            CEGStage(id="S2", member_nodes=["N2"]),
            CEGStage(id="S3", member_nodes=["N3"]),
            CEGStage(id="S4", member_nodes=["N4"]),
            CEGStage(id="S5", member_nodes=["N5"]),
        ],
        root_node_id="N0",
        leaf_node_ids=["N3", "N4", "N5"],
    )


# ----------------------------------------------------------------------
# The integration test
# ----------------------------------------------------------------------

def test_pipeline_end_to_end_with_mocks(tmp_path: Path):
    case = _load_toy_case()

    hypotheses = [_h1_thomson(), _h2_sinclair()]

    investigator_client = MockClient(
        name="mock-investigator",
        structured_responses=[
            HypothesisGenerationOutput(hypotheses=hypotheses),  # generate
            HypothesisGenerationOutput(hypotheses=hypotheses),  # revise
            ScoreBundle(scores=[
                HypothesisScore(hypothesis_id="H1", score=0.65,
                                rationale="Strong evidence chain; gaps remain."),
                HypothesisScore(hypothesis_id="H2", score=0.20,
                                rationale="Motive present but alibi robust."),
            ]),
        ],
    )

    forensic_client = MockClient(
        name="mock-forensic",
        structured_responses=[
            CritiqueBundle(critiques=[
                HypothesisCritique(
                    hypothesis_id="H1",
                    strengths=["E003 CCTV evidence is strong",
                               "Theft profile in E010 is consistent"],
                    weaknesses=["E013 cash not directly tied to stolen items",
                                "Weapon not recovered (E005)"],
                    overlooked_evidence=["E011"],
                    suggested_revisions=["Address the partial fingerprint E011"],
                    overall_assessment=(
                        "Plausible primary hypothesis; forensic gaps remain."
                    ),
                ),
                HypothesisCritique(
                    hypothesis_id="H2",
                    strengths=["Clear motive from business dispute"],
                    weaknesses=["E007 cell tower alibi is strong",
                                "E008 has three corroborating witnesses"],
                    overlooked_evidence=[],
                    suggested_revisions=["Explain Sinclair's presence given E007"],
                    overall_assessment="Motive clear but alibi appears robust.",
                ),
            ]),
            ScoreBundle(scores=[
                HypothesisScore(hypothesis_id="H1", score=0.60,
                                rationale="Forensic chain strong with gaps."),
                HypothesisScore(hypothesis_id="H2", score=0.10,
                                rationale="Cell tower alibi is strong."),
            ]),
        ],
    )

    devils_advocate_client = MockClient(
        name="mock-devils-advocate",
        structured_responses=[
            CritiqueBundle(critiques=[
                HypothesisCritique(
                    hypothesis_id="H1",
                    strengths=["Coherent theft narrative"],
                    weaknesses=["Assumes £200 deposit is criminal proceeds",
                                "Partial fingerprint E011 is not Thomson's"],
                    overlooked_evidence=["E011"],
                    suggested_revisions=["Consider whether E011 points elsewhere"],
                    overall_assessment=(
                        "Thomson narrative plausible but E011 unresolved."
                    ),
                ),
                HypothesisCritique(
                    hypothesis_id="H2",
                    strengths=["Direct motive"],
                    weaknesses=["Alibi hard to challenge"],
                    overlooked_evidence=[],
                    suggested_revisions=["Consider conspiracy with third party"],
                    overall_assessment="Surface motive strong; alibi closes the door.",
                ),
            ]),
            ScoreBundle(scores=[
                HypothesisScore(hypothesis_id="H1", score=0.55,
                                rationale="Plausible; E011 unresolved."),
                HypothesisScore(hypothesis_id="H2", score=0.15,
                                rationale="Alibi strong; conspiracy speculative."),
            ]),
        ],
    )

    investigator = Agent(
        name="investigator",
        role="investigator",
        client=investigator_client,
        system_prompt_template="system/investigator.j2",
    )
    forensic = Agent(
        name="forensic_analyst",
        role="critic",
        client=forensic_client,
        system_prompt_template="system/forensic_analyst.j2",
    )
    devils_advocate = Agent(
        name="devils_advocate",
        role="critic",
        client=devils_advocate_client,
        system_prompt_template="system/devils_advocate.j2",
    )

    # ---- Stage A: consortium ----
    ranked = run_consortium(
        case,
        [investigator, forensic, devils_advocate],
        PhasedOrchestrator(),
        max_hypotheses=6,
    )

    assert ranked.case_id == case.metadata.case_id
    assert len(ranked.hypotheses) == 2

    # H1 should rank above H2 — mocked scores favour H1 consistently.
    assert ranked.hypotheses[0].id == "H1"
    assert ranked.hypotheses[0].rank == 1
    assert ranked.hypotheses[1].id == "H2"
    assert ranked.hypotheses[1].rank == 2

    for h in ranked.hypotheses:
        assert h.confidence_score is not None
        assert 0.0 <= h.confidence_score <= 1.0
        # Three agents (investigator + two critics) all scored every hypothesis.
        assert {s.agent_name for s in h.agent_scores} == {
            "investigator", "forensic_analyst", "devils_advocate"
        }

    # Weighted mean of (0.65, 0.60, 0.55) with equal weights = 0.6.
    assert abs(ranked.hypotheses[0].confidence_score - 0.6) < 1e-6
    # Weighted mean of (0.20, 0.10, 0.15) = 0.15.
    assert abs(ranked.hypotheses[1].confidence_score - 0.15) < 1e-6

    # ---- Stage B: CEG generation ----
    ceg_client = MockClient(
        name="mock-ceg",
        structured_responses=[_thomson_event_tree(case.metadata.case_id)],
    )

    top_hypothesis = ranked.hypotheses[0]
    ceg = generate_ceg(case, top_hypothesis, ceg_client)

    assert ceg.case_id == case.metadata.case_id
    assert ceg.hypothesis_id == "H1"
    assert ceg.root_node_id == "N0"
    
    # cegpy collapses terminal positions to a single sink node, so the
    # exact leaf IDs depend on the cegpy/fallback path taken. Just
    # confirm there's at least one leaf.
    assert len(ceg.leaf_node_ids) >= 1

    # ---- Stage C: render to DOT ----
    dot_path = tmp_path / "ceg.dot"
    written = write_ceg_dot(ceg, dot_path)

    assert written == dot_path
    assert dot_path.exists()
    content = dot_path.read_text(encoding="utf-8")
    assert "digraph" in content
    for node in ceg.nodes:
        assert f'"{node.id}"' in content


def test_pipeline_renders_svg_if_graphviz_available(tmp_path: Path):
    """Render the CEG to SVG. Skips if Graphviz binary is not on PATH."""
    pytest.importorskip("graphviz")
    from graphviz import ExecutableNotFound

    case = _load_toy_case()
    ceg = _thomson_ceg(case.metadata.case_id)

    try:
        svg_path = render_ceg_to_svg(ceg, tmp_path / "ceg")
    except ExecutableNotFound:
        pytest.skip("Graphviz binary not on PATH")

    assert svg_path.exists()
    assert svg_path.stat().st_size > 0