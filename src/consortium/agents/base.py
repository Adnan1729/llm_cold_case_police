"""Agent definitions.

An Agent is a framework-agnostic specification of a consortium participant:
its name, its role, the LLM client backing it, the path to its system
prompt template, and its weight in score aggregation. The Orchestrator
interprets these into framework-specific objects at runtime — AutoGen's
AssistantAgent, LangGraph's node, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from consortium.clients.base import LLMClient


@dataclass
class Agent:
    """A participant in the consortium.

    Attributes:
        name: Unique identifier used in logs and per-hypothesis scores.
        role: One of 'investigator', 'critic', 'moderator'. The
            orchestrator decides which roles it needs and may ignore
            roles it doesn't use (e.g. PhasedOrchestrator ignores
            'moderator').
        client: The LLMClient backing this agent.
        system_prompt_template: Path to the Jinja2 system prompt relative
            to the prompts directory, e.g. 'system/investigator.j2'.
        weight: Weight in weighted-mean score aggregation. Defaults to 1.0.
        default_max_tokens: Default max tokens for this agent's responses.
            None means use the client's default.
    """

    name: str
    role: str
    client: LLMClient
    system_prompt_template: str
    weight: float = 1.0
    default_max_tokens: Optional[int] = None