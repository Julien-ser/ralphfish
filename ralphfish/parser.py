"""
Seed document parser using LLM extraction.

Parses user input text to identify:
- Key entities (people, organizations, locations, concepts)
- Relationships between entities
- Conflicts or problems
- Initial conditions and assumptions

Uses OpenRouter LLM to perform structured extraction.
"""

import json
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .client import OpenRouterClient, simple_chat
from .models import Scenario, Fact, AgentPersona

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT_TEMPLATE = """
You are an expert analyst extracting structured information from text.

## Task
Analyze the following scenario text and extract key information in JSON format.

## Scenario Text
{scenario_text}

## Instructions
Extract and return a JSON object with these keys:
- "entities": list of key entities (name, type, description)
- "relationships": list of relationships between entities {subject: "A", predicate: "works_for", object: "B"}
- "conflicts": list of conflicts or problems identified
- "initial_facts": list of factual statements from the text
- "assumptions": list of implicit assumptions that can be made

For each entity, include:
- name (string): the entity name
- type (string): person, organization, location, concept, etc.
- description (string): brief description

For relationships, use the format:
- subject (string): source entity name
- predicate (string): relationship verb
- object (string): target entity name

For conflicts, include:
- type (string): disagreement, resource_scarcity, goal_conflict, etc.
- parties (list): entities involved
- description (string): what the conflict is about

For initial_facts and assumptions, provide concise statements.

## Response Format
Return ONLY valid JSON. Do not include markdown or explanations.

Example:
{{
  "entities": [
    {{"name": "Alice", "type": "person", "description": "Project manager"}},
    {{"name": "TechCorp", "type": "organization", "description": "Technology company"}}
  ],
  "relationships": [
    {{"subject": "Alice", "predicate": "works_for", "object": "TechCorp"}}
  ],
  "conflicts": [
    {{"type": "goal_conflict", "parties": ["Alice", "Bob"], "description": "Budget vs quality disagreement"}}
  ],
  "initial_facts": ["TechCorp has 100 employees", "Project deadline is December"],
  "assumptions": ["Alice has budget authority", "Bob is the technical lead"]
}}
"""


class SeedParser:
    """Parser for extracting structured data from seed documents."""

    def __init__(
        self,
        client: Optional[OpenRouterClient] = None,
        prompt_template: str = EXTRACTION_PROMPT_TEMPLATE,
        model: Optional[str] = None,
    ):
        self.client = client
        self.prompt_template = prompt_template
        self.model = model

    async def parse(
        self, seed_text: str, title: Optional[str] = None, context: Optional[str] = None
    ) -> Scenario:
        """
        Parse seed text and return a Scenario object.

        Args:
            seed_text: The input text to analyze
            title: Optional title for the scenario
            context: Additional context to include

        Returns:
            Scenario object with extracted entities and facts

        Raises:
            ValueError: If extraction fails or returns invalid JSON
        """
        # Combine text and context
        full_text = seed_text
        if context:
            full_text = f"{context}\n\n{seed_text}"

        # Build the prompt
        prompt = self.prompt_template.format(scenario_text=full_text)

        # Call LLM
        if self.client:
            response = await self.client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise data extraction assistant that outputs only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.3,  # Lower temperature for consistent extraction
                max_tokens=2000,
            )
            content = response["content"]
        else:
            # Fallback to simple_chat (for testing/demo)
            content = await simple_chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise data extraction assistant that outputs only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )

        # Parse JSON response
        try:
            # Clean response: remove markdown code blocks if present
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            extracted = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse LLM response as JSON", extra={"response": content}
            )
            raise ValueError(f"Invalid JSON from LLM: {e}") from e

        # Validate structure
        required_keys = [
            "entities",
            "relationships",
            "conflicts",
            "initial_facts",
            "assumptions",
        ]
        for key in required_keys:
            if key not in extracted:
                logger.warning("Missing extraction key", extra={"key": key})
                extracted[key] = []  # Default to empty list

        # Build Scenario object
        initial_facts = [
            Fact(
                key=self._fact_key_from_statement(fact),
                value=fact,
                source_agent_id="seed_parser",
                round_extracted=0,
                confidence=1.0,  # Seed facts start with high confidence
                evidence=[fact],
            )
            for fact in extracted["initial_facts"]
        ]

        scenario = Scenario(
            seed_text=seed_text,
            title=title or self._extract_title(seed_text),
            context=context,
            extracted_entities=extracted["entities"],
            extracted_relationships=extracted["relationships"],
            initial_facts=initial_facts,
        )

        logger.info(
            "Seed parsing complete",
            extra={
                "entities": len(extracted["entities"]),
                "relationships": len(extracted["relationships"]),
                "conflicts": len(extracted["conflicts"]),
                "facts": len(initial_facts),
            },
        )

        return scenario

    def _fact_key_from_statement(self, statement: str) -> str:
        """Generate a deterministic key for a fact statement."""
        # Simple: lowercase, remove punctuation, take first few words
        import re

        cleaned = re.sub(r"[^\w\s]", "", statement.lower())
        words = cleaned.split()[:5]
        return "_".join(words) if words else "unnamed_fact"

    def _extract_title(self, text: str, max_words: int = 10) -> str:
        """Extract a title from the first sentence or first few words."""
        first_sentence = text.split(".")[0].strip()
        words = first_sentence.split()[:max_words]
        return " ".join(words) if words else "Untitled Scenario"

    async def parse_batch(self, texts: List[str], **kwargs) -> List[Scenario]:
        """
        Parse multiple seed texts concurrently.

        Args:
            texts: List of seed texts to parse
            **kwargs: Additional arguments to pass to parse()

        Returns:
            List of Scenario objects
        """
        if not self.client:
            raise ValueError("Batch parsing requires an OpenRouterClient")

        tasks = [self.parse(text, **kwargs) for text in texts]
        return await asyncio.gather(*tasks, return_exceptions=True)


# Convenience function for one-off parsing
async def parse_seed(
    seed_text: str, api_key: Optional[str] = None, model: Optional[str] = None, **kwargs
) -> Scenario:
    """
    Quick parse without needing to instantiate a parser.

    Args:
        seed_text: Text to parse
        api_key: OpenRouter API key
        model: Model to use for extraction
        **kwargs: Additional arguments

    Returns:
        Scenario object
    """
    # Import here to avoid circular dependency
    from .client import OpenRouterClient, ClientConfig

    config = ClientConfig(api_key=api_key)
    client = OpenRouterClient(config)
    try:
        parser = SeedParser(client=client, model=model)
        return await parser.parse(seed_text, **kwargs)
    finally:
        await client.close()


# Export
__all__ = [
    "SeedParser",
    "parse_seed",
    "EXTRACTION_PROMPT_TEMPLATE",
]
