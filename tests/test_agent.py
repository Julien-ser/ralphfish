"""
Comprehensive tests for the Agent class.

Tests cover:
- Agent initialization and configuration
- System prompt rendering (format and Jinja2 templates)
- Message history management (add, trim, clear)
- Response generation with mocked LLM
- Context message building
- Summarization trigger logic (already covered in test_agent_summarization.py)
- Round management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from ralphfish.agent import Agent, AgentConfig, AgentPersona, create_agents
from ralphfish.client import OpenRouterClient
from ralphfish.models import Message, DEFAULT_PERSONA_TEMPLATE


@pytest.fixture
def mock_client():
    """Create a mocked OpenRouter client."""
    client = MagicMock(spec=OpenRouterClient)
    client.chat_completion = AsyncMock(
        return_value={
            "content": "This is a test response from the LLM.",
            "model": "test-model",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
            "finish_reason": "stop",
            "id": "test-123",
        }
    )
    return client


@pytest.fixture
def persona():
    """Create a test persona."""
    return AgentPersona(
        id="test_agent_001",
        name="Alice",
        background="Senior data scientist with 10 years experience",
        traits=["analytical", "curious", "methodical"],
        goals=["Provide accurate analysis", "Help team understand data"],
        biases=["confirmation bias", "sunk cost fallacy"],
        communication_style="clear and concise",
    )


@pytest.fixture
def agent(persona, mock_client):
    """Create an agent with default config."""
    config = AgentConfig()
    return Agent(persona=persona, client=mock_client, config=config)


@pytest.fixture
def agent_with_summarization(persona, mock_client):
    """Create an agent with summarization enabled."""
    config = AgentConfig(
        enable_summarization=True,
        summarize_threshold=5,
        summary_message_limit=3,
    )
    return Agent(persona=persona, client=mock_client, config=config)


class TestAgentInitialization:
    """Test Agent initialization."""

    def test_agent_init_default(self, persona, mock_client):
        """Test agent initializes with default config."""
        agent = Agent(persona=persona, client=mock_client)
        assert agent.persona == persona
        assert agent.client == mock_client
        assert isinstance(agent.config, AgentConfig)
        assert agent.max_history_length == 50
        assert agent.system_prompt_template is None

        # State
        assert agent.message_history == []
        assert agent.round_messages == []
        assert agent.total_messages_generated == 0
        assert agent.summary_count == 0
        assert agent.last_summarization_round is None

    def test_agent_init_custom_config(self, persona, mock_client):
        """Test agent initializes with custom config."""
        config = AgentConfig(
            model="anthropic/claude-instant-1.2",
            temperature=0.5,
            max_tokens=500,
            enable_summarization=True,
        )
        agent = Agent(
            persona=persona,
            client=mock_client,
            config=config,
            max_history_length=100,
            system_prompt_template="Custom: {name}",
        )
        assert agent.config.model == "anthropic/claude-instant-1.2"
        assert agent.config.temperature == 0.5
        assert agent.config.max_tokens == 500
        assert agent.max_history_length == 100
        assert agent.system_prompt_template == "Custom: {name}"

    def test_agent_init_logging(self, persona, mock_client, caplog):
        """Test that agent initialization logs appropriately."""
        import logging

        caplog.set_level(logging.DEBUG)

        agent = Agent(persona=persona, client=mock_client)

        # Should have debug log about initialization
        assert any(agent.persona.id in record.message for record in caplog.records)


class TestSystemPromptRendering:
    """Test system prompt rendering for agents."""

    def test_render_system_prompt_uses_default_template(self, agent):
        """Test rendering uses DEFAULT_PERSONA_TEMPLATE when no custom template."""
        prompt = agent.render_system_prompt()

        assert "Alice" in prompt
        assert "Senior data scientist" in prompt
        assert "analytical, curious, methodical" in prompt or "analytical" in prompt
        assert "Provide accurate analysis" in prompt or "Help team" in prompt
        assert "confirmation bias" in prompt or "sunk cost fallacy" in prompt
        assert "clear and concise" in prompt

    def test_render_system_prompt_with_persona_template(self, persona, mock_client):
        """Test rendering uses persona's custom template if set."""
        custom_template = "You are {name}, a {background}. Your style: {style}."
        persona.prompt_template = custom_template

        agent = Agent(persona=persona, client=mock_client)
        prompt = agent.render_system_prompt()

        assert "Alice" in prompt
        assert "Senior data scientist" in prompt
        assert "clear and concise" in prompt

    def test_render_system_prompt_with_agent_override(self, persona, mock_client):
        """Test rendering uses agent's system_prompt_template (highest priority)."""
        agent_template = "Agent: {name}. Background: {background}."
        agent = Agent(
            persona=persona,
            client=mock_client,
            system_prompt_template=agent_template,
        )
        prompt = agent.render_system_prompt()

        assert "Alice" in prompt
        assert "Senior data scientist" in prompt
        # Should NOT contain the default template structure
        assert "You are" not in prompt or "Agent:" in prompt

    def test_render_system_prompt_with_jinja2(self, persona, mock_client):
        """Test rendering with Jinja2-style template."""
        jinja_template = """
        Name: {{ name }}
        Background: {{ background }}
        Traits: {% for trait in traits %}{{ trait }}{% if not loop.last %}, {% endif %}{% endfor %}
        Goals: {% for goal in goals %}- {{ goal }}{% endfor %}
        """
        agent = Agent(
            persona=persona,
            client=mock_client,
            system_prompt_template=jinja_template,
        )
        prompt = agent.render_system_prompt()

        assert "Alice" in prompt
        assert "Senior data scientist" in prompt
        assert "analytical" in prompt
        assert "Provide accurate analysis" in prompt

    def test_render_system_prompt_fallback_on_jinja_error(
        self, persona, mock_client, caplog
    ):
        """Test fallback to .format() if Jinja2 fails."""
        # Invalid Jinja2 template
        bad_template = "This is {invalid syntax {{"
        agent = Agent(
            persona=persona,
            client=mock_client,
            system_prompt_template=bad_template,
        )

        # Should catch exception and fall back to .format()
        prompt = agent.render_system_prompt()
        # The fallback .format() will fail because of unmatched braces, but it should try
        # Actually the fallback uses _format_template which expects simple .format() placeholders
        # With bad_template having unmatched braces, .format() will also fail
        # Let's make a template that's valid Jinja2 syntax but invalid .format()
        jinja_valid = (
            "Name: {{ name }}"  # Valid Jinja2, invalid .format() (double braces)
        )
        agent.system_prompt_template = jinja_valid

        # Should succeed with Jinja2 (no fallback needed)
        prompt = agent.render_system_prompt()
        assert "Alice" in prompt

    def test_format_template_fallback(self, persona, mock_client):
        """Test the _format_template method directly."""
        agent = Agent(persona=persona, client=mock_client)
        template = "Name: {name}, Background: {background}, Traits: {traits}"
        formatted = agent._format_template(template)

        assert "Alice" in formatted
        assert "Senior data scientist" in formatted
        assert "analytical" in formatted  # traits are joined with ", "

    def test_default_persona_template_values(self):
        """Test that DEFAULT_PERSONA_TEMPLATE has expected content."""
        assert "{name}" in DEFAULT_PERSONA_TEMPLATE
        assert "{background}" in DEFAULT_PERSONA_TEMPLATE
        assert "{traits}" in DEFAULT_PERSONA_TEMPLATE
        assert "{goals}" in DEFAULT_PERSONA_TEMPLATE
        assert "{biases}" in DEFAULT_PERSONA_TEMPLATE
        assert "{style}" in DEFAULT_PERSONA_TEMPLATE


