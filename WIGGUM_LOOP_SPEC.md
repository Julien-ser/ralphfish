# Wiggum Loop Specification

## Overview

The Wiggum loop is a multi-agent simulation system where AI agents with distinct personas interact to analyze scenarios and make predictions. The system orchestrates N agents through M rounds of structured discourse, evolving a shared state and producing aggregated predictions with confidence metrics.

## Core Components

### 1. Simulation State

```python
class SimulationState:
    round: int                    # Current round number (0-indexed)
    agents: List[Agent]           # All agents in the simulation
    scenario: Scenario            # The seed scenario being analyzed
    world_facts: Dict             # Shared facts and context
    message_history: List[Message]  # Complete interaction log
    round_states: List[RoundState]   # Per-round state snapshots
    final_predictions: Dict       # Aggregated results from final round
```

### 2. Agent Persona

```python
class AgentPersona:
    name: str                     # Agent identifier
    background: str               # Professional/personal history
    traits: List[str]             # Personality characteristics
    goals: List[str]              # Primary objectives
    biases: List[str]             # Known cognitive biases
    communication_style: str      # How they express themselves
```

### 3. Message Structure

```python
class Message:
    round: int
    agent_id: str
    agent_name: str
    role: str                     # "reasoning", "proposal", "critique", "vote"
    content: str                  # The actual message text
    timestamp: datetime
    referenced_messages: List[int] # IDs of messages this responds to
    confidence: float             # Agent's confidence in this message (0-1)
```

### 4. Round State

```python
class RoundState:
    round_number: int
    messages: List[Message]       # All messages in this round
    consensus_score: float        # Agreement level (0-1)
    topics_discussed: List[str]   # Extracted themes
    state_snapshot: Dict         # Serialized state at round end
```

## The Wiggum Loop: Iteration Pattern

### Pseudocode

```
function run_wiggum_simulation(scenario, agents, num_rounds, interaction_protocol):
    // Initialization Phase
    state = SimulationState(
        round=0,
        agents=agents,
        scenario=scenario,
        world_facts=extract_initial_facts(scenario),
        message_history=[],
        round_states=[],
        final_predictions={}
    )

    // Pre-round: Each agent reasons privately
    for agent in agents:
        reasoning = agent.private_reasoning(state)
        state.message_history.append(reasoning)

    // Main Interaction Loop
    for round_num in 0 to num_rounds-1:
        state.round = round_num

        // Phase 1: Interaction
        messages_this_round = []

        // Turn-based interaction according to protocol
        for turn in interaction_protocol.turns:
            for agent in randomized_agent_order(agents):
                if turn.is_agent_turn(agent):
                    # Agent generates response based on context
                    context = build_context(
                        state,
                        messages_this_round,
                        turn.instruction
                    )

                    message = agent.generate_message(context, turn)
                    messages_this_round.append(message)
                    state.message_history.append(message)

        // Phase 2: State Update
        round_state = RoundState(
            round_number=round_num,
            messages=messages_this_round,
            consensus_score=calculate_consensus(messages_this_round),
            topics_discussed=extract_topics(messages_this_round),
            state_snapshot=serialize_state(state)
        )
        state.round_states.append(round_state)

        // Phase 3: Aggregation (Partial, per-round)
        if round_num == num_rounds - 1:
            # Final aggregation
            state.final_predictions = aggregate_final_predictions(
                messages_this_round,
                state.world_facts
            )
        else:
            # Optional: mid-simulation synthesis to guide next round
            synthesis = synthesize_round_summary(round_state)
            state.world_facts.update(synthesis.extracted_facts)

        // Phase 4: Memory Management
        trim_agent_histories(agents, max_tokens=config.context_window)

    return state
```

## State Transition Rules

### Transition 1: Initialization → Round 0
**Trigger**: Simulation start
**Actions**:
- Parse scenario into structured Scenario object
- Extract initial world facts from scenario seed text
- Generate initial private reasoning from each agent
- Validate all agents have valid personas
**Guards**:
- All agent personas must be valid (non-empty name, goals)
- Scenario must contain at least one extractable fact/entity
- Number of agents >= 2

### Transition 2: Round N → Round N+1
**Trigger**: Completion of all turns in current round
**Actions**:
- Calculate consensus metrics for the round
- Extract new facts/topics from round messages
- Update world_facts with verified new information
- Optionally inject a "moderator" summary message
- Trim agent context windows to respect token limits
**Guards**:
- Every agent must have participated in required turns
- No duplicate message IDs
- Round state must serialize correctly

### Transition 3: Round M-1 → Final Aggregation
**Trigger**: Final round completed (round == num_rounds - 1)
**Actions**:
- Collect all final round messages
- Extract predictions from designated "prediction" role messages
- Calculate confidence scores based on:
  - Agent's self-reported confidence
  - Agreement with other agents
  - Historical accuracy (if available)
- Perform divergence analysis:
  - Identify consensus viewpoints
  - Flag significant outliers
  - Compute polarization metrics
**Guards**:
- At least 2 predictions must be extracted
- Confidence scores must sum to 1.0 (normalized)

