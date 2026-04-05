"""
Additional tests to achieve >90% coverage for data models (models.py).

Focuses on covering lines not executed by existing test suite:
- Dissent validator (unique agent IDs)
- AgentPersona.render_prompt
- Scenario.to_prompt
- SimulationState helper methods (get_agent, get_fact, add_fact merging, to_dict)
- Fact.update_confidence boundary conditions
- Message model
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from ralphfish.models import (
    Dissent,
    AgentPersona,
    Scenario,
    SimulationState,
    Fact,
    Message,
    DEFAULT_PERSONA_TEMPLATE,
)


@pytest.fixture
def basic_agent_persona():
    """Create a basic AgentPersona for testing."""
    return AgentPersona(
        id="agent1",
        name="Alice",
        background="Test background",
        traits=["trait1"],
        goals=["goal1"],
        biases=[],
        communication_style="formal",
    )


@pytest.fixture
def basic_scenario():
    """Create a basic Scenario."""
    return Scenario(
        seed_text="Test seed text",
        title="Test Scenario",
        context="Test context",
    )


@pytest.fixture
def basic_simulation_state(basic_agent_persona):
    """Create a basic SimulationState."""
    scenario = Scenario(seed_text="Test", title="Test")
    return SimulationState(
        scenario=scenario,
        agents=[basic_agent_persona],
        round=0,
    )


class TestDissentValidation:
    """Test Dissent validator for unique agent IDs (lines 67-72)."""

    def test_dissent_duplicate_agent_ids_raises(self):
        """Test that Dissent with duplicate agent_ids raises ValidationError."""
        with pytest.raises(ValidationError, match="Agent IDs must be unique"):
            Dissent(
                fact_key="test",
                values=["a"],
                agent_ids=["agent1", "agent1"],  # Duplicate
                round_introduced=1,
            )

    def test_dissent_unique_agent_ids_passes(self):
        """Test that Dissent with unique agent IDs is valid."""
        dissent = Dissent(
            fact_key="test",
            values=["a"],
            agent_ids=["agent1", "agent2"],
            round_introduced=1,
        )
        assert dissent.agent_ids == ["agent1", "agent2"]


class TestAgentPersonaRenderPrompt:
    """Test AgentPersona.render_prompt method (lines 108-118)."""

    def test_render_with_default_template(self, basic_agent_persona):
        """Test rendering uses DEFAULT_PERSONA_TEMPLATE."""
        prompt = basic_agent_persona.render_prompt()
        assert basic_agent_persona.name in prompt
        assert basic_agent_persona.background in prompt
        assert "trait1" in prompt
        assert "goal1" in prompt
        assert "formal" in prompt

    def test_render_with_custom_template(self, basic_agent_persona):
        """Test rendering with custom template."""
        template = "Name: {name}, Background: {background}"
        prompt = basic_agent_persona.render_prompt(template)
        assert (
            prompt
            == f"Name: {basic_agent_persona.name}, Background: {basic_agent_persona.background}"
        )

    def test_render_with_persona_prompt_template(self, basic_agent_persona):
        """Test rendering uses persona's prompt_template if set."""
        custom = "You are {name}."
        basic_agent_persona.prompt_template = custom
        prompt = basic_agent_persona.render_prompt()
        assert prompt == f"You are {basic_agent_persona.name}."

    def test_render_priority(self, basic_agent_persona):
        """Test template argument overrides persona template."""
        arg_template = "Arg: {name}"
        persona_template = "Persona: {name}"
        basic_agent_persona.prompt_template = persona_template
        prompt = basic_agent_persona.render_prompt(arg_template)
        assert prompt == f"Arg: {basic_agent_persona.name}."


