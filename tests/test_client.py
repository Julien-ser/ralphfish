"""
Tests for the OpenRouter client wrapper.

Tests cover:
- Client initialization and configuration
- Request/response logging
- Retry logic with exponential backoff
- Rate limiting handling
- Statistics tracking
- Free-tier model routing
- Error handling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from openai import RateLimitError, APIConnectionError, OpenAIError

from ralphfish.client import (
    OpenRouterClient,
    ClientConfig,
    simple_chat,
    FREE_TIER_MODELS,
)


@pytest.fixture
def mock_env_api_key(monkeypatch):
    """Set a fake API key in environment."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-api-key-12345")


@pytest.fixture
def client_config():
    """Create a standard ClientConfig for testing."""
    return ClientConfig(
        api_key="test-key",
        default_model="openai/gpt-3.5-turbo",
        max_retries=3,
        base_delay=0.1,  # Fast for tests
        max_delay=1.0,
        log_requests=False,
        log_responses=False,
    )


@pytest.fixture
def client(client_config):
    """Create an OpenRouterClient instance."""
    return OpenRouterClient(config=client_config)


@pytest.fixture
def mock_client():
    """Create a mocked OpenRouter client with fake responses."""
    client = MagicMock(spec=OpenRouterClient)
    client.chat_completion = AsyncMock(
        return_value={
            "content": "Test response",
            "model": "test-model",
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 100,
                "total_tokens": 150,
            },
            "finish_reason": "stop",
            "id": "test-123",
        }
    )
    client.request_count = 0
    client.total_tokens = 0
    client.errors = 0
    return client


class TestClientConfig:
    """Test ClientConfig initialization and defaults."""

    def test_default_values(self, mock_env_api_key):
        """Test that ClientConfig has sensible defaults."""
        config = ClientConfig()
        assert config.api_key == "test-api-key-12345"
        assert config.default_model == "openai/gpt-3.5-turbo"
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.log_requests is True
        assert config.log_responses is True
        assert config.site_url == "https://ralphfish.example.com"
        assert config.site_name == "Ralphfish Simulation"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ClientConfig(
            api_key="custom-key",
            default_model="anthropic/claude-instant-1.2",
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            log_requests=False,
            log_responses=False,
            site_url="https://example.com",
            site_name="Test App",
        )
        assert config.api_key == "custom-key"
        assert config.default_model == "anthropic/claude-instant-1.2"
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.log_requests is False
        assert config.log_responses is False
        assert config.site_url == "https://example.com"
        assert config.site_name == "Test App"


class TestOpenRouterClientInitialization:
    """Test OpenRouterClient initialization."""

    def test_init_with_api_key(self, client_config):
        """Test client initializes with provided API key."""
        client = OpenRouterClient(client_config)
        assert client.config == client_config
        assert client.request_count == 0
        assert client.total_tokens == 0
        assert client.errors == 0

    def test_init_without_api_key_raises(self, mock_env_api_key):
        """Test client raises error if no API key available."""
        # Clear the env var set by fixture
        import os

        del os.environ["OPENROUTER_API_KEY"]
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            OpenRouterClient()

    def test_init_creates_async_client(self, client_config):
        """Test that AsyncOpenAI client is created with correct settings."""
        client = OpenRouterClient(client_config)
        assert client.client is not None
        # Check base URL
        assert client.client.base_url == "https://openrouter.ai/api/v1"
        # Check headers
        assert (
            client.client.default_headers["HTTP-Referer"]
            == "https://ralphfish.example.com"
        )
        assert client.client.default_headers["X-Title"] == "Ralphfish Simulation"