### Transition 4: Aggregation → Termination
**Trigger**: Final predictions computed
**Actions**:
- Serialize full state to disk
- Generate reports (JSON, YAML, Markdown)
- Log simulation statistics:
  - Total messages exchanged
  - Average round consensus
  - Token usage
  - API call counts
**Guards**:
- Report templates must exist
- Output directory must be writable

## Interaction Protocols

### Discuss Protocol
All agents can respond to any message. Free-form discussion.
- Turns: [broadcast, reply, broadcast, reply, ...]
- Goal: Open exploration

### Debate Protocol
Agents assigned to "pro" or "con" positions on scenario claims.
- Turns: [pro_position, con_position, rebuttal_pro, rebuttal_con, ...]
- Goal: Structured argumentation

### Vote Protocol
Agents first discuss, then cast independent votes.
- Turns: [discuss (3 turns), vote]
- Vote role messages contain numeric scores/ratings

## Agent Reasoning Flow

```
For each agent per turn:
    1. Retrieve relevant context from:
       - Scenario description
       - Current round state
       - Recent message history (last N messages)
       - Agent's persona and goals

    2. Construct prompt:
       - System: Agent persona + simulation rules
       - User: Context + turn instruction + response format

    3. Call LLM with:
       - Model: configurable (default: openai/gpt-4)
       - Max tokens: configurable (default: 1000)
       - Temperature: 0.7 (allows some variance)

    4. Parse response:
       - Validate required fields (role, content, confidence)
       - Extract structured data if applicable
       - Log to agent's message history

    5. Update agent state:
       - Add message to personal history
       - Update token usage counter
```

## Aggregation Algorithms

### Consensus Score
```
For round with messages M:
  similarity_matrix = pairwise_message_similarity(M)
  consensus = average(similarity_matrix) * message_count_factor
  returns float in [0, 1]
```

### Confidence Scoring
```
For each prediction p from agent a:
  self_confidence = p.confidence (from agent's self-assessment)
  agreement_score = average(similarity(p, all_other_predictions))
  final_score = (0.4 * self_confidence) + (0.6 * agreement_score)
  returns normalized confidence in [0, 1]
```

### Divergence Analysis
```
- Identify clusters of similar predictions using DBSCAN
- Outliers = predictions not in any cluster with >=2 members
- Polarization = (num_outliers / total_predictions)
- Entropy = Shannon entropy of prediction distribution
```

## Data Flow Diagram

```
Scenario (seed text)
    ↓
[Seed Parser]
    ↓
Scenario + World Facts
    ↓
Initialize Agents with Personas
    ↓
┌─────────────────────────────────────┐
│   Wiggum Loop (M rounds)            │
│  ┌─────────────────────────────┐   │
│  │ ROUND N                     │   │
│  │ 1. Agent Reasoning          │───┼──→ Message History
│  │ 2. Turn-based Interaction   │   │
│  │ 3. State Update             │───┼──→ Round State
│  │ 4. Fact Synthesis (optional)│   │
│  └─────────────────────────────┘   │
│         ↓                           │
│    Consensus Calc                   │
│    Memory Trim                      │
│         ↓                           │
│    [if final round]                │
│         ↓                           │
│    Prediction Aggregation           │
│    Confidence Scoring              │
│    Divergence Analysis              │
└─────────────────────────────────────┘
    ↓
Report Generation (JSON/YAML/Markdown)
Export to Filesystem
```

## Configuration

The loop behavior is configurable via:

```yaml
simulation:
  rounds: 5
  agents: 4
  protocol: "discuss"  # or "debate", "vote"

agents:
  persona_templates: "templates/personas/"
  model: "openai/gpt-4"  # OpenRouter model ID
  temperature: 0.7
  max_tokens: 1000
  context_window: 4096

aggregation:
  confidence_weights:
    self: 0.4
    agreement: 0.6
  clustering_epsilon: 0.3

output:
  formats: ["json", "markdown"]
  save_transcript: true
  timestamp_naming: true
```

## Proof of Correctness

### Invariants
1. **Round order**: Messages in `message_history` are strictly ordered by (round, turn, timestamp)
2. **Agent participation**: Each agent generates exactly `turns_per_round` messages per complete round
3. **State consistency**: `SimulationState` serialized snapshots can reconstruct full state
4. **Determinism**: Given fixed LLM outputs, simulation produces identical results (no random ordering without seed)

### Termination
The loop terminates after exactly `num_rounds` iterations, or earlier if:
- All agents converge (consensus > 0.95) and early stopping enabled
- API quota exhausted
- Critical error in agent messaging

## Implementation Notes

- Actual implementation will use Pydantic for data models
- Async execution via `asyncio` for concurrent LLM calls
- Rate limiting through OpenRouter's recommended backoff strategy
- Persistence: State saved as JSON after each round for crash recovery

## Next Steps After Specification

1. Design base Pydantic models (AgentPersona, SimulationState, Message, etc.)
2. Implement agent class with persona rendering and LLM isolation
3. Build the loop executor using the pseudocode above
4. Implement aggregation and report generation
5. Add CLI interface with arg parsing