class TestScenarioToPrompt:
    """Test Scenario.to_prompt method (lines 137-140)."""

    def test_to_prompt_without_context(self, basic_scenario):
        """Test to_prompt includes seed_text only."""
        prompt = basic_scenario.to_prompt()
        assert basic_scenario.seed_text in prompt
        assert "Context" not in prompt

    def test_to_prompt_with_context(self, basic_scenario):
        """Test to_prompt includes both seed and context."""
        basic_scenario.context = "Additional context"
        prompt = basic_scenario.to_prompt()
        assert basic_scenario.seed_text in prompt
        assert basic_scenario.context in prompt
        assert "Context:" in prompt


class TestSimulationStateHelpers:
    """Test SimulationState helper methods (lines 161-199)."""

    def test_get_agent_existing(self, basic_simulation_state, basic_agent_persona):
        """Test get_agent returns agent when found (lines 161-166)."""
        agent = basic_simulation_state.get_agent(basic_agent_persona.id)
        assert agent == basic_agent_persona

    def test_get_agent_missing(self, basic_simulation_state):
        """Test get_agent returns None when not found."""
        agent = basic_simulation_state.get_agent("nonexistent")
        assert agent is None

    def test_get_fact_existing(self, basic_simulation_state):
        """Test get_fact returns fact when present (line 174)."""
        fact = Fact(key="test", value="value", source_agent_id="a", round_extracted=0)
        basic_simulation_state.world_facts["test"] = fact
        retrieved = basic_simulation_state.get_fact("test")
        assert retrieved == fact

    def test_get_fact_missing(self, basic_simulation_state):
        """Test get_fact returns None when key not found."""
        assert basic_simulation_state.get_fact("nonexistent") is None

    def test_add_fact_new(self, basic_simulation_state):
        """Test add_fact adds a new fact (lines 176-184)."""
        fact = Fact(key="new", value="val", source_agent_id="a", round_extracted=0)
        basic_simulation_state.add_fact(fact)
        assert "new" in basic_simulation_state.world_facts
        assert basic_simulation_state.world_facts["new"] == fact

    def test_add_fact_merges_evidence_and_confidence(self, basic_simulation_state):
        """Test add_fact merges evidence and updates confidence when fact exists (lines 178-182)."""
        fact1 = Fact(
            key="same",
            value="value1",
            source_agent_id="agent1",
            round_extracted=0,
            confidence=0.5,
            evidence=["evidence1"],
        )
        fact2 = Fact(
            key="same",
            value="value2",
            source_agent_id="agent2",
            round_extracted=1,
            confidence=0.3,
            evidence=["evidence2"],
        )
        basic_simulation_state.add_fact(fact1)
        assert basic_simulation_state.world_facts["same"].confidence == 0.5
        assert basic_simulation_state.world_facts["same"].evidence == ["evidence1"]

        basic_simulation_state.add_fact(fact2)
        merged = basic_simulation_state.world_facts["same"]
        assert len(merged.evidence) == 2
        assert "evidence1" in merged.evidence
        assert "evidence2" in merged.evidence
        # Confidence: 0.5 + 0.3 = 0.8
        assert merged.confidence == 0.8

    def test_add_fact_confidence_clamping(self, basic_simulation_state):
        """Test add_fact clamps confidence to [0,1]."""
        fact1 = Fact(
            key="clamp",
            value="v1",
            source_agent_id="a1",
            round_extracted=0,
            confidence=0.9,
        )
        basic_simulation_state.add_fact(fact1)
        fact2 = Fact(
            key="clamp",
            value="v2",
            source_agent_id="a2",
            round_extracted=1,
            confidence=0.3,
        )
        basic_simulation_state.add_fact(fact2)
        # 0.9 + 0.3 = 1.2 -> clamp to 1.0
        assert basic_simulation_state.world_facts["clamp"].confidence == 1.0

        # Test negative overflow
        fact3 = Fact(
            key="clamp2",
            value="v",
            source_agent_id="a3",
            round_extracted=2,
            confidence=-0.5,
        )
        basic_simulation_state.world_facts["clamp2"] = Fact(
            key="clamp2",
            value="v",
            source_agent_id="a",
            round_extracted=0,
            confidence=0.2,
        )
        basic_simulation_state.add_fact(fact3)
        assert basic_simulation_state.world_facts["clamp2"].confidence == 0.0

    def test_to_dict_include_messages(self, basic_simulation_state):
        """Test to_dict includes message_history when include_messages=True (lines 186-199)."""
        msg = Message(
            round=1, agent_id="a", agent_name="A", thought="", content="Hello"
        )
        basic_simulation_state.message_history.append(msg)
        d = basic_simulation_state.to_dict(include_messages=True)
        assert "message_history" in d
        assert len(d["message_history"]) == 1

    def test_to_dict_exclude_messages(self, basic_simulation_state):
        """Test to_dict excludes message_history when include_messages=False."""
        msg = Message(
            round=1, agent_id="a", agent_name="A", thought="", content="Hello"
        )
        basic_simulation_state.message_history.append(msg)
        d = basic_simulation_state.to_dict(include_messages=False)
        assert "message_history" not in d


