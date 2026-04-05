"""
Base data models for the Wiggum loop simulation.

Defines the core entities: Scenario, AgentPersona, SimulationState, Message, and Fact.
All models use Pydantic v2 for validation and serialization.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class InteractionProtocol(str, Enum):
    """Supported interaction protocols for agent communication."""

    DISCUSSION = "discussion"
    DEBATE = "debate"
    VOTING = "voting"


class Message(BaseModel):
    """A single message/action from an agent during a round."""

    round: int
    agent_id: str
    agent_name: str
    thought: str = Field(..., description="Agent's internal reasoning")
    content: str = Field(..., description="Public message/action")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class Fact(BaseModel):
    """A discrete piece of information extracted from messages."""

    key: str
    value: Any
    source_agent_id: Optional[str] = None
    round_extracted: int
    confidence: float = Field(default=0.1, ge=0.0, le=1.0)
    evidence: List[str] = Field(
        default_factory=list, description="Supporting text snippets"
    )

    def update_confidence(self, delta: float) -> float:
        """Update confidence by delta, clamping to [0, 1]."""
        self.confidence = max(0.0, min(1.0, self.confidence + delta))
        return self.confidence


class Dissent(BaseModel):
    """Record of a disagreement between agents."""

    fact_key: str
    values: List[Any]
    agent_ids: List[str]
    round_introduced: int
    resolution: Optional[Dict[str, Any]] = None  # How it was resolved (if at all)

    @field_validator("agent_ids")
    @classmethod
    def validate_unique_agents(cls, v: List[str]) -> List[str]:
        if len(v) != len(set(v)):
            raise ValueError("Agent IDs must be unique")
        return v


class AgentPersona(BaseModel):
    """
    Identity template for an LLM-powered agent.

    Personas shape how the agent thinks and communicates through the LLM.
    """

    id: str
    name: str
    background: str = Field(..., description="Personal history, profession, expertise")
    traits: List[str] = Field(default_factory=list, description="Personality traits")
    goals: List[str] = Field(default_factory=list, description="Primary objectives")
    biases: List[str] = Field(
        default_factory=list, description="Known biases or tendencies"
    )
    communication_style: str = Field(
        default="balanced",
        description="How the agent communicates (formal, casual, aggressive, etc.)",
    )
    prompt_template: Optional[str] = Field(
        default=None, description="Custom Jinja2 template for rendering persona prompts"
    )

    def render_prompt(self, template: Optional[str] = None) -> str:
        """
        Render persona into a system prompt for the LLM.

        Args:
            template: Optional custom Jinja2 template; uses default if None

        Returns:
            Formatted system prompt string
        """
        tpl = template or self.prompt_template or DEFAULT_PERSONA_TEMPLATE

        # Simple string formatting (can be upgraded to Jinja2)
        return tpl.format(
            name=self.name,
            background=self.background,
            traits=", ".join(self.traits),
            goals="\n- ".join(self.goals),
            biases=", ".join(self.biases) if self.biases else "None",
            style=self.communication_style,
        )


class Scenario(BaseModel):
    """
    Initial scenario/seed for the simulation.

    Contains the raw input text and any pre-extracted entities/relationships.
    """

    seed_text: str
    title: Optional[str] = None
    context: Optional[str] = None
    extracted_entities: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    initial_facts: List[Fact] = Field(default_factory=list)

    def to_prompt(self) -> str:
        """Convert scenario to a prompt for parsing/analysis."""
        prompt = f"Scenario: {self.seed_text}\n"
        if self.context:
            prompt += f"Context: {self.context}\n"
        return prompt


class SimulationState(BaseModel):
    """
    Complete state of the simulation at any point.

    This is the central state object that gets updated each round.
    """

    round: int = 0
    scenario: Scenario
    agents: List[AgentPersona]
    world_facts: Dict[str, Fact] = Field(default_factory=dict)
    message_history: List[Message] = Field(default_factory=list)
    aggregated_facts: List[Fact] = Field(default_factory=list)
    dissent_points: List[Dissent] = Field(default_factory=list)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    protocol: InteractionProtocol = InteractionProtocol.DISCUSSION
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_agent(self, agent_id: str) -> Optional[AgentPersona]:
        """Retrieve agent by ID."""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def get_round_messages(self, round_num: int) -> List[Message]:
        """Get all messages from a specific round."""
        return [m for m in self.message_history if m.round == round_num]

    def get_fact(self, key: str) -> Optional[Fact]:
        """Get fact by key."""
        return self.world_facts.get(key)

    def add_fact(self, fact: Fact) -> None:
        """Add or update a fact in world_facts."""
        if fact.key in self.world_facts:
            existing = self.world_facts[fact.key]
            # Merge evidence
            existing.evidence.extend(fact.evidence)
            existing.update_confidence(fact.confidence)
        else:
            self.world_facts[fact.key] = fact

    def to_dict(self, include_messages: bool = True) -> Dict[str, Any]:
        """
        Convert state to dictionary for serialization.

        Args:
            include_messages: Whether to include full message history

        Returns:
            Dictionary representation
        """
        data = self.model_dump()
        if not include_messages:
            data.pop("message_history", None)
        return data

    def get_round_summary(self, round_num: int) -> Dict[str, Any]:
        """Generate a summary of a specific round."""
        messages = self.get_round_messages(round_num)
        facts_this_round = [
            f for f in self.aggregated_facts if f.round_extracted == round_num
        ]

        return {
            "round": round_num,
            "message_count": len(messages),
            "participants": list(set(m.agent_id for m in messages)),
            "new_facts": len(facts_this_round),
            "facts": [f.model_dump() for f in facts_this_round],
        }


# Default persona template (can be overridden per agent)
DEFAULT_PERSONA_TEMPLATE = """
You are {name}, a {background}.

**Personality Traits:** {traits}

**Goals:**
- {goals}

**Potential Biases:** {biases}

**Communication Style:** {style}

You are participating in a multi-agent simulation. Engage with other agents constructively,
provide reasoned responses, and work towards the simulation objectives while staying
true to your persona.
""".strip()


# Export all models
__all__ = [
    "Message",
    "Fact",
    "Dissent",
    "AgentPersona",
    "Scenario",
    "SimulationState",
    "InteractionProtocol",
    "DEFAULT_PERSONA_TEMPLATE",
]
