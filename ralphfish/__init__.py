"""Ralphfish - LLM Multi-Agent Simulation Engine."""

from .agent import Agent, AgentConfig, create_agents
from .client import OpenRouterClient, ClientConfig, simple_chat, FREE_TIER_MODELS
from .models import (
    AgentPersona,
    Message,
    Fact,
    Dissent,
    Scenario,
    SimulationState,
    InteractionProtocol,
    DEFAULT_PERSONA_TEMPLATE,
)
from .parser import SeedParser, parse_seed, EXTRACTION_PROMPT_TEMPLATE
from .executor import LoopExecutor, run_simulation
from .synthesizer import PredictionSynthesizer, SynthesisReport
from .report_generator import ReportGenerator, generate_report

__all__ = [
    # Agent
    "Agent",
    "AgentConfig",
    "create_agents",
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
    # Executor
    "LoopExecutor",
    "run_simulation",
    # Synthesizer
    "PredictionSynthesizer",
    "SynthesisReport",
    # Report Generator
    "ReportGenerator",
    "generate_report",
]

__version__ = "0.1.0"
