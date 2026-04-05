"""
Unit tests for ralphfish.models module.

Tests cover data validation, state machine transitions, and all Pydantic models.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from ralphfish.models import (
    InteractionProtocol,
    Message,
    Fact,
    Dissent,
    AgentPersona,
    Scenario,
    SimulationState,
    DEFAULT_PERSONA_TEMPLATE,
)


# ==================== InteractionProtocol Tests ====================


class TestInteractionProtocol:
    """Test the InteractionProtocol enum."""

    def test_protocol_values(self):
        """Test that protocol values are strings."""
        assert InteractionProtocol.DISCUSSION.value == "discussion"
        assert InteractionProtocol.DEBATE.value == "debate"
        assert InteractionProtocol.VOTING.value == "voting"


# ==================== Message Tests ====================


class TestMessage:
    """Test the Message model."""

    def test_valid_message_creation(self):
        """Test creating a valid Message."""
        msg = Message(
            round=1,
            agent_id="agent_001",
            agent_name="Agent One",
            thought="Thinking about the problem",
            content="This is my response",
        )
        assert msg.round == 1
        assert msg.agent_id == "agent_001"
        assert msg.agent_name == "Agent One"
        assert msg.thought == "Thinking about the problem"
        assert msg.content == "This is my response"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}

    def test_message_with_metadata(self):
        """Test Message with metadata."""
        msg = Message(
            round=2,
            agent_id="agent_002",
            agent_name="Agent Two",
            thought="Another thought",
            content="Another response",
            metadata={"model": "gpt-4", "usage": {"tokens": 100}},
        )
        assert msg.metadata["model"] == "gpt-4"

    def test_message_missing_required_fields(self):
        """Test that Message requires round, agent_id, agent_name, thought, content."""
        with pytest.raises(ValidationError) as exc_info:
            Message(
                round=1,
                agent_id="agent_001",
                agent_name="Agent",
                # Missing thought and content
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("thought",) for e in errors)
        assert any(e["loc"] == ("content",) for e in errors)

    def test_message_json_encoding(self):
        """Test that datetime is properly encoded in JSON."""
        msg = Message(
            round=1,
            agent_id="test",
            agent_name="Test",
            thought="test",
            content="test",
        )
        json_data = msg.model_dump_json()
        assert isinstance(json_data, str)


# ==================== Fact Tests ====================


class TestFact:
    """Test the Fact model."""

    def test_valid_fact_creation(self):
        """Test creating a valid Fact."""
        fact = Fact(
            key="test_key",
            value="Test value",
            source_agent_id="agent_001",
            round_extracted=1,
            confidence=0.75,
            evidence=["Evidence line 1", "Evidence line 2"],
        )
        assert fact.key == "test_key"
        assert fact.value == "Test value"
        assert fact.confidence == 0.75
        assert len(fact.evidence) == 2

    def test_fact_default_confidence(self):
        """Test Fact uses default confidence of 0.1."""
        fact = Fact(
            key="key",
            value="value",
            round_extracted=1,
        )
        assert fact.confidence == 0.1

    def test_fact_confidence_bounds(self):
        """Test Fact confidence is bounded [0, 1]."""
        with pytest.raises(ValidationError):
            Fact(key="k", value="v", round_extracted=1, confidence=1.5)
        with pytest.raises(ValidationError):
            Fact(key="k", value="v", round_extracted=1, confidence=-0.1)

    def test_update_confidence_clamps(self):
        """Test update_confidence clamps to [0, 1]."""
        fact = Fact(key="k", value="v", round_extracted=1, confidence=0.5)

        fact.update_confidence(0.3)
        assert fact.confidence == 0.8

        fact.update_confidence(0.5)
        assert fact.confidence == 1.0  # clamped

        fact.update_confidence(-2.0)
        assert fact.confidence == 0.0  # clamped


# ==================== Dissent Tests ====================


class TestDissent:
    """Test the Dissent model."""

    def test_valid_dissent_creation(self):
        """Test creating a valid Dissent."""
        dissent = Dissent(
            fact_key="controversial_fact",
            values=["value1", "value2"],
            agent_ids=["agent_001", "agent_002"],
            round_introduced=3,
        )
        assert dissent.fact_key == "controversial_fact"
        assert dissent.values == ["value1", "value2"]
        assert dissent.agent_ids == ["agent_001", "agent_002"]
        assert dissent.resolution is None

    def test_dissent_requires_unique_agent_ids(self):
        """Test Dissent validates unique agent IDs."""
        with pytest.raises(ValidationError) as exc_info:
            Dissent(
                fact_key="key",
                values=["v1"],
                agent_ids=["agent_001", "agent_001"],  # Duplicate
                round_introduced=1,
            )
        errors = exc_info.value.errors()
        assert any("unique" in str(e["msg"]).lower() for e in errors)

    def test_dissent_with_resolution(self):
        """Test Dissent with resolution data."""
        dissent = Dissent(
            fact_key="key",
            values=["a", "b"],
            agent_ids=["a", "b"],
            round_introduced=2,
            resolution={"outcome": "compromise", "agreed_value": "c"},
        )
        assert dissent.resolution["outcome"] == "compromise"


# ==================== AgentPersona Tests ====================


class TestAgentPersona:
    """Test the AgentPersona model."""

    def test_valid_persona_creation(self):
        """Test creating a valid AgentPersona."""
        persona = AgentPersona(
            id="persona_001",
            name="Alice",
            background="Software engineer with 10 years experience",
            traits=["analytical", "creative"],
            goals=["Build awesome products", "Help team succeed"],
            biases=["optimism bias"],
            communication_style="professional",
        )
        assert persona.id == "persona_001"
        assert persona.name == "Alice"
        assert len(persona.traits) == 2
        assert persona.communication_style == "professional"

    def test_persona_defaults(self):
        """Test AgentPersona default values."""
        persona = AgentPersona(
            id="p",
            name="Test",
            background="Test background",
        )
        assert persona.traits == []
        assert persona.goals == []
        assert persona.biases == []
        assert persona.communication_style == "balanced"
        assert persona.prompt_template is None

    def test_persona_render_prompt_default(self):
        """Test rendering persona with default template."""
        persona = AgentPersona(
            id="p1",
            name="Bob",
            background="Data scientist",
            traits=["curious", "methodical"],
            goals=["Find insights"],
            biases=[],
        )
        prompt = persona.render_prompt()
        assert "Bob" in prompt
        assert "Data scientist" in prompt
        assert "curious, methodical" in prompt
        assert "Find insights" in prompt

    def test_persona_render_prompt_custom_template(self):
        """Test rendering persona with custom template."""
        custom_tpl = "Name: {name}, Background: {background}, Goals: {goals}"
        persona = AgentPersona(
            id="p2",
            name="Charlie",
            background="Researcher",
            goals=["Publish papers"],
        )
        prompt = persona.render_prompt(template=custom_tpl)
        assert "Name: Charlie" in prompt
        assert "Background: Researcher" in prompt

    def test_persona_render_prompt_uses_persona_template(self):
        """Test that persona's prompt_template is used if provided."""
        persona = AgentPersona(
            id="p3",
            name="Dana",
            background="Engineer",
            prompt_template="Custom: {name} - {background}",
        )
        prompt = persona.render_prompt()
        assert prompt == "Custom: Dana - Engineer"