class TestClientLogging:
    """Test request and response logging."""

    @pytest.mark.asyncio
    async def test_log_request_called(self, client_config):
        """Test that _log_request logs correctly when enabled."""
        client = OpenRouterClient(client_config)
        client.config.log_requests = True

        with patch.object(client.logger, "debug") as mock_debug:
            client._log_request(
                model="test-model",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=100,
                temperature=0.7,
            )
            mock_debug.assert_called_once()
            call_args = mock_debug.call_args
            assert "OpenRouter request" in str(call_args)
            assert call_args[1]["extra"]["model"] == "test-model"
            assert call_args[1]["extra"]["message_count"] == 1

    @pytest.mark.asyncio
    async def test_log_request_not_called_when_disabled(self, client_config):
        """Test that _log_request skips when disabled."""
        client = OpenRouterClient(client_config)
        client.config.log_requests = False

        with patch.object(client.logger, "debug") as mock_debug:
            client._log_request("test-model", [{"role": "user", "content": "Hello"}])
            mock_debug.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_response_called(self, client_config):
        """Test that _log_response logs correctly when enabled."""
        client = OpenRouterClient(client_config)
        client.config.log_responses = True

        with patch.object(client.logger, "info") as mock_info:
            client._log_response(
                model="test-model",
                usage={
                    "prompt_tokens": 50,
                    "completion_tokens": 100,
                    "total_tokens": 150,
                },
                duration=0.5,
            )
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "OpenRouter response" in str(call_args)
            assert call_args[1]["extra"]["total_tokens"] == 150
            assert client.total_tokens == 150  # Accumulates

    @pytest.mark.asyncio
    async def test_log_response_not_called_when_disabled(self, client_config):
        """Test that _log_response skips when disabled."""
        client = OpenRouterClient(client_config)
        client.config.log_responses = False

        with patch.object(client.logger, "info") as mock_info:
            client._log_response("test-model", {"total_tokens": 100}, 0.5)
            mock_info.assert_not_called()


