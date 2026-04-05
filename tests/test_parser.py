"""
Tests for the SeedParser component.

Tests cover:
- Seed text parsing with mocked LLM responses
- JSON extraction and validation
- Error handling for invalid responses
- Batch parsing
- Fact key generation
- Title extraction
- Edge cases and malformed inputs
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from ralphfish.parser import SeedParser, EXTRACTION_PROMPT_TEMPLATE, parse_seed
from ralphfish.models import Scenario, Fact, AgentPersona
from ralphfish.client import OpenRouterClient


@pytest.fixture
def mock_client():
    """Create a mocked OpenRouter client."""
    client = MagicMock(spec=OpenRouterClient)
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def parser(mock_client):
    """Create a SeedParser instance with mocked client."""
    return SeedParser(client=mock_client)


@pytest.fixture
def sample_llm_response():
    """Sample valid LLM JSON response."""
    return {
        "entities": [
            {
                "name": "TechCorp",
                "type": "organization",
                "description": "Technology company",
            },
            {"name": "Alice", "type": "person", "description": "Project manager"},
        ],
        "relationships": [
            {"subject": "Alice", "predicate": "works_for", "object": "TechCorp"}
        ],
        "conflicts": [
            {
                "type": "goal_conflict",
                "parties": ["Alice", "Bob"],
                "description": "Budget vs quality",
            }
        ],
        "initial_facts": [
            "TechCorp has 100 employees",
            "Project deadline is December",
        ],
        "assumptions": ["Alice has budget authority", "Bob is the technical lead"],
    }


class TestSeedParserInitialization:
    """Test SeedParser initialization."""

    def test_parser_init_with_client(self, mock_client):
        """Test parser initializes with provided client."""
        parser = SeedParser(client=mock_client)
        assert parser.client == mock_client
        assert parser.prompt_template == EXTRACTION_PROMPT_TEMPLATE
        assert parser.model is None

    def test_parser_init_with_custom_prompt(self):
        """Test parser initializes with custom prompt template."""
        custom_template = "Custom prompt: {scenario_text}"
        parser = SeedParser(prompt_template=custom_template)
        assert parser.prompt_template == custom_template

    def test_parser_init_with_model(self, mock_client):
        """Test parser initializes with specific model."""
        parser = SeedParser(client=mock_client, model="anthropic/claude-instant-1.2")
        assert parser.model == "anthropic/claude-instant-1.2"


class TestParseMethod:
    """Test the main parse() method."""

    @pytest.mark.asyncio
    async def test_parse_successful(self, parser, mock_client, sample_llm_response):
        """Test successful parsing of seed text."""
        mock_client.chat_completion.return_value = {
            "content": json.dumps(sample_llm_response)
        }

        seed_text = "TechCorp is a technology company with 100 employees. Alice is the project manager."
        scenario = await parser.parse(
            seed_text, title="Test Scenario", context="Additional context"
        )

        assert isinstance(scenario, Scenario)
        assert scenario.seed_text == seed_text
        assert scenario.title == "Test Scenario"
        assert scenario.context == "Additional context"
        assert len(scenario.extracted_entities) == 2
        assert len(scenario.extracted_relationships) == 1
        assert len(scenario.initial_facts) == 2
        assert len(scenario.initial_facts[0].evidence) == 1

    @pytest.mark.asyncio
    async def test_parse_with_markdown_json(
        self, parser, mock_client, sample_llm_response
    ):
        """Test parsing when LLM wraps JSON in markdown code block."""
        json_str = json.dumps(sample_llm_response)
        wrapped = f"```json\n{json_str}\n```"

        mock_client.chat_completion.return_value = {"content": wrapped}

        scenario = await parser.parse("Test seed text")
        assert len(scenario.extracted_entities) == 2

    @pytest.mark.asyncio
    async def test_parse_with_plain_markdown(
        self, parser, mock_client, sample_llm_response
    ):
        """Test parsing when LLM uses plain markdown code block (no 'json' tag)."""
        json_str = json.dumps(sample_llm_response)
        wrapped = f"```\n{json_str}\n```"

        mock_client.chat_completion.return_value = {"content": wrapped}

        scenario = await parser.parse("Test seed text")
        assert len(scenario.extracted_entities) == 2

    @pytest.mark.asyncio
    async def test_parse_missing_required_keys(self, parser, mock_client):
        """Test that missing keys are handled gracefully with defaults."""
        incomplete_response = {
            "entities": [{"name": "Test", "type": "person"}],
            # Missing other keys
        }

        mock_client.chat_completion.return_value = {
            "content": json.dumps(incomplete_response)
        }

        # Should not raise; missing keys get empty lists
        scenario = await parser.parse("Test")
        # Provided entities should be present
        assert len(scenario.extracted_entities) == 1
        # Missing relationships and conflicts default to empty list
        assert scenario.extracted_relationships == []
        # initial_facts should be built from "initial_facts" key, missing -> empty list
        assert scenario.initial_facts == []  # Missing key defaults to empty list

    @pytest.mark.asyncio
    async def test_parse_invalid_json(self, parser, mock_client):
        """Test that invalid JSON raises ValueError."""
        mock_client.chat_completion.return_value = {"content": "Not valid JSON"}

        with pytest.raises(ValueError, match="Invalid JSON from LLM"):
            await parser.parse("Test")

    @pytest.mark.asyncio
    async def test_parse_malformed_json(self, parser, mock_client):
        """Test parsing with syntactically invalid JSON."""
        mock_client.chat_completion.return_value = {"content": '{"invalid": json}'}

        with pytest.raises(ValueError, match="Invalid JSON"):
            await parser.parse("Test")

    @pytest.mark.asyncio
    async def test_parse_empty_response(self, parser, mock_client):
        """Test handling of empty response."""
        mock_client.chat_completion.return_value = {"content": ""}

        with pytest.raises(ValueError, match="Invalid JSON"):
            await parser.parse("Test")

    @pytest.mark.asyncio
    async def test_fact_key_from_statement(self, parser):
        """Test the _fact_key_from_statement method."""
        # Test basic statement
        key = parser._fact_key_from_statement("The project deadline is December")
        assert key == "the_project_deadline_is"

        # Test with punctuation
        key = parser._fact_key_from_statement("TechCorp has 100 employees!")
        assert "techcorp" in key
        assert "employees" in key

        # Test very short statement
        key = parser._fact_key_from_statement("OK")
        assert len(key) > 0

        # Test empty-ish statement
        key = parser._fact_key_from_statement("...")
        assert key.isalnum() or key == "unnamed_fact"

    def test_extract_title(self, parser):
        """Test the _extract_title method."""
        # From first sentence
        text = "This is the title. More text follows."
        title = parser._extract_title(text)
        assert title == "This is the title"

        # Limit to max_words
        text = "One two three four five six seven eight nine ten"
        title = parser._extract_title(text, max_words=5)
        assert title == "One two three four five"

        # Empty-ish text
        title = parser._extract_title("")
        assert title == "Untitled Scenario"

        # Single word
        title = parser._extract_title("Hello")
        assert title == "Hello"

    @pytest.mark.asyncio
    async def test_parse_without_client_uses_simple_chat(self):
        """Test that parse without client falls back to simple_chat."""
        # We'll mock simple_chat instead of making real API call
        with patch(
            "ralphfish.parser.OpenRouterClient", new_callable=MagicMock
        ) as mock_client_cls:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client.chat_completion = AsyncMock(
                return_value={
                    "content": json.dumps(
                        {
                            "entities": [],
                            "relationships": [],
                            "conflicts": [],
                            "initial_facts": [],
                            "assumptions": [],
                        }
                    )
                }
            )
            mock_client_cls.return_value = mock_client

            await parse_seed("Test seed", api_key="test-key")

            # Should create config with provided api_key
            mock_client_cls.assert_called_once()
            config_arg = (
                mock_client_cls.call_args[0][0]
                if mock_client_cls.call_args[0]
                else mock_client_cls.call_args[1]["config"]
            )
            assert config_arg.api_key == "test-key"

            # Should close client at end
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_seed_with_kwargs(self):
        """Test parse_seed forwards kwargs to parser."""
        with patch("ralphfish.parser.OpenRouterClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_client.chat_completion = AsyncMock(
                return_value={
                    "content": json.dumps(
                        {
                            "entities": [],
                            "relationships": [],
                            "conflicts": [],
                            "initial_facts": [],
                            "assumptions": [],
                        }
                    )
                }
            )
            mock_client_cls.return_value = mock_client

            with patch.object(
                SeedParser, "parse", new_callable=AsyncMock
            ) as mock_parse:
                mock_parse.return_value = Scenario(seed_text="test")

                await parse_seed("Test", title="My Title", context="My Context")

                mock_parse.assert_called_once_with(
                    "Test", title="My Title", context="My Context"
                )


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_parse_with_extra_whitespace_in_json(
        self, parser, mock_client, sample_llm_response
    ):
        """Test that extra whitespace in JSON is handled."""
        json_str = json.dumps(sample_llm_response)
        spaced = f"\n{json_str}\n\n"
        mock_client.chat_completion.return_value = {"content": spaced}

        scenario = await parser.parse("Test")
        assert len(scenario.extracted_entities) == 2

    @pytest.mark.asyncio
    async def test_parse_with_trailing_commas_vulnerability(self, parser, mock_client):
        """Test that trailing commas in JSON would cause failure (not lenient)."""
        # The parser uses json.loads, which is strict
        # This test documents that behavior
        bad_json = '{"entities": [{"name": "Test"}],}'  # Trailing comma
        mock_client.chat_completion.return_value = {"content": bad_json}

        with pytest.raises(ValueError, match="Invalid JSON"):
            await parser.parse("Test")

    @pytest.mark.asyncio
    async def test_parse_with_unicode(self, parser, mock_client):
        """Test that unicode characters are handled."""
        unicode_response = {
            "entities": [
                {"name": "Café", "type": "place", "description": "French café"}
            ],
            "relationships": [],
            "conflicts": [],
            "initial_facts": ["The café serves coffee"],
            "assumptions": [],
        }
        mock_client.chat_completion.return_value = {
            "content": json.dumps(unicode_response)
        }

        scenario = await parser.parse("Test")
        assert "Café" in scenario.extracted_entities[0]["name"]

    @pytest.mark.asyncio
    async def test_parse_with_large_response(self, parser, mock_client):
        """Test parsing with many entities and facts."""
        large_response = {
            "entities": [
                {
                    "name": f"Entity{i}",
                    "type": "person",
                    "description": f"Description {i}",
                }
                for i in range(100)
            ],
            "relationships": [],
            "conflicts": [],
            "initial_facts": [f"Fact {i}" for i in range(50)],
            "assumptions": [f"Assumption {i}" for i in range(20)],
        }
        mock_client.chat_completion.return_value = {
            "content": json.dumps(large_response)
        }

        scenario = await parser.parse("Test")
        assert len(scenario.extracted_entities) == 100
        assert len(scenario.initial_facts) == 50

    @pytest.mark.asyncio
    async def test_parse_none_values_in_entities(self, parser, mock_client):
        """Test that None values in entity fields are handled."""
        weird_response = {
            "entities": [
                {"name": None, "type": None, "description": None},  # All None
                {"name": "Valid", "type": "person", "description": "Valid desc"},
            ],
            "relationships": [],
            "conflicts": [],
            "initial_facts": [],
            "assumptions": [],
        }
        mock_client.chat_completion.return_value = {
            "content": json.dumps(weird_response)
        }

        # Should not crash; Pydantic will validate
        scenario = await parser.parse("Test")
        assert len(scenario.extracted_entities) == 2

    @pytest.mark.asyncio
    async def test_parse_title_extraction_fallback(self, parser, mock_client):
        """Test title extraction when no title provided."""
        mock_client.chat_completion.return_value = {
            "content": json.dumps(
                {
                    "entities": [],
                    "relationships": [],
                    "conflicts": [],
                    "initial_facts": [],
                    "assumptions": [],
                }
            )
        }

        # No title provided, should extract from seed_text
        seed_text = "This is a very long scenario that goes on and on with many details and explanations."
        scenario = await parser.parse(seed_text)

        # Should extract first sentence or first few words
        assert scenario.title is not None
        assert len(scenario.title.split()) <= 10

    @pytest.mark.asyncio
    async def test_parse_with_multiple_markdown_blocks(
        self, parser, mock_client, sample_llm_response
    ):
        """Test that first code block is used when multiple present."""
        json_str = json.dumps(sample_llm_response)
        wrapped = (
            f"Some text\n```json\n{json_str}\n```\nMore text\n```\nignore this\n```"
        )

        mock_client.chat_completion.return_value = {"content": wrapped}

        scenario = await parser.parse("Test")
        assert len(scenario.extracted_entities) == 2  # Should use first block

    @pytest.mark.asyncio
    async def test_parse_with_relationship_missing_fields(self, parser, mock_client):
        """Test that relationships with missing fields are accepted."""
        response = {
            "entities": [],
            "relationships": [
                {"subject": "A"}  # Missing predicate and object
            ],
            "conflicts": [],
            "initial_facts": [],
            "assumptions": [],
        }
        mock_client.chat_completion.return_value = {"content": json.dumps(response)}

        # Should not crash; just store what's there
        scenario = await parser.parse("Test")
        assert len(scenario.extracted_relationships) == 1
        assert "subject" in scenario.extracted_relationships[0]


class TestPromptComposition:
    """Test prompt template and composition."""

    def test_default_prompt_template_structure(self):
        """Test that the default prompt template has expected placeholders."""
        assert "{scenario_text}" in EXTRACTION_PROMPT_TEMPLATE
        assert "entities" in EXTRACTION_PROMPT_TEMPLATE
        assert "relationships" in EXTRACTION_PROMPT_TEMPLATE
        assert "conflicts" in EXTRACTION_PROMPT_TEMPLATE
        assert "initial_facts" in EXTRACTION_PROMPT_TEMPLATE
        assert "assumptions" in EXTRACTION_PROMPT_TEMPLATE

    @pytest.mark.asyncio
    async def test_custom_prompt_used(self, mock_client):
        """Test that custom prompt template is used."""
        custom = "Analyze: {scenario_text}. Return JSON with key 'data'."
        parser = SeedParser(client=mock_client, prompt_template=custom)

        mock_client.chat_completion.return_value = {
            "content": json.dumps({"data": "test"})
        }

        # Should not raise; prompt will be different but should still work or fail gracefully
        # Actually the LLM might not return correct format, but that's fine for this test
        try:
            await parser.parse("Test")
        except:
            pass  # Expected if LLM doesn't follow non-standard prompt

        # Check that custom prompt was used
        call_args = mock_client.chat_completion.call_args
        messages = call_args[1]["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Analyze: Test" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_prompt_includes_scenario_text(self, parser, mock_client):
        """Test that the prompt includes the full scenario text."""
        mock_client.chat_completion.return_value = {
            "content": json.dumps(
                {
                    "entities": [],
                    "relationships": [],
                    "conflicts": [],
                    "initial_facts": [],
                    "assumptions": [],
                }
            )
        }

        seed = "This is a detailed scenario about a company decision."
        context = "Background: It's Q4 2024."
        await parser.parse(seed, context=context)

        call_args = mock_client.chat_completion.call_args
        messages = call_args[1]["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert seed in user_msg["content"]
        if context:
            assert context in user_msg["content"]