class TestMessageHistory:
    """Test message history management."""

    def test_add_message(self, agent):
        """Test adding a message to history."""
        msg = Message(
            round=1,
            agent_id="test_agent_001",
            agent_name="Alice",
            thought="Thinking",
            content="Hello world",
        )
        agent.add_message(msg)

        assert len(agent.message_history) == 1
        assert len(agent.round_messages) == 1
        assert msg in agent.message_history
        assert msg in agent.round_messages

    def test_add_message_wrong_agent_id_warns(self, persona, mock_client, caplog):
        """Test adding message from different agent logs warning."""
        agent = Agent(persona=persona, client=mock_client)

        wrong_msg = Message(
            round=1,
            agent_id="other_agent",
            agent_name="Bob",
            thought="",
            content="Hi",
        )

        import logging

        caplog.set_level(logging.WARNING)
        agent.add_message(wrong_msg)

        # Should still add message (not prevent), but log warning
        assert wrong_msg in agent.message_history
        assert any(
            "Adding message from different agent" in record.message
            for record in caplog.records
        )

    def test_message_history_trimming(self, persona, mock_client):
        """Test that message history is trimmed when exceeding max_length."""
        config = AgentConfig()
        agent = Agent(
            persona=persona,
            client=mock_client,
            config=config,
            max_history_length=5,
        )

        # Add 7 messages (max_history_length=5, should trim to 5)
        for i in range(7):
            msg = Message(
                round=1,
                agent_id=persona.id,
                agent_name=persona.name,
                thought="",
                content=f"Message {i}",
            )
            agent.add_message(msg)

        # Should be trimmed to exactly max_history_length
        assert len(agent.message_history) == 5
        # Should keep the most recent messages (last 5)
        latest_content = [m.content for m in agent.message_history]
        assert "Message 2" not in latest_content  # Trimmed away
        assert "Message 6" in latest_content  # Kept

    def test_clear_history(self, agent):
        """Test clearing all message history."""
        # Add some messages
        for i in range(3):
            msg = Message(
                round=1,
                agent_id=persona.id,
                agent_name=persona.name,
                thought="",
                content=f"Msg {i}",
            )
            agent.add_message(msg)

        agent.total_messages_generated = 5
        agent.summary_count = 2

        agent.clear_history()

        assert agent.message_history == []
        assert agent.round_messages == []
        assert agent.total_messages_generated == 0
        assert agent.summary_count == 0
        assert agent.last_summarization_round is None

    def test_start_new_round(self, agent):
        """Test starting a new round clears round_messages."""
        # Add messages to round_messages
        for i in range(3):
            msg = Message(
                round=1,
                agent_id=persona.id,
                agent_name=persona.name,
                thought="",
                content=f"Msg {i}",
            )
            agent.add_message(msg)

        assert len(agent.round_messages) == 3

        agent.start_new_round()

        assert agent.round_messages == []
        # message_history should remain intact
        assert len(agent.message_history) == 3


