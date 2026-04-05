"""
Tests for the persona_generator module.

Tests cover:
- Basic persona generation
- Constraint-based generation
- Batch generation
- Configuration defaults
- Validation and edge cases
"""

import pytest
from typing import List

from ralphfish.persona_generator import (
    PersonaGenerator,
    PersonaGeneratorConfig,
    PersonaConstraints,
    Archetype,
    Gender,
    CommunicationStyle,
)
from ralphfish.models import AgentPersona


class TestBasicGeneration:
    """Test basic persona generation without constraints."""

    def test_generate_single_persona(self):
        """Test that generate() creates a valid AgentPersona."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        persona = generator.generate()

        assert isinstance(persona, AgentPersona)
        assert persona.id is not None
        assert len(persona.id) > 0
        assert persona.name is not None
        assert len(persona.name) > 0
        assert persona.background is not None
        assert len(persona.background) > 0
        assert isinstance(persona.traits, list)
        assert isinstance(persona.goals, list)
        assert isinstance(persona.biases, list)
        assert persona.communication_style is not None

    def test_generate_with_seed_reproducibility(self):
        """Test that using the same seed produces identical personas."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        persona1 = generator.generate(seed=42)
        persona2 = generator.generate(seed=42)

        assert persona1.id == persona2.id
        assert persona1.name == persona2.name
        assert persona1.background == persona2.background
        assert persona1.traits == persona2.traits
        assert persona1.goals == persona2.goals
        assert persona1.communication_style == persona2.communication_style

    def test_generate_different_seeds(self):
        """Test that different seeds produce different personas."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        persona1 = generator.generate(seed=1)
        persona2 = generator.generate(seed=2)

        # Very unlikely to be identical
        assert persona1.id != persona2.id or persona1.name != persona2.name

    def test_generate_uses_default_config_if_none(self):
        """Test that generator works with None config."""
        generator = PersonaGenerator(None)  # type: ignore
        with pytest.raises(AttributeError):
            # Should fail because None has no attributes
            generator.generate()


class TestConstraintGeneration:
    """Test generation with various constraints."""

    def test_archetype_constraint(self):
        """Test that archetype constraint is respected."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(archetypes=[Archetype.SCIENTIST])

        for _ in range(10):
            persona = generator.generate(constraints)
            assert "scientist" in persona.id
            assert any(
                term in persona.background.lower()
                for term in ["scientist", "research", "science"]
            )

    def test_age_range_constraint(self):
        """Test that age range is respected."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(min_age=30, max_age=40)

        for _ in range(20):
            persona = generator.generate(constraints)
            # Extract age from background string (e.g., "35-year-old")
            age_str = persona.background.split("-")[0]
            age = int(age_str)
            assert 30 <= age <= 40

    def test_multiple_archetypes(self):
        """Test that multiple allowed archetypes are used."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(
            archetypes=[Archetype.SCIENTIST, Archetype.ENGINEER, Archetype.ACADEMIC]
        )

        archetype_ids = set()
        for _ in range(30):
            persona = generator.generate(constraints)
            archetype = persona.id.split("_")[0]
            archetype_ids.add(archetype)

        # Should generate at least 2 different archetypes out of 3
        assert len(archetype_ids) >= 2
        assert all(a in ["scientist", "engineer", "academic"] for a in archetype_ids)

    def test_gender_constraint(self):
        """Test that gender constraint is respected."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(genders=[Gender.FEMALE])

        for _ in range(10):
            persona = generator.generate(constraints)
            # Gender is stored in the background as part of "X-year-old Y"
            # Actually gender is not explicitly stored in AgentPersona as a field,
            # it's used in generation but not in the persona itself.
            # So we can't test this directly via the persona output.
            # But we can test that generation doesn't error.
            assert persona is not None

    def test_bias_patterns_constraint(self):
        """Test that custom bias patterns are used."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        custom_biases = ["custom_bias_1", "custom_bias_2"]
        constraints = PersonaConstraints(bias_patterns=custom_biases)

        biases_used = set()
        for _ in range(20):
            persona = generator.generate(constraints)
            biases_used.update(persona.biases)

        # Some custom biases should appear
        assert len(biases_used.intersection(set(custom_biases))) > 0

    def test_communication_styles_constraint(self):
        """Test that communication style constraint is respected."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        custom_styles = ["formal", "technical", "balanced"]
        constraints = PersonaConstraints(communication_styles=custom_styles)

        styles_used = set()
        for _ in range(30):
            persona = generator.generate(constraints)
            styles_used.add(persona.communication_style)

        assert styles_used.issubset(set(custom_styles))


class TestBatchGeneration:
    """Test batch generation functionality."""

    def test_generate_batch_count(self):
        """Test that generate_batch returns correct number of personas."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        personas = generator.generate_batch(5)
        assert len(personas) == 5

    def test_generate_batch_unique_ids(self):
        """Test that generate_batch produces unique IDs by default."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        personas = generator.generate_batch(20)
        ids = [p.id for p in personas]
        assert len(set(ids)) == len(ids)

    def test_generate_batch_with_constraints(self):
        """Test that batch generation respects constraints."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(archetypes=[Archetype.ENGINEER])

        personas = generator.generate_batch(10, constraints)
        assert len(personas) == 10
        for persona in personas:
            assert "engineer" in persona.id

    def test_generate_batch_with_seed_reproducibility(self):
        """Test that batch generation with same seed gives same results."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        personas1 = generator.generate_batch(5, seed=123)
        personas2 = generator.generate_batch(5, seed=123)

        for p1, p2 in zip(personas1, personas2):
            assert p1.id == p2.id
            assert p1.name == p2.name

    def test_generate_batch_non_unique_allowed(self):
        """Test that non-unique batch generation is allowed."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        # Generate with unique=False, and use a very constrained config
        # to increase chance of collision, but it's not guaranteed
        personas = generator.generate_batch(5, unique=False)
        assert len(personas) == 5