class TestFactUpdateConfidence:
    """Test Fact.update_confidence method (lines 52-55)."""

    def test_update_confidence_increases(self):
        """Test confidence increases within bounds."""
        fact = Fact(
            key="k", value="v", source_agent_id="a", round_extracted=0, confidence=0.3
        )
        new = fact.update_confidence(0.2)
        assert new == 0.5
        assert fact.confidence == 0.5

    def test_update_confidence_decreases(self):
        """Test confidence decreases within bounds."""
        fact = Fact(
            key="k", value="v", source_agent_id="a", round_extracted=0, confidence=0.7
        )
        new = fact.update_confidence(-0.3)
        assert new == 0.4
        assert fact.confidence == 0.4

    def test_update_confidence_clamp_max(self):
        """Test confidence does not exceed 1.0."""
        fact = Fact(
            key="k", value="v", source_agent_id="a", round_extracted=0, confidence=0.9
        )
        new = fact.update_confidence(0.2)
        assert new == 1.0
        assert fact.confidence == 1.0

    def test_update_confidence_clamp_min(self):
        """Test confidence does not go below 0.0."""
        fact = Fact(
            key="k", value="v", source_agent_id="a", round_extracted=0, confidence=0.3
        )
        new = fact.update_confidence(-0.5)
        assert new == 0.0
        assert fact.confidence == 0.0

    def test_update_confidence_zero(self):
        """Test confidence at 0.0."""
        fact = Fact(
            key="k", value="v", source_agent_id="a", round_extracted=0, confidence=0.0
        )
        fact.update_confidence(0.1)
        assert fact.confidence == 0.1
        fact.update_confidence(-0.1)
        assert fact.confidence == 0.0


class TestMessageModel:
    """Test Message model."""

    def test_message_creation(self):
        """Test creating a Message."""
        msg = Message(
            round=1,
            agent_id="a1",
            agent_name="Alice",
            thought="Thinking",
            content="Hello",
        )
        assert msg.round == 1
        assert msg.agent_id == "a1"
        assert msg.agent_name == "Alice"
        assert msg.thought == "Thinking"
        assert msg.content == "Hello"
        assert isinstance(msg.timestamp, datetime)

    def test_message_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        msg = Message(
            round=1,
            agent_id="a1",
            agent_name="Alice",
            thought="",
            content="Hello",
        )
        assert msg.metadata == {}


class TestDefaultPersonaTemplate:
    """Test the DEFAULT_PERSONA_TEMPLATE string."""

    def test_template_contains_all_placeholders(self):
        """Ensure all expected placeholders exist."""
        placeholders = [
            "{name}",
            "{background}",
            "{traits}",
            "{goals}",
            "{biases}",
            "{style}",
        ]
        for ph in placeholders:
            assert ph in DEFAULT_PERSONA_TEMPLATE
