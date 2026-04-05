#!/usr/bin/env python3
"""
Example: Using the Seed Parser to extract structured data from text.

This demonstrates how to parse a scenario description and get structured
entities, relationships, conflicts, and facts using the LLM.
"""

import asyncio
import os
import json
from ralphfish import SeedParser, OpenRouterClient


async def main():
    # Example scenario text
    scenario_text = """
    A tech startup, InnovateCo, is developing a new AI product. The project manager,
    Sarah, believes they should prioritize features to meet the quarterly deadline.
    The lead engineer, Mike, argues they need more time for testing to ensure quality.
    The CEO, David, wants both speed and quality but has limited budget.
    
    InnovateCo has 15 employees and a 6-month deadline. Their main competitor,
    TechGiant, is rumored to be working on a similar product.
    """

    # Initialize parser with OpenRouter client
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Please set OPENROUTER_API_KEY environment variable")
        print("Get your key from: https://openrouter.ai/keys")
        return

    client = OpenRouterClient()
    parser = SeedParser(client=client)

    try:
        # Parse the scenario
        print("Parsing scenario...")
        scenario = await parser.parse(
            seed_text=scenario_text.strip(), title="Startup Product Dilemma"
        )

        # Display results
        print("\n" + "=" * 60)
        print(f"Scenario: {scenario.title}")
        print("=" * 60)

        print("\nExtracted Entities:")
        for entity in scenario.extracted_entities:
            print(f"  - {entity['name']} ({entity['type']}): {entity['description']}")

        print(f"\nRelationships ({len(scenario.extracted_relationships)}):")
        for rel in scenario.extracted_relationships:
            print(f"  - {rel['subject']} {rel['predicate']} {rel['object']}")

        print(f"\nInitial Facts ({len(scenario.initial_facts)}):")
        for fact in scenario.initial_facts:
            print(f"  - {fact.value} (confidence: {fact.confidence})")

        # Save to JSON file
        output_file = "scenario_output.json"
        with open(output_file, "w") as f:
            json.dump(scenario.to_dict(), f, indent=2, default=str)
        print(f"\nFull scenario saved to: {output_file}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
