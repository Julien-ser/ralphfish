# Ralphfish - LLM Multi-Agent Simulation Engine

Ralphfish implements the Wiggum loop pattern for running multi-agent simulations with LLM-powered agents. Agents with distinct personas interact, debate, and make predictions through structured rounds.

## Quickstart

```bash
# Install dependencies
pip install -e .

# Set your OpenRouter API key
export OPENROUTER_API_KEY="your-key-here"

# Example: Parse a seed document (see examples/parse_seed.py)
python examples/parse_seed.py
```

## Seed Parser

The seed parser extracts structured information from scenario text:

```python
import asyncio
from ralphfish import SeedParser, OpenRouterClient

async def extract():
    client = OpenRouterClient()
    parser = SeedParser(client=client)
    scenario = await parser.parse(
        seed_text="Your scenario description here...",
        title="My Scenario"
    )
    print(scenario.extracted_entities)
    print(scenario.initial_facts)
    await client.close()

asyncio.run(extract())
```

## Wiggum Loop Specification

The core iteration pattern is fully documented in [WIGGUM_SPECIFICATION.md](WIGGUM_SPECIFICATION.md), including:
- State machine transitions
- Interaction protocols (discuss/debate/vote)
- Pseudocode for the complete loop
- Aggregation and synthesis rules

## Architecture

- **Seed Parser**: Extracts entities and relationships from input text
- **Agent Engine**: Manages personas, LLM calls, and message history
- **Loop Executor**: Orchestrates rounds and state persistence
- **Synthesizer**: Aggregates final outputs into prediction reports
- **CLI**: Command interface for running simulations

## Agent Class

The `Agent` class is the core building block for creating autonomous agents:

```python
from ralphfish import Agent, AgentPersona, OpenRouterClient, AgentConfig

# Create a persona
persona = AgentPersona(
    id="analyst_001",
    name="Alice",
    background="Data scientist with expertise in statistics",
    traits=["analytical", "cautious", "thorough"],
    goals=["Provide accurate predictions", "Identify data inconsistencies"],
    biases=["Prefers quantitative evidence"],
    communication_style="formal"
)

# Create OpenRouter client
client = OpenRouterClient()

# Configure agent-specific settings (optional)
config = AgentConfig(
    model="anthropic/claude-instant-1.2",
    temperature=0.5,
    use_free_tier=True
)

# Create the agent
agent = Agent(
    persona=persona,
    client=client,
    config=config,
    max_history_length=100
)

# Generate a response (async)
response = await agent.generate_response(
    additional_context="Scenario context here...",
    round_num=1
)

print(response.content)  # Agent's response
print(agent.get_stats())  # Agent statistics
```

### Agent Features

- **Isolated State**: Each agent maintains its own message history
- **Per-Agent Configuration**: Custom model, temperature, and other LLM parameters
- **Persona Template Rendering**: Supports Jinja2 or simple .format() templates
- **History Management**: Automatic trimming to respect context window limits
- **Async Support**: Fully async for concurrent execution

### Creating Multiple Agents

```python
from ralphfish import create_agents

# Prepare personas list
personas = [...]  # List of AgentPersona objects

# Create all agents with shared client
agents = await create_agents(
    personas=personas,
    client=client,
    max_history_length=50
)
```

## Loop Executor

The `LoopExecutor` class orchestrates multiple agents through multiple rounds of interaction.

```python
import asyncio
from ralphfish import (
    Agent, AgentPersona, AgentConfig,
    OpenRouterClient,
    Scenario, SimulationState,
    LoopExecutor, InteractionProtocol,
    create_agents
)

async def run_sim():
    # Create OpenRouter client
    client = OpenRouterClient()
    
    # Define agent personas
    personas = [
        AgentPersona(
            id="analyst_001",
            name="Alice",
            background="Data scientist with expertise in statistics",
            traits=["analytical", "cautious", "thorough"],
            goals=["Provide accurate predictions", "Identify data inconsistencies"],
            biases=["Prefers quantitative evidence"],
            communication_style="formal"
        ),
        AgentPersona(
            id="optimist_002",
            name="Bob",
            background="Entrepreneur with optimistic outlook",
            traits=["optimistic", "risk-taking"],
            goals=["Identify opportunities", "Inspire confidence"],
            biases=["Overestimates success probability"],
            communication_style="casual"
        ),
    ]
    
    # Create agents from personas
    agents = await create_agents(personas, client)
    
    # Define the scenario
    scenario = Scenario(
        seed_text="Will the new product launch succeed?",
        context="A tech startup is launching a new AI-powered tool."
    )
    
    # Create the initial simulation state
    initial_state = SimulationState(
        scenario=scenario,
        agents=personas,
        protocol=InteractionProtocol.DISCUSSION
    )
    
    # Create and run the executor
    executor = LoopExecutor(
        agents=agents,
        initial_state=initial_state,
        rounds=3,
        protocol=InteractionProtocol.DISCUSSION,
        on_round_complete=None  # Optional: add fact extraction later
    )
    
    final_state = await executor.run()
    
    # Output results
    print(f"Simulation completed after {final_state.round} rounds")
    print(f"Total messages: {len(final_state.message_history)}")
    
    await client.close()

asyncio.run(run_sim())
```

