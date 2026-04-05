"""
Configurable persona generator for creating AgentPersona instances with constraints.

Provides random persona generation within user-defined boundaries including
archetypes, demographics, bias patterns, and personality traits.
"""

import random
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .models import AgentPersona


class Archetype(str, Enum):
    """Common agent archetypes for persona generation."""

    SCIENTIST = "scientist"
    POLITICIAN = "politician"
    JOURNALIST = "journalist"
    ACTIVIST = "activist"
    BUSINESS_LEADER = "business_leader"
    ACADEMIC = "academic"
    ARTIST = "artist"
    ENGINEER = "engineer"
    DOCTOR = "doctor"
    TEACHER = "teacher"
    LAWYER = "lawyer"
    FARMER = "farmer"
    STUDENT = "student"
    RETIREE = "retiree"
    CIVIL_SERVANT = "civil_servant"


class Gender(str, Enum):
    """Gender options for personas."""

    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class CommunicationStyle(str, Enum):
    """Communication style options."""

    FORMAL = "formal"
    CASUAL = "casual"
    AGGRESSIVE = "aggressive"
    DIPLOMATIC = "diplomatic"
    TECHNICAL = "technical"
    EMOTIONAL = "emotional"
    HUMOROUS = "humorous"
    PEDANTIC = "pedantic"


@dataclass
class PersonaConstraints:
    """
    Constraints for random persona generation.

    All fields are optional; when None, defaults or full ranges are used.
    """

    archetypes: Optional[List[Archetype]] = None
    min_age: int = 18
    max_age: int = 80
    genders: Optional[List[Gender]] = None
    nationalities: Optional[List[str]] = None
    bias_patterns: Optional[List[str]] = None
    traits: Optional[List[str]] = None
    communication_styles: Optional[List[str]] = None
    background_categories: Optional[List[str]] = None

    def validate(self) -> None:
        """Validate constraints are sensible."""
        if self.min_age < 0 or self.max_age < self.min_age:
            raise ValueError("Invalid age range")


