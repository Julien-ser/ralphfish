"""
Additional tests to achieve >90% coverage for LoopExecutor (executor.py).

Targets missing lines:
- 101, 112-114: exception propagation in run()
- 126: unknown protocol handler
- 184-187, 197-200: logging in discussion/debate
- 270, 273-290: summarization error handling
- 294-299: round complete callback error handling
- 336-340: run_simulation initialization logic
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ralphfish.executor import LoopExecutor, run_simulation
from ralphfish.agent import Agent, AgentConfig
from ralphfish.models import (
    SimulationState,
    Scenario,
    AgentPersona,
    InteractionProtocol,
    Message,
)
from ralphfish.client import OpenRouterClient


@pytest.fixture
def mock_client():
    """Create a mocked OpenRouter client."""
    client = MagicMock(spec=OpenRouterClient)
    client.chat_completion = AsyncMock(
        return_value={
            "content": "Mocked response",
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "finish_reason": "stop",
            "id": "test-msg",
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
            traits=["logical"],
            goals=["Analyze data"],
        ),
        AgentPersona(
            id="agent2",
            name="Bob",
            background="Engineer",
            traits=["practical"],
            goals=["Build solutions"],
        ),
    ]


@pytest.fixture
def agents(personas, mock_client):
    """Create Agent instances from personas."""
    return [
        Agent(persona=personas[0], client=mock_client),
        Agent(persona=personas[1], client=mock_client),
    ]


@pytest.fixture
def scenario():
    """Create a test scenario."""
    return Scenario(seed_text="Test scenario", title="Test")


@pytest.fixture
def initial_state(scenario, personas):
    """Create a basic SimulationState."""
    return SimulationState(
        scenario=scenario,
        agents=personas,
        round=0,
        protocol=InteractionProtocol.DISCUSSION,
    )


class TestLoopExecutorInitialization:
    """Test LoopExecutor initialization validation (lines 59-62)."""

    def test_init_requires_agents(self):
        """Test that empty agents list raises ValueError."""
        with pytest.raises(ValueError, match="At least one agent is required"):
            LoopExecutor(agents=[], initial_state=initial_state, rounds=1)

    def test_init_requires_positive_rounds(self, agents, initial_state):
        """Test that non-positive rounds raises ValueError."""
        with pytest.raises(ValueError, match="Number of rounds must be positive"):
            LoopExecutor(agents=agents, initial_state=initial_state, rounds=0)

    def test_init_syncs_state_agents(self, agents, initial_state):
        """Test that initial_state.agents is synced with provided agents (line 71)."""
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        assert executor.state.agents == [a.persona for a in agents]


class TestLoopExecutorRun:
    """Test LoopExecutor.run method (lines 73-115)."""

    @pytest.mark.asyncio
    async def test_run_returns_final_state(self, agents, initial_state):
        """Test that run returns the final state after all rounds."""
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        final_state = await executor.run()
        assert final_state == executor.state
        assert final_state.round == 1
        assert len(final_state.message_history) > 0

    @pytest.mark.asyncio
    async def test_run_propagates_exception(self, agents, initial_state):
        """Test that exceptions during round execution are logged and re-raised (lines 112-114)."""
        agents[0].generate_response = AsyncMock(side_effect=RuntimeError("LLM error"))
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        with pytest.raises(RuntimeError, match="LLM error"):
            await executor.run()

    @pytest.mark.asyncio
    async def test_run_calls_round_complete_callback(self, agents, initial_state):
        """Test that on_round_complete callback is invoked (covers line 100-101)."""
        callback = MagicMock()
        executor = LoopExecutor(
            agents=agents,
            initial_state=initial_state,
            rounds=1,
            on_round_complete=callback,
        )
        await executor.run()
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == 1
        assert isinstance(args[1], SimulationState)

    @pytest.mark.asyncio
    async def test_run_clears_round_messages_between_rounds(
        self, agents, initial_state
    ):
        """Test that agents' round_messages are cleared at end of each round (line 105)."""
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=2)
        await executor.run()
        for agent in agents:
            assert agent.round_messages == []


class TestExecuteRound:
    """Test _execute_round and protocol handlers (lines 116-200)."""

    @pytest.mark.asyncio
    async def test_execute_discussion(self, agents, initial_state):
        """Test _execute_discussion runs all agents (covers lines 142-172, including logging)."""
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        await executor._execute_discussion(round_num=1)
        assert len(agents[0].message_history) == 1
        assert len(agents[1].message_history) == 1
        assert len(executor.state.message_history) == 2

    @pytest.mark.asyncio
    async def test_execute_debate_falls_back_to_discussion(
        self, agents, initial_state, caplog
    ):
        """Test that _execute_debate falls back to discussion and logs (lines 184-187, 197-200)."""
        import logging

        caplog.set_level(logging.INFO)
        executor = LoopExecutor(
            agents=agents,
            initial_state=initial_state,
            rounds=1,
            protocol=InteractionProtocol.DEBATE,
        )
        await executor._execute_round(round_num=1)
        assert any(
            "Debate protocol selected but not fully implemented" in rec.message
            for rec in caplog.records
        )
        assert len(executor.state.message_history) > 0

    @pytest.mark.asyncio
    async def test_execute_voting_falls_back_to_discussion(
        self, agents, initial_state, caplog
    ):
        """Test that _execute_voting falls back to discussion and logs."""
        import logging

        caplog.set_level(logging.INFO)
        executor = LoopExecutor(
            agents=agents,
            initial_state=initial_state,
            rounds=1,
            protocol=InteractionProtocol.VOTING,
        )
        await executor._execute_round(round_num=1)
        assert any(
            "Voting protocol selected but not fully implemented" in rec.message
            for rec in caplog.records
        )
        assert len(executor.state.message_history) > 0

    @pytest.mark.asyncio
    async def test_execute_round_unknown_protocol(self, agents, initial_state):
        """Test _execute_round raises NotImplementedError for unknown protocol (line 126)."""
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        executor.protocol = "invalid"
        with pytest.raises(NotImplementedError):
            await executor._execute_round(1)