# ==================== Scenario Tests ====================


class TestScenario:
    """Test the Scenario model."""

    def test_valid_scenario_creation(self):
        """Test creating a valid Scenario."""
        scenario = Scenario(
            seed_text="A project team is facing a deadline.",
            title="Project Deadline",
            context="Team of 5 developers working on a mobile app",
            extracted_entities=[
                {"name": "Team", "type": "group"},
            ],
            extracted_relationships=[
                {"subject": "DevA", "predicate": "reports_to", "object": "Lead"},
            ],
        )
        assert scenario.seed_text == "A project team is facing a deadline."
        assert scenario.title == "Project Deadline"
        assert len(scenario.extracted_entities) == 1

    def test_scenario_defaults(self):
        """Test Scenario default values."""
        scenario = Scenario(seed_text="Simple scenario")
        assert scenario.title is None
        assert scenario.context is None
        assert scenario.extracted_entities == []
        assert scenario.extracted_relationships == []
        assert scenario.initial_facts == []

    def test_scenario_to_prompt(self):
        """Test converting scenario to prompt."""
        scenario = Scenario(
            seed_text="The sky is blue.",
            context="This is a simple observation",
        )
        prompt = scenario.to_prompt()
        assert "The sky is blue." in prompt
        assert "Context: This is a simple observation" in prompt


# ==================== SimulationState Tests ====================