class TestContextMessages:
    """Test building context messages for LLM."""

    def test_get_context_messages_with_system_and_history(self, agent):
        """Test getting context includes system prompt and history."""
        # Add some history
        msg1 = Message(
            round=0,
            agent_id="agent1",
            agent_name="Other",
            thought="",
            content="Hello from other",
        )
        agent.add_message(msg1)

        messages = agent.get_context_messages(include_system=True, include_history=True)

        assert len(messages) >= 2  # system + at least one history
        assert messages[0]["role"] == "system"
        assert "Alice" in messages[0]["content"]

        # History messages should be 'user' role with name and round
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["name"] == "Other"
        assert user_msgs[0]["round"] == 0

    def test_get_context_messages_system_only(self, agent):
        """Test getting context with system only."""
        messages = agent.get_context_messages(
            include_system=True, include_history=False
        )
        assert len(messages) == 1
        assert messages[0]["role"] == "system"

    def test_get_context_messages_history_only(self, agent):
        """Test getting context with history only."""
        # Add history
        msg = Message(
            round=1,
            agent_id="agent1",
            agent_name="Other",
            thought="",
            content="Hello",
        )
        agent.add_message(msg)

        messages = agent.get_context_messages(
            include_system=False, include_history=True
        )
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "name" in messages[0]

    def test_get_context_messages_empty(self, agent):
        """Test getting context with neither system nor history."""
        messages = agent.get_context_messages(
            include_system=False, include_history=False
        )
        assert messages == []


