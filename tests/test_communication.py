"""
Tests for inter-agent communication layer (LoopExecutor).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from ralphfish.agent import Agent, AgentPersona, AgentConfig
from ralphfish.client import OpenRouterClient
from ralphfish.models import Message, SimulationState, Scenario, InteractionProtocol
from ralphfish.executor import LoopExecutor, run_simulation


@pytest.fixture
def mock_client():
    """Create a mocked OpenRouter client."""
    client = MagicMock(spec=OpenRouterClient)
    client.chat_completion = AsyncMock(
        return_value={
            "content": "This is a test response.",
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
def personas():
    """Create a list of test personas."""
    return [
        AgentPersona(
            id="agent1",
            name="Alice",
            background="Analyst",
            traits=["analytical"],
            goals=["Understand the scenario"],
            communication_style="clear",
        ),
        AgentPersona(
            id="agent2",
            name="Bob",
            background="Manager",
            traits=["pragmatic"],
            goals=["Make decisions"],
            communication_style="direct",
        ),
    ]


@pytest.fixture
def agents(personas, mock_client):
    """Create agents with no summarization to keep tests simple."""
    agents = []
    for persona in personas:
        config = AgentConfig(enable_summarization=False)
        agent = Agent(persona=persona, client=mock_client, config=config)
        agents.append(agent)
    return agents


@pytest.fixture
def scenario():
    """Create a simple scenario."""
    return Scenario(
        seed_text="Test scenario",
        title="Test Scenario",
        context="A test scenario for unit testing.",
    )


@pytest.fixture
def initial_state(scenario, personas):
    """Create initial simulation state."""
    return SimulationState(
        scenario=scenario, agents=personas, protocol=InteractionProtocol.DISCUSSION
    )


def test_loop_executor_initialization(agents, initial_state):
    """Test LoopExecutor initialization."""
    executor = LoopExecutor(
        agents=agents,
        initial_state=initial_state,
        rounds=3,
        protocol=InteractionProtocol.DISCUSSION,
    )
    assert executor.agents == agents
    assert executor.state == initial_state
    assert executor.rounds == 3
    assert executor.protocol == InteractionProtocol.DISCUSSION


def test_loop_executor_invalid_agents(initial_state):
    """Test LoopExecutor raises error with no agents."""
    with pytest.raises(ValueError, match="At least one agent is required"):
        LoopExecutor(agents=[], initial_state=initial_state, rounds=1)


def test_loop_executor_invalid_rounds(agents, initial_state):
    """Test LoopExecutor raises error with non-positive rounds."""
    with pytest.raises(ValueError, match="Number of rounds must be positive"):
        LoopExecutor(agents=agents, initial_state=initial_state, rounds=0)


@pytest.mark.asyncio
async def test_execute_discussion_basic(agents, initial_state, mock_client):
    """Test that a discussion round produces messages from all agents."""
    executor = LoopExecutor(
        agents=agents,
        initial_state=initial_state,
        rounds=1,
        protocol=InteractionProtocol.DISCUSSION,
    )

    # Mock responses to be different for each agent
    mock_client.chat_completion.side_effect = [
        {
            "content": "Alice's response",
            "model": "test",
            "usage": {},
            "finish_reason": "stop",
            "id": "1",
        },
        {
            "content": "Bob's response",
            "model": "test",
            "usage": {},
            "finish_reason": "stop",
            "id": "2",
        },
    ]

    final_state = await executor.run()

    # Should have 2 messages (one per agent)
    assert len(final_state.message_history) == 2

    # Check round number is 1
    assert final_state.round == 1

    # Verify messages are from correct agents
    agent_ids = [msg.agent_id for msg in final_state.message_history]
    assert "agent1" in agent_ids
    assert "agent2" in agent_ids

    # Each agent should have both messages in their history (broadcast)
    for agent in agents:
        assert len(agent.message_history) == 2


@pytest.mark.asyncio
async def test_visible_messages_calculation(agents, initial_state, mock_client):
    """Test that agents see the correct set of visible messages."""
    executor = LoopExecutor(
        agents=agents,
        initial_state=initial_state,
        rounds=2,
        protocol=InteractionProtocol.DISCUSSION,
    )

    # Manually add some messages to state to test visibility
    msg1 = Message(
        round=1,
        agent_id="agent1",
        agent_name="Alice",
        thought="",
        content="Round 1 message",
    )
    msg2 = Message(
        round=2,
        agent_id="agent1",
        agent_name="Alice",
        thought="",
        content="Round 2 first",
    )
    executor.state.message_history = [msg1, msg2]

    # For agent2 at round 2, visible messages should include:
    # - All messages from round 1 (msg1)
    # - Messages from round 2 that are already in state (msg2) because agent1 already spoke
    visible = executor._get_visible_messages(agents[1], current_round=2)

    assert len(visible) == 2
    assert msg1 in visible
    assert msg2 in visible
    # Should not include any message from agent2 itself (none added)
    assert all(m.agent_id != "agent2" for m in visible)


def test_format_conversation(agents):
    """Test conversation formatting."""
    messages = [
        Message(
            round=1, agent_id="a1", agent_name="Alice", thought="", content="Hello"
        ),
        Message(
            round=1, agent_id="a2", agent_name="Bob", thought="", content="Hi there"
        ),
    ]
    # Need an executor instance for _format_conversation; create minimal
    executor = LoopExecutor(
        agents=agents,  # Use provided agents to satisfy requirement
        initial_state=SimulationState(
            scenario=Scenario(seed_text="test"),
            agents=[],
            protocol=InteractionProtocol.DISCUSSION,
        ),
        rounds=1,
    )
    formatted = executor._format_conversation(messages)
    assert "## Conversation Transcript" in formatted
    assert "[Round 1] Alice: Hello" in formatted
    assert "[Round 1] Bob: Hi there" in formatted


def test_broadcast(agents, initial_state):
    """Test that broadcast sends messages to all agents except the excluded one."""
    executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)

    test_message = Message(
        round=1, agent_id="agent1", agent_name="Alice", thought="", content="Test"
    )
    executor._broadcast(test_message, exclude=agents[0])

    # Agent0 (excluded) should not have received the message
    assert test_message not in agents[0].message_history

    # Agent1 should have received it
    assert test_message in agents[1].message_history

    # Agent2 should have received it
    assert len(agents) > 1
    assert test_message in agents[1].message_history

    # If there are more agents, check them too
    for agent in agents[1:]:
        assert test_message in agent.message_history


@pytest.mark.asyncio
async def test_run_simulation_convenience(agents, scenario, mock_client):
    """Test the run_simulation convenience function."""
    # Disable summarization for all agents via config
    for agent in agents:
        agent.config.enable_summarization = False

    final_state = await run_simulation(
        agents=agents,
        scenario=scenario,
        rounds=1,
        protocol=InteractionProtocol.DISCUSSION,
    )

    assert final_state.round == 1
    assert len(final_state.message_history) == len(agents)


@pytest.mark.asyncio
async def test_multiple_rounds(agents, initial_state, mock_client):
    """Test that multiple rounds accumulate messages correctly."""
    executor = LoopExecutor(
        agents=agents,
        initial_state=initial_state,
        rounds=2,
        protocol=InteractionProtocol.DISCUSSION,
    )

    # Mock responses: 2 agents * 2 rounds = 4 responses
    mock_client.chat_completion.side_effect = [
        {
            "content": f"Response {i}",
            "model": "test",
            "usage": {},
            "finish_reason": "stop",
            "id": str(i),
        }
        for i in range(4)
    ]

    final_state = await executor.run()

    assert final_state.round == 2
    # Should have 4 messages total (2 rounds * 2 agents)
    assert len(final_state.message_history) == 4

    # Each agent's history should have 4 messages (all broadcasts)
    for agent in agents:
        assert len(agent.message_history) == 4

    # Verify round distribution
    round1_msgs = [m for m in final_state.message_history if m.round == 1]
    round2_msgs = [m for m in final_state.message_history if m.round == 2]
    assert len(round1_msgs) == 2
    assert len(round2_msgs) == 2


def test_round_intro_building(agents):
    """Test building round intro context."""
    executor = LoopExecutor(
        agents=agents,
        initial_state=SimulationState(
            scenario=Scenario(seed_text="test", context="Test context"),
            agents=[],
            protocol=InteractionProtocol.DISCUSSION,
        ),
        rounds=3,
    )

    # Round 1 with context should include scenario context
    intro1 = executor._build_round_intro(1)
    assert "Scenario: Test context" in intro1

    # Round 2 should have recap of round 1
    executor.state.round = 1
    intro2 = executor._build_round_intro(2)
    assert "Round 1 recap:" in intro2

    # Round 3 would have recap of round 2
    executor.state.round = 2
    intro3 = executor._build_round_intro(3)
    assert "Round 2 recap:" in intro3


def test_combine_contexts(agents):
    """Test combining contexts."""
    executor = LoopExecutor(
        agents=agents,
        initial_state=SimulationState(
            scenario=Scenario(seed_text="test"),
            agents=[],
            protocol=InteractionProtocol.DISCUSSION,
        ),
        rounds=1,
    )

    combined = executor._combine_contexts("Intro text", "Conversation text")
    assert combined == "Intro text\n\nConversation text"

    # Empty intro
    combined = executor._combine_contexts("", "Conversation")
    assert combined == "Conversation"

    # Empty conversation
    combined = executor._combine_contexts("Intro", "")
    assert combined == "Intro"