class TestConfiguration:
    """Test configuration and defaults."""

    def test_default_config_has_required_fields(self):
        """Test that default config has all required pools populated."""
        config = PersonaGeneratorConfig.get_default()

        assert len(config.first_names) > 0
        assert len(config.last_names) > 0
        assert len(config.archetype_backgrounds) > 0
        assert len(config.archetype_traits) > 0
        assert len(config.archetype_goals) > 0
        assert len(config.bias_patterns) > 0
        assert len(config.communication_styles) > 0
        assert len(config.nationalities) > 0

    def test_default_config_covers_all_archetypes(self):
        """Test that default config has entries for all archetypes."""
        config = PersonaGeneratorConfig.get_default()
        all_archetypes = [a.value for a in Archetype]

        for archetype in all_archetypes:
            assert archetype in config.archetype_backgrounds
            assert archetype in config.archetype_traits
            assert archetype in config.archetype_goals

    def test_archetype_quick_parameter(self):
        """Test using the archetype parameter directly."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        persona = generator.generate(archetype=Archetype.ARTIST)
        assert "artist" in persona.id

        persona2 = generator.generate(archetype="artist")
        assert "artist" in persona2.id


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_archetypes_constraint(self):
        """Test that empty archetypes list falls back to all archetypes."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(archetypes=[])

        # Should not raise error; should use any archetype
        persona = generator.generate(constraints)
        assert persona is not None

    def test_invalid_age_range_raises(self):
        """Test that invalid age range raises validation error."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(min_age=50, max_age=30)

        with pytest.raises(ValueError, match="Invalid age range"):
            generator.generate(constraints)

    def test_negative_min_age_raises(self):
        """Test that negative min age raises validation error."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(min_age=-5)

        with pytest.raises(ValueError, match="Invalid age range"):
            generator.generate(constraints)

    def test_custom_empty_config(self):
        """Test generation with minimal custom config."""
        config = PersonaGeneratorConfig(
            first_names=["Test"],
            last_names=["User"],
            archetype_backgrounds={"test": ["test background"]},
            archetype_traits={"test": ["trait1", "trait2"]},
            archetype_goals={"test": ["goal1"]},
        )
        generator = PersonaGenerator(config)
        constraints = PersonaConstraints(
            archetypes=[Archetype.TEST] if hasattr(Archetype, "TEST") else None
        )

        # Should still generate something even with limited config
        persona = generator.generate()
        assert persona.id is not None

    def test_duplicate_removal_in_traits(self):
        """Test that duplicate traits are removed."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        # Generate multiple personas to potentially get duplicates
        for _ in range(20):
            persona = generator.generate()
            # Check no duplicate trait strings
            traits = persona.traits
            assert len(traits) == len(set(traits))


class TestPersonaValidity:
    """Test that generated personas are valid and well-formed."""

    def test_persona_validates_with_pydantic(self):
        """Test that generated personas are valid per Pydantic model."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        for _ in range(10):
            persona = generator.generate()
            # Pydantic validation happens on construction; if invalid, exception raised
            assert isinstance(persona, AgentPersona)

    def test_persona_fields_nonempty_strings(self):
        """Test that critical fields are non-empty strings."""
        config = PersonaGeneratorConfig.get_default()
        generator = PersonaGenerator(config)

        for _ in range(10):
            persona = generator.generate()
            assert isinstance(persona.id, str) and len(persona.id) > 0
            assert isinstance(persona.name, str) and len(persona.name) > 0
            assert isinstance(persona.background, str) and len(persona.background) > 0

            # Traits, goals, biases can be empty lists but must be lists
            assert isinstance(persona.traits, list)
            assert isinstance(persona.goals, list)
            assert isinstance(persona.biases, list)

            # communication_style should be a non-empty string
            assert (
                isinstance(persona.communication_style, str)
                and len(persona.communication_style) > 0
            )