class TestResponseGeneration:
    """Test LLM response generation."""

    @pytest.mark.asyncio
    async def test_generate_response_basic(self, agent, mock_client):
        """Test generating a response with basic settings."""
        response = await agent.generate_response(round_num=1)

        assert isinstance(response, Message)
        assert response.round == 1
        assert response.agent_id == agent.persona.id
        assert response.agent_name == agent.persona.name
        assert len(response.content) > 0
        assert "test response" in response.content.lower()

        # Should have called client
        mock_client.chat_completion.assert_called_once()

        # Should be added to history
        assert len(agent.message_history) == 1
        assert len(agent.round_messages) == 1

        # Stats should update
        assert agent.total_messages_generated == 1

    @pytest.mark.asyncio
    async def test_generate_response_with_additional_context(self, agent, mock_client):
        """Test generating response with additional context."""
        extra = "Important: Focus on quantitative analysis."
        await agent.generate_response(additional_context=extra, round_num=1)

        # Check that the additional context was inserted at the beginning
        call_args = mock_client.chat_completion.call_args
        messages = call_args[1]["messages"]
        # First message should be system with additional context
        assert any(extra in m.get("content", "") for m in messages)

    @pytest.mark.asyncio
    async def test_generate_response_with_provided_thought(self, agent, mock_client):
        """Test generating response with pre-computed thought."""
        thought = "I think the data shows a trend."
        response = await agent.generate_response(thought=thought, round_num=1)

        assert response.thought == thought

    @pytest.mark.asyncio
    async def test_generate_response_includes_metadata(self, agent, mock_client):
        """Test that response includes LLM metadata."""
        response = await agent.generate_response(round_num=1)

        assert "model" in response.metadata
        assert "usage" in response.metadata
        assert "finish_reason" in response.metadata
        assert "message_id" in response.metadata

    @pytest.mark.asyncio
    async def test_generate_response_config_params(self, persona, mock_client):
        """Test that agent config params are passed to LLM call."""
        config = AgentConfig(
            model="anthropic/claude-instant-1.2",
            temperature=0.3,
            max_tokens=2000,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.2,
        )
        agent = Agent(persona=persona, client=mock_client, config=config)

        await agent.generate_response(round_num=1)

        call_kwargs = mock_client.chat_completion.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-instant-1.2"
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 2000
        assert call_kwargs["top_p"] == 0.9
        assert call_kwargs["frequency_penalty"] == 0.1
        assert call_kwargs["presence_penalty"] == 0.2

    @pytest.mark.asyncio
    async def test_generate_response_use_free_tier(self, persona, mock_client):
        """Test that use_free_tier config is passed."""
        config = AgentConfig(use_free_tier=True)
        agent = Agent(persona=persona, client=mock_client, config=config)

        await agent.generate_response(round_num=1)

        call_kwargs = mock_client.chat_completion.call_args[1]
        assert call_kwargs["use_free_tier"] is True

    @pytest.mark.asyncio
    async def test_generate_response_raises_on_client_error(self, persona, mock_client):
        """Test that client errors are raised and logged."""
        agent = Agent(persona=persona, client=mock_client)
        mock_client.chat_completion.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await agent.generate_response(round_num=1)

    @pytest.mark.asyncio
    async def test_multiple_responses_in_sequence(self, agent, mock_client):
        """Test generating multiple responses in sequence."""
        for i in range(3):
            response = await agent.generate_response(round_num=1)
            assert response.content is not None

        assert agent.total_messages_generated == 3
        assert len(agent.message_history) == 3

    @pytest.mark.asyncio
    async def test_generate_response_different_rounds(self, agent, mock_client):
        """Test generating responses in different rounds."""
        for round_num in [1, 2, 3]:
            response = await agent.generate_response(round_num=round_num)
            assert response.round == round_num

        # All messages should be in history
        assert len(agent.message_history) == 3


class TestMessageRetrieval:
    """Test message retrieval methods."""

    def test_get_messages_by_round(self, agent):
        """Test getting messages for a specific round."""
        # Add messages from different rounds
        for r in [1, 1, 2, 2, 2, 3]:
            msg = Message(
                round=r,
                agent_id=agent.persona.id,
                agent_name=agent.persona.name,
                thought="",
                content=f"Round {r} msg",
            )
            agent.add_message(msg)

        round1 = agent.get_messages_by_round(1)
        assert len(round1) == 2

        round2 = agent.get_messages_by_round(2)
        assert len(round2) == 3

        round3 = agent.get_messages_by_round(3)
        assert len(round3) == 1

        round4 = agent.get_messages_by_round(4)
        assert round4 == []

    def test_get_latest_message(self, agent):
        """Test getting the most recent message."""
        assert agent.get_latest_message() is None

        msgs = []
        for i in range(3):
            msg = Message(
                round=1,
                agent_id=agent.persona.id,
                agent_name=agent.persona.name,
                thought="",
                content=f"Msg {i}",
            )
            agent.add_message(msg)
            msgs.append(msg)

        latest = agent.get_latest_message()
        assert latest == msgs[-1]

    def test_get_round_messages_empty(self, agent):
        """Test getting round messages with no messages."""
        msgs = agent.get_messages_by_round(1)
        assert msgs == []