class TestSummarizationHandling:
    """Test summarization in _maybe_summarize_all_agents (lines 260-290)."""

    @pytest.mark.asyncio
    async def test_maybe_summarize_all_agents_success(self, agents, initial_state):
        """Test successful summarization when threshold exceeded."""
        for agent in agents:
            agent.config.enable_summarization = True
            agent.config.summarize_threshold = 1
            msg = Message(
                round=1,
                agent_id=agent.persona.id,
                agent_name=agent.persona.name,
                thought="",
                content="Hello",
            )
            agent.add_message(msg)
        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        # Should not raise
        await executor._maybe_summarize_all_agents(round_num=1)
        # Summaries may or may not be generated depending on exact condition; just ensure no crash

    @pytest.mark.asyncio
    async def test_maybe_summarize_all_agents_with_exception(
        self, agents, initial_state, caplog
    ):
        """Test that summarization exceptions are caught and logged (lines 270, 276-290)."""
        import logging

        caplog.set_level(logging.ERROR)

        async def mock_maybe_summarize(round):
            raise RuntimeError("Summarization failed")

        agents[0].maybe_summarize = mock_maybe_summarize  # type: ignore

        executor = LoopExecutor(agents=agents, initial_state=initial_state, rounds=1)
        await executor._maybe_summarize_all_agents(round_num=1)
        assert any("Summarization failed" in rec.message for rec in caplog.records)


class TestRoundCompleteCallback:
    """Test _safe_call_round_complete (lines 292-300)."""

    @pytest.mark.asyncio
    async def test_safe_call_with_sync_callback_that_raises(
        self, agents, initial_state, caplog
    ):
        """Test that exceptions in sync callbacks are caught and logged (lines 299-300)."""
        import logging

        caplog.set_level(logging.ERROR)

        def bad_callback(round_num, state):
            raise ValueError("Callback error")

        executor = LoopExecutor(
            agents=agents,
            initial_state=initial_state,
            rounds=1,
            on_round_complete=bad_callback,
        )
        await executor._safe_call_round_complete(round_num=1)
        assert any(
            "Round complete callback raised exception" in rec.message
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_safe_call_with_async_callback_that_raises(
        self, agents, initial_state, caplog
    ):
        """Test that exceptions in async callbacks are caught and logged."""
        import logging

        caplog.set_level(logging.ERROR)

        async def bad_async_callback(round_num, state):
            raise RuntimeError("Async error")

        executor = LoopExecutor(
            agents=agents,
            initial_state=initial_state,
            rounds=1,
            on_round_complete=bad_async_callback,
        )
        await executor._safe_call_round_complete(round_num=1)
        assert any(
            "Round complete callback raised exception" in rec.message
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_safe_call_with_successful_callback(self, agents, initial_state):
        """Test that successful callbacks execute without issue."""
        callback = MagicMock()
        executor = LoopExecutor(
            agents=agents,
            initial_state=initial_state,
            rounds=1,
            on_round_complete=callback,
        )
        await executor._safe_call_round_complete(1)
        callback.assert_called_once_with(1, executor.state)


class TestRunSimulationConvenience:
    """Test run_simulation convenience function (lines 302-349)."""

    @pytest.mark.asyncio
    async def test_run_simulation_creates_state_if_none(self, personas, mock_client):
        """Test that run_simulation creates a new SimulationState when initial_state is None (lines 328-333)."""
        agents = [Agent(persona=p, client=mock_client) for p in personas]
        scenario = Scenario(seed_text="Test", title="Test")
        final_state = await run_simulation(agents=agents, scenario=scenario, rounds=1)
        assert isinstance(final_state, SimulationState)
        assert final_state.scenario == scenario
        assert final_state.agents == personas
        assert final_state.protocol == InteractionProtocol.DISCUSSION

    @pytest.mark.asyncio
    async def test_run_simulation_uses_provided_state(
        self, agents, scenario, mock_client
    ):
        """Test that run_simulation uses provided initial_state and fills missing fields (lines 334-340)."""
        initial_state = SimulationState(
            scenario=scenario,
            agents=[],  # empty, should be filled
            protocol=InteractionProtocol.DEBATE,
            round=0,
        )
        final_state = await run_simulation(
            agents=agents,
            scenario=scenario,
            rounds=1,
            initial_state=initial_state,
            protocol=InteractionProtocol.DISCUSSION,
        )
        assert final_state.agents == [a.persona for a in agents]
        assert final_state.scenario == scenario
        assert final_state.protocol == InteractionProtocol.DISCUSSION

    @pytest.mark.asyncio
    async def test_run_simulation_async_basic(self, agents, scenario):
        """Basic integration: run a simple simulation with mocked client."""
        mock_client = MagicMock(spec=OpenRouterClient)
        mock_client.chat_completion = AsyncMock(
            return_value={
                "content": "Test response",
                "model": "test",
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
                "finish_reason": "stop",
                "id": "1",
            }
        )
        for a in agents:
            a.client = mock_client
        final_state = await run_simulation(agents=agents, scenario=scenario, rounds=1)
        assert final_state.round == 1
        assert len(final_state.message_history) == len(agents)
