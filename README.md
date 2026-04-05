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

## Development Status

**Phase 1**: Planning & Setup - ✅ Complete
- [x] Wiggum loop specification defined
- [x] Python project structure (`pyproject.toml`)
- [x] OpenRouter client wrapper
- [x] Base data models

**Phase 2**: Core Engine Development - In Progress
- [x] Build seed document parser using LLM extraction
- [ ] Implement `Agent` class with persona template rendering
- [ ] Create Wiggum loop executor
- [ ] Develop inter-agent communication layer

## Project Context

Part of the Wiggum ecosystem: autonomous OpenCode agent loops for complex simulation systems.