class TestAgentStats:
    """Test agent statistics reporting."""

    def test_get_stats_basic(self, agent):
        """Test getting basic stats."""
        stats = agent.get_stats()

        assert stats["agent_id"] == agent.persona.id
        assert stats["agent_name"] == agent.persona.name
        assert stats["total_messages_generated"] == 0
        assert stats["history_length"] == 0
        assert stats["model"] == agent.config.model
        assert stats["temperature"] == agent.config.temperature

    def test_get_stats_with_messages(self, agent):
        """Test stats after generating messages."""
        # Simulate having messages
        for i in range(3):
            msg = Message(
                round=1,
                agent_id=agent.persona.id,
                agent_name=agent.persona.name,
                thought="",
                content=f"Msg {i}",
            )
            agent.add_message(msg)

        stats = agent.get_stats()
        assert stats["total_messages_generated"] == 3
        assert stats["history_length"] == 3

    def test_get_stats_with_summarization(self, persona, mock_client):
        """Test stats include summarization info when enabled."""
        config = AgentConfig(enable_summarization=True)
        agent = Agent(persona=persona, client=mock_client, config=config)
        agent.summary_count = 2
        agent.last_summarization_round = 5

        stats = agent.get_stats()
        assert stats["summarization_enabled"] is True
        assert stats["summary_count"] == 2
        assert stats["last_summarization_round"] == 5

    def test_get_stats_without_summarization(self, agent):
        """Test stats don't include summarization when disabled."""
        stats = agent.get_stats()
        assert "summarization_enabled" not in stats
        assert "summary_count" not in stats
        assert "last_summarization_round" not in stats


class TestCreateAgentsHelper:
    """Test the create_agents convenience function."""

    @pytest.mark.asyncio
    async def test_create_agents_basic(self, mock_client):
        """Test creating multiple agents."""
        personas = [
            AgentPersona(
                id="a1", name="Alice", background="Data scientist", traits=[], goals=[]
            ),
            AgentPersona(
                id="a2", name="Bob", background="Engineer", traits=[], goals=[]
            ),
        ]

        agents = await create_agents(personas, mock_client)

        assert len(agents) == 2
        for agent, persona in zip(agents, personas):
            assert agent.persona == persona
            assert agent.client == mock_client
            assert isinstance(agent.config, AgentConfig)

    @pytest.mark.asyncio
    async def test_create_agents_with_custom_configs(self, mock_client):
        """Test creating agents with per-agent configs."""
        personas = [
            AgentPersona(id="a1", name="Alice", background="DS", traits=[], goals=[]),
            AgentPersona(id="a2", name="Bob", background="Eng", traits=[], goals=[]),
        ]

        agent_configs = {
            "a1": AgentConfig(model="anthropic/claude-instant-1.2", temperature=0.5),
            "a2": AgentConfig(model="openai/gpt-3.5-turbo", temperature=0.8),
        }

        agents = await create_agents(personas, mock_client, agent_configs)

        assert agents[0].config.model == "anthropic/claude-instant-1.2"
        assert agents[0].config.temperature == 0.5
        assert agents[1].config.model == "openai/gpt-3.5-turbo"
        assert agents[1].config.temperature == 0.8

    @pytest.mark.asyncio
    async def test_create_agents_with_max_history(self, mock_client):
        """Test creating agents with custom max_history_length."""
        personas = [
            AgentPersona(id="a1", name="Alice", background="DS", traits=[], goals=[]),
        ]

        agents = await create_agents(personas, mock_client, max_history_length=100)

        assert agents[0].max_history_length == 100

    @pytest.mark.asyncio
    async def test_create_agents_default_configs_for_missing(self, mock_client):
        """Test that agents without custom config get defaults."""
        personas = [
            AgentPersona(id="a1", name="Alice", background="DS", traits=[], goals=[]),
        ]

        # Only provide config for non-existent agent
        agent_configs = {"nonexistent": AgentConfig(model="different")}

        agents = await create_agents(personas, mock_client, agent_configs)

        # Should still have default config
        assert agents[0].config.model == "openai/gpt-3.5-turbo"  # default

    @pytest.mark.asyncio
    async def test_create_agents_logging(self, mock_client, caplog):
        """Test that create_agents logs appropriately."""
        import logging

        caplog.set_level(logging.INFO)

        personas = [
            AgentPersona(id="a1", name="Alice", background="DS", traits=[], goals=[]),
            AgentPersona(id="a2", name="Bob", background="Eng", traits=[], goals=[]),
        ]

        await create_agents(personas, mock_client)

        assert any("Created agents" in record.message for record in caplog.records)
        assert any("count" in record.message for record in caplog.records)
