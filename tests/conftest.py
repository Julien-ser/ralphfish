"""
Shared test fixtures and utilities for ralphfish tests.

This module provides common fixtures used across multiple test files,
including mock OpenRouter clients and sample data objects.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from pydantic import BaseModel

from ralphfish.models import (
    AgentPersona,
    Scenario,
    SimulationState,
    Message,
    Fact,
    InteractionProtocol,
    DEFAULT_PERSONA_TEMPLATE,
)
from ralphfish.client import OpenRouterClient, ClientConfig
from ralphfish.agent import Agent, AgentConfig
from ralphfish.persona_generator import (
    PersonaGenerator,
    PersonaGeneratorConfig,
    PersonaConstraints,
    Archetype,
)


# ==================== Mock OpenRouter Fixtures ====================


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI API response."""

    def _create_response(content: str, model: str = "gpt-3.5-turbo"):
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = model
        mock_response.id = "test-123"
        mock_response.response_ms = 500

        return mock_response

    return _create_response


@pytest.fixture
def mock_openrouter_client():
    """
    Create a mocked OpenRouterClient with patched AsyncOpenAI.

    Returns a fixture that provides a client where the chat_completion
    method returns a controlled response.
    """
    with patch("openai.AsyncOpenAI") as MockOpenAI:
        mock_client_instance = MagicMock()
        MockOpenAI.return_value = mock_client_instance

        # Create a real OpenRouterClient but with mocked underlying client
        config = ClientConfig(api_key="test-key")
        client = OpenRouterClient(config)
        client.client = mock_client_instance

        # Replace chat_completion with a mock
        original_chat_completion = client.chat_completion
        client.chat_completion = AsyncMock(side_effect=original_chat_completion)

        yield client


@pytest.fixture
def mock_simple_chat():
    """Patch the simple_chat function for testing."""
    with patch("ralphfish.client.simple_chat", new_callable=AsyncMock) as mock:
        mock.return_value = "Mock response"
        yield mock


# ==================== Sample Data Fixtures ====================


@pytest.fixture
def sample_agent_persona():
    """Create a sample AgentPersona for testing."""
    return AgentPersona(
        id="test_agent_001",
        name="Test Agent",
        background="Test background with expertise in testing",
        traits=["analytical", "thorough", "precise"],
        goals=["Write comprehensive tests", "Ensure code quality"],
        biases=["confirmation bias"],
        communication_style="balanced",
    )


@pytest.fixture
def sample_scenario():
    """Create a sample Scenario for testing."""
    return Scenario(
        seed_text="This is a test scenario with entities and relationships.",
        title="Test Scenario",
        context="Additional context for the simulation",
        extracted_entities=[
            {"name": "Alice", "type": "person", "description": "Project manager"},
            {"name": "Bob", "type": "person", "description": "Developer"},
        ],
        extracted_relationships=[
            {"subject": "Alice", "predicate": "manages", "object": "Bob"},
        ],
        initial_facts=[
            Fact(
                key="project_exists",
                value="There is a project",
                source_agent_id="seed",
                round_extracted=0,
                confidence=1.0,
                evidence=["Project is mentioned"],
            )
        ],
    )


@pytest.fixture
def sample_simulation_state(sample_scenario, sample_agent_persona):
    """Create a sample SimulationState for testing."""
    return SimulationState(
        round=0,
        scenario=sample_scenario,
        agents=[sample_agent_persona],
        protocol=InteractionProtocol.DISCUSSION,
    )


@pytest.fixture
def sample_message():
    """Create a sample Message for testing."""
    return Message(
        round=1,
        agent_id="test_agent_001",
        agent_name="Test Agent",
        thought="I need to provide a thoughtful response",
        content="This is my response content",
        timestamp=datetime.utcnow(),
        metadata={"model": "gpt-3.5-turbo"},
    )


@pytest.fixture
def sample_fact():
    """Create a sample Fact for testing."""
    return Fact(
        key="test_fact_001",
        value="Test value",
        source_agent_id="test_agent_001",
        round_extracted=1,
        confidence=0.8,
        evidence=["Evidence 1", "Evidence 2"],
    )


@pytest.fixture
def sample_agent_config():
    """Create a sample AgentConfig for testing."""
    return AgentConfig(
        model="openai/gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=1000,
        use_free_tier=False,
        enable_summarization=True,
        summarize_threshold=30,
    )


@pytest.fixture
def sample_persona_generator_config():
    """Create a sample PersonaGeneratorConfig for testing."""
    return PersonaGeneratorConfig.get_default()


# ==================== Helper Functions ====================


def create_mock_chat_response(content: str, **kwargs):
    """Helper to create a dict response matching chat_completion return format."""
    return {
        "content": content,
        "model": kwargs.get("model", "gpt-3.5-turbo"),
        "usage": {
            "prompt_tokens": kwargs.get("prompt_tokens", 100),
            "completion_tokens": kwargs.get("completion_tokens", 50),
            "total_tokens": kwargs.get("total_tokens", 150),
        },
        "finish_reason": kwargs.get("finish_reason", "stop"),
        "id": kwargs.get("id", "test-123"),
    }


# ==================== Pytest Configuration ====================


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring API access"
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")
