"""Command-line interface for Ralphfish simulation engine."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

from .client import OpenRouterClient, DEFAULT_MODEL
from .models import InteractionProtocol, SimulationState
from .parser import parse_seed
from .executor import run_simulation
from .persona_generator import (
    PersonaGenerator,
    PersonaGeneratorConfig,
    PersonaConstraints,
    Archetype,
)
from .synthesizer import PredictionSynthesizer, SynthesisReport
from .report_generator import ReportGenerator
from .agent import Agent, AgentConfig


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ralphfish - LLM Multi-Agent Simulation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run-simulation command
    sim_parser = subparsers.add_parser(
        "run-simulation", help="Run a multi-agent simulation"
    )
    sim_parser.add_argument(
        "-s", "--scenario", type=Path, required=True, help="Path to scenario text file"
    )
    sim_parser.add_argument(
        "-a",
        "--agents",
        type=int,
        default=3,
        help="Number of agents to create (default: 3)",
    )
    sim_parser.add_argument(
        "-r",
        "--rounds",
        type=int,
        default=3,
        help="Number of rounds to simulate (default: 3)",
    )
    sim_parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"OpenRouter model to use (default: {DEFAULT_MODEL})",
    )
    sim_parser.add_argument(
        "-p",
        "--protocol",
        type=str,
        choices=[p.value for p in InteractionProtocol],
        default=InteractionProtocol.DISCUSSION.value,
        help="Interaction protocol (default: discussion)",
    )
    sim_parser.add_argument(
        "-c",
        "--max-concurrent",
        type=int,
        default=1,
        help="Maximum concurrent LLM calls (default: 1)",
    )
    sim_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("./output"),
        help="Output directory for results (default: ./output)",
    )
    sim_parser.add_argument(
        "--title", type=str, help="Scenario title (default: derived from filename)"
    )
    sim_parser.add_argument(
        "--context", type=str, help="Additional context for the scenario"
    )

    # generate-personas command
    persona_parser = subparsers.add_parser(
        "generate-personas", help="Generate agent personas"
    )
    persona_parser.add_argument(
        "-n", "--count", type=int, required=True, help="Number of personas to generate"
    )
    persona_parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output JSON file path"
    )
    persona_parser.add_argument(
        "-a",
        "--archetype",
        type=str,
        choices=[a.value for a in Archetype],
        help="Restrict to specific archetype",
    )
    persona_parser.add_argument(
        "--min-age", type=int, default=18, help="Minimum age (default: 18)"
    )
    persona_parser.add_argument(
        "--max-age", type=int, default=80, help="Maximum age (default: 80)"
    )
    persona_parser.add_argument(
        "--seed", type=int, help="Random seed for reproducibility"
    )

    # export-report command
    report_parser = subparsers.add_parser(
        "export-report", help="Export simulation report"
    )
    report_parser.add_argument(
        "-s", "--state", type=Path, required=True, help="Simulation state JSON file"
    )
    report_parser.add_argument(
        "-r",
        "--report",
        type=Path,
        help="Pre-synthesized report JSON file (optional, will synthesize if not provided)",
    )
    report_parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("./reports"),
        help="Output directory for reports (default: ./reports)",
    )
    report_parser.add_argument(
        "-f",
        "--formats",
        type=str,
        nargs="+",
        choices=["markdown", "json", "yaml"],
        default=["markdown"],
        help="Output format(s) (default: markdown)",
    )
    report_parser.add_argument(
        "--summary-only", action="store_true", help="Generate summary report only"
    )
    report_parser.add_argument(
        "--prefix", type=str, help="Filename prefix for exported reports"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "run-simulation":
            asyncio.run(run_simulation_command(args))
        elif args.command == "generate-personas":
            asyncio.run(generate_personas_command(args))
        elif args.command == "export-report":
            asyncio.run(export_report_command(args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def run_simulation_command(args: argparse.Namespace) -> None:
    """Execute the run-simulation command."""
    # Read scenario file
    scenario_text = args.scenario.read_text(encoding="utf-8")

    # Parse scenario
    scenario = await parse_seed(
        scenario_text, title=args.title or args.scenario.stem, context=args.context
    )

    # Generate personas
    constraints = PersonaConstraints(
        min_age=18,
        max_age=80,
    )
    generator = PersonaGenerator(PersonaGeneratorConfig())
    personas = []
    for _ in range(args.agents):
        persona = generator.generate(constraints=constraints)
        personas.append(persona)

    # Create agents with shared client
    client = OpenRouterClient()
    agents = []
    for persona in personas:
        agent = Agent(
            persona=persona, client=client, config=AgentConfig(model=args.model)
        )
        agents.append(agent)

    # Set up protocol
    protocol = InteractionProtocol(args.protocol.upper())

    # Run simulation
    print(
        f"Starting simulation: {len(agents)} agents, {args.rounds} rounds, protocol={protocol.value}"
    )
    final_state = await run_simulation(
        agents=agents,
        scenario=scenario,
        rounds=args.rounds,
        protocol=protocol,
        max_concurrent=args.max_concurrent,
    )

    # Ensure output directory exists
    args.output.mkdir(parents=True, exist_ok=True)

    # Save simulation state
    state_file = args.output / "simulation_state.json"
    state_data = final_state.model_dump()
    state_file.write_text(json.dumps(state_data, indent=2, default=str))
    print(f"Saved simulation state to {state_file}")

    # Synthesize report
    synthesizer = PredictionSynthesizer()
    report = await synthesizer.synthesize(final_state)

    report_file = args.output / "synthesis_report.json"
    report_data = report.model_dump()
    report_file.write_text(json.dumps(report_data, indent=2, default=str))
    print(f"Saved synthesis report to {report_file}")

    # Export human-readable reports
    report_gen = ReportGenerator()
    exported = report_gen.export(
        state=final_state,
        report=report,
        output_dir=args.output,
        formats=args.formats,
        summary_only=False,
        filename_prefix=args.title or args.scenario.stem,
    )
    for fmt, path in exported.items():
        print(f"Exported {fmt} report to {path}")

    print("Simulation completed successfully!")


async def generate_personas_command(args: argparse.Namespace) -> None:
    """Execute the generate-personas command."""
    archetype_value = args.archetype
    constraints = PersonaConstraints(
        min_age=args.min_age,
        max_age=args.max_age,
        archetypes=[Archetype(archetype_value)] if archetype_value else None,
    )

    generator = PersonaGenerator(PersonaGeneratorConfig())
    personas = []

    if args.seed is not None:
        import random

        random.seed(args.seed)

    for _ in range(args.count):
        persona = generator.generate(constraints=constraints)
        personas.append(persona)

    # Convert to dict for JSON serialization
    personas_data = [p.model_dump() for p in personas]

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(json.dumps(personas_data, indent=2))
    print(f"Generated {len(personas)} personas and saved to {args.output}")


async def export_report_command(args: argparse.Namespace) -> None:
    """Execute the export-report command."""
    # Load simulation state
    state_data = json.loads(args.state.read_text(encoding="utf-8"))
    state = SimulationState(**state_data)

    # Load or synthesize report
    if args.report:
        report_data = json.loads(args.report.read_text(encoding="utf-8"))
        report = SynthesisReport(**report_data)
    else:
        synthesizer = PredictionSynthesizer()
        report = await synthesizer.synthesize(state)

    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Generate reports
    report_gen = ReportGenerator()

    formats = args.formats if args.formats else ["markdown"]

    exported = report_gen.export(
        state=state,
        report=report,
        output_dir=args.output_dir,
        formats=formats,
        summary_only=args.summary_only,
        filename_prefix=args.prefix or state.scenario.title or "report",
    )

    for fmt, path in exported.items():
        print(f"Exported {fmt} report to {path}")


if __name__ == "__main__":
    main()