@dataclass
class PersonaGeneratorConfig:
    """
    Configuration for the persona generator.

    Contains pools of values to randomly select from when generating personas.
    """

    first_names: List[str] = field(default_factory=list)
    last_names: List[str] = field(default_factory=list)
    archetype_backgrounds: Dict[str, List[str]] = field(default_factory=dict)
    archetype_traits: Dict[str, List[str]] = field(default_factory=dict)
    archetype_goals: Dict[str, List[str]] = field(default_factory=dict)
    bias_patterns: List[str] = field(default_factory=list)
    communication_styles: List[str] = field(default_factory=list)
    nationalities: List[str] = field(default_factory=list)

    @classmethod
    def get_default(cls) -> "PersonaGeneratorConfig":
        """Get a default configuration with common values."""
        return cls(
            first_names=[
                "James",
                "Mary",
                "John",
                "Patricia",
                "Robert",
                "Jennifer",
                "Michael",
                "Linda",
                "William",
                "Elizabeth",
                "David",
                "Barbara",
                "Richard",
                "Susan",
                "Joseph",
                "Jessica",
                "Thomas",
                "Sarah",
                "Charles",
                "Karen",
                "Emma",
                "Daniel",
                "Lisa",
                "Matthew",
                "Sofia",
                "Alexander",
                "Maria",
                "Olivia",
                "Ethan",
                "Isabella",
            ],
            last_names=[
                "Smith",
                "Johnson",
                "Williams",
                "Brown",
                "Jones",
                "Garcia",
                "Miller",
                "Davis",
                "Rodriguez",
                "Martinez",
                "Hernandez",
                "Lopez",
                "Gonzalez",
                "Wilson",
                "Anderson",
                "Thomas",
                "Taylor",
                "Moore",
                "Jackson",
                "Martin",
                "Lee",
                "Perez",
                "Thompson",
                "White",
                "Harris",
                "Clark",
                "Hall",
                "Lewis",
                "Young",
                "King",
            ],
            archetype_backgrounds={
                "scientist": [
                    "research scientist in artificial intelligence",
                    "biologist specializing in genetics",
                    "physicist working on quantum computing",
                    "environmental scientist studying climate change",
                    "neuroscience researcher",
                ],
                "politician": [
                    "city council member",
                    "state legislator",
                    "congressional representative",
                    "senator",
                    "policy advisor",
                    "campaign manager",
                ],
                "journalist": [
                    "investigative reporter",
                    "foreign correspondent",
                    "science writer",
                    "opinion columnist",
                    "digital media journalist",
                ],
                "activist": [
                    "environmental activist",
                    "human rights advocate",
                    "economic justice organizer",
                    "animal rights campaigner",
                    "digital privacy advocate",
                ],
                "business_leader": [
                    "tech startup CEO",
                    "venture capitalist",
                    "corporate strategy executive",
                    "small business owner",
                    "management consultant",
                ],
                "academic": [
                    "university professor of philosophy",
                    "history scholar",
                    "literature critic",
                    "economics researcher",
                    "sociology lecturer",
                ],
                "artist": [
                    "conceptual artist",
                    "novelist",
                    "filmmaker",
                    "theater director",
                    "musician and composer",
                ],
                "engineer": [
                    "software architect",
                    "civil engineer",
                    "aerospace engineer",
                    "electrical systems engineer",
                    "biomedical engineer",
                ],
                "doctor": [
                    "emergency room physician",
                    "family practice doctor",
                    "surgeon",
                    "psychiatrist",
                    "public health specialist",
                ],
                "teacher": [
                    "high school science teacher",
                    "elementary school educator",
                    "university lecturer",
                    "special education teacher",
                    "curriculum developer",
                ],
                "lawyer": [
                    "criminal defense attorney",
                    "corporate lawyer",
                    "public interest lawyer",
                    "judge",
                    "legal aid advocate",
                ],
                "farmer": [
                    "organic vegetable farmer",
                    "cattle rancher",
                    "sustainable agriculture advocate",
                    "agricultural economist",
                    "forestry manager",
                ],
                "student": [
                    "undergraduate in computer science",
                    "graduate student in biology",
                    "PhD candidate in political science",
                    "MBA student",
                    "medical student",
                ],
                "retiree": [
                    "former teacher",
                    "retired engineer",
                    "ex-business owner",
                    "former civil servant",
                    "retired healthcare worker",
                ],
                "civil_servant": [
                    "government agency director",
                    "policy analyst",
                    "regulatory specialist",
                    "public administrator",
                    "diplomatic service officer",
                ],
            },
            archetype_traits={
                "scientist": [
                    "analytical",
                    "curious",
                    "methodical",
                    "skeptical",
                    "precise",
                ],
                "politician": [
                    "charismatic",
                    "persuasive",
                    "pragmatic",
                    "opportunistic",
                    "strategic",
                ],
                "journalist": [
                    "inquisitive",
                    "observant",
                    "persistent",
                    "ethical",
                    "adaptable",
                ],
                "activist": [
                    "passionate",
                    "determined",
                    "principled",
                    "charismatic",
                    "resilient",
                ],
                "business_leader": [
                    "ambitious",
                    "decisive",
                    "competitive",
                    "innovative",
                    "results-oriented",
                ],
                "academic": [
                    "intellectual",
                    "detail-oriented",
                    "theoretical",
                    "critical",
                    "specialized",
                ],
                "artist": [
                    "creative",
                    "expressive",
                    "intuitive",
                    "individualistic",
                    "sensitive",
                ],
                "engineer": [
                    "logical",
                    "practical",
                    "problem-solving",
                    "detail-oriented",
                    "systematic",
                ],
                "doctor": [
                    "compassionate",
                    "decisive",
                    "calm under pressure",
                    "ethical",
                    "knowledgeable",
                ],
                "teacher": [
                    "patient",
                    "encouraging",
                    "organized",
                    "adaptable",
                    "nurturing",
                ],
                "lawyer": [
                    "argumentative",
                    "detail-oriented",
                    "persuasive",
                    "ethical",
                    "strategic",
                ],
                "farmer": [
                    "practical",
                    "patient",
                    "resilient",
                    "knowledgeable",
                    "independent",
                ],
                "student": [
                    "curious",
                    "malleable",
                    "ambitious",
                    "idealistic",
                    "energetic",
                ],
                "retiree": [
                    "experienced",
                    "reflective",
                    "traditional",
                    "wise",
                    "cautious",
                ],
                "civil_servant": [
                    "methodical",
                    "impartial",
                    "procedural",
                    "detail-oriented",
                    "service-oriented",
                ],
            },
            archetype_goals={
                "scientist": [
                    "advance scientific knowledge",
                    "publish groundbreaking research",
                    "secure funding for experiments",
                    "translate research into practical applications",
                ],
                "politician": [
                    "get re-elected",
                    "pass meaningful legislation",
                    "build a loyal constituency",
                    "achieve higher office",
                ],
                "journalist": [
                    "uncover the truth",
                    "inform the public",
                    "win prestigious awards",
                    "protect press freedom",
                ],
                "activist": [
                    "create social change",
                    "raise awareness",
                    "mobilize supporters",
                    "influence policy",
                ],
                "business_leader": [
                    "increase company value",
                    "expand market share",
                    "drive innovation",
                    "maximize shareholder returns",
                ],
                "academic": [
                    "publish influential papers",
                    "secure tenure",
                    "advance the field",
                    "mentor students",
                ],
                "artist": [
                    "create meaningful art",
                    "express a unique vision",
                    "gain recognition",
                    "connect with audiences",
                ],
                "engineer": [
                    "build reliable systems",
                    "solve complex problems",
                    "optimize performance",
                    "ensure safety and quality",
                ],
                "doctor": [
                    "heal patients",
                    "advance medical knowledge",
                    "improve healthcare outcomes",
                    "maintain ethical standards",
                ],
                "teacher": [
                    "educate and inspire",
                    "prepare students for success",
                    "create engaging lessons",
                    "foster critical thinking",
                ],
                "lawyer": [
                    "win cases",
                    "protect client interests",
                    "uphold justice",
                    "navigate complex regulations",
                ],
                "farmer": [
                    "produce quality crops",
                    "sustain the land",
                    "maintain profitability",
                    "adapt to climate conditions",
                ],
                "student": [
                    "gain knowledge",
                    "earn good grades",
                    "prepare for career",
                    "explore interests",
                ],
                "retiree": [
                    "enjoy retirement",
                    "share wisdom",
                    "stay active and healthy",
                    "spend time with family",
                ],
                "civil_servant": [
                    "serve the public interest",
                    "ensure fair governance",
                    "implement effective policies",
                    "maintain institutional integrity",
                ],
            },
            bias_patterns=[
                "confirmation bias",
                "status quo bias",
                "bandwagon effect",
                "anchoring bias",
                "sunk cost fallacy",
                "availability heuristic",
                "optimism bias",
                "negativity bias",
                "self-serving bias",
                "groupthink",
            ],
            communication_styles=[
                "formal",
                "casual",
                "aggressive",
                "diplomatic",
                "technical",
                "emotional",
                "humorous",
                "pedantic",
                "balanced",
                "assertive",
            ],
            nationalities=[
                "American",
                "British",
                "Canadian",
                "Australian",
                "Indian",
                "Chinese",
                "Japanese",
                "Korean",
                "German",
                "French",
                "Italian",
                "Spanish",
                "Brazilian",
                "Mexican",
                "Russian",
                "South African",
                "Nigerian",
                "Egyptian",
                "Indonesian",
                "Global",
            ],
        )


