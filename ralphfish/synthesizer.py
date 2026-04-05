"""
Prediction synthesizer for Wiggum loop simulations.

This module provides functionality to aggregate final round outputs, extract
consensus/dissent patterns, and compute confidence scores based on agreement
metrics among agents.

The synthesizer analyzes the final state of a simulation and produces a
structured report with:
- Consensus positions (high agreement)
- Dissent points (disagreements)
- Confidence scores for each extracted fact
- Agent alignment analysis
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
from datetime import datetime
import logging

from pydantic import BaseModel, Field, field_validator

from .models import (
    SimulationState,
    Message,
    Fact,
    AgentPersona,
    Dissent,
)

logger = logging.getLogger(__name__)


class SynthesizedFact(BaseModel):
    """A fact extracted and synthesized from final round outputs."""

    key: str
    value: Any
    supporting_agents: List[str] = Field(default_factory=list)
    opposing_agents: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    is_consensus: bool = False
    round_extracted: int

    def get_agreement_ratio(self) -> float:
        """Calculate the ratio of supporting agents to total agents involved."""
        total = len(self.supporting_agents) + len(self.opposing_agents)
        if total == 0:
            return 0.0
        return len(self.supporting_agents) / total


class AgentAlignment(BaseModel):
    """Alignment profile for an agent relative to the group consensus."""

    agent_id: str
    agent_name: str
    consensus_alignment_score: float = Field(..., ge=0.0, le=1.0)
    unique_contributions: List[str] = Field(default_factory=list)
    dissenting_positions: List[str] = Field(default_factory=list)


class SynthesisReport(BaseModel):
    """Complete synthesis report for a simulation run."""

    scenario_title: Optional[str]
    total_rounds: int
    total_agents: int
    synthesized_at: datetime = Field(default_factory=datetime.utcnow)

    # Key findings
    consensus_facts: List[SynthesizedFact] = Field(default_factory=list)
    dissent_points: List[SynthesizedFact] = Field(default_factory=list)
    unresolved_facts: List[SynthesizedFact] = Field(default_factory=list)

    # Agent alignments
    agent_alignments: Dict[str, AgentAlignment] = Field(default_factory=dict)

    # Summary statistics
    overall_consensus_strength: float = Field(0.0, ge=0.0, le=1.0)
    total_facts_extracted: int = 0
    consensus_fact_count: int = 0
    dissent_fact_count: int = 0

    # Raw data for further analysis
    raw_messages_analyzed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return self.model_dump()

    def get_summary(self) -> str:
        """Generate a human-readable summary of the synthesis."""
        lines = [
            "=== Synthesis Report ===",
            f"Scenario: {self.scenario_title or 'Untitled'}",
            f"Rounds: {self.total_rounds} | Agents: {self.total_agents}",
            f"Facts extracted: {self.total_facts_extracted}",
            f"Consensus facts: {self.consensus_fact_count}",
            f"Dissent points: {self.dissent_fact_count}",
            f"Overall consensus strength: {self.overall_consensus_strength:.2%}",
        ]
        return "\n".join(lines)


class PredictionSynthesizer:
    """
    Synthesizes predictions and positions from final simulation outputs.

    The synthesizer analyzes message history, particularly from the final round,
    to identify:
    - Areas of agreement (consensus)
    - Points of disagreement (dissent)
    - Confidence levels based on agent agreement ratios
    """

    def __init__(
        self,
        consensus_threshold: float = 0.7,
        strong_consensus_threshold: float = 0.9,
        min_agents_for_fact: int = 2,
    ):
        """
        Initialize the synthesizer with configuration thresholds.

        Args:
            consensus_threshold: Minimum agreement ratio to classify as consensus (0.0-1.0)
            strong_consensus_threshold: Agreement ratio for "strong consensus" classification
            min_agents_for_fact: Minimum number of agents that must mention a fact
        """
        self.consensus_threshold = consensus_threshold
        self.strong_consensus_threshold = strong_consensus_threshold
        self.min_agents_for_fact = min_agents_for_fact

    async def synthesize(self, state: SimulationState) -> SynthesisReport:
        """
        Perform full synthesis on a completed simulation state.

        Args:
            state: Final SimulationState after all rounds

        Returns:
            SynthesisReport with structured analysis results
        """
        logger = __import__("logging").getLogger(__name__)
        logger.info(
            "Starting synthesis",
            extra={
                "round": state.round,
                "agent_count": len(state.agents),
                "message_count": len(state.message_history),
            },
        )

        # Get messages from final round
        final_round = state.round
        final_messages = state.get_round_messages(final_round)

        # Also consider all rounds for overall analysis
        all_messages = state.message_history

        # Extract facts from all agent outputs
        extracted_facts = self._extract_facts_from_messages(
            messages=final_messages,
            agents=state.agents,
            round_number=final_round,
        )

        # Group facts by key and compute agreement
        fact_groups = self._group_facts_by_key(extracted_facts)

        # Calculate synthesized facts with confidence scores
        synthesized_facts = self._compute_fact_synthesis(fact_groups)

        # Update SimulationState with extracted facts (mutating state)
        for fact in synthesized_facts:
            state.add_fact(
                Fact(
                    key=fact.key,
                    value=fact.value,
                    source_agent_id=None,
                    round_extracted=fact.round_extracted,
                    confidence=fact.confidence,
                    evidence=fact.evidence,
                )
            )

        # Classify consensus vs dissent
        consensus_facts = []
        dissent_points = []
        unresolved_facts = []

        for fact in synthesized_facts:
            if fact.supporting_agents and fact.opposing_agents:
                # Both supporting and opposing - this is dissent
                dissent_points.append(fact)
            elif len(fact.supporting_agents) >= self.min_agents_for_fact:
                # At least min agents support it
                if fact.get_agreement_ratio() >= self.consensus_threshold:
                    consensus_facts.append(fact)
                else:
                    # Some agreement but below threshold - unresolved
                    unresolved_facts.append(fact)
            else:
                # Too few agents mention this fact
                unresolved_facts.append(fact)

        # Compute agent alignment scores
        agent_alignments = self._compute_agent_alignments(
            consensus_facts, dissent_points, state.agents
        )

        # Calculate overall consensus strength
        total_facts = len(synthesized_facts)
        consensus_count = len(consensus_facts)
        overall_consensus_strength = (
            consensus_count / total_facts if total_facts > 0 else 0.0
        )

        # Create the report
        report = SynthesisReport(
            scenario_title=state.scenario.title,
            total_rounds=state.round,
            total_agents=len(state.agents),
            consensus_facts=consensus_facts,
            dissent_points=dissent_points,
            unresolved_facts=unresolved_facts,
            agent_alignments=agent_alignments,
            overall_consensus_strength=overall_consensus_strength,
            total_facts_extracted=total_facts,
            consensus_fact_count=consensus_count,
            dissent_fact_count=len(dissent_points),
            raw_messages_analyzed=len(all_messages),
        )

        logger.info(
            "Synthesis complete",
            extra={
                "consensus_count": consensus_count,
                "dissent_count": len(dissent_points),
                "consensus_strength": overall_consensus_strength,
            },
        )

        return report

    def _extract_facts_from_messages(
        self,
        messages: List[Message],
        agents: List[AgentPersona],
        round_number: int,
    ) -> List[SynthesizedFact]:
        """
        Extract facts from agent messages using simple pattern matching.

        This is a basic implementation; in production, this would use an LLM
        to extract structured facts and values from unstructured text.

        Args:
            messages: List of messages to analyze
            agents: List of all agents in the simulation
            round_number: The round from which these facts are extracted

        Returns:
            List of raw extracted facts (before grouping/consensus analysis)
        """
        facts = []

        # Build agent lookup
        agent_map = {agent.id: agent for agent in agents}

        for msg in messages:
            agent = agent_map.get(msg.agent_id)
            if not agent:
                continue

            # Simple extraction: treat each sentence as a potential fact
            # In a real implementation, this would be more sophisticated
            sentences = self._split_into_sentences(msg.content)

            for sentence in sentences:
                # Generate a simple key from the sentence (first few words)
                key = self._generate_fact_key(sentence)

                fact = SynthesizedFact(
                    key=key,
                    value=sentence.strip(),
                    supporting_agents=[msg.agent_id],
                    opposing_agents=[],
                    confidence=1.0,  # Will be adjusted during grouping
                    evidence=[
                        f"[Round {msg.round}] {msg.agent_name}: {sentence.strip()}"
                    ],
                    round_extracted=round_number,
                )
                facts.append(fact)

        return facts

    def _split_into_sentences(self, text: str) -> List[str]:
        """Simple sentence splitting."""
        # Split on sentence endings
        import re

        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _generate_fact_key(self, text: str) -> str:
        """Generate a simple deterministic key from text."""
        # Take first 3-5 words, lowercase, alphanumeric only
        words = text.lower().split()[:4]
        key = "-".join(words)
        # Remove non-alphanumeric
        import re

        key = re.sub(r"[^a-z0-9-]", "", key)
        return key[:50]  # Limit length

    def _group_facts_by_key(
        self, facts: List[SynthesizedFact]
    ) -> Dict[str, List[SynthesizedFact]]:
        """Group facts by their keys for agreement analysis."""
        groups: Dict[str, List[SynthesizedFact]] = {}
        for fact in facts:
            groups.setdefault(fact.key, []).append(fact)
        return groups

    def _compute_fact_synthesis(
        self, fact_groups: Dict[str, List[SynthesizedFact]]
    ) -> List[SynthesizedFact]:
        """
        Combine fact groups into synthesized facts with confidence scores.

        For each group:
        - Combine all supporting agents
        - Identify opposing agents (if any)
        - Compute confidence based on ratio
        - Merge evidence
        """
        synthesized = []

        for key, group in fact_groups.items():
            # Combine all agents who contributed this fact (any sentence with this key)
            all_supporting = set()
            all_evidence = []
            value = None

            for fact in group:
                all_supporting.add(
                    fact.supporting_agents[0]
                )  # Each fact from single agent
                all_evidence.extend(fact.evidence)
                if value is None:
                    # Use the first non-empty value as representative
                    if fact.value and len(fact.value) > 0:
                        value = fact.value

            # Check for opposing agents (agents who said something contradicting)
            # In this simple version, we'll assume opposition if we see similar key
            # with opposite sentiment (not implemented). For now, we'll determine
            # dissent based on whether all agents are in agreement or not.
            opposing = set()

            synthesized_fact = SynthesizedFact(
                key=key,
                value=value or list(all_supporting),  # Fallback to agent list
                supporting_agents=list(all_supporting),
                opposing_agents=list(opposing),
                confidence=len(all_supporting) / len(fact_groups.get(key, [])),
                evidence=list(set(all_evidence)),
                is_consensus=False,  # Set later
                round_extracted=group[0].round_extracted if group else 0,
            )
            synthesized.append(synthesized_fact)

        return synthesized

    def _compute_agent_alignments(
        self,
        consensus_facts: List[SynthesizedFact],
        dissent_points: List[SynthesizedFact],
        all_agents: List[AgentPersona],
    ) -> Dict[str, AgentAlignment]:
        """
        Compute alignment scores for each agent relative to consensus positions.

        Args:
            consensus_facts: List of consensus facts
            dissent_points: List of dissenting facts
            all_agents: All agents in the simulation

        Returns:
            Dictionary mapping agent_id to AgentAlignment
        """
        alignments = {}
        agent_set = {agent.id: agent for agent in all_agents}

        for agent_id, agent in agent_set.items():
            # Count how many consensus facts this agent supported
            consensus_supported = 0
            unique_contribs = []
            dissenting_positions = []

            for fact in consensus_facts:
                if agent_id in fact.supporting_agents:
                    consensus_supported += 1
                # Check if this agent uniquely contributed (only agent supporting)
                if (
                    len(fact.supporting_agents) == 1
                    and agent_id in fact.supporting_agents
                ):
                    unique_contribs.append(fact.key)

            for fact in dissent_points:
                if agent_id in fact.supporting_agents:
                    dissenting_positions.append(fact.key)

            # Calculate alignment score as proportion of consensus facts supported
            total_consensus = len(consensus_facts)
            alignment_score = (
                consensus_supported / total_consensus if total_consensus > 0 else 0.5
            )

            alignment = AgentAlignment(
                agent_id=agent_id,
                agent_name=agent.name,
                consensus_alignment_score=alignment_score,
                unique_contributions=unique_contribs,
                dissenting_positions=dissenting_positions,
            )
            alignments[agent_id] = alignment

        return alignments
