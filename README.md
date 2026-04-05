# Ralphfish - LLM Multi-Agent Simulation Engine

Ralphfish implements the Wiggum loop pattern for running multi-agent simulations with LLM-powered agents. Agents with distinct personas interact, debate, and make predictions through structured rounds.

## Quickstart

```bash
# Install dependencies
pip install -e .

# Run a simulation (after implementing)
python -m ralphfish.run-simulation --scenario scenario.txt --agents 3 --rounds 5
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

**Phase 1**: Planning & Setup - In Progress
- [x] Wiggum loop specification defined
- [ ] Python project structure (`pyproject.toml`)
- [ ] OpenRouter client wrapper
- [ ] Base data models

## Project Context

Part of the Wiggum ecosystem: autonomous OpenCode agent loops for complex simulation systems.