class PersonaGenerator:
    """
    Generates random AgentPersona instances within specified constraints.

    Usage:
        config = PersonaGeneratorConfig.get_default()
        constraints = PersonaConstraints(archetypes=[Archetype.SCIENTIST])
        persona = PersonaGenerator(config).generate(constraints=constraints)
        personas = PersonaGenerator(config).generate_batch(5, constraints)
    """

    def __init__(self, config: PersonaGeneratorConfig):
        """
        Initialize generator with configuration.

        Args:
            config: Configuration object with value pools
        """
        self.config = config

    def generate(
        self,
        constraints: Optional[PersonaConstraints] = None,
        archetype: Optional[Union[Archetype, str]] = None,
        seed: Optional[int] = None,
    ) -> AgentPersona:
        """
        Generate a single random persona.

        Args:
            constraints: Optional constraints to limit generation
            archetype: Quick way to specify an archetype (overrides constraints.archetypes)
            seed: Optional random seed for reproducibility

        Returns:
            Generated AgentPersona instance
        """
        if seed is not None:
            random.seed(seed)

        constraints = constraints or PersonaConstraints()
        constraints.validate()

        # Determine archetype
        if archetype:
            selected_archetype = (
                Archetype(archetype) if isinstance(archetype, str) else archetype
            )
        elif constraints.archetypes:
            selected_archetype = random.choice(constraints.archetypes)
        else:
            selected_archetype = random.choice(list(Archetype))

        archetype_str = selected_archetype.value

        # Select values from pools
        name = self._generate_name(constraints)
        age = random.randint(constraints.min_age, constraints.max_age)
        gender = self._select_gender(constraints)
        nationality = self._select_nationality(constraints)

        # Get archetype-specific values
        backgrounds = self.config.archetype_backgrounds.get(archetype_str, [])
        background = (
            random.choice(backgrounds)
            if backgrounds
            else f"background related to {archetype_str}"
        )

        traits = self._select_traits(constraints, archetype_str)
        goals = self._select_goals(constraints, archetype_str)
        biases = self._select_biases(constraints)
        communication_style = self._select_communication_style(constraints)

        # Generate unique ID
        persona_id = f"{archetype_str}_{random.randint(1000, 9999)}"

        return AgentPersona(
            id=persona_id,
            name=name,
            background=f"{age}-year-old {nationality} {background}",
            traits=traits,
            goals=goals,
            biases=biases,
            communication_style=communication_style,
        )

    def generate_batch(
        self,
        count: int,
        constraints: Optional[PersonaConstraints] = None,
        archetype: Optional[Union[Archetype, str]] = None,
        unique: bool = True,
        seed: Optional[int] = None,
    ) -> List[AgentPersona]:
        """
        Generate multiple random personas.

        Args:
            count: Number of personas to generate
            constraints: Optional constraints to limit generation
            archetype: Optional archetype filter
            unique: If True, ensure generated personas are unique by ID
            seed: Optional random seed for reproducibility

        Returns:
            List of generated AgentPersona instances
        """
        if seed is not None:
            random.seed(seed)

        personas = []
        generated_ids = set()

        for _ in range(count):
            persona = self.generate(constraints, archetype)

            if unique:
                # Regenerate if duplicate ID (unlikely but possible)
                attempts = 0
                while persona.id in generated_ids and attempts < 100:
                    persona = self.generate(constraints, archetype)
                    attempts += 1

                if persona.id in generated_ids:
                    # Append random suffix to force uniqueness
                    persona = AgentPersona(
                        **persona.model_dump(),
                        id=f"{persona.id}_{random.randint(1000, 9999)}",
                    )

            personas.append(persona)
            generated_ids.add(persona.id)

        return personas

    def _generate_name(self, constraints: PersonaConstraints) -> str:
        """Generate a random full name."""
        if self.config.first_names and self.config.last_names:
            first = random.choice(self.config.first_names)
            last = random.choice(self.config.last_names)
            return f"{first} {last}"
        else:
            # Fallback: generate simple names
            return f"Agent_{random.randint(100, 999)}"

    def _select_gender(self, constraints: PersonaConstraints) -> Optional[str]:
        """Select gender based on constraints."""
        if constraints.genders:
            return random.choice(constraints.genders).value
        return None

    def _select_nationality(self, constraints: PersonaConstraints) -> str:
        """Select nationality based on constraints."""
        pool = constraints.nationalities or self.config.nationalities
        return random.choice(pool) if pool else "Global"

    def _select_traits(
        self, constraints: PersonaConstraints, archetype: str
    ) -> List[str]:
        """Select traits combining archetype-specific and optional additional traits."""
        traits = []

        # Add archetype-specific traits
        archetype_traits = self.config.archetype_traits.get(archetype, [])
        if archetype_traits:
            num_traits = random.randint(2, 4)
            traits = random.sample(
                archetype_traits, min(num_traits, len(archetype_traits))
            )

        # Add any additional constraint traits
        if constraints.traits:
            additional = random.sample(
                constraints.traits, min(random.randint(1, 2), len(constraints.traits))
            )
            traits.extend(additional)

        return list(set(traits))  # Remove duplicates while preserving some order

    def _select_goals(
        self, constraints: PersonaConstraints, archetype: str
    ) -> List[str]:
        """Select goals based on archetype and constraints."""
        goals_pool = self.config.archetype_goals.get(archetype, [])
        if goals_pool:
            num_goals = random.randint(2, 3)
            goals = random.sample(goals_pool, min(num_goals, len(goals_pool)))
        else:
            goals = [f"Contribute effectively as a {archetype}"]

        # Add any constraint goals
        if constraints.background_categories:
            goals.append(random.choice(constraints.background_categories))

        return goals

    def _select_biases(self, constraints: PersonaConstraints) -> List[str]:
        """Select biases based on constraints."""
        bias_pool = constraints.bias_patterns or self.config.bias_patterns
        if bias_pool:
            num_biases = random.randint(0, 2)
            biases = random.sample(bias_pool, min(num_biases, len(bias_pool)))
        else:
            biases = []
        return biases

    def _select_communication_style(self, constraints: PersonaConstraints) -> str:
        """Select communication style based on constraints."""
        pool = constraints.communication_styles or self.config.communication_styles
        return random.choice(pool) if pool else "balanced"


# Export all public classes and enums
__all__ = [
    "PersonaGenerator",
    "PersonaGeneratorConfig",
    "PersonaConstraints",
    "Archetype",
    "Gender",
    "CommunicationStyle",
]
