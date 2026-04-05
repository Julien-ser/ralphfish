"""
Tests for the ReportGenerator component.
"""

import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

from ralphfish.models import (
    AgentPersona,
    Message,
    SimulationState,
    Scenario,
    InteractionProtocol,
)
from ralphfish.synthesizer import (
    PredictionSynthesizer,
    SynthesisReport,
    SynthesizedFact,
    AgentAlignment,
)
from ralphfish.report_generator import ReportGenerator, generate_report


@pytest.fixture
def mock_agents():
    """Create a set of test agents."""
    return [
        AgentPersona(
            id="agent1",
            name="Alice",
            background="Data scientist",
            traits=["analytical"],
            goals=["Accurate analysis"],
        ),
        AgentPersona(
            id="agent2",
            name="Bob",
            background="Business analyst",
            traits=["pragmatic"],
            goals=["Actionable insights"],
        ),
    ]


@pytest.fixture
def simulation_state(mock_agents):
    """Create a complete SimulationState for testing."""
    scenario = Scenario(
        seed_text="Test scenario for report generation",
        title="Test Report Scenario",
        context="This is a test context.",
    )

    state = SimulationState(
        scenario=scenario,
        agents=mock_agents,
        round=2,
        protocol=InteractionProtocol.DISCUSSION,
    )

    # Add messages across rounds
    for r in [1, 2]:
        for agent in mock_agents:
            msg = Message(
                round=r,
                agent_id=agent.id,
                agent_name=agent.name,
                thought=f"Thought for round {r}",
                content=f"Message from {agent.name} in round {r}. The outcome is positive.",
            )
            state.message_history.append(msg)

    # Add some facts
    from ralphfish.models import Fact

    state.world_facts["fact1"] = Fact(
        key="test-fact",
        value="Test value",
        confidence=0.8,
        evidence=["Test evidence"],
        round_extracted=1,
    )

    return state


@pytest.fixture
def synthesis_report(mock_agents):
    """Create a SynthesisReport for testing."""
    consensus_fact = SynthesizedFact(
        key="outcome",
        value="Positive outcome",
        supporting_agents=["agent1", "agent2"],
        opposing_agents=[],
        confidence=0.9,
        evidence=["Evidence 1", "Evidence 2"],
        round_extracted=2,
        is_consensus=True,
    )

    dissent_fact = SynthesizedFact(
        key="risk",
        value="High risk",
        supporting_agents=["agent1"],
        opposing_agents=["agent2"],
        confidence=0.5,
        evidence=["Evidence 3"],
        round_extracted=2,
        is_consensus=False,
    )

    agent_alignment = AgentAlignment(
        agent_id="agent1",
        agent_name="Alice",
        consensus_alignment_score=0.8,
        unique_contributions=["unique-insight"],
        dissenting_positions=["risk"],
    )

    report = SynthesisReport(
        scenario_title="Test Report Scenario",
        total_rounds=2,
        total_agents=2,
        consensus_facts=[consensus_fact],
        dissent_points=[dissent_fact],
        unresolved_facts=[],
        agent_alignments={"agent1": agent_alignment},
        overall_consensus_strength=0.75,
        total_facts_extracted=2,
        consensus_fact_count=1,
        dissent_fact_count=1,
        raw_messages_analyzed=4,
    )

    return report


def test_report_generator_initialization():
    """Test ReportGenerator can be initialized with default and custom settings."""
    generator = ReportGenerator()
    assert generator.default_format == "markdown"
    assert generator.template_dir is None

    custom_dir = Path("/tmp/test_templates")
    generator = ReportGenerator(template_dir=custom_dir, default_format="json")
    assert generator.default_format == "json"
    assert generator.template_dir == custom_dir


def test_generate_markdown_report(simulation_state, synthesis_report):
    """Test generating a markdown report."""
    generator = ReportGenerator()
    report = generator.generate(simulation_state, synthesis_report, format="markdown")

    assert isinstance(report, str)
    assert "# Simulation Report:" in report or "##" in report
    assert "Test Report Scenario" in report
    assert "Alice" in report
    assert "Bob" in report
    assert "Consensus Facts" in report or "consensus" in report.lower()


def test_generate_json_report(simulation_state, synthesis_report):
    """Test generating a JSON report."""
    generator = ReportGenerator()
    report = generator.generate(simulation_state, synthesis_report, format="json")

    assert isinstance(report, str)
    # Should be valid JSON
    import json

    data = json.loads(report)
    assert "scenario" in data
    assert "agents" in data
    assert "synthesis" in data
    assert data["scenario"]["title"] == "Test Report Scenario"


def test_generate_yaml_report(simulation_state, synthesis_report):
    """Test generating a YAML report."""
    generator = ReportGenerator()
    report = generator.generate(simulation_state, synthesis_report, format="yaml")

    assert isinstance(report, str)
    # Should be valid YAML (parseable)
    import yaml

    data = yaml.safe_load(report)
    assert "scenario" in data
    assert "agents" in data
    assert data["scenario"]["title"] == "Test Report Scenario"


def test_generate_all_formats(simulation_state, synthesis_report):
    """Test generating reports in all formats at once."""
    generator = ReportGenerator()
    reports = generator.generate_all_formats(simulation_state, synthesis_report)

    assert "markdown" in reports
    assert "json" in reports
    assert "yaml" in reports

    for fmt, content in reports.items():
        assert isinstance(content, str)
        assert len(content) > 0


