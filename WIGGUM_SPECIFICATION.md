# Wiggum Loop Specification

## Overview

The Wiggum loop is a multi-agent simulation pattern where LLM-powered agents with distinct personas interact to solve problems, make predictions, or reach consensus. This document defines the exact iteration pattern, state transitions, and protocols.

## Core Concepts

- **Simulation Round**: A complete cycle where all agents have an opportunity to contribute
- **State**: The cumulative knowledge and facts accumulated up to the current round
- **Agent Persona**: Identity template (name, background, traits, goals) that shapes LLM responses
- **Interaction Protocol**: Rules for how agents communicate (discuss, debate, vote)

## State Machine

```
Initial State
    ↓
[Seed Document Parsed]
    ↓
[Scenario Initialized] → world_facts, agent_personas
    ↓
Round 1 ──→ Each agent reasons → interacts → state updated
    ↓
Round 2 ──→ Each agent reasons WITH context from Round 1 → interacts → state updated
    ↓
...
    ↓
Round M ──→ Final interactions
    ↓
[Aggregation Phase] → consensus analysis, confidence scoring, report generation
    ↓
[Complete]
```

## Detailed Iteration Pattern

### Pseudocode

```
function wiggum_loop(scenario_seed, num_agents, num_rounds, protocol):
    # Phase 0: Extraction
    entities = parse_seed(scenario_seed)
    
    # Phase 1: Initialization
    personas = generate_personas(num_agents)
    state = SimulationState(
        round=0,
        agents=personas,
        world_facts=entities,
        message_history=[]
    )
    
    # Phase 2: Iteration Loop
    for round in 1 to num_rounds:
        state.round = round
        
        # Shuffle turn order (or use defined protocol)
        turn_order = determine_turn_order(state.agents, protocol)
        
        for agent_id in turn_order:
            # Build context for this agent
            context = build_agent_context(
                agent=state.agents[agent_id],
                state=state,
                protocol=protocol,
                round_history=get_round_messages(state.message_history, round)
            )
            
            # Agent reasoning (LLM call)
            thought, action = agent_reason(context)
            
            # Record the reasoning
            message = Message(
                round=round,
                agent_id=agent_id,
                thought=thought,
                action=action,
                timestamp=now()
            )
            state.message_history.append(message)
            
            # State update based on action
            state = update_state(state, message, protocol)
            
            # Optional: memory summarization if context exceeds limits
            if context_window_exceeded(state):
                state = summarize_memory(state)
        
        # End of round: produce aggregated state snapshot
        state = aggregate_round(state, round)
    
    # Phase 3: Final Synthesis
    report = synthesize_prediction(state)
    
    return report
```

## State Transition Rules

### State Structure

```python
@dataclass
class SimulationState:
    round: int
    agents: List[AgentPersona]
    world_facts: Dict[str, Any]  # Extracted entities, relationships
    message_history: List[Message]
    aggregated_facts: List[Fact]  # Consensus facts after each round
    dissent_points: List[Dissent]  # Points of disagreement
    confidence_scores: Dict[str, float]  # Per-topic confidence
```

### Transition Triggers

1. **Round Start** → `state.round` increments, turn order determined
2. **Agent Message** → `state.message_history` appended, `world_facts` potentially updated
3. **Protocol Complete** (all agents acted) → `aggregate_round()` called, `aggregated_facts` updated
4. **Conflict Detected** → ` dissent_points` records disagreement
5. **Consensus Reached** → confidence scores adjusted upward
6. **Final Round** → transition to synthesis phase

### Update Rules

```python
def update_state(state: SimulationState, message: Message, protocol: Protocol) -> SimulationState:
    # Extract facts from message
    new_facts = extract_facts(message.content)
    
    # Merge with existing world facts
    for fact in new_facts:
        if fact.key in state.world_facts:
            # Check for agreement/disagreement
            if fact.value == state.world_facts[fact.key]:
                state.confidence_scores[fact.key] += PROTOCOL_CONFIDENCE_INCREMENT
            else:
                # Record dissent
                state.dissent_points.append(Dissent(
                    fact_key=fact.key,
                    values=[state.world_facts[fact.key], fact.value],
                    agents=[message.agent_id, holder_of_old_value]
                ))
                state.confidence_scores[fact.key] -= DISSENT_PENALTY
        else:
            # New fact, add with initial confidence
            state.world_facts[fact.key] = fact.value
            state.confidence_scores[fact.key] = INITIAL_CONFIDENCE
    
    return state
```

## Interaction Protocols

### Protocol: DISCUSSION
- **Turn order**: Round-robin (all agents speak once per round)
- **Action types**: Share observation, ask question, propose hypothesis
- **State update**: Facts added with confidence +0.1
- **End condition**: All agents have spoken

### Protocol: DEBATE
- **Turn order**: Randomized per round
- **Action types**: Support claim, challenge claim, present evidence
- **State update**: Agreement → confidence +0.2, Disagreement → confidence -0.1, record dissent
- **End condition**: Predefined number of turns OR consensus threshold reached

### Protocol: VOTING
- **Turn order**: Sequential (each agent sees previous votes)
- **Action types**: Cast vote with reasoning
- **State update**: Track vote counts, compute statistical confidence
- **End condition**: All agents voted OR supermajority achieved

## Aggregation Phase Logic

After all rounds complete:

```python
def aggregate_final_state(state: SimulationState) -> Report:
    # Compute consensus metrics
    consensus_facts = {
        key: value
        for key, value in state.world_facts.items()
        if state.confidence_scores[key] >= CONSENSUS_THRESHOLD
    }
    
    dissent_clusters = cluster_dissent(state.dissent_points)
    
    # Generate report
    return Report(
        scenario_summary=summarize_scenario(state.world_facts),
        agent_lineup=format_agents(state.agents),
        round_evolution=extract_round_transitions(state.message_history),
        final_prediction=extract_consensus(consensus_facts),
        divergence_analysis=analyze_dissent_clusters(dissent_clusters),
        confidence_scores=state.confidence_scores
    )
```

## State Persistence

Between iterations:
- Serialize `SimulationState` to JSON after each round for checkpoint/resume
- Store full message history separately for transcript dumps
- Keep aggregated facts in memory for performance

## Exit Conditions

The loop terminates when:
1. Maximum rounds reached (`round == M`)
2. Early stopping: consensus threshold met on all key facts
3. Confidence stabilization: no significant changes in confidence scores for 3 consecutive rounds

## Configuration Parameters

```yaml
wiggum:
  max_rounds: 10
  consensus_threshold: 0.7
  confidence_increment: 0.1
  dissent_penalty: 0.1
  early_stop_stable_rounds: 3
  context_window_limit: 4000  # tokens
  summarization_trigger: 0.8  # when 80% of window used
  protocol: "debate"  # discussion, debate, or voting
```

---

This specification defines the exact pattern: agents reason based on persona + current state → produce actions → state updates via fact extraction → round aggregation → repeat → final synthesis.