Alternatively, use the convenience function:

```python
from ralphfish import run_simulation

final_state = await run_simulation(
    agents=agents,
    scenario=scenario,
    rounds=3,
    protocol=InteractionProtocol.DISCUSSION
)
```

The `on_round_complete` callback can be used to inject fact extraction or confidence scoring after each round; this will be implemented in the prediction synthesizer phase.

## Prediction Synthesizer

The `PredictionSynthesizer` analyzes the final state of a simulation to extract consensus, identify dissent, and compute confidence scores based on agent agreement.

```python
from ralphfish.synthesizer import PredictionSynthesizer

# After simulation completes
synthesizer = PredictionSynthesizer(
    consensus_threshold=0.7,      # 70% agreement required for consensus
    strong_consensus_threshold=0.9,
    min_agents_for_fact=2         # Minimum agents mentioning a fact
)

report = await synthesizer.synthesize(final_state)

# Print summary
print(report.get_summary())

# Access consensus facts
for fact in report.consensus_facts:
    print(f"Consensus: {fact.value}")
    print(f"  Confidence: {fact.confidence:.2%}")
    print(f"  Supporting agents: {', '.join(fact.supporting_agents)}")

# Access dissent points
for fact in report.dissent_points:
    print(f"Dissent: {fact.value}")
    print(f"  Support: {len(fact.supporting_agents)} vs {len(fact.opposing_agents)}")

# View agent alignments
for agent_id, alignment in report.agent_alignments.items():
    print(f"{alignment.agent_name}: {alignment.consensus_alignment_score:.2%} aligned with consensus")
```

The `SynthesisReport` includes:
- `consensus_facts`: Facts with high agreement
- `dissent_points`: Issues with significant disagreement
- `agent_alignments`: How each agent aligns with the consensus
- `overall_consensus_strength`: Single metric summarizing agreement level

Reports can be exported to JSON, YAML, or Markdown using the report generator.

## Report Generator

The `ReportGenerator` class creates comprehensive simulation reports in multiple formats using Jinja2 templates.

### Basic Usage

```python
from ralphfish import ReportGenerator, PredictionSynthesizer

# After simulation completes
synthesizer = PredictionSynthesizer()
report = await synthesizer.synthesize(final_state)

# Create a report generator
generator = ReportGenerator()

# Generate in different formats
markdown = generator.generate(final_state, report, format="markdown")
json_data = generator.generate(final_state, report, format="json")
yaml_data = generator.generate(final_state, report, format="yaml")

print(markdown)
```

### Exporting to Filesystem

```python
from pathlib import Path

# Export full reports with transcript (default)
saved_files = generator.export(
    final_state,
    report,
    output_dir=Path("./reports"),
    filename_prefix="my_simulation",
    formats=["markdown", "json", "yaml"]  # or use ["all"]
)

# Export summary-only reports (without round-by-round transcript)
summary_files = generator.export(
    final_state,
    report,
    output_dir=Path("./reports"),
    filename_prefix="my_simulation",
    formats=["all"],
    summary_only=True  # Omit detailed round evolution
)

# saved_files maps format -> Path object
print(f"Saved {len(saved_files)} reports")
```

### Using the Convenience Function

```python
from ralphfish import generate_report

# One-liner to generate and optionally save
report_md = await generate_report(
    state=final_state,
    format="markdown",
    output_dir=Path("./reports")
)
```

### Report Sections

All report formats include these sections:

1. **Scenario Summary**: Title, seed text, context, extracted entities, initial facts
2. **Agent Lineup**: All agents with their personas (background, traits, goals, biases, communication style)
3. **Round Evolution**: Message counts, participants, facts extracted per round
4. **Final Prediction**: Consensus facts, dissent points, unresolved facts with confidence scores
5. **Divergence Analysis**: Overall consensus strength, agent alignment scores, unique contributions, dissenting positions

### Custom Templates

You can provide custom Jinja2 templates:

```python
from pathlib import Path

custom_template_dir = Path("./my_templates")
generator = ReportGenerator(template_dir=custom_template_dir)

# Place templates named:
# - report.markdown.j2
# - report.json.j2
# - report.yaml.j2
```

Template variables are available in the context; see `ReportGenerator._prepare_context()` for the full structure.

## Development Status

**Phase 1**: Planning & Setup - ✅ Complete
- [x] Define the Wiggum loop specification
- [x] Set up Python project with `pyproject.toml`
- [x] Create OpenRouter API client wrapper
- [x] Design the base data models

**Phase 2**: Core Engine Development - ✅ Complete
- [x] Build seed document parser using LLM extraction
- [x] Implement `Agent` class with persona template rendering
- [x] Create Wiggum loop executor
- [x] Develop inter-agent communication layer with message passing, context window management, and memory summarization

**Phase 3**: Prediction & Output Generation - 🔄 In Progress
- [x] Build prediction synthesizer (aggregation, consensus/dissent detection, confidence scoring)
- [x] Implement structured report generator using Jinja2 templates (JSON, YAML, Markdown)
- [x] Add export functionality with timestamped filesystem output and summary-only option
- [ ] Create configurable persona generator

## Project Context

Part of the Wiggum ecosystem: autonomous OpenCode agent loops for complex simulation systems.