def test_export_functionality(simulation_state, synthesis_report, tmp_path):
    """Test exporting reports to filesystem."""
    generator = ReportGenerator()
    saved_files = generator.export(
        simulation_state,
        synthesis_report,
        output_dir=tmp_path,
        filename_prefix="test_sim",
        formats=["markdown", "json"],
    )

    assert len(saved_files) == 2
    assert "markdown" in saved_files
    assert "json" in saved_files

    for fmt, filepath in saved_files.items():
        assert filepath.exists()
        assert filepath.suffix == f".{fmt}"
        assert filepath.name.startswith("test_sim_")
        content = filepath.read_text()
        assert len(content) > 0


def test_export_with_timestamp(simulation_state, synthesis_report, tmp_path):
    """Test that exported files include timestamps."""
    import re

    generator = ReportGenerator()
    saved_files = generator.export(
        simulation_state,
        synthesis_report,
        output_dir=tmp_path,
        filename_prefix="timestamped",
    )

    filepath = saved_files["markdown"]
    filename = filepath.name
    assert "timestamped_" in filename

    # Extract timestamp using regex (pattern: 8 digits, underscore, 6 digits)
    match = re.search(r"(\d{8}_\d{6})", filename)
    assert match is not None, "No timestamp found in filename"
    timestamp_str = match.group(1)

    # Parse to ensure valid datetime and that it's recent (within last 5 minutes)
    file_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
    now = datetime.utcnow()
    time_diff = abs((now - file_time).total_seconds())
    assert time_diff < 300, f"Timestamp {file_time} is not recent (diff: {time_diff}s)"


def test_export_all_formats(simulation_state, synthesis_report, tmp_path):
    """Test exporting all formats using 'all' keyword."""
    generator = ReportGenerator()
    saved_files = generator.export(
        simulation_state, synthesis_report, output_dir=tmp_path, formats=["all"]
    )

    assert len(saved_files) == 3
    for fmt in ["markdown", "json", "yaml"]:
        assert fmt in saved_files


def test_generate_with_unsupported_format_raises(simulation_state, synthesis_report):
    """Test that unsupported format raises ValueError."""
    generator = ReportGenerator()

    with pytest.raises(ValueError, match="Unsupported format"):
        generator.generate(simulation_state, synthesis_report, format="xml")


def test_context_preparation(simulation_state, synthesis_report):
    """Test that _prepare_context produces expected structure."""
    generator = ReportGenerator()
    context = generator._prepare_context(simulation_state, synthesis_report)

    # Check all required keys are present
    required_keys = [
        "scenario",
        "scenario_summary",
        "agents",
        "agent_lineup",
        "total_rounds",
        "round_summaries",
        "message_count",
        "consensus_facts",
        "dissent_points",
        "unresolved_facts",
        "agent_alignments",
        "overall_consensus_strength",
        "consensus_fact_count",
        "dissent_fact_count",
        "total_facts_extracted",
        "synthesized_at",
        "generated_at",
        "protocol",
    ]
    for key in required_keys:
        assert key in context

    # Check agent lineup structure
    assert len(context["agent_lineup"]) == 2
    for agent_info in context["agent_lineup"]:
        assert "id" in agent_info
        assert "name" in agent_info
        assert "background" in agent_info
        assert "traits" in agent_info
        assert "goals" in agent_info

    # Check round summaries
    assert len(context["round_summaries"]) == 2  # rounds 1 and 2
    for rs in context["round_summaries"]:
        assert "round" in rs
        assert "message_count" in rs


def test_convenience_generate_report_function(simulation_state):
    """Test the convenience generate_report async function."""
    # Create a real synthesizer and run
    synthesizer = PredictionSynthesizer()

    # This should work without needing to manually create a report
    # We'll just test that it returns a string
    import asyncio

    report = asyncio.run(
        generate_report(
            state=simulation_state, synthesizer=synthesizer, format="markdown"
        )
    )

    assert isinstance(report, str)
    assert len(report) > 0


def test_markdown_template_includes_all_sections(simulation_state, synthesis_report):
    """Test that the default markdown template includes all required sections."""
    generator = ReportGenerator()
    report = generator.generate(simulation_state, synthesis_report, "markdown")

    # Check for all required sections (case-insensitive)
    sections = [
        "scenario summary",
        "agent lineup",
        "round evolution",
        "final prediction",
        "divergence analysis",
    ]

    report_lower = report.lower()
    for section in sections:
        assert section in report_lower, f"Missing section: {section}"


def test_json_template_structure(simulation_state, synthesis_report):
    """Test that JSON output has expected structure."""
    generator = ReportGenerator()
    report = generator.generate(simulation_state, synthesis_report, "json")

    import json

    data = json.loads(report)

    # Check top-level keys
    assert "scenario" in data
    assert "agents" in data
    assert "simulation" in data
    assert "synthesis" in data
    assert "metadata" in data

    # Check synthesis structure
    synthesis = data["synthesis"]
    assert "consensus_facts" in synthesis
    assert "dissent_points" in synthesis
    assert "agent_alignments" in synthesis
    assert "overall_consensus_strength" in synthesis


def test_yaml_template_readability(simulation_state, synthesis_report):
    """Test that YAML output is well-formed and readable."""
    generator = ReportGenerator()
    report = generator.generate(simulation_state, synthesis_report, "yaml")

    import yaml

    data = yaml.safe_load(report)

    # Should be able to access key data
    assert data["scenario"]["title"] == "Test Report Scenario"
    assert len(data["agents"]) == 2
    assert data["simulation"]["total_rounds"] == 2
