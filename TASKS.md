# ralphfish

## Phase 1: Planning & Setup
- [x] Define the Wiggum loop specification: document the exact iteration pattern (agent reasoning → interaction → state update → aggregation) with pseudocode and state transition rules
- [x] Set up Python project with `pyproject.toml`, including dependencies: `openai` (OpenRouter SDK), `pydantic` (data validation), `jinja2` (templating), `python-dotenv` (config)
- [ ] Create OpenRouter API client wrapper with free-tier model routing, request/response logging, and exponential backoff retry logic
- [ ] Design the base data models: `AgentPersona` (name, background, traits, goals), `SimulationState` (round, agents, world facts), `Scenario` (seed text, extracted entities)

## Phase 2: Core Engine Development
- [ ] Build seed document parser using LLM extraction: parse user input to identify key entities, relationships, conflicts, and initial conditions (output: structured JSON)
- [ ] Implement `Agent` class with persona template rendering, message history management, and per-agent LLM call isolation
- [ ] Create Wiggum loop executor: orchestrate N agents for M rounds, managing turn order, interaction protocols (discuss/debate/vote), and state persistence between rounds
- [ ] Develop inter-agent communication layer: message passing with role labels, context window management, and optional memory summarization

## Phase 3: Prediction & Output Generation
- [ ] Build prediction synthesizer: aggregate final round outputs, extract consensus/dissent patterns, compute confidence scores based on agreement metrics
- [ ] Implement structured report generator using Jinja2 templates supporting JSON, YAML, and markdown outputs with sections: scenario summary, agent lineup, round evolution, final prediction, divergence analysis
- [ ] Add export functionality: save reports to filesystem with timestamped naming, option to dump full transcript or summary-only
- [ ] Create configurable persona generator: random persona creation within user-defined constraints ( archetypes, demographic ranges, bias patterns)

## Phase 4: Testing, Optimization & Documentation
- [ ] Write unit tests for all core components with mocked OpenRouter responses; achieve >90% coverage for state machines and data validation
- [ ] Implement concurrent agent execution using `asyncio` to parallelize LLM calls while respecting OpenRouter rate limits (configurable max_concurrent)
- [ ] Create CLI interface with `argparse`: commands for `run-simulation`, `generate-personas`, `export-report` with flags for agent count, rounds, model selection
- [ ] Write comprehensive README with quickstart example, architecture diagram, persona customization guide, and troubleshooting for common OpenRouter errors
