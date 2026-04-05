"""
Tests for Agent memory summarization functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from ralphfish.agent import Agent, AgentConfig, AgentPersona, create_agents
from ralphfish.client import OpenRouterClient
from ralphfish.models import Message


@pytest.fixture
def mock_client():
    """Create a mocked OpenRouter client."""
    client = MagicMock(spec=OpenRouterClient)
    client.chat_completion = AsyncMock(
        return_value={
            "content": "Summary: Agents discussed the scenario and agreed on key points.",
            "model": "test-model",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
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
        id="agent1",
        name="Test Agent",
        background="A test agent",
        traits=["analytical", "cooperative"],
        goals=["Understand the scenario"],
        communication_style="clear and concise",
    )


@pytest.fixture
def agent_config():
    """Create agent config with summarization enabled."""
    return AgentConfig(
        enable_summarization=True,
        summarize_threshold=5,
        summary_message_limit=3,
    )


@pytest.fixture
def agent(persona, mock_client, agent_config):
    """Create an agent with summarization enabled."""
    return Agent(
        persona=persona,
        client=mock_client,
        config=agent_config,
        max_history_length=50,
    )


def test_agent_config_summarization_defaults():
    """Test that summarization defaults are set correctly."""
    config = AgentConfig()
    assert config.enable_summarization is False
    assert config.summarize_threshold == 30
    assert config.summary_message_limit == 5
    assert config.summarization_interval == 0


def test_agent_config_summarization_enabled():
    """Test custom summarization settings."""
    config = AgentConfig(
        enable_summarization=True,
        summarize_threshold=10,
        summary_message_limit=2,
        summarization_interval=2,
    )
    assert config.enable_summarization is True
    assert config.summarize_threshold == 10
    assert config.summary_message_limit == 2
    assert config.summarization_interval == 2


def test_agent_initialization_with_summarization(persona, mock_client, agent_config):
    """Test agent initializes summarization stats correctly."""
    agent = Agent(persona, mock_client, agent_config)
    assert agent.summary_count == 0
    assert agent.last_summarization_round is None


def test_should_summarize_disabled(persona, mock_client):
    """Test _should_summarize returns False when disabled."""
    config = AgentConfig(enable_summarization=False)
    agent = Agent(persona, mock_client, config)
    assert agent._should_summarize(1) is False


def test_should_summarize_threshold(persona, mock_client):
    """Test summarization triggers when threshold is exceeded."""
    config = AgentConfig(
        enable_summarization=True,
        summarize_threshold=5,
        summarization_interval=0,  # Disable periodic
    )
    agent = Agent(persona, mock_client, config)

    # Below threshold
    agent.message_history = [
        Message(round=0, agent_id="a1", agent_name="A", thought="", content="test1")
    ]
    assert agent._should_summarize(1) is False

    # At threshold
    agent.message_history = [
        Message(round=0, agent_id="a1", agent_name="A", thought="", content=f"test{i}")
        for i in range(5)
    ]
    assert agent._should_summarize(1) is True


def test_should_summarize_periodic(persona, mock_client):
    """Test periodic summarization based on interval."""
    config = AgentConfig(
        enable_summarization=True,
        summarization_interval=2,
    )
    agent = Agent(persona, mock_client, config)
    agent.last_summarization_round = None

    # Round 2 should trigger (interval = 2)
    assert agent._should_summarize(2) is True
    agent.last_summarization_round = 2

    # Round 3 should not trigger
    assert agent._should_summarize(3) is False

    # Round 4 should trigger
    assert agent._should_summarize(4) is True


@pytest.mark.asyncio
async def test_summarize_old_messages(persona, mock_client):
    """Test that summarization replaces old messages with a summary."""
    config = AgentConfig(
        enable_summarization=True,
        summarize_threshold=3,
        summary_message_limit=2,
        summarization_interval=0,
    )
    agent = Agent(persona, mock_client, config)

    # Add enough messages to trigger summarization
    for i in range(5):
        msg = Message(
            round=1, agent_id="a1", agent_name="A", thought="", content=f"Message {i}"
        )
        agent.add_message(msg)

    assert len(agent.message_history) == 5

    # Trigger summarization
    summary = await agent.summarize_old_messages(current_round=1)

    assert summary is not None
    assert summary.content.startswith("[SUMMARY")
    # With 5 messages, n = min(2, 5//2=2) = 2; new length = (5-2) + 1 = 4
    assert len(agent.message_history) == 4
    assert agent.summary_count == 1
    assert agent.last_summarization_round == 1


@pytest.mark.asyncio
async def test_summarize_old_messages_with_llm_call(persona, mock_client):
    """Test that summarization calls the LLM."""
    agent_config = AgentConfig(
        enable_summarization=True,
        summarize_threshold=3,
        summary_message_limit=2,
        summarization_interval=0,
    )
    agent = Agent(persona, mock_client, agent_config)

    # Add messages
    for i in range(3):
        msg = Message(
            round=1, agent_id="a1", agent_name="A", thought="", content=f"Message {i}"
        )
        agent.add_message(msg)

    # Mock the client.chat_completion to track calls
    mock_client.chat_completion = AsyncMock(
        return_value={
            "content": "Mocked summary",
            "model": "test",
            "usage": {},
            "finish_reason": "stop",
            "id": "123",
        }
    )

    summary = await agent.summarize_old_messages(current_round=1)

    assert summary is not None
    assert "Mocked summary" in summary.content
    mock_client.chat_completion.assert_called_once()


def test_get_stats_with_summarization(persona, mock_client, agent_config):
    """Test that get_stats includes summarization info."""
    agent = Agent(persona, mock_client, agent_config)
    agent.summary_count = 2
    agent.last_summarization_round = 3

    stats = agent.get_stats()
    assert stats["summarization_enabled"] is True
    assert stats["summary_count"] == 2
    assert stats["last_summarization_round"] == 3
