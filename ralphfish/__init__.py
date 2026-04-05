"""Ralphfish - LLM Multi-Agent Simulation Engine."""

from .models import (
    Message,
    Fact,
    Dissent,
    AgentPersona,
    Scenario,
    SimulationState,
    InteractionProtocol,
    DEFAULT_PERSONA_TEMPLATE,
)
from .client import OpenRouterClient, ClientConfig, simple_chat, FREE_TIER_MODELS
from .parser import SeedParser, parse_seed, EXTRACTION_PROMPT_TEMPLATE

__all__ = [
    # Models
    "Message",
    "Fact",
    "Dissent",
    "AgentPersona",
    "Scenario",
    "SimulationState",
    "InteractionProtocol",
    "DEFAULT_PERSONA_TEMPLATE",
    # Client
    "OpenRouterClient",
    "ClientConfig",
    "simple_chat",
    "FREE_TIER_MODELS",
    # Parser
    "SeedParser",
    "parse_seed",
    "EXTRACTION_PROMPT_TEMPLATE",
]

__version__ = "0.1.0"
