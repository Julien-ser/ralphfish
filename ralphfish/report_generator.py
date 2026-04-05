"""
Structured report generator for Wiggum loop simulations.

This module generates comprehensive simulation reports in multiple formats
(JSON, YAML, Markdown) using Jinja2 templates. Reports include:

- Scenario summary
- Agent lineup with personas
- Round evolution (messages and facts per round)
- Final prediction analysis
- Divergence analysis (consensus vs dissent)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
from jinja2 import Template, Environment, FileSystemLoader

from .models import SimulationState, AgentPersona
from .synthesizer import PredictionSynthesizer, SynthesisReport


class ReportGenerator:
    """
    Generates structured simulation reports using Jinja2 templates.

    The generator can produce reports in multiple formats and includes
    comprehensive analysis of the simulation results.
    """

    def __init__(
        self, template_dir: Optional[Path] = None, default_format: str = "markdown"
    ):
        """
        Initialize the report generator.

        Args:
            template_dir: Directory containing Jinja2 template files.
                         If None, uses embedded default templates.
            default_format: Default output format ('markdown', 'json', 'yaml')
        """
        self.template_dir = template_dir
        self.default_format = default_format
        self.env = None

        if template_dir:
            self.env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True,
            )

        # Embedded default templates
        self._templates = {
            "markdown": self._default_markdown_template(),
            "json": self._default_json_template(),
            "yaml": self._default_yaml_template(),
        }

    def generate(
        self,
        state: SimulationState,
        report: SynthesisReport,
        format: Optional[str] = None,
    ) -> str:
        """
        Generate a report in the specified format.

        Args:
            state: Final SimulationState from the simulation
            report: SynthesisReport from the PredictionSynthesizer
            format: Output format ('markdown', 'json', 'yaml').
                   If None, uses self.default_format.

        Returns:
            Rendered report as a string

        Raises:
            ValueError: If format is not supported
        """
        fmt = format or self.default_format

        if fmt not in ["markdown", "json", "yaml"]:
            raise ValueError(
                f"Unsupported format: {fmt}. Use 'markdown', 'json', or 'yaml'"
            )

        # Prepare comprehensive context for templates
        context = self._prepare_context(state, report)

        # Get template
        if self.env and fmt in self.env.list_templates():
            template = self.env.get_template(f"report.{fmt}.j2")
        else:
            template_str = self._templates[fmt]
            template = Template(template_str)

        return template.render(**context)

    def generate_all_formats(
        self, state: SimulationState, report: SynthesisReport
    ) -> Dict[str, str]:
        """
        Generate reports in all supported formats.

        Args:
            state: Final SimulationState
            report: SynthesisReport

        Returns:
            Dictionary mapping format names to rendered report strings
        """
        return {
            fmt: self.generate(state, report, fmt)
            for fmt in ["markdown", "json", "yaml"]
        }

    def export(
        self,
        state: SimulationState,
        report: SynthesisReport,
        output_dir: Path,
        filename_prefix: Optional[str] = None,
        formats: Optional[list] = None,
    ) -> Dict[str, Path]:
        """
        Generate and export reports to filesystem.

        Args:
            state: Final SimulationState
            report: SynthesisReport
            output_dir: Directory to save report files
            filename_prefix: Prefix for filename (default: scenario title or 'report')
            formats: List of formats to export. If None, uses default_format only.
                    Use ['all'] for all formats.

        Returns:
            Dictionary mapping format names to Path objects of saved files

        Example:
            generator.export(state, report, Path("./reports"), formats=["markdown", "json"])
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine filename prefix
        if not filename_prefix:
            filename_prefix = state.scenario.title or "report"
            # Sanitize filename
            filename_prefix = "".join(
                c if c.isalnum() or c in (" ", "-", "_") else "_"
                for c in filename_prefix
            ).strip()

        # Determine which formats to generate
        if formats is None:
            formats = [self.default_format]
        elif "all" in formats:
            formats = ["markdown", "json", "yaml"]

        saved_files = {}

        for fmt in formats:
            try:
                content = self.generate(state, report, fmt)
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"{filename_prefix}_{timestamp}.{fmt}"
                filepath = output_dir / filename
                filepath.write_text(content, encoding="utf-8")
                saved_files[fmt] = filepath
            except Exception as e:
                # Log error but continue with other formats
                import logging

                logging.error(f"Failed to export {fmt}: {e}")

        return saved_files

    def _prepare_context(
        self, state: SimulationState, report: SynthesisReport
    ) -> Dict[str, Any]:
        """
        Prepare comprehensive context dictionary for template rendering.

        Args:
            state: SimulationState
            report: SynthesisReport

        Returns:
            Dictionary with all data needed for templates
        """
        # Build round summaries
        round_summaries = []
        for r in range(1, state.round + 1):
            round_summaries.append(state.get_round_summary(r))

        # Build full message history for each agent
        agent_messages = {}
        for agent in state.agents:
            agent_msgs = [m for m in state.message_history if m.agent_id == agent.id]
            agent_messages[agent.id] = agent_msgs

        context = {
            # Scenario info
            "scenario": state.scenario,
            "scenario_summary": {
                "title": state.scenario.title or "Untitled Scenario",
                "seed_text": state.scenario.seed_text,
                "context": state.scenario.context,
                "extracted_entities": state.scenario.extracted_entities,
                "extracted_relationships": state.scenario.extracted_relationships,
                "initial_facts": [f.model_dump() for f in state.scenario.initial_facts],
            },
            # Agent lineup
            "agents": state.agents,
            "agent_lineup": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "background": agent.background,
                    "traits": agent.traits,
                    "goals": agent.goals,
                    "biases": agent.biases,
                    "communication_style": agent.communication_style,
                }
                for agent in state.agents
            ],
            # Round evolution
            "total_rounds": state.round,
            "round_summaries": round_summaries,
            "message_count": len(state.message_history),
            # Final prediction (from report)
            "consensus_facts": report.consensus_facts,
            "dissent_points": report.dissent_points,
            "unresolved_facts": report.unresolved_facts,
            # Divergence analysis
            "agent_alignments": report.agent_alignments,
            "overall_consensus_strength": report.overall_consensus_strength,
            "consensus_fact_count": report.consensus_fact_count,
            "dissent_fact_count": report.dissent_fact_count,
            "total_facts_extracted": report.total_facts_extracted,
            # Metadata
            "synthesized_at": report.synthesized_at,
            "generated_at": datetime.utcnow(),
            "protocol": state.protocol.value,
        }

        return context

    def _default_markdown_template(self) -> str:
        """Default Jinja2 template for Markdown output."""
        return """
# Simulation Report: {{ scenario_summary.title }}

**Generated:** {{ generated_at.strftime('%Y-%m-%d %H:%M:%S UTC') }}
**Synthesized:** {{ synthesized_at.strftime('%Y-%m-%d %H:%M:%S UTC') }}

---

## Scenario Summary

**Title:** {{ scenario_summary.title }}

**Seed Text:**
> {{ scenario_summary.seed_text }}

{% if scenario_summary.context %}
**Context:** {{ scenario_summary.context }}
{% endif %}

{% if scenario_summary.extracted_entities %}
### Extracted Entities
```json
{{ scenario_summary.extracted_entities | tojson(indent=2) }}
```
{% endif %}

{% if scenario_summary.initial_facts %}
### Initial Facts
{% for fact in scenario_summary.initial_facts %}
- **{{ fact.key }}:** {{ fact.value }} (confidence: {{ (fact.confidence*100)|round(1) }}%)
{% endfor %}
{% endif %}

---

## Agent Lineup

**Total Agents:** {{ total_agents }}

{% for agent in agent_lineup %}
### {{ agent.name }} (ID: {{ agent.id }})

- **Background:** {{ agent.background }}
- **Traits:** {{ agent.traits | join(', ') }}
- **Goals:**
{% for goal in agent.goals %}
  - {{ goal }}
{% endfor %}
- **Biases:** {{ agent.biases | join(', ') if agent.biases else 'None' }}
- **Communication Style:** {{ agent.communication_style }}

{% endfor %}

---

## Round Evolution

**Total Rounds:** {{ total_rounds }}
**Total Messages:** {{ message_count }}

{% for round in round_summaries %}
### Round {{ round.round }}

- **Messages:** {{ round.message_count }}
- **Participants:** {{ round.participants | join(', ') }}
- **New Facts:** {{ round.new_facts }}

{% if round.facts %}
**Facts extracted this round:**
{% for fact in round.facts %}
- **{{ fact.key }}:** {{ fact.value }} (confidence: {{ (fact.confidence*100)|round(1) }}%)
{% endfor %}
{% endif %}

{% endfor %}

---

## Final Prediction

### Consensus Facts ({{ consensus_fact_count }})

{% for fact in consensus_facts %}
#### {{ fact.key }}

**Value:** {{ fact.value }}

- **Confidence:** {{ (fact.confidence*100)|round(1) }}%
- **Supporting Agents:** {{ fact.supporting_agents | join(', ') }}
- **Evidence:**
{% for ev in fact.evidence[:3] %}
  > {{ ev }}
{% endfor %}
{% if fact.evidence|length > 3 %}
  *...and {{ fact.evidence|length - 3 }} more evidence items*
{% endif %}

{% endfor %}

### Dissent Points ({{ dissent_fact_count }})

{% for fact in dissent_points %}
#### {{ fact.key }}

**Value:** {{ fact.value }}

- **Supporting:** {{ fact.supporting_agents | join(', ') }}
- **Opposing:** {{ fact.opposing_agents | join(', ') }}
- **Evidence:**
{% for ev in fact.evidence[:2] %}
  > {{ ev }}
{% endfor %}
{% if fact.evidence|length > 2 %}
  *...and {{ fact.evidence|length - 2 }} more evidence items*
{% endif %}

{% endfor %}

{% if unresolved_facts %}
### Unresolved Facts ({{ unresolved_facts|length }})

{% for fact in unresolved_facts %}
- **{{ fact.key }}:** {{ fact.value }}
{% endfor %}
{% endif %}

---

## Divergence Analysis

### Overall Consensus Strength
{{ (overall_consensus_strength*100)|round(1) }}%

---

### Agent Alignment Scores

| Agent | Alignment Score | Unique Contributions | Dissenting Positions |
|-------|----------------|----------------------|---------------------|
{% for agent_id, alignment in agent_alignments.items() %}
| {{ alignment.agent_name }} | {{ (alignment.consensus_alignment_score*100)|round(1) }}% | {{ alignment.unique_contributions|length }} | {{ alignment.dissenting_positions|length }} |
{% endfor %}

{% for agent_id, alignment in agent_alignments.items() %}
{% if alignment.unique_contributions %}
**{{ alignment.agent_name }}** uniquely contributed: {{ alignment.unique_contributions | join(', ') }}
{% endif %}
{% endfor %}

---

### Key Insights

- **Total Facts Extracted:** {{ total_facts_extracted }}
- **Consensus Rate:** {{ (consensus_fact_count/total_facts_extracted*100)|round(1) if total_facts_extracted > 0 else 0 }}%
- **Dissent Rate:** {{ (dissent_fact_count/total_facts_extracted*100)|round(1) if total_facts_extracted > 0 else 0 }}%
- **Protocol Used:** {{ protocol }}

---

*End of Report*
"""  # noqa: E501

    def _default_json_template(self) -> str:
        """Default Jinja2 template for JSON output."""
        return """{
  "scenario": {{ scenario_summary | tojson }},
  "agents": {{ agent_lineup | tojson }},
  "simulation": {
    "total_rounds": {{ total_rounds }},
    "total_messages": {{ message_count }},
    "round_summaries": {{ round_summaries | tojson }}
  },
  "synthesis": {
    "consensus_facts": {{ consensus_facts | tojson }},
    "dissent_points": {{ dissent_points | tojson }},
    "unresolved_facts": {{ unresolved_facts | tojson }},
    "agent_alignments": {{ agent_alignments | tojson }},
    "overall_consensus_strength": {{ overall_consensus_strength }},
    "consensus_fact_count": {{ consensus_fact_count }},
    "dissent_fact_count": {{ dissent_fact_count }},
    "total_facts_extracted": {{ total_facts_extracted }}
  },
  "metadata": {
    "synthesized_at": "{{ synthesized_at.isoformat() }}",
    "generated_at": "{{ generated_at.isoformat() }}",
    "protocol": "{{ protocol }}"
  }
}"""

    def _default_yaml_template(self) -> str:
        """Default Jinja2 template for YAML output."""
        return """scenario:
  title: "{{ scenario_summary.title }}"
  seed_text: "{{ scenario_summary.seed_text }}"
  context: {% if scenario_summary.context %}"{{ scenario_summary.context }}"{% else %}null{% endif %}
  extracted_entities: {{ scenario_summary.extracted_entities | tojson }}
  initial_facts: {{ scenario_summary.initial_facts | tojson }}

agents:
{% for agent in agent_lineup %}
  - id: "{{ agent.id }}"
    name: "{{ agent.name }}"
    background: "{{ agent.background }}"
    traits: {{ agent.traits | tojson }}
    goals: {{ agent.goals | tojson }}
    biases: {{ agent.biases | tojson }}
    communication_style: "{{ agent.communication_style }}"
{% endfor %}

simulation:
  total_rounds: {{ total_rounds }}
  total_messages: {{ message_count }}
  round_summaries: {{ round_summaries | tojson }}

synthesis:
  consensus_facts: {{ consensus_facts | tojson }}
  dissent_points: {{ dissent_points | tojson }}
  unresolved_facts: {{ unresolved_facts | tojson }}
  agent_alignments: {{ agent_alignments | tojson }}
  overall_consensus_strength: {{ overall_consensus_strength }}
  consensus_fact_count: {{ consensus_fact_count }}
  dissent_fact_count: {{ dissent_fact_count }}
  total_facts_extracted: {{ total_facts_extracted }}

metadata:
  synthesized_at: "{{ synthesized_at.isoformat() }}"
  generated_at: "{{ generated_at.isoformat() }}"
  protocol: "{{ protocol }}"
"""


# Convenience function for one-off report generation
async def generate_report(
    state: SimulationState,
    synthesizer: Optional[PredictionSynthesizer] = None,
    format: str = "markdown",
    output_dir: Optional[Path] = None,
    template_dir: Optional[Path] = None,
) -> str:
    """
    Convenience function to generate a report from a simulation state.

    Args:
        state: Final SimulationState (must have completed simulation)
        synthesizer: PredictionSynthesizer instance (creates default if None)
        format: Output format ('markdown', 'json', 'yaml')
        output_dir: If provided, also saves to filesystem
        template_dir: Custom template directory

    Returns:
        Rendered report string

    Example:
        report = await generate_report(final_state, format="markdown")
    """
    if synthesizer is None:
        synthesizer = PredictionSynthesizer()

    report = await synthesizer.synthesize(state)
    generator = ReportGenerator(template_dir=template_dir, default_format=format)
    output = generator.generate(state, report, format)

    if output_dir:
        generator.export(state, report, output_dir)

    return output
