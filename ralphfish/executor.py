"""Wiggum Loop Executor for multi-agent simulations.

This module provides the core LoopExecutor class which orchestrates multiple
agents through repeated rounds of interaction according to a specified protocol.
The executor manages turn order, message passing, state persistence, and
provides hooks for post-round processing such as fact extraction.
"""

import asyncio
import logging
from typing import List, Optional, Callable, Any
from .models import SimulationState, InteractionProtocol, Message
from .agent import Agent

logger = logging.getLogger(__name__)


class LoopExecutor:
    """Orchestrates a multi-agent simulation over multiple rounds.

    The LoopExecutor is the central engine of the Wiggum loop. It takes a
    group of agents, an initial simulation state, and runs them through a
    series of rounds where they interact according to the specified protocol.

    Key responsibilities:
    - Manage turn order and round progression
    - Facilitate message passing between agents
    - Update and persist simulation state
    - Provide extension points via callbacks
    """

    def __init__(
        self,
        agents: List[Agent],
        initial_state: SimulationState,
        rounds: int,
        protocol: InteractionProtocol = InteractionProtocol.DISCUSSION,
        on_round_complete: Optional[Callable[[int, SimulationState], Any]] = None,
    ):
        """
        Initialize the loop executor.

        Args:
            agents: List of Agent instances to participate in the simulation.
                All agents should share the same OpenRouter client for connection pooling.
            initial_state: SimulationState object containing initial scenario,
                agent personas, and any pre-existing world facts.
            rounds: Number of rounds to execute (must be >= 1).
            protocol: Interaction protocol to use; defaults to DISCUSSION.
                Supported protocols: DISCUSSION, DEBATE, VOTING.
            on_round_complete: Optional callback invoked after each round completes.
                The callback receives (round_number, simulation_state) and may be
                a regular function or an async coroutine. Use this for fact extraction,
                confidence updates, or other post-round processing.

        Raises:
            ValueError: If agents list is empty or rounds is not positive.
        """
        if not agents:
            raise ValueError("At least one agent is required")
        if rounds <= 0:
            raise ValueError("Number of rounds must be positive")

        self.agents = agents
        self.state = initial_state
        self.rounds = rounds
        self.protocol = protocol
        self.on_round_complete = on_round_complete

        # Ensure state has the right agents list (sync with provided agents)
        self.state.agents = [agent.persona for agent in agents]

    async def run(self) -> SimulationState:
        """
        Execute the simulation loop for all rounds.

        Returns:
            The final SimulationState containing all messages, facts, and aggregated
            results after the last round.
        """
        logger.info(
            "Starting Wiggum loop",
            extra={
                "agent_count": len(self.agents),
                "rounds": self.rounds,
                "protocol": self.protocol,
                "scenario": self.state.scenario.title or "Untitled",
            },
        )

        try:
            for round_num in range(1, self.rounds + 1):
                self.state.round = round_num
                logger.info("Starting round", extra={"round": round_num})

                # Execute the round according to protocol
                await self._execute_round(round_num)

                # Post-round processing
                if self.on_round_complete:
                    await self._safe_call_round_complete(round_num)

                # Prepare agents for next round (clear round-specific caches)
                for agent in self.agents:
                    agent.start_new_round()

                logger.info("Round completed", extra={"round": round_num})

            logger.info("Simulation completed successfully")
            return self.state

        except Exception as e:
            logger.error("Simulation failed", exc_info=True)
            raise

    async def _execute_round(self, round_num: int):
        """Execute a single round using the configured protocol."""
        protocol_handlers = {
            InteractionProtocol.DISCUSSION: self._execute_discussion,
            InteractionProtocol.DEBATE: self._execute_debate,
            InteractionProtocol.VOTING: self._execute_voting,
        }

        handler = protocol_handlers.get(self.protocol)
        if handler is None:
            raise NotImplementedError(f"Protocol '{self.protocol}' is not implemented")

        await handler(round_num)

    async def _execute_discussion(self, round_num: int):
        """
        Discussion protocol: agents take sequential turns.

        Each agent, when it's their turn:
        - Receives all messages from previous rounds
        - Receives all messages already sent in the current round
        - Generates a response
        - That response is broadcast to all other agents

        Turn order is the order of agents in the list.
        """
        for agent in self.agents:
            # Gather messages this agent can see
            visible_messages = self._get_visible_messages(agent, round_num)
            conversation_context = self._format_conversation(visible_messages)

            # Build additional context (scenario, previous round summary)
            additional = self._build_round_intro(round_num)

            # Combine contexts
            full_prompt = self._combine_contexts(additional, conversation_context)

            # Generate response
            response = await agent.generate_response(
                additional_context=full_prompt, round_num=round_num
            )

            # Update global state
            self.state.message_history.append(response)

            # Broadcast to other agents
            self._broadcast(response, exclude=agent)

            logger.debug(
                "Agent response recorded",
                extra={
                    "agent": agent.persona.name,
                    "round": round_num,
                    "msg_id": response.timestamp,
                },
            )

        # After all agents have spoken, optionally trigger memory summarization
        await self._maybe_summarize_all_agents(round_num)

    async def _execute_debate(self, round_num: int):
        """
        Debate protocol: structured debate with sides.

        This is a placeholder for future implementation. Currently falls back
        to discussion. In a full implementation, agents would be assigned roles
        (proposition, opposition) and the turn order might alternate between sides.
        """
        logger.info(
            "Debate protocol selected but not fully implemented, using discussion"
        )
        await self._execute_discussion(round_num)

    async def _execute_voting(self, round_num: int):
        """
        Voting protocol: agents cast votes, possibly after discussion.

        This is a placeholder for future implementation. Currently falls back
        to discussion. A full implementation might have two phases: discussion
        round(s) followed by a voting round where each agent outputs a structured vote.
        """
        logger.info(
            "Voting protocol selected but not fully implemented, using discussion"
        )
        await self._execute_discussion(round_num)

    def _get_visible_messages(self, agent: Agent, current_round: int) -> List[Message]:
        """
        Determine which messages an agent can see at the start of their turn.

        An agent can see:
        - All messages from previous rounds
        - All messages from the current round that were generated by agents who have already taken their turn
        (The agent does not see its own message from the current round until after it generates it)
        """
        visible = []
        # Previous rounds
        visible.extend(m for m in self.state.message_history if m.round < current_round)
        # Current round: only messages from agents who already went this round
        visible.extend(
            m for m in self.state.message_history if m.round == current_round
        )
        return visible

    def _format_conversation(self, messages: List[Message]) -> str:
        """Format messages into a readable conversation transcript."""
        if not messages:
            return ""
        lines = ["## Conversation Transcript"]
        # Sort by round then timestamp to preserve order
        sorted_msgs = sorted(messages, key=lambda m: (m.round, m.timestamp))
        for msg in sorted_msgs:
            lines.append(f"[Round {msg.round}] {msg.agent_name}: {msg.content}")
        return "\n".join(lines)

    def _build_round_intro(self, round_num: int) -> str:
        """Build introductory context for the current round."""
        parts = []
        # Include scenario context once (maybe only for round 1)
        if round_num == 1 and self.state.scenario.context:
            parts.append(f"Scenario: {self.state.scenario.context}")
        # Include previous round summary
        if round_num > 1:
            prev = self.state.get_round_summary(round_num - 1)
            parts.append(
                f"Round {round_num - 1} recap: {prev['message_count']} messages from {len(prev['participants'])} participants"
            )
        return "\n".join(parts) if parts else ""

    def _combine_contexts(self, intro: str, conversation: str) -> str:
        """Combine the round intro and conversation context into a single prompt."""
        parts = []
        if intro:
            parts.append(intro)
        if conversation:
            parts.append(conversation)
        return "\n\n".join(parts) if parts else ""

    def _broadcast(self, message: Message, exclude: Agent):
        """Send a message to all agents except the excluded one."""
        for agent in self.agents:
            if agent.persona.id != exclude.persona.id:
                agent.add_message(message)

    async def _maybe_summarize_all_agents(self, round_num: int):
        """
        Trigger memory summarization for all agents that have it enabled.

        This is called after all agents have taken their turn in a round.
        Summarization runs concurrently but with limited parallelism.
        """
        tasks = []
        for agent in self.agents:
            if agent.config.enable_summarization:
                tasks.append(agent.maybe_summarize(round_num))

        if tasks:
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(
                            "Summarization failed",
                            extra={"error": str(result), "round": round_num},
                        )
                    elif result:
                        logger.debug(
                            "Summarization completed",
                            extra={
                                "agent_id": result.agent_id,
                                "round": round_num,
                            },
                        )
            except Exception as e:
                logger.error("Summarization batch failed", exc_info=True)

    async def _safe_call_round_complete(self, round_num: int):
        """Safely invoke the round-complete callback, handling both sync and async."""
        try:
            result = self.on_round_complete(round_num, self.state)
            if result is not None and hasattr(result, "__await__"):
                await result
        except Exception as e:
            logger.error("Round complete callback raised exception", exc_info=True)
            # Continue execution despite callback failure