class TestSimulationState:
    """Test the SimulationState model - core state machine."""

    def test_valid_state_creation(self, sample_scenario, sample_agent_persona):
        """Test creating a valid SimulationState."""
        state = SimulationState(
            round=0,
            scenario=sample_scenario,
            agents=[sample_agent_persona],
            protocol=InteractionProtocol.DISCUSSION,
        )
        assert state.round == 0
        assert state.scenario == sample_scenario
        assert len(state.agents) == 1
        assert state.protocol == InteractionProtocol.DISCUSSION

    def test_state_defaults(self, sample_scenario):
        """Test SimulationState default values."""
        state = SimulationState(scenario=sample_scenario)
        assert state.round == 0
        assert state.agents == []
        assert state.world_facts == {}
        assert state.message_history == []
        assert state.aggregated_facts == []
        assert state.dissent_points == []
        assert state.confidence_scores == {}

    def test_get_agent_by_id(self, sample_simulation_state, sample_agent_persona):
        """Test retrieving agent by ID."""
        agent = sample_simulation_state.get_agent(sample_agent_persona.id)
        assert agent == sample_agent_persona
        assert sample_simulation_state.get_agent("nonexistent") is None

    def test_get_round_messages(self, sample_simulation_state, sample_message):
        """Test getting messages from a specific round."""
        sample_simulation_state.message_history.append(sample_message)
        round_msgs = sample_simulation_state.get_round_messages(1)
        assert len(round_msgs) == 1
        assert round_msgs[0] == sample_message

        # No messages from round 2
        assert sample_simulation_state.get_round_messages(2) == []

    def test_get_fact(self, sample_simulation_state, sample_fact):
        """Test getting fact by key."""
        sample_simulation_state.world_facts[sample_fact.key] = sample_fact
        retrieved = sample_simulation_state.get_fact(sample_fact.key)
        assert retrieved == sample_fact
        assert sample_simulation_state.get_fact("missing_key") is None

    def test_add_fact_new(self, sample_simulation_state):
        """Test adding a new fact."""
        fact = Fact(key="new_fact", value="new", round_extracted=1)
        sample_simulation_state.add_fact(fact)
        assert "new_fact" in sample_simulation_state.world_facts
        assert sample_simulation_state.world_facts["new_fact"] == fact

    def test_add_fact_merge_evidence(self, sample_simulation_state):
        """Test adding fact merges evidence with existing."""
        fact1 = Fact(
            key="shared", value="v1", round_extracted=1, confidence=0.5, evidence=["e1"]
        )
        fact2 = Fact(
            key="shared", value="v2", round_extracted=2, confidence=0.3, evidence=["e2"]
        )

        sample_simulation_state.add_fact(fact1)
        sample_simulation_state.add_fact(fact2)

        stored = sample_simulation_state.world_facts["shared"]
        assert len(stored.evidence) == 2
        assert "e1" in stored.evidence
        assert "e2" in stored.evidence
        # Confidence should be updated (0.5 + 0.3 = 0.8, clamped to 1.0 if >1)
        assert stored.confidence == 0.8

    def test_to_dict_include_messages(self, sample_simulation_state, sample_message):
        """Test converting state to dict with messages."""
        sample_simulation_state.message_history.append(sample_message)
        data = sample_simulation_state.to_dict(include_messages=True)
        assert "message_history" in data
        assert len(data["message_history"]) == 1

    def test_to_dict_exclude_messages(self, sample_simulation_state, sample_message):
        """Test converting state to dict without messages."""
        sample_simulation_state.message_history.append(sample_message)
        data = sample_simulation_state.to_dict(include_messages=False)
        assert "message_history" not in data

    def test_get_round_summary(self, sample_simulation_state, sample_message):
        """Test generating round summary."""
        sample_simulation_state.message_history.append(sample_message)
        summary = sample_simulation_state.get_round_summary(1)
        assert summary["round"] == 1
        assert summary["message_count"] == 1
        assert sample_message.agent_id in summary["participants"]

    def test_state_transitions(self, sample_scenario, sample_agent_persona):
        """Test state transitions through rounds."""
        state = SimulationState(
            scenario=sample_scenario,
            agents=[sample_agent_persona],
        )

        # Simulate adding messages over rounds
        for round_num in range(1, 4):
            msg = Message(
                round=round_num,
                agent_id=sample_agent_persona.id,
                agent_name=sample_agent_persona.name,
                thought=f"Round {round_num} thought",
                content=f"Round {round_num} content",
            )
            state.message_history.append(msg)
            state.round = round_num

        assert state.round == 3
        assert len(state.message_history) == 3
        assert len(state.get_round_messages(1)) == 1
        assert len(state.get_round_messages(2)) == 1
        assert len(state.get_round_messages(3)) == 1


# ==================== Integration Tests ====================


class TestModelsIntegration:
    """Integration tests for models working together."""

    def test_full_simulation_cycle(self, sample_scenario, sample_agent_persona):
        """Test a complete simulation cycle with state updates."""
        state = SimulationState(
            scenario=sample_scenario,
            agents=[sample_agent_persona],
            protocol=InteractionProtocol.DISCUSSION,
        )

        # Add a message
        msg = Message(
            round=1,
            agent_id=sample_agent_persona.id,
            agent_name=sample_agent_persona.name,
            thought="Initial response",
            content="Hello world",
        )
        state.message_history.append(msg)

        # Extract a fact
        fact = Fact(
            key="greeting",
            value="Agent said hello",
            source_agent_id=sample_agent_persona.id,
            round_extracted=1,
            confidence=0.9,
        )
        state.add_fact(fact)

        # Check state
        assert len(state.message_history) == 1
        assert "greeting" in state.world_facts
        assert state.world_facts["greeting"].confidence == 0.9

    def test_persona_message_flow(self, sample_agent_persona):
        """Test that persona can be used to create messages."""
        msg = Message(
            round=1,
            agent_id=sample_agent_persona.id,
            agent_name=sample_agent_persona.name,
            thought="Acting according to persona",
            content="Response aligned with traits: "
            + ", ".join(sample_agent_persona.traits),
        )
        assert msg.agent_name == sample_agent_persona.name
        assert sample_agent_persona.id in msg.agent_id