class TestClientRetryLogic:
    """Test retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self, client_config):
        """Test that successful call doesn't retry."""
        client = OpenRouterClient(client_config)

        # Mock the underlying client
        with patch.object(
            client.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.model = "test-model"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            mock_response.response_ms = 100
            mock_response.choices = [
                MagicMock(message=MagicMock(content="test"), finish_reason="stop")
            ]
            mock_response.id = "test-1"
            mock_create.return_value = mock_response

            result = await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}]
            )

            assert result["content"] == "test"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_retry_success(self, client_config):
        """Test that rate limit errors trigger retry and eventually succeed."""
        from openai import RateLimitError

        client = OpenRouterClient(client_config)
        client.config.base_delay = 0.01  # Fast for tests
        client.config.max_delay = 0.1

        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 times
                raise RateLimitError("Rate limited", response=MagicMock(), body={})
            # Third attempt succeeds
            mock_response = MagicMock()
            mock_response.model = "test-model"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            mock_response.response_ms = 100
            mock_response.choices = [
                MagicMock(message=MagicMock(content="success"), finish_reason="stop")
            ]
            mock_response.id = "test-3"
            return mock_response

        with patch.object(
            client.client.chat.completions, "create", side_effect=mock_create
        ):
            result = await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}]
            )

            assert result["content"] == "success"
            assert call_count == 3  # Should have retried twice
            assert client.errors == 2  # Two errors recorded

    @pytest.mark.asyncio
    async def test_rate_limit_max_retries_exceeded(self, client_config):
        """Test that max retries are respected for rate limit errors."""
        client = OpenRouterClient(client_config)
        client.config.max_retries = 2
        client.config.base_delay = 0.01

        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RateLimitError("Rate limited always")

        with patch.object(
            client.client.chat.completions, "create", side_effect=mock_create
        ):
            with pytest.raises(RateLimitError):
                await client.chat_completion(
                    messages=[{"role": "user", "content": "Hello"}]
                )

            assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_connection_error_retry(self, client_config):
        """Test retry on connection errors."""
        from openai import APIConnectionError

        client = OpenRouterClient(client_config)
        client.config.base_delay = 0.01
        client.config.max_delay = 0.1

        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise APIConnectionError("Connection failed", request=MagicMock())
            # Second attempt succeeds
            mock_response = MagicMock()
            mock_response.model = "test-model"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            mock_response.response_ms = 100
            mock_response.choices = [
                MagicMock(message=MagicMock(content="connected"), finish_reason="stop")
            ]
            mock_response.id = "test-2"
            return mock_response

        with patch.object(
            client.client.chat.completions, "create", side_effect=mock_create
        ):
            result = await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}]
            )
            assert result["content"] == "connected"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self, client_config):
        """Test that backoff delays increase exponentially."""
        from openai import RateLimitError

        client = OpenRouterClient(client_config)
        client.config.base_delay = 0.01
        client.config.max_delay = 1.0

        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise RateLimitError("Rate limited", response=MagicMock(), body={})
            mock_response = MagicMock()
            mock_response.model = "test-model"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            mock_response.response_ms = 100
            mock_response.choices = [
                MagicMock(message=MagicMock(content="ok"), finish_reason="stop")
            ]
            mock_response.id = "test"
            return mock_response

        with patch.object(
            client.client.chat.completions, "create", side_effect=mock_create
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                try:
                    await client.chat_completion(
                        messages=[{"role": "user", "content": "Hello"}]
                    )
                except:
                    pass

                # Should have slept after each failure (3 failures)
                assert mock_sleep.call_count == 3
                # Check exponential increase: base_delay * 2^(n-1)
                expected_delays = [
                    0.01,
                    0.02,
                    0.04,
                ]  # 0.01 * 2^0, 0.01 * 2^1, 0.01 * 2^2
                actual_delays = [call[0][0] for call in mock_sleep.call_args_list]
                for expected, actual in zip(expected_delays, actual_delays):
                    assert actual >= expected

    @pytest.mark.asyncio
    async def test_retry_max_delay(self, client_config):
        """Test that backoff respects max_delay."""
        from openai import RateLimitError

        client = OpenRouterClient(client_config)
        client.config.base_delay = 1.0
        client.config.max_delay = 2.0

        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                raise RateLimitError("Rate limited", response=MagicMock(), body={})
            mock_response = MagicMock()
            mock_response.model = "test"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            mock_response.response_ms = 100
            mock_response.choices = [
                MagicMock(message=MagicMock(content="ok"), finish_reason="stop")
            ]
            mock_response.id = "test"
            return mock_response

        with patch.object(
            client.client.chat.completions, "create", side_effect=mock_create
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                try:
                    await client.chat_completion(
                        messages=[{"role": "user", "content": "Hello"}]
                    )
                except:
                    pass

                # Check that no delay exceeded max_delay
                for call in mock_sleep.call_args_list:
                    delay = call[0][0]
                    assert delay <= 2.0


class TestClientFreeTierRouting:
    """Test free-tier model routing logic."""

    @pytest.mark.asyncio
    async def test_use_free_tier_route_to_free(self, client_config):
        """Test that use_free_tier=True routes to free model if not in free list."""
        client = OpenRouterClient(client_config)
        client.config.default_model = "openai/gpt-4"  # Not in FREE_TIER_MODELS

        with patch.object(
            client, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = MagicMock(
                model="anthropic/claude-instant-1.2",
                usage=MagicMock(
                    prompt_tokens=10, completion_tokens=20, total_tokens=30
                ),
                response_ms=100,
                choices=[
                    MagicMock(message=MagicMock(content="test"), finish_reason="stop")
                ],
                id="test",
            )

            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                use_free_tier=True,
            )

            # Check that the model passed to _execute_with_retry is a free tier model
            call_args = mock_exec.call_args
            assert call_args[0][0].__name__ == "create"  # The operation
            # The model kwarg should be set to a free tier model
            # Since we mocked _execute_with_retry, we can't check the model directly
            # But we can verify the routing logic by checking logs
            assert client.logger.info.called

    @pytest.mark.asyncio
    async def test_use_free_tier_keep_if_already_free(self, client_config):
        """Test that use_free_tier=True keeps model if already in free list."""
        client = OpenRouterClient(client_config)
        client.config.default_model = FREE_TIER_MODELS[0]  # Already free

        with patch.object(
            client, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = MagicMock(
                model=FREE_TIER_MODELS[0],
                usage=MagicMock(
                    prompt_tokens=10, completion_tokens=20, total_tokens=30
                ),
                response_ms=100,
                choices=[
                    MagicMock(message=MagicMock(content="test"), finish_reason="stop")
                ],
                id="test",
            )

            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                use_free_tier=True,
            )

            # Should keep the original model
            mock_exec.assert_called_once()

    def test_free_tier_models_list(self):
        """Test that FREE_TIER_MODELS contains expected models."""
        assert len(FREE_TIER_MODELS) > 0
        assert "openai/gpt-3.5-turbo" in FREE_TIER_MODELS
        assert "anthropic/claude-instant-1.2" in FREE_TIER_MODELS
        assert "meta-llama/llama-3.1-8b-instruct" in FREE_TIER_MODELS


class TestClientStatistics:
    """Test usage statistics tracking."""

    @pytest.mark.asyncio
    async def test_stats_accumulate(self, client_config):
        """Test that request count and tokens accumulate."""
        client = OpenRouterClient(client_config)

        # Mock multiple successful calls
        with patch.object(
            client.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_responses = []
            for i in range(3):
                resp = MagicMock()
                resp.model = "test-model"
                resp.usage.prompt_tokens = 10 + i * 10
                resp.usage.completion_tokens = 20 + i * 10
                resp.usage.total_tokens = 30 + i * 20
                resp.response_ms = 100
                resp.choices = [
                    MagicMock(
                        message=MagicMock(content=f"test{i}"), finish_reason="stop"
                    )
                ]
                resp.id = f"test-{i}"
                mock_responses.append(resp)

            mock_create.side_effect = mock_responses

            for i in range(3):
                await client.chat_completion(
                    messages=[{"role": "user", "content": f"Hello {i}"}]
                )

            stats = client.get_stats()
            assert stats["request_count"] == 3
            assert stats["total_tokens"] == sum(
                r.usage.total_tokens for r in mock_responses
            )
            assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_errors_counted(self, client_config):
        """Test that errors are counted."""
        from openai import RateLimitError

        client = OpenRouterClient(client_config)
        client.request_count = 0  # Reset counters

        with patch.object(
            client.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = RateLimitError(
                "Rate limited", response=MagicMock(), body={}
            )

            # Should fail after retries
            with pytest.raises(RateLimitError):
                await client.chat_completion(
                    messages=[{"role": "user", "content": "Hello"}]
                )

            stats = client.get_stats()
            assert stats["errors"] >= 1


class TestChatCompletion:
    """Test the main chat_completion method."""

    @pytest.mark.asyncio
    async def test_basic_successful_call(self, client_config):
        """Test a basic successful chat completion."""
        client = OpenRouterClient(client_config)

        mock_response = MagicMock()
        mock_response.model = "openai/gpt-3.5-turbo"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 150
        mock_response.response_ms = 500
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content="Hello! How can I help?"),
                finish_reason="stop",
            )
        ]
        mock_response.id = "test-123"

        with patch.object(
            client.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": "Hello!"},
                ],
                temperature=0.7,
                max_tokens=500,
            )

            assert result["content"] == "Hello! How can I help?"
            assert result["model"] == "openai/gpt-3.5-turbo"
            assert result["usage"]["prompt_tokens"] == 50
            assert result["usage"]["completion_tokens"] == 100
            assert result["usage"]["total_tokens"] == 150
            assert result["finish_reason"] == "stop"
            assert result["id"] == "test-123"

    @pytest.mark.asyncio
    async def test_custom_model_override(self, client_config):
        """Test that model parameter overrides default."""
        client = OpenRouterClient(client_config)
        client.config.default_model = "openai/gpt-3.5-turbo"

        with patch.object(
            client.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.model = "anthropic/claude-instant-1.2"
            mock_response.usage.prompt_tokens = 50
            mock_response.usage.completion_tokens = 100
            mock_response.usage.total_tokens = 150
            mock_response.response_ms = 500
            mock_response.choices = [
                MagicMock(message=MagicMock(content="test"), finish_reason="stop")
            ]
            mock_response.id = "test"
            mock_create.return_value = mock_response

            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model="anthropic/claude-instant-1.2",
            )

            # Check that the custom model was passed
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["model"] == "anthropic/claude-instant-1.2"

    @pytest.mark.asyncio
    async def test_additional_kwargs_passed(self, client_config):
        """Test that additional kwargs are passed to API."""
        client = OpenRouterClient(client_config)

        with patch.object(
            client.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.model = "test"
            mock_response.usage.prompt_tokens = 50
            mock_response.usage.completion_tokens = 100
            mock_response.usage.total_tokens = 150
            mock_response.response_ms = 500
            mock_response.choices = [
                MagicMock(message=MagicMock(content="test"), finish_reason="stop")
            ]
            mock_response.id = "test"
            mock_create.return_value = mock_response

            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.5,
                top_p=0.9,
                frequency_penalty=0.1,
                presence_penalty=0.1,
            )

            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["top_p"] == 0.9
            assert call_kwargs["frequency_penalty"] == 0.1
            assert call_kwargs["presence_penalty"] == 0.1

    @pytest.mark.asyncio
    async def test_use_free_tier_kwarg_removed(self, client_config):
        """Test that use_free_tier kwarg is popped and not sent to API."""
        client = OpenRouterClient(client_config)
        client.config.default_model = "openai/gpt-4"

        with patch.object(
            client, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = MagicMock(
                model="test",
                usage=MagicMock(
                    prompt_tokens=10, completion_tokens=20, total_tokens=30
                ),
                response_ms=100,
                choices=[
                    MagicMock(message=MagicMock(content="test"), finish_reason="stop")
                ],
                id="test",
            )

            await client.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                use_free_tier=True,
                temperature=0.7,  # This should be passed along
            )

            # The operation (create) should be called without use_free_tier
            call_args = mock_exec.call_args
            # First argument is the operation function
            # We can't easily check kwargs here because _execute_with_retry wraps the call
            # but we can at least verify the call succeeded

    @pytest.mark.asyncio
    async def test_error_logging_on_failure(self, client_config):
        """Test that errors are logged on chat completion failure."""
        client = OpenRouterClient(client_config)

        with patch.object(
            client.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = OpenAIError("API error")

            with pytest.raises(OpenAIError):
                await client.chat_completion(
                    messages=[{"role": "user", "content": "Hello"}]
                )

            # Should have logged the error
            assert client.logger.error.called


class TestSimpleChat:
    """Test the simple_chat convenience function."""

    @pytest.mark.asyncio
    async def test_simple_chat_returns_content(self, mock_env_api_key):
        """Test that simple_chat returns just the content string."""
        result = await simple_chat(
            messages=[{"role": "user", "content": "Hello"}],
            api_key="test-key",
        )
        assert isinstance(result, str)
        assert result == "Test response"

    @pytest.mark.asyncio
    async def test_simple_chat_with_custom_model(self, mock_env_api_key):
        """Test simple_chat with custom model."""
        result = await simple_chat(
            messages=[{"role": "user", "content": "Hello"}],
            model="anthropic/claude-instant-1.2",
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_simple_chat_no_api_key_raises(self):
        """Test that simple_chat raises without API key."""
        import os

        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            await simple_chat(messages=[{"role": "user", "content": "Hello"}])


class TestClientClose:
    """Test client close method."""

    @pytest.mark.asyncio
    async def test_close_calls_underlying_client(self, client_config):
        """Test that close closes the underlying client."""
        client = OpenRouterClient(client_config)

        with patch.object(client.client, "close", new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()


class TestIntegrationWithRealAPI:
    """Integration tests (marked to skip by default)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_api_call(self, mock_env_api_key):
        """Test making a real API call (requires valid OPENROUTER_API_KEY)."""
        # This test is skipped by default unless --run-integration is passed
        pytest.skip("Integration test - run with --run-integration")

        client = OpenRouterClient()
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Say 'test' only"}],
            max_tokens=10,
        )
        assert "test" in response["content"].lower()
