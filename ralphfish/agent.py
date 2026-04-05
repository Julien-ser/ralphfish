"""
Agent class implementing persona-based LLM interactions with isolated state.

Each Agent has:
- A persona (AgentPersona) defining identity and behavior
- Isolated message history per agent
- Per-agent LLM configuration (model, temperature, etc.)
- Persona template rendering with Jinja2 support
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field

from .client import OpenRouterClient
from .models import AgentPersona, Message, DEFAULT_PERSONA_TEMPLATE

logger = logging.getLogger(__name__)


class AgentConfig(BaseModel):
    """Configuration for an individual agent's LLM behavior."""

    model: str = Field(
        default="openai/gpt-3.5-turbo",
        description="Model to use for this agent (overrides client default)",
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1, le=4000)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    use_free_tier: bool = Field(
        default=False, description="Force use of free-tier models"
    )


class Agent:
    """
    An autonomous agent with a persona, message history, and LLM isolation.

    Agents maintain their own conversation context and can be configured
    individually for model, temperature, and other LLM parameters while
    sharing an underlying OpenRouter client for connection pooling.
    """

    def __init__(
        self,
        persona: AgentPersona,
        client: OpenRouterClient,
        config: Optional[AgentConfig] = None,
        max_history_length: int = 50,
        system_prompt_template: Optional[str] = None,
    ):
        """
        Initialize an agent with persona and LLM configuration.

        Args:
            persona: AgentPersona defining identity and behavior
            client: Shared OpenRouterClient instance
            config: Agent-specific LLM parameters (uses client defaults if None)
            max_history_length: Maximum messages to retain in context window
            system_prompt_template: Optional custom Jinja2 template for system prompt
        """
        self.persona = persona
        self.client = client
        self.config = config or AgentConfig()
        self.max_history_length = max_history_length
        self.system_prompt_template = system_prompt_template

        # Isolated state per agent
        self.message_history: List[Message] = []
        self.round_messages: List[Message] = []  # Messages from current round only
        self.total_messages_generated: int = 0

        logger.debug(
            "Agent initialized",
            extra={
                "agent_id": persona.id,
                "agent_name": persona.name,
                "model": self.config.model,
            },
        )

    def render_system_prompt(self) -> str:
        """
        Render the system prompt for this agent using persona data.

        Uses either:
        1. Custom system_prompt_template if provided
        2. AgentPersona's prompt_template if set
        3. Default global DEFAULT_PERSONA_TEMPLATE

        Returns:
            Formatted system prompt string
        """
        template = (
            self.system_prompt_template
            or self.persona.prompt_template
            or DEFAULT_PERSONA_TEMPLATE
        )

        # Support both Jinja2-style and .format() style templates
        if "{{" in template or "{%" in template:
            try:
                from jinja2 import Template

                jinja_template = Template(template)
                return jinja_template.render(
                    name=self.persona.name,
                    background=self.persona.background,
                    traits=", ".join(self.persona.traits),
                    goals=self.persona.goals,
                    biases=self.persona.biases,
                    style=self.persona.communication_style,
                )
            except ImportError:
                logger.warning("Jinja2 not available, falling back to .format()")
                return self._format_template(template)
            except Exception as e:
                logger.error("Jinja2 rendering failed", extra={"error": str(e)})
                return self._format_template(template)
        else:
            return self._format_template(template)

    def _format_template(self, template: str) -> str:
        """Simple .format() based template rendering."""
        return template.format(
            name=self.persona.name,
            background=self.persona.background,
            traits=", ".join(self.persona.traits),
            goals="\n- ".join(self.persona.goals),
            biases=", ".join(self.persona.biases) if self.persona.biases else "None",
            style=self.persona.communication_style,
        )

    def add_message(self, message: Message) -> None:
        """
        Add a message to this agent's history.

        Args:
            message: Message object to add (should have agent_id matching this agent)
        """
        if message.agent_id != self.persona.id:
            logger.warning(
                "Adding message from different agent",
                extra={
                    "agent_id": self.persona.id,
                    "message_agent_id": message.agent_id,
                },
            )

        self.message_history.append(message)
        self.round_messages.append(message)

        # Trim history if exceeding max length
        if len(self.message_history) > self.max_history_length:
            removed = self.message_history[: -self.max_history_length]
            self.message_history = self.message_history[-self.max_history_length :]
            logger.debug(
                "Trimmed message history",
                extra={"agent_id": self.persona.id, "removed_count": len(removed)},
            )

    def start_new_round(self) -> None:
        """Mark the start of a new round, clearing round-specific messages."""
        self.round_messages = []

    def get_context_messages(
        self, include_system: bool = True, include_history: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Build the message context for LLM API call.

        Args:
            include_system: Include system prompt
            include_history: Include previous message history

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        messages: List[Dict[str, Any]] = []

        if include_system:
            system_prompt = self.render_system_prompt()
            messages.append({"role": "system", "content": system_prompt})

        if include_history:
            for msg in self.message_history:
                # All messages from this agent's perspective are 'user' (input context)
                # Other agents' messages provide the conversation history
                messages.append(
                    {
                        "role": "user",
                        "content": msg.content,
                        "name": msg.agent_name,
                        "round": msg.round,
                    }
                )

        return messages

    async def generate_response(
        self,
        additional_context: Optional[str] = None,
        round_num: int = 0,
        thought: Optional[str] = None,
    ) -> Message:
        """
        Generate a response using the LLM with isolated agent state.

        Args:
            additional_context: Optional extra context to prepend to messages
            round_num: Current round number for the generated message
            thought: Optional pre-computed thought (if None, will be part of response)

        Returns:
            Message object containing the agent's response
        """
        messages = self.get_context_messages(include_system=True, include_history=True)

        if additional_context:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"Additional context:\n{additional_context}",
                },
            )

        try:
            response = await self.client.chat_completion(
                messages=messages,
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                use_free_tier=self.config.use_free_tier,
            )

            content = response["content"]

        except Exception as e:
            logger.error(
                "Failed to generate response",
                extra={
                    "agent_id": self.persona.id,
                    "agent_name": self.persona.name,
                    "error": str(e),
                },
            )
            raise

        # Create message
        message = Message(
            round=round_num,
            agent_id=self.persona.id,
            agent_name=self.persona.name,
            thought=thought or "",  # Could be extracted from content with parsing
            content=content,
            metadata={
                "model": response.get("model"),
                "usage": response.get("usage", {}),
                "finish_reason": response.get("finish_reason"),
                "message_id": response.get("id"),
            },
        )

        # Update state
        self.add_message(message)
        self.total_messages_generated += 1

        logger.debug(
            "Generated response",
            extra={
                "agent_id": self.persona.id,
                "round": round_num,
                "content_length": len(content),
                "total_generated": self.total_messages_generated,
            },
        )

        return message

    def get_messages_by_round(self, round_num: int) -> List[Message]:
        """Get all messages from this agent for a specific round."""
        return [msg for msg in self.round_messages if msg.round == round_num]

    def get_latest_message(self) -> Optional[Message]:
        """Get the most recent message generated by this agent."""
        return self.message_history[-1] if self.message_history else None

    def clear_history(self) -> None:
        """Clear all message history for this agent."""
        self.message_history = []
        self.round_messages = []
        self.total_messages_generated = 0
        logger.debug("Cleared agent history", extra={"agent_id": self.persona.id})

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for this agent."""
        return {
            "agent_id": self.persona.id,
            "agent_name": self.persona.name,
            "total_messages_generated": self.total_messages_generated,
            "history_length": len(self.message_history),
            "model": self.config.model,
            "temperature": self.config.temperature,
        }


# Convenience function to create agents from persona list
async def create_agents(
    personas: List[AgentPersona],
    client: OpenRouterClient,
    agent_configs: Optional[Dict[str, AgentConfig]] = None,
    max_history_length: int = 50,
) -> List[Agent]:
    """
    Create multiple agents with shared client and individual configurations.

    Args:
        personas: List of AgentPersona objects
        client: Shared OpenRouterClient instance
        agent_configs: Optional dict mapping agent_id to AgentConfig
        max_history_length: History limit for all agents

    Returns:
        List of initialized Agent objects
    """
    agents = []
    configs = agent_configs or {}

    for persona in personas:
        config = configs.get(persona.id, AgentConfig())
        agent = Agent(
            persona=persona,
            client=client,
            config=config,
            max_history_length=max_history_length,
        )
        agents.append(agent)

    logger.info(
        "Created agents",
        extra={"count": len(agents), "agent_ids": [a.persona.id for a in agents]},
    )

    return agents