async def run_simulation(
    agents: List[Agent],
    scenario: "Scenario",
    rounds: int,
    protocol: InteractionProtocol = InteractionProtocol.DISCUSSION,
    on_round_complete: Optional[Callable] = None,
    initial_state: Optional[SimulationState] = None,
) -> SimulationState:
    """
    Convenience function to set up and run a simulation in one call.

    Args:
        agents: List of Agent instances
        scenario: Scenario object (seed document)
        rounds: Number of rounds
        protocol: Interaction protocol
        on_round_complete: Optional callback after each round
        initial_state: Optional pre-built SimulationState; if None, creates new one

    Returns:
        Final SimulationState
    """
    # Import here to avoid circular dependency
    from .models import Scenario

    if initial_state is None:
        initial_state = SimulationState(
            scenario=scenario,
            agents=[a.persona for a in agents],
            protocol=protocol,
        )
    else:
        # Ensure state is properly initialized
        if not initial_state.agents:
            initial_state.agents = [a.persona for a in agents]
        if not initial_state.scenario:
            initial_state.scenario = scenario
        initial_state.protocol = protocol

    executor = LoopExecutor(
        agents=agents,
        initial_state=initial_state,
        rounds=rounds,
        protocol=protocol,
        on_round_complete=on_round_complete,
    )
    return await executor.run()
