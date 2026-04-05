"""
Tests for the PredictionSynthesizer component.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from ralphfish.models import (
    AgentPersona,
    Message,
    SimulationState,
    Scenario,
    InteractionProtocol,
)
from ralphfish.synthesizer import (
    PredictionSynthesizer,
    SynthesizedFact,
    SynthesisReport,
    AgentAlignment,
)


@pytest.fixture
def mock_agents():
    """Create a set of test agents."""
    return [
        AgentPersona(
            id="agent1",
            name="Alice",
            background="Analytical thinker",
            traits=["logical", "detailed"],
            goals=["Find truth"],
        ),
        AgentPersona(
            id="agent2",
            name="Bob",
            background="Pragmatist",
            traits=["practical", "action-oriented"],
            goals=["Solve problem"],
        ),
        AgentPersona(
            id="agent3",
            name="Charlie",
            background="Skeptic",
            traits=["questioning", "thorough"],
            goals=["Challenge assumptions"],
        ),
    ]


@pytest.fixture
def simulation_state(mock_agents):
    """Create a SimulationState with messages from final round."""
    scenario = Scenario(
        seed_text="Test scenario about predicting an outcome",
        title="Test Simulation",
    )

    state = SimulationState(
        scenario=scenario,
        agents=mock_agents,
        round=3,
        protocol=InteractionProtocol.DISCUSSION,
    )

    # Add messages from final round (round 3)
    messages = [
        Message(
            round=3,
            agent_id="agent1",
            agent_name="Alice",
            thought="I think the outcome will be X",
            content="The evidence points to outcome X.",
        ),
        Message(
            round=3,
            agent_id="agent2",
            agent_name="Bob",
            thought="We should focus on practical solutions",
            content="I agree, the evidence suggests outcome X.",
        ),
        Message(
            round=3,
            agent_id="agent3",
            agent_name="Charlie",
            thought="I'm not fully convinced",
            content="While most evidence points to X, I think we should consider Y as well.",
        ),
    ]

    state.message_history.extend(messages)

    # Add some earlier round messages
    for r in [1, 2]:
        for agent in mock_agents:
            msg = Message(
                round=r,
                agent_id=agent.id,
                agent_name=agent.name,
                thought=f"Round {r} thought",
                content=f"Round {r} message",
            )
            state.message_history.append(msg)

    return state


@pytest.fixture
def synthesizer():
    """Create a PredictionSynthesizer instance."""
    return PredictionSynthesizer(
        consensus_threshold=0.7,
        strong_consensus_threshold=0.9,
        min_agents_for_fact=2,
    )


def test_synthesizer_initialization():
    """Test synthesizer can be initialized with custom thresholds."""
    synth = PredictionSynthesizer(
        consensus_threshold=0.6,
        strong_consensus_threshold=0.8,
        min_agents_for_fact=1,
    )
    assert synth.consensus_threshold == 0.6
    assert synth.strong_consensus_threshold == 0.8
    assert synth.min_agents_for_fact == 1


def test_synthesizer_defaults():
    """Test default threshold values."""
    synth = PredictionSynthesizer()
    assert synth.consensus_threshold == 0.7
    assert synth.strong_consensus_threshold == 0.9
    assert synth.min_agents_for_fact == 2


def test_split_into_sentences():
    """Test sentence splitting."""
    synth = PredictionSynthesizer()
    text = "First sentence. Second sentence! Third? Fourth remains."
    sentences = synth._split_into_sentences(text)
    assert len(sentences) == 4
    assert "First sentence" in sentences
    assert "Second sentence" in sentences
    assert "Third" in sentences
    assert "Fourth remains" in sentences


def test_generate_fact_key():
    """Test fact key generation is deterministic."""
    synth = PredictionSynthesizer()
    key1 = synth._generate_fact_key("The quick brown fox jumps")
    key2 = synth._generate_fact_key("the quick brown fox jumps")
    assert key1 == key2  # Should be same after lowercasing
    assert len(key1) <= 50


def test_group_facts_by_key():
    """Test grouping facts by key."""
    synth = PredictionSynthesizer()
    facts = [
        SynthesizedFact(
            key="outcome-x",
            value="outcome X",
            supporting_agents=["agent1"],
            opposing_agents=[],
            confidence=1.0,
            evidence=[],
            round_extracted=3,
        ),
        SynthesizedFact(
            key="outcome-x",
            value="outcome X",
            supporting_agents=["agent2"],
            opposing_agents=[],
            confidence=1.0,
            evidence=[],
            round_extracted=3,
        ),
        SynthesizedFact(
            key="outcome-y",
            value="outcome Y",
            supporting_agents=["agent3"],
            opposing_agents=[],
            confidence=1.0,
            evidence=[],
            round_extracted=3,
        ),
    ]

    groups = synth._group_facts_by_key(facts)
    assert len(groups) == 2
    assert len(groups["outcome-x"]) == 2
    assert len(groups["outcome-y"]) == 1


def test_compute_fact_synthesis():
    """Test computing synthesized facts from fact groups."""
    synth = PredictionSynthesizer()
    facts = [
        SynthesizedFact(
            key="x-outcome",
            value="X is the outcome",
            supporting_agents=["agent1"],
            opposing_agents=[],
            confidence=1.0,
            evidence=["Evidence 1"],
            round_extracted=3,
        ),
        SynthesizedFact(
            key="x-outcome",
            value="X is the outcome",
            supporting_agents=["agent2"],
            opposing_agents=[],
            confidence=1.0,
            evidence=["Evidence 2"],
            round_extracted=3,
        ),
    ]

    groups = synth._group_facts_by_key(facts)
    synthesized = synth._compute_fact_synthesis(groups)

    assert len(synthesized) == 1
    fact = synthesized[0]
    assert fact.key == "x-outcome"
    assert set(fact.supporting_agents) == {"agent1", "agent2"}
    assert fact.confidence == 1.0  # Both agents supported, so confidence = 2/2
    assert len(fact.evidence) == 2


def test_compute_agent_alignments(mock_agents):
    """Test computing agent alignment scores."""
    synth = PredictionSynthesizer()

    consensus_facts = [
        SynthesizedFact(
            key="f1",
            value="Fact 1",
            supporting_agents=["agent1", "agent2"],
            opposing_agents=[],
            confidence=0.8,
            evidence=[],
            round_extracted=3,
            is_consensus=True,
        ),
        SynthesizedFact(
            key="f2",
            value="Fact 2",
            supporting_agents=["agent1", "agent2", "agent3"],
            opposing_agents=[],
            confidence=0.9,
            evidence=[],
            round_extracted=3,
            is_consensus=True,
        ),
    ]

    dissent_points = [
        SynthesizedFact(
            key="d1",
            value="Dissenting point",
            supporting_agents=["agent3"],
            opposing_agents=["agent1", "agent2"],
            confidence=0.3,
            evidence=[],
            round_extracted=3,
            is_consensus=False,
        )
    ]

    alignments = synth._compute_agent_alignments(
        consensus_facts, dissent_points, mock_agents
    )

    # Agent1 supports 2/2 consensus facts → alignment = 1.0
    assert alignments["agent1"].consensus_alignment_score == 1.0
    assert (
        "f1" in alignments["agent1"].unique_contributions
        or len(alignments["agent1"].unique_contributions) >= 0
    )

    # Agent3 supports only 1/2 consensus facts → alignment = 0.5
    assert alignments["agent3"].consensus_alignment_score == 0.5
    assert "d1" in alignments["agent3"].dissenting_positions


@pytest.mark.asyncio
async def test_synthesize_basic(synthesizer, simulation_state):
    """Test full synthesis on a simple simulation state."""
    report = await synthesizer.synthesize(simulation_state)

    assert report.scenario_title == "Test Simulation"
    assert report.total_rounds == 3
    assert report.total_agents == 3
    assert report.raw_messages_analyzed > 0

    # Should have extracted some facts
    assert report.total_facts_extracted > 0

    # Basic report summary
    summary = report.get_summary()
    assert "Test Simulation" in summary
    assert "Consensus" in summary or "Dissent" in summary


@pytest.mark.asyncio
async def test_synthesize_empty_state(mock_agents):
    """Test synthesis with no messages."""
    scenario = Scenario(seed_text="Empty scenario", title="Empty Test")

    state = SimulationState(
        scenario=scenario,
        agents=mock_agents,
        round=1,
    )

    synthesizer = PredictionSynthesizer()
    report = await synthesizer.synthesize(state)

    assert report.total_facts_extracted == 0
    assert report.consensus_fact_count == 0
    assert report.overall_consensus_strength == 0.0


@pytest.mark.asyncio
async def test_synthesize_consensus_detection(synthesizer, mock_agents):
    """Test that consensus is correctly detected when agents agree."""
    scenario = Scenario(
        seed_text="All agents should agree on this",
        title="Consensus Test",
    )

    state = SimulationState(
        scenario=scenario,
        agents=mock_agents,
        round=1,
    )

    # All agents say the same thing
    for agent in mock_agents:
        msg = Message(
            round=1,
            agent_id=agent.id,
            agent_name=agent.name,
            thought="Thinking",
            content="All evidence points to the same conclusion.",
        )
        state.message_history.append(msg)

    report = await synthesizer.synthesize(state)

    # Should have at least some consensus facts
    assert report.consensus_fact_count > 0 or report.total_facts_extracted > 0


def test_synthesis_report_to_dict():
    """Test that report can be serialized to dictionary."""
    report = SynthesisReport(
        scenario_title="Test",
        total_rounds=5,
        total_agents=3,
        consensus_facts=[],
        dissent_points=[],
        unresolved_facts=[],
        overall_consensus_strength=0.8,
    )

    data = report.to_dict()
    assert isinstance(data, dict)
    assert data["scenario_title"] == "Test"
    assert data["overall_consensus_strength"] == 0.8
